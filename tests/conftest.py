"""Isolation des tests vis-à-vis de la configuration de production.

Une dizaine de tests appelaient `collecter()` sans préciser de profil et
lisaient donc `config/profil.md` — le fichier qu'Abdoulaye est précisément
invité à modifier (AD-3). Ajouter un mot-clé de bruit touchant une fixture
faisait alors échouer des tests sans aucun rapport avec le scoring.

Ce garde-fou rend le comportement sûr par défaut : sauf mention contraire,
un test s'exécute sur un profil, des pondérations et des quotas neutres. Les
tests qui portent réellement sur la configuration livrée la désignent
explicitement par son chemin (`test_profil.py`, `test_socle_reel.py`).
"""

import pytest

from veille import collect, filter as filtre


@pytest.fixture(autouse=True)
def profil_neutre_par_defaut(tmp_path_factory, monkeypatch):
    """Neutralise le profil, les pondérations et les quotas par défaut vus
    par `collecter()`.

    Un profil sans mot-clé laisse tous les items passer avec un score nul,
    et des quotas très larges ne tronquent aucun résultat : les tests de
    collecte, de dédoublonnage et de rapport observent donc le comportement
    qu'ils entendent tester, et rien d'autre.

    Story 1.5 : le branchement des quotas dans `collecter()` a ajouté cette
    troisième neutralisation dans le même mouvement — la Story 1.4 avait dû
    corriger les deux premières après coup, en revue, une fois que des
    dizaines de tests comptant des items exacts s'étaient mis à échouer sans
    rapport avec ce qu'ils testaient. Ne pas répéter une troisième fois.
    """
    racine = tmp_path_factory.mktemp("config-neutre")

    profil = racine / "profil.md"
    profil.write_text(
        "# Profil neutre de test\n\n## Posture\n- aucun mot-clé\n", encoding="utf-8"
    )

    scoring = racine / "scoring.yaml"
    scoring.write_text("ponderations: {}\n", encoding="utf-8")

    quotas = racine / "quotas.yaml"
    quotas.write_text(
        "quotas:\n  apprendre: 1000\n  ce_qui_bouge: 1000\n  pour_le_metier: 1000\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(collect, "DEFAULT_PROFIL_PATH", profil)
    monkeypatch.setattr(collect, "DEFAULT_SCORING_PATH", scoring)
    monkeypatch.setattr(collect, "DEFAULT_QUOTAS_PATH", quotas)

    # Quatrième neutralisation, même leçon que les trois précédentes (audit
    # du 2026-09-22) : le filtre de fraîcheur introduit par l'audit compare
    # `date_publication` à l'heure réelle du run, alors que les fixtures du
    # dépôt portent des dates figées dans le passé. Sans ce garde-fou, une
    # trentaine de tests sans aucun rapport avec la fraîcheur se mettaient à
    # observer zéro item — exactement le symptôme décrit plus haut pour le
    # profil et les quotas.
    #
    # Les tests qui portent réellement sur la fraîcheur passent un horizon
    # explicite (`test_filter.py`) ou re-substituent cette constante
    # (`test_collecte_integration.py`) : le filtre reste donc bel et bien
    # exercé, jamais désactivé partout sans contrepartie.
    monkeypatch.setattr(filtre, "HORIZON_FRAICHEUR_DEFAUT", 100_000)
