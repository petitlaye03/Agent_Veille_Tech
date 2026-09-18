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


# --- Bandeau d'échec (Story 3.2) ------------------------------------------


def _page_publiee(html: str, sha: str = "sha-existant") -> _FakeResponse:
    return _FakeResponse(
        200,
        payload={"content": base64.b64encode(html.encode("utf-8")).decode("ascii"), "sha": sha},
    )


def test_bandeau_echec_insere_apres_body_quand_absent():
    html_existant = "<html><body>\n<h1>Digest du 14 septembre</h1>\n</body></html>"
    client = _FakeClient(get_response=_page_publiee(html_existant), put_response=_FakeResponse(200))

    reussite = publish.publier_bandeau_echec("<!-- BANDEAU-ECHEC:DEBUT -->x<!-- BANDEAU-ECHEC:FIN -->", client=client)

    assert reussite is True
    corps_publie = base64.b64decode(client.put_calls[0][1]["content"]).decode("utf-8")
    assert "<!-- BANDEAU-ECHEC:DEBUT -->x<!-- BANDEAU-ECHEC:FIN -->" in corps_publie
    assert "Digest du 14 septembre" in corps_publie  # contenu existant préservé
    assert client.put_calls[0][1]["sha"] == "sha-existant"


def test_bandeau_echec_remplace_plutot_que_d_empiler():
    """AC4 : deux nuits d'échec consécutives ne doivent jamais empiler deux
    bandeaux."""
    ancien_bandeau = "<!-- BANDEAU-ECHEC:DEBUT -->ancien (nuit d'avant)<!-- BANDEAU-ECHEC:FIN -->"
    html_existant = f"<html><body>\n{ancien_bandeau}\n<h1>Digest</h1>\n</body></html>"
    client = _FakeClient(get_response=_page_publiee(html_existant), put_response=_FakeResponse(200))

    nouveau_bandeau = "<!-- BANDEAU-ECHEC:DEBUT -->nouveau (cette nuit)<!-- BANDEAU-ECHEC:FIN -->"
    publish.publier_bandeau_echec(nouveau_bandeau, client=client)

    corps_publie = base64.b64decode(client.put_calls[0][1]["content"]).decode("utf-8")
    assert corps_publie.count("BANDEAU-ECHEC:DEBUT") == 1
    assert "ancien (nuit d'avant)" not in corps_publie
    assert "nouveau (cette nuit)" in corps_publie
    assert "<h1>Digest</h1>" in corps_publie  # contenu existant toujours préservé


def test_bandeau_echec_sans_page_deja_publiee_ne_fait_rien():
    """Première nuit jamais publiée avec succès : rien à annoter, pas une
    panne — `None`, distinct de `False` (correctif de revue : une vraie
    panne et « rien à faire » ne doivent pas partager le même signal)."""
    client = _FakeClient(get_response=_FakeResponse(404))

    resultat = publish.publier_bandeau_echec("<!-- BANDEAU-ECHEC:DEBUT --><!-- BANDEAU-ECHEC:FIN -->", client=client)

    assert resultat is None
    assert client.put_calls == []


def test_bandeau_echec_insere_apres_une_balise_body_avec_attributs():
    """Trouvé en revue : `<body class="...">`/`<body lang="fr">` etc. —
    pas seulement la balise nue `<body>` que le premier jet ne matchait
    que via `str.replace` littéral."""
    html_existant = '<html><body class="sombre" data-theme="auto">\n<h1>Digest</h1>\n</body></html>'
    client = _FakeClient(get_response=_page_publiee(html_existant), put_response=_FakeResponse(200))

    publish.publier_bandeau_echec("<!-- BANDEAU-ECHEC:DEBUT -->x<!-- BANDEAU-ECHEC:FIN -->", client=client)

    corps_publie = base64.b64decode(client.put_calls[0][1]["content"]).decode("utf-8")
    assert '<body class="sombre" data-theme="auto">\n<!-- BANDEAU-ECHEC:DEBUT -->x<!-- BANDEAU-ECHEC:FIN -->' in corps_publie
    assert "<h1>Digest</h1>" in corps_publie


