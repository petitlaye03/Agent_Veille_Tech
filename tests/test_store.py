"""Tests de l'état « déjà vu » persistant (AD-5, AD-11, Story 3.4) — aucun
appel réseau ni subprocess réel : client HTTP simulé, résolution de jeton
monkeypatchée, fichier SQLite toujours sous `tmp_path`."""

import base64
from datetime import datetime, timezone

import httpx
import pytest

from veille import store
from veille.models import Item


def _item(source_id="src", guid="g1", url="https://exemple.test/a"):
    return Item(
        source_id=source_id,
        guid=guid,
        titre="Titre",
        date_publication=datetime(2026, 9, 1, tzinfo=timezone.utc),
        langue="fr",
        registre="apprendre",
        url=url,
        contenu_brut="",
    )


# --- _cles_identite ----------------------------------------------------


def test_cles_identite_url_et_guid():
    item = _item(source_id="src", guid="g1", url="https://exemple.test/a")
    cles = store._cles_identite(item)
    assert "url:exemple.test/a" in cles
    assert "guid:src:g1" in cles


def test_cles_identite_sans_url_ni_guid_liste_vide():
    item = _item(guid="", url="")
    assert store._cles_identite(item) == []


def test_cles_identite_guid_scope_par_source():
    """Deux sources avec le même `guid` brut ne doivent jamais se confondre
    — même principe que `dedup._cles_identite`."""
    item_a = _item(source_id="source-a", guid="123", url="")
    item_b = _item(source_id="source-b", guid="123", url="")
    assert store._cles_identite(item_a) != store._cles_identite(item_b)


# --- RapportDejaVu -------------------------------------------------------


def test_rapport_deja_vu_resume_vide():
    assert "aucun item" in store.RapportDejaVu().resume()


def test_rapport_deja_vu_resume_ventile_par_source_triee():
    rapport = store.RapportDejaVu(ecartes_par_source={"b": 1, "a": 3})
    resume = rapport.resume()
    assert "4 item" in resume
    # Le plus gros décompte d'abord, à décompte égal l'ordre alphabétique.
    assert resume.index("a (-3)") < resume.index("b (-1)")


# --- ouvrir / filtrer_deja_vus / marquer_vus ----------------------------


def test_ouvrir_cree_le_fichier_et_la_table(tmp_path):
    chemin = tmp_path / "sous-dossier" / "deja-vu.sqlite3"
    conn = store.ouvrir(chemin)
    try:
        assert chemin.exists()
        conn.execute("SELECT cle FROM deja_vu")  # ne lève pas : la table existe
    finally:
        conn.close()


def test_ouvrir_fixe_le_mode_journal_delete(tmp_path):
    """Revue (Edge Case Hunter) : `televerser_vers_distant` lit le fichier
    en octets bruts, pas via SQL — le mode WAL laisserait des lignes
    commitées dans un fichier `-wal` compagnon jamais téléversé."""
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert mode.lower() == "delete"


def test_filtrer_deja_vus_liste_vide(tmp_path):
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    retenus, rapport = store.filtrer_deja_vus([], conn)
    conn.close()
    assert retenus == []
    assert rapport.total_ecartes == 0


def test_filtrer_deja_vus_retient_tout_si_rien_de_connu(tmp_path):
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    items = [_item(guid="g1"), _item(guid="g2")]
    retenus, rapport = store.filtrer_deja_vus(items, conn)
    conn.close()
    assert retenus == items
    assert rapport.total_ecartes == 0


def test_filtrer_deja_vus_ecarte_par_url_et_par_guid(tmp_path):
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    deja_vu_par_url = _item(source_id="s1", guid="autre", url="https://exemple.test/vu")
    deja_vu_par_guid = _item(source_id="s2", guid="vu-guid", url="https://exemple.test/inconnu")
    nouveau = _item(source_id="s1", guid="neuf", url="https://exemple.test/neuf")

    store.marquer_vus([deja_vu_par_url], conn)
    conn.execute("INSERT OR IGNORE INTO deja_vu (cle) VALUES (?)", ("guid:s2:vu-guid",))
    conn.commit()

    retenus, rapport = store.filtrer_deja_vus(
        [deja_vu_par_url, deja_vu_par_guid, nouveau], conn
    )
    conn.close()

    assert retenus == [nouveau]
    assert rapport.ecartes_par_source == {"s1": 1, "s2": 1}


