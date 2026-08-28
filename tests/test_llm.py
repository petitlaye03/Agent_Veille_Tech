"""Tests de la frontière LLM unique (Story 1.6, AD-7).

Aucun appel réseau réel : le client Anthropic est systématiquement simulé
via `_ClientSimule` (voir Dev Notes de la story pour le patron).
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import anthropic
import pytest

from veille.enrich import llm
from veille.filter import ItemScore, Ponderations, Score
from veille.models import Entree, Item


@pytest.fixture(autouse=True)
def _reset_etat_module():
    """`_client()` mémorise l'état du chargement de `.env` et l'émission de
    son avertissement au niveau du module — sans réinitialisation, l'ordre
    d'exécution des tests changerait leur résultat."""
    llm._env_charge = False
    llm._avertissement_cle_absente_emis = False
    llm._avertissement_echec_api_emis = False
    yield


class _MessagesSimulees:
    """Simule `client.messages` : ne touche jamais le réseau."""

    def __init__(self, texte=None, exception=None):
        self._texte = texte
        self._exception = exception
        self.derniere_requete: dict | None = None

    def create(self, **kwargs):
        self.derniere_requete = kwargs
        if self._exception:
            raise self._exception
        return SimpleNamespace(
            content=[SimpleNamespace(text=self._texte)],
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        )


class _ClientSimule:
    def __init__(self, texte=None, exception=None):
        self.messages = _MessagesSimulees(texte, exception)


# --- Task 2 : _client() ---------------------------------------------------


def test_client_absent_de_cle_api_ne_leve_pas(monkeypatch):
    """Sans ANTHROPIC_API_KEY, `_client()` dégrade vers `None` — jamais de
    plantage, cohérent avec le reste du projet (charger_profil, etc.)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    assert llm._client() is None


def test_client_present_avec_cle_api(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-000")

    client = llm._client()

    assert client is not None


def test_client_avec_cle_composee_uniquement_d_espaces_est_traitee_comme_absente(monkeypatch):
    """Régression (revue) : une clé blanche (copier-coller malheureux)
    passait le test `if not cle` et produisait un client inutilisable."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")

    assert llm._client() is None


def test_avertissement_de_cle_absente_n_est_emis_qu_une_fois(monkeypatch, caplog):
    """Un digest compte jusqu'à ~240 items : appeler `_client()` une fois
    par item ne doit pas produire 240 avertissements identiques."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with caplog.at_level("WARNING"):
        for _ in range(5):
            llm._client()

    avertissements = [r for r in caplog.records if "ANTHROPIC_API_KEY absente" in r.message]
    assert len(avertissements) == 1


def _make_item(**overrides):
    defaults = dict(
        source_id="src",
        guid="guid-1",
        titre="Un titre en anglais",
        date_publication=datetime(2026, 8, 1, tzinfo=timezone.utc),
        langue="en",
        registre="apprendre",
        url="https://exemple.invalid/article",
        contenu_brut="Un extrait de contenu en anglais, assez long pour servir de contexte.",
    )
    defaults.update(overrides)
    return Item(**defaults)


def test_le_prompt_systeme_avertit_contre_les_instructions_du_contenu_source():
    """Régression (revue) : le contenu d'un item vient de sources externes
    non fiables (RSS, scraping) et est injecté verbatim dans le message
    utilisateur ; le prompt système doit au moins consigner explicitement
    qu'il ne s'agit jamais d'instructions à suivre."""
    assert "jamais" in llm._PROMPT_SYSTEME.lower()
    assert "instruction" in llm._PROMPT_SYSTEME.lower()


# --- Task 3 : generer_accroche ------------------------------------------


def test_generer_accroche_retourne_le_texte_de_la_reponse():
    client = _ClientSimule(texte="Une accroche en français.")

    accroche = llm.generer_accroche(_make_item(), client)

    assert accroche == "Une accroche en français."


