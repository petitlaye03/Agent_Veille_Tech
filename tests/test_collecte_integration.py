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

import json
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

    def test_le_dedoublonnage_fonctionne_entre_deux_types_de_connecteurs(self, tmp_path):
        """Story 2.4 (AC1) : jusqu'ici, seul le cas RSS+RSS (même flux
        dupliqué) était vérifié par le chemin réel — `normaliser_url` agit
        sur la chaîne d'URL seule, sans jamais regarder le type d'origine,
        mais rien ne le confirmait de bout en bout entre deux types.
        `json-source` pointe (via `mapping.url`) vers la même URL cible que
        le premier item de `sample_feed.xml`."""
        api = tmp_path / "api.json"
        api.write_text(
            json.dumps(
                [{"id": "abc-1", "titre": "Reprise JSON", "url": "https://example.invalid/articles/premier"}]
            ),
            encoding="utf-8",
        )

        socle = _socle(
            tmp_path,
            f"""
            sources:
              - id: source-rss
                type: rss
                url: {(FIXTURE_DIR / "sample_feed.xml").as_posix()}
                langue: fr
                registre: apprendre
                priorite: 1
              - id: source-json
                type: json
                url: {api.as_uri()}
                langue: fr
                registre: apprendre
                priorite: 9
                mapping:
                  guid: id
                  titre: titre
                  url: url
            """,
        )

        resultat = collecter(socle)

        # sample_feed.xml porte 2 items, api.json en porte 1 (doublon du
        # premier) : 3 collectés, 2 restent après dédoublonnage inter-types.
        collectes = sum(r.nb_items for r in resultat.rapports)
        assert collectes == 3
        assert len(resultat.items) == 2
        # La source json (priorité 9) gagne l'arbitrage sur la source rss
        # (priorité 1) — même mécanisme que le cas RSS+RSS déjà testé.
        gagnant = next(
            (i for i in resultat.items if i.url == "https://example.invalid/articles/premier"), None
        )
        assert gagnant is not None, "l'article dupliqué a disparu, pas seulement changé de source_id"
        assert gagnant.source_id == "source-json"
        # La couche de comptage (celle qu'un opérateur consulte réellement,
        # via `resume()`) doit elle aussi attribuer correctement le doublon
        # — trouvé en revue : le test initial ne vérifiait que la liste
        # finale, jamais le rapport de dédoublonnage lui-même.
        assert resultat.dedoublonnage.ecartes_par_source == {"source-rss": 1}
        assert resultat.dedoublonnage.gagnants_par_source == {"source-json": 1}

    def test_le_dedoublonnage_fonctionne_entre_scrape_et_rss(self, tmp_path):
        """Story 2.4 (AC1), correctif de revue : le cas `rss`+`json` ne
        suffit pas à verrouiller « y compris entre deux sources de types
        différents (rss/json/scrape) » à la lettre — `scrape` est le
        connecteur le plus divergent (son `guid` vaut toujours son URL
        résolue, et il applique déjà sa propre déduplication intra-page
        avant que l'item n'atteigne `dedup.py`) et le seul des trois jamais
        exercé dans un scénario inter-types jusqu'ici. C'est aussi la seule
        combinaison que l'exécution réelle (Task 3) ne peut structurellement
        jamais observer : le socle réel ne compte qu'une seule source
        `scrape` (`anthropic-news`)."""
        page = tmp_path / "news.html"
        page.write_text(
            '<a href="/articles/premier"><h2>Reprise scrapée</h2>'
            '<time datetime="2026-07-24">24 juillet 2026</time></a>',
            encoding="utf-8",
        )

        socle = _socle(
            tmp_path,
            f"""
            sources:
              - id: source-rss
                type: rss
                url: {(FIXTURE_DIR / "sample_feed.xml").as_posix()}
                langue: fr
                registre: apprendre
                priorite: 1
              - id: source-scrape
                type: scrape
                url: {page.as_uri()}
                langue: fr
                registre: apprendre
                priorite: 9
                selecteur: /articles/
                base_url: https://example.invalid
            """,
        )

        resultat = collecter(socle)

        collectes = sum(r.nb_items for r in resultat.rapports)
        assert collectes == 3
        assert len(resultat.items) == 2
        gagnant = next(
            (i for i in resultat.items if i.url == "https://example.invalid/articles/premier"), None
        )
        assert gagnant is not None
        assert gagnant.source_id == "source-scrape"
        assert resultat.dedoublonnage.ecartes_par_source == {"source-rss": 1}
        assert resultat.dedoublonnage.gagnants_par_source == {"source-scrape": 1}


