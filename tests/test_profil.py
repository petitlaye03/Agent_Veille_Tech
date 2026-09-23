"""Tests du chargement et de l'analyse du profil (Task 2, Story 1.4)."""

import textwrap
from pathlib import Path

from veille.profil import Profil, _analyser, charger_profil

RACINE_PROJET = Path(__file__).resolve().parent.parent
CHEMIN_PROFIL_REEL = RACINE_PROJET / "config" / "profil.md"


def _ecrire(tmp_path: Path, contenu: str) -> Path:
    chemin = tmp_path / "profil.md"
    chemin.write_text(textwrap.dedent(contenu), encoding="utf-8")
    return chemin


# --- Profil réel -------------------------------------------------------


def test_le_profil_reel_existe():
    assert CHEMIN_PROFIL_REEL.is_file(), f"{CHEMIN_PROFIL_REEL} introuvable"


def test_le_profil_reel_produit_des_mots_cles_non_vides_par_categorie():
    """Garde-fou (Testing Standards) : le profil réel produit des mots-clés
    exploitables dans chaque catégorie attendue."""
    profil = charger_profil(CHEMIN_PROFIL_REEL)

    assert not profil.est_vide
    assert profil.prioritaire
    assert profil.signal_fort
    assert profil.domaine
    assert profil.secondaire
    assert profil.bruit


def test_le_profil_reel_contient_les_mots_cles_prioritaires_attendus():
    """Les exemples cités par l'AC4 (RAG, agents, evals) doivent être présents."""
    profil = charger_profil(CHEMIN_PROFIL_REEL)
    prioritaires = {m.lower() for m in profil.prioritaire}

    assert "rag" in prioritaires
    assert "agents" in prioritaires
    assert "evals" in prioritaires


def test_le_profil_reel_contient_les_mots_cles_de_bruit_attendus():
    """Les exemples cités par l'AC5 (crypto, hype, actu conso) doivent être présents."""
    profil = charger_profil(CHEMIN_PROFIL_REEL)
    bruit = {m.lower() for m in profil.bruit}

    assert "crypto" in bruit


def test_le_profil_reel_contient_les_domaines_attendus():
    profil = charger_profil(CHEMIN_PROFIL_REEL)

    assert "Finance" in profil.domaine
    assert "Multimédia" in profil.domaine


# --- Robustesse (ne jamais lever) --------------------------------------


def test_profil_absent_produit_un_profil_neutre(tmp_path):
    profil = charger_profil(tmp_path / "inexistant.md")

    assert profil == Profil()
    assert profil.est_vide


def test_profil_vide_produit_un_profil_neutre(tmp_path):
    chemin = _ecrire(tmp_path, "")

    profil = charger_profil(chemin)

    assert profil.est_vide


def test_profil_sans_aucune_section_connue_produit_un_profil_neutre(tmp_path):
    chemin = _ecrire(
        tmp_path,
        """
        # Un profil qui ne respecte aucune convention

        Rien que de la prose, sans le moindre titre `##`.
        """,
    )

    profil = charger_profil(chemin)

    assert profil.est_vide


# --- Section inconnue ----------------------------------------------------


def test_une_section_inconnue_est_ignoree_sans_lever(tmp_path):
    chemin = _ecrire(
        tmp_path,
        """
        ## Thèmes prioritaires — font monter le score
        - RAG, agents

        ## Section fantaisiste inventée pour le test
        - foo, bar

        ## Bruit — fait descendre ou disparaître
        - crypto
        """,
    )

    profil = charger_profil(chemin)

    assert "RAG" in profil.prioritaire
    assert "crypto" in profil.bruit
    mots_connus = set(profil.prioritaire) | set(profil.bruit)
    assert "foo" not in mots_connus
    assert "bar" not in mots_connus


def test_la_section_posture_est_ignoree_sans_avertissement_de_section_inconnue(tmp_path):
    """Posture est une section connue mais prose : pas de mots-clés, pas d'alerte."""
    chemin = _ecrire(
        tmp_path,
        """
        ## Posture
        - Junior Data Scientist, vise AI Engineer.

        ## Thèmes prioritaires — font monter le score
        - RAG
        """,
    )

    profil = charger_profil(chemin)

    assert profil.prioritaire == ("RAG",)


# --- Extraction : gras, listes, asides italiques, tirets cadratins ------


def test_terme_en_gras_est_extrait_comme_mot_cle(tmp_path):
    chemin = _ecrire(
        tmp_path,
        """
        ## Thèmes prioritaires — font monter le score
        **RAG & retrieval** *(mon terrain — chatbot juridique en RAG hybride : Milvus, Ollama)*
        - hybrid search
        """,
    )

    profil = charger_profil(chemin)

    assert "RAG" in profil.prioritaire
    assert "retrieval" in profil.prioritaire
    assert "hybrid search" in profil.prioritaire


