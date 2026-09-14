"""Tests de l'orchestrateur (AD-1, Story 1.8) — chemin complet, clients LLM
et de publication simulés, aucun appel réseau réel."""

import textwrap
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from veille import pipeline

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _sources_yaml(tmp_path):
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


class _MessagesSimulees:
    """Simule `client.messages` d'Anthropic : ne touche jamais le réseau."""

    def create(self, **kwargs):
        return SimpleNamespace(
            content=[SimpleNamespace(text="Accroche simulée.")],
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
            stop_reason="end_turn",
        )


class _ClientLLMSimule:
    def __init__(self):
        self.messages = _MessagesSimulees()


class _FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("erreur HTTP", request=None, response=self)


class _ClientPublicationSimule:
    """Simule le client HTTP de `publish.py` : capture ce qui aurait été
    envoyé, sans jamais toucher le réseau."""

    def __init__(self):
        self.put_calls = []
        self.closed = False

    def get(self, url):
        return _FakeResponse(404)

    def put(self, url, json=None):
        self.put_calls.append((url, json))
        return _FakeResponse(201)

    def close(self):
        self.closed = True


def test_executer_publie_la_page_et_l_archive_datee(tmp_path):
    """Story 1.9 : deux publications par run — la page (index.html) et
    l'archive du jour (site/archive/YYYY-MM-DD.md), à partir du même
    horodatage de génération."""
    sources_yaml = _sources_yaml(tmp_path)
    client_llm = _ClientLLMSimule()
    client_publication = _ClientPublicationSimule()

    reussite = pipeline.executer(
        sources_path=sources_yaml,
        llm_client=client_llm,
        publish_client=client_publication,
    )

    assert reussite is True
    assert len(client_publication.put_calls) == 2

    import base64
    import re

    corps_par_chemin = {url: corps for url, corps in client_publication.put_calls}
    chemin_page = next((c for c in corps_par_chemin if c.endswith("/contents/index.html")), None)
    chemin_archive = next(
        (c for c in corps_par_chemin if re.search(r"/contents/site/archive/\d{4}-\d{2}-\d{2}\.md$", c)),
        None,
    )
    assert chemin_page is not None
    assert chemin_archive is not None

    # Corrélation contenu ↔ chemin (trouvé en revue) : une régression qui
    # inverserait les deux corps (HTML publié comme archive, Markdown publié
    # comme page) passerait inaperçue si on se contentait de chercher les
    # mêmes sous-chaînes dans les deux corps indistinctement.
    html_publie = base64.b64decode(corps_par_chemin[chemin_page]["content"]).decode("utf-8")
    markdown_publie = base64.b64decode(corps_par_chemin[chemin_archive]["content"]).decode("utf-8")

    assert html_publie.lstrip().startswith("<!doctype html>")
    assert "<style>" in html_publie
    assert not markdown_publie.lstrip().startswith("<!doctype html>")
    assert markdown_publie.lstrip().startswith("# Veille tech")

    for contenu in (html_publie, markdown_publie):
        # Pas de point final dans l'assertion : l'archive Markdown échappe
        # la ponctuation (CommonMark, `_echapper_markdown`), sans effet une
        # fois rendue — ce n'est pas ce que ce test vérifie.
        assert "Accroche simulée" in contenu
        assert "Apprendre" in contenu


def test_executer_ne_publie_pas_avec_un_client_ferme_par_erreur(tmp_path):
    """Un client de publication fourni explicitement n'est jamais fermé par
    `publier()` — vérifié de bout en bout via l'orchestrateur, pas
    seulement au niveau unitaire de `publish.py`."""
    sources_yaml = _sources_yaml(tmp_path)
    client_publication = _ClientPublicationSimule()

    pipeline.executer(
        sources_path=sources_yaml,
        llm_client=_ClientLLMSimule(),
        publish_client=client_publication,
    )

    assert client_publication.closed is False


