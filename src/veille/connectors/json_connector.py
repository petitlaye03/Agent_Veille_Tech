"""Connecteur d'API JSON (AD-2).

Respecte le contrat `fetch(source_config) -> list[Item]` commun à tous les
connecteurs. La forme de l'API n'est **pas** codée en dur : les chemins
d'extraction sont déclarés dans `sources.yaml` (AD-3), si bien qu'une
nouvelle API JSON se branche par configuration, sans nouveau module.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.request import url2pathname
from urllib.parse import urlparse

import httpx

from veille.config import SourceConfig
from veille.models import Item

logger = logging.getLogger(__name__)

TIMEOUT_SECONDES = 30


def fetch(source_config: SourceConfig) -> list[Item]:
    """Récupère une charge utile JSON et la projette en `Item` canoniques.

    Une entrée individuelle inexploitable est ignorée sans faire perdre les
    autres entrées de la même source.
    """
    charge = _charger(source_config.url)
    entrees = _resoudre_chemin(charge, source_config.racine)

    if not isinstance(entrees, list):
        logger.warning(
            "La racine '%s' de la source '%s' ne désigne pas une liste — source ignorée.",
            source_config.racine,
            source_config.id,
        )
        return []

    items: list[Item] = []
    for entree in entrees:
        try:
            items.append(_to_item(entree, source_config))
        except Exception:  # noqa: BLE001 — isolation au niveau de l'entrée
            logger.warning(
                "Entrée ignorée dans la source '%s'.", source_config.id, exc_info=True
            )

    return items


def _charger(url: str) -> Any:
    """Lit la charge utile, depuis le réseau ou depuis un fichier local (tests)."""
    if url.startswith("file://"):
        chemin = url2pathname(urlparse(url).path)
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)

    reponse = httpx.get(url, timeout=TIMEOUT_SECONDES, follow_redirects=True)
    reponse.raise_for_status()
    return reponse.json()


def _resoudre_chemin(donnees: Any, chemin: str) -> Any:
    """Suit un chemin pointé (`paper.summary`) dans une structure imbriquée."""
    if not chemin:
        return donnees

    courant = donnees
    for segment in chemin.split("."):
        if not isinstance(courant, dict):
            return None
        courant = courant.get(segment)
        if courant is None:
            return None

    return courant


def _to_item(entree: dict, source_config: SourceConfig) -> Item:
    mapping = source_config.mapping

    guid = _resoudre_chemin(entree, mapping.get("guid", ""))
    if not guid:
        raise ValueError("entrée sans identifiant exploitable")

    guid = str(guid)
    url = (
        source_config.url_modele.format(guid=guid)
        if source_config.url_modele
        else str(_resoudre_chemin(entree, mapping.get("url", "")) or "")
    )

    return Item(
        source_id=source_config.id,
        guid=guid,
        titre=str(_resoudre_chemin(entree, mapping.get("titre", "")) or ""),
        date_publication=_to_utc_datetime(
            _resoudre_chemin(entree, mapping.get("date_publication", ""))
        ),
        langue=source_config.langue,
        registre=source_config.registre,
        url=url,
        contenu_brut=str(_resoudre_chemin(entree, mapping.get("contenu_brut", "")) or ""),
    )


def _to_utc_datetime(valeur: Any) -> datetime:
    """Normalise une date ISO 8601 en datetime UTC timezone-aware."""
    if not valeur:
        return datetime.now(timezone.utc)

    texte = str(valeur).replace("Z", "+00:00")
    try:
        parsee = datetime.fromisoformat(texte)
    except ValueError:
        logger.warning("Date illisible (%r) — horodatage à la collecte.", valeur)
        return datetime.now(timezone.utc)

    if parsee.tzinfo is None:
        return parsee.replace(tzinfo=timezone.utc)
    return parsee.astimezone(timezone.utc)
