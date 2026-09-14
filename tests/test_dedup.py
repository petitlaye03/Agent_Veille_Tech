import time
from datetime import datetime, timezone

from veille.dedup import dedupliquer, normaliser_url
from veille.models import Item


def _item(source_id="s", guid=None, url="https://exemple.invalid/a", titre="T"):
    return Item(
        source_id=source_id,
        guid=guid if guid is not None else url,
        titre=titre,
        date_publication=datetime(2026, 7, 24, 10, 0, tzinfo=timezone.utc),
        langue="fr",
        registre="apprendre",
        url=url,
        contenu_brut="",
    )


class TestNormalisationUrl:
    def test_le_schema_et_le_prefixe_www_sont_neutralises(self):
        assert normaliser_url("http://www.exemple.invalid/a") == normaliser_url(
            "https://exemple.invalid/a"
        )

    def test_la_barre_oblique_finale_est_neutralisee(self):
        assert normaliser_url("https://exemple.invalid/a/") == normaliser_url(
            "https://exemple.invalid/a"
        )

    def test_le_fragment_est_neutralise(self):
        assert normaliser_url("https://exemple.invalid/a#section") == normaliser_url(
            "https://exemple.invalid/a"
        )

    def test_les_parametres_de_suivi_sont_neutralises(self):
        avec_suivi = "https://exemple.invalid/a?utm_source=news&utm_medium=mail&fbclid=xyz"
        assert normaliser_url(avec_suivi) == normaliser_url("https://exemple.invalid/a")

    def test_les_parametres_signifiants_sont_conserves(self):
        """`?id=42` peut être l'identité même de l'article : ne pas le jeter."""
        a = normaliser_url("https://exemple.invalid/article?id=42")
        b = normaliser_url("https://exemple.invalid/article?id=43")

        assert a != b

    def test_les_parametres_signifiants_survivent_au_nettoyage_du_suivi(self):
        a = normaliser_url("https://exemple.invalid/article?id=42&utm_source=x")
        b = normaliser_url("https://exemple.invalid/article?id=42")

        assert a == b

    def test_l_ordre_des_parametres_n_influe_pas(self):
        a = normaliser_url("https://exemple.invalid/a?x=1&y=2")
        b = normaliser_url("https://exemple.invalid/a?y=2&x=1")

        assert a == b

    def test_une_url_vide_reste_geree(self):
        assert normaliser_url("") == ""


class TestDedoublonnage:
    def test_deux_sources_sur_la_meme_url_ne_produisent_qu_une_entree(self):
        items = [
            _item(source_id="agregateur", url="https://exemple.invalid/annonce"),
            _item(source_id="source-primaire", url="https://exemple.invalid/annonce"),
        ]

        retenus, _ = dedupliquer(items, priorites={})

        assert len(retenus) == 1

    def test_la_source_prioritaire_l_emporte(self):
        items = [
            _item(source_id="agregateur", url="https://exemple.invalid/annonce"),
            _item(source_id="source-primaire", url="https://exemple.invalid/annonce"),
        ]

        retenus, _ = dedupliquer(items, priorites={"source-primaire": 10, "agregateur": 0})

        assert [i.source_id for i in retenus] == ["source-primaire"]

    def test_la_priorite_l_emporte_meme_si_l_agregateur_arrive_en_second(self):
        """L'ordre de collecte ne doit pas décider du gagnant."""
        items = [
            _item(source_id="source-primaire", url="https://exemple.invalid/annonce"),
            _item(source_id="agregateur", url="https://exemple.invalid/annonce"),
        ]

        retenus, _ = dedupliquer(items, priorites={"source-primaire": 10, "agregateur": 0})

        assert [i.source_id for i in retenus] == ["source-primaire"]

    def test_a_priorite_egale_le_premier_rencontre_est_conserve(self):
        items = [
            _item(source_id="a", url="https://exemple.invalid/x", titre="Version A"),
            _item(source_id="b", url="https://exemple.invalid/x", titre="Version B"),
        ]

        retenus, _ = dedupliquer(items, priorites={})

        assert [i.titre for i in retenus] == ["Version A"]

    def test_les_variantes_d_url_sont_reconnues_comme_un_doublon(self):
        items = [
            _item(source_id="a", url="https://exemple.invalid/annonce"),
            _item(source_id="b", url="http://www.exemple.invalid/annonce/?utm_source=x#top"),
        ]

        retenus, _ = dedupliquer(items, priorites={})

        assert len(retenus) == 1

    def test_un_guid_repete_dans_une_meme_source_ne_passe_qu_une_fois(self):
        items = [
            _item(source_id="a", guid="meme-id", url="https://exemple.invalid/1"),
            _item(source_id="a", guid="meme-id", url="https://exemple.invalid/2"),
        ]

        retenus, _ = dedupliquer(items, priorites={})

        assert len(retenus) == 1

    def test_des_articles_distincts_sont_tous_conserves(self):
        items = [
            _item(source_id="a", url="https://exemple.invalid/1"),
            _item(source_id="a", url="https://exemple.invalid/2"),
            _item(source_id="b", url="https://exemple.invalid/3"),
        ]

        retenus, _ = dedupliquer(items, priorites={})

        assert len(retenus) == 3

    def test_l_ordre_des_items_retenus_est_preserve(self):
        items = [
            _item(source_id="a", url="https://exemple.invalid/1", titre="Premier"),
            _item(source_id="a", url="https://exemple.invalid/2", titre="Deuxieme"),
            _item(source_id="b", url="https://exemple.invalid/1", titre="Doublon"),
        ]

        retenus, _ = dedupliquer(items, priorites={})

        assert [i.titre for i in retenus] == ["Premier", "Deuxieme"]

    def test_un_identifiant_identique_dans_deux_flux_ne_designe_pas_le_meme_article(self):
        """Un `guid` natif n'a de sens que dans son propre flux.

        Deux flux distincts peuvent employer « post-123 » pour des articles
        sans rapport : les confondre supprimerait un article légitime.
        """
        items = [
            _item(source_id="a", guid="post-123", url=""),
            _item(source_id="b", guid="post-123", url=""),
        ]

        retenus, _ = dedupliquer(items, priorites={})

        assert len(retenus) == 2

    def test_un_item_sans_url_reste_dedoublonne_par_son_guid_dans_sa_source(self):
        items = [
            _item(source_id="a", guid="abc", url=""),
            _item(source_id="a", guid="abc", url=""),
            _item(source_id="a", guid="def", url=""),
        ]

        retenus, _ = dedupliquer(items, priorites={})

        assert len(retenus) == 2


