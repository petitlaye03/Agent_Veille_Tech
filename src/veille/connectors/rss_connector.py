"""Connecteur RSS/Atom (AD-2).

Respecte le contrat `fetch(source_config) -> list[Item]` commun à tous les
connecteurs, quel que soit leur type (RSS, API JSON, scraping).
"""

import calendar
import hashlib
import logging
from datetime import datetime, timezone

import feedparser

from veille.config import SourceConfig
from veille.models import Item

logger = logging.getLogger(__name__)


def fetch(source_config: SourceConfig) -> list[Item]:
    """Récupère et parse un flux RSS/Atom, retourne des `Item` canoniques.

    Un flux imparfait (feedparser.bozo) est journalisé mais reste exploité
    si des entrées ont pu être récupérées : `bozo` signale aussi bien une
    anomalie mineure (esperluette non échappée, encodage limite) qu'un flux
    réellement illisible. Seul un flux sans aucune entrée exploitable
    produit une liste vide.

    Une entrée individuelle défaillante est ignorée sans faire perdre les
    autres entrées de la même source (AD-6 au niveau de l'entrée).
    """
    feed = feedparser.parse(source_config.url)

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
