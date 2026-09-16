"""Tests de l'orchestrateur (AD-1, Story 1.8) — chemin complet, clients LLM
et de publication simulés, aucun appel réseau réel."""

import textwrap
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from veille import pipeline, publish, store

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _isoler_le_stockage_deja_vu(tmp_path, monkeypatch):
    """Isole tous les tests de ce module du vrai `data/deja-vu.sqlite3` du
    dépôt de travail et de tout appel réseau de synchronisation (Story 3.4)
    — sans ceci, chaque appel à `pipeline.executer()` ouvrirait/écrirait le
    fichier par défaut et tenterait de résoudre un jeton réel (`gh auth
    token`). Les tests qui exercent spécifiquement le câblage du stockage
    (synchronisation, marquage, retéléversement) remplacent explicitement
    ce qu'il faut par-dessus cette isolation par défaut.

    `publish._jeton` neutralisé aussi (trouvé en implémentation de la
    Story 4.3) : `controler_fraicheur()` appelle désormais `publish.
    publier_recapitulatif_sante(..., client=publish_client)`, et
    `publish_client=None` par défaut — sans cette neutralisation, chaque
    test de `controler_fraicheur()` sans client explicite aurait résolu un
    vrai jeton (`gh auth token`) et fait un vrai appel réseau en lecture
    vers l'API GitHub du dépôt de sortie."""
    monkeypatch.setattr(store, "CHEMIN_LOCAL_DEFAUT", tmp_path / "deja-vu.sqlite3")
    monkeypatch.setattr(store, "_jeton", lambda: None)
    monkeypatch.setattr(publish, "_jeton", lambda: None)


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


class _ClientPublicationAvecEtat:
    """Simule le client HTTP de `publish.py` **avec mémoire entre appels**
    (Story 3.3) — contrairement à `_ClientPublicationSimule` (toujours 404
    au `GET`, jamais de `sha` à réutiliser), celui-ci se comporte comme
    l'API Contents de GitHub sur deux runs successifs : un contenu publié
    par un `PUT` est retrouvé par le `GET` suivant, avec le `sha` que
    GitHub aurait réellement renvoyé.

    `sha` est un simple compteur global, pas un vrai hash de contenu
    (simplification délibérée, sans conséquence : rien de ce que `publish.py`
    fait ne dépend de la valeur du `sha`, seulement de sa présence/absence).
    Statut HTTP réaliste (trouvé en revue) : 201 à la création, **200** à
    la mise à jour — comme la vraie API Contents ; `publish.py` ne
    distingue pas les deux aujourd'hui, mais la fidélité de la simulation
    ne doit pas être surévaluée dans sa propre docstring pour autant."""

    def __init__(self):
        self.put_calls = []
        self.closed = False
        self._fichiers: dict[str, dict] = {}
        self._compteur_sha = 0

    def _chemin(self, url: str) -> str:
        return url.split("/contents/", 1)[1]

    def get(self, url):
        fichier = self._fichiers.get(self._chemin(url))
        if fichier is None:
            return _FakeResponse(404)
        return _FakeResponse(200, payload=fichier)

    def put(self, url, json=None):
        self.put_calls.append((url, json))
        chemin = self._chemin(url)
        creation = chemin not in self._fichiers
        self._compteur_sha += 1
        self._fichiers[chemin] = {
            "content": json["content"],
            "sha": f"sha-{self._compteur_sha}",
        }
        return _FakeResponse(201 if creation else 200)

    def close(self):
        self.closed = True


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


