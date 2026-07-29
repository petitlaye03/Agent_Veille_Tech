"""Non-régressions issues de la revue de code de la Story 1.3.

Chaque test ici correspond à un défaut reproduit avant correction.
"""

from datetime import datetime, timezone

import pytest

from veille.dedup import dedupliquer, normaliser_url
from veille.models import Item


def _item(source_id="s", guid="g", url="https://ex.invalid/a", titre="T"):
    return Item(
        source_id=source_id,
        guid=guid,
        titre=titre,
        date_publication=datetime(2026, 7, 24, tzinfo=timezone.utc),
        langue="fr",
        registre="apprendre",
        url=url,
        contenu_brut="",
    )


class TestUrlMalformee:
    """Une URL illisible ne doit jamais faire tomber le run entier.

    Le dédoublonnage s'exécute APRÈS la boucle protégée par source : une
    exception ici contourne l'isolation de panne (AD-6) et fait perdre la
    nuit complète, y compris les sources saines.
    """

    @pytest.mark.parametrize(
        "url",
        [
            "https://[fe80::1/x",  # littéral IPv6 non fermé
            "http://[::1",
            "https://ex.invalid:port/x",  # port non numérique
        ],
    )
    def test_une_url_malformee_ne_leve_jamais(self, url):
        assert normaliser_url(url) == ""

    def test_une_url_non_textuelle_ne_leve_jamais(self):
        assert normaliser_url(None) == ""
        assert normaliser_url(12345) == ""

    def test_le_dedoublonnage_survit_a_une_url_malformee(self):
        items = [
            _item(source_id="saine", guid="g1", url="https://ex.invalid/bon"),
            _item(source_id="cassee", guid="g2", url="https://[fe80::1/x"),
        ]

        retenus, _ = dedupliquer(items, priorites={})

        # Les deux survivent : l'article sain n'est pas sacrifié.
        assert len(retenus) == 2


class TestTransitivite:
    """Deux critères d'identité doivent être unifiés, pas consultés l'un après l'autre."""

    def test_trois_items_lies_transitivement_ne_font_qu_un(self):
        # a≡b par l'URL ; b≡c par (source, guid) ; donc a≡b≡c
        items = [
            _item(source_id="primaire", guid="g1", url="https://ex.invalid/annonce"),
            _item(source_id="agregateur", guid="g2", url="https://ex.invalid/annonce"),
            _item(source_id="agregateur", guid="g2", url="https://ex.invalid/reprise"),
        ]

        retenus, _ = dedupliquer(items, priorites={})

        assert len(retenus) == 1

    def test_un_guid_deja_ecarte_reste_reconnu_ensuite(self):
        items = [
            _item(source_id="a", guid="g1", url="https://ex.invalid/u1"),
            _item(source_id="a", guid="g2", url="https://ex.invalid/u1"),
            _item(source_id="a", guid="g2", url="https://ex.invalid/u9"),
        ]

        retenus, _ = dedupliquer(items, priorites={})

        assert len(retenus) == 1


class TestIndependanceDeLOrdre:
    """Le partitionnement ne doit pas dépendre de l'ordre d'arrivée.

    L'ordre de collecte suit l'ordre du YAML : ajouter une source sans
    rapport ne doit pas changer combien d'articles survivent.
    """

    def test_toutes_les_permutations_donnent_le_meme_compte(self):
        from itertools import permutations

        base = [
            _item(source_id="a", guid="g1", url="https://ex.invalid/u1"),
            _item(source_id="a", guid="g1", url="https://ex.invalid/u2"),
            _item(source_id="b", guid="g9", url="https://ex.invalid/u2"),
        ]

        comptes = {len(dedupliquer(list(p), {})[0]) for p in permutations(base)}

        assert comptes == {1}, f"comptes observés selon l'ordre : {comptes}"


class TestPrioriteAvecIdentiteMultiple:
    """AC3 : deux items de même (source, guid) ne survivent jamais tous les deux."""

    def test_meme_source_meme_guid_avec_priorites_inegales(self):
        items = [
            _item(source_id="a", guid="g1", url="https://ex.invalid/u1"),
            _item(source_id="b", guid="g2", url="https://ex.invalid/u2"),
            _item(source_id="a", guid="g1", url="https://ex.invalid/u2"),
        ]

        retenus, _ = dedupliquer(items, priorites={"a": 10, "b": 0})

        paires = [(i.source_id, i.guid) for i in retenus]
        assert len(paires) == len(set(paires)), f"(source, guid) dupliqué : {paires}"


class TestGuidVide:
    """Un guid vide ne doit pas effondrer toute une source en un seul item."""

    def test_des_items_sans_guid_ni_url_restent_distincts(self):
        items = [
            _item(source_id="a", guid="", url="", titre="Premier"),
            _item(source_id="a", guid="", url="", titre="Deuxieme"),
            _item(source_id="a", guid="", url="", titre="Troisieme"),
        ]

        retenus, _ = dedupliquer(items, priorites={})

        assert len(retenus) == 3


class TestNormalisationRenforcee:
    def test_les_ports_par_defaut_sont_neutralises(self):
        assert normaliser_url("https://ex.invalid:443/a") == normaliser_url(
            "https://ex.invalid/a"
        )
        assert normaliser_url("http://ex.invalid:80/a") == normaliser_url(
            "https://ex.invalid/a"
        )

    def test_un_port_explicite_non_standard_est_conserve(self):
        assert normaliser_url("https://ex.invalid:8443/a") != normaliser_url(
            "https://ex.invalid/a"
        )

    def test_l_encodage_pourcent_est_normalise(self):
        assert normaliser_url("https://ex.invalid/%7Euser") == normaliser_url(
            "https://ex.invalid/~user"
        )

    def test_une_url_sans_hote_ne_produit_pas_de_cle_collisionnable(self):
        """Sans hôte, deux sites publiant /news/x seraient confondus."""
        assert normaliser_url("/news/article") == ""

    def test_le_prefixe_www_repete_est_entierement_retire(self):
        assert normaliser_url("https://www.www.ex.invalid/a") == normaliser_url(
            "https://ex.invalid/a"
        )


class TestParametresSignifiants:
    """`source` et `ref` portent l'identité sur certains sites : ne pas les jeter."""

    def test_le_parametre_source_distingue_deux_articles(self):
        assert normaliser_url("https://ex.invalid/a?source=1") != normaliser_url(
            "https://ex.invalid/a?source=2"
        )

    def test_les_parametres_utm_restent_neutralises(self):
        assert normaliser_url("https://ex.invalid/a?utm_source=x") == normaliser_url(
            "https://ex.invalid/a"
        )


class TestRapportComplet:
    """AC4 : le rapport doit permettre de tracer, pas seulement de compter."""

    def test_le_rapport_indique_qui_a_absorbe_quoi(self):
        items = [
            _item(source_id="agregateur", guid="g1", url="https://ex.invalid/x"),
            _item(source_id="primaire", guid="g2", url="https://ex.invalid/x"),
        ]

        _, rapport = dedupliquer(items, priorites={"primaire": 10})

        assert rapport.ecartes_par_source == {"agregateur": 1}
        assert rapport.gagnants_par_source == {"primaire": 1}
