"""Garde-fous sur le socle de sources réellement livré.

Tous les autres tests écrivent leur propre YAML dans un dossier temporaire :
le fichier `config/sources.yaml` effectivement utilisé en production n'était
gardé par rien. Une clé mal orthographiée y supprime pourtant la source
entière, silencieusement.
"""

import re
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


# --- Garde-fous sur le seuil de signal (revue 2026-08-28) ---------------
#
# Ces livrables de configuration des Tasks 0 et 2bis pouvaient être retirés
# de `sources.yaml` sans qu'aucun test ne bronche : l'audit par mutation
# n'avait porté que sur le code, jamais sur la configuration.


def test_le_fichier_de_ponderations_existe_et_se_charge():
    """`config/scoring.yaml` porte les mêmes valeurs que les défauts en dur :
    le supprimer serait donc sans effet observable, et passerait inaperçu.
    Ce garde-fou rend la disparition du livrable visible (AD-3)."""
    from veille.filter import charger_ponderations

    chemin = RACINE_PROJET / "config" / "scoring.yaml"

    assert chemin.is_file(), f"{chemin} introuvable"
    ponderations = charger_ponderations(chemin)
    assert ponderations.prioritaire > 0
    assert ponderations.bruit < 0
    assert ponderations.signal_fort > ponderations.secondaire

    # `marge_recommandation` (Story 1.7) partage la valeur par défaut du
    # code (10) : un simple test de valeur ne détecterait pas sa suppression
    # du fichier (le défaut prendrait silencieusement le relais, exactement
    # le trou déjà trouvé en revue des Stories 1.4/1.5). On vérifie donc la
    # présence explicite de la clé dans le fichier réel, pas seulement la
    # valeur résultante. Ancré en début de ligne (`^`, multiligne) pour ne
    # pas matcher une ligne mise en commentaire (`# marge_recommandation: 10`)
    # — un simple test de sous-chaîne s'y laisserait tromper (trouvé en
    # revue par le Edge Case Hunter).
    assert re.search(
        r"^marge_recommandation:", chemin.read_text(encoding="utf-8"), re.MULTILINE
    )


def test_le_fichier_de_quotas_existe_et_se_charge():
    """Comme `scoring.yaml` : un fichier de quotas supprimé serait sans
    effet observable pour la plupart des tests (`conftest.py` fournit
    toujours un fichier explicite), et passerait donc inaperçu. Ce
    garde-fou rend sa disparition visible (AD-3, Story 1.5)."""
    from veille.filter import charger_quotas

    chemin = RACINE_PROJET / "config" / "quotas.yaml"

    assert chemin.is_file(), f"{chemin} introuvable"
    quotas = charger_quotas(chemin)
    assert quotas.apprendre > 0
    assert quotas.ce_qui_bouge > 0
    assert quotas.pour_le_metier > 0


def test_le_socle_declare_au_moins_un_seuil_de_signal(socle):
    """FR-4 : le seuil de signal est le mécanisme central de la Story 1.4.
    Sans aucune source qui en déclare un, il n'est plus exercé nulle part."""
    avec_seuil = [s.id for s in socle if s.seuil_signal is not None]

    assert avec_seuil, (
        "aucune source ne déclare de seuil_signal — FR-4 n'est plus exercé "
        "par le socle réel"
    )


def test_une_source_a_seuil_declare_extrait_bien_un_signal(socle):
    """Un seuil sur une source qui ne produit aucun signal est inerte : le
    rapport afficherait « 0 écarté », qui se lit « rien n'était sous le
    seuil » alors que le filtre n'a jamais tourné."""
    for source in (s for s in socle if s.seuil_signal is not None):
        assert source.type == "json", (
            f"{source.id} : seuil_signal déclaré sur un type '{source.type}', "
            "qui ne renseigne jamais Item.signal"
        )
        assert source.mapping.get("signal"), (
            f"{source.id} : seuil_signal déclaré sans 'mapping.signal' — "
            "le filtre ne pourra rien écarter"
        )


def test_un_mapping_signal_s_accompagne_d_un_seuil(socle):
    """La réciproque : extraire un signal sans jamais s'en servir signale un
    seuil oublié lors d'une édition."""
    for source in (s for s in socle if s.mapping.get("signal")):
        assert source.seuil_signal is not None, (
            f"{source.id} : 'mapping.signal' déclaré sans seuil_signal — "
            "le signal est extrait puis ignoré"
        )
