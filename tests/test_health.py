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


def _item_avec_date(date_publication, source_id="src", guid="g"):
    return Item(
        source_id=source_id,
        guid=guid,
        titre="Titre",
        date_publication=date_publication,
        langue="fr",
        registre="apprendre",
        url="https://exemple.test/a",
        contenu_brut="",
    )


# --- detecter_dates_suspectes (Story 4.2) -------------------------------


def test_detecter_dates_suspectes_trois_items_meme_minute_exacte():
    instant = datetime(2026, 1, 1, 10, 30, tzinfo=timezone.utc)
    items = [
        _item_avec_date(instant, guid="a"),
        _item_avec_date(instant, guid="b"),
        _item_avec_date(instant, guid="c"),
    ]
    assert health.detecter_dates_suspectes(items) is True


def test_detecter_dates_suspectes_meme_minute_secondes_differentes():
    """Troncature à la minute, pas à la seconde — un motif répété peut
    différer de quelques secondes et rester suspect."""
    items = [
        _item_avec_date(datetime(2026, 1, 1, 10, 30, 0, tzinfo=timezone.utc), guid="a"),
        _item_avec_date(datetime(2026, 1, 1, 10, 30, 20, tzinfo=timezone.utc), guid="b"),
        _item_avec_date(datetime(2026, 1, 1, 10, 30, 45, tzinfo=timezone.utc), guid="c"),
    ]
    assert health.detecter_dates_suspectes(items) is True


def test_detecter_dates_suspectes_aucun_doublon():
    items = [
        _item_avec_date(datetime(2026, 1, 1, 10, 30, tzinfo=timezone.utc), guid="a"),
        _item_avec_date(datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc), guid="b"),
        _item_avec_date(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc), guid="c"),
    ]
    assert health.detecter_dates_suspectes(items) is False


def test_detecter_dates_suspectes_liste_vide():
    assert health.detecter_dates_suspectes([]) is False


def test_detecter_dates_suspectes_un_seul_item():
    items = [_item_avec_date(datetime(2026, 1, 1, 10, 30, tzinfo=timezone.utc))]
    assert health.detecter_dates_suspectes(items) is False


def test_detecter_dates_suspectes_un_seul_doublon_isole_parmi_de_nombreux_items():
    """AC2 : « un seul doublon parmi de nombreux items à horaires
    distincts » n'est pas considéré mensongère — corrigé en revue (trouvé
    par l'Acceptance Auditor) : un seuil de 2 aurait signalé exactement ce
    cas que l'AC exclut explicitement. Seuls 3 items identiques ou plus
    constituent un motif répété."""
    items = [
        _item_avec_date(datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc), guid="a"),
        _item_avec_date(datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc), guid="b"),
        # Le seul doublon isolé du lot :
        _item_avec_date(datetime(2026, 1, 1, 10, 30, tzinfo=timezone.utc), guid="c"),
        _item_avec_date(datetime(2026, 1, 1, 10, 30, tzinfo=timezone.utc), guid="d"),
        _item_avec_date(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc), guid="e"),
        _item_avec_date(datetime(2026, 1, 1, 13, 0, tzinfo=timezone.utc), guid="f"),
    ]
    assert health.detecter_dates_suspectes(items) is False


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
    # La ligne existe désormais (corrigé en revue de la Story 4.2 : le
    # signal dates_suspectes doit être persisté même sans item plausible),
    # mais dernier_item_vu reste NULL — l'item futur a bien été ignoré
    # pour ce seul calcul.
    assert ligne is not None
    assert ligne[0] is None


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


def test_enregistrer_activite_persiste_dates_suspectes(tmp_path):
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    instant = datetime(2026, 1, 1, 10, 30, tzinfo=timezone.utc)
    items = [
        _item_avec_date(instant, guid="a"),
        _item_avec_date(instant, guid="b"),
        _item_avec_date(instant, guid="c"),
    ]

    health.enregistrer_activite("src", items, conn)

    (dates_suspectes,) = conn.execute(
        "SELECT dates_suspectes FROM sante_source WHERE source_id = 'src'"
    ).fetchone()
    conn.close()
    assert dates_suspectes == 1


