"""Tests du filtrage par signal et du scoring par profil (Story 1.4)."""

import textwrap
from datetime import datetime, timezone

from veille.config import SourceConfig
from veille.filter import (
    ItemScore,
    Ponderations,
    Quotas,
    Score,
    charger_ponderations,
    charger_quotas,
    classer,
    filtrer_par_signal,
    rapport_classement,
    rapport_quotas,
    repartir_par_quotas,
    scorer,
)
from veille.models import Item
from veille.profil import Profil


def _item(source_id="src", signal=None, **overrides):
    defaults = dict(
        source_id=source_id,
        guid=f"{source_id}-guid",
        titre="Titre",
        date_publication=datetime(2026, 8, 1, tzinfo=timezone.utc),
        langue="en",
        registre="apprendre",
        url=f"https://exemple.invalid/{source_id}",
        contenu_brut="Contenu.",
        signal=signal,
    )
    defaults.update(overrides)
    return Item(**defaults)


def _source(id="src", seuil_signal=None):
    return SourceConfig(
        id=id, type="json", url="https://exemple.invalid", langue="en",
        registre="apprendre", seuil_signal=seuil_signal,
    )


# --- Task 2bis : filtrage par seuil de signal --------------------------


def test_un_item_sous_le_seuil_est_ecarte():
    sources = {"hf": _source("hf", seuil_signal=15)}
    items = [_item("hf", signal=20), _item("hf", signal=5)]

    retenus, rapport = filtrer_par_signal(items, sources)

    assert [i.signal for i in retenus] == [20]
    assert rapport.ecartes_par_source == {"hf": 1}


def test_une_source_sans_seuil_conserve_tous_ses_items():
    """AC2 : le filtrage par signal est optionnel, jamais implicite."""
    sources = {"openai": _source("openai", seuil_signal=None)}
    items = [_item("openai", signal=0), _item("openai", signal=None)]

    retenus, rapport = filtrer_par_signal(items, sources)

    assert len(retenus) == 2
    assert rapport.total_ecartes == 0


def test_un_item_sans_signal_face_a_un_seuil_declare_est_conserve():
    """L'absence de donnée n'est pas une insuffisance : l'écarter perdrait
    silencieusement du contenu légitime."""
    sources = {"hf": _source("hf", seuil_signal=15)}
    items = [_item("hf", signal=None)]

    retenus, rapport = filtrer_par_signal(items, sources)

    assert retenus == items
    assert rapport.total_ecartes == 0


def test_un_item_au_seuil_exact_est_conserve():
    sources = {"hf": _source("hf", seuil_signal=15)}
    items = [_item("hf", signal=15)]

    retenus, _ = filtrer_par_signal(items, sources)

    assert retenus == items


def test_source_inconnue_du_dict_conserve_l_item():
    """Un item dont la source n'est plus dans la config (cas limite) ne
    doit jamais être perdu silencieusement par le filtrage de signal."""
    items = [_item("source-disparue", signal=1)]

    retenus, rapport = filtrer_par_signal(items, sources={})

    assert retenus == items
    assert rapport.total_ecartes == 0


# --- Task 3 : scorer un item --------------------------------------------


def test_item_touchant_un_theme_prioritaire_marque_positivement():
    profil = Profil(prioritaire=("RAG",))
    item = _item(titre="Nouveautés en RAG cette semaine")

    score = scorer(item, profil)

    assert score.valeur > 0


def test_item_de_bruit_est_fortement_penalise():
    profil = Profil(bruit=("crypto",))
    item = _item(titre="Une nouvelle crypto explose")

    score = scorer(item, profil)

    assert score.valeur < 0


def test_item_generique_reste_neutre():
    profil = Profil(prioritaire=("RAG",), bruit=("crypto",))
    item = _item(titre="Un sujet qui ne touche à rien de déclaré")

    score = scorer(item, profil)

    assert score.valeur == 0


def test_item_prioritaire_est_mieux_note_qu_un_item_generique():
    """AC4 : un item touchant un thème prioritaire devant un item générique."""
    profil = Profil(prioritaire=("RAG",))
    prioritaire = scorer(_item(titre="Un article sur le RAG"), profil)
    generique = scorer(_item(titre="Un article sur autre chose"), profil)

    assert prioritaire.valeur > generique.valeur