def test_filtrer_deja_vus_conserve_un_item_sans_identite_verifiable(tmp_path):
    """Même principe que le seuil de signal (Story 1.4) : l'absence de
    donnée n'est jamais une présomption de doublon — un item sans URL ni
    `guid` exploitable reste toujours retenu."""
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    item_sans_identite = _item(guid="", url="")
    retenus, rapport = store.filtrer_deja_vus([item_sans_identite], conn)
    conn.close()
    assert retenus == [item_sans_identite]
    assert rapport.total_ecartes == 0


def test_filtrer_deja_vus_decoupe_les_requetes_par_lots(tmp_path, monkeypatch):
    """Revue (Edge Case Hunter) : une seule requête `IN (...)` sur tout le
    lot d'une nuit peut dépasser le plafond de paramètres liés de SQLite à
    l'échelle. Vérifié avec un lot artificiellement petit (2) pour forcer
    plusieurs requêtes sans construire des centaines d'items en test."""
    monkeypatch.setattr(store, "_TAILLE_LOT_REQUETE", 2)
    conn = store.ouvrir(tmp_path / "d.sqlite3")

    items = [_item(source_id="s", guid=f"g{i}", url="") for i in range(7)]
    vus, nouveaux = items[:5], items[5:]
    store.marquer_vus(vus, conn)

    retenus, rapport = store.filtrer_deja_vus(items, conn)
    conn.close()

    assert retenus == nouveaux
    assert rapport.total_ecartes == 5


def test_filtrer_deja_vus_degrade_sans_lever_si_la_connexion_echoue(tmp_path):
    """Revue (convergence blind+edge) : une panne du sous-système « déjà
    vu » ne doit jamais faire perdre toute la nuit — dégrade en retenant
    tout, sans filtrage, plutôt que de lever."""
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    conn.close()  # toute requête sur une connexion fermée lève désormais

    items = [_item()]
    retenus, rapport = store.filtrer_deja_vus(items, conn)  # ne lève pas

    assert retenus == items
    assert rapport.total_ecartes == 0


def test_marquer_vus_est_idempotent(tmp_path):
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    item = _item()
    store.marquer_vus([item], conn)
    store.marquer_vus([item], conn)  # ne doit jamais lever (clé déjà connue)

    retenus, rapport = store.filtrer_deja_vus([item], conn)
    conn.close()
    assert retenus == []
    assert rapport.total_ecartes == 1


def test_marquer_vus_puis_reouverture_persiste_sur_disque(tmp_path):
    """La persistance doit survivre à une fermeture/réouverture de la
    connexion — condition nécessaire à la persistance à travers les runs
    GitHub Actions une fois le fichier retéléversé/resynchronisé."""
    chemin = tmp_path / "d.sqlite3"
    item = _item()

    conn = store.ouvrir(chemin)
    store.marquer_vus([item], conn)
    conn.close()

    conn2 = store.ouvrir(chemin)
    retenus, _ = store.filtrer_deja_vus([item], conn2)
    conn2.close()
    assert retenus == []


# --- Résolution du jeton -------------------------------------------------


def test_jeton_priorite_a_source_github_token(monkeypatch):
    monkeypatch.setattr(store, "_env_charge", True)
    monkeypatch.setenv("SOURCE_GITHUB_TOKEN", "jeton-source")
    monkeypatch.setattr(store, "_jeton_depuis_gh_cli", lambda: "jeton-gh-cli")
    assert store._jeton() == "jeton-source"


def test_jeton_blanc_traite_comme_absent_puis_replie_sur_gh_cli(monkeypatch):
    monkeypatch.setattr(store, "_env_charge", True)
    monkeypatch.setenv("SOURCE_GITHUB_TOKEN", "   ")
    monkeypatch.setattr(store, "_jeton_depuis_gh_cli", lambda: "jeton-gh-cli")
    assert store._jeton() == "jeton-gh-cli"