class TestRapportDedoublonnage:
    def test_le_rapport_compte_les_ecarts_par_source(self):
        items = [
            _item(source_id="primaire", url="https://exemple.invalid/x"),
            _item(source_id="agregateur", url="https://exemple.invalid/x"),
            _item(source_id="agregateur", url="https://exemple.invalid/y"),
            _item(source_id="primaire", url="https://exemple.invalid/y"),
        ]

        _, rapport = dedupliquer(items, priorites={"primaire": 10})

        assert rapport.total_ecartes == 2
        assert rapport.ecartes_par_source == {"agregateur": 2}

    def test_sans_doublon_le_rapport_est_vide(self):
        items = [
            _item(source_id="a", url="https://exemple.invalid/1"),
            _item(source_id="b", url="https://exemple.invalid/2"),
        ]

        _, rapport = dedupliquer(items, priorites={})

        assert rapport.total_ecartes == 0
        assert rapport.ecartes_par_source == {}


class TestPerformanceAEchelle:
    """Story 2.4 (AC2) : garde-fou de non-régression de complexité, pas un
    test de performance strict — `dedupliquer()` est un union-find à
    compression de chemin (quasi linéaire), jamais mesuré à un volume
    représentatif du socle réel avant cette story (Story 2.1, Task 4 :
    2800 items collectés sur 17 sources). Un plafond largement au-dessus du
    temps réel mesuré, pour ne jamais rendre la suite fragile sur une
    machine lente ou chargée ; sert uniquement à détecter une régression
    qui réintroduirait un comportement quadratique (ex. un scan de classes
    d'équivalence sans compression de chemin, ou une recherche par liste
    plutôt que par dictionnaire)."""

    def test_dedupliquer_reste_rapide_sur_un_volume_representatif_du_socle(self):
        # ~3200 items : au-dessus des 2800-2819 réellement collectés sur les
        # 17 sources actuelles (Stories 2.1/2.4). `guid` et `url` sont
        # délibérément indépendants (contrairement au défaut de `_item()`,
        # qui pose guid == url) : une vraie source porte les deux
        # séparément, et confondre les deux signaux masquerait une
        # régression propre à l'un des deux chemins d'identité.
        items = []

        # 2400 articles uniques.
        for i in range(2400):
            items.append(
                _item(source_id=f"source-{i % 17}", guid=f"guid-{i}", url=f"https://exemple.invalid/article-{i}")
            )

        # 500 doublons « par URL » : même URL qu'un article ci-dessus, mais
        # un guid distinct — deux sources numérotent différemment le même
        # article, cas réel (ex. Hacker News reprenant un article déjà
        # publié par sa source d'origine).
        for i in range(500):
            items.append(
                _item(
                    source_id=f"source-{(i + 1) % 17}",
                    guid=f"guid-doublon-url-{i}",
                    url=f"https://exemple.invalid/article-{i}",
                )
            )

        # 100 chaînes transitives à 3 membres (A, X, Y) : A et X partagent
        # une URL, X et Y partagent un guid — A et Y ne partagent directement
        # ni URL ni guid, seule la transitivité de l'union-find les regroupe
        # (raison d'être du regroupement en classes d'équivalence, énoncée
        # dans le docstring même de `dedup.py` — jamais exercée à l'échelle
        # avant cette story, trouvé en revue).
        # (`guid` est scopé par source dans `dedup.py` — `f"guid:{source_id}:
        # {guid}"` — donc X et Y doivent partager le **même** source_id pour
        # que leur guid commun les relie ; A, lui, vient d'une autre source
        # et ne les rejoint que par l'URL qu'il partage avec X.)
        for i in range(100):
            url_chaine = f"https://exemple.invalid/chaine-{i}"
            guid_partage = f"guid-chaine-{i}"
            source_a = f"source-{i % 17}"
            source_xy = f"source-{(i + 1) % 17}"
            items.append(_item(source_id=source_a, guid=f"guid-a-{i}", url=url_chaine))
            items.append(_item(source_id=source_xy, guid=guid_partage, url=url_chaine))
            items.append(
                _item(source_id=source_xy, guid=guid_partage, url=f"https://exemple.invalid/chaine-{i}-alt")
            )

        priorites = {f"source-{n}": n for n in range(17)}

        debut = time.monotonic()
        retenus, rapport = dedupliquer(items, priorites)
        duree = time.monotonic() - debut

        # 2400 uniques + 100 chaînes (1 survivant chacune) = 2500 classes.
        assert len(retenus) == 2500
        # 500 doublons par URL + 100 chaînes à 2 perdants chacune = 700.
        assert rapport.total_ecartes == 700
        # Plafond volontairement généreux (garde-fou, pas une exigence de
        # latence produit) — voir docstring de la classe.
        assert duree < 2.0, f"dedupliquer() a pris {duree:.2f}s sur ~3200 items — régression de complexité ?"