def test_cumul_de_plusieurs_categories_pour_le_meme_item():
    profil = Profil(prioritaire=("RAG",), secondaire=("Python",))
    item = _item(titre="RAG", contenu_brut="Un nouveau framework Python pour le RAG")

    score = scorer(item, profil)
    score_prioritaire_seul = scorer(_item(titre="RAG"), Profil(prioritaire=("RAG",)))

    assert score.valeur > score_prioritaire_seul.valeur


def test_correspondance_insensible_a_la_casse_et_aux_accents():
    profil = Profil(prioritaire=("évaluation",))
    item = _item(titre="EVALUATION des modèles")

    score = scorer(item, profil)

    assert score.valeur > 0


def test_correspondance_sur_mot_entier_evite_les_faux_positifs():
    """Piège documenté dans les Dev Notes : `ia` ne doit pas matcher `media`,
    ni `rag` matcher `fragment`."""
    profil = Profil(prioritaire=("ia", "rag"))
    item = _item(titre="Un fragment de media social")

    score = scorer(item, profil)

    assert score.valeur == 0


def test_mot_cle_multi_mots_recherche_comme_sequence():
    profil = Profil(prioritaire=("hybrid search",))
    correspond = scorer(_item(contenu_brut="Une avancée en hybrid search notable"), profil)
    ne_correspond_pas = scorer(
        _item(contenu_brut="Un moteur hybrid, une recherche search séparée"), profil
    )

    assert correspond.valeur > 0
    assert ne_correspond_pas.valeur == 0


def test_ponderations_par_defaut_utilisees_si_non_fournies():
    profil = Profil(prioritaire=("RAG",))

    score = scorer(_item(titre="RAG"), profil)

    assert score.valeur == Ponderations().prioritaire


# --- Règles de cumul tranchées en revue (2026-08-28) --------------------


def test_un_theme_present_dans_deux_categories_ne_compte_qu_une_fois():
    """Régression : `retrieval` en prioritaire ET signal_fort valait 10+15=25
    pour un seul thème, rendant l'édition du profil imprévisible."""
    profil = Profil(prioritaire=("retrieval",), signal_fort=("retrieval",))

    score = scorer(_item(titre="Un article sur le retrieval"), profil)

    assert score.valeur == Ponderations().signal_fort  # le poids le plus fort, une seule fois


def test_entre_bonus_et_penalite_le_signal_le_plus_fort_tranche():
    """Un profil contradictoire (même terme prioritaire et bruit) doit
    retenir la catégorie qui pèse le plus lourd, pas les additionner."""
    profil = Profil(prioritaire=("agents",), bruit=("agents",))

    score = scorer(_item(titre="agents"), profil)

    assert score.valeur == Ponderations().bruit


def test_les_mots_cles_suivants_d_une_categorie_comptent_de_moins_en_moins():
    """AC4 (intention) : empiler des mots-clés génériques ne doit pas battre
    un item en plein cœur de cible."""
    profil = Profil(prioritaire=("cloud", "infrastructure", "monitoring"))
    p = Ponderations()

    score = scorer(_item(titre="Cloud infrastructure monitoring at Netflix"), profil)

    attendu = p.prioritaire * (1 + 0.5 + 0.25)
    assert score.valeur == attendu
    assert score.valeur < p.prioritaire * 3  # la somme brute d'avant


def test_trois_mots_cles_generiques_ne_battent_pas_le_coeur_de_cible():
    profil = Profil(
        prioritaire=("cloud", "infrastructure", "monitoring", "RAG"),
        signal_fort=("retrieval",),
    )
    generique = scorer(_item(titre="Cloud infrastructure monitoring at Netflix"), profil)
    coeur = scorer(_item(titre="RAG retrieval at scale"), profil)

    assert coeur.valeur > generique.valeur


# --- Correspondance : ponctuation et singulier/pluriel ------------------


def test_un_mot_cle_borde_de_ponctuation_matche_au_moins_son_propre_texte():
    """Régression : `\\b` ne peut s'ancrer que contre un caractère de mot, si
    bien qu'un mot-clé bordé de ponctuation ne matchait même pas son propre
    texte littéral — il était inerte en toutes circonstances.

    La vraie défense est en amont (le parseur retire la ponctuation de
    bordure, cf. `test_profil.py`) ; celle-ci est la défense de profondeur."""
    profil = Profil(prioritaire=("Qwen…",))

    assert scorer(_item(titre="Le modèle Qwen… vient de sortir"), profil).valeur > 0


