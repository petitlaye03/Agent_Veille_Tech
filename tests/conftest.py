"""Isolation des tests vis-à-vis de la configuration de production.

Une dizaine de tests appelaient `collecter()` sans préciser de profil et
lisaient donc `config/profil.md` — le fichier qu'Abdoulaye est précisément
invité à modifier (AD-3). Ajouter un mot-clé de bruit touchant une fixture
faisait alors échouer des tests sans aucun rapport avec le scoring.

Ce garde-fou rend le comportement sûr par défaut : sauf mention contraire,
un test s'exécute sur un profil et des pondérations neutres. Les tests qui
portent réellement sur la configuration livrée la désignent explicitement
par son chemin (`test_profil.py`, `test_socle_reel.py`).
"""

import pytest

from veille import collect


@pytest.fixture(autouse=True)
def profil_neutre_par_defaut(tmp_path_factory, monkeypatch):
    """Neutralise le profil par défaut vu par `collecter()`.

    Un profil sans mot-clé laisse tous les items passer avec un score nul :
    les tests de collecte, de dédoublonnage et de rapport observent donc le
    comportement qu'ils entendent tester, et rien d'autre.
    """
    racine = tmp_path_factory.mktemp("config-neutre")

    profil = racine / "profil.md"
    profil.write_text(
        "# Profil neutre de test\n\n## Posture\n- aucun mot-clé\n", encoding="utf-8"
    )

    scoring = racine / "scoring.yaml"
    scoring.write_text("ponderations: {}\n", encoding="utf-8")

    monkeypatch.setattr(collect, "DEFAULT_PROFIL_PATH", profil)
    monkeypatch.setattr(collect, "DEFAULT_SCORING_PATH", scoring)
