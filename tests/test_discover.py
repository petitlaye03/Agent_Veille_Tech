"""Tests de la découverte de nouvelles sources (FR-14, Story 4.4) — aucun
appel réseau réel : connecteurs simulés, `aujourdhui`/`maintenant` toujours
injectés explicitement."""

import textwrap
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from veille import discover
from veille.config import SourceConfig
from veille.models import Item

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _source(id_="candidat", type_="rss", url="https://exemple.test/feed"):
    return SourceConfig(id=id_, type=type_, url=url, langue="en", registre="apprendre")


def _candidat(id_="candidat", justification="Une bonne raison."):
    return discover.CandidatSource(source=_source(id_=id_), justification=justification)


def _item(jours_avant=0):
    return Item(
        source_id="candidat",
        guid="g",
        titre="T",
        date_publication=datetime.now(timezone.utc) - timedelta(days=jours_avant),
        langue="en",
        registre="apprendre",
        url="https://exemple.test/a",
        contenu_brut="",
    )


def _ecrire_candidats_yaml(tmp_path, entrees: str) -> Path:
    chemin = tmp_path / "candidats.yaml"
    chemin.write_text(f"candidats:\n{entrees}", encoding="utf-8")
    return chemin


def _ecrire_sources_yaml(tmp_path, ids: list[str]) -> Path:
    chemin = tmp_path / "sources.yaml"
    lignes = "\n".join(
        f"  - id: {id_}\n    type: rss\n    url: https://exemple.test/{id_}\n    langue: en\n    registre: apprendre"
        for id_ in ids
    )
    chemin.write_text(f"sources:\n{lignes}\n" if ids else "sources: []\n", encoding="utf-8")
    return chemin


# --- charger_candidats ----------------------------------------------------


def test_charger_candidats_fichier_absent_degrade_sans_lever(tmp_path):
    assert discover.charger_candidats(tmp_path / "n_existe_pas.yaml") == []


def test_charger_candidats_fichier_malforme_degrade_sans_lever(tmp_path):
    chemin = tmp_path / "candidats.yaml"
    chemin.write_text("ceci: [n'est: pas: du yaml valide\n", encoding="utf-8")
    assert discover.charger_candidats(chemin) == []


def test_charger_candidats_racine_non_mapping_degrade(tmp_path):
    chemin = tmp_path / "candidats.yaml"
    chemin.write_text("- juste\n- une\n- liste\n", encoding="utf-8")
    assert discover.charger_candidats(chemin) == []


def test_charger_candidats_cle_candidats_absente_degrade(tmp_path):
    chemin = tmp_path / "candidats.yaml"
    chemin.write_text("autre_chose: []\n", encoding="utf-8")
    assert discover.charger_candidats(chemin) == []


def test_charger_candidats_ignore_une_entree_invalide_sans_perdre_les_autres(tmp_path):
    chemin = _ecrire_candidats_yaml(
        tmp_path,
        textwrap.dedent(
            """\
              - justification: "Bonne source."
                source:
                  id: bonne-source
                  type: rss
                  url: https://exemple.test/bonne
                  langue: en
                  registre: apprendre
              - justification: "Entrée cassée, sans champ source."
              - justification: "Autre bonne source."
                source:
                  id: autre-bonne-source
                  type: rss
                  url: https://exemple.test/autre
                  langue: fr
                  registre: ce_qui_bouge
            """
        ),
    )

    candidats = discover.charger_candidats(chemin)

    assert [c.source.id for c in candidats] == ["bonne-source", "autre-bonne-source"]


def test_charger_candidats_encodage_invalide_degrade_sans_lever(tmp_path):
    """Trouvé en revue (Acceptance Auditor) : `UnicodeDecodeError` (levée par
    `open(...).read()` avant même `yaml.safe_load`) était absente du tuple
    `except`, contrairement à ce que la docstring promettait déjà
    (« absent/illisible/malformé »)."""
    chemin = tmp_path / "candidats.yaml"
    chemin.write_bytes(b"candidats:\n  - justification: \xff\xfe invalide\n")

    assert discover.charger_candidats(chemin) == []


