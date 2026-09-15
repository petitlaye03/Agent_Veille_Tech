"""Tests de la santé des sources (AD-5, AD-6, FR-12/13, Story 4.1) — aucune
horloge réelle, aucun appel réseau : connexions SQLite réelles sur fichier
temporaire, `aujourdhui` toujours injecté explicitement."""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from veille import health, store
from veille.models import Item


def _item(source_id="src", jours_avant=0, guid="g"):
    return Item(
        source_id=source_id,
        guid=guid,
        titre="Titre",
        date_publication=datetime.now(timezone.utc) - timedelta(days=jours_avant),
        langue="fr",
        registre="apprendre",
        url="https://exemple.test/a",
        contenu_brut="",
    )


def _source(id_):
    return SimpleNamespace(id=id_)


# --- enregistrer_activite -------------------------------------------------


def test_enregistrer_activite_liste_vide_ne_fait_rien(tmp_path):
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    health.enregistrer_activite("src", [], conn)
    ligne = conn.execute("SELECT * FROM sante_source WHERE source_id = 'src'").fetchone()
    conn.close()
    assert ligne is None


def test_enregistrer_activite_insere_avec_etat_actif_par_defaut(tmp_path):
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    health.enregistrer_activite("src", [_item(jours_avant=1)], conn)
    dernier, etat = conn.execute(
        "SELECT dernier_item_vu, etat FROM sante_source WHERE source_id = 'src'"
    ).fetchone()
    conn.close()
    assert dernier is not None
    assert etat == health.ETAT_ACTIF


def test_enregistrer_activite_prend_le_plus_recent_du_lot(tmp_path):
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    item_vieux = _item(jours_avant=10, guid="vieux")
    item_frais = _item(jours_avant=1, guid="frais")
    health.enregistrer_activite("src", [item_vieux, item_frais], conn)
    (dernier,) = conn.execute(
        "SELECT dernier_item_vu FROM sante_source WHERE source_id = 'src'"
    ).fetchone()
    conn.close()
    assert datetime.fromisoformat(dernier) == item_frais.date_publication


def test_enregistrer_activite_ne_regresse_jamais(tmp_path):
    """Une nuit sans nouvel item ne doit jamais rajeunir artificiellement
    une source dont le dernier item connu est plus récent que ce lot."""
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    item_frais = _item(jours_avant=1, guid="frais")
    health.enregistrer_activite("src", [item_frais], conn)
    health.enregistrer_activite("src", [_item(jours_avant=20, guid="vieux")], conn)
    (dernier,) = conn.execute(
        "SELECT dernier_item_vu FROM sante_source WHERE source_id = 'src'"
    ).fetchone()
    conn.close()
    assert datetime.fromisoformat(dernier) == item_frais.date_publication


def test_enregistrer_activite_ne_touche_jamais_etat_existant(tmp_path):
    """La transition d'état est le rôle exclusif d'`evaluer_fraicheur` —
    un nouvel item ne doit pas remettre `suspecte` à `active` tout seul."""
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    health.enregistrer_activite("src", [_item(jours_avant=40)], conn)
    conn.execute("UPDATE sante_source SET etat = 'suspecte' WHERE source_id = 'src'")
    conn.commit()

    health.enregistrer_activite("src", [_item(jours_avant=1)], conn)

    (etat,) = conn.execute("SELECT etat FROM sante_source WHERE source_id = 'src'").fetchone()
    conn.close()
    assert etat == "suspecte"


def test_enregistrer_activite_degrade_sans_lever_si_la_connexion_echoue(tmp_path):
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    conn.close()
    health.enregistrer_activite("src", [_item()], conn)  # ne lève pas


def test_enregistrer_activite_ignore_un_item_a_date_future(tmp_path):
    """Trouvé en revue (Edge Case Hunter) : sans ce filtre, un item à date
    future (bug d'horloge côté source, flux malformé) figerait
    `dernier_item_vu` dans le futur pour toujours — la règle « ne régresse
    jamais » empêcherait alors toute correction ultérieure, et la source
    resterait `active` indéfiniment même si elle s'était réellement tue."""
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    maintenant = datetime(2026, 1, 1, tzinfo=timezone.utc)
    item_futur = Item(
        source_id="src",
        guid="futur",
        titre="T",
        date_publication=maintenant + timedelta(days=30),
        langue="fr",
        registre="apprendre",
        url="https://exemple.test/a",
        contenu_brut="",
    )

    health.enregistrer_activite("src", [item_futur], conn, maintenant=maintenant)

    ligne = conn.execute("SELECT dernier_item_vu FROM sante_source WHERE source_id = 'src'").fetchone()
    conn.close()
    assert ligne is None  # l'item futur a été ignoré, rien à enregistrer


def test_enregistrer_activite_retient_le_plus_recent_plausible_parmi_un_lot_mixte(tmp_path):
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    maintenant = datetime(2026, 1, 1, tzinfo=timezone.utc)
    item_plausible = Item(
        source_id="src",
        guid="plausible",
        titre="T",
        date_publication=maintenant - timedelta(days=2),
        langue="fr",
        registre="apprendre",
        url="https://exemple.test/a",
        contenu_brut="",
    )
    item_futur = Item(
        source_id="src",
        guid="futur",
        titre="T",
        date_publication=maintenant + timedelta(days=30),
        langue="fr",
        registre="apprendre",
        url="https://exemple.test/a",
        contenu_brut="",
    )

    health.enregistrer_activite("src", [item_futur, item_plausible], conn, maintenant=maintenant)

    (dernier,) = conn.execute(
        "SELECT dernier_item_vu FROM sante_source WHERE source_id = 'src'"
    ).fetchone()
    conn.close()
    assert datetime.fromisoformat(dernier) == item_plausible.date_publication