def test_executer_publie_quand_meme_la_page_si_rendre_markdown_leve(tmp_path, monkeypatch):
    """Trouvé en revue : la docstring affirme que la page et l'archive sont
    « toujours tentées, même si l'une échoue » — mais ça ne tenait que pour
    des échecs côté publication. Si `rendre_markdown()` lève *après* que
    `rendre()` a réussi, la page déjà rendue avec succès ne doit pas être
    perdue faute d'avoir été publiée avant l'échec de l'archive."""
    sources_yaml = _sources_yaml(tmp_path)
    client_publication = _ClientPublicationSimule()

    def _rendre_markdown_qui_leve(*args, **kwargs):
        raise RuntimeError("template markdown cassé")

    monkeypatch.setattr(pipeline, "rendre_markdown", _rendre_markdown_qui_leve)

    reussite = pipeline.executer(
        sources_path=sources_yaml,
        llm_client=_ClientLLMSimule(),
        publish_client=client_publication,
    )

    assert reussite is False  # l'archive n'a jamais pu être publiée
    # Mais la page, elle, a bien été tentée et publiée avant l'échec.
    assert len(client_publication.put_calls) == 1
    assert client_publication.put_calls[0][0].endswith("/contents/index.html")


def test_executer_ne_leve_pas_si_rendre_leve(tmp_path, monkeypatch):
    """Trouvé en revue : `rendre()` n'a pas de garantie de non-levée qui lui
    soit propre (pas d'appel réseau à isoler, mais un template
    manquant/corrompu lèverait) — l'orchestrateur doit rester le filet de
    sécurité de dernier recours, cohérent avec sa propre docstring."""
    sources_yaml = _sources_yaml(tmp_path)

    def _rendre_qui_leve(*args, **kwargs):
        raise RuntimeError("template cassé")

    monkeypatch.setattr(pipeline, "rendre", _rendre_qui_leve)

    reussite = pipeline.executer(
        sources_path=sources_yaml,
        llm_client=_ClientLLMSimule(),
        publish_client=_ClientPublicationSimule(),
    )

    assert reussite is False


class _ClientPublicationPartielle:
    """La page se publie, l'archive échoue — vérifie que les deux
    publications sont tentées indépendamment (AC7/8, Story 1.9)."""

    def __init__(self):
        self.put_calls = []
        self.closed = False

    def get(self, url):
        return _FakeResponse(404)

    def put(self, url, json=None):
        self.put_calls.append((url, json))
        if "archive" in url:
            return _FakeResponse(500)
        return _FakeResponse(201)

    def close(self):
        self.closed = True


def test_executer_tente_les_deux_publications_meme_si_l_une_echoue(tmp_path):
    sources_yaml = _sources_yaml(tmp_path)
    client_publication = _ClientPublicationPartielle()

    reussite = pipeline.executer(
        sources_path=sources_yaml,
        llm_client=_ClientLLMSimule(),
        publish_client=client_publication,
    )

    assert reussite is False  # l'archive a échoué
    assert len(client_publication.put_calls) == 2  # les deux ont bien été tentées


def test_un_echec_de_collecte_n_atteint_jamais_la_publication(tmp_path, monkeypatch):
    """Story 3.2 (AC2) : un échec avant `rendre()` ne doit jamais atteindre
    `publier()` — la page déjà publiée les nuits précédentes reste donc
    intacte par construction. Vérifié ici pour `collecter()`, la toute
    première étape."""
    sources_yaml = _sources_yaml(tmp_path)
    client_publication = _ClientPublicationSimule()

    def _collecter_qui_leve(*args, **kwargs):
        raise RuntimeError("collecte cassée")

    monkeypatch.setattr(pipeline.collect, "collecter", _collecter_qui_leve)

    reussite = pipeline.executer(
        sources_path=sources_yaml,
        llm_client=_ClientLLMSimule(),
        publish_client=client_publication,
    )

    assert reussite is False
    assert client_publication.put_calls == []


def test_un_echec_d_enrichissement_n_atteint_jamais_la_publication(tmp_path, monkeypatch):
    """Story 3.2 (AC2) : idem pour `enrichir()` — un échec après une
    collecte réussie mais avant tout rendu ne doit toujours rien publier."""
    sources_yaml = _sources_yaml(tmp_path)
    client_publication = _ClientPublicationSimule()

    def _enrichir_qui_leve(*args, **kwargs):
        raise RuntimeError("enrichissement cassé")

    monkeypatch.setattr(pipeline, "enrichir", _enrichir_qui_leve)

    reussite = pipeline.executer(
        sources_path=sources_yaml,
        llm_client=_ClientLLMSimule(),
        publish_client=client_publication,
    )

    assert reussite is False
    assert client_publication.put_calls == []


