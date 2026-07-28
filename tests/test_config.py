import textwrap

import pytest

from veille.config import SourceConfig, load_sources


def test_load_sources_lit_un_fichier_valide(tmp_path):
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        textwrap.dedent(
            """
            sources:
              - id: openai-news
                type: rss
                url: https://openai.com/news/rss.xml
                langue: en
                registre: ce_qui_bouge
            """
        ),
        encoding="utf-8",
    )

    sources = load_sources(sources_yaml)

    assert len(sources) == 1
    assert isinstance(sources[0], SourceConfig)
    assert sources[0].id == "openai-news"
    assert sources[0].type == "rss"
    assert sources[0].url == "https://openai.com/news/rss.xml"
    assert sources[0].langue == "en"
    assert sources[0].registre == "ce_qui_bouge"


def test_load_sources_chaque_source_a_un_id_non_vide(tmp_path):
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        textwrap.dedent(
            """
            sources:
              - id: openai-news
                type: rss
                url: https://openai.com/news/rss.xml
                langue: en
                registre: ce_qui_bouge
              - id: hf-daily-papers
                type: rss
                url: https://example.invalid/feed
                langue: en
                registre: apprendre
            """
        ),
        encoding="utf-8",
    )

    sources = load_sources(sources_yaml)

    assert all(source.id for source in sources)
    assert [s.id for s in sources] == ["openai-news", "hf-daily-papers"]


def test_une_entree_invalide_n_empeche_pas_de_charger_les_autres(tmp_path):
    """Une faute de frappe dans une seule entrée ne doit pas tuer tout le socle."""
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        textwrap.dedent(
            """
            sources:
              - id: source-cassee
                type: rss
                url: https://example.invalid/feed
                langue: fr
                champ_inconnu: valeur inattendue
              - id: source-valide
                type: rss
                url: https://example.invalid/ok
                langue: fr
                registre: apprendre
            """
        ),
        encoding="utf-8",
    )

    sources = load_sources(sources_yaml)

    assert [s.id for s in sources] == ["source-valide"]


def test_fichier_sans_cle_sources_retourne_liste_vide(tmp_path):
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text("sources:\n", encoding="utf-8")

    assert load_sources(sources_yaml) == []


def test_fichier_yaml_de_forme_inattendue_retourne_liste_vide(tmp_path):
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text("- ceci est une liste, pas un mapping\n", encoding="utf-8")

    assert load_sources(sources_yaml) == []


def test_fichier_absent_leve_une_erreur_explicite(tmp_path):
    """load_sources reste stricte ; c'est `collect.run` qui absorbe l'échec."""
    with pytest.raises(FileNotFoundError):
        load_sources(tmp_path / "inexistant.yaml")