class _HorlogeFigee:
    """Trouvé en revue (Story 3.3, convergence des 3 couches) : sans horloge
    figée, deux runs qui chevaucheraient minuit UTC viseraient deux chemins
    d'archive différents — le test perdrait alors sa prémisse (« même
    date ») sans que rien ne le signale, un risque de fragilité rare mais
    réel pour un test censé prouver l'absence de duplication."""

    _MAINTENANT = datetime(2026, 9, 14, 22, 17, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        return cls._MAINTENANT


def test_relancer_pour_la_meme_date_ecrase_au_lieu_de_dupliquer(tmp_path, monkeypatch):
    """Story 3.3 (AC1/AC2) : deux runs successifs de `pipeline.executer()`
    pour la même date ne doivent produire qu'une création suivie d'une
    mise à jour — jamais deux créations (= deux fichiers). Le client à
    état se comporte comme l'API Contents de GitHub réelle sur deux runs
    successifs, contrairement à `_ClientPublicationSimule` (toujours 404),
    qui ne peut jamais exercer le chemin « mise à jour »."""
    monkeypatch.setattr(pipeline, "datetime", _HorlogeFigee)

    sources_yaml = _sources_yaml(tmp_path)
    client = _ClientPublicationAvecEtat()

    # Espionne collect.collecter (trouvé en revue) : les deux runs
    # produisent un contenu identique par construction (fixture statique),
    # ce qui à lui seul ne prouve pas que le second run a vraiment
    # recollecté plutôt que rejoué une sortie mise en cache.
    appels_collecte = []
    collecter_reel = pipeline.collect.collecter

    def _collecter_espion(*args, **kwargs):
        resultat = collecter_reel(*args, **kwargs)
        appels_collecte.append(resultat)
        return resultat

    monkeypatch.setattr(pipeline.collect, "collecter", _collecter_espion)

    premiere_reussite = pipeline.executer(
        sources_path=sources_yaml, llm_client=_ClientLLMSimule(), publish_client=client
    )
    # État après le premier run : le `sha` que le second run doit retrouver
    # et réutiliser — capturé ici, avant qu'il ne soit remplacé par le
    # second run (le client à état ne garde que le `sha` le plus récent
    # par chemin, comme le ferait réellement GitHub).
    sha_apres_premier_run = {chemin: f["sha"] for chemin, f in client._fichiers.items()}

    seconde_reussite = pipeline.executer(
        sources_path=sources_yaml, llm_client=_ClientLLMSimule(), publish_client=client
    )

    assert premiere_reussite is True
    assert seconde_reussite is True
    assert len(appels_collecte) == 2  # vraie recollecte, pas une sortie rejouée
    assert client.closed is False  # un client fourni explicitement n'est jamais fermé, même réutilisé

    par_chemin = {}
    for url, corps in client.put_calls:
        par_chemin.setdefault(client._chemin(url), []).append(corps)

    # 2 chemins (page + archive), exactement 2 PUT chacun (1 création + 1
    # mise à jour) — jamais plus, ce qui signalerait une duplication.
    assert len(par_chemin) == 2, f"{len(par_chemin)} chemin(s) publié(s) au lieu de 2 : {list(par_chemin)}"
    for chemin, appels in par_chemin.items():
        assert len(appels) == 2, f"{chemin} : {len(appels)} PUT au lieu de 2"
        creation, mise_a_jour = appels
        assert "sha" not in creation  # rien à écraser au premier run
        # Le second run réutilise le sha renvoyé par le premier PUT de ce
        # même chemin — la mise à jour, pas une création parallèle.
        assert mise_a_jour["sha"] == sha_apres_premier_run[chemin]

    # L'archive vise bien un seul chemin daté sur les deux runs (AC2) —
    # jamais deux entrées pour la même date.
    chemins_archive = [c for c in par_chemin if "/archive/" in c]
    assert len(chemins_archive) == 1


def test_relancer_apres_un_echec_partiel_n_ecrase_que_ce_qui_manquait(tmp_path, monkeypatch):
    """Story 3.3 (AC1), scénario plus réaliste que « succès puis succès » :
    la page se publie mais l'archive échoue au premier run (ex. panne
    réseau ponctuelle) — la reprise doit mettre à jour la page (elle
    existait déjà) et **créer** l'archive (elle n'a jamais réussi), jamais
    dupliquer la page ni échouer à combler l'archive manquante."""
    monkeypatch.setattr(pipeline, "datetime", _HorlogeFigee)
    sources_yaml = _sources_yaml(tmp_path)

    client = _ClientPublicationAvecEtat()
    put_reel = client.put

    def _put_qui_echoue_une_fois_sur_larchive(url, json=None):
        if "/archive/" in url and not any("archive" in u for u, _ in client.put_calls):
            client.put_calls.append((url, json))  # la tentative a bien eu lieu
            return _FakeResponse(500)
        return put_reel(url, json=json)

    monkeypatch.setattr(client, "put", _put_qui_echoue_une_fois_sur_larchive)

    premier_run = pipeline.executer(
        sources_path=sources_yaml, llm_client=_ClientLLMSimule(), publish_client=client
    )
    assert premier_run is False  # l'archive a échoué

    second_run = pipeline.executer(
        sources_path=sources_yaml, llm_client=_ClientLLMSimule(), publish_client=client
    )
    assert second_run is True

    par_chemin = {}
    for url, corps in client.put_calls:
        par_chemin.setdefault(client._chemin(url), []).append(corps)

    # Page : 2 PUT (créée avec succès au 1er run, mise à jour au 2nd).
    chemin_page = next(c for c in par_chemin if "/archive/" not in c)
    assert len(par_chemin[chemin_page]) == 2
    assert "sha" not in par_chemin[chemin_page][0]
    assert "sha" in par_chemin[chemin_page][1]

    # Archive : 2 tentatives de PUT (1 échouée au 1er run, jamais
    # enregistrée côté serveur simulé, donc la 2ᵉ est aussi une création,
    # pas une mise à jour) — mais une seule entrée finale, jamais deux.
    chemin_archive = next(c for c in par_chemin if "/archive/" in c)
    assert len(par_chemin[chemin_archive]) == 2
    assert "sha" not in par_chemin[chemin_archive][0]
    assert "sha" not in par_chemin[chemin_archive][1]  # toujours une création : le 1er a échoué côté serveur
    assert len([c for c in par_chemin if "/archive/" in c]) == 1  # une seule entrée d'archive au final


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


# --- Câblage de l'état « déjà vu » (AD-5, AD-11, Story 3.4) --------------


class _ClientStoreSimule:
    """Simule le client HTTP de `store.py` : mêmes conventions que
    `_ClientPublicationSimule`, dépôt source distinct."""

    def __init__(self):
        self.get_calls = []
        self.put_calls = []
        self.closed = False

    def get(self, url):
        self.get_calls.append(url)
        return _FakeResponse(404)

    def put(self, url, json=None):
        self.put_calls.append((url, json))
        return _FakeResponse(201)

    def close(self):
        self.closed = True


def test_executer_marque_vus_et_televerse_seulement_apres_succes(tmp_path):
    """AD-11 : `marquer_vus`/`televerser_vers_distant` ne doivent être
    appelés qu'une fois `page_ok and archive_ok` confirmés — jamais avant,
    jamais sur un échec, pour qu'un run qui échoue puisse retenter les
    mêmes items à la prochaine reprise."""
    sources_yaml = _sources_yaml(tmp_path)
    deja_vus_path = tmp_path / "deja-vu.sqlite3"
    client_store = _ClientStoreSimule()

    reussite = pipeline.executer(
        sources_path=sources_yaml,
        llm_client=_ClientLLMSimule(),
        publish_client=_ClientPublicationSimule(),
        deja_vus_path=deja_vus_path,
        store_client=client_store,
    )

    assert reussite is True
    # Synchronisation en lecture avant collecte, retéléversement après
    # succès : au moins un GET (sync + vérif sha avant PUT) et un PUT.
    assert len(client_store.get_calls) >= 1
    assert len(client_store.put_calls) == 1

    from veille import store

    conn = store.ouvrir(deja_vus_path)
    try:
        lignes = conn.execute("SELECT cle FROM deja_vu").fetchall()
    finally:
        conn.close()
    # Chaque item de test porte à la fois une URL et un guid distincts
    # (fixture RSS) : deux items marqués vus = 4 clés d'identité en base.
    assert len(lignes) == 4


def test_executer_ne_marque_rien_ni_ne_televerse_si_la_publication_echoue(tmp_path, monkeypatch):
    sources_yaml = _sources_yaml(tmp_path)
    deja_vus_path = tmp_path / "deja-vu.sqlite3"
    client_store = _ClientStoreSimule()

    from veille import publish

    monkeypatch.setattr(publish, "_jeton_depuis_env", lambda: None)
    monkeypatch.setattr(publish, "_jeton_depuis_gh_cli", lambda: None)

    reussite = pipeline.executer(
        sources_path=sources_yaml,
        llm_client=_ClientLLMSimule(),
        publish_client=None,  # aucun jeton résolu en test → publication en échec
        deja_vus_path=deja_vus_path,
        store_client=client_store,
    )

    assert reussite is False
    assert client_store.put_calls == []

    from veille import store

    conn = store.ouvrir(deja_vus_path)
    try:
        lignes = conn.execute("SELECT cle FROM deja_vu").fetchall()
    finally:
        conn.close()
    assert lignes == []


def test_executer_filtre_les_items_deja_marques_vus_lors_d_une_relance(tmp_path, monkeypatch):
    """Bout en bout : un run réussi marque ses items vus ; un second run,
    mêmes sources, ne republie plus rien (tout est déjà vu) — sans qu'un
    troisième run ne casse quoi que ce soit une fois la nuit épuisée."""
    monkeypatch.setattr(pipeline, "datetime", _HorlogeFigee)
    sources_yaml = _sources_yaml(tmp_path)
    deja_vus_path = tmp_path / "deja-vu.sqlite3"

    entrees_captees = []
    rendre_original = pipeline.rendre

    def _rendre_espion(entrees, maintenant):
        entrees_captees.append(list(entrees))
        return rendre_original(entrees, maintenant)

    monkeypatch.setattr(pipeline, "rendre", _rendre_espion)

    premiere_reussite = pipeline.executer(
        sources_path=sources_yaml,
        llm_client=_ClientLLMSimule(),
        publish_client=_ClientPublicationSimule(),
        deja_vus_path=deja_vus_path,
        store_client=_ClientStoreSimule(),
    )
    seconde_reussite = pipeline.executer(
        sources_path=sources_yaml,
        llm_client=_ClientLLMSimule(),
        publish_client=_ClientPublicationSimule(),
        deja_vus_path=deja_vus_path,
        store_client=_ClientStoreSimule(),
    )

    assert premiere_reussite is True
    assert seconde_reussite is True
    assert len(entrees_captees[0]) == 2  # premier run : tout est nouveau
    assert entrees_captees[1] == []  # second run : tout est déjà vu


class _ClientStoreQuiEchoueAuTeleversement:
    """PUT échoue systématiquement (panne réseau/jeton expiré simulée) —
    GET se comporte normalement (404 : rien de distant encore)."""

    def __init__(self):
        self.put_calls = []
        self.closed = False

    def get(self, url):
        return _FakeResponse(404)

    def put(self, url, json=None):
        self.put_calls.append((url, json))
        return _FakeResponse(500)

    def close(self):
        self.closed = True


def test_executer_reussit_quand_meme_si_le_televersement_echoue_mais_avertit(
    tmp_path, caplog
):
    """Revue (convergence 3/3 couches) : un échec de retéléversement après
    une publication réussie ne doit jamais faire échouer le run (le digest
    a bel et bien été publié) — mais ne doit plus non plus rester
    totalement silencieux, corrigé en revue par un log explicite."""
    import logging

    sources_yaml = _sources_yaml(tmp_path)
    deja_vus_path = tmp_path / "deja-vu.sqlite3"

    with caplog.at_level(logging.WARNING, logger="veille.pipeline"):
        reussite = pipeline.executer(
            sources_path=sources_yaml,
            llm_client=_ClientLLMSimule(),
            publish_client=_ClientPublicationSimule(),
            deja_vus_path=deja_vus_path,
            store_client=_ClientStoreQuiEchoueAuTeleversement(),
        )

    assert reussite is True  # la page ET l'archive ont bien été publiées
    assert "Retéléversement de l'état « déjà vu » en échec" in caplog.text


def test_executer_ne_devient_pas_un_echec_si_le_marquage_deja_vu_leve(
    tmp_path, monkeypatch
):
    """Revue : une exception dans le marquage/retéléversement (après une
    publication pourtant réussie) ne doit jamais requalifier le run en
    échec — isolée par son propre `try` plutôt que par le filet de
    sécurité englobant de `executer()`."""
    sources_yaml = _sources_yaml(tmp_path)
    deja_vus_path = tmp_path / "deja-vu.sqlite3"

    from veille import store

    def _marquer_vus_qui_leve(*args, **kwargs):
        raise RuntimeError("disque plein simulé")

    monkeypatch.setattr(store, "marquer_vus", _marquer_vus_qui_leve)

    reussite = pipeline.executer(
        sources_path=sources_yaml,
        llm_client=_ClientLLMSimule(),
        publish_client=_ClientPublicationSimule(),
        deja_vus_path=deja_vus_path,
        store_client=_ClientStoreSimule(),
    )

    assert reussite is True  # la publication, elle, a bien réussi


def test_executer_degrade_sans_filtrage_deja_vu_si_store_ouvrir_leve(
    tmp_path, monkeypatch
):
    """Revue (convergence blind+edge) : une panne d'ouverture du fichier
    SQLite local ne doit dégrader que le filtrage « déjà vu » de ce run —
    jamais faire perdre toute la collecte/publication."""
    sources_yaml = _sources_yaml(tmp_path)
    deja_vus_path = tmp_path / "deja-vu.sqlite3"

    from veille import store

    def _ouvrir_qui_leve(*args, **kwargs):
        raise RuntimeError("fichier corrompu simulé")

    monkeypatch.setattr(store, "ouvrir", _ouvrir_qui_leve)

    reussite = pipeline.executer(
        sources_path=sources_yaml,
        llm_client=_ClientLLMSimule(),
        publish_client=_ClientPublicationSimule(),
        deja_vus_path=deja_vus_path,
        store_client=_ClientStoreSimule(),
    )

    assert reussite is True


def test_executer_ne_marque_pas_vu_un_item_de_registre_inconnu(tmp_path):
    """Revue (Acceptance Auditor) : un item dont le `registre` n'est
    reconnu par aucune section rendue (`render._grouper_par_registre`,
    dégradation pré-existante documentée depuis la Story 1.8) n'a jamais
    été réellement montré à l'utilisateur — le marquer « vu » le ferait
    disparaître en permanence sans avoir jamais été publié une seule fois."""
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
                registre: registre-inconnu
            """
        ),
        encoding="utf-8",
    )
    deja_vus_path = tmp_path / "deja-vu.sqlite3"

    reussite = pipeline.executer(
        sources_path=sources_yaml,
        llm_client=_ClientLLMSimule(),
        publish_client=_ClientPublicationSimule(),
        deja_vus_path=deja_vus_path,
        store_client=_ClientStoreSimule(),
    )

    assert reussite is True

    from veille import store

    conn = store.ouvrir(deja_vus_path)
    try:
        lignes = conn.execute("SELECT cle FROM deja_vu").fetchall()
    finally:
        conn.close()
    assert lignes == []  # rien marqué : jamais réellement publié


# --- Contrôle de fraîcheur hebdomadaire (FR-12/13, Story 4.1) -----------


def test_controler_fraicheur_evalue_et_reteleverse(tmp_path):
    from veille import store

    sources_yaml = _sources_yaml(tmp_path)
    deja_vus_path = tmp_path / "deja-vu.sqlite3"

    conn = store.ouvrir(deja_vus_path)
    conn.execute(
        "INSERT INTO sante_source (source_id, dernier_item_vu, etat) "
        "VALUES ('test-source', '2000-01-01T00:00:00+00:00', 'active')"
    )
    conn.commit()
    conn.close()

    client_store = _ClientStoreSimule()
    reussite = pipeline.controler_fraicheur(
        sources_path=sources_yaml, deja_vus_path=deja_vus_path, store_client=client_store
    )

    assert reussite is True
    assert len(client_store.put_calls) == 1

    conn = store.ouvrir(deja_vus_path)
    (etat,) = conn.execute(
        "SELECT etat FROM sante_source WHERE source_id = 'test-source'"
    ).fetchone()
    conn.close()
    assert etat == "en_sommeil"  # très ancienne date : > 90 jours


def test_controler_fraicheur_journalise_le_resume(tmp_path, caplog):
    import logging

    from veille import store

    sources_yaml = _sources_yaml(tmp_path)
    deja_vus_path = tmp_path / "deja-vu.sqlite3"
    conn = store.ouvrir(deja_vus_path)
    conn.execute(
        "INSERT INTO sante_source (source_id, dernier_item_vu, etat) "
        "VALUES ('test-source', '2000-01-01T00:00:00+00:00', 'active')"
    )
    conn.commit()
    conn.close()

    with caplog.at_level(logging.INFO, logger="veille.pipeline"):
        pipeline.controler_fraicheur(
            sources_path=sources_yaml, deja_vus_path=deja_vus_path, store_client=_ClientStoreSimule()
        )

    assert "Contrôle de fraîcheur" in caplog.text


def test_controler_fraicheur_retourne_false_si_le_televersement_echoue(tmp_path):
    sources_yaml = _sources_yaml(tmp_path)
    deja_vus_path = tmp_path / "deja-vu.sqlite3"

    reussite = pipeline.controler_fraicheur(
        sources_path=sources_yaml,
        deja_vus_path=deja_vus_path,
        store_client=_ClientStoreQuiEchoueAuTeleversement(),
    )

    assert reussite is False


def test_controler_fraicheur_ne_leve_jamais_si_ouverture_echoue(tmp_path, monkeypatch):
    from veille import store

    def _ouvrir_qui_leve(*args, **kwargs):
        raise RuntimeError("fichier corrompu simulé")

    monkeypatch.setattr(store, "ouvrir", _ouvrir_qui_leve)

    reussite = pipeline.controler_fraicheur(
        sources_path=_sources_yaml(tmp_path),
        deja_vus_path=tmp_path / "deja-vu.sqlite3",
        store_client=_ClientStoreSimule(),
    )

    assert reussite is False


class _ClientDigestPublie:
    """Simule le client HTTP de `publish.py` pour le dépôt de sortie
    (Story 4.3) : une page déjà publiée existe, avec ou sans panneau de
    récapitulatif déjà présent."""

    def __init__(self, html_publie: str):
        self.html_publie = html_publie
        self.put_calls = []
        self.closed = False

    def get(self, url):
        import base64

        return _FakeResponse(
            200,
            payload={
                "content": base64.b64encode(self.html_publie.encode("utf-8")).decode("ascii"),
                "sha": "sha-page",
            },
        )

    def put(self, url, json=None):
        self.put_calls.append((url, json))
        return _FakeResponse(200)

    def close(self):
        self.closed = True


def test_controler_fraicheur_publie_le_recapitulatif_des_sources_a_surveiller(tmp_path):
    from veille import store

    sources_yaml = _sources_yaml(tmp_path)
    deja_vus_path = tmp_path / "deja-vu.sqlite3"
    conn = store.ouvrir(deja_vus_path)
    conn.execute(
        "INSERT INTO sante_source (source_id, dernier_item_vu, etat) "
        "VALUES ('test-source', '2000-01-01T00:00:00+00:00', 'active')"
    )
    conn.commit()
    conn.close()

    client_digest = _ClientDigestPublie("<html><body>\n<h1>Digest</h1>\n</body></html>")

    reussite = pipeline.controler_fraicheur(
        sources_path=sources_yaml,
        deja_vus_path=deja_vus_path,
        store_client=_ClientStoreSimule(),
        publish_client=client_digest,
    )

    assert reussite is True
    assert len(client_digest.put_calls) == 1  # le récapitulatif a bien été publié
    corps_publie = client_digest.put_calls[0][1]["content"]
    import base64

    html_publie = base64.b64decode(corps_publie).decode("utf-8")
    assert "test-source" in html_publie
    assert "en_sommeil" in html_publie


def test_controler_fraicheur_n_echoue_pas_si_la_publication_du_recapitulatif_echoue(tmp_path, monkeypatch):
    """Isolation dédiée (Story 4.3) : une panne de la publication annexe
    du récapitulatif ne doit jamais changer ce que retourne
    `controler_fraicheur()`, gouverné uniquement par le retéléversement de
    l'état de santé."""
    from veille import store

    sources_yaml = _sources_yaml(tmp_path)
    deja_vus_path = tmp_path / "deja-vu.sqlite3"
    conn = store.ouvrir(deja_vus_path)
    conn.execute(
        "INSERT INTO sante_source (source_id, dernier_item_vu, etat) "
        "VALUES ('test-source', '2000-01-01T00:00:00+00:00', 'active')"
    )
    conn.commit()
    conn.close()

    def _publier_recapitulatif_qui_leve(*args, **kwargs):
        raise RuntimeError("panne simulée")

    monkeypatch.setattr(pipeline, "publier_recapitulatif_sante", _publier_recapitulatif_qui_leve)

    reussite = pipeline.controler_fraicheur(
        sources_path=sources_yaml,
        deja_vus_path=deja_vus_path,
        store_client=_ClientStoreSimule(),
        publish_client=_ClientDigestPublie("<html><body></body></html>"),
    )

    assert reussite is True  # inchangé : gouverné par le retéléversement, pas par le récapitulatif


def test_main_controle_sante_sort_avec_le_code_zero_si_reussi(monkeypatch):
    monkeypatch.setattr(pipeline, "controler_fraicheur", lambda **kwargs: True)

    with pytest.raises(SystemExit) as exc_info:
        pipeline.main_controle_sante()

    assert exc_info.value.code == 0


def test_main_controle_sante_sort_avec_un_code_non_nul_si_echoue(monkeypatch):
    monkeypatch.setattr(pipeline, "controler_fraicheur", lambda **kwargs: False)

    with pytest.raises(SystemExit) as exc_info:
        pipeline.main_controle_sante()

    assert exc_info.value.code == 1


# --- Réapplication du récapitulatif après la publication nocturne (Story 4.3) ---


def test_executer_reapplique_le_recapitulatif_apres_avoir_republie_la_page(tmp_path):
    """Trouvé en revue (Blind Hunter, constat le plus sérieux de la Story
    4.3) : `rendre()` régénère `index.html` sans rien savoir des marqueurs
    du récapitulatif de santé — sans réapplication, la publication
    nocturne normale effacerait silencieusement le panneau publié par le
    contrôle hebdomadaire, alors même que les sources concernées restent
    réellement `suspecte`/`en_sommeil`."""
    from veille import store

    sources_yaml = _sources_yaml(tmp_path)
    deja_vus_path = tmp_path / "deja-vu.sqlite3"
    conn = store.ouvrir(deja_vus_path)
    conn.execute(
        "INSERT INTO sante_source (source_id, dernier_item_vu, etat) "
        "VALUES ('test-source', '2000-01-01T00:00:00+00:00', 'suspecte')"
    )
    conn.commit()
    conn.close()

    client_publication = _ClientPublicationAvecEtat()

    reussite = pipeline.executer(
        sources_path=sources_yaml,
        llm_client=_ClientLLMSimule(),
        publish_client=client_publication,
        deja_vus_path=deja_vus_path,
        store_client=_ClientStoreSimule(),
    )

    import base64

    assert reussite is True
    html_final = base64.b64decode(
        client_publication._fichiers["index.html"]["content"]
    ).decode("utf-8")
    assert "test-source" in html_final
    assert "RECAPITULATIF-SANTE" in html_final


def test_controler_fraicheur_retire_le_recapitulatif_si_plus_rien_a_surveiller(tmp_path):
    """Complète le test unitaire déjà présent dans `test_publish.py` au
    niveau du câblage réel de `controler_fraicheur()` (trouvé en revue,
    test-coverage gap) : AC4 — un panneau déjà publié doit être retiré une
    fois que plus aucune source n'est à surveiller."""
    from veille import store

    from datetime import datetime, timezone

    sources_yaml = _sources_yaml(tmp_path)
    deja_vus_path = tmp_path / "deja-vu.sqlite3"
    conn = store.ouvrir(deja_vus_path)
    conn.execute(
        "INSERT INTO sante_source (source_id, dernier_item_vu, etat) VALUES (?, ?, 'active')",
        ("test-source", datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()

    html_avec_panneau = (
        "<html><body>\n"
        "<!-- RECAPITULATIF-SANTE:DEBUT -->ancien souci<!-- RECAPITULATIF-SANTE:FIN -->\n"
        "<h1>Digest</h1>\n</body></html>"
    )
    client_digest = _ClientDigestPublie(html_avec_panneau)

    reussite = pipeline.controler_fraicheur(
        sources_path=sources_yaml,
        deja_vus_path=deja_vus_path,
        store_client=_ClientStoreSimule(),
        publish_client=client_digest,
    )

    import base64

    assert reussite is True
    corps_publie = client_digest.put_calls[0][1]["content"]
    html_publie = base64.b64decode(corps_publie).decode("utf-8")
    assert "RECAPITULATIF-SANTE" not in html_publie
    assert "ancien souci" not in html_publie
    assert "<h1>Digest</h1>" in html_publie