def test_un_mot_cle_au_pluriel_trouve_le_singulier():
    """Le profil est rédigé au pluriel, les titres d'articles sont souvent
    au singulier."""
    profil = Profil(prioritaire=("agents",))

    assert scorer(_item(titre="An AI agent that plans"), profil).valeur > 0
    assert scorer(_item(titre="AI agents that plan"), profil).valeur > 0


def test_un_mot_cle_au_singulier_trouve_le_pluriel():
    profil = Profil(bruit=("smartphone",))

    assert scorer(_item(titre="New smartphones released"), profil).valeur < 0


def test_la_tolerance_au_pluriel_ne_reintroduit_pas_de_faux_positifs():
    """Le `s?` ne doit pas rouvrir le piège que les Dev Notes écartaient."""
    profil = Profil(prioritaire=("rag", "ia"))

    assert scorer(_item(titre="Un fragment de media social"), profil).valeur == 0
    assert scorer(_item(titre="Une agence de strategie"), profil).valeur == 0


# --- Chargement des pondérations (config/scoring.yaml) ------------------


def test_charger_ponderations_absent_retourne_les_valeurs_par_defaut(tmp_path):
    ponderations = charger_ponderations(tmp_path / "inexistant.yaml")

    assert ponderations == Ponderations()


def test_charger_ponderations_lit_le_fichier_declare(tmp_path):
    chemin = tmp_path / "scoring.yaml"
    chemin.write_text(
        textwrap.dedent(
            """
            ponderations:
              prioritaire: 100
              bruit: -50
            seuil_bruit: -10
            """
        ),
        encoding="utf-8",
    )

    ponderations = charger_ponderations(chemin)

    assert ponderations.prioritaire == 100
    assert ponderations.bruit == -50
    assert ponderations.seuil_bruit == -10
    # Les catégories non déclarées gardent leur valeur par défaut.
    assert ponderations.secondaire == Ponderations().secondaire


def test_charger_ponderations_fichier_malforme_retourne_les_valeurs_par_defaut(tmp_path):
    chemin = tmp_path / "scoring.yaml"
    chemin.write_text("- ceci est une liste, pas un mapping\n", encoding="utf-8")

    assert charger_ponderations(chemin) == Ponderations()


# --- Robustesse du chargement des pondérations (revue 2026-08-28) --------


def test_charger_ponderations_ne_leve_pas_sur_un_fichier_non_utf8(tmp_path):
    """Régression : `UnicodeDecodeError` n'était pas attrapé, et cette
    fonction s'exécute hors de l'isolation de panne — le run entier était
    perdu parce qu'un éditeur avait réenregistré le fichier en latin-1."""
    chemin = tmp_path / "scoring.yaml"
    chemin.write_bytes("ponderations:\n  prioritaire: 10  # pondérations\n".encode("latin-1"))

    assert charger_ponderations(chemin) == Ponderations()


def test_une_ponderation_nan_retombe_sur_son_defaut(tmp_path):
    """Toute comparaison à `nan` est fausse : un `seuil_bruit` à `nan`
    viderait le digest en silence."""
    chemin = tmp_path / "scoring.yaml"
    chemin.write_text("seuil_bruit: .nan\n", encoding="utf-8")

    assert charger_ponderations(chemin).seuil_bruit == Ponderations().seuil_bruit


def test_une_ponderation_booleenne_retombe_sur_son_defaut(tmp_path):
    """`prioritaire: yes` vaut `True` en YAML : `float(True)` donnerait un
    poids de 1.0 silencieux au lieu du repli documenté."""
    chemin = tmp_path / "scoring.yaml"
    chemin.write_text("ponderations:\n  prioritaire: yes\n", encoding="utf-8")

    assert charger_ponderations(chemin).prioritaire == Ponderations().prioritaire


def test_une_ponderation_invalide_ne_fait_pas_perdre_les_autres(tmp_path):
    """Le repli est par valeur, pas global : une faute de frappe isolée ne
    doit pas annuler les réglages voisins."""
    chemin = tmp_path / "scoring.yaml"
    chemin.write_text(
        "ponderations:\n  prioritaire: beaucoup\n  bruit: -99\n", encoding="utf-8"
    )

    ponderations = charger_ponderations(chemin)

    assert ponderations.prioritaire == Ponderations().prioritaire  # replié
    assert ponderations.bruit == -99  # conservé