def test_charger_candidats_justification_non_chaine_est_ignoree(tmp_path):
    """Trouvé en revue (Blind Hunter) : contrairement à `source` (validé par
    `SourceConfig`), une `justification` non-chaîne était silencieusement
    coercée par `str(...)` plutôt que rejetée comme toute autre entrée
    malformée."""
    chemin = _ecrire_candidats_yaml(
        tmp_path,
        textwrap.dedent(
            """\
              - justification: ["ceci", "n'est", "pas", "une", "chaine"]
                source:
                  id: candidat-liste
                  type: rss
                  url: https://exemple.test/liste
                  langue: en
                  registre: apprendre
              - justification: "Bonne source."
                source:
                  id: bonne-source
                  type: rss
                  url: https://exemple.test/bonne
                  langue: en
                  registre: apprendre
            """
        ),
    )

    candidats = discover.charger_candidats(chemin)

    assert [c.source.id for c in candidats] == ["bonne-source"]


def test_charger_candidats_id_duplique_ignore_le_second(tmp_path):
    """Trouvé en revue (Edge Case Hunter) : deux entrées partageant le même
    `id` survivaient toutes les deux dans le pool sans avertissement,
    doublant silencieusement les chances de ce candidat dans la rotation."""
    chemin = _ecrire_candidats_yaml(
        tmp_path,
        textwrap.dedent(
            """\
              - justification: "Première occurrence."
                source:
                  id: candidat-duplique
                  type: rss
                  url: https://exemple.test/premiere
                  langue: en
                  registre: apprendre
              - justification: "Seconde occurrence, même id."
                source:
                  id: candidat-duplique
                  type: rss
                  url: https://exemple.test/seconde
                  langue: en
                  registre: apprendre
            """
        ),
    )

    candidats = discover.charger_candidats(chemin)

    assert len(candidats) == 1
    assert candidats[0].justification == "Première occurrence."


def test_charger_candidats_lit_justification_et_source(tmp_path):
    chemin = _ecrire_candidats_yaml(
        tmp_path,
        textwrap.dedent(
            """\
              - justification: "Une bonne raison précise."
                source:
                  id: candidat-1
                  type: rss
                  url: https://exemple.test/candidat-1
                  langue: en
                  registre: apprendre
            """
        ),
    )

    (candidat,) = discover.charger_candidats(chemin)

    assert candidat.justification == "Une bonne raison précise."
    assert candidat.source.id == "candidat-1"
    assert candidat.source.url == "https://exemple.test/candidat-1"


# --- verifier_candidat -----------------------------------------------------


def test_verifier_candidat_type_inconnu_est_faux(monkeypatch):
    candidat = _candidat()
    monkeypatch.setattr(discover, "CONNECTORS", {})
    assert discover.verifier_candidat(candidat) is False


def test_verifier_candidat_connecteur_qui_leve_degrade_en_faux(monkeypatch):
    candidat = _candidat()

    def _fetch_qui_leve(source_config):
        raise RuntimeError("panne réseau simulée")

    monkeypatch.setattr(discover, "CONNECTORS", {"rss": _fetch_qui_leve})

    assert discover.verifier_candidat(candidat) is False


def test_verifier_candidat_liste_vide_est_faux(monkeypatch):
    candidat = _candidat()
    monkeypatch.setattr(discover, "CONNECTORS", {"rss": lambda source_config: []})

    assert discover.verifier_candidat(candidat) is False


def test_verifier_candidat_item_recent_est_vrai(monkeypatch):
    candidat = _candidat()
    monkeypatch.setattr(discover, "CONNECTORS", {"rss": lambda source_config: [_item(jours_avant=1)]})

    assert discover.verifier_candidat(candidat) is True


def test_verifier_candidat_item_trop_vieux_est_faux(monkeypatch):
    candidat = _candidat()
    monkeypatch.setattr(discover, "CONNECTORS", {"rss": lambda source_config: [_item(jours_avant=45)]})

    assert discover.verifier_candidat(candidat) is False


