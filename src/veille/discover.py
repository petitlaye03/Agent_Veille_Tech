"""Découverte de nouvelles sources (FR-14, Story 4.4).

Propose chaque semaine une source candidate, hors du socle actuel,
vérifiée active (flux valide, publication récente) juste avant d'être
suggérée — jamais une simple liste statique resservie sans contrôle.

**Aucune adoption automatique** (PRD §4.7, Non-Goals : « v1 = édition
manuelle du fichier de sources ») : ce module ne fait jamais qu'un GET en
lecture sur les candidats de `config/candidats.yaml`, jamais une écriture
sur `sources.yaml`.

**Aucun appel LLM** : l'architecture mappe `FR-14 → discover.py → AD-2,
AD-3` (connecteur, configuration), pas `AD-7` (frontière LLM unique,
réservée à `enrich/llm.py`, vérifiée mécaniquement par `grep`). Le pool de
candidats est une liste déjà vérifiée manuellement pendant la cartographie
du brief (`addendum.md`), pas une génération à la volée.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from veille.collect import CONNECTORS, DEFAULT_SOURCES_PATH
from veille.config import SourceConfig, load_sources

logger = logging.getLogger(__name__)

DEFAULT_CANDIDATS_PATH = Path("config/candidats.yaml")

# Même valeur que `health.SEUIL_SUSPECTE_JOURS` — dupliquée, pas importée
# (module volontairement indépendant, même principe que `store.py` vis-à-vis
# de `publish.py`, AD-2). Un candidat dont le dernier item date de plus de
# 30 jours n'est pas considéré « publication récente ».
SEUIL_RECENCE_JOURS = 30


@dataclass(frozen=True)
class CandidatSource:
    """Un candidat du pool, avant toute vérification de fraîcheur."""

    source: SourceConfig
    justification: str


def charger_candidats(path: str | Path | None = None) -> list[CandidatSource]:
    """Lit `config/candidats.yaml` et retourne le pool typé.

    Isolation de panne (AD-6) : un fichier absent/illisible/malformé
    dégrade en pool vide, journalisé — jamais un plantage du cycle de
    découverte. Une entrée individuellement malformée est ignorée, pas
    tout le pool (même discipline que `config.load_sources`).
    """
    chemin = Path(path) if path is not None else DEFAULT_CANDIDATS_PATH
    try:
        with open(chemin, encoding="utf-8") as f:
            brut = yaml.safe_load(f)
    except (OSError, yaml.YAMLError, UnicodeDecodeError):
        # `UnicodeDecodeError` (trouvé en revue, Acceptance Auditor) : un
        # fichier à l'encodage invalide lève cette exception avant même
        # d'atteindre `yaml.safe_load` — absente à tort du tuple initial,
        # alors que la docstring promet déjà « absent/illisible/malformé »
        # pour ce fichier.
        logger.exception("Impossible de charger %s — aucun candidat disponible.", chemin)
        return []

    if not isinstance(brut, dict):
        logger.warning(
            "%s ne contient pas un mapping YAML à la racine — aucun candidat chargé.",
            chemin,
        )
        return []

    entrees = brut.get("candidats") or []
    if not isinstance(entrees, list):
        logger.warning(
            "La clé 'candidats' de %s n'est pas une liste — aucun candidat chargé.",
            chemin,
        )
        return []

    candidats: list[CandidatSource] = []
    ids_deja_vus: set[str] = set()
    for entree in entrees:
        try:
            source = SourceConfig(**entree["source"])
            justification = entree["justification"]
            if not isinstance(justification, str):
                # Trouvé en revue (Blind Hunter) : contrairement à `source`
                # (validé par `SourceConfig`), une `justification` non-chaîne
                # (liste, mapping, nombre — copier-coller malheureux dans le
                # YAML) était silencieusement coercée par `str(...)` plutôt
                # que rejetée comme toute autre entrée malformée.
                raise TypeError("justification doit être une chaîne")
            if source.id in ids_deja_vus:
                # Trouvé en revue (Edge Case Hunter) : deux entrées partageant
                # le même `id` survivraient toutes les deux dans le pool sans
                # avertissement, doublant silencieusement les chances de ce
                # candidat dans la rotation.
                logger.warning(
                    "Candidat en double ignoré dans %s (id déjà chargé) : '%s'",
                    chemin,
                    source.id,
                )
                continue
            ids_deja_vus.add(source.id)
            candidats.append(CandidatSource(source=source, justification=justification))
        except (TypeError, AttributeError, KeyError):
            logger.warning(
                "Entrée de candidat invalide dans %s, ignorée : %r", chemin, entree
            )

    return candidats


def verifier_candidat(candidat: CandidatSource, maintenant: datetime | None = None) -> bool:
    """Vérifie qu'un candidat est réellement actif : flux valide (fetch
    réussi) et publication récente (dernier item à moins de
    `SEUIL_RECENCE_JOURS` jours de `maintenant`).

    Réutilise `collect.CONNECTORS` tel quel (AD-2) — un candidat qui
    échouerait à ce fetch échouerait de la même façon s'il était adopté
    demain, même mécanisme que la collecte nocturne.

    `maintenant` est un paramètre explicite (`None` par défaut → horloge
    réelle), jamais lu directement en interne — testable déterministe,
    même discipline que `health.py`. L'horloge réelle n'est capturée
    qu'**après** le fetch (trouvé pendant l'implémentation de cette même
    revue, avant tout commit — pas seulement documenté après coup) :
    la capturer avant, comme un premier brouillon le faisait, ferait
    paraître « du futur » tout item qu'un connecteur daterait via son
    propre `datetime.now()` interne (repli sur date illisible, voir
    `deferred-work.md`, Story 2.1) — puisque ce fetch prend un temps non
    nul, ce `datetime.now()` interne au connecteur serait mécaniquement
    postérieur à un `maintenant` déjà figé avant l'appel, rejetant à tort
    un item réellement frais comme « daté dans le futur ».

    Ne lève jamais (AD-6) : toute panne du connecteur ou de comparaison de
    date dégrade en `False`, jamais une levée qui remonterait à l'appelant.
    """
    connecteur = CONNECTORS.get(candidat.source.type)
    if connecteur is None:
        return False

    try:
        items = connecteur(candidat.source)
    except Exception:  # noqa: BLE001 — isolation totale (AD-6)
        logger.exception(
            "Échec de la vérification du candidat '%s' — non proposé cette semaine.",
            candidat.source.id,
        )
        return False

    if not items:
        return False

    if maintenant is None:
        maintenant = datetime.now(timezone.utc)

    try:
        plus_recent = max(item.date_publication for item in items)
        age_jours = (maintenant - plus_recent).days
        # `0 <=` (trouvé en revue, Blind Hunter) : sans cette borne, un item
        # daté dans le futur par rapport à `maintenant` (horloge décalée côté
        # source, ou repli `datetime.now()` d'un connecteur sur une date
        # illisible — voir `deferred-work.md`, Story 2.1) produirait un
        # `age_jours` négatif, toujours `<= SEUIL_RECENCE_JOURS` — accepté
        # comme « frais » sans jamais être questionné, contrairement à
        # `health.py` qui traite ce genre d'anomalie de date comme suspecte.
        return 0 <= age_jours <= SEUIL_RECENCE_JOURS
    except Exception:  # noqa: BLE001 — isolation totale (AD-6)
        logger.exception(
            "Échec du calcul de fraîcheur pour le candidat '%s' — non proposé cette semaine.",
            candidat.source.id,
        )
        return False


def proposer_source(
    candidats_path: str | Path | None = None,
    sources_path: str | Path | None = None,
    aujourdhui: date | None = None,
) -> CandidatSource | None:
    """Propose un candidat non encore adopté et vérifié actif cette
    semaine.

    Exclut tout candidat déjà présent dans `sources.yaml` — par `id` **ou**
    par `url` (trouvé en revue, Edge Case Hunter : un candidat adopté sous
    un `id` différent de celui de `config/candidats.yaml`, ce que rien
    n'empêche, continuerait sinon d'être « redécouvert » indéfiniment ; la
    même URL de flux, elle, ne ment pas). Rotation **déterministe** par
    numéro de semaine ISO sur le pool **complet**, pas sur le pool déjà
    filtré des candidats disponibles (corrigé en revue, Blind Hunter —
    constat le plus sérieux de cette revue) : `aujourdhui.isocalendar().week
    % len(candidats)` fixe le point de départ sur la liste chargée telle
    quelle, chaque candidat est essayé à partir de là (en bouclant),
    ignoré silencieusement s'il est déjà adopté, jusqu'à en trouver un qui
    passe `verifier_candidat`. Baser le calcul sur la taille du pool
    **après** exclusion (comme le faisait la première version) rompait
    l'invariant documenté ailleurs (« reproduit le même candidat tant qu'il
    reste vérifié actif ») : adopter n'importe quel candidat en cours de
    semaine — même sans rapport avec celui actuellement proposé — réduisait
    la taille du pool disponible et pouvait donc décaler le point de départ
    calculé, faisant silencieusement changer le candidat mis en avant avant
    la fin de la semaine.

    Ne lève jamais (AD-6) : dégrade en `None` (rien à proposer cette
    semaine) plutôt que de faire perdre le cycle de découverte en cours.
    """
    if aujourdhui is None:
        aujourdhui = datetime.now(timezone.utc).date()

    try:
        candidats = charger_candidats(candidats_path)
        if not candidats:
            return None

        sources_path_resolu = (
            DEFAULT_SOURCES_PATH if sources_path is None else sources_path
        )
        sources_configurees = load_sources(sources_path_resolu)
        ids_adoptes = {s.id for s in sources_configurees}
        urls_adoptees = {s.url for s in sources_configurees}

        depart = aujourdhui.isocalendar().week % len(candidats)
        for decalage in range(len(candidats)):
            candidat = candidats[(depart + decalage) % len(candidats)]
            if candidat.source.id in ids_adoptes or candidat.source.url in urls_adoptees:
                continue
            if verifier_candidat(candidat):
                return candidat

        return None
    except Exception:  # noqa: BLE001 — filet de sécurité de dernier recours (AD-6)
        logger.exception("Échec de la proposition de nouvelle source.")
        return None