def test_un_echec_de_rendu_html_n_atteint_jamais_la_publication(tmp_path, monkeypatch):
    """Story 3.2 (AC2) : idem pour `rendre()` — complète
    `test_executer_ne_leve_pas_si_rendre_leve` (Story 1.9) avec l'assertion
    qui manquait : aucune publication n'est tentée, pas seulement « le run
    ne plante pas »."""
    sources_yaml = _sources_yaml(tmp_path)
    client_publication = _ClientPublicationSimule()

    def _rendre_qui_leve(*args, **kwargs):
        raise RuntimeError("template cassé")

    monkeypatch.setattr(pipeline, "rendre", _rendre_qui_leve)

    reussite = pipeline.executer(
        sources_path=sources_yaml,
        llm_client=_ClientLLMSimule(),
        publish_client=client_publication,
    )

    assert reussite is False
    assert client_publication.put_calls == []


def test_main_bandeau_echec_appelle_render_puis_publish(monkeypatch):
    """Story 3.2 : le point d'entrée dédié construit le fragment du jour
    (`render.rendre_bandeau_echec`) puis le publie
    (`publish.publier_bandeau_echec`) — ne passe jamais par `executer()`."""
    appels = {}

    def _rendre_bandeau_echec_espion(date_echec):
        appels["date"] = date_echec
        return "<!-- BANDEAU-ECHEC:DEBUT -->x<!-- BANDEAU-ECHEC:FIN -->"

    def _publier_bandeau_echec_espion(bandeau):
        appels["bandeau"] = bandeau
        return True

    monkeypatch.setattr(pipeline, "rendre_bandeau_echec", _rendre_bandeau_echec_espion)
    monkeypatch.setattr(pipeline, "publier_bandeau_echec", _publier_bandeau_echec_espion)

    with pytest.raises(SystemExit) as exc_info:
        pipeline.main_bandeau_echec()

    assert exc_info.value.code == 0
    assert "date" in appels
    assert appels["bandeau"] == "<!-- BANDEAU-ECHEC:DEBUT -->x<!-- BANDEAU-ECHEC:FIN -->"


def test_main_bandeau_echec_sort_avec_un_code_non_nul_si_la_publication_echoue(monkeypatch):
    monkeypatch.setattr(pipeline, "rendre_bandeau_echec", lambda d: "x")
    monkeypatch.setattr(pipeline, "publier_bandeau_echec", lambda b: False)

    with pytest.raises(SystemExit) as exc_info:
        pipeline.main_bandeau_echec()

    assert exc_info.value.code == 1


def test_main_bandeau_echec_sort_avec_le_code_zero_si_rien_a_annoncer(monkeypatch):
    """Trouvé en revue : `publier_bandeau_echec` renvoie `None` (pas
    `False`) quand il n'y a aucune page déjà publiée à annoter — ce n'est
    pas une panne, `main_bandeau_echec` ne doit pas en faire un run rouge
    dans Actions."""
    monkeypatch.setattr(pipeline, "rendre_bandeau_echec", lambda d: "x")
    monkeypatch.setattr(pipeline, "publier_bandeau_echec", lambda b: None)

    with pytest.raises(SystemExit) as exc_info:
        pipeline.main_bandeau_echec()

    assert exc_info.value.code == 0


def test_main_bandeau_echec_ne_leve_jamais(monkeypatch):
    """Même filet de sécurité que `executer()` (Story 1.9) : une exception
    inattendue dégrade en code de sortie non nul, jamais une levée."""

    def _rendre_qui_leve(date_echec):
        raise RuntimeError("erreur inattendue")

    monkeypatch.setattr(pipeline, "rendre_bandeau_echec", _rendre_qui_leve)

    with pytest.raises(SystemExit) as exc_info:
        pipeline.main_bandeau_echec()

    assert exc_info.value.code == 1


def test_executer_degrade_proprement_sans_client_llm_ni_jeton_de_publication(
    tmp_path, monkeypatch
):
    """Aucune clé API Anthropic, aucun jeton GitHub résolu : le pipeline ne
    lève jamais, l'accroche retombe sur le titre, la publication échoue
    proprement (`False`) — même limite que Stories 1.6/1.7 sans clé."""
    sources_yaml = _sources_yaml(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    from veille import publish

    monkeypatch.setattr(publish, "_jeton_depuis_env", lambda: None)
    monkeypatch.setattr(publish, "_jeton_depuis_gh_cli", lambda: None)

    reussite = pipeline.executer(sources_path=sources_yaml)

    assert reussite is False
