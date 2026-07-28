"""Chargement de la configuration des sources (AD-3).

Les sources sont de la configuration, jamais du code en dur : ajouter ou
retirer une source ne doit jamais nécessiter de modifier ce module.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceConfig:
    """Descripteur d'une source déclarée dans `sources.yaml`.

    Les cinq premiers champs sont communs à tous les types de source. Les
    suivants sont optionnels et propres à certains types : ils permettent
    de brancher une nouvelle source par configuration seule (AD-3), sans
    écrire de code.
    """

    id: str
    type: str
    url: str
    langue: str
    registre: str

    # Départage le dédoublonnage : à article identique, la source de plus
    # haute priorité l'emporte. Utile pour préférer une source primaire
    # (blog de laboratoire) à un agrégateur qui la relaie.
    priorite: int = 0

    # --- Spécifique aux sources JSON ---
    # Chemin vers la liste d'items dans la réponse (vide = la racine est la liste).
    racine: str = ""
    # Correspondance champ_item -> chemin pointé dans la charge utile.
    mapping: dict[str, Any] = field(default_factory=dict)
    # Gabarit d'URL construit à partir des champs extraits, ex. ".../{guid}".
    url_modele: str = ""

    # --- Spécifique aux sources scrapées ---
    # Motif que doit contenir un lien pour être retenu, ex. "/news/".
    selecteur: str = ""
    # Racine servant à résoudre les liens relatifs en URL absolues.
    base_url: str = ""


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
