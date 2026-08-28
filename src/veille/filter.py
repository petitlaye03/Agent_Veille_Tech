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
DEFAULT_QUOTAS_PATH = chemin_config("quotas.yaml")

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
            f"source — {_ventilation(self.ecartes_par_source)}"
        )


def _avertir_cles_inconnues(
    categories: dict, connues: tuple[str, ...], chemin, label: str
) -> None:
    """Signale une clé de configuration non reconnue plutôt que de la perdre
    en silence. Sans ce garde-fou, une faute de frappe dans le **nom** d'un
    réglage (`pour_le_metier` mal orthographié) est strictement plus
    discrète qu'une faute dans sa **valeur** (`apprendre: beaucoup`), qui
    est déjà journalisée — asymétrie trouvée en revue de la Story 1.5.
    """
    for cle in sorted(set(categories) - set(connues)):
        logger.warning(
            "%s '%s' inconnu(e) dans %s, ignoré(e) — attendu parmi : %s.",
            label,
            cle,
            chemin,
            ", ".join(connues),
        )


def _ventilation(comptes: dict[str, int]) -> str:
    """Ventilation nommée d'un compte de pertes, sur le modèle de
    `RapportDedoublonnage.resume()`. Générique : sert aussi bien à ventiler
    par source (signal, bruit) que par registre (quotas) — un total seul ne
    dit pas *où* le tri a été agressif, et c'est précisément ce qu'il faut
    voir pour corriger un réglage trop serré.
    """
    return ", ".join(
        f"{cle} (-{n})"
        for cle, n in sorted(comptes.items(), key=lambda x: (-x[1], x[0]))
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

    # Écart minimal entre le meilleur score du jour et le second pour que
    # l'entrée soit recommandée (Story 1.7, FR-8). Même ordre de grandeur
    # qu'une seule correspondance `prioritaire` : se démarquer d'un bruit de
    # mesure, pas d'un simple thème de plus.
    marge_recommandation: float = 10.0


def charger_ponderations(chemin: str | Path = DEFAULT_SCORING_PATH) -> Ponderations:
    """Lit `config/scoring.yaml`. Ne lève jamais : un fichier absent,
    illisible, ou dont les valeurs ne sont pas numériques, dégrade vers les
    pondérations par défaut plutôt que de faire échouer le classement."""
    try:
        with open(chemin, encoding="utf-8") as f:
            brut = yaml.safe_load(f)
    except (OSError, TypeError, UnicodeDecodeError, yaml.YAMLError):
        # `UnicodeDecodeError` fait partie du contrat : le fichier contient
        # des accents, et un éditeur mal configuré suffit à le réenregistrer
        # en latin-1. `TypeError` couvre un appel direct avec `chemin=None` —
        # improbable via `collecter()` (qui résout toujours un chemin par
        # défaut), mais cette fonction est publique et sa docstring promet
        # de ne jamais lever. Cette fonction s'exécute hors de l'isolation de
        # panne par source (AD-6) — y laisser filer une exception coûterait
        # la nuit entière, sources saines comprises.
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
    # `.get(..., {})` et non `.get(...) or {}` : la seconde forme masquerait
    # une clé présente mais falsy-et-mal-typée (`ponderations: 0`) derrière
    # le même silence qu'une clé absente, alors qu'une valeur véritablement
    # mal typée mais truthy (`ponderations: 5`) est, elle, déjà journalisée
    # juste en dessous — asymétrie trouvée en revue de la Story 1.5.
    categories = brut.get("ponderations", {})
    if not isinstance(categories, dict):
        logger.warning(
            "La clé 'ponderations' de %s n'est pas un mapping — valeurs par défaut.",
            chemin,
        )
        return Ponderations()

    _avertir_cles_inconnues(
        categories,
        ("prioritaire", "signal_fort", "domaine", "secondaire", "bruit"),
        chemin,
        "Catégorie de pondération",
    )

    valeurs = {}
    for nom in ("prioritaire", "signal_fort", "domaine", "secondaire", "bruit"):
        valeurs[nom] = _ponderation(categories, nom, getattr(defauts, nom), chemin)
    # `seuil_bruit` et `marge_recommandation` vivent à la racine du fichier,
    # pas sous `ponderations:` — ce sont des seuils globaux de comparaison,
    # pas des pondérations par catégorie (Story 1.7).
    valeurs["seuil_bruit"] = _ponderation(
        brut, "seuil_bruit", defauts.seuil_bruit, chemin
    )
    valeurs["marge_recommandation"] = _ponderation(
        brut,
        "marge_recommandation",
        defauts.marge_recommandation,
        chemin,
        positif_strict=True,
    )
    return Ponderations(**valeurs)


def _ponderation(
    source: dict, nom: str, defaut: float, chemin, positif_strict: bool = False
) -> float:
    """Lit une pondération, en retombant sur son défaut si elle est inutilisable.

    Le repli est **par valeur** et non global : une seule faute de frappe ne
    doit pas faire perdre les autres réglages du fichier. `nan` est rejeté
    en particulier — toute comparaison à `nan` étant fausse, un `seuil_bruit`
    à `nan` viderait le digest sans le moindre avertissement.

    `positif_strict` (Story 1.7, trouvé en revue — unanime sur les 3 couches) :
    `marge_recommandation` n'a de sens que strictement positive — à `0`,
    `premier.score.valeur - second.score.valeur >= 0` est toujours vrai
    (`classement` est trié décroissant), donc une marge nulle romprait la
    garantie d'AC2 (« égalité jamais recommandée ») en recommandant quelqu'un
    tous les jours. `bruit`/`seuil_bruit` restent volontairement exclus de ce
    contrôle : eux sont légitimement négatifs.
    """
    if nom not in source:
        return defaut

    converti = to_float_fini(source[nom])
    if converti is None or (positif_strict and converti <= 0):
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
            base += f" — {_ventilation(self.ecartes_par_source)}"
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

    Précondition non vérifiée (relevée en revue de la Story 1.5) : un même
    objet `Item` référencé plusieurs fois dans `classement` ferait
    sur-compter les retenus. Non atteignable via `collecter()` — `dedup.py`
    garantit qu'un `Item` gagnant n'apparaît qu'une fois — donc non corrigé
    ici ; à traiter si cette fonction est un jour appelée hors de ce chemin.
    """
    retenus = {id(item_score.item) for item_score in classement}

    ecartes: Counter[str] = Counter()
    for item in items:
        if id(item) not in retenus:
            ecartes[item.source_id] += 1

    scores_retenus = tuple(item_score.score.valeur for item_score in classement)
    return RapportClassement(ecartes_par_source=dict(ecartes), scores_retenus=scores_retenus)


@dataclass(frozen=True)
class Quotas:
    """Quotas d'items retenus par registre (AD-3, FR-6) : déclarés en
    configuration (`config/quotas.yaml`), jamais en dur. Ces valeurs ne
    servent que de repli quand le fichier est absent ou illisible."""

    apprendre: int = 3
    ce_qui_bouge: int = 3
    pour_le_metier: int = 2


# Ordre canonique des registres — utilisé pour les quotas ici, et réutilisé
# tel quel par `render.py` (Story 1.8) pour l'ordre d'affichage des sections
# de la page publiée. Nom public (pas de préfixe `_`) précisément parce que
# c'est désormais un contrat inter-module, pas un détail interne à ce fichier.
CHAMPS_QUOTAS = ("apprendre", "ce_qui_bouge", "pour_le_metier")


def charger_quotas(chemin: str | Path = DEFAULT_QUOTAS_PATH) -> Quotas:
    """Lit `config/quotas.yaml`. Ne lève jamais : mêmes garde-fous que
    `charger_ponderations` — fichier absent, illisible (y compris
    `UnicodeDecodeError`), ou dont une valeur n'est pas un entier positif,
    dégrade vers les quotas par défaut plutôt que de faire échouer la
    répartition."""
    try:
        with open(chemin, encoding="utf-8") as f:
            brut = yaml.safe_load(f)
    except (OSError, TypeError, UnicodeDecodeError, yaml.YAMLError):
        # `TypeError` couvre un appel direct avec `chemin=None` : improbable
        # via `collecter()` (qui résout toujours un chemin par défaut), mais
        # cette fonction est publique et sa docstring promet de ne jamais
        # lever.
        logger.warning("Quotas illisibles (%s) — valeurs par défaut.", chemin)
        return Quotas()

    if not isinstance(brut, dict):
        logger.warning(
            "%s ne contient pas un mapping YAML à la racine — valeurs par défaut.",
            chemin,
        )
        return Quotas()

    defauts = Quotas()
    # `.get(..., {})` et non `.get(...) or {}` : voir la note équivalente
    # dans `charger_ponderations` — un `quotas: 0` doit être signalé comme
    # mal typé, pas confondu avec une clé absente.
    categories = brut.get("quotas", {})
    if not isinstance(categories, dict):
        logger.warning(
            "La clé 'quotas' de %s n'est pas un mapping — valeurs par défaut.",
            chemin,
        )
        return Quotas()

    _avertir_cles_inconnues(categories, CHAMPS_QUOTAS, chemin, "Registre")

    valeurs = {
        nom: _quota(categories, nom, getattr(defauts, nom), chemin)
        for nom in CHAMPS_QUOTAS
    }
    return Quotas(**valeurs)


def _quota(source: dict, nom: str, defaut: int, chemin) -> int:
    """Lit un quota, en retombant sur son défaut si inutilisable.

    Repli **par valeur**, pas global (leçon Story 1.4) : une seule faute de
    frappe ne doit pas réinitialiser les autres quotas du fichier.
    """
    if nom not in source:
        return defaut

    converti = _to_int_positif(source[nom])
    if converti is None:
        logger.warning(
            "Quota '%s' inutilisable (%r) dans %s — valeur par défaut (%s).",
            nom,
            source[nom],
            chemin,
            defaut,
        )
        return defaut
    return converti


def _to_int_positif(valeur) -> int | None:
    """Convertit en entier positif ou nul, ou `None` si inutilisable.

    Rejette les booléens (`apprendre: yes` vaut `True` en YAML 1.1, ce qui
    donnerait silencieusement un quota de 1), les valeurs non entières
    (`2.5`), et les valeurs négatives — un quota négatif n'a pas de sens et
    romprait le comptage de `repartir_par_quotas`.
    """
    if isinstance(valeur, bool):
        return None
    if isinstance(valeur, int):
        return valeur if valeur >= 0 else None
    if isinstance(valeur, float):
        return int(valeur) if valeur.is_integer() and valeur >= 0 else None
    try:
        entier = int(str(valeur))
    except (TypeError, ValueError):
        return None
    return entier if entier >= 0 else None


def repartir_par_quotas(classement: list[ItemScore], quotas: Quotas) -> list[ItemScore]:
    """Répartit un classement déjà trié en respectant un quota par registre.

    Un seul passage, dans l'ordre où `classement` arrive : `classer()` l'a
    déjà trié par score décroissant, donc garder les N premiers items d'un
    registre revient à garder ses N mieux notés, sans second tri.

    Un registre absent de `Quotas` — faute de frappe, section oubliée — est
    **conservé sans limite**, pas écarté (AC6) : l'absence de réglage n'est
    pas une insuffisance de contenu, même principe que le signal absent en
    Story 1.4 (AC2).
    """
    limites = {nom: getattr(quotas, nom) for nom in CHAMPS_QUOTAS}

    retenus: list[ItemScore] = []
    comptes: Counter[str] = Counter()
    avertis: set[str] = set()

    for item_score in classement:
        registre = item_score.item.registre
        limite = limites.get(registre)

        if limite is None:
            if registre not in avertis:
                if registre is None:
                    # Distinct du cas ci-dessous : ici la donnée elle-même
                    # est probablement mal formée en amont (`registre: null`
                    # dans `sources.yaml`), pas un simple registre non réglé.
                    logger.warning(
                        "Item sans registre défini (source mal configurée en "
                        "amont ?) — conservé sans limite."
                    )
                else:
                    logger.warning(
                        "Registre '%s' absent de la configuration de quotas — "
                        "ses items sont conservés sans limite.",
                        registre,
                    )
                avertis.add(registre)
            retenus.append(item_score)
            continue

        if comptes[registre] < limite:
            retenus.append(item_score)
            comptes[registre] += 1

    return retenus


@dataclass(frozen=True)
class RapportQuotas:
    """Ce que la répartition par quotas a retenu et écarté, par registre —
    sans quoi un quota trop serré serait invisible (AC5).

    `ecartes_par_source` est un détail supplémentaire, non exigé par l'AC
    (qui ne demande que « par registre ») : sans lui, le diagnostic « source
    absorbée » de `collect.py` ne pourrait pas nommer un quota dépassé comme
    cause possible, et retomberait à tort sur « cause indéterminée ».
    """

    retenus_par_registre: dict[str, int] = field(default_factory=dict)
    ecartes_par_registre: dict[str, int] = field(default_factory=dict)
    ecartes_par_source: dict[str, int] = field(default_factory=dict)

    @property
    def total_ecartes(self) -> int:
        return sum(self.ecartes_par_registre.values())

    def resume(self) -> str:
        if not self.retenus_par_registre and not self.total_ecartes:
            return "Quotas : aucun item réparti."

        if self.retenus_par_registre:
            retenus = ", ".join(
                f"{registre}={n}" for registre, n in sorted(self.retenus_par_registre.items())
            )
            base = f"Quotas : {retenus} retenu(s)"
        else:
            # Un quota à 0 peut vider entièrement tout registre présent
            # cette nuit-là : `retenus_par_registre` est alors vide alors
            # que `total_ecartes` ne l'est pas — cas distinct du « rien à
            # rapporter » ci-dessus (trouvé en revue de la Story 1.5).
            base = "Quotas : aucun item retenu"
        if self.total_ecartes:
            base += (
                f" — {self.total_ecartes} écarté(s) par dépassement de quota "
                f"({_ventilation(self.ecartes_par_registre)})"
            )
        return base


def rapport_quotas(
    classement: list[ItemScore], repartition: list[ItemScore]
) -> RapportQuotas:
    """Construit le compte-rendu à partir du résultat de `repartir_par_quotas`.

    Même principe que `rapport_classement` (Story 1.4) : comparer l'entrée à
    la sortie par identité d'objet plutôt que de reproduire la logique de
    quota — et la même précondition non vérifiée s'applique (voir sa
    docstring) : non atteignable via `collecter()` aujourd'hui.
    """
    retenus_ids = {id(item_score.item) for item_score in repartition}

    retenus: Counter[str] = Counter()
    ecartes: Counter[str] = Counter()
    ecartes_source: Counter[str] = Counter()
    for item_score in classement:
        item = item_score.item
        if id(item) in retenus_ids:
            retenus[item.registre] += 1
        else:
            ecartes[item.registre] += 1
            ecartes_source[item.source_id] += 1

    return RapportQuotas(
        retenus_par_registre=dict(retenus),
        ecartes_par_registre=dict(ecartes),
        ecartes_par_source=dict(ecartes_source),
    )
