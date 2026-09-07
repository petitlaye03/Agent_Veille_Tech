"""Backoff partagé sur `429` (Story 2.3, FR-2).

Aucun test ici n'attend réellement : `time.sleep` est toujours monkeypatché.
"""

import httpx
import pytest

from veille.connectors import _reseau


def _reponse(status_code: int, *, headers: dict | None = None, url: str = "https://exemple.invalid/x") -> httpx.Response:
    return httpx.Response(status_code, headers=headers or {}, request=httpx.Request("GET", url))


def test_succes_du_premier_coup_ne_retente_pas(monkeypatch):
    appels = []

    def _get(url, timeout, follow_redirects, headers=None):
        appels.append(url)
        return _reponse(200)

    dormis = []
    monkeypatch.setattr(_reseau.httpx, "get", _get)
    monkeypatch.setattr(_reseau.time, "sleep", lambda s: dormis.append(s))

    reponse = _reseau.get_avec_backoff("https://exemple.invalid/flux", timeout=30)

    assert reponse.status_code == 200
    assert len(appels) == 1
    assert dormis == []


def test_429_retente_puis_reussit(monkeypatch):
    reponses = [_reponse(429), _reponse(200)]

    def _get(url, timeout, follow_redirects, headers=None):
        return reponses.pop(0)

    dormis = []
    monkeypatch.setattr(_reseau.httpx, "get", _get)
    monkeypatch.setattr(_reseau.time, "sleep", lambda s: dormis.append(s))

    reponse = _reseau.get_avec_backoff("https://exemple.invalid/flux", timeout=30)

    assert reponse.status_code == 200
    assert len(dormis) == 1


def test_429_persistant_leve_apres_max_tentatives(monkeypatch):
    appels = {"n": 0}

    def _get(url, timeout, follow_redirects, headers=None):
        appels["n"] += 1
        return _reponse(429)

    dormis = []
    monkeypatch.setattr(_reseau.httpx, "get", _get)
    monkeypatch.setattr(_reseau.time, "sleep", lambda s: dormis.append(s))

    with pytest.raises(httpx.HTTPStatusError):
        _reseau.get_avec_backoff("https://exemple.invalid/flux", timeout=30)

    assert appels["n"] == _reseau.MAX_TENTATIVES
    # Une tentative de moins que d'appels : pas de sommeil après le dernier échec.
    assert len(dormis) == _reseau.MAX_TENTATIVES - 1


def test_retry_after_est_respecte(monkeypatch):
    reponses = [_reponse(429, headers={"Retry-After": "7"}), _reponse(200)]

    def _get(url, timeout, follow_redirects, headers=None):
        return reponses.pop(0)

    dormis = []
    monkeypatch.setattr(_reseau.httpx, "get", _get)
    monkeypatch.setattr(_reseau.time, "sleep", lambda s: dormis.append(s))

    _reseau.get_avec_backoff("https://exemple.invalid/flux", timeout=30)

    assert dormis == [7.0]


def test_retry_after_illisible_retombe_sur_le_backoff_exponentiel(monkeypatch):
    reponses = [_reponse(429, headers={"Retry-After": "pas-un-nombre"}), _reponse(200)]

    def _get(url, timeout, follow_redirects, headers=None):
        return reponses.pop(0)

    dormis = []
    monkeypatch.setattr(_reseau.httpx, "get", _get)
    monkeypatch.setattr(_reseau.time, "sleep", lambda s: dormis.append(s))

    _reseau.get_avec_backoff("https://exemple.invalid/flux", timeout=30)

    assert dormis == [_reseau.DELAI_DEFAUT_SECONDES]


def test_retry_after_est_plafonne(monkeypatch):
    """Trouvé en revue : un `Retry-After` légal mais énorme (ex. 86400s, un
    jour entier — un serveur peut légitimement l'envoyer) ne doit pas
    bloquer tout le run séquentiel pour cette seule source."""
    reponses = [_reponse(429, headers={"Retry-After": "86400"}), _reponse(200)]

    def _get(url, timeout, follow_redirects, headers=None):
        return reponses.pop(0)

    dormis = []
    monkeypatch.setattr(_reseau.httpx, "get", _get)
    monkeypatch.setattr(_reseau.time, "sleep", lambda s: dormis.append(s))

    _reseau.get_avec_backoff("https://exemple.invalid/flux", timeout=30)

    assert dormis == [_reseau.DELAI_MAX_SECONDES]


