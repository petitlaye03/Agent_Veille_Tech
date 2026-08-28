"""Filtrage par signal de source et classement par pertinence (FR-4, FR-5).

Deux mécanismes distincts, exécutés dans cet ordre :

1. **Seuil de signal** (`filtrer_par_signal`) : écarte les items dont le
   signal de leur source (votes, points…) est sous un seuil déclaré en
   configuration. Optionnel par source, jamais implicite.
2. **Scoring par profil** (`scorer`, `classer`) : classe le reste par
   proximité avec `profil.md`, et écarte ce qui relève du bruit.

Le seuil de signal s'exécute en premier : inutile de scorer un item qu'on
va écarter, et il utilise le jugement d'une communauté entière — un
jugement que le scoring lexical, qui ne connaît que des mots-clés, ne
reproduirait que mal.
"""

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from veille.config import SourceConfig, chemin_config, to_float_fini
from veille.models import Item
from veille.profil import Profil, sans_accents

logger = logging.getLogger(__name__)

DEFAULT_SCORING_PATH = chemin_config("scoring.yaml")

# Atténuation appliquée à chaque mot-clé supplémentaire d'une même catégorie :
# le deuxième compte moitié, le troisième un quart, etc. Sans elle, empiler
# des mots-clés génériques (cloud, infrastructure, monitoring) l'emporterait
# sur un article en plein cœur de cible.
_ATTENUATION_PAR_RANG = 0.5


@dataclass(frozen=True)
class RapportFiltrageSignal:
    """Ce que le filtrage par signal a écarté, par source.

    Sans ce compte-rendu, un seuil trop agressif viderait une source en
    silence — la même leçon que le dédoublonnage (Story 1.3)."""

    ecartes_par_source: dict[str, int] = field(default_factory=dict)

    @property
    def total_ecartes(self) -> int:
        return sum(self.ecartes_par_source.values())

    def resume(self) -> str:
        if not self.total_ecartes:
            return "Signal : aucun item sous le seuil."
        return (
            f"Signal : {self.total_ecartes} item(s) sous le seuil de leur "
            f"source — {_par_source(self.ecartes_par_source)}"
        )


def _par_source(comptes: dict[str, int]) -> str:
    """Ventilation nommée, sur le modèle de `RapportDedoublonnage.resume()`.

    AC7 exige un compte rendu **par source** : un total seul ne dit pas
    laquelle a été vidée, et c'est précisément ce qu'il faut voir quand un
    seuil ou un profil devient trop agressif.
    """
    return ", ".join(
        f"{source} (-{n})"
        for source, n in sorted(comptes.items(), key=lambda x: (-x[1], x[0]))
    )


def filtrer_par_signal(
    items: list[Item], sources: dict[str, SourceConfig]
) -> tuple[list[Item], RapportFiltrageSignal]:
    """Écarte les items dont le signal est sous le seuil déclaré par leur source.

    Deux garde-fous (AC2) : une source sans `seuil_signal` laisse passer
    tous ses items — le filtrage n'est jamais implicite ; et un item sans
    signal face à une source qui en déclare un est **conservé**, pas
    écarté — l'absence de donnée n'est pas une insuffisance, l'écarter
    supprimerait silencieusement du contenu légitime.
    """
    retenus: list[Item] = []
    ecartes: Counter[str] = Counter()
    avec_signal: Counter[str] = Counter()
    vus: Counter[str] = Counter()

    for item in items:
        source = sources.get(item.source_id)
        seuil = source.seuil_signal if source else None

        vus[item.source_id] += 1
        if item.signal is not None:
            avec_signal[item.source_id] += 1

        if seuil is not None and item.signal is not None and item.signal < seuil:
            ecartes[item.source_id] += 1
            continue
        retenus.append(item)

    _avertir_seuils_inertes(sources, vus, avec_signal)
    return retenus, RapportFiltrageSignal(ecartes_par_source=dict(ecartes))