def test_generer_accroche_tronque_un_titre_demesure():
    """Régression (revue) : seul l'extrait était borné, pas le titre —
    un titre anormalement long (flux malformé) gonflait le prompt sans
    limite, contredisant le contrôle de coût "par construction"."""
    client = _ClientSimule(texte="Accroche.")
    item = _make_item(titre="T" * 5000, contenu_brut="")

    llm.generer_accroche(item, client)

    contenu_envoye = client.messages.derniere_requete["messages"][0]["content"]
    assert len(contenu_envoye) < 1000


def test_generer_accroche_reponse_tronquee_par_max_tokens_est_un_echec():
    """Régression (revue) : `stop_reason` n'était jamais vérifié — un texte
    coupé en plein mot était publié comme accroche valide."""
    client = SimpleNamespace(
        messages=SimpleNamespace(
            create=lambda **kw: SimpleNamespace(
                content=[SimpleNamespace(text="Une accroche coupée en pl")],
                stop_reason="max_tokens",
            )
        )
    )

    accroche = llm.generer_accroche(_make_item(), client)

    assert accroche is None


def test_generer_accroche_transmet_le_titre_et_l_extrait_dans_le_prompt():
    client = _ClientSimule(texte="Accroche.")
    item = _make_item(titre="Titre précis", contenu_brut="Contenu précis.")

    llm.generer_accroche(item, client)

    requete = client.messages.derniere_requete
    contenu_envoye = requete["messages"][0]["content"]
    assert "Titre précis" in contenu_envoye
    assert "Contenu précis." in contenu_envoye
    assert requete["model"] == llm.MODELE
    assert requete["max_tokens"] == llm.MAX_TOKENS_ACCROCHE


def test_generer_accroche_isole_une_erreur_api_sans_lever():
    client = _ClientSimule(exception=anthropic.APIConnectionError(request=SimpleNamespace()))

    accroche = llm.generer_accroche(_make_item(), client)

    assert accroche is None


def test_generer_accroche_isole_une_exception_inattendue_sans_lever():
    client = _ClientSimule(exception=RuntimeError("panne inattendue"))

    accroche = llm.generer_accroche(_make_item(), client)

    assert accroche is None


def test_generer_accroche_reponse_sans_contenu_ne_leve_pas():
    client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **kw: SimpleNamespace(content=[]))
    )

    accroche = llm.generer_accroche(_make_item(), client)

    assert accroche is None