# --- Task 4 : classer et écarter le bruit -------------------------------


def test_un_item_prioritaire_precede_un_item_generique():
    """AC4."""
    profil = Profil(prioritaire=("RAG",))
    prioritaire = _item("a", titre="Un article sur le RAG")
    generique = _item("b", titre="Un article sur autre chose")

    classement = classer([generique, prioritaire], profil)

    assert [is_.item for is_ in classement] == [prioritaire, generique]


def test_un_item_de_bruit_est_ecarte_pas_seulement_retrograde():
    """AC5 : le bruit disparaît, il ne descend pas seulement au classement."""
    profil = Profil(bruit=("crypto",))
    bruit = _item("a", titre="Une nouvelle crypto")
    neutre = _item("b", titre="Un article neutre")

    classement = classer([bruit, neutre], profil)

    assert [is_.item for is_ in classement] == [neutre]


def test_le_departage_a_score_egal_est_stable():
    """Leçon Story 1.3 : pas d'ordre aléatoire à score égal."""
    profil = Profil()  # aucun mot-clé : tous les items restent à 0
    items = [_item(f"src-{i}", titre=f"Item {i}") for i in range(5)]

    classement = classer(items, profil)

    assert [is_.item for is_ in classement] == items


def test_classer_utilise_les_ponderations_fournies():
    profil = Profil(bruit=("crypto",))
    item = _item(titre="Une nouvelle crypto")

    # Avec un seuil de bruit très permissif, l'item n'est pas écarté.
    classement = classer([item], profil, Ponderations(seuil_bruit=-1000))

    assert [is_.item for is_ in classement] == [item]


# --- Compte-rendu du classement (Task 5, AC7) ---------------------------


def test_rapport_classement_compte_les_ecartes_par_source():
    profil = Profil(bruit=("crypto",))
    items = [
        _item("src-a", titre="Une nouvelle crypto"),
        _item("src-a", titre="Neutre"),
        _item("src-b", titre="Encore une crypto qui explose"),
    ]

    classement = classer(items, profil)
    rapport = rapport_classement(items, classement)

    assert rapport.ecartes_par_source == {"src-a": 1, "src-b": 1}
    assert rapport.total_ecartes == 2


def test_rapport_classement_sans_ecarte_est_vide():
    profil = Profil()
    items = [_item("src-a", titre="Neutre")]

    classement = classer(items, profil)
    rapport = rapport_classement(items, classement)

    assert rapport.total_ecartes == 0


def test_le_rapport_de_signal_nomme_les_sources_ecartees():
    """AC7 : rendre compte **par source**, pas seulement en total — sans quoi
    on ne sait pas laquelle un seuil trop haut a vidée."""
    sources = {"hf": _source("hf", seuil_signal=15), "ax": _source("ax", seuil_signal=15)}
    items = [_item("hf", signal=1), _item("hf", signal=2), _item("ax", signal=3)]

    _, rapport = filtrer_par_signal(items, sources)

    assert "hf (-2)" in rapport.resume()
    assert "ax (-1)" in rapport.resume()


def test_le_rapport_de_classement_nomme_les_sources_ecartees():
    profil = Profil(bruit=("crypto",))
    items = [_item("src-a", titre="crypto"), _item("src-b", titre="crypto")]

    classement = classer(items, profil)
    resume = rapport_classement(items, classement).resume()

    assert "src-a (-1)" in resume
    assert "src-b (-1)" in resume


def test_rapport_classement_expose_les_scores_retenus():
    profil = Profil(prioritaire=("RAG",))
    items = [_item("src-a", titre="RAG"), _item("src-a", titre="Neutre")]

    classement = classer(items, profil)
    rapport = rapport_classement(items, classement)

    assert set(rapport.scores_retenus) == {Ponderations().prioritaire, 0.0}


# --- Story 1.5 : Task 1 — chargement des quotas -------------------------