def test_retry_after_infini_retombe_sur_le_backoff_exponentiel(monkeypatch):
    """Trouvé en revue : `float("inf")`/`float("1e300")` sont des valeurs
    Python valides mais feraient planter `time.sleep` (`OverflowError`) si
    elles n'étaient pas explicitement rejetées comme illisibles."""
    reponses = [_reponse(429, headers={"Retry-After": "inf"}), _reponse(200)]

    def _get(url, timeout, follow_redirects, headers=None):
        return reponses.pop(0)

    dormis = []
    monkeypatch.setattr(_reseau.httpx, "get", _get)
    monkeypatch.setattr(_reseau.time, "sleep", lambda s: dormis.append(s))

    _reseau.get_avec_backoff("https://exemple.invalid/flux", timeout=30)

    assert dormis == [_reseau.DELAI_DEFAUT_SECONDES]


def test_backoff_exponentiel_sans_retry_after(monkeypatch):
    """3 tentatives : deux sommeils, le second double le premier."""
    def _get(url, timeout, follow_redirects, headers=None):
        return _reponse(429)

    dormis = []
    monkeypatch.setattr(_reseau.httpx, "get", _get)
    monkeypatch.setattr(_reseau.time, "sleep", lambda s: dormis.append(s))

    with pytest.raises(httpx.HTTPStatusError):
        _reseau.get_avec_backoff("https://exemple.invalid/flux", timeout=30)

    assert dormis == [
        _reseau.DELAI_DEFAUT_SECONDES,
        _reseau.DELAI_DEFAUT_SECONDES * 2,
    ]


def test_autre_erreur_http_leve_immediatement_sans_retry(monkeypatch):
    appels = {"n": 0}

    def _get(url, timeout, follow_redirects, headers=None):
        appels["n"] += 1
        return _reponse(403)

    dormis = []
    monkeypatch.setattr(_reseau.httpx, "get", _get)
    monkeypatch.setattr(_reseau.time, "sleep", lambda s: dormis.append(s))

    with pytest.raises(httpx.HTTPStatusError):
        _reseau.get_avec_backoff("https://exemple.invalid/flux", timeout=30)

    assert appels["n"] == 1
    assert dormis == []


def test_une_panne_reseau_pendant_le_backoff_n_est_pas_avalee(monkeypatch):
    """Trouvé en revue : un 429 suivi d'une vraie panne réseau (pas d'un
    second 429) doit laisser cette panne se propager telle quelle — le
    backoff ne doit avaler que des 429, jamais une autre exception."""
    appels = {"n": 0}

    def _get(url, timeout, follow_redirects, headers=None):
        appels["n"] += 1
        if appels["n"] == 1:
            return _reponse(429)
        raise httpx.ConnectTimeout("délai de connexion dépassé")

    monkeypatch.setattr(_reseau.httpx, "get", _get)
    monkeypatch.setattr(_reseau.time, "sleep", lambda s: None)

    with pytest.raises(httpx.ConnectTimeout):
        _reseau.get_avec_backoff("https://exemple.invalid/flux", timeout=30)

    assert appels["n"] == 2


def test_headers_et_follow_redirects_sont_transmis(monkeypatch):
    recus = {}

    def _get(url, timeout, follow_redirects, headers=None):
        recus["timeout"] = timeout
        recus["follow_redirects"] = follow_redirects
        recus["headers"] = headers
        return _reponse(200)

    monkeypatch.setattr(_reseau.httpx, "get", _get)
    monkeypatch.setattr(_reseau.time, "sleep", lambda s: None)

    _reseau.get_avec_backoff(
        "https://exemple.invalid/flux",
        timeout=12,
        headers={"User-Agent": "veille-ia/0.1"},
        follow_redirects=False,
    )

    assert recus == {
        "timeout": 12,
        "follow_redirects": False,
        "headers": {"User-Agent": "veille-ia/0.1"},
    }
