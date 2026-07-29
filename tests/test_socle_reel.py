"""Garde-fous sur le socle de sources réellement livré.

Tous les autres tests écrivent leur propre YAML dans un dossier temporaire :
le fichier `config/sources.yaml` effectivement utilisé en production n'était
gardé par rien. Une clé mal orthographiée y supprime pourtant la source
entière, silencieusement.
"""

from pathlib import Path

import pytest

from veille.collect import CONNECTORS, DEFAULT_SOURCES_PATH
from veille.config import load_sources

RACINE_PROJET = Path(__file__).resolve().parent.parent
CHEMIN_SOCLE = RACINE_PROJET / DEFAULT_SOURCES_PATH

REGISTRES_VALIDES = {"apprendre", "ce_qui_bouge", "pour_le_metier"}


@pytest.fixture(scope="module")
def socle():
    return load_sources(CHEMIN_SOCLE)


def test_le_fichier_de_socle_existe():
    assert CHEMIN_SOCLE.is_file(), f"{CHEMIN_SOCLE} introuvable"


def test_toutes_les_sources_declarees_sont_chargees(socle):
    """Une clé inconnue ferait disparaître une source sans bruit : on compte."""
    declarees = CHEMIN_SOCLE.read_text(encoding="utf-8").count("\n  - id:")

    assert len(socle) == declarees, (
        f"{declarees} source(s) déclarée(s) mais {len(socle)} chargée(s) — "
        "une entrée a probablement une clé invalide."
    )


def test_le_socle_couvre_au_moins_trois_types(socle):
    types = {s.type for s in socle}

    assert len(types) >= 3, f"types présents : {types}"


def test_chaque_type_declare_a_un_connecteur(socle):
    """Une faute de frappe sur `type` rend la source collectable par personne."""
    inconnus = {s.type for s in socle} - set(CONNECTORS)

    assert not inconnus, f"types sans connecteur : {inconnus}"


def test_les_identifiants_sont_uniques(socle):
    identifiants = [s.id for s in socle]

    assert len(identifiants) == len(set(identifiants)), (
        f"identifiants dupliqués dans {identifiants}"
    )


def test_les_registres_sont_valides(socle):
    """Un registre mal orthographié ferait disparaître les items du digest."""
    invalides = {s.registre for s in socle} - REGISTRES_VALIDES

    assert not invalides, f"registres inconnus : {invalides}"


def test_les_sources_json_declarent_un_mapping_avec_guid(socle):
    for source in (s for s in socle if s.type == "json"):
        assert source.mapping, f"{source.id} : mapping absent"
        assert source.mapping.get("guid"), f"{source.id} : mapping sans 'guid'"


def test_les_sources_scrape_declarent_selecteur_et_base_url(socle):
    """Sans `selecteur`, toute ancre de la page deviendrait un article."""
    for source in (s for s in socle if s.type == "scrape"):
        assert source.selecteur, f"{source.id} : `selecteur` absent"
        assert source.base_url, f"{source.id} : `base_url` absent"


def test_chaque_source_declare_une_priorite(socle):
    """Sans priorité déclarée, le dédoublonnage retomberait sur l'ordre du
    fichier — un comportement que réordonner le YAML changerait en silence."""
    sans_priorite = [s.id for s in socle if s.priorite == 0]

    assert not sans_priorite, (
        f"sources sans priorité explicite : {sans_priorite} — "
        "le départage du dédoublonnage serait alors implicite"
    )