def test_verifier_candidat_prend_le_plus_recent_du_lot(monkeypatch):
    candidat = _candidat()
    items = [_item(jours_avant=45), _item(jours_avant=1)]
    monkeypatch.setattr(discover, "CONNECTORS", {"rss": lambda source_config: items})

    assert discover.verifier_candidat(candidat) is True


def test_verifier_candidat_seuil_exact_est_vrai(monkeypatch):
    """`age_jours <= SEUIL_RECENCE_JOURS` — la limite exacte est incluse."""
    candidat = _candidat()
    maintenant = datetime(2026, 2, 1, tzinfo=timezone.utc)
    item_pile_au_seuil = Item(
        source_id="candidat",
        guid="g",
        titre="T",
        date_publication=maintenant - timedelta(days=discover.SEUIL_RECENCE_JOURS),
        langue="en",
        registre="apprendre",
        url="https://exemple.test/a",
        contenu_brut="",
    )
    monkeypatch.setattr(discover, "CONNECTORS", {"rss": lambda source_config: [item_pile_au_seuil]})

    assert discover.verifier_candidat(candidat, maintenant=maintenant) is True


def test_verifier_candidat_item_date_dans_le_futur_est_faux(monkeypatch):
    """Trouvé en revue (Blind Hunter) : un item daté dans le futur par
    rapport à `maintenant` (horloge décalée côté source, ou repli
    `datetime.now()` d'un connecteur sur une date illisible) produisait un
    `age_jours` négatif — toujours `<= SEUIL_RECENCE_JOURS`, donc accepté
    comme « frais » sans jamais être questionné."""
    candidat = _candidat()
    maintenant = datetime(2026, 2, 1, tzinfo=timezone.utc)
    item_futur = Item(
        source_id="candidat",
        guid="g",
        titre="T",
        date_publication=maintenant + timedelta(days=5),
        langue="en",
        registre="apprendre",
        url="https://exemple.test/a",
        contenu_brut="",
    )
    monkeypatch.setattr(discover, "CONNECTORS", {"rss": lambda source_config: [item_futur]})

    assert discover.verifier_candidat(candidat, maintenant=maintenant) is False


# --- proposer_source --------------------------------------------------


def test_proposer_source_pool_vide_renvoie_none(tmp_path):
    candidats_path = _ecrire_candidats_yaml(tmp_path, "")
    sources_path = _ecrire_sources_yaml(tmp_path, [])

    resultat = discover.proposer_source(candidats_path=candidats_path, sources_path=sources_path)

    assert resultat is None


def test_proposer_source_exclut_un_candidat_deja_adopte(tmp_path, monkeypatch):
    candidats_path = _ecrire_candidats_yaml(
        tmp_path,
        textwrap.dedent(
            """\
              - justification: "x"
                source:
                  id: deja-adopte
                  type: rss
                  url: https://exemple.test/deja-adopte
                  langue: en
                  registre: apprendre
            """
        ),
    )
    sources_path = _ecrire_sources_yaml(tmp_path, ["deja-adopte"])
    monkeypatch.setattr(discover, "CONNECTORS", {"rss": lambda source_config: [_item(jours_avant=1)]})

    resultat = discover.proposer_source(candidats_path=candidats_path, sources_path=sources_path)

    assert resultat is None  # seul candidat du pool, déjà adopté


