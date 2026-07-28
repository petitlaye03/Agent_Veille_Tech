"""Chargement de la configuration des sources (AD-3).

Les sources sont de la configuration, jamais du code en dur : ajouter ou
retirer une source ne doit jamais nécessiter de modifier ce module.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceConfig:
    """Descripteur d'une source déclarée dans `sources.yaml`."""

    id: str
    type: str
    url: str
    langue: str
    registre: str


def load_sources(path: str | Path) -> list[SourceConfig]:
    """Lit `sources.yaml` et retourne la liste typée des sources déclarées.

    Une entrée mal formée est journalisée et ignorée : une faute de frappe
    sur une seule source ne doit pas priver le digest de toutes les autres.
    """
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        logger.warning(
            "%s ne contient pas un mapping YAML à la racine — aucune source chargée.",
            path,
        )
        return []

    entries = raw.get("sources") or []
    if not isinstance(entries, list):
        logger.warning(
            "La clé 'sources' de %s n'est pas une liste — aucune source chargée.",
            path,
        )
        return []

    sources: list[SourceConfig] = []
    for entry in entries:
        try:
            sources.append(SourceConfig(**entry))
        except TypeError:
            logger.warning(
                "Entrée de source invalide dans %s, ignorée : %r", path, entry
            )

    return sources