class TestScoringEffectif:
    """Tue le mutant « classement court-circuité » (Task 5, Story 1.4) :
    vérifie que `collecter()` emprunte réellement `profil.md`/`scoring.yaml`
    plutôt que d'ignorer le résultat de `classer()`."""

    def _socle_rss_simple(self, tmp_path: Path) -> Path:
        return _socle(
            tmp_path,
            f"""
            sources:
              - id: source-rss
                type: rss
                url: {(FIXTURE_DIR / "sample_feed.xml").as_posix()}
                langue: fr
                registre: apprendre
            """,
        )

    def _profil(self, tmp_path: Path, contenu: str) -> Path:
        chemin = tmp_path / "profil.md"
        chemin.write_text(textwrap.dedent(contenu), encoding="utf-8")
        return chemin

    def test_un_item_de_bruit_est_ecarte_par_le_chemin_reel(self, tmp_path):
        """sample_feed.xml contient « Premier article de test » et
        « Deuxième article de test » : marquer « Deuxième » comme bruit
        via profil.md doit faire disparaître le second, en passant
        uniquement par la configuration."""
        profil = self._profil(
            tmp_path, "## Bruit — fait descendre ou disparaître\n- Deuxième\n"
        )
        socle = self._socle_rss_simple(tmp_path)

        resultat = collecter(socle, profil_path=profil)

        assert [i.titre for i in resultat.items] == ["Premier article de test"]
        assert resultat.classement.total_ecartes == 1

    def test_un_item_prioritaire_est_place_en_tete_par_le_chemin_reel(self, tmp_path):
        profil = self._profil(
            tmp_path, "## Thèmes prioritaires — font monter le score\n- Deuxième\n"
        )
        socle = self._socle_rss_simple(tmp_path)

        resultat = collecter(socle, profil_path=profil)

        assert resultat.items[0].titre == "Deuxième article de test"

    def test_nb_retenus_reflete_la_survie_apres_classement_pas_seulement_le_dedoublonnage(
        self, tmp_path
    ):
        """Dev Notes : `nb_retenus` doit refléter la contribution finale au
        digest, y compris après le scoring — pas seulement le dédoublonnage."""
        profil = self._profil(
            tmp_path, "## Bruit — fait descendre ou disparaître\n- Deuxième\n"
        )
        socle = self._socle_rss_simple(tmp_path)

        rapport = collecter(socle, profil_path=profil).rapports[0]

        assert rapport.nb_items == 2
        assert rapport.nb_retenus == 1

    def test_seuil_signal_ecarte_via_le_socle_reel(self, tmp_path):
        """hf_daily_papers.json a des votes à 1 et 0 : un seuil_signal de 5
        déclaré dans sources.yaml doit tout écarter, avant même le scoring."""
        socle = _socle(
            tmp_path,
            f"""
            sources:
              - id: hf
                type: json
                seuil_signal: 5
                url: {(FIXTURE_DIR / "hf_daily_papers.json").as_uri()}
                langue: en
                registre: apprendre
                mapping:
                  guid: paper.id
                  titre: title
                  contenu_brut: paper.summary
                  signal: paper.upvotes
            """,
        )
        profil_neutre = self._profil(tmp_path, "")

        resultat = collecter(socle, profil_path=profil_neutre)

        assert resultat.items == []
        assert resultat.filtrage_signal.ecartes_par_source == {"hf": 2}

    def test_le_resume_rend_compte_du_classement(self, tmp_path):
        profil = self._profil(
            tmp_path, "## Bruit — fait descendre ou disparaître\n- Deuxième\n"
        )
        socle = self._socle_rss_simple(tmp_path)

        resume = collecter(socle, profil_path=profil).resume()

        # Nommer la source écartée, pas seulement le total (AC7).
        assert "1 item(s) écarté(s) comme bruit" in resume
        assert "source-rss (-1)" in resume

    def test_le_fichier_de_ponderations_change_reellement_le_classement(self, tmp_path):
        """Tue le mutant « scoring.yaml sans effet » : le fichier livré porte
        les mêmes valeurs que les défauts en dur, si bien que le supprimer ne
        cassait aucun test. AD-3/AC6 n'étaient satisfaits qu'en apparence."""
        profil = self._profil(
            tmp_path,
            "## Thèmes prioritaires\n- Premier\n\n## Thèmes secondaires\n- Deuxième\n",
        )
        socle = self._socle_rss_simple(tmp_path)

        scoring = tmp_path / "scoring.yaml"
        scoring.write_text(
            "ponderations:\n  prioritaire: 1\n  secondaire: 100\n", encoding="utf-8"
        )

        resultat = collecter(socle, profil_path=profil, scoring_path=scoring)

        # « Deuxième » est secondaire, mais pesé 100 contre 1 : il passe devant.
        assert resultat.items[0].titre == "Deuxième article de test"

    def test_un_profil_neutre_est_signale_dans_le_recapitulatif(self, tmp_path):
        """Un profil introuvable ou vide désactive le classement en entier.
        Sans ce signal, la nuit non filtrée se lit comme une nuit saine."""
        socle = self._socle_rss_simple(tmp_path)

        resultat = collecter(socle, profil_path=tmp_path / "profil-absent.md")

        assert resultat.profil_neutre
        assert "Profil neutre" in resultat.resume()

    def test_le_recapitulatif_rend_le_total_collecte_meme_sans_doublon(self, tmp_path):
        """Régression : le total collecté n'apparaissait qu'en cas de doublon,
        donc les pertes dues au seuil ou au bruit disparaissaient de l'en-tête."""
        profil = self._profil(tmp_path, "## Bruit\n- Deuxième\n")
        socle = self._socle_rss_simple(tmp_path)

        resume = collecter(socle, profil_path=profil).resume()

        assert "2 collecté(s)" in resume
        assert "1 bruit" in resume


