"""Santé des sources — fraîcheur et mise en sommeil (AD-5, AD-6, FR-12/13, Story 4.1).

Partage le même fichier SQLite que `store.py` (AD-5 : « un fichier SQLite
local est la seule source de vérité pour... le "déjà vu par source" et
l'État d'une Source ») — ce module ne possède aucun schéma ni connexion en
propre, seulement la logique de transition d'état sur la table
`sante_source` déjà créée par `store.ouvrir()`.

Deux usages distincts, appelés depuis deux endroits différents — **et
c'est délibéré**, précision apportée en revue (Acceptance Auditor,
question soulevée sur la portée exacte d'AD-5 : « seuls le contrôle de
santé et l'étape publish écrivent le store ») :
- **`enregistrer_activite`** — appelée chaque nuit par `collect.collecter()`
  après la collecte de chaque source, mais ne touche **jamais** `etat` —
  seulement `dernier_item_vu`, une observation brute (« un item de cette
  source a été vu à telle date »), pas un jugement de santé. La lecture
  d'AD-5 retenue ici : « l'État d'une Source » désigne le jugement
  lui-même (`etat` : `active`/`suspecte`/`en_sommeil`), pas la donnée brute
  qui l'alimente — même distinction que pour le « déjà vu », où
  `marquer_vus()` (Story 3.4) est la seule fonction à écrire les clés,
  mais où `filtrer_deja_vus()` (appelée depuis `collect.py`, pas depuis
  l'étape `publish`) en a le droit de lecture. `collect.py` ne construit
  jamais lui-même de requête SQL sur `sante_source` : il appelle une
  fonction de ce module, qui reste seule responsable de la logique et du
  schéma d'écriture — un seul propriétaire du *comment*, même si l'appel
  vient de plusieurs endroits (même principe que `store.marquer_vus()`,
  appelée par `pipeline.py`, pas par `store.py` lui-même).
- **`evaluer_fraicheur`**/**`sources_en_sommeil`** — la première, seule
  fonction de tout le projet à écrire `etat` (« le contrôle de santé »
  d'AD-5, au sens strict), est appelée par le contrôle de fraîcheur
  hebdomadaire (`pipeline.controler_fraicheur`) ; la seconde, purement en
  lecture, par `collect.collecter()` avant chaque tentative de collecte
  (une source en sommeil n'est plus interrogée).

Isolation totale (AD-6) : aucune fonction de ce module ne lève — une panne
de lecture/écriture dégrade (aucune source ignorée par excès de prudence,
aucune transition appliquée) plutôt que de faire perdre la collecte ou le
contrôle en cours. Isolée **par source** dans `evaluer_fraicheur` (trouvé
en revue) : une seule ligne corrompue ne doit jamais bloquer l'évaluation
des autres sources du lot.
"""

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from veille.models import Item

logger = logging.getLogger(__name__)

# « 3 mois » (formulation de l'AC) équivaut à 90 jours ici — aucune notion
# de mois n'existe ailleurs dans le projet, toutes les fenêtres temporelles
# sont exprimées en jours/secondes ; 90 jours est l'équivalence la plus
# directe et reste facilement testable.
SEUIL_SUSPECTE_JOURS = 30
SEUIL_SOMMEIL_JOURS = 90

ETAT_ACTIF = "active"
ETAT_SUSPECTE = "suspecte"
ETAT_SOMMEIL = "en_sommeil"


@dataclass(frozen=True)
class RapportSante:
    """Ce que le dernier contrôle de fraîcheur a changé — même patron que
    les autres rapports du projet (`RapportFiltrageSignal`, `RapportDejaVu`) :
    un dict vide plutôt qu'un booléen, pour que la Story 4.3 (récapitulatif)
    puisse consommer le détail sans qu'il ait à être recalculé."""

    transitions: dict[str, tuple[str, str]] = field(default_factory=dict)

    def resume(self) -> str:
        if not self.transitions:
            return "Contrôle de fraîcheur : aucun changement d'état."
        detail = ", ".join(
            f"{source_id} ({ancien}→{nouveau})"
            for source_id, (ancien, nouveau) in sorted(self.transitions.items())
        )
        return f"Contrôle de fraîcheur : {len(self.transitions)} changement(s) d'état — {detail}"


