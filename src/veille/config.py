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


# Formats de contenu reconnus, rendus sur la page publiée (audit du
# 2026-09-22). Volontairement fermé : un format inconnu dans `sources.yaml`
# est une faute de frappe, et la laisser passer produirait une page muette
# sur la nature réelle du contenu plutôt qu'un avertissement lisible.
FORMATS_CONNUS = ("article", "podcast", "papier", "video", "release")
FORMAT_DEFAUT = "article"


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

    # --- Présentation et fraîcheur (audit du 2026-09-22) ---
    # Nom lisible affiché sur la page publiée, à la place de l'`id`
    # technique (« DataGen » plutôt que « datagen-podcast »). Optionnel :
    # une source qui n'en déclare pas s'affiche sous son `id`, jamais sous
    # une chaîne vide — le rendu ne doit jamais dépendre d'un champ
    # facultatif renseigné.
    nom: str = ""

    # Nature du contenu servi par la source, rendue sur la page : un
    # épisode de podcast de 50 minutes et une brève de 2 minutes ne
    # demandent pas le même engagement, et rien ne les distinguait
    # jusqu'ici (audit du 2026-09-22). Déclaré en configuration plutôt
    # qu'inféré de l'URL ou du contenu : l'inférence se trompe en silence,
    # la déclaration est vérifiable d'un coup d'œil (AD-3).
    format: str = FORMAT_DEFAUT

    # Âge maximal, en jours, d'un item de cette source pour entrer dans le
    # digest du jour (FR-1, « les Items publiés depuis la dernière
    # exécution »). Optionnel : sans valeur, l'horizon global de
    # `filter.filtrer_par_fraicheur` s'applique. À relever pour une source
    # à cadence lente (podcast bimensuel, blog irrégulier) dont les
    # publications resteraient sinon systématiquement hors fenêtre.
    horizon_jours: int | None = None

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
    identifiant = normalisee.get("id", "?")
    brut = normalisee.get("seuil_signal")

    if brut is not None:
        seuil = to_float_fini(brut)
        if seuil is None:
            logger.warning(
                "Source '%s' : seuil_signal invalide (%r) — seuil ignoré, "
                "tous les items de cette source sont conservés.",
                identifiant,
                brut,
            )
        normalisee["seuil_signal"] = seuil

    # `format` (audit du 2026-09-22) : une valeur hors de `FORMATS_CONNUS`
    # retombe sur le défaut avec un avertissement nommant les valeurs
    # acceptées — jamais rendue telle quelle sur la page, où elle
    # produirait une pastille vide ou un libellé incompréhensible.
    brut_format = normalisee.get("format")
    if brut_format is not None:
        format_normalise = str(brut_format).strip().lower()
        if format_normalise not in FORMATS_CONNUS:
            logger.warning(
                "Source '%s' : format inconnu (%r) — repli sur '%s'. "
                "Valeurs acceptées : %s.",
                identifiant,
                brut_format,
                FORMAT_DEFAUT,
                ", ".join(FORMATS_CONNUS),
            )
            format_normalise = FORMAT_DEFAUT
        normalisee["format"] = format_normalise

    # `horizon_jours` (audit du 2026-09-22) : même piège que `seuil_signal`
    # laissé mal typé — un `horizon_jours: sept` comparé plus loin à un
    # nombre de jours lèverait une `TypeError` hors de l'isolation par
    # source. Un horizon nul ou négatif écarterait par ailleurs la totalité
    # des items de la source sans le moindre signe : rejeté ici aussi.
    brut_horizon = normalisee.get("horizon_jours")
    if brut_horizon is not None:
        horizon = to_entier_positif(brut_horizon)
        if horizon is None:
            logger.warning(
                "Source '%s' : horizon_jours invalide (%r) — horizon global "
                "appliqué à cette source.",
                identifiant,
                brut_horizon,
            )
        normalisee["horizon_jours"] = horizon

    # `nom` (audit du 2026-09-22) : normalisé en chaîne nettoyée — un `nom:`
    # laissé vide, ou composé d'espaces seuls, doit retomber sur l'`id`
    # plutôt que d'afficher un blanc sur la page (même piège de « clé
    # blanche » que `_jeton_depuis_env`, trouvé en revue de la Story 1.6).
    brut_nom = normalisee.get("nom")
    if brut_nom is not None:
        normalisee["nom"] = str(brut_nom).strip()

    return normalisee


def to_entier_positif(valeur: Any) -> int | None:
    """Convertit en entier strictement positif, ou `None`.

    Mêmes rejets que `to_float_fini` (booléens, `nan`/`inf`), plus le rejet
    des valeurs nulles ou négatives : un horizon de fraîcheur à 0 ou -3 ne
    décrit aucune fenêtre exploitable, il viderait simplement la source.
    Une valeur fractionnaire (`7.5`) est tronquée vers l'entier inférieur
    plutôt que rejetée — l'intention reste lisible, contrairement à une
    faute de frappe alphabétique.
    """
    nombre = to_float_fini(valeur)
    if nombre is None or nombre < 1:
        return None
    return int(nombre)


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