def test_aside_italique_entre_parentheses_est_exclu(tmp_path):
    """Un commentaire italique n'est jamais un mot-clé (Dev Notes)."""
    chemin = _ecrire(
        tmp_path,
        """
        ## Signal fort — à privilégier quand ça apparaît
        - Contenu directement lié au RAG / retrieval *(mon atout à valoriser en entretien)*
        """,
    )

    profil = charger_profil(chemin)

    assert not any("entretien" in m.lower() for m in profil.signal_fort)
    assert not any("atout" in m.lower() for m in profil.signal_fort)


def test_texte_apres_tiret_cadratin_est_exclu(tmp_path):
    """`- **Finance** — data/IA appliquée à la finance` ne garde que « Finance »."""
    chemin = _ecrire(
        tmp_path,
        """
        ## Domaines d'application privilégiés
        - **Finance** — data/IA appliquée à la finance
        """,
    )

    profil = charger_profil(chemin)

    assert profil.domaine == ("Finance",)


def test_parentheses_dans_une_ligne_de_liste_produisent_des_mots_cles_distincts(tmp_path):
    """`inference (vLLM, Ollama)` doit donner trois mots-clés, pas un seul collé."""
    chemin = _ecrire(
        tmp_path,
        """
        ## Thèmes prioritaires — font monter le score
        - inference (vLLM, Ollama)
        """,
    )

    profil = charger_profil(chemin)

    assert set(profil.prioritaire) == {"inference", "vLLM", "Ollama"}


def test_prefixe_de_titre_suffit_meme_si_la_fin_change(tmp_path):
    """Reformuler la fin d'un titre ne doit pas casser le parseur (préfixe, pas égalité)."""
    chemin = _ecrire(
        tmp_path,
        """
        ## Thèmes prioritaires - reformulé complètement différemment
        - RAG
        """,
    )

    profil = charger_profil(chemin)

    assert "RAG" in profil.prioritaire


def test_correspondance_de_section_insensible_aux_accents_et_a_la_casse(tmp_path):
    chemin = _ecrire(
        tmp_path,
        """
        ## THEMES PRIORITAIRES SANS ACCENTS
        - RAG
        """,
    )

    profil = charger_profil(chemin)

    assert "RAG" in profil.prioritaire


# --- Robustesse aux éditions manuelles plausibles (revue 2026-08-28) ----
#
# `profil.md` est LE fichier qu'Abdoulaye est invité à modifier (AD-3).
# Chacune des éditions ci-dessous perdait auparavant des mots-clés, ou une
# section entière, sans le moindre avertissement.


def test_apostrophe_typographique_dans_un_titre_de_section(tmp_path):
    """Régression : la plupart des éditeurs produisent « ’ ». La section
    entière était alors classée inconnue et tous ses mots-clés perdus."""
    chemin = _ecrire(tmp_path, "## Domaines d’application privilégiés\n- Finance\n")

    assert charger_profil(chemin).domaine == ("Finance",)


def test_un_titre_de_niveau_trois_est_reconnu(tmp_path):
    """Régression : `### Thèmes prioritaires` produisait un profil vide."""
    chemin = _ecrire(tmp_path, "### Thèmes prioritaires — montent\n- RAG\n")

    assert "RAG" in charger_profil(chemin).prioritaire


def test_les_puces_non_tiret_sont_reconnues(tmp_path):
    chemin = _ecrire(
        tmp_path,
        """
        ## Thèmes prioritaires
        * RAG
        + agents
        1. evals
        """,
    )

    profil = charger_profil(chemin)

    assert set(profil.prioritaire) == {"RAG", "agents", "evals"}


def test_un_titre_ferme_la_section_precedente(tmp_path):
    """Régression : la catégorie n'était pas réinitialisée, si bien qu'un
    mot-clé placé après un titre de niveau 1 atterrissait dans la section
    précédente — un thème prioritaire pouvait se retrouver pénalisé."""
    chemin = _ecrire(
        tmp_path,
        """
        ## Bruit — fait descendre
        - crypto

        # Une autre partie du document

        - RAG
        """,
    )

    profil = charger_profil(chemin)

    assert profil.bruit == ("crypto",)
    assert "RAG" not in profil.bruit


def test_la_ponctuation_de_bordure_est_retiree_des_mots_cles(tmp_path):
    """Régression : `Qwen…` conservait ses points de suspension et devenait
    inerte, car une frontière de mot ne s'ancre pas contre « … »."""
    chemin = _ecrire(
        tmp_path,
        "## Thèmes prioritaires\n- LLM open source (Mistral, Llama, Qwen…)\n",
    )

    assert "Qwen" in charger_profil(chemin).prioritaire


