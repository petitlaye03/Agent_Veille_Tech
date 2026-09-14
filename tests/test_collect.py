import textwrap
from pathlib import Path

from veille import store
from veille.collect import collecter, run
from veille.filter import ItemScore

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _write_sources_yaml(tmp_path: Path) -> Path:
    sources_yaml = tmp_path / "sources.yaml"
    feed_path = (FIXTURE_DIR / "sample_feed.xml").as_posix()
    sources_yaml.write_text(
        textwrap.dedent(
            f"""
            sources:
              - id: test-source
                type: rss
                url: {feed_path}
                langue: fr
                registre: apprendre
            """
        ),
        encoding="utf-8",
    )
    return sources_yaml


def test_run_collecte_depuis_sources_yaml(tmp_path):
    sources_yaml = _write_sources_yaml(tmp_path)

    items = run(sources_yaml)

    assert len(items) == 2
    assert all(item.source_id == "test-source" for item in items)


def test_run_deux_executions_consecutives_ne_plantent_pas(tmp_path):
    sources_yaml = _write_sources_yaml(tmp_path)

    premiere_execution = run(sources_yaml)
    deuxieme_execution = run(sources_yaml)

    assert len(premiere_execution) == len(deuxieme_execution) == 2


def test_run_ignore_un_type_de_source_non_reconnu(tmp_path, caplog):
    sources_yaml = tmp_path / "sources.yaml"
    feed_path = (FIXTURE_DIR / "sample_feed.xml").as_posix()
    sources_yaml.write_text(
        textwrap.dedent(
            f"""
            sources:
              - id: source-inconnue
                type: futur-type-non-implemente
                url: https://example.invalid/whatever
                langue: fr
                registre: apprendre
              - id: test-source
                type: rss
                url: {feed_path}
                langue: fr
                registre: apprendre
            """
        ),
        encoding="utf-8",
    )

    items = run(sources_yaml)

    # La source inconnue est ignorée sans faire planter la collecte des autres.
    assert len(items) == 2
    assert all(item.source_id == "test-source" for item in items)


def test_run_survit_a_un_fichier_de_sources_absent(tmp_path):
    """Un problème de configuration ne doit jamais faire planter la nuit entière."""
    items = run(tmp_path / "fichier_qui_n_existe_pas.yaml")

    assert items == []


def test_run_survit_a_un_fichier_de_sources_illisible(tmp_path):
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text("sources: [ceci: n'est: pas: du yaml valide\n", encoding="utf-8")

    items = run(sources_yaml)

    assert items == []


def test_run_collecte_un_socle_melangeant_les_trois_types(tmp_path):
    """Le cœur de la Story 1.2 : RSS, JSON et scraping produisent le même format."""
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        textwrap.dedent(
            f"""
            sources:
              - id: source-rss
                type: rss
                url: {(FIXTURE_DIR / "sample_feed.xml").as_posix()}
                langue: fr
                registre: apprendre
              - id: source-json
                type: json
                url: {(FIXTURE_DIR / "hf_daily_papers.json").as_uri()}
                langue: en
                registre: apprendre
                mapping:
                  guid: paper.id
                  titre: title
                  date_publication: publishedAt
                  contenu_brut: paper.summary
                url_modele: https://huggingface.co/papers/{{guid}}
              - id: source-scrape
                type: scrape
                url: {(FIXTURE_DIR / "anthropic_news.html").as_uri()}
                langue: en
                registre: ce_qui_bouge
                selecteur: /news/
                base_url: https://www.anthropic.com
            """
        ),
        encoding="utf-8",
    )

    items = run(sources_yaml)

    # 2 (rss) + 2 (json) + 4 (scrape)
    assert len(items) == 8

    # Les trois types sont représentés
    assert {i.source_id for i in items} == {"source-rss", "source-json", "source-scrape"}

    # Format canonique homogène quel que soit le type d'origine (AC2)
    for item in items:
        assert item.guid, f"guid vide pour {item.source_id}"
        assert item.titre, f"titre vide pour {item.source_id}"
        assert item.date_publication.tzinfo is not None
        assert item.langue and item.registre


# --- Story 1.8 : ResultatCollecte.resultats_repartis --------------------