def test_bandeau_echec_sans_balise_body_du_tout_ne_perd_pas_le_contenu():
    """Trouvé en revue : chemin de repli jusque-là non testé. Une page
    corrompue de façon inattendue (pas de `<body>`) ne doit toujours pas
    perdre son contenu — le bandeau est ajouté en tête plutôt que rien."""
    html_existant = "<p>Contenu sans structure de page complète</p>"
    client = _FakeClient(get_response=_page_publiee(html_existant), put_response=_FakeResponse(200))

    publish.publier_bandeau_echec("<!-- BANDEAU-ECHEC:DEBUT -->x<!-- BANDEAU-ECHEC:FIN -->", client=client)

    corps_publie = base64.b64decode(client.put_calls[0][1]["content"]).decode("utf-8")
    assert corps_publie.startswith("<!-- BANDEAU-ECHEC:DEBUT -->x<!-- BANDEAU-ECHEC:FIN -->")
    assert "Contenu sans structure de page complète" in corps_publie


def test_bandeau_echec_avec_un_antislash_ne_leve_pas_et_ne_corrompt_pas(monkeypatch):
    """Trouvé en revue : `re.sub` interprète `\\1`/`\\g<0>` dans une chaîne
    de remplacement littérale — un bandeau qui en contiendrait aurait pu
    lever `re.error` ou corrompre le HTML publié. Reproduit sur le
    remplacement (bandeau déjà présent), le chemin où `re.sub` reçoit un
    texte de remplacement plutôt qu'une simple insertion."""
    ancien_bandeau = "<!-- BANDEAU-ECHEC:DEBUT -->ancien<!-- BANDEAU-ECHEC:FIN -->"
    html_existant = f"<html><body>\n{ancien_bandeau}\n</body></html>"
    client = _FakeClient(get_response=_page_publiee(html_existant), put_response=_FakeResponse(200))

    bandeau_avec_antislash = r"<!-- BANDEAU-ECHEC:DEBUT -->C:\1\dossier<!-- BANDEAU-ECHEC:FIN -->"
    reussite = publish.publier_bandeau_echec(bandeau_avec_antislash, client=client)

    assert reussite is True
    corps_publie = base64.b64decode(client.put_calls[0][1]["content"]).decode("utf-8")
    assert r"C:\1\dossier" in corps_publie


def test_bandeau_echec_sha_absent_n_est_jamais_envoye_comme_null():
    """Trouvé en revue : `_publier()` n'inclut `sha` que s'il est présent
    (`if sha: ...`) — `publier_bandeau_echec` doit suivre la même garde,
    pas envoyer `"sha": null` sans discernement."""
    payload_sans_sha = {"content": base64.b64encode(b"<html><body></body></html>").decode("ascii")}
    client = _FakeClient(get_response=_FakeResponse(200, payload=payload_sans_sha), put_response=_FakeResponse(200))

    publish.publier_bandeau_echec("<!-- BANDEAU-ECHEC:DEBUT --><!-- BANDEAU-ECHEC:FIN -->", client=client)

    assert "sha" not in client.put_calls[0][1]


def test_bandeau_echec_contenu_illisible_est_une_vraie_panne():
    """Trouvé en revue : un `content` absent/vidé par l'API (ex. fichier
    trop volumineux) doit être une vraie panne (`False`), pas confondu avec
    l'absence de page (`None`)."""
    payload_sans_content = {"sha": "sha-existant"}
    client = _FakeClient(get_response=_FakeResponse(200, payload=payload_sans_content))

    resultat = publish.publier_bandeau_echec("<!-- BANDEAU-ECHEC:DEBUT --><!-- BANDEAU-ECHEC:FIN -->", client=client)

    assert resultat is False


