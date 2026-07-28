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
import re
from datetime import datetime, timezone
from urllib import robotparser
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.request import url2pathname

import httpx
from bs4 import BeautifulSoup

from veille.config import SourceConfig
from veille.models import Item

logger = logging.getLogger(__name__)

TIMEOUT_SECONDES = 30
# ASCII uniquement : les en-têtes HTTP n'acceptent pas les caractères accentués.
USER_AGENT = "veille-ia/0.1 (personal news aggregator)"

# Mois anglais résolus par table explicite plutôt que par `%b`/`%B` : ces
# directives dépendent de la locale du processus, si bien que sur un système
# en français toutes les dates échoueraient silencieusement et seraient
# remplacées par l'heure de collecte.
MOIS_ANGLAIS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Formats indépendants de la locale (chiffres uniquement).
FORMATS_DATE_NUMERIQUES = ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d")

# Libellés d'appel à l'action à ne pas confondre avec un chapeau d'article.
LONGUEUR_MIN_EXTRAIT = 30
LIBELLES_ACTION = frozenset(
    {"read more", "lire la suite", "en savoir plus", "learn more", "read", "more"}
)

# « Jul 24, 2026 » ou « 24 July 2026 »
MOTIF_MOIS_JOUR_ANNEE = re.compile(
    r"(?P<mois>[A-Za-z]{3,9})\.?\s+(?P<jour>\d{1,2})(?:st|nd|rd|th)?,?\s+(?P<annee>\d{4})"
)
MOTIF_JOUR_MOIS_ANNEE = re.compile(
    r"(?P<jour>\d{1,2})\s+(?P<mois>[A-Za-z]{3,9})\.?,?\s+(?P<annee>\d{4})"
)


def fetch(source_config: SourceConfig) -> list[Item]:
    """Récupère une page HTML et en extrait des `Item` canoniques.

    Le `robots.txt` de la cible est consulté avant toute collecte (AD-10) :
    une source ajoutée par configuration ne doit jamais pouvoir contourner
    ce garde-fou.

    Une entrée sans titre exploitable est ignorée : mieux vaut perdre une
    ligne que publier un item vide.
    """
    if not _collecte_autorisee(source_config.url):
        logger.warning(
            "robots.txt interdit la collecte de '%s' (%s) — source ignorée (AD-10).",
            source_config.id,
            source_config.url,
        )
        return []

    html = _charger(source_config.url)
    soup = BeautifulSoup(html, "html.parser")

    items: list[Item] = []
    vus: set[str] = set()

    base = source_config.base_url or source_config.url
    domaine_attendu = urlparse(base).netloc

    for ancre in soup.find_all("a", href=True):
        href = ancre["href"]
        if source_config.selecteur and source_config.selecteur not in href:
            continue

        url = urljoin(base, href)

        # Un lien externe peut contenir le motif sans être un article de la
        # source : ne jamais attribuer à celle-ci du contenu d'un autre domaine.
        if domaine_attendu and urlparse(url).netloc != domaine_attendu:
            logger.debug("Lien hors domaine ignoré : %s", url)
            continue

        # Fragment et barre oblique finale ne distinguent pas deux articles.
        cle = urldefrag(url)[0].rstrip("/")
        if cle in vus:
            continue

        try:
            item = _to_item(ancre, url, source_config)
        except ValueError as e:
            logger.debug("Lien ignoré (%s) : %s", href, e)
            continue
        except Exception:  # noqa: BLE001 — isolation au niveau de l'entrée
            logger.warning("Lien ignoré (%s) dans '%s'.", href, source_config.id, exc_info=True)
            continue

        vus.add(cle)
        items.append(item)

    if not items:
        logger.warning(
            "Aucun item extrait de '%s' — la structure de la page a peut-être changé.",
            source_config.id,
        )

    return items


def _collecte_autorisee(url: str) -> bool:
    """Consulte le `robots.txt` du domaine cible (AD-10).

    En cas de `robots.txt` absent ou injoignable, la collecte est autorisée —
    c'est le comportement standard. Un `robots.txt` présent et restrictif,
    lui, est respecté.
    """
    decoupe = urlparse(url)
    if decoupe.scheme not in ("http", "https"):
        return True  # fichier local (tests) : rien à consulter

    robots_url = f"{decoupe.scheme}://{decoupe.netloc}/robots.txt"
    try:
        reponse = httpx.get(
            robots_url,
            timeout=TIMEOUT_SECONDES,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        if reponse.status_code >= 400:
            return True  # pas de robots.txt : collecte autorisée par défaut
        lecteur = robotparser.RobotFileParser()
        lecteur.parse(reponse.text.splitlines())
        return lecteur.can_fetch(USER_AGENT, url)
    except Exception:  # noqa: BLE001 — un robots.txt injoignable ne bloque pas
        logger.debug("robots.txt injoignable pour %s — collecte autorisée.", robots_url)
        return True


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
        contenu_brut=_extraire_extrait(ancre, titre),
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
    # Si ce parent est l'ancre elle-même, il n'y a pas de bloc méta distinct :
    # exclure ses spans reviendrait à tous les écarter, et à perdre le titre.
    horodatage = ancre.find("time")
    bloc_meta = horodatage.find_parent() if horodatage else None
    spans_meta = set()
    if bloc_meta is not None and bloc_meta is not ancre:
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
    brut = (balise.get("datetime") or balise.get_text(" ", strip=True)).strip()

    # 1. ISO 8601 — l'attribut `datetime` du HTML l'utilise le plus souvent.
    texte_iso = brut[:-1] + "+00:00" if brut.endswith("Z") else brut
    try:
        parsee = datetime.fromisoformat(texte_iso)
        return (
            parsee.replace(tzinfo=timezone.utc)
            if parsee.tzinfo is None
            else parsee.astimezone(timezone.utc)
        )
    except ValueError:
        pass

    # 2. Formats numériques, insensibles à la locale.
    for format_date in FORMATS_DATE_NUMERIQUES:
        try:
            return datetime.strptime(brut, format_date).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    # 3. Mois écrits en toutes lettres, résolus sans dépendre de la locale.
    for motif in (MOTIF_MOIS_JOUR_ANNEE, MOTIF_JOUR_MOIS_ANNEE):
        trouve = motif.search(brut)
        if not trouve:
            continue
        mois = MOIS_ANGLAIS.get(trouve.group("mois")[:3].lower())
        if mois is None:
            continue
        try:
            return datetime(
                int(trouve.group("annee")), mois, int(trouve.group("jour")),
                tzinfo=timezone.utc,
            )
        except ValueError:
            continue

    logger.debug("Date illisible (%r) — horodatage à la collecte.", brut)
    return datetime.now(timezone.utc)


def _extraire_extrait(ancre, titre: str = "") -> str:
    """Extrait le chapeau, en écartant les libellés d'appel à l'action.

    Le premier `<p>` n'est pas toujours le chapeau : certaines cartes
    placent un « Read more » avant lui. On retient le premier paragraphe
    substantiel qui n'est ni un libellé court, ni une répétition du titre.
    """
    for balise in ancre.find_all("p"):
        texte = balise.get_text(" ", strip=True)
        if not texte or texte == titre:
            continue
        if len(texte) < LONGUEUR_MIN_EXTRAIT and texte.lower().rstrip(" .›→»") in LIBELLES_ACTION:
            continue
        return texte
    return ""