def test_collecter_expose_resultats_repartis(tmp_path):
    """Sans ce champ, `pipeline.py` n'a aucun moyen de fournir un classement
    à `marquer_recommandation` — le Score serait calculé puis jeté, comme
    documenté depuis la revue de la Story 1.4 (`deferred-work.md`)."""
    sources_yaml = _write_sources_yaml(tmp_path)

    resultat = collecter(sources_yaml)

    assert resultat.resultats_repartis
    assert all(isinstance(rs, ItemScore) for rs in resultat.resultats_repartis)


def test_resultats_repartis_dans_le_meme_ordre_que_items(tmp_path):
    sources_yaml = _write_sources_yaml(tmp_path)

    resultat = collecter(sources_yaml)

    assert [item_score.item for item_score in resultat.resultats_repartis] == resultat.items


def test_resultats_repartis_vide_si_aucune_source_configuree(tmp_path):
    resultat = collecter(tmp_path / "fichier_qui_n_existe_pas.yaml")

    assert resultat.resultats_repartis == []


def test_une_source_defaillante_n_empeche_pas_les_autres_types(tmp_path):
    """Une source JSON injoignable ne doit pas priver le digest des sources RSS."""
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        textwrap.dedent(
            f"""
            sources:
              - id: json-injoignable
                type: json
                url: file:///chemin/qui/n/existe/pas.json
                langue: en
                registre: apprendre
                mapping:
                  guid: id
              - id: source-rss
                type: rss
                url: {(FIXTURE_DIR / "sample_feed.xml").as_posix()}
                langue: fr
                registre: apprendre
            """
        ),
        encoding="utf-8",
    )

    items = run(sources_yaml)

    assert len(items) == 2
    assert all(i.source_id == "source-rss" for i in items)


# --- Déjà vu (Story 3.4) ----------------------------------------------


def test_collecter_sans_connexion_deja_vus_ne_filtre_rien(tmp_path):
    """`deja_vus_conn` est optionnel (`None` par défaut) : sans connexion
    fournie, aucun filtrage « déjà vu » n'a lieu — pas de régression pour
    les appelants existants."""
    sources_yaml = _write_sources_yaml(tmp_path)

    resultat = collecter(sources_yaml)

    assert len(resultat.items) == 2
    assert resultat.deja_vu.total_ecartes == 0


def test_collecter_ecarte_un_item_deja_marque_vu(tmp_path):
    sources_yaml = _write_sources_yaml(tmp_path)
    conn = store.ouvrir(tmp_path / "deja-vu.sqlite3")

    # Premier passage : rien de connu, les deux items sont retenus, puis
    # marqués vus (comme le ferait `pipeline.executer()` après publication).
    premier = collecter(sources_yaml, deja_vus_conn=conn)
    assert len(premier.items) == 2
    store.marquer_vus(premier.items, conn)

    # Second passage, mêmes sources : les deux items sont déjà vus, donc
    # écartés **avant** même le seuil de signal/dédoublonnage/scoring.
    second = collecter(sources_yaml, deja_vus_conn=conn)
    conn.close()

    assert second.items == []
    assert second.deja_vu.total_ecartes == 2
    assert second.deja_vu.ecartes_par_source == {"test-source": 2}


def test_collecter_ne_filtre_que_les_items_deja_vus_pas_les_nouveaux(tmp_path):
    sources_yaml = tmp_path / "sources.yaml"
    feed_path = (FIXTURE_DIR / "sample_feed.xml").as_posix()
    sources_yaml.write_text(
        textwrap.dedent(
            f"""
            sources:
              - id: test-source
                type: rss
                url: {feed_path}
                langue: fr
                registre: apprendre
            """
        ),
        encoding="utf-8",
    )
    conn = store.ouvrir(tmp_path / "deja-vu.sqlite3")
    conn.execute(
        "INSERT OR IGNORE INTO deja_vu (cle) VALUES (?)",
        ("url:example.invalid/articles/premier",),
    )
    conn.commit()

    resultat = collecter(sources_yaml, deja_vus_conn=conn)
    conn.close()

    assert len(resultat.items) == 1
    assert resultat.items[0].url == "https://example.invalid/articles/deuxieme"
    assert resultat.deja_vu.total_ecartes == 1