# --- evaluer_fraicheur -----------------------------------------------------


def test_evaluer_fraicheur_source_sans_historique_reste_active(tmp_path):
    """Donnée absente ≠ anomalie présumée (même principe que le seuil de signal)."""
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    rapport = health.evaluer_fraicheur([_source("jamais-collectee")], conn, date.today())
    conn.close()
    assert rapport.transitions == {}


def test_evaluer_fraicheur_moins_de_30_jours_reste_active(tmp_path):
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    health.enregistrer_activite("src", [_item(jours_avant=10)], conn)
    rapport = health.evaluer_fraicheur([_source("src")], conn, date.today())
    (etat,) = conn.execute("SELECT etat FROM sante_source WHERE source_id = 'src'").fetchone()
    conn.close()
    assert etat == health.ETAT_ACTIF
    assert rapport.transitions == {}  # déjà active, aucune transition à signaler


def test_evaluer_fraicheur_plus_de_30_jours_passe_suspecte(tmp_path):
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    health.enregistrer_activite("src", [_item(jours_avant=45)], conn)
    rapport = health.evaluer_fraicheur([_source("src")], conn, date.today())
    (etat,) = conn.execute("SELECT etat FROM sante_source WHERE source_id = 'src'").fetchone()
    conn.close()
    assert etat == health.ETAT_SUSPECTE
    assert rapport.transitions == {"src": (health.ETAT_ACTIF, health.ETAT_SUSPECTE)}


def test_evaluer_fraicheur_plus_de_90_jours_passe_en_sommeil(tmp_path):
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    health.enregistrer_activite("src", [_item(jours_avant=100)], conn)
    rapport = health.evaluer_fraicheur([_source("src")], conn, date.today())
    (etat,) = conn.execute("SELECT etat FROM sante_source WHERE source_id = 'src'").fetchone()
    conn.close()
    assert etat == health.ETAT_SOMMEIL
    assert rapport.transitions == {"src": (health.ETAT_ACTIF, health.ETAT_SOMMEIL)}


def test_evaluer_fraicheur_suspecte_redevient_active_si_a_nouveau_fraiche(tmp_path):
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    health.enregistrer_activite("src", [_item(jours_avant=45)], conn)
    health.evaluer_fraicheur([_source("src")], conn, date.today())  # → suspecte

    health.enregistrer_activite("src", [_item(jours_avant=1)], conn)
    rapport = health.evaluer_fraicheur([_source("src")], conn, date.today())

    (etat,) = conn.execute("SELECT etat FROM sante_source WHERE source_id = 'src'").fetchone()
    conn.close()
    assert etat == health.ETAT_ACTIF
    assert rapport.transitions == {"src": (health.ETAT_SUSPECTE, health.ETAT_ACTIF)}


def test_evaluer_fraicheur_degrade_sans_lever_si_la_connexion_echoue(tmp_path):
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    conn.close()
    rapport = health.evaluer_fraicheur([_source("src")], conn, date.today())  # ne lève pas
    assert rapport.transitions == {}


def test_evaluer_fraicheur_isole_une_ligne_corrompue_sans_bloquer_les_autres(tmp_path):
    """Trouvé en revue (Blind Hunter) : sans isolation par source, une
    seule ligne corrompue (`dernier_item_vu` illisible) bloquait
    l'évaluation de **toutes** les sources du lot, chaque semaine,
    indéfiniment — jamais seulement celle qui est réellement en cause."""
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    conn.execute(
        "INSERT INTO sante_source (source_id, dernier_item_vu, etat) "
        "VALUES ('corrompue', 'ceci-n-est-pas-une-date', 'active')"
    )
    health.enregistrer_activite("saine", [_item(jours_avant=45)], conn)

    rapport = health.evaluer_fraicheur([_source("corrompue"), _source("saine")], conn, date.today())

    (etat_saine,) = conn.execute(
        "SELECT etat FROM sante_source WHERE source_id = 'saine'"
    ).fetchone()
    conn.close()
    assert etat_saine == health.ETAT_SUSPECTE  # évaluée malgré la ligne corrompue
    assert rapport.transitions == {"saine": (health.ETAT_ACTIF, health.ETAT_SUSPECTE)}


# --- sources_en_sommeil -----------------------------------------------------


def test_sources_en_sommeil_vide_par_defaut(tmp_path):
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    resultat = health.sources_en_sommeil(conn)
    conn.close()
    assert resultat == set()


def test_sources_en_sommeil_ne_liste_que_l_etat_sommeil(tmp_path):
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    health.enregistrer_activite("actif", [_item(jours_avant=1)], conn)
    health.enregistrer_activite("dodo", [_item(jours_avant=100)], conn)
    health.evaluer_fraicheur([_source("actif"), _source("dodo")], conn, date.today())

    resultat = health.sources_en_sommeil(conn)
    conn.close()
    assert resultat == {"dodo"}


def test_sources_en_sommeil_degrade_sans_lever_si_la_connexion_echoue(tmp_path):
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    conn.close()
    assert health.sources_en_sommeil(conn) == set()  # ne lève pas


# --- RapportSante.resume() --------------------------------------------------


def test_rapport_sante_resume_vide():
    assert "aucun changement" in health.RapportSante().resume()


def test_rapport_sante_resume_liste_les_transitions_triees():
    rapport = health.RapportSante(
        transitions={"b": ("active", "suspecte"), "a": ("suspecte", "en_sommeil")}
    )
    resume = rapport.resume()
    assert "2 changement" in resume
    assert resume.index("a (") < resume.index("b (")
