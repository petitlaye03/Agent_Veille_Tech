"""Tests de la publication (AD-8, Story 1.8) — aucun appel réseau ni
subprocess réel : client HTTP simulé, résolution de jeton monkeypatchée."""

import base64

import httpx
import pytest

from veille import publish


class _FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("erreur HTTP", request=None, response=self)


class _FakeClient:
    def __init__(self, get_response=None, put_response=None, get_leve=None):
        self._get_response = get_response
        self._put_response = put_response
        self._get_leve = get_leve
        self.put_calls = []
        self.closed = False

    def get(self, url):
        if self._get_leve is not None:
            raise self._get_leve
        return self._get_response

    def put(self, url, json=None):
        self.put_calls.append((url, json))
        return self._put_response

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def reset_avertissements(monkeypatch):
    """Les avertissements one-shot du module ne doivent pas fuiter d'un test à l'autre."""
    monkeypatch.setattr(publish, "_avertissement_jeton_absent_emis", False)
    monkeypatch.setattr(publish, "_avertissement_echec_publication_emis", False)


# --- Résolution du jeton --------------------------------------------------


def test_jeton_priorite_a_l_env_sur_gh_cli(monkeypatch):
    monkeypatch.setattr(publish, "_jeton_depuis_env", lambda: "jeton-env")
    monkeypatch.setattr(publish, "_jeton_depuis_gh_cli", lambda: "jeton-gh-cli")

    assert publish._jeton() == "jeton-env"


def test_jeton_replie_sur_gh_cli_si_env_absent(monkeypatch):
    monkeypatch.setattr(publish, "_jeton_depuis_env", lambda: None)
    monkeypatch.setattr(publish, "_jeton_depuis_gh_cli", lambda: "jeton-gh-cli")

    assert publish._jeton() == "jeton-gh-cli"


def test_jeton_none_si_aucune_voie_ne_resout(monkeypatch):
    monkeypatch.setattr(publish, "_jeton_depuis_env", lambda: None)
    monkeypatch.setattr(publish, "_jeton_depuis_gh_cli", lambda: None)

    assert publish._jeton() is None


def test_jeton_env_blanc_traite_comme_absent(monkeypatch):
    """Même piège que la clé API composée uniquement d'espaces, trouvé en
    revue de la Story 1.6 : `.strip()` avant le test de présence."""
    monkeypatch.setenv("GITHUB_TOKEN", "   ")

    assert publish._jeton_depuis_env() is None


def test_jeton_env_present_et_non_blanc(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "  un-jeton  ")

    assert publish._jeton_depuis_env() == "un-jeton"


# --- publier() -------------------------------------------------------------


def test_publier_cree_le_fichier_quand_il_n_existe_pas():
    client = _FakeClient(
        get_response=_FakeResponse(404),
        put_response=_FakeResponse(201),
    )

    assert publish.publier("<html>ok</html>", client=client) is True
    _, corps = client.put_calls[0]
    assert "sha" not in corps
    assert base64.b64decode(corps["content"]).decode("utf-8") == "<html>ok</html>"


def test_publier_met_a_jour_le_fichier_existant():
    client = _FakeClient(
        get_response=_FakeResponse(200, {"sha": "abc123"}),
        put_response=_FakeResponse(200),
    )

    assert publish.publier("<html>nouveau</html>", client=client) is True
    _, corps = client.put_calls[0]
    assert corps["sha"] == "abc123"


def test_publier_sans_jeton_resolu_ne_leve_pas(monkeypatch):
    monkeypatch.setattr(publish, "_jeton", lambda: None)

    assert publish.publier("<html></html>") is False


def test_publier_echec_reseau_ne_leve_pas():
    client = _FakeClient(get_leve=httpx.ConnectError("réseau indisponible"))

    assert publish.publier("<html></html>", client=client) is False


def test_publier_reponse_en_erreur_ne_leve_pas():
    client = _FakeClient(
        get_response=_FakeResponse(404),
        put_response=_FakeResponse(500),
    )

    assert publish.publier("<html></html>", client=client) is False


def test_publier_get_en_erreur_non_404_n_essaie_pas_de_creer_par_dessus(monkeypatch):
    """Trouvé en revue : un GET en échec pour une autre raison que « fichier
    absent » (401/403/5xx) ne doit pas être traité comme un 404 — sinon le
    PUT suivant tenterait une création sans `sha` sur un fichier qui existe
    peut-être réellement, masquant la vraie cause (jeton invalide, quota
    épuisé) derrière un rejet générique de l'API."""
    client = _FakeClient(get_response=_FakeResponse(500), put_response=_FakeResponse(201))

    assert publish.publier("<html></html>", client=client) is False
    # Le PUT ne doit jamais avoir été tenté : la cause exacte reste visible
    # dans les logs plutôt que d'être masquée par un second échec.
    assert client.put_calls == []


def test_publier_ne_ferme_pas_un_client_fourni_explicitement():
    client = _FakeClient(get_response=_FakeResponse(404), put_response=_FakeResponse(201))

    publish.publier("<html></html>", client=client)

    assert client.closed is False
