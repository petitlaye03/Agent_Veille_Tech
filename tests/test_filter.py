"""Tests du filtrage par signal et du scoring par profil (Story 1.4)."""

import textwrap
from datetime import datetime, timezone

from veille.config import SourceConfig
from veille.filter import (
    Ponderations,
    charger_ponderations,
    classer,
    filtrer_par_signal,
    rapport_classement,
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