def _avertir_seuils_inertes(
    sources: dict[str, SourceConfig], vus: Counter, avec_signal: Counter
) -> None:
    """Signale un `seuil_signal` déclaré qui ne peut rien filtrer.

    Seules les sources JSON déclarant `mapping.signal` renseignent le champ.
    Un seuil posé sur une source RSS ou scrapée — ou sur une source JSON qui
    a oublié son mapping — ne s'applique donc à rien. Le rapport afficherait
    « 0 écarté », qui se lit « rien n'était sous le seuil » alors que le
    filtre n'a jamais tourné : un silence à lever explicitement.
    """
    for source_id, source in sources.items():
        if source.seuil_signal is None or not vus[source_id]:
            continue
        if avec_signal[source_id] == 0:
            logger.warning(
                "Source '%s' : seuil_signal=%s déclaré mais aucun de ses %d "
                "item(s) ne porte de signal — le filtre est inopérant "
                "(mapping.signal manquant, ou type de source qui n'en produit pas).",
                source_id,
                source.seuil_signal,
                vus[source_id],
            )


@dataclass(frozen=True)
class Ponderations:
    """Pondérations du scoring par catégorie (AD-3) : déclarées en
    configuration (`config/scoring.yaml`), jamais en dur. Ces valeurs ne
    servent que de repli quand le fichier est absent ou illisible."""

    prioritaire: float = 10.0
    signal_fort: float = 15.0
    domaine: float = 5.0
    secondaire: float = 2.0
    bruit: float = -20.0

    # Score en dessous duquel un item est écarté, pas seulement rétrogradé.
    seuil_bruit: float = -5.0


def charger_ponderations(chemin: str | Path = DEFAULT_SCORING_PATH) -> Ponderations:
    """Lit `config/scoring.yaml`. Ne lève jamais : un fichier absent,
    illisible, ou dont les valeurs ne sont pas numériques, dégrade vers les
    pondérations par défaut plutôt que de faire échouer le classement."""
    try:
        with open(chemin, encoding="utf-8") as f:
            brut = yaml.safe_load(f)
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        # `UnicodeDecodeError` fait partie du contrat : le fichier contient
        # des accents, et un éditeur mal configuré suffit à le réenregistrer
        # en latin-1. Cette fonction s'exécute hors de l'isolation de panne
        # par source (AD-6) — y laisser filer une exception coûterait la nuit
        # entière, sources saines comprises.
        logger.warning(
            "Pondérations illisibles (%s) — valeurs par défaut.", chemin
        )
        return Ponderations()

    if not isinstance(brut, dict):
        logger.warning(
            "%s ne contient pas un mapping YAML à la racine — valeurs par défaut.",
            chemin,
        )
        return Ponderations()

    defauts = Ponderations()
    categories = brut.get("ponderations") or {}
    if not isinstance(categories, dict):
        logger.warning(
            "La clé 'ponderations' de %s n'est pas un mapping — valeurs par défaut.",
            chemin,
        )
        return Ponderations()

    valeurs = {}
    for nom in ("prioritaire", "signal_fort", "domaine", "secondaire", "bruit"):
        valeurs[nom] = _ponderation(categories, nom, getattr(defauts, nom), chemin)
    valeurs["seuil_bruit"] = _ponderation(
        brut, "seuil_bruit", defauts.seuil_bruit, chemin
    )
    return Ponderations(**valeurs)


def _ponderation(source: dict, nom: str, defaut: float, chemin) -> float:
    """Lit une pondération, en retombant sur son défaut si elle est inutilisable.

    Le repli est **par valeur** et non global : une seule faute de frappe ne
    doit pas faire perdre les autres réglages du fichier. `nan` est rejeté
    en particulier — toute comparaison à `nan` étant fausse, un `seuil_bruit`
    à `nan` viderait le digest sans le moindre avertissement.
    """
    if nom not in source:
        return defaut

    converti = to_float_fini(source[nom])
    if converti is None:
        logger.warning(
            "Pondération '%s' inutilisable (%r) dans %s — valeur par défaut (%s).",
            nom,
            source[nom],
            chemin,
            defaut,
        )
        return defaut
    return converti