def test_proposer_source_renvoie_le_candidat_qui_passe_la_verification(tmp_path, monkeypatch):
    candidats_path = _ecrire_candidats_yaml(
        tmp_path,
        textwrap.dedent(
            """\
              - justification: "x"
                source:
                  id: candidat-mort
                  type: rss
                  url: https://exemple.test/mort
                  langue: en
                  registre: apprendre
              - justification: "y"
                source:
                  id: candidat-vivant
                  type: rss
                  url: https://exemple.test/vivant
                  langue: en
                  registre: apprendre
            """
        ),
    )
    sources_path = _ecrire_sources_yaml(tmp_path, [])

    def _fetch(source_config):
        if source_config.id == "candidat-mort":
            raise RuntimeError("panne simulée")
        return [_item(jours_avant=1)]

    monkeypatch.setattr(discover, "CONNECTORS", {"rss": _fetch})

    resultat = discover.proposer_source(
        candidats_path=candidats_path,
        sources_path=sources_path,
        # Trouvé en revue (Blind Hunter) : le commentaire d'origine affirmait
        # à tort « semaine ISO 1 » — `date(2026, 1, 5).isocalendar().week`
        # vaut réellement 2 (vérifié, jamais deviné à la main). `2 % 2 == 0`
        # place bien le départ sur `candidat-mort` (index 0) en premier.
        aujourdhui=date(2026, 1, 5),  # semaine ISO 2 → départ sur candidat-mort (index 0) en premier
    )

    assert resultat is not None
    assert resultat.source.id == "candidat-vivant"


def test_proposer_source_pool_entierement_mort_renvoie_none(tmp_path, monkeypatch):
    candidats_path = _ecrire_candidats_yaml(
        tmp_path,
        textwrap.dedent(
            """\
              - justification: "x"
                source:
                  id: candidat-1
                  type: rss
                  url: https://exemple.test/1
                  langue: en
                  registre: apprendre
            """
        ),
    )
    sources_path = _ecrire_sources_yaml(tmp_path, [])
    monkeypatch.setattr(discover, "CONNECTORS", {"rss": lambda source_config: []})

    resultat = discover.proposer_source(candidats_path=candidats_path, sources_path=sources_path)

    assert resultat is None


def test_proposer_source_rotation_change_selon_la_semaine_iso(tmp_path, monkeypatch):
    candidats_path = _ecrire_candidats_yaml(
        tmp_path,
        textwrap.dedent(
            """\
              - justification: "x"
                source:
                  id: candidat-a
                  type: rss
                  url: https://exemple.test/a
                  langue: en
                  registre: apprendre
              - justification: "y"
                source:
                  id: candidat-b
                  type: rss
                  url: https://exemple.test/b
                  langue: en
                  registre: apprendre
            """
        ),
    )
    sources_path = _ecrire_sources_yaml(tmp_path, [])
    monkeypatch.setattr(discover, "CONNECTORS", {"rss": lambda source_config: [_item(jours_avant=1)]})

    # Deux dates dont les numéros de semaine ISO ont une parité différente.
    resultat_semaine_paire = discover.proposer_source(
        candidats_path=candidats_path, sources_path=sources_path, aujourdhui=date(2026, 1, 5)
    )
    resultat_semaine_impaire = discover.proposer_source(
        candidats_path=candidats_path, sources_path=sources_path, aujourdhui=date(2026, 1, 12)
    )

    assert resultat_semaine_paire.source.id != resultat_semaine_impaire.source.id