class TestSeuilDeSignalSurLeSocle:
    """Le seuil éprouvé **des deux côtés**, via le chemin réel.

    La story exigeait une fixture aux votes variés ; elle n'avait pas été
    créée, et le seul test d'intégration n'observait que le côté « tout
    écarté » — aucun test ne montrait un item survivant au-dessus du seuil.
    """

    def _socle_hf(self, tmp_path: Path, seuil: str) -> Path:
        return _socle(
            tmp_path,
            f"""
            sources:
              - id: hf
                type: json
                {seuil}
                url: {(FIXTURE_DIR / "hf_daily_papers_votes.json").as_uri()}
                langue: en
                registre: apprendre
                mapping:
                  guid: paper.id
                  titre: title
                  date_publication: publishedAt
                  contenu_brut: paper.summary
                  signal: paper.upvotes
            """,
        )

    def _profil_neutre(self, tmp_path: Path) -> Path:
        chemin = tmp_path / "profil.md"
        chemin.write_text("## Posture\n- rien\n", encoding="utf-8")
        return chemin

    def test_le_seuil_garde_les_items_au_dessus_et_ecarte_ceux_en_dessous(self, tmp_path):
        """Votes de la fixture : 45, 24, 15, 11, 3, 0 — seuil à 15."""
        socle = self._socle_hf(tmp_path, "seuil_signal: 15")

        resultat = collecter(socle, profil_path=self._profil_neutre(tmp_path))

        assert sorted(i.signal for i in resultat.items) == [15.0, 24.0, 45.0]
        assert resultat.filtrage_signal.ecartes_par_source == {"hf": 3}

    def test_sans_seuil_declare_tous_les_items_sont_conserves(self, tmp_path):
        """AC2 : le filtrage par signal n'est jamais implicite."""
        socle = self._socle_hf(tmp_path, "")

        resultat = collecter(socle, profil_path=self._profil_neutre(tmp_path))

        assert len(resultat.items) == 6
        assert resultat.filtrage_signal.total_ecartes == 0

    def test_relever_le_seuil_ecarte_davantage(self, tmp_path):
        """AC6 : changer le seuil dans le YAML change le résultat, sans code."""
        strict = collecter(
            self._socle_hf(tmp_path, "seuil_signal: 25"),
            profil_path=self._profil_neutre(tmp_path),
        )

        assert [i.signal for i in strict.items] == [45.0]


