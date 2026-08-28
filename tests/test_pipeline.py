"""Tests de l'orchestrateur (AD-1, Story 1.8) — chemin complet, clients LLM
et de publication simulés, aucun appel réseau réel."""

import textwrap
from pathlib import Path
from types import SimpleNamespace

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
        pass


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


def test_executer_publie_un_html_contenant_les_entrees_du_socle(tmp_path):
    sources_yaml = _sources_yaml(tmp_path)
    client_llm = _ClientLLMSimule()
    client_publication = _ClientPublicationSimule()

    reussite = pipeline.executer(
        sources_path=sources_yaml,
        llm_client=client_llm,
        publish_client=client_publication,
    )

    assert reussite is True
    assert len(client_publication.put_calls) == 1
    _, corps = client_publication.put_calls[0]
    import base64

    html = base64.b64decode(corps["content"]).decode("utf-8")
    assert "Accroche simulée." in html
    assert "Apprendre" in html


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
