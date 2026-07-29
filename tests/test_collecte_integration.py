"""Tests d'intégration du chemin configuration → collecte → dédoublonnage → rapport.

Ces tests existent parce qu'un audit par mutation a montré que la suite
restait verte alors que le câblage était cassé :

    MUTANT [priorités vidées]              -> 70 tests passaient
    MUTANT [priorité inversée]             -> 70 tests passaient
    MUTANT [dédoublonnage court-circuité]  -> 70 tests passaient

Le dernier était le plus grave : `collecter()` retournait la liste NON
dédoublonnée tout en annonçant « après N doublons écartés ». Tous les tests
du dédoublonnage appelaient `dedupliquer()` directement, sans jamais
emprunter le chemin réel depuis `sources.yaml`.
"""

import textwrap
from pathlib import Path

from veille.collect import collecter
from veille.config import load_sources

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _socle(tmp_path: Path, contenu: str) -> Path:
    chemin = tmp_path / "sources.yaml"
    chemin.write_text(textwrap.dedent(contenu), encoding="utf-8")
    return chemin


def _socle_avec_doublons(tmp_path: Path, priorite_haute: str, priorite_basse: str) -> Path:
    """Deux sources servant le même flux : recouvrement intégral garanti."""
    flux = (FIXTURE_DIR / "sample_feed.xml").as_posix()
    return _socle(
        tmp_path,
        f"""
        sources:
          - id: {priorite_basse}
            type: rss
            url: {flux}
            langue: fr
            registre: apprendre
            priorite: 1
          - id: {priorite_haute}
            type: rss
            url: {flux}
            langue: fr
            registre: apprendre
            priorite: 9
        """,
    )


class TestCablagePriorite:
    """Tue les mutants « priorités vidées » et « priorité inversée »."""

    def test_la_priorite_est_lue_depuis_le_yaml(self, tmp_path):
        socle = _socle_avec_doublons(tmp_path, "gagnante", "perdante")

        sources = {s.id: s.priorite for s in load_sources(socle)}

        assert sources == {"perdante": 1, "gagnante": 9}

    def test_la_source_prioritaire_du_yaml_remporte_l_arbitrage(self, tmp_path):
        socle = _socle_avec_doublons(tmp_path, "gagnante", "perdante")

        resultat = collecter(socle)

        assert {i.source_id for i in resultat.items} == {"gagnante"}

    def test_inverser_les_priorites_inverse_le_gagnant(self, tmp_path):
        """Si le câblage était inerte, ce test et le précédent ne pourraient
        pas passer tous les deux."""
        socle = _socle_avec_doublons(tmp_path, "b", "a")  # b priorité 9
        assert {i.source_id for i in collecter(socle).items} == {"b"}

        socle_inverse = _socle_avec_doublons(tmp_path, "a", "b")  # a priorité 9
        assert {i.source_id for i in collecter(socle_inverse).items} == {"a"}


class TestDedoublonnageEffectif:
    """Tue le mutant « dédoublonnage court-circuité »."""

    def test_les_items_retournes_sont_bien_dedoublonnes(self, tmp_path):
        socle = _socle_avec_doublons(tmp_path, "gagnante", "perdante")

        resultat = collecter(socle)

        collectes = sum(r.nb_items for r in resultat.rapports)
        assert collectes == 4, "le socle doit bien collecter deux fois le flux"
        assert len(resultat.items) == 2, "la liste retournée doit être dédoublonnée"

    def test_le_compte_annonce_correspond_aux_items_reellement_retournes(self, tmp_path):
        """Le rapport ne doit jamais annoncer un tri qu'il n'a pas fait."""
        socle = _socle_avec_doublons(tmp_path, "gagnante", "perdante")

        resultat = collecter(socle)

        collectes = sum(r.nb_items for r in resultat.rapports)
        assert len(resultat.items) + resultat.dedoublonnage.total_ecartes == collectes


class TestVisibiliteDuTriExcessif:
    """AC4 : une source entièrement absorbée ne doit pas passer pour saine."""

    def test_une_source_absorbee_est_signalee(self, tmp_path):
        socle = _socle_avec_doublons(tmp_path, "gagnante", "perdante")

        resultat = collecter(socle)

        absorbees = [r.source_id for r in resultat.sources_absorbees]
        assert absorbees == ["perdante"]
        # Elle n'a rien collecté d'inutile : elle a collecté, mais rien n'a survécu.
        assert not resultat.sources_muettes

    def test_le_recapitulatif_mentionne_la_source_absorbee(self, tmp_path):
        socle = _socle_avec_doublons(tmp_path, "gagnante", "perdante")

        resume = collecter(socle).resume()

        assert "ABSORBÉE" in resume
        assert "perdante" in resume

    def test_le_recapitulatif_se_lit_seul(self, tmp_path):
        """Le détail du dédoublonnage doit figurer dans le récapitulatif,
        pas dans un journal séparé qu'un filtre pourrait perdre."""
        socle = _socle_avec_doublons(tmp_path, "gagnante", "perdante")

        resume = collecter(socle).resume()

        assert "doublon(s) écarté(s)" in resume
        assert "absorbés par" in resume
        assert "gagnante" in resume
