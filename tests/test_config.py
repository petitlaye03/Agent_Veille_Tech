import textwrap

import pytest

from veille.config import FORMAT_DEFAUT, SourceConfig, load_sources


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


# --- Audit du 2026-09-22 : nom, format, horizon de fraîcheur ----------


def _ecrire(tmp_path, contenu):
    chemin = tmp_path / "sources.yaml"
    chemin.write_text(contenu, encoding="utf-8")
    return chemin



def test_source_sans_metadonnees_d_affichage_garde_des_valeurs_sures():
    """Les trois champs sont facultatifs : une `sources.yaml` antérieure à
    l'audit doit continuer de se charger exactement comme avant."""
    source = SourceConfig(id="s", type="rss", url="u", langue="fr", registre="apprendre")

    assert source.nom == ""
    assert source.format == FORMAT_DEFAUT
    assert source.horizon_jours is None


def test_format_est_normalise_en_minuscules(tmp_path):
    chemin = _ecrire(tmp_path, "sources:\n  - {id: s, type: rss, url: u, langue: fr, registre: apprendre, format: PODCAST}\n")

    assert load_sources(chemin)[0].format == "podcast"


def test_format_inconnu_retombe_sur_le_defaut_avec_avertissement(tmp_path, caplog):
    """Laisser passer un format inventé produirait une pastille vide sur la
    page plutôt qu'un avertissement lisible."""
    chemin = _ecrire(tmp_path, "sources:\n  - {id: s, type: rss, url: u, langue: fr, registre: apprendre, format: chanson}\n")

    with caplog.at_level("WARNING"):
        source = load_sources(chemin)[0]

    assert source.format == FORMAT_DEFAUT
    assert "chanson" in caplog.text


def test_horizon_jours_mal_type_est_ignore_sans_faire_lever(tmp_path, caplog):
    """Même piège que `seuil_signal` laissé mal typé : comparé plus loin à un
    nombre de jours, il lèverait hors de l'isolation de panne par source."""
    chemin = _ecrire(tmp_path, "sources:\n  - {id: s, type: rss, url: u, langue: fr, registre: apprendre, horizon_jours: sept}\n")

    with caplog.at_level("WARNING"):
        source = load_sources(chemin)[0]

    assert source.horizon_jours is None
    assert "horizon_jours" in caplog.text


def test_horizon_jours_nul_ou_negatif_est_rejete(tmp_path):
    """Un horizon à 0 ou -3 ne décrit aucune fenêtre : il viderait la source."""
    chemin = _ecrire(tmp_path, "sources:\n  - {id: a, type: rss, url: u, langue: fr, registre: apprendre, horizon_jours: 0}\n  - {id: b, type: rss, url: u, langue: fr, registre: apprendre, horizon_jours: -3}\n")

    assert [s.horizon_jours for s in load_sources(chemin)] == [None, None]


def test_horizon_jours_booleen_est_rejete(tmp_path):
    """`horizon_jours: yes` vaut `True` en YAML 1.1 — donc un horizon d'un
    jour, silencieusement."""
    chemin = _ecrire(tmp_path, "sources:\n  - {id: s, type: rss, url: u, langue: fr, registre: apprendre, horizon_jours: yes}\n")

    assert load_sources(chemin)[0].horizon_jours is None


def test_nom_compose_d_espaces_est_ramene_a_vide(tmp_path):
    """Truthy tel quel, il ferait afficher un blanc à la place de la source."""
    chemin = _ecrire(tmp_path, "sources:\n  - {id: s, type: rss, url: u, langue: fr, registre: apprendre, nom: '   '}\n")

    assert load_sources(chemin)[0].nom == ""