def test_les_valeurs_par_defaut_des_quotas_correspondent_a_la_cible_du_prd():
    """Assertion en dur, volontairement : comparer à `Quotas()` ne détecterait
    pas une neutralisation des défauts (les deux membres dériveraient
    ensemble). `conftest.py` fournit toujours un fichier de quotas explicite
    aux tests, donc ces valeurs par défaut ne sont exercées que par un
    fichier absent en production réelle — elles doivent rester correctes."""
    quotas = Quotas()

    assert quotas.apprendre == 3
    assert quotas.ce_qui_bouge == 3
    assert quotas.pour_le_metier == 2


def test_charger_quotas_absent_retourne_les_valeurs_par_defaut(tmp_path):
    assert charger_quotas(tmp_path / "inexistant.yaml") == Quotas()


def test_charger_quotas_lit_le_fichier_declare(tmp_path):
    chemin = tmp_path / "quotas.yaml"
    chemin.write_text(
        textwrap.dedent(
            """
            quotas:
              apprendre: 5
              pour_le_metier: 1
            """
        ),
        encoding="utf-8",
    )

    quotas = charger_quotas(chemin)

    assert quotas.apprendre == 5
    assert quotas.pour_le_metier == 1
    # Non déclaré : garde son défaut.
    assert quotas.ce_qui_bouge == Quotas().ce_qui_bouge


def test_charger_quotas_fichier_malforme_retourne_les_valeurs_par_defaut(tmp_path):
    chemin = tmp_path / "quotas.yaml"
    chemin.write_text("- ceci est une liste, pas un mapping\n", encoding="utf-8")

    assert charger_quotas(chemin) == Quotas()


def test_charger_quotas_ne_leve_pas_sur_un_fichier_non_utf8(tmp_path):
    chemin = tmp_path / "quotas.yaml"
    chemin.write_bytes("quotas:\n  apprendre: 3  # décompte\n".encode("latin-1"))

    assert charger_quotas(chemin) == Quotas()


def test_un_quota_non_entier_retombe_sur_son_defaut_sans_affecter_les_autres(tmp_path):
    """Repli par valeur, pas global (leçon Story 1.4)."""
    chemin = tmp_path / "quotas.yaml"
    chemin.write_text(
        "quotas:\n  apprendre: beaucoup\n  pour_le_metier: 1\n", encoding="utf-8"
    )

    quotas = charger_quotas(chemin)

    assert quotas.apprendre == Quotas().apprendre  # replié
    assert quotas.pour_le_metier == 1  # conservé


def test_un_quota_booleen_retombe_sur_son_defaut(tmp_path):
    """`apprendre: yes` vaut `True` en YAML : ne doit pas donner un quota de 1."""
    chemin = tmp_path / "quotas.yaml"
    chemin.write_text("quotas:\n  apprendre: yes\n", encoding="utf-8")

    assert charger_quotas(chemin).apprendre == Quotas().apprendre


def test_un_quota_negatif_retombe_sur_son_defaut(tmp_path):
    chemin = tmp_path / "quotas.yaml"
    chemin.write_text("quotas:\n  apprendre: -1\n", encoding="utf-8")

    assert charger_quotas(chemin).apprendre == Quotas().apprendre


def test_un_quota_non_entier_flottant_retombe_sur_son_defaut(tmp_path):
    chemin = tmp_path / "quotas.yaml"
    chemin.write_text("quotas:\n  apprendre: 2.5\n", encoding="utf-8")

    assert charger_quotas(chemin).apprendre == Quotas().apprendre


# --- Story 1.5 : Task 2 — répartition par quotas -------------------------


def _is_(item, score=0.0):
    return ItemScore(item=item, score=Score(valeur=score))


def test_le_quota_est_respecte_par_registre():
    quotas = Quotas(apprendre=2, ce_qui_bouge=1, pour_le_metier=1)
    classement = [
        _is_(_item("a", registre="apprendre"), 30),
        _is_(_item("b", registre="apprendre"), 20),
        _is_(_item("c", registre="apprendre"), 10),  # au-delà du quota
        _is_(_item("d", registre="ce_qui_bouge"), 25),
        _is_(_item("e", registre="ce_qui_bouge"), 5),  # au-delà du quota
    ]

    repartition = repartir_par_quotas(classement, quotas)

    registres_retenus = [is_.item.registre for is_ in repartition]
    assert registres_retenus.count("apprendre") == 2
    assert registres_retenus.count("ce_qui_bouge") == 1