def test_tiret_demi_cadratin_traite_comme_le_cadratin(tmp_path):
    chemin = _ecrire(tmp_path, "## Domaines d'application\n- Finance – data appliquée\n")

    assert charger_profil(chemin).domaine == ("Finance",)


def test_aside_italique_contenant_une_parenthese_est_entierement_retire(tmp_path):
    """Régression : l'expression gourmande s'arrêtait à la première `)`,
    laissant la fin de l'aside devenir des mots-clés."""
    chemin = _ecrire(
        tmp_path,
        "## Thèmes prioritaires\n- RAG *(mon terrain (Milvus) au quotidien)*\n",
    )

    profil = charger_profil(chemin)

    assert profil.prioritaire == ("RAG",)


def test_un_tiret_isole_ne_devient_pas_un_mot_cle(tmp_path):
    """Un mot-clé sans caractère alphanumérique matcherait un peu partout."""
    chemin = _ecrire(tmp_path, "## Bruit\n- -\n- crypto\n")

    assert charger_profil(chemin).bruit == ("crypto",)


def test_un_commentaire_html_ne_produit_pas_de_mots_cles(tmp_path):
    """Régression : un commentaire placé DANS une section était lu comme des
    mots-clés — chaque ligne de la note devenait un terme de filtrage."""
    chemin = _ecrire(
        tmp_path,
        """
        ## Bruit — fait descendre
        <!--
          Note pour plus tard : ne pas oublier les levées de fonds.
        -->
        - crypto
        """,
    )

    assert charger_profil(chemin).bruit == ("crypto",)


def test_un_profil_vide_est_journalise(tmp_path, caplog):
    """Un profil neutre désactive le classement en entier : il ne doit
    jamais passer inaperçu."""
    chemin = _ecrire(tmp_path, "# Titre seul, aucune section reconnue\n")

    with caplog.at_level("WARNING"):
        profil = charger_profil(chemin)

    assert profil.est_vide
    assert any("neutralis" in r.message.lower() for r in caplog.records)


# --- Garde-fous sur la section Bruit réelle (AC5) ------------------------


def test_les_mots_cles_de_bruit_reels_sont_des_termes_pas_des_phrases():
    """Régression AC5 : 6 des 14 mots-clés de bruit étaient des phrases
    entières, donc introuvables dans un article. Un mot-clé long est le
    signe d'une puce rédigée en prose."""
    profil = charger_profil(CHEMIN_PROFIL_REEL)

    trop_longs = [m for m in profil.bruit if len(m.split()) > 4]

    assert not trop_longs, (
        f"mots-clés de bruit rédigés en phrase, donc inertes : {trop_longs}"
    )


def test_le_profil_reel_couvre_les_trois_exemples_nommes_par_l_ac5():
    """L'AC5 nomme crypto, hype et actu conso. Le test précédent n'assurait
    que `crypto`, et laissait donc passer deux tiers du critère."""
    profil = charger_profil(CHEMIN_PROFIL_REEL)
    bruit = {m.lower() for m in profil.bruit}

    assert "crypto" in bruit
    assert "hype" in bruit
    assert "smartphone" in bruit


# --- Audit du 2026-09-22 : la posture, lue pour la rédaction ----------
# `profil.md` pilotait le tri sans jamais atteindre `enrich/llm.py`, qui
# rédigeait donc ses accroches sans rien savoir du lecteur.


def test_la_section_posture_est_collectee_comme_prose():
    profil = _analyser(
        "## Posture\n"
        "- Junior Data Scientist à **Dakar**.\n"
        "- Vise : *(surtout)* AI/LLM Engineer.\n"
        "\n## Bruit — fait descendre\n- crypto\n"
    )

    assert profil.posture == (
        "Junior Data Scientist à Dakar.",
        "Vise : AI/LLM Engineer.",
    )


def test_la_posture_ne_devient_jamais_un_mot_cle():
    """Ses phrases ne sont pas des mots-clés : les scorer ferait remonter
    n'importe quel article contenant « junior » ou « Dakar »."""
    profil = _analyser("## Posture\n- Junior Data Scientist à Dakar.\n")

    assert profil.prioritaire == () and profil.bruit == ()


def test_un_profil_sans_mots_cles_reste_vide_meme_avec_une_posture():
    """`est_vide` ne décrit que la neutralisation du **classement** : une
    posture seule ne doit pas faire croire que le scoring est actif."""
    profil = _analyser("## Posture\n- Une phrase.\n")

    assert profil.est_vide is True


def test_le_profil_reel_declare_une_posture():
    """Garde-fou sur le fichier livré : sans posture, les accroches
    retombent silencieusement sur le prompt générique."""
    profil = charger_profil(CHEMIN_PROFIL_REEL)

    assert len(profil.posture) >= 3