def enregistrer_activite(
    source_id: str,
    items: list[Item],
    conn: sqlite3.Connection,
    maintenant: datetime | None = None,
) -> None:
    """Met à jour `dernier_item_vu` pour `source_id` avec le plus récent
    entre la valeur déjà connue et le plus récent `date_publication`
    **plausible** (pas futur) de `items` — ne régresse jamais (une nuit
    sans nouvel item ne doit jamais rajeunir artificiellement une source
    qui, elle, n'a rien de neuf).

    Un item dont `date_publication` est postérieure à `maintenant` (horloge
    d'appel réelle du run, un flux malformé ou un bug d'horloge côté source
    peut en produire — trouvé en revue) est **ignoré** pour ce calcul :
    sans ce filtre, la règle « ne régresse jamais » figerait `dernier_item_vu`
    dans le futur de façon permanente, rendant `age_jours` négatif pour
    toujours dans `evaluer_fraicheur` — une source resterait alors `active`
    indéfiniment, y compris si elle s'était réellement tue depuis. Si
    aucun item de `items` n'est plausible, l'appel se comporte comme si
    `items` était vide (aucune mise à jour). `maintenant` est un paramètre
    explicite (`None` par défaut → horloge réelle), jamais lu directement
    en interne — testable déterministe, même discipline qu'`evaluer_fraicheur`.

    Ne touche jamais `etat` : la transition d'état est le rôle exclusif
    d'`evaluer_fraicheur` (contrôle hebdomadaire), pas de la collecte
    nocturne — une source `suspecte` reste `suspecte` tant que le contrôle
    hebdomadaire suivant ne l'a pas réévaluée, même si elle vient de
    produire un nouvel item.

    Ne fait rien si `items` est vide (rien de nouveau à enregistrer) et ne
    lève jamais (AD-6) : une panne ici dégrade en laissant l'état de santé
    inchangé, jamais en faisant perdre la collecte.
    """
    if not items:
        return
    try:
        if maintenant is None:
            maintenant = datetime.now(timezone.utc)

        candidats = [item.date_publication for item in items if item.date_publication <= maintenant]
        if not candidats:
            return
        plus_recent = max(candidats)

        ligne = conn.execute(
            "SELECT dernier_item_vu FROM sante_source WHERE source_id = ?", (source_id,)
        ).fetchone()
        existant = None
        if ligne is not None and ligne[0]:
            try:
                existant = datetime.fromisoformat(ligne[0])
            except ValueError:
                existant = None

        nouvelle_valeur = plus_recent if existant is None or plus_recent > existant else existant

        conn.execute(
            "INSERT INTO sante_source (source_id, dernier_item_vu) VALUES (?, ?) "
            "ON CONFLICT(source_id) DO UPDATE SET dernier_item_vu = excluded.dernier_item_vu",
            (source_id, nouvelle_valeur.isoformat()),
        )
        conn.commit()
    except Exception:  # noqa: BLE001 — isolation totale (AD-6)
        logger.exception(
            "Échec de l'enregistrement d'activité pour la source '%s' — état de santé inchangé.",
            source_id,
        )