def test_bandeau_echec_bout_en_bout_avec_le_vrai_fragment_rendu():
    """Trouvé en revue : aucun test ne combinait le vrai
    `render.rendre_bandeau_echec` avec `publish.publier_bandeau_echec` —
    une dérive du format des marqueurs entre les deux modules serait passée
    inaperçue (chacun testé isolément avec des marqueurs écrits à la main)."""
    from veille.render import rendre_bandeau_echec

    html_existant = "<html><body>\n<h1>Digest</h1>\n</body></html>"
    client = _FakeClient(get_response=_page_publiee(html_existant), put_response=_FakeResponse(200))

    fragment_reel = rendre_bandeau_echec(date(2026, 9, 14))
    reussite = publish.publier_bandeau_echec(fragment_reel, client=client)

    assert reussite is True
    corps_publie = base64.b64decode(client.put_calls[0][1]["content"]).decode("utf-8")
    assert "14/09/2026" in corps_publie
    assert "<h1>Digest</h1>" in corps_publie


def test_bandeau_echec_degrade_proprement_sans_jeton(monkeypatch):
    monkeypatch.setattr(publish, "_jeton_depuis_env", lambda: None)
    monkeypatch.setattr(publish, "_jeton_depuis_gh_cli", lambda: None)

    reussite = publish.publier_bandeau_echec("<!-- BANDEAU-ECHEC:DEBUT --><!-- BANDEAU-ECHEC:FIN -->")

    assert reussite is False


def test_bandeau_echec_degrade_proprement_sur_panne_reseau():
    client = _FakeClient(get_leve=httpx.ConnectError("panne réseau"))

    reussite = publish.publier_bandeau_echec("<!-- BANDEAU-ECHEC:DEBUT --><!-- BANDEAU-ECHEC:FIN -->", client=client)

    assert reussite is False


# --- Récapitulatif des sources à surveiller (Story 4.3) --------------------


def _source_a_surveiller(source_id="src", etat="suspecte", raison="45 jour(s) sans nouvel item"):
    from veille.health import SourceASurveiller

    return SourceASurveiller(source_id=source_id, etat=etat, raison=raison)


def test_recapitulatif_insere_apres_body_quand_absent():
    html_existant = "<html><body>\n<h1>Digest du 14 septembre</h1>\n</body></html>"
    client = _FakeClient(get_response=_page_publiee(html_existant), put_response=_FakeResponse(200))

    reussite = publish.publier_recapitulatif_sante([_source_a_surveiller()], client=client)

    assert reussite is True
    corps_publie = base64.b64decode(client.put_calls[0][1]["content"]).decode("utf-8")
    assert "RECAPITULATIF-SANTE:DEBUT" in corps_publie
    assert "src" in corps_publie
    assert "Digest du 14 septembre" in corps_publie  # contenu existant préservé
    assert client.put_calls[0][1]["sha"] == "sha-existant"


def test_recapitulatif_remplace_plutot_que_d_empiler():
    ancien = "<!-- RECAPITULATIF-SANTE:DEBUT -->ancien (semaine d'avant)<!-- RECAPITULATIF-SANTE:FIN -->"
    html_existant = f"<html><body>\n{ancien}\n<h1>Digest</h1>\n</body></html>"
    client = _FakeClient(get_response=_page_publiee(html_existant), put_response=_FakeResponse(200))

    publish.publier_recapitulatif_sante([_source_a_surveiller(source_id="nouvelle-source")], client=client)

    corps_publie = base64.b64decode(client.put_calls[0][1]["content"]).decode("utf-8")
    assert corps_publie.count("RECAPITULATIF-SANTE:DEBUT") == 1
    assert "ancien (semaine d'avant)" not in corps_publie
    assert "nouvelle-source" in corps_publie
    assert "<h1>Digest</h1>" in corps_publie


def test_recapitulatif_sources_vide_retire_le_panneau_existant():
    """AC4 : plus aucune source à surveiller — le panneau existant doit
    être retiré, pas laissé périmé."""
    ancien = "<!-- RECAPITULATIF-SANTE:DEBUT -->ancien-souci<!-- RECAPITULATIF-SANTE:FIN -->"
    html_existant = f"<html><body>\n{ancien}\n<h1>Digest</h1>\n</body></html>"
    client = _FakeClient(get_response=_page_publiee(html_existant), put_response=_FakeResponse(200))

    resultat = publish.publier_recapitulatif_sante([], client=client)

    assert resultat is True
    corps_publie = base64.b64decode(client.put_calls[0][1]["content"]).decode("utf-8")
    assert "RECAPITULATIF-SANTE" not in corps_publie
    assert "ancien-souci" not in corps_publie
    assert "<h1>Digest</h1>" in corps_publie


