"""Observabilité de la collecte.

Sans compte par source, une nuit où trois sources sur quatre tombent
ressemble exactement à une nuit saine dans les journaux. C'est le signal
qui rend tous les autres défauts visibles.
"""

import textwrap
from pathlib import Path

import pytest

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


def test_une_panne_http_rss_est_capturee_avec_sa_cause(tmp_path, monkeypatch):
    """Story 2.2 (AC1/AC3) : avant cette story, une panne HTTP sur une
    source RSS ne levait jamais (avalée dans le mécanisme `bozo`) et
    remontait comme MUETTE plutôt qu'ÉCHEC — la cause était perdue."""
    import httpx

    import veille.connectors.rss_connector as rss_module

    def _get_403(url, timeout, follow_redirects, headers):
        return httpx.Response(403, request=httpx.Request("GET", url))

    monkeypatch.setattr(rss_module.httpx, "get", _get_403)

    socle = _ecrire_socle(
        tmp_path,
        """
        sources:
          - id: source-en-panne-http
            type: rss
            url: https://exemple.invalid/flux.xml
            langue: fr
            registre: apprendre
        """,
    )

    resultat = collecter(socle)

    en_echec = [r.source_id for r in resultat.sources_en_echec]
    assert en_echec == ["source-en-panne-http"]
    assert not resultat.sources_muettes
    assert "403" in resultat.rapports[0].echec


def test_anomalie_signalee_quand_plus_de_la_moitie_des_sources_echouent(tmp_path, caplog):
    """Story 2.2 (AC4) : au-delà de 50 % de sources en échec la même nuit,
    le digest est quand même produit, mais l'anomalie doit être visible."""
    socle = _ecrire_socle(
        tmp_path,
        f"""
        sources:
          - id: cassee-1
            type: json
            url: file:///chemin/inexistant-1.json
            langue: fr
            registre: apprendre
          - id: cassee-2
            type: json
            url: file:///chemin/inexistant-2.json
            langue: fr
            registre: apprendre
          - id: cassee-3
            type: json
            url: file:///chemin/inexistant-3.json
            langue: fr
            registre: apprendre
          - id: source-vivante
            type: rss
            url: {(FIXTURE_DIR / "sample_feed.xml").as_posix()}
            langue: fr
            registre: apprendre
        """,
    )

    import logging

    with caplog.at_level(logging.ERROR, logger="veille.collect"):
        resultat = collecter(socle)

    # 3/4 sources en échec (75 %) : le digest est quand même produit...
    assert len(resultat.items) == 2
    # ... mais l'anomalie doit être détectable et journalisée de façon visible.
    assert resultat.anomalie_pannes is True
    assert resultat.taux_echec == pytest.approx(0.75)
    assert any("3/4" in record.message for record in caplog.records)
    assert any(record.levelno == logging.ERROR for record in caplog.records)


def test_pas_d_anomalie_quand_la_moitie_ou_moins_des_sources_echouent(tmp_path):
    """« Plus de la moitié » exclut l'égalité exacte à 50 %."""
    socle = _ecrire_socle(
        tmp_path,
        f"""
        sources:
          - id: cassee-1
            type: json
            url: file:///chemin/inexistant-1.json
            langue: fr
            registre: apprendre
          - id: source-vivante
            type: rss
            url: {(FIXTURE_DIR / "sample_feed.xml").as_posix()}
            langue: fr
            registre: apprendre
        """,
    )

    resultat = collecter(socle)

    assert resultat.anomalie_pannes is False
    assert resultat.taux_echec == pytest.approx(0.5)


def test_un_type_de_source_mal_orthographie_ne_compte_pas_comme_panne_reseau(tmp_path):
    """Trouvé en revue (Story 2.2) : une faute de frappe dans `type:` est une
    erreur de configuration statique, jamais tentée par un connecteur — pas
    une panne réseau/HTTP de la nuit. Ne doit pas déclencher l'anomalie."""
    socle = _ecrire_socle(
        tmp_path,
        f"""
        sources:
          - id: type-invalide
            type: rrs
            url: https://exemple.invalid/flux.xml
            langue: fr
            registre: apprendre
          - id: source-vivante
            type: rss
            url: {(FIXTURE_DIR / "sample_feed.xml").as_posix()}
            langue: fr
            registre: apprendre
        """,
    )

    resultat = collecter(socle)

    # La source à type invalide est bien en échec (pas muette)...
    assert [r.source_id for r in resultat.sources_en_echec] == ["type-invalide"]
    # ... mais elle ne compte pas dans le taux de panne réseau/HTTP : 0/2,
    # pas 1/2. Sans quoi une simple faute de frappe pourrait, à elle seule
    # ou combinée à une autre, déclencher à tort l'anomalie de la nuit.
    assert resultat.sources_en_panne_reseau == []
    assert resultat.taux_echec == 0.0
    assert resultat.anomalie_pannes is False


def test_une_source_rss_en_panne_http_n_empeche_pas_la_collecte_d_une_autre_source_rss(
    tmp_path, monkeypatch
):
    """AC1, spécifiquement RSS-vs-RSS : jusqu'ici, seule une source RSS en
    échec associée à une source d'un AUTRE type avait été testée (voir les
    tests ci-dessus). Trouvé en revue (Story 2.2) : vérifier explicitement
    que deux sources RSS dans le même run — l'une en panne HTTP, l'autre
    vivante — n'interfèrent pas."""
    import httpx

    import veille.connectors.rss_connector as rss_module

    appels = {"n": 0}

    def _get_selon_url(url, timeout, follow_redirects, headers):
        appels["n"] += 1
        if url == "https://exemple.invalid/en-panne.xml":
            return httpx.Response(500, request=httpx.Request("GET", url))
        return httpx.Response(
            200,
            content=(FIXTURE_DIR / "sample_feed.xml").read_bytes(),
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(rss_module.httpx, "get", _get_selon_url)

    socle = _ecrire_socle(
        tmp_path,
        """
        sources:
          - id: rss-en-panne
            type: rss
            url: https://exemple.invalid/en-panne.xml
            langue: fr
            registre: apprendre
          - id: rss-vivante
            type: rss
            url: https://exemple.invalid/vivante.xml
            langue: fr
            registre: apprendre
        """,
    )

    resultat = collecter(socle)

    assert appels["n"] == 2
    en_echec = [r.source_id for r in resultat.sources_en_echec]
    assert en_echec == ["rss-en-panne"]
    retenus = {r.source_id: r.nb_items for r in resultat.rapports}
    assert retenus["rss-vivante"] == 2
    assert len(resultat.items) == 2


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
