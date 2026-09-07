"""Connecteur RSS/Atom (AD-2).

Respecte le contrat `fetch(source_config) -> list[Item]` commun à tous les
connecteurs, quel que soit leur type (RSS, API JSON, scraping).
"""

import calendar
import hashlib
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

import feedparser
import httpx  # noqa: F401 — non appelé directement (délégué à `_reseau`), mais
# gardé importé ici : `tests/test_rss_connector.py`/`test_rapport_collecte.py`
# (Story 2.2) monkeypatchent `module.httpx.get` — comme `httpx` est un module
# singleton (`sys.modules`), muter son attribut `get` depuis cette référence
# affecte aussi l'appel réel fait dans `_reseau.get_avec_backoff` (Story 2.3).
# Retirer cet import casserait ces tests avec une simple `AttributeError`,
# sans rapport avec le comportement réellement testé.

from veille.config import SourceConfig
from veille.connectors._reseau import get_avec_backoff
from veille.models import Item

logger = logging.getLogger(__name__)

TIMEOUT_SECONDES = 30
# ASCII uniquement : les en-têtes HTTP n'acceptent pas les caractères accentués.
USER_AGENT = "veille-ia/0.1 (personal news aggregator)"


def fetch(source_config: SourceConfig) -> list[Item]:
    """Récupère et parse un flux RSS/Atom, retourne des `Item` canoniques.

    Un flux imparfait (feedparser.bozo) est journalisé mais reste exploité
    si des entrées ont pu être récupérées : `bozo` signale aussi bien une
    anomalie mineure (esperluette non échappée, encodage limite) qu'un flux
    réellement illisible. Seul un flux sans aucune entrée exploitable
    produit une liste vide.

    Une entrée individuelle défaillante est ignorée sans faire perdre les
    autres entrées de la même source (AD-6 au niveau de l'entrée).

    La récupération réseau elle-même (délai d'attente, statut HTTP) est
    isolée dans `_charger` : une panne à ce niveau lève (`httpx.TimeoutException`,
    `httpx.HTTPStatusError`...), volontairement pas capturée ici — c'est
    `collect._fetch_one` qui isole chaque source par panne (AD-6), exactement
    comme pour `json_connector`/`scrape_connector` (Story 2.2).
    """
    feed = feedparser.parse(_charger(source_config.url))

    if feed.bozo:
        logger.warning(
            "Flux imparfait pour la source '%s' (%s) : %s",
            source_config.id,
            source_config.url,
            getattr(feed, "bozo_exception", "raison inconnue"),
        )
        if not feed.entries:
            logger.warning(
                "Aucune entrée exploitable pour la source '%s' — source ignorée.",
                source_config.id,
            )
            return []
        logger.info(
            "Flux '%s' partiellement exploitable : %d entrée(s) conservée(s).",
            source_config.id,
            len(feed.entries),
        )

    items: list[Item] = []
    for entry in feed.entries:
        try:
            items.append(_to_item(entry, source_config))
        except Exception:  # noqa: BLE001 — isolation au niveau de l'entrée
            logger.warning(
                "Entrée ignorée dans la source '%s' (titre : %r).",
                source_config.id,
                entry.get("title", "<sans titre>"),
                exc_info=True,
            )

    return items


def _charger(url: str) -> str | bytes:
    """Récupère le flux, depuis le réseau (délai d'attente explicite) ou
    depuis un chemin local (tests) — même patron que `json_connector._charger`
    et `scrape_connector._charger` (Story 2.2).

    Seule une URL réseau (`http(s)://`) passe par `httpx` : un chemin de
    fichier brut ou une URI `file://` (utilisés par tous les tests existants
    et jamais par une source réelle de ce projet) est rendu tel quel, pour
    que `feedparser.parse()` continue de le lire lui-même sans changement de
    comportement.

    Ne capture aucune exception réseau (délai dépassé, statut HTTP) :
    `collect._fetch_one` isole chaque source par panne (AD-6), exactement
    comme pour les deux autres connecteurs.
    """
    # `urlparse(...).scheme` (pas `str.startswith`) : insensible à la casse et
    # tolérant à un espace de tête, comme `_collecte_autorisee` de
    # `scrape_connector.py` — un schéma `HTTP://` ou un chemin mal formé ne
    # doit pas retomber silencieusement sur la branche locale, sans quoi la
    # panne que cette story ferme (Task 1) reviendrait pour cette seule URL.
    if urlparse(url).scheme not in ("http", "https"):
        return url

    reponse = get_avec_backoff(
        url,
        timeout=TIMEOUT_SECONDES,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )
    return reponse.content


def _to_item(entry, source_config: SourceConfig) -> Item:
    url = entry.get("link", "") or ""
    # L'identifiant natif du flux prime : il est conçu pour être permanent,
    # là où une URL peut dériver (tracking, migration) sans que le contenu change.
    guid = entry.get("id") or url or _fallback_guid(source_config.id, entry.get("title", ""))

    return Item(
        source_id=source_config.id,
        guid=guid,
        titre=entry.get("title", ""),
        date_publication=_to_utc_datetime(entry),
        langue=source_config.langue,
        registre=source_config.registre,
        url=url,
        contenu_brut=_extract_contenu(entry),
    )


def _extract_contenu(entry) -> str:
    """Extrait le contenu textuel, quel que soit le champ porteur du flux.

    feedparser normalise le plus souvent `<description>` (RSS) et `<content>`
    (Atom) vers `summary`, mais pas systématiquement : ce repli garantit que
    `contenu_brut` ne revient pas vide alors que le flux porte du contenu.
    """
    summary = entry.get("summary")
    if summary:
        return summary

    contents = entry.get("content")
    if contents:
        premier = contents[0]
        valeur = premier.get("value") if isinstance(premier, dict) else None
        if valeur:
            return valeur

    return entry.get("description") or ""


def _to_utc_datetime(entry) -> datetime:
    struct = entry.get("published_parsed")
    if struct is None:
        # Pas de date exploitable dans le flux : horodater à la collecte
        # plutôt que planter — mieux vaut une date approximative qu'un item perdu.
        return datetime.now(timezone.utc)
    # published_parsed est un struct_time déjà normalisé en UTC par feedparser ;
    # calendar.timegm (et non time.mktime, qui appliquerait le fuseau local) le
    # convertit correctement en timestamp UTC.
    return datetime.fromtimestamp(calendar.timegm(struct), tz=timezone.utc)


def _fallback_guid(source_id: str, titre: str) -> str:
    return hashlib.sha256(f"{source_id}{titre}".encode("utf-8")).hexdigest()