def test_proposer_source_exclut_aussi_par_url_quand_l_id_differe(tmp_path, monkeypatch):
    """Trouvé en revue (Edge Case Hunter) : un candidat adopté sous un `id`
    différent de celui de `config/candidats.yaml` (rien ne l'empêche)
    continuerait sinon d'être « redécouvert » indéfiniment — la même URL de
    flux, elle, ne ment pas."""
    candidats_path = _ecrire_candidats_yaml(
        tmp_path,
        textwrap.dedent(
            """\
              - justification: "x"
                source:
                  id: candidat-x
                  type: rss
                  url: https://exemple.test/meme-flux
                  langue: en
                  registre: apprendre
            """
        ),
    )
    sources_path = tmp_path / "sources.yaml"
    sources_path.write_text(
        textwrap.dedent(
            """\
            sources:
              - id: adopte-sous-un-autre-nom
                type: rss
                url: https://exemple.test/meme-flux
                langue: en
                registre: apprendre
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(discover, "CONNECTORS", {"rss": lambda source_config: [_item(jours_avant=1)]})

    resultat = discover.proposer_source(candidats_path=candidats_path, sources_path=sources_path)

    assert resultat is None  # seul candidat du pool, déjà adopté (même URL, id différent)


def test_proposer_source_rotation_stable_si_adoption_d_un_autre_candidat(tmp_path, monkeypatch):
    """Trouvé en revue (Blind Hunter, constat le plus sérieux de cette
    revue) : la rotation ne doit pas se recalculer sur la taille du pool
    *après* exclusion — sinon l'adoption d'un candidat quelconque, même
    sans rapport avec celui actuellement proposé, pouvait silencieusement
    faire changer le candidat proposé en cours de semaine, contredisant
    l'invariant documenté (« reproduit le même candidat tant qu'il reste
    vérifié actif »)."""
    candidats_path = _ecrire_candidats_yaml(
        tmp_path,
        textwrap.dedent(
            """\
              - justification: "a"
                source:
                  id: cand-a
                  type: rss
                  url: https://exemple.test/a
                  langue: en
                  registre: apprendre
              - justification: "b"
                source:
                  id: cand-b
                  type: rss
                  url: https://exemple.test/b
                  langue: en
                  registre: apprendre
              - justification: "c"
                source:
                  id: cand-c
                  type: rss
                  url: https://exemple.test/c
                  langue: en
                  registre: apprendre
            """
        ),
    )
    monkeypatch.setattr(discover, "CONNECTORS", {"rss": lambda source_config: [_item(jours_avant=1)]})

    # Une date dont le numéro de semaine ISO diverge selon qu'on le calcule
    # modulo 3 (pool complet) ou modulo 2 (pool après exclusion d'un
    # candidat) — condition nécessaire pour que le bug corrigé ici soit
    # observable (calculé, jamais une semaine ISO devinée à la main : voir
    # la leçon de revue de la Story 4.4 sur ce point précis).
    aujourdhui = next(
        d
        for d in (date(2026, 1, 1) + timedelta(days=i) for i in range(400))
        if d.isocalendar().week % 3 != d.isocalendar().week % 2
    )

    sources_path_vide = _ecrire_sources_yaml(tmp_path, [])
    candidat_avant = discover.proposer_source(
        candidats_path=candidats_path, sources_path=sources_path_vide, aujourdhui=aujourdhui
    )
    assert candidat_avant is not None

    # Un candidat *sans rapport* avec celui proposé est adopté en cours de semaine.
    autre_id = next(id_ for id_ in ("cand-a", "cand-b", "cand-c") if id_ != candidat_avant.source.id)
    sources_path_apres = _ecrire_sources_yaml(tmp_path, [autre_id])

    candidat_apres = discover.proposer_source(
        candidats_path=candidats_path, sources_path=sources_path_apres, aujourdhui=aujourdhui
    )

    assert candidat_apres is not None
    assert candidat_apres.source.id == candidat_avant.source.id


def test_proposer_source_degrade_sans_lever_si_sources_yaml_illisible(tmp_path, monkeypatch):
    """`config.load_sources` lève sur un fichier absent (l'isolation est la
    responsabilité de l'appelant, pas la sienne — même contrat que pour
    `collect.collecter()`) : `proposer_source` isole ça à son tour, dégrade
    en `None` (rien à proposer cette semaine) plutôt que de laisser
    l'exception remonter."""
    candidats_path = _ecrire_candidats_yaml(
        tmp_path,
        textwrap.dedent(
            """\
              - justification: "x"
                source:
                  id: candidat-1
                  type: rss
                  url: https://exemple.test/1
                  langue: en
                  registre: apprendre
            """
        ),
    )
    monkeypatch.setattr(discover, "CONNECTORS", {"rss": lambda source_config: [_item(jours_avant=1)]})

    resultat = discover.proposer_source(
        candidats_path=candidats_path,
        sources_path=tmp_path / "n_existe_pas.yaml",
    )

    assert resultat is None
