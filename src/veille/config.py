"""Chargement de la configuration des sources (AD-3).

Les sources sont de la configuration, jamais du code en dur : ajouter ou
retirer une source ne doit jamais nécessiter de modifier ce module.
"""

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Racine du dépôt, déduite de l'emplacement du module : src/veille/config.py
RACINE_PROJET = Path(__file__).resolve().parents[2]


def chemin_config(nom: str) -> Path:
    """Résout un fichier de configuration indépendamment du répertoire courant.

    Le pipeline est destiné à tourner depuis un planificateur de tâches
    (Epic 3), où le répertoire courant n'est **pas** garanti. Un chemin
    relatif y deviendrait introuvable : le socle serait vide et le profil
    neutre, sans que rien ne distingue cette panne d'une nuit calme.
    """
    return RACINE_PROJET / "config" / nom


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

    # Seuil de signal (votes, points…) sous lequel un item de cette source
    # est écarté avant tout scoring (FR-4, Story 1.4). Optionnel : une
    # source qui n'en déclare pas voit tous ses items conservés — le
    # filtrage par signal n'est jamais implicite (AC2).
    seuil_signal: float | None = None

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
            sources.append(SourceConfig(**_normaliser(entry)))
        except (TypeError, AttributeError):
            logger.warning(
                "Entrée de source invalide dans %s, ignorée : %r", path, entry
            )

    return sources


def _normaliser(entry: dict) -> dict:
    """Corrige les valeurs mal typées d'une entrée avant construction.

    `sources.yaml` est édité à la main (AD-3) : une faute de frappe y est un
    incident attendu, pas exceptionnel. Un `seuil_signal: quinze` laissé tel
    quel ferait lever une `TypeError` lors de la comparaison au signal — bien
    plus loin dans le pipeline, **hors de l'isolation de panne par source**,
    donc au prix de la nuit entière.
    """
    normalisee = dict(entry)
    brut = normalisee.get("seuil_signal")

    if brut is not None:
        seuil = to_float_fini(brut)
        if seuil is None:
            logger.warning(
                "Source '%s' : seuil_signal invalide (%r) — seuil ignoré, "
                "tous les items de cette source sont conservés.",
                normalisee.get("id", "?"),
                brut,
            )
        normalisee["seuil_signal"] = seuil

    return normalisee


def to_float_fini(valeur: Any) -> float | None:
    """Convertit en `float` fini, ou `None`.

    Rejette explicitement les booléens (`seuil_signal: yes` vaut `True` en
    YAML 1.1, et `float(True)` donnerait un seuil de 1.0 silencieux) ainsi
    que `nan`/`inf`, dont toute comparaison est fausse — un seuil `nan`
    laisserait passer l'intégralité des items sans le moindre signe.
    """
    if isinstance(valeur, bool):
        return None
    try:
        converti = float(valeur)
    except (TypeError, ValueError):
        return None
    return converti if math.isfinite(converti) else None
