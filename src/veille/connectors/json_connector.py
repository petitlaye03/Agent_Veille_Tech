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
from urllib.parse import quote, urlparse

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


def _champ(entree: dict, mapping: dict, nom: str) -> Any:
    """Résout un champ déclaré dans le mapping.

    Un champ absent du mapping vaut `None` — surtout pas l'entrée entière,
    ce que renverrait `_resoudre_chemin` avec un chemin vide.
    """
    chemin = mapping.get(nom)
    if not chemin:
        return None
    return _resoudre_chemin(entree, chemin)


def _to_item(entree: dict, source_config: SourceConfig) -> Item:
    mapping = source_config.mapping

    guid = _champ(entree, mapping, "guid")
    # `0` et `False` sont des identifiants légitimes : ne rejeter que l'absence
    # réelle et la chaîne vide.
    if guid is None or guid == "":
        raise ValueError("entrée sans identifiant exploitable")
    if isinstance(guid, (dict, list)):
        raise ValueError(f"identifiant non scalaire : {type(guid).__name__}")

    guid = str(guid)
    if source_config.url_modele:
        try:
            url = source_config.url_modele.format(guid=quote(guid, safe=""))
        except (KeyError, IndexError, ValueError) as e:
            raise ValueError(f"gabarit d'URL invalide : {e}") from e
    else:
        url = str(_champ(entree, mapping, "url") or "")

    return Item(
        source_id=source_config.id,
        guid=guid,
        titre=str(_champ(entree, mapping, "titre") or ""),
        date_publication=_to_utc_datetime(_champ(entree, mapping, "date_publication")),
        langue=source_config.langue,
        registre=source_config.registre,
        url=url,
        contenu_brut=str(_champ(entree, mapping, "contenu_brut") or ""),
    )


def _to_utc_datetime(valeur: Any) -> datetime:
    """Normalise une date en datetime UTC timezone-aware.

    Accepte l'ISO 8601 et les horodatages Unix (secondes ou millisecondes),
    plusieurs API exposant l'un ou l'autre.
    """
    if valeur is None or valeur == "":
        return datetime.now(timezone.utc)

    if isinstance(valeur, (int, float)) and not isinstance(valeur, bool):
        # Au-delà de ce seuil, la valeur est en millisecondes.
        secondes = valeur / 1000 if valeur > 1e11 else valeur
        try:
            return datetime.fromtimestamp(secondes, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            logger.warning("Horodatage hors limites (%r).", valeur)
            return datetime.now(timezone.utc)

    texte = str(valeur)
    # Ne remplacer le « Z » qu'en fin de chaîne : il peut apparaître ailleurs.
    if texte.endswith("Z"):
        texte = texte[:-1] + "+00:00"
    try:
        parsee = datetime.fromisoformat(texte)
    except ValueError:
        logger.warning("Date illisible (%r) — horodatage à la collecte.", valeur)
        return datetime.now(timezone.utc)

    if parsee.tzinfo is None:
        return parsee.replace(tzinfo=timezone.utc)
    return parsee.astimezone(timezone.utc)
