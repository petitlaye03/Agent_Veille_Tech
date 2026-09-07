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


def test_un_429_persistant_devient_une_panne_normale_sans_bloquer_les_autres(
    tmp_path, monkeypatch
):
    """Story 2.3 (AC3/AC4) : après épuisement du backoff, un 429 persistant
    redevient une panne isolée comme n'importe quelle autre (AD-6) — les
    autres sources du socle restent collectées."""
    import httpx

    import veille.connectors._reseau as reseau_module

    def _get_429(url, timeout, follow_redirects, headers=None):
        return httpx.Response(429, request=httpx.Request("GET", url))

    # Monkeypatché sur `_reseau` directement (pas via `rss_connector.httpx`,
    # qui ne fonctionne que parce que `httpx` est un module singleton
    # partagé — trouvé fragile en revue) : cible sans ambiguïté le point où
    # la requête a réellement lieu.
    monkeypatch.setattr(reseau_module.httpx, "get", _get_429)
    monkeypatch.setattr(reseau_module.time, "sleep", lambda s: None)

    socle = _ecrire_socle(
        tmp_path,
        f"""
        sources:
          - id: rss-rate-limitee
            type: rss
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

    en_echec = [r.source_id for r in resultat.sources_en_echec]
    assert en_echec == ["rss-rate-limitee"]
    echecs_par_source = {r.source_id: r.echec for r in resultat.rapports}
    assert "429" in echecs_par_source["rss-rate-limitee"]
    retenus = {r.source_id: r.nb_items for r in resultat.rapports}
    assert retenus["source-vivante"] == 2
    assert len(resultat.items) == 2


def test_un_429_qui_reussit_apres_backoff_produit_des_items_normalement(
    tmp_path, monkeypatch
):
    """Story 2.3 (AC1) : un 429 suivi d'un succès (dans la limite de
    MAX_TENTATIVES) ne doit laisser aucune trace d'échec — le backoff a
    fait son travail."""
    import httpx

    import veille.connectors._reseau as reseau_module

    reponses = [
        httpx.Response(429, request=httpx.Request("GET", "https://exemple.invalid/flux.xml")),
        httpx.Response(
            200,
            content=(FIXTURE_DIR / "sample_feed.xml").read_bytes(),
            request=httpx.Request("GET", "https://exemple.invalid/flux.xml"),
        ),
    ]

    def _get_puis_succes(url, timeout, follow_redirects, headers=None):
        return reponses.pop(0)

    dormis = []
    monkeypatch.setattr(reseau_module.httpx, "get", _get_puis_succes)
    monkeypatch.setattr(reseau_module.time, "sleep", lambda s: dormis.append(s))

    socle = _ecrire_socle(
        tmp_path,
        """
        sources:
          - id: rss-temporairement-limitee
            type: rss
            url: https://exemple.invalid/flux.xml
            langue: fr
            registre: apprendre
        """,
    )

    resultat = collecter(socle)

    assert not resultat.sources_en_echec
    assert resultat.rapports[0].nb_items == 2
    assert len(dormis) == 1


def test_le_backoff_429_fonctionne_aussi_pour_une_source_json(tmp_path, monkeypatch):
    """Story 2.3 (AC2) : le backoff est partagé par les trois connecteurs,
    pas seulement `rss` — vérifié ici pour `json` (jusque-là, seul le
    connecteur RSS était exercé de bout en bout avec un vrai 429, trouvé en
    revue)."""
    import httpx

    import veille.connectors._reseau as reseau_module

    reponses = [
        httpx.Response(429, request=httpx.Request("GET", "https://exemple.invalid/api.json")),
        httpx.Response(
            200,
            content=(FIXTURE_DIR / "hf_daily_papers.json").read_bytes(),
            request=httpx.Request("GET", "https://exemple.invalid/api.json"),
        ),
    ]

    def _get_puis_succes(url, timeout, follow_redirects, headers=None):
        return reponses.pop(0)

    dormis = []
    monkeypatch.setattr(reseau_module.httpx, "get", _get_puis_succes)
    monkeypatch.setattr(reseau_module.time, "sleep", lambda s: dormis.append(s))

    socle = _ecrire_socle(
        tmp_path,
        """
        sources:
          - id: json-temporairement-limitee
            type: json
            url: https://exemple.invalid/api.json
            langue: en
            registre: apprendre
            mapping:
              guid: paper.id
              titre: title
        """,
    )

    resultat = collecter(socle)

    assert not resultat.sources_en_echec
    assert resultat.rapports[0].nb_items == 2
    assert len(dormis) == 1


def test_le_backoff_429_fonctionne_aussi_pour_une_source_scrape(tmp_path, monkeypatch):
    """Story 2.3 (AC2) : idem pour `scrape` — la page elle-même (`_charger`),
    pas la requête `robots.txt` (`_collecte_autorisee`, non branchée sur le
    backoff par choix explicite).

    `httpx` étant un module singleton partagé, monkeypatcher `_reseau.httpx`
    intercepte aussi la requête `robots.txt` de `_collecte_autorisee` (qui
    n'appelle pas `get_avec_backoff`, mais `httpx.get` directement sur le
    même module) : la router par URL pour ne pas confondre les deux appels.
    """
    import httpx

    import veille.connectors._reseau as reseau_module

    page_html = (
        '<a href="/news/a"><h2>Article A</h2><time datetime="2026-07-24">24 juillet 2026</time></a>'
    ).encode("utf-8")

    reponses_page = [
        httpx.Response(429, request=httpx.Request("GET", "https://exemple.invalid/news")),
        httpx.Response(200, content=page_html, request=httpx.Request("GET", "https://exemple.invalid/news")),
    ]

    def _get_route_par_url(url, timeout, follow_redirects, headers=None):
        if url.endswith("/robots.txt"):
            # 404 : pas de robots.txt — collecte autorisée par défaut,
            # comportement inchangé de `_collecte_autorisee`.
            return httpx.Response(404, request=httpx.Request("GET", url))
        return reponses_page.pop(0)

    dormis = []
    monkeypatch.setattr(reseau_module.httpx, "get", _get_route_par_url)
    monkeypatch.setattr(reseau_module.time, "sleep", lambda s: dormis.append(s))

    socle = _ecrire_socle(
        tmp_path,
        """
        sources:
          - id: scrape-temporairement-limitee
            type: scrape
            url: https://exemple.invalid/news
            langue: fr
            registre: apprendre
            selecteur: /news/
            base_url: https://exemple.invalid
        """,
    )

    resultat = collecter(socle)

    assert not resultat.sources_en_echec
    assert resultat.rapports[0].nb_items == 1
    assert len(dormis) == 1