def test_recapitulatif_sources_vide_sans_panneau_existant_ne_fait_rien():
    html_existant = "<html><body>\n<h1>Digest</h1>\n</body></html>"
    client = _FakeClient(get_response=_page_publiee(html_existant), put_response=_FakeResponse(200))

    resultat = publish.publier_recapitulatif_sante([], client=client)

    assert resultat is None
    assert client.put_calls == []


def test_recapitulatif_sans_page_deja_publiee_ne_fait_rien():
    client = _FakeClient(get_response=_FakeResponse(404))

    resultat = publish.publier_recapitulatif_sante([_source_a_surveiller()], client=client)

    assert resultat is None
    assert client.put_calls == []


def test_recapitulatif_contenu_illisible_est_une_vraie_panne():
    payload_sans_content = {"sha": "sha-existant"}
    client = _FakeClient(get_response=_FakeResponse(200, payload=payload_sans_content))

    resultat = publish.publier_recapitulatif_sante([_source_a_surveiller()], client=client)

    assert resultat is False


def test_recapitulatif_degrade_proprement_sans_jeton(monkeypatch):
    monkeypatch.setattr(publish, "_jeton_depuis_env", lambda: None)
    monkeypatch.setattr(publish, "_jeton_depuis_gh_cli", lambda: None)

    resultat = publish.publier_recapitulatif_sante([_source_a_surveiller()])

    assert resultat is False


def test_recapitulatif_degrade_proprement_sur_panne_reseau():
    client = _FakeClient(get_leve=httpx.ConnectError("panne réseau"))

    resultat = publish.publier_recapitulatif_sante([_source_a_surveiller()], client=client)

    assert resultat is False


def test_recapitulatif_bout_en_bout_avec_le_vrai_fragment_rendu():
    """Même précaution qu'en Story 3.2 pour le bandeau d'échec : combiner
    le vrai `render.rendre_recapitulatif_sante` avec `publish.publier_
    recapitulatif_sante` — une dérive du format des marqueurs entre les
    deux modules serait passée inaperçue si chacun n'était testé
    qu'isolément avec des marqueurs écrits à la main."""
    html_existant = "<html><body>\n<h1>Digest</h1>\n</body></html>"
    client = _FakeClient(get_response=_page_publiee(html_existant), put_response=_FakeResponse(200))

    reussite = publish.publier_recapitulatif_sante([_source_a_surveiller(source_id="flux-x")], client=client)

    assert reussite is True
    corps_publie = base64.b64decode(client.put_calls[0][1]["content"]).decode("utf-8")
    assert "flux-x" in corps_publie
    assert "<h1>Digest</h1>" in corps_publie


# --- Panneau « À découvrir » (Story 4.4) -----------------------------------


def _candidat(id_="candidat-x", url="https://exemple.test/feed", justification="Une bonne raison."):
    from veille.config import SourceConfig
    from veille.discover import CandidatSource

    source = SourceConfig(id=id_, type="rss", url=url, langue="en", registre="apprendre")
    return CandidatSource(source=source, justification=justification)


def test_a_decouvrir_insere_apres_body_quand_absent():
    html_existant = "<html><body>\n<h1>Digest du 14 septembre</h1>\n</body></html>"
    client = _FakeClient(get_response=_page_publiee(html_existant), put_response=_FakeResponse(200))

    reussite = publish.publier_a_decouvrir(_candidat(), client=client)

    assert reussite is True
    corps_publie = base64.b64decode(client.put_calls[0][1]["content"]).decode("utf-8")
    assert "A-DECOUVRIR:DEBUT" in corps_publie
    assert "candidat-x" in corps_publie
    assert "Digest du 14 septembre" in corps_publie  # contenu existant préservé
    assert client.put_calls[0][1]["sha"] == "sha-existant"


