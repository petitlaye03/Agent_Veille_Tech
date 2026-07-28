"""Connecteur de scraping HTML (AD-2).

Respecte le contrat `fetch(source_config) -> list[Item]` commun à tous les
connecteurs. Réservé aux sources sans flux ni API — et seulement lorsque
le `robots.txt` de la cible l'autorise (AD-10).

**Choix d'extraction délibéré** : l'analyse s'appuie exclusivement sur des
balises sémantiques (`h2`/`h3`/`h4`, `time`, `p`) et jamais sur les classes
CSS. Les sites modernes génèrent des noms de classes hachés qui changent à
chaque build — s'y fier casserait le connecteur en silence.
"""

import logging
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from urllib.request import url2pathname

import httpx
from bs4 import BeautifulSoup

from veille.config import SourceConfig
from veille.models import Item

logger = logging.getLogger(__name__)

TIMEOUT_SECONDES = 30
# ASCII uniquement : les en-têtes HTTP n'acceptent pas les caractères accentués.
USER_AGENT = "veille-ia/0.1 (personal news aggregator)"

# Formats de date rencontrés sur les pages d'actualité, du plus au moins courant.
FORMATS_DATE = ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%d %B %Y")


def fetch(source_config: SourceConfig) -> list[Item]:
    """Récupère une page HTML et en extrait des `Item` canoniques.

    Une entrée sans titre exploitable est ignorée : mieux vaut perdre une
    ligne que publier un item vide.
    """
    html = _charger(source_config.url)
    soup = BeautifulSoup(html, "html.parser")

    items: list[Item] = []
    vus: set[str] = set()

    for ancre in soup.find_all("a", href=True):
        href = ancre["href"]
        if source_config.selecteur and source_config.selecteur not in href:
            continue

        url = urljoin(source_config.base_url, href)
        if url in vus:
            continue

        try:
            item = _to_item(ancre, url, source_config)
        except ValueError as e:
            logger.debug("Lien ignoré (%s) : %s", href, e)
            continue
        except Exception:  # noqa: BLE001 — isolation au niveau de l'entrée
            logger.warning("Lien ignoré (%s) dans '%s'.", href, source_config.id, exc_info=True)
            continue

        vus.add(url)
        items.append(item)

    if not items:
        logger.warning(
            "Aucun item extrait de '%s' — la structure de la page a peut-être changé.",
            source_config.id,
        )

    return items


def _charger(url: str) -> str:
    """Lit la page, depuis le réseau ou depuis un fichier local (tests)."""
    if url.startswith("file://"):
        chemin = url2pathname(urlparse(url).path)
        with open(chemin, encoding="utf-8") as f:
            return f.read()

    reponse = httpx.get(
        url,
        timeout=TIMEOUT_SECONDES,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )
    reponse.raise_for_status()
    return reponse.text


def _to_item(ancre, url: str, source_config: SourceConfig) -> Item:
    titre = _extraire_titre(ancre)
    if not titre:
        raise ValueError("aucun titre exploitable")

    return Item(
        source_id=source_config.id,
        # La page n'expose pas d'identifiant natif : l'URL canonique fait office
        # d'identité, conformément à la convention (identifiant natif > URL > hash).
        guid=url,
        titre=titre,
        date_publication=_extraire_date(ancre),
        langue=source_config.langue,
        registre=source_config.registre,
        url=url,
        contenu_brut=_extraire_extrait(ancre),
    )


def _extraire_titre(ancre) -> str:
    """Extrait le titre, avec un repli structurel quand aucun titre sémantique n'existe.

    Deux formes coexistent sur une même page d'actualité : les articles mis
    en avant portent un vrai titre (`h2`/`h3`), les articles courants le
    placent dans un simple `span`. Le repli distingue ce titre des
    métadonnées (date, catégorie) par leur position dans le DOM plutôt que
    par leurs classes CSS, qui sont générées et instables.
    """
    balise = ancre.find(["h1", "h2", "h3", "h4"])
    if balise:
        titre = balise.get_text(" ", strip=True)
        if titre:
            return titre

    # Le bloc de métadonnées est identifié par la balise <time> qu'il contient.
    horodatage = ancre.find("time")
    bloc_meta = horodatage.find_parent() if horodatage else None
    spans_meta = set()
    if bloc_meta is not None:
        spans_meta = {id(s) for s in bloc_meta.find_all("span")}

    for span in ancre.find_all("span"):
        if id(span) in spans_meta:
            continue
        texte = span.get_text(" ", strip=True)
        if texte:
            return texte

    return ""


def _extraire_date(ancre) -> datetime:
    balise = ancre.find("time")
    if balise is None:
        return datetime.now(timezone.utc)

    # L'attribut datetime, s'il existe, est plus fiable que le texte affiché.
    brut = balise.get("datetime") or balise.get_text(" ", strip=True)

    for format_date in FORMATS_DATE:
        try:
            return datetime.strptime(brut, format_date).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(brut.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        logger.debug("Date illisible (%r) — horodatage à la collecte.", brut)
        return datetime.now(timezone.utc)


def _extraire_extrait(ancre) -> str:
    balise = ancre.find("p")
    return balise.get_text(" ", strip=True) if balise else ""