@dataclass(frozen=True)
class Score:
    """Résultat du scoring d'un item : la valeur qui pilote le classement,
    et les mots-clés qui y ont contribué — pour qu'Abdoulaye puisse
    comprendre pourquoi un item est remonté (Dev Notes : explicabilité)."""

    valeur: float
    motifs: tuple[str, ...] = ()


# Catégories de mots-clés du profil, dans l'ordre où elles sont recherchées.
# L'ordre n'affecte pas le score (tout se cumule), seulement l'ordre des
# `motifs` rapportés.
_CATEGORIES = ("prioritaire", "signal_fort", "domaine", "secondaire", "bruit")


def scorer(item: Item, profil: Profil, ponderations: Ponderations = Ponderations()) -> Score:
    """Score un item par proximité lexicale avec le profil.

    Recherche de mots-clés sur titre + contenu, insensible à la casse et
    aux accents, sur mot entier (une correspondance par sous-chaîne ferait
    matcher `ia` dans `media` — voir Dev Notes).

    Deux règles de cumul, tranchées en revue le 2026-08-28 :

    - **Un thème ne compte qu'une fois**, au poids de la catégorie qui pèse
      le plus lourd. Sans cela, un terme répété dans deux sections du profil
      doublerait sa contribution à l'insu de celui qui édite le fichier.
    - **Rendements décroissants par catégorie** : le deuxième mot-clé d'une
      même catégorie compte moitié, le troisième un quart. Sans cela,
      accumuler des mots-clés génériques battrait la pertinence réelle.
    """
    texte = sans_accents(f"{item.titre} {item.contenu_brut}").lower()

    # 1. Retenir chaque thème une seule fois, sous sa catégorie la plus
    #    lourde. La comparaison porte sur la valeur absolue : entre un bonus
    #    et une pénalité, c'est le signal le plus fort qui doit trancher.
    retenus: dict[str, tuple[str, str]] = {}
    for categorie in _CATEGORIES:
        poids = getattr(ponderations, categorie)
        for mot_cle in getattr(profil, categorie):
            if not _contient_mot_cle(texte, mot_cle):
                continue
            cle = sans_accents(mot_cle).lower()
            precedent = retenus.get(cle)
            if precedent is None or abs(poids) > abs(getattr(ponderations, precedent[0])):
                retenus[cle] = (categorie, mot_cle)

    # 2. Cumuler catégorie par catégorie, en atténuant chaque correspondance
    #    supplémentaire. L'ordre de `_CATEGORIES` rend le résultat
    #    déterministe quel que soit l'ordre du profil.
    valeur = 0.0
    motifs: list[str] = []
    for categorie in _CATEGORIES:
        poids = getattr(ponderations, categorie)
        rang = 0
        for categorie_retenue, mot_cle in retenus.values():
            if categorie_retenue != categorie:
                continue
            valeur += poids * (_ATTENUATION_PAR_RANG**rang)
            rang += 1
            motifs.append(f"{categorie}:{mot_cle}")

    return Score(valeur=valeur, motifs=tuple(motifs))