def test_un_jour_creux_n_est_jamais_rempli_artificiellement():
    """AC3 : moins d'items que le quota affiche moins d'entrées."""
    quotas = Quotas(apprendre=3, ce_qui_bouge=3, pour_le_metier=2)
    classement = [_is_(_item("a", registre="apprendre"), 10)]

    repartition = repartir_par_quotas(classement, quotas)

    assert len(repartition) == 1


def test_l_ordre_par_score_est_preserve_a_l_interieur_d_un_registre():
    """AC2 : jamais retrié — l'ordre de `classer()` fait foi."""
    quotas = Quotas(apprendre=5, ce_qui_bouge=5, pour_le_metier=5)
    classement = [
        _is_(_item("a", registre="apprendre"), 30),
        _is_(_item("b", registre="apprendre"), 20),
        _is_(_item("c", registre="apprendre"), 10),
    ]

    repartition = repartir_par_quotas(classement, quotas)

    assert [is_.item.source_id for is_ in repartition] == ["a", "b", "c"]


def test_le_quota_ne_retient_que_les_mieux_scores_du_registre():
    """Le quota coupe après les N meilleurs scores du registre, pas les N premiers arrivés."""
    quotas = Quotas(apprendre=1, ce_qui_bouge=5, pour_le_metier=5)
    classement = [
        _is_(_item("a", registre="apprendre"), 30),
        _is_(_item("b", registre="apprendre"), 20),
    ]

    repartition = repartir_par_quotas(classement, quotas)

    assert [is_.item.source_id for is_ in repartition] == ["a"]


def test_un_registre_inconnu_de_quotas_est_conserve_sans_limite(caplog):
    """AC6 : l'absence de réglage n'est pas une insuffisance de contenu."""
    quotas = Quotas(apprendre=1, ce_qui_bouge=1, pour_le_metier=1)
    classement = [
        _is_(_item("a", registre="registre-invente"), 30),
        _is_(_item("b", registre="registre-invente"), 20),
        _is_(_item("c", registre="registre-invente"), 10),
    ]

    with caplog.at_level("WARNING"):
        repartition = repartir_par_quotas(classement, quotas)

    assert len(repartition) == 3
    assert any("registre-invente" in r.message for r in caplog.records)


def test_le_departage_a_score_egal_reste_stable_apres_repartition():
    """Aucun ordre aléatoire (leçon Story 1.3/1.4)."""
    quotas = Quotas(apprendre=10, ce_qui_bouge=10, pour_le_metier=10)
    classement = [_is_(_item(f"src-{i}", registre="apprendre"), 0.0) for i in range(4)]

    repartition = repartir_par_quotas(classement, quotas)

    assert [is_.item.source_id for is_ in repartition] == [f"src-{i}" for i in range(4)]


# --- Rapport de la répartition (AC5) -------------------------------------


def test_rapport_quotas_compte_les_retenus_et_ecartes_par_registre():
    quotas = Quotas(apprendre=1, ce_qui_bouge=5, pour_le_metier=5)
    classement = [
        _is_(_item("a", registre="apprendre"), 30),
        _is_(_item("b", registre="apprendre"), 20),
        _is_(_item("c", registre="ce_qui_bouge"), 15),
    ]

    repartition = repartir_par_quotas(classement, quotas)
    rapport = rapport_quotas(classement, repartition)

    assert rapport.retenus_par_registre == {"apprendre": 1, "ce_qui_bouge": 1}
    assert rapport.ecartes_par_registre == {"apprendre": 1}
    assert rapport.total_ecartes == 1


def test_rapport_quotas_expose_aussi_les_ecartes_par_source():
    """Détail non exigé par l'AC (qui ne demande que « par registre ») mais
    nécessaire au diagnostic « source absorbée » de `collect.py` — sans lui,
    un quota dépassé retomberait à tort sur « cause indéterminée »."""
    quotas = Quotas(apprendre=1, ce_qui_bouge=5, pour_le_metier=5)
    classement = [
        _is_(_item("src-a", registre="apprendre"), 30),
        _is_(_item("src-b", registre="apprendre"), 20),
    ]

    repartition = repartir_par_quotas(classement, quotas)
    rapport = rapport_quotas(classement, repartition)

    assert rapport.ecartes_par_source == {"src-b": 1}