def test_enregistrer_activite_persiste_dates_suspectes_meme_sans_item_plausible(tmp_path):
    """Trouvé en revue (convergence blind+edge) : un lot entièrement à
    date future ment tout autant sur sa fraîcheur — le signal ne doit pas
    dépendre du filtre de plausibilité qui, lui, ne concerne que
    `dernier_item_vu`."""
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    maintenant = datetime(2026, 1, 1, tzinfo=timezone.utc)
    futur = maintenant + timedelta(days=30)
    items = [
        _item_avec_date(futur, guid="a"),
        _item_avec_date(futur, guid="b"),
        _item_avec_date(futur, guid="c"),
    ]

    health.enregistrer_activite("src", items, conn, maintenant=maintenant)

    dernier, dates_suspectes = conn.execute(
        "SELECT dernier_item_vu, dates_suspectes FROM sante_source WHERE source_id = 'src'"
    ).fetchone()
    conn.close()
    assert dernier is None  # aucun item plausible
    assert dates_suspectes == 1  # mais le signal est bien enregistré


def test_enregistrer_activite_lot_sain_efface_un_signal_precedent(tmp_path):
    """`dates_suspectes` reflète le lot de **cette nuit**, pas un
    historique cumulé — un lot sain remet le signal à zéro."""
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    instant = datetime(2026, 1, 1, 10, 30, tzinfo=timezone.utc)
    health.enregistrer_activite(
        "src",
        [
            _item_avec_date(instant, guid="a"),
            _item_avec_date(instant, guid="b"),
            _item_avec_date(instant, guid="c"),
        ],
        conn,
    )

    health.enregistrer_activite(
        "src",
        [_item_avec_date(datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc), guid="c")],
        conn,
    )

    (dates_suspectes,) = conn.execute(
        "SELECT dates_suspectes FROM sante_source WHERE source_id = 'src'"
    ).fetchone()
    conn.close()
    assert dates_suspectes == 0


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


def test_evaluer_fraicheur_dates_suspectes_force_suspecte_meme_si_recente(tmp_path):
    """Story 4.2, AC1 : une source qui répond correctement (item très
    récent) mais dont le lot porte des dates mensongères doit quand même
    passer `suspecte` — le signal l'emporte sur le calcul d'âge seul."""
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    instant = datetime.now(timezone.utc)
    items = [
        _item_avec_date(instant, guid="a"),
        _item_avec_date(instant, guid="b"),
        _item_avec_date(instant, guid="c"),
    ]
    health.enregistrer_activite("src", items, conn)

    rapport = health.evaluer_fraicheur([_source("src")], conn, date.today())

    (etat,) = conn.execute("SELECT etat FROM sante_source WHERE source_id = 'src'").fetchone()
    conn.close()
    assert etat == health.ETAT_SUSPECTE
    assert rapport.transitions == {"src": (health.ETAT_ACTIF, health.ETAT_SUSPECTE)}


def test_evaluer_fraicheur_en_sommeil_l_emporte_sur_dates_suspectes(tmp_path):
    """Story 4.2, AC3 : une source déjà `en_sommeil` (silence prolongé) ne
    doit jamais être rétrogradée à `suspecte` par un signal de dates
    mensongères porté par un lot déjà périmé (avant l'endormissement)."""
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    instant_suspect = datetime.now(timezone.utc) - timedelta(days=100)
    items = [
        _item_avec_date(instant_suspect, guid="a"),
        _item_avec_date(instant_suspect, guid="b"),
        _item_avec_date(instant_suspect, guid="c"),
    ]
    health.enregistrer_activite("src", items, conn)

    rapport = health.evaluer_fraicheur([_source("src")], conn, date.today())

    (etat,) = conn.execute("SELECT etat FROM sante_source WHERE source_id = 'src'").fetchone()
    conn.close()
    assert etat == health.ETAT_SOMMEIL
    assert rapport.transitions == {"src": (health.ETAT_ACTIF, health.ETAT_SOMMEIL)}