class TestOrdreDuPipeline:
    """Le seuil de signal s'applique AVANT le dédoublonnage (revue 2026-08-28).

    Le seuil est déclaré *par source* : chaque item doit être jugé sur le
    seuil de la sienne. Dans l'ordre inverse, l'élection d'un gagnant
    faisait disparaître un article auquel aucun seuil ne s'appliquait.
    """

    def test_le_seuil_d_une_source_n_ampute_pas_une_autre(self, tmp_path):
        """Deux sources relaient le même article. Celle qui porte un seuil a
        la priorité la plus haute et son signal est sous le seuil ; la copie
        sans seuil doit survivre."""
        payload = tmp_path / "avec_signal.json"
        payload.write_text(
            '[{"id": "art-1", "titre": "Article relayé", "votes": 3}]', encoding="utf-8"
        )
        sans_signal = tmp_path / "sans_signal.json"
        sans_signal.write_text(
            '[{"id": "art-1", "titre": "Article relayé"}]', encoding="utf-8"
        )

        socle = _socle(
            tmp_path,
            f"""
            sources:
              - id: avec-seuil
                type: json
                priorite: 9
                seuil_signal: 15
                url: {payload.as_uri()}
                langue: fr
                registre: apprendre
                mapping: {{guid: id, titre: titre, signal: votes}}
                url_modele: https://exemple.invalid/{{guid}}
              - id: sans-seuil
                type: json
                priorite: 1
                url: {sans_signal.as_uri()}
                langue: fr
                registre: apprendre
                mapping: {{guid: id, titre: titre}}
                url_modele: https://exemple.invalid/{{guid}}
            """,
        )
        profil = tmp_path / "profil.md"
        profil.write_text("## Posture\n- rien\n", encoding="utf-8")

        resultat = collecter(socle, profil_path=profil)

        assert [i.source_id for i in resultat.items] == ["sans-seuil"], (
            "l'article a disparu : le seuil de 'avec-seuil' a amputé 'sans-seuil'"
        )