def _contient_mot_cle(texte_normalise: str, mot_cle: str) -> bool:
    """Correspondance sur mot entier, tolérante au singulier comme au pluriel.

    `rag` ne doit pas matcher `fragment`, ni `ia` matcher `media` : d'où les
    frontières de mot. Mais celles-ci ne peuvent s'ancrer que contre un
    caractère alphanumérique — les poser inconditionnellement rendait
    inatteignable tout mot-clé bordé de ponctuation (`Qwen…` ne matchait
    même pas son propre texte). Elles sont donc conditionnelles.

    Le `s` final optionnel réconcilie un profil rédigé au pluriel avec des
    titres d'articles souvent au singulier (`agents` ↔ `agent`). Les
    mots-clés multi-mots restent cherchés comme séquence exacte.
    """
    noyau = sans_accents(mot_cle).lower().strip()
    if not noyau:
        return False

    corps = re.escape(noyau)
    suffixe = ""
    if noyau[-1].isalnum():
        # `agents` -> `agents?` matche aussi `agent` ; `smartphone` ->
        # `smartphones?` matche aussi `smartphones`.
        corps = re.escape(noyau[:-1]) + "s?" if noyau.endswith("s") else corps + "s?"
        suffixe = r"\b"

    prefixe = r"\b" if noyau[0].isalnum() else ""
    return re.search(prefixe + corps + suffixe, texte_normalise) is not None


@dataclass(frozen=True)
class ItemScore:
    """Un item et le score qui a déterminé son rang dans le digest."""

    item: Item
    score: Score


def classer(
    items: list[Item], profil: Profil, ponderations: Ponderations = Ponderations()
) -> list[ItemScore]:
    """Score chaque item, écarte le bruit, trie par score décroissant.

    Un item sous le seuil de bruit est **écarté**, pas seulement
    rétrogradé (AC5) : le laisser en fin de classement laisserait croire
    qu'il a sa place dans le digest. Le tri Python étant stable, deux
    items à score égal conservent l'ordre dans lequel ils sont arrivés —
    aucun départage aléatoire (leçon Story 1.3).
    """
    scores = (ItemScore(item=item, score=scorer(item, profil, ponderations)) for item in items)
    retenus = [s for s in scores if s.score.valeur >= ponderations.seuil_bruit]
    retenus.sort(key=lambda s: s.score.valeur, reverse=True)
    return retenus


@dataclass(frozen=True)
class RapportClassement:
    """Ce que le classement a écarté comme bruit, par source, et la
    répartition des scores retenus — sans quoi un tri excessif serait
    invisible (AC7, leçon Story 1.3)."""

    ecartes_par_source: dict[str, int] = field(default_factory=dict)
    scores_retenus: tuple[float, ...] = ()

    @property
    def total_ecartes(self) -> int:
        return sum(self.ecartes_par_source.values())

    def resume(self) -> str:
        if not self.total_ecartes and not self.scores_retenus:
            return "Classement : aucun item scoré."

        base = f"Classement : {self.total_ecartes} item(s) écarté(s) comme bruit"
        if self.total_ecartes:
            base += f" — {_par_source(self.ecartes_par_source)}"
        if self.scores_retenus:
            base += (
                f" — scores retenus min {min(self.scores_retenus):.0f} / "
                f"max {max(self.scores_retenus):.0f} / "
                f"moyenne {sum(self.scores_retenus) / len(self.scores_retenus):.1f}"
            )
        return base


def rapport_classement(items: list[Item], classement: list[ItemScore]) -> RapportClassement:
    """Construit le compte-rendu à partir du résultat de `classer`.

    Compare l'entrée à la sortie plutôt que de reproduire le scoring : les
    items encore présents ont survécu, les autres ont été écartés comme
    bruit (`classer` ne renvoie que les survivants). La comparaison se fait
    par identité d'objet, pas par valeur : deux items distincts qui
    partageraient exactement les mêmes champs ne doivent pas se masquer
    l'un l'autre dans le compte.
    """
    retenus = {id(item_score.item) for item_score in classement}

    ecartes: Counter[str] = Counter()
    for item in items:
        if id(item) not in retenus:
            ecartes[item.source_id] += 1

    scores_retenus = tuple(item_score.score.valeur for item_score in classement)
    return RapportClassement(ecartes_par_source=dict(ecartes), scores_retenus=scores_retenus)
