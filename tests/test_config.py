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


# --- Validation de `seuil_signal` (revue 2026-08-28) --------------------
#
# `sources.yaml` est édité à la main (AD-3) : une faute de frappe y est un
# incident attendu. Une valeur mal typée levait auparavant une TypeError à
# la comparaison, bien plus loin dans le pipeline et hors de l'isolation de
# panne par source — au prix de la nuit entière.


def _socle_avec_seuil(tmp_path, valeur: str):
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        textwrap.dedent(
            f"""
            sources:
              - id: source-seuil
                type: json
                url: https://example.invalid/api
                langue: fr
                registre: apprendre
                seuil_signal: {valeur}
            """
        ),
        encoding="utf-8",
    )
    return load_sources(sources_yaml)[0]


def test_un_seuil_signal_numerique_est_conserve(tmp_path):
    assert _socle_avec_seuil(tmp_path, "15").seuil_signal == 15.0


def test_un_seuil_signal_non_numerique_est_neutralise(tmp_path):
    """La source reste chargée — seul le seuil est abandonné : perdre la
    source entière pour un seuil illisible serait pire que le mal."""
    source = _socle_avec_seuil(tmp_path, "quinze")

    assert source.seuil_signal is None
    assert source.id == "source-seuil"


def test_un_seuil_signal_booleen_est_neutralise(tmp_path):
    """`yes` vaut `True` en YAML : `float(True)` donnerait un seuil de 1.0."""
    assert _socle_avec_seuil(tmp_path, "yes").seuil_signal is None


def test_un_seuil_signal_nan_est_neutralise(tmp_path):
    """Toute comparaison à `nan` étant fausse, un tel seuil laisserait
    passer l'intégralité des items sans le moindre signe."""
    assert _socle_avec_seuil(tmp_path, ".nan").seuil_signal is None


def test_un_seuil_signal_invalide_n_empeche_pas_la_collecte(tmp_path):
    """Le scénario complet : le pipeline ne doit pas lever."""
    from veille.filter import filtrer_par_signal
    from veille.models import Item
    from datetime import datetime, timezone

    source = _socle_avec_seuil(tmp_path, "quinze")
    item = Item(
        source_id="source-seuil", guid="g", titre="t",
        date_publication=datetime(2026, 8, 1, tzinfo=timezone.utc),
        langue="fr", registre="apprendre", url="u", contenu_brut="", signal=3.0,
    )

    retenus, rapport = filtrer_par_signal([item], {"source-seuil": source})

    assert retenus == [item]
    assert rapport.total_ecartes == 0