class TestQuotasEffectifs:
    """Tue le mutant « quotas court-circuités » (Task 3, Story 1.5) : vérifie
    que `collecter()` emprunte réellement `config/quotas.yaml` plutôt que
    d'ignorer le résultat de `repartir_par_quotas()`."""

    def _socle_registre(self, tmp_path: Path, registre: str, n: int) -> Path:
        """n items dans un seul registre, via une source JSON inline."""
        payload = tmp_path / f"{registre}.json"
        payload.write_text(
            json.dumps([{"id": f"{registre}-{i}", "titre": f"Item {i}"} for i in range(n)]),
            encoding="utf-8",
        )
        return _socle(
            tmp_path,
            f"""
            sources:
              - id: source-{registre}
                type: json
                url: {payload.as_uri()}
                langue: fr
                registre: {registre}
                mapping: {{guid: id, titre: titre}}
            """,
        )

    def test_le_quota_est_applique_par_le_chemin_reel(self, tmp_path):
        socle = self._socle_registre(tmp_path, "apprendre", 5)
        quotas = tmp_path / "quotas.yaml"
        quotas.write_text("quotas:\n  apprendre: 2\n", encoding="utf-8")

        resultat = collecter(socle, quotas_path=quotas)

        assert len(resultat.items) == 2

    def test_relever_le_quota_retient_davantage(self, tmp_path):
        """AC4 : changer le quota dans le YAML change le résultat, sans code."""
        socle = self._socle_registre(tmp_path, "apprendre", 5)
        quotas = tmp_path / "quotas.yaml"
        quotas.write_text("quotas:\n  apprendre: 4\n", encoding="utf-8")

        resultat = collecter(socle, quotas_path=quotas)

        assert len(resultat.items) == 4

    def test_un_jour_creux_n_est_jamais_rempli_via_le_chemin_reel(self, tmp_path):
        """AC3 : moins d'items que le quota, jamais de remplissage."""
        socle = self._socle_registre(tmp_path, "apprendre", 1)
        quotas = tmp_path / "quotas.yaml"
        quotas.write_text("quotas:\n  apprendre: 3\n", encoding="utf-8")

        resultat = collecter(socle, quotas_path=quotas)

        assert len(resultat.items) == 1

    def test_le_recapitulatif_rend_compte_des_quotas_par_registre(self, tmp_path):
        """AC5."""
        socle = self._socle_registre(tmp_path, "apprendre", 5)
        quotas = tmp_path / "quotas.yaml"
        quotas.write_text("quotas:\n  apprendre: 2\n", encoding="utf-8")

        resume = collecter(socle, quotas_path=quotas).resume()

        assert "3 écarté(s) par dépassement de quota" in resume
        assert "apprendre" in resume

    def test_une_source_entierement_absorbee_par_le_quota_est_diagnostiquee(
        self, tmp_path, caplog
    ):
        """Une source noyée par une autre du même registre doit être
        diagnostiquée comme un quota dépassé, pas une cause indéterminée."""
        payload_dominante = tmp_path / "dominante.json"
        payload_dominante.write_text(
            json.dumps([{"id": f"d{i}", "titre": f"Dominant {i}"} for i in range(5)]),
            encoding="utf-8",
        )
        payload_noyee = tmp_path / "noyee.json"
        payload_noyee.write_text(
            json.dumps([{"id": "n0", "titre": "Noyé"}]), encoding="utf-8"
        )

        socle = _socle(
            tmp_path,
            f"""
            sources:
              - id: source-dominante
                type: json
                priorite: 10
                url: {payload_dominante.as_uri()}
                langue: fr
                registre: apprendre
                mapping: {{guid: id, titre: titre}}
              - id: source-noyee
                type: json
                priorite: 1
                url: {payload_noyee.as_uri()}
                langue: fr
                registre: apprendre
                mapping: {{guid: id, titre: titre}}
            """,
        )
        quotas = tmp_path / "quotas.yaml"
        quotas.write_text("quotas:\n  apprendre: 1\n", encoding="utf-8")
        # Le profil neutre par défaut (`conftest.py`) laisse tous les scores
        # à égalité : le départage stable garde les items dans l'ordre de
        # collecte, donc 'source-dominante' (déclarée en premier) l'emporte.

        with caplog.at_level("WARNING"):
            resultat = collecter(socle, quotas_path=quotas)

        assert [r.source_id for r in resultat.sources_absorbees] == ["source-noyee"]
        message = next(
            r.message for r in caplog.records if "source-noyee' absorbée" in r.message
        )
        assert "quota de registre dépassé" in message


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
