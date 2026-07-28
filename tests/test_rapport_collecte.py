"""Observabilité de la collecte.

Sans compte par source, une nuit où trois sources sur quatre tombent
ressemble exactement à une nuit saine dans les journaux. C'est le signal
qui rend tous les autres défauts visibles.
"""

import textwrap
from pathlib import Path

from veille.collect import collecter, run

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _ecrire_socle(tmp_path: Path, contenu: str) -> Path:
    chemin = tmp_path / "sources.yaml"
    chemin.write_text(textwrap.dedent(contenu), encoding="utf-8")
    return chemin


def test_le_rapport_donne_le_compte_par_source(tmp_path):
    socle = _ecrire_socle(
        tmp_path,
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
        """,
    )

    resultat = collecter(socle)

    comptes = {r.source_id: r.nb_items for r in resultat.rapports}
    assert comptes == {"source-rss": 2, "source-json": 2}
    assert len(resultat.items) == 4


def test_une_source_muette_est_signalee_distinctement(tmp_path):
    """Zéro item sans erreur : le mode de panne le plus insidieux."""
    page_vide = tmp_path / "vide.html"
    page_vide.write_text("<html><body>Rien ici.</body></html>", encoding="utf-8")

    socle = _ecrire_socle(
        tmp_path,
        f"""
        sources:
          - id: source-muette
            type: scrape
            url: {page_vide.as_uri()}
            langue: fr
            registre: apprendre
            selecteur: /news/
            base_url: https://exemple.invalid
          - id: source-vivante
            type: rss
            url: {(FIXTURE_DIR / "sample_feed.xml").as_posix()}
            langue: fr
            registre: apprendre
        """,
    )

    resultat = collecter(socle)

    muettes = [r.source_id for r in resultat.sources_muettes]
    assert muettes == ["source-muette"]
    assert not resultat.sources_en_echec


def test_une_source_en_echec_est_distinguee_d_une_source_muette(tmp_path):
    socle = _ecrire_socle(
        tmp_path,
        f"""
        sources:
          - id: source-cassee
            type: json
            url: file:///chemin/inexistant.json
            langue: fr
            registre: apprendre
            mapping:
              guid: id
          - id: source-vivante
            type: rss
            url: {(FIXTURE_DIR / "sample_feed.xml").as_posix()}
            langue: fr
            registre: apprendre
        """,
    )

    resultat = collecter(socle)

    en_echec = [r.source_id for r in resultat.sources_en_echec]
    assert en_echec == ["source-cassee"]
    # Une source en échec n'est pas « muette » : la cause est connue.
    assert not resultat.sources_muettes
    assert resultat.rapports[0].echec  # raison renseignée


def test_le_resume_est_lisible_et_mentionne_les_anomalies(tmp_path):
    page_vide = tmp_path / "vide.html"
    page_vide.write_text("<html><body></body></html>", encoding="utf-8")

    socle = _ecrire_socle(
        tmp_path,
        f"""
        sources:
          - id: source-muette
            type: scrape
            url: {page_vide.as_uri()}
            langue: fr
            registre: apprendre
            selecteur: /news/
            base_url: https://exemple.invalid
          - id: source-vivante
            type: rss
            url: {(FIXTURE_DIR / "sample_feed.xml").as_posix()}
            langue: fr
            registre: apprendre
        """,
    )

    resume = collecter(socle).resume()

    assert "source-vivante" in resume
    assert "source-muette" in resume
    assert "2" in resume  # le compte de la source vivante


def test_les_dates_approximatives_sont_comptees(tmp_path):
    """Une date illisible retombe sur l'heure de collecte : il faut le savoir."""
    page = tmp_path / "sans_date.html"
    page.write_text(
        '<a href="/news/a"><h2>Article sans date</h2></a>'
        '<a href="/news/b"><h2>Autre sans date</h2></a>',
        encoding="utf-8",
    )

    socle = _ecrire_socle(
        tmp_path,
        f"""
        sources:
          - id: sans-dates
            type: scrape
            url: {page.as_uri()}
            langue: fr
            registre: apprendre
            selecteur: /news/
            base_url: https://exemple.invalid
        """,
    )

    resultat = collecter(socle)

    rapport = resultat.rapports[0]
    assert rapport.nb_items == 2
    assert rapport.nb_dates_approximatives == 2


def test_run_reste_compatible_et_ne_retourne_que_les_items(tmp_path):
    socle = _ecrire_socle(
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

    items = run(socle)

    assert isinstance(items, list)
    assert len(items) == 2
