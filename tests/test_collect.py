import textwrap
from pathlib import Path

from veille.collect import run

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