def evaluer_fraicheur(sources, conn: sqlite3.Connection, aujourdhui: date) -> RapportSante:
    """Réévalue l'état de chaque source de `sources` (itérable d'objets
    portant un `.id`, typiquement `list[SourceConfig]`) à partir de
    `dernier_item_vu` : `> SEUIL_SUSPECTE_JOURS` jours → `suspecte`,
    `> SEUIL_SOMMEIL_JOURS` jours → `en_sommeil`, sinon `active` (une
    source `suspecte` redevenue fraîche repasse `active`).

    `aujourdhui` est un paramètre explicite, jamais lu en interne via
    `datetime.now()` — un contrôle de fraîcheur doit être testable
    déterministe, pas dépendre de l'horloge réelle au moment du test
    (même discipline que la Story 3.3, leçon #47 du journal des décisions).

    Une source sans `dernier_item_vu` connu (jamais encore collectée, ou
    jamais encore enregistrée par `enregistrer_activite`) n'est **jamais**
    présumée anomale — l'absence de donnée n'est pas une évidence de
    panne (même principe que le seuil de signal, Story 1.4).

    Ne lève jamais (AD-6) : dégrade en renvoyant un rapport vide (aucune
    transition appliquée) plutôt que de faire perdre le contrôle en cours.

    Isolation **par source**, pas seulement globale (trouvé en revue) :
    une seule ligne corrompue (`dernier_item_vu` illisible, écriture
    manuelle malformée) ne doit jamais empêcher l'évaluation de toutes les
    autres sources — sans cette isolation, une seule source à l'état
    invalide aurait bloqué la totalité du contrôle hebdomadaire, chaque
    semaine, indéfiniment, sans qu'aucun journal ne nomme la source
    fautive (même philosophie qu'AD-6 pour `_fetch_one`, jamais appliquée
    jusqu'ici à ce module).
    """
    transitions: dict[str, tuple[str, str]] = {}
    for source in sources:
        try:
            ligne = conn.execute(
                "SELECT dernier_item_vu, etat FROM sante_source WHERE source_id = ?",
                (source.id,),
            ).fetchone()
            if ligne is None or ligne[0] is None:
                continue

            dernier_item_vu_str, etat_actuel = ligne
            dernier_item_vu = datetime.fromisoformat(dernier_item_vu_str)

            age_jours = (aujourdhui - dernier_item_vu.date()).days
            if age_jours > SEUIL_SOMMEIL_JOURS:
                nouvel_etat = ETAT_SOMMEIL
            elif age_jours > SEUIL_SUSPECTE_JOURS:
                nouvel_etat = ETAT_SUSPECTE
            else:
                nouvel_etat = ETAT_ACTIF

            if nouvel_etat != etat_actuel:
                conn.execute(
                    "UPDATE sante_source SET etat = ? WHERE source_id = ?",
                    (nouvel_etat, source.id),
                )
                transitions[source.id] = (etat_actuel, nouvel_etat)
        except Exception:  # noqa: BLE001 — isolation par source (AD-6, trouvé en revue)
            logger.exception(
                "Échec de l'évaluation de la fraîcheur pour la source '%s' — "
                "état inchangé pour cette source cette semaine.",
                source.id,
            )
            continue

    try:
        if transitions:
            conn.commit()
    except Exception:  # noqa: BLE001 — isolation totale (AD-6)
        logger.exception("Échec de la validation du contrôle de fraîcheur — état de santé inchangé pour cette exécution.")
        return RapportSante()

    return RapportSante(transitions=transitions)


def sources_en_sommeil(conn: sqlite3.Connection) -> set[str]:
    """Identifiants des sources actuellement `en_sommeil` — consultée par
    `collect.collecter()` avant chaque tentative de collecte pour ne plus
    interroger ces sources. Ne lève jamais : dégrade en renvoyant un
    ensemble vide (aucune source ignorée par excès de prudence) plutôt que
    de faire perdre la collecte."""
    try:
        lignes = conn.execute(
            "SELECT source_id FROM sante_source WHERE etat = ?", (ETAT_SOMMEIL,)
        ).fetchall()
        return {ligne[0] for ligne in lignes}
    except Exception:  # noqa: BLE001 — isolation totale (AD-6)
        logger.exception("Échec de la lecture des sources en sommeil — aucune source ignorée par prudence.")
        return set()
