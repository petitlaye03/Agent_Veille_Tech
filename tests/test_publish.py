"""Tests de la publication (AD-8, Story 1.8 ; archive Markdown, Story 1.9) —
aucun appel réseau ni subprocess réel : client HTTP simulé, résolution de
jeton monkeypatchée."""

import base64
from datetime import date

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
    monkeypatch.setattr(publish, "_categories_echec_avec_trace_emise", set())


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


# --- publier_archive() (Story 1.9) -----------------------------------------


def test_publier_archive_cree_le_fichier_au_bon_chemin_date():
    client = _FakeClient(get_response=_FakeResponse(404), put_response=_FakeResponse(201))

    ok = publish.publier_archive("# Digest\n", date(2026, 8, 28), client=client)

    assert ok is True
    url, corps = client.put_calls[0]
    assert url.endswith("/contents/site/archive/2026-08-28.md")
    assert "sha" not in corps
    assert base64.b64decode(corps["content"]).decode("utf-8") == "# Digest\n"


def test_publier_archive_met_a_jour_l_archive_existante_du_meme_jour():
    """AC3 (AD-9) : relancer pour la même date écrase, jamais un second fichier."""
    client = _FakeClient(
        get_response=_FakeResponse(200, {"sha": "def456"}),
        put_response=_FakeResponse(200),
    )

    ok = publish.publier_archive("# Digest mis à jour\n", date(2026, 8, 28), client=client)

    assert ok is True
    _, corps = client.put_calls[0]
    assert corps["sha"] == "def456"


def test_publier_archive_sans_jeton_resolu_ne_leve_pas(monkeypatch):
    monkeypatch.setattr(publish, "_jeton", lambda: None)

    assert publish.publier_archive("# Digest\n", date(2026, 8, 28)) is False


def test_publier_archive_echec_reseau_ne_leve_pas():
    client = _FakeClient(get_leve=httpx.ConnectError("réseau indisponible"))

    assert publish.publier_archive("# Digest\n", date(2026, 8, 28), client=client) is False


def test_publier_archive_reponse_en_erreur_ne_leve_pas():
    client = _FakeClient(get_response=_FakeResponse(404), put_response=_FakeResponse(500))

    assert publish.publier_archive("# Digest\n", date(2026, 8, 28), client=client) is False


def test_echec_de_page_et_echec_d_archive_produisent_des_messages_distincts(caplog):
    """AC8 : sans ça, Abdoulaye ne saurait pas laquelle des deux publications
    a échoué une nuit donnée."""
    client_page = _FakeClient(get_response=_FakeResponse(500))
    client_archive = _FakeClient(get_response=_FakeResponse(500))

    with caplog.at_level("WARNING"):
        publish.publier("<html></html>", client=client_page)
        publish.publier_archive("# Digest\n", date(2026, 8, 28), client=client_archive)

    messages = [r.message for r in caplog.records]
    messages_page = [m for m in messages if "page" in m.lower()]
    messages_archive = [m for m in messages if "archive" in m.lower()]
    assert messages_page, "aucun message ne mentionne la page"
    assert messages_archive, "aucun message ne mentionne l'archive"
    assert messages_page != messages_archive


def test_echec_de_page_et_echec_d_archive_ont_chacun_leur_propre_trace_complete(caplog):
    """Trouvé en revue : le drapeau « trace complète au premier échec »
    était un booléen unique partagé entre page et archive — si les deux
    échouaient dans le même run, seule la première des deux obtenait sa
    trace complète (`exc_info=True`), l'autre n'ayant plus qu'un message
    sans contexte de diagnostic. Chacune des deux catégories doit obtenir
    sa propre trace complète au premier échec, indépendamment de l'ordre."""
    client_page = _FakeClient(get_response=_FakeResponse(500))
    client_archive = _FakeClient(get_response=_FakeResponse(500))

    with caplog.at_level("WARNING"):
        publish.publier("<html></html>", client=client_page)
        publish.publier_archive("# Digest\n", date(2026, 8, 28), client=client_archive)

    # `exc_info` sur l'enregistrement de log confirme qu'une trace complète
    # a été demandée pour cet appel (`logger.warning(msg, exc_info=True)`).
    records_avec_trace = [r for r in caplog.records if r.exc_info is not None]
    assert len(records_avec_trace) == 2