def test_a_decouvrir_remplace_plutot_que_d_empiler():
    ancien = "<!-- A-DECOUVRIR:DEBUT -->ancien (semaine d'avant)<!-- A-DECOUVRIR:FIN -->"
    html_existant = f"<html><body>\n{ancien}\n<h1>Digest</h1>\n</body></html>"
    client = _FakeClient(get_response=_page_publiee(html_existant), put_response=_FakeResponse(200))

    publish.publier_a_decouvrir(_candidat(id_="nouveau-candidat"), client=client)

    corps_publie = base64.b64decode(client.put_calls[0][1]["content"]).decode("utf-8")
    assert corps_publie.count("A-DECOUVRIR:DEBUT") == 1
    assert "ancien (semaine d'avant)" not in corps_publie
    assert "nouveau-candidat" in corps_publie
    assert "<h1>Digest</h1>" in corps_publie


def test_a_decouvrir_candidat_none_retire_le_panneau_existant():
    """AC4 : aucun candidat vivant cette semaine — le panneau existant doit
    être retiré, pas laissé à proposer une source peut-être déjà morte."""
    ancien = "<!-- A-DECOUVRIR:DEBUT -->ancien-candidat<!-- A-DECOUVRIR:FIN -->"
    html_existant = f"<html><body>\n{ancien}\n<h1>Digest</h1>\n</body></html>"
    client = _FakeClient(get_response=_page_publiee(html_existant), put_response=_FakeResponse(200))

    resultat = publish.publier_a_decouvrir(None, client=client)

    assert resultat is True
    corps_publie = base64.b64decode(client.put_calls[0][1]["content"]).decode("utf-8")
    assert "A-DECOUVRIR" not in corps_publie
    assert "ancien-candidat" not in corps_publie
    assert "<h1>Digest</h1>" in corps_publie


def test_a_decouvrir_candidat_none_sans_panneau_existant_ne_fait_rien():
    html_existant = "<html><body>\n<h1>Digest</h1>\n</body></html>"
    client = _FakeClient(get_response=_page_publiee(html_existant), put_response=_FakeResponse(200))

    resultat = publish.publier_a_decouvrir(None, client=client)

    assert resultat is None
    assert client.put_calls == []


def test_a_decouvrir_sans_page_deja_publiee_ne_fait_rien():
    client = _FakeClient(get_response=_FakeResponse(404))

    resultat = publish.publier_a_decouvrir(_candidat(), client=client)

    assert resultat is None
    assert client.put_calls == []


def test_a_decouvrir_contenu_illisible_est_une_vraie_panne():
    payload_sans_content = {"sha": "sha-existant"}
    client = _FakeClient(get_response=_FakeResponse(200, payload=payload_sans_content))

    resultat = publish.publier_a_decouvrir(_candidat(), client=client)

    assert resultat is False


def test_a_decouvrir_degrade_proprement_sans_jeton(monkeypatch):
    monkeypatch.setattr(publish, "_jeton_depuis_env", lambda: None)
    monkeypatch.setattr(publish, "_jeton_depuis_gh_cli", lambda: None)

    resultat = publish.publier_a_decouvrir(_candidat())

    assert resultat is False


def test_a_decouvrir_degrade_proprement_sur_panne_reseau():
    client = _FakeClient(get_leve=httpx.ConnectError("panne réseau"))

    resultat = publish.publier_a_decouvrir(_candidat(), client=client)

    assert resultat is False


def test_a_decouvrir_bout_en_bout_avec_le_vrai_fragment_rendu():
    """Même précaution que pour le récapitulatif de santé : combiner le
    vrai `render.rendre_a_decouvrir` avec `publish.publier_a_decouvrir` —
    une dérive du format des marqueurs entre les deux modules serait
    passée inaperçue si chacun n'était testé qu'isolément."""
    html_existant = "<html><body>\n<h1>Digest</h1>\n</body></html>"
    client = _FakeClient(get_response=_page_publiee(html_existant), put_response=_FakeResponse(200))

    reussite = publish.publier_a_decouvrir(_candidat(id_="flux-x"), client=client)

    assert reussite is True
    corps_publie = base64.b64decode(client.put_calls[0][1]["content"]).decode("utf-8")
    assert "flux-x" in corps_publie
    assert "<h1>Digest</h1>" in corps_publie