def test_generer_accroche_sans_client_disponible_retourne_none(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    accroche = llm.generer_accroche(_make_item())

    assert accroche is None


# --- Task 4 : enrichir ----------------------------------------------------


def test_enrichir_produit_une_entree_par_item():
    client = _ClientSimule(texte="Accroche générée.")
    items = [_make_item(guid="a"), _make_item(guid="b")]

    entrees = llm.enrichir(items, client)

    assert len(entrees) == 2
    assert all(e.accroche == "Accroche générée." for e in entrees)
    assert [e.item for e in entrees] == items


def test_enrichir_ne_produit_jamais_une_accroche_vide():
    """Régression (revue) : `generer_accroche(...) or item.titre` renvoie
    `''` (pas `None`) quand le titre lui-même est vide — `None or "" == ""`
    en Python. Un dernier repli garantit qu'une `Entree` n'est jamais
    publiée avec une accroche entièrement vide."""
    client = _ClientSimule(exception=RuntimeError("panne"))
    item = _make_item(titre="")

    entrees = llm.enrichir([item], client)

    assert entrees[0].accroche == "(titre indisponible)"


def test_enrichir_resout_le_client_une_seule_fois(monkeypatch):
    """Régression (revue) : sans client explicite, chaque item reconstruisait
    son propre `anthropic.Anthropic()` — un nouveau pool de connexions par
    item sur un lot pouvant compter ~240 entrées."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-000")
    appels = []

    def _client_espion():
        client = _ClientSimule(texte="Accroche.")
        appels.append(client)
        return client

    monkeypatch.setattr(llm, "_client", _client_espion)

    llm.enrichir([_make_item(guid="a"), _make_item(guid="b"), _make_item(guid="c")])

    assert len(appels) == 1


def test_avertissement_echec_api_n_est_journalise_en_detail_qu_une_fois(caplog):
    """Régression (revue) : une panne systémique (clé invalide, quota
    épuisé) échoue de la même façon pour chaque item — jusqu'à 240
    tracebacks quasi identiques sans cette dégradation."""
    client = _ClientSimule(exception=RuntimeError("panne systémique"))
    items = [_make_item(guid=f"item-{i}") for i in range(3)]

    with caplog.at_level("WARNING"):
        llm.enrichir(items, client)

    avertissements = [r for r in caplog.records if "Échec de l'appel API" in r.message]
    assert len(avertissements) == 3  # un par item, aucun perdu
    # Seul le premier porte la trace complète (exc_info).
    assert avertissements[0].exc_info is not None
    assert avertissements[1].exc_info is None
    assert avertissements[2].exc_info is None


def test_enrichir_replie_sur_le_titre_si_l_accroche_echoue():
    """Décision actée le 2026-08-28 (option B) : un item est conservé avec
    son titre original en repli, jamais écarté du digest."""
    client = _ClientSimule(exception=RuntimeError("panne"))
    item = _make_item(titre="Titre de repli")

    entrees = llm.enrichir([item], client)

    assert len(entrees) == 1
    assert entrees[0].accroche == "Titre de repli"
    assert entrees[0].item is item


class _MessagesConditionnelles:
    """Échoue pour l'item dont le titre contient « ko », réussit pour les
    autres — permet de représenter un lot mixte avec un seul client simulé."""

    def create(self, **kwargs):
        contenu = kwargs["messages"][0]["content"]
        if "Titre ko" in contenu:
            raise RuntimeError("panne réseau simulée")
        return SimpleNamespace(
            content=[SimpleNamespace(text="Accroche générée.")],
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        )


def test_enrichir_isole_l_echec_d_un_item_sans_perdre_les_autres():
    """Dans un lot de plusieurs items, l'échec de l'un ne doit ni faire
    lever d'exception, ni faire disparaître les autres de la liste."""
    client = SimpleNamespace(messages=_MessagesConditionnelles())
    items = [
        _make_item(guid="a", titre="Titre bon A"),
        _make_item(guid="ko", titre="Titre ko"),
        _make_item(guid="b", titre="Titre bon B"),
    ]

    entrees = llm.enrichir(items, client)

    assert len(entrees) == 3  # aucun item perdu
    assert entrees[0].accroche == "Accroche générée."
    assert entrees[1].accroche == "Titre ko"  # repli sur le titre, pas de plantage
    assert entrees[2].accroche == "Accroche générée."


# --- Story 1.7 : determiner_recommandation -------------------------------


def _is(guid, valeur):
    return ItemScore(item=_make_item(guid=guid), score=Score(valeur=valeur))


def test_determiner_recommandation_quand_la_marge_est_depassee():
    classement = [_is("a", 30), _is("b", 15), _is("c", 5)]  # 30-15=15 >= marge(10)

    gagnant = llm.determiner_recommandation(classement)

    assert gagnant.item.guid == "a"


def test_determiner_recommandation_quand_la_marge_n_est_pas_depassee():
    classement = [_is("a", 20), _is("b", 15)]  # écart 5 < marge(10)

    assert llm.determiner_recommandation(classement) is None


def test_determiner_recommandation_avec_des_scores_egaux():
    classement = [_is("a", 20), _is("b", 20)]

    assert llm.determiner_recommandation(classement) is None


def test_determiner_recommandation_avec_un_seul_item():
    """Rien à comparer : jamais de recommandation (AC2)."""
    assert llm.determiner_recommandation([_is("a", 1000)]) is None


def test_determiner_recommandation_avec_une_liste_vide():
    assert llm.determiner_recommandation([]) is None


def test_determiner_recommandation_egalite_exacte_a_la_marge_est_recommandee():
    """`>=`, pas `>` — un écart exactement égal à la marge compte."""
    classement = [_is("a", 20), _is("b", 10)]  # écart 10 == marge(10)

    gagnant = llm.determiner_recommandation(classement)

    assert gagnant.item.guid == "a"


def test_determiner_recommandation_respecte_une_marge_personnalisee():
    classement = [_is("a", 20), _is("b", 15)]  # écart 5

    assert llm.determiner_recommandation(classement, Ponderations(marge_recommandation=3)) is not None
    assert llm.determiner_recommandation(classement, Ponderations(marge_recommandation=6)) is None


def test_determiner_recommandation_ne_retrie_pas():
    """Le classement est déjà trié par `classer()` — un ordre non trié en
    entrée refléterait un appelant fautif, pas quelque chose à corriger ici :
    la fonction doit utiliser le premier élément tel quel."""
    # Volontairement non trié : si la fonction retriait, elle choisirait "a".
    classement = [_is("b", 15), _is("a", 30)]

    gagnant = llm.determiner_recommandation(classement)

    # Sur une entrée non triée, le "premier" (b) ne dépasse pas le second (a)
    # d'une marge suffisante (15 - 30 < 0) : aucune recommandation.
    assert gagnant is None


# --- Story 1.7 : marquer_recommandation -----------------------------------


def _entree_pour(item_score):
    return Entree(item=item_score.item, accroche=f"Accroche {item_score.item.guid}")


def test_marquer_recommandation_marque_la_bonne_entree():
    classement = [_is("a", 30), _is("b", 15)]
    entrees = [_entree_pour(is_) for is_ in classement]

    resultat = llm.marquer_recommandation(entrees, classement)

    assert resultat[0].recommandee is True
    assert resultat[1].recommandee is False


def test_marquer_recommandation_sans_gagnant_ne_marque_personne():
    classement = [_is("a", 20), _is("b", 15)]  # écart < marge
    entrees = [_entree_pour(is_) for is_ in classement]

    resultat = llm.marquer_recommandation(entrees, classement)

    assert all(not e.recommandee for e in resultat)


def test_marquer_recommandation_fonctionne_meme_si_l_ordre_differe():
    classement = [_is("a", 30), _is("b", 15)]
    entrees = [_entree_pour(classement[1]), _entree_pour(classement[0])]  # ordre inversé

    resultat = llm.marquer_recommandation(entrees, classement)

    assert resultat[0].recommandee is False  # b
    assert resultat[1].recommandee is True  # a


def test_marquer_recommandation_avec_une_liste_vide_ne_leve_pas():
    assert llm.marquer_recommandation([], []) == []


def test_marquer_recommandation_gagnant_sans_entree_correspondante_ne_leve_pas():
    """Listes désynchronisées (trouvé en revue — affirmé par la docstring
    mais jamais exercé) : le gagnant du `classement` ne correspond à aucune
    `Entree` de `entrees` (aucun `id(entree.item)` égal). La fonction ne
    doit ni lever, ni marquer qui que ce soit — `entrees` ressort inchangée."""
    classement = [_is("a", 30), _is("b", 15)]  # "a" gagne largement
    entrees = [_entree_pour(_is("x", 1)), _entree_pour(_is("y", 1))]  # items différents

    resultat = llm.marquer_recommandation(entrees, classement)

    assert resultat == entrees
    assert all(not e.recommandee for e in resultat)


def test_marquer_recommandation_ne_modifie_pas_les_entrees_non_gagnantes():
    """`Entree` est frozen : seules de nouvelles instances sont créées, et
    seulement pour l'entrée gagnante — les autres restent les mêmes objets."""
    classement = [_is("a", 30), _is("b", 15)]
    entrees = [_entree_pour(is_) for is_ in classement]

    resultat = llm.marquer_recommandation(entrees, classement)

    assert resultat[1] is entrees[1]  # objet inchangé, pas une copie
    assert resultat[0] is not entrees[0]  # nouvelle instance (frozen + replace)