def test_rapport_quotas_sans_depassement_est_vide():
    quotas = Quotas(apprendre=5, ce_qui_bouge=5, pour_le_metier=5)
    classement = [_is_(_item("a", registre="apprendre"), 10)]

    repartition = repartir_par_quotas(classement, quotas)
    rapport = rapport_quotas(classement, repartition)

    assert rapport.total_ecartes == 0
    assert rapport.retenus_par_registre == {"apprendre": 1}


# --- Correctifs de revue (2026-08-28) ------------------------------------


def test_resume_avec_retenus_vides_mais_ecartes_reste_lisible():
    """Régression : un quota à 0 pouvait vider tout un registre présent,
    laissant `retenus_par_registre` vide alors que `total_ecartes` ne
    l'était pas — `resume()` produisait `'Quotas :  retenu(s)'` (chaîne
    vide avant « retenu(s) »)."""
    quotas = Quotas(apprendre=0, ce_qui_bouge=5, pour_le_metier=5)
    classement = [_is_(_item("a", registre="apprendre"), 10)]

    repartition = repartir_par_quotas(classement, quotas)
    resume = rapport_quotas(classement, repartition).resume()

    assert "Quotas :  retenu" not in resume  # jamais de champ vide
    assert "aucun item retenu" in resume
    assert "1 écarté(s) par dépassement de quota" in resume


def test_charger_quotas_valeur_falsy_mal_typee_est_signalee(tmp_path):
    """Régression : `quotas: 0` (falsy) passait `.get(...) or {}` sans
    déclencher l'avertissement `'n'est pas un mapping'` que `quotas: 5`
    (truthy, tout aussi mal typé) déclenchait bien."""
    chemin = tmp_path / "quotas.yaml"
    chemin.write_text("quotas: 0\n", encoding="utf-8")

    assert charger_quotas(chemin) == Quotas()


def test_charger_quotas_cle_inconnue_est_signalee(tmp_path, caplog):
    """Régression : une clé mal orthographiée sous `quotas:` était perdue
    sans le moindre avertissement, contrairement à une valeur mal typée
    pour une clé reconnue."""
    chemin = tmp_path / "quotas.yaml"
    chemin.write_text(
        "quotas:\n  pour_le_metier_mal_ecrit: 7\n  apprendre: 1\n", encoding="utf-8"
    )

    with caplog.at_level("WARNING"):
        quotas = charger_quotas(chemin)

    assert quotas.apprendre == 1
    assert any("pour_le_metier_mal_ecrit" in r.message for r in caplog.records)


def test_charger_quotas_none_ne_leve_pas():
    """Régression : `charger_quotas(None)` levait `TypeError`, alors que la
    docstring promet « ne lève jamais »."""
    assert charger_quotas(None) == Quotas()


def test_charger_ponderations_valeur_falsy_mal_typee_est_signalee(tmp_path):
    chemin = tmp_path / "scoring.yaml"
    chemin.write_text("ponderations: 0\n", encoding="utf-8")

    assert charger_ponderations(chemin) == Ponderations()


def test_charger_ponderations_cle_inconnue_est_signalee(tmp_path, caplog):
    chemin = tmp_path / "scoring.yaml"
    chemin.write_text("ponderations:\n  priorotaire: 100\n", encoding="utf-8")

    with caplog.at_level("WARNING"):
        charger_ponderations(chemin)

    assert any("priorotaire" in r.message for r in caplog.records)


def test_charger_ponderations_none_ne_leve_pas():
    assert charger_ponderations(None) == Ponderations()


def test_un_registre_none_est_distingue_d_un_registre_inconnu_texte(caplog):
    """Régression : `item.registre is None` (source mal configurée en
    amont) produisait le même message qu'un registre valide mais non réglé
    — deux causes différentes méritent deux diagnostics différents."""
    quotas = Quotas(apprendre=1, ce_qui_bouge=1, pour_le_metier=1)
    classement = [_is_(_item("a", registre=None), 10)]

    with caplog.at_level("WARNING"):
        repartition = repartir_par_quotas(classement, quotas)

    assert len(repartition) == 1  # toujours conservé, comportement inchangé
    message = caplog.records[0].message
    assert "sans registre défini" in message
    assert "'None'" not in message