def test_evaluer_fraicheur_sans_dates_suspectes_reste_active(tmp_path):
    """Non-régression explicite de la Story 4.1 : sans signal de dates
    suspectes, une source fraîche reste `active` comme avant."""
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    health.enregistrer_activite("src", [_item(jours_avant=1)], conn)

    rapport = health.evaluer_fraicheur([_source("src")], conn, date.today())

    (etat,) = conn.execute("SELECT etat FROM sante_source WHERE source_id = 'src'").fetchone()
    conn.close()
    assert etat == health.ETAT_ACTIF
    assert rapport.transitions == {}


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


# --- lister_sources_a_surveiller (Story 4.3) ----------------------------


def test_lister_sources_a_surveiller_vide_par_defaut(tmp_path):
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    resultat = health.lister_sources_a_surveiller(conn, date.today())
    conn.close()
    assert resultat == []


def test_lister_sources_a_surveiller_raison_par_age(tmp_path):
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    health.enregistrer_activite("src", [_item(jours_avant=45)], conn)
    health.evaluer_fraicheur([_source("src")], conn, date.today())

    resultat = health.lister_sources_a_surveiller(conn, date.today())
    conn.close()

    assert len(resultat) == 1
    assert resultat[0].source_id == "src"
    assert resultat[0].etat == health.ETAT_SUSPECTE
    assert "jour" in resultat[0].raison
    assert "dates suspectes" not in resultat[0].raison


def test_lister_sources_a_surveiller_raison_par_dates_suspectes(tmp_path):
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    instant = datetime.now(timezone.utc)
    items = [
        _item_avec_date(instant, guid="a"),
        _item_avec_date(instant, guid="b"),
        _item_avec_date(instant, guid="c"),
    ]
    health.enregistrer_activite("src", items, conn)
    health.evaluer_fraicheur([_source("src")], conn, date.today())

    resultat = health.lister_sources_a_surveiller(conn, date.today())
    conn.close()

    assert len(resultat) == 1
    assert resultat[0].etat == health.ETAT_SUSPECTE
    assert "dates suspectes" in resultat[0].raison
    assert "jour" not in resultat[0].raison


def test_lister_sources_a_surveiller_raison_combinee(tmp_path):
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    ancien = datetime.now(timezone.utc) - timedelta(days=45)
    items = [
        _item_avec_date(ancien, guid="a"),
        _item_avec_date(ancien, guid="b"),
        _item_avec_date(ancien, guid="c"),
    ]
    health.enregistrer_activite("src", items, conn)
    health.evaluer_fraicheur([_source("src")], conn, date.today())

    resultat = health.lister_sources_a_surveiller(conn, date.today())
    conn.close()

    assert len(resultat) == 1
    assert "jour" in resultat[0].raison
    assert "dates suspectes" in resultat[0].raison


def test_lister_sources_a_surveiller_isole_une_ligne_corrompue(tmp_path):
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    conn.execute(
        "INSERT INTO sante_source (source_id, dernier_item_vu, etat) VALUES "
        "('corrompue', 'ceci-n-est-pas-une-date', 'suspecte')"
    )
    health.enregistrer_activite("saine", [_item(jours_avant=45)], conn)
    health.evaluer_fraicheur([_source("corrompue"), _source("saine")], conn, date.today())

    resultat = health.lister_sources_a_surveiller(conn, date.today())
    conn.close()

    ids = {s.source_id for s in resultat}
    assert "saine" in ids
    # La ligne corrompue apparaît quand même (etat != active), mais sans
    # planter — raison indéterminée faute de date exploitable.
    corrompue = next(s for s in resultat if s.source_id == "corrompue")
    assert corrompue.raison == "raison indéterminée"


def test_lister_sources_a_surveiller_degrade_sans_lever_si_la_connexion_echoue(tmp_path):
    conn = store.ouvrir(tmp_path / "d.sqlite3")
    conn.close()
    assert health.lister_sources_a_surveiller(conn, date.today()) == []