def test_jeton_none_si_aucune_voie_ne_resout(monkeypatch):
    monkeypatch.setattr(store, "_env_charge", True)
    monkeypatch.delenv("SOURCE_GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(store, "_jeton_depuis_gh_cli", lambda: None)
    assert store._jeton() is None


def test_client_none_si_jeton_absent(monkeypatch):
    monkeypatch.setattr(store, "_jeton", lambda: None)
    monkeypatch.setattr(store, "_avertissement_jeton_absent_emis", False)
    assert store._client() is None


# --- synchroniser_depuis_distant / televerser_vers_distant --------------


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


def test_synchroniser_sans_jeton_ne_touche_pas_au_fichier_local(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_jeton", lambda: None)
    chemin = tmp_path / "d.sqlite3"
    store.synchroniser_depuis_distant(chemin)
    assert not chemin.exists()


def test_synchroniser_404_distant_n_ecrit_rien(tmp_path):
    client = _FakeClient(get_response=_FakeResponse(404))
    chemin = tmp_path / "d.sqlite3"
    store.synchroniser_depuis_distant(chemin, client=client)
    assert not chemin.exists()
    assert not client.closed  # client fourni : jamais fermé par la fonction


def test_synchroniser_ecrit_le_contenu_decode(tmp_path):
    contenu = b"contenu-sqlite-simule"
    payload = {"content": base64.b64encode(contenu).decode("ascii")}
    client = _FakeClient(get_response=_FakeResponse(200, payload))
    chemin = tmp_path / "sous-dossier" / "d.sqlite3"

    store.synchroniser_depuis_distant(chemin, client=client)

    assert chemin.read_bytes() == contenu


def test_synchroniser_ne_leve_jamais_sur_panne_reseau(tmp_path):
    client = _FakeClient(get_leve=httpx.ConnectError("panne"))
    chemin = tmp_path / "d.sqlite3"
    store.synchroniser_depuis_distant(chemin, client=client)  # ne lève pas
    assert not chemin.exists()


def test_televerser_sans_jeton_renvoie_false(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_jeton", lambda: None)
    chemin = tmp_path / "d.sqlite3"
    chemin.write_bytes(b"x")
    assert store.televerser_vers_distant(chemin) is False


def test_televerser_cree_quand_le_fichier_distant_n_existe_pas(tmp_path):
    chemin = tmp_path / "d.sqlite3"
    chemin.write_bytes(b"contenu")
    client = _FakeClient(
        get_response=_FakeResponse(404),
        put_response=_FakeResponse(201),
    )

    reussite = store.televerser_vers_distant(chemin, client=client)

    assert reussite is True
    url, corps = client.put_calls[0]
    assert corps["message"] == "Publication de l'état déjà-vu"
    assert "sha" not in corps
    assert base64.b64decode(corps["content"]) == b"contenu"


def test_televerser_met_a_jour_avec_le_sha_existant(tmp_path):
    chemin = tmp_path / "d.sqlite3"
    chemin.write_bytes(b"contenu")
    client = _FakeClient(
        get_response=_FakeResponse(200, {"sha": "sha-existant"}),
        put_response=_FakeResponse(200),
    )

    reussite = store.televerser_vers_distant(chemin, client=client)

    assert reussite is True
    _, corps = client.put_calls[0]
    assert corps["message"] == "Mise à jour de l'état déjà-vu"
    assert corps["sha"] == "sha-existant"


def test_televerser_echec_put_renvoie_false(tmp_path):
    chemin = tmp_path / "d.sqlite3"
    chemin.write_bytes(b"contenu")
    client = _FakeClient(
        get_response=_FakeResponse(404),
        put_response=_FakeResponse(500),
    )
    assert store.televerser_vers_distant(chemin, client=client) is False


def test_televerser_ne_leve_jamais_sur_panne_reseau(tmp_path):
    chemin = tmp_path / "d.sqlite3"
    chemin.write_bytes(b"contenu")
    client = _FakeClient(get_leve=httpx.ConnectError("panne"))
    assert store.televerser_vers_distant(chemin, client=client) is False
