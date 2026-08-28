"""Orchestration de la collecte (FR-1, FR-2).

Charge le socle de sources, dispatche chaque source vers le connecteur
correspondant à son type, et consolide les résultats. Isole les pannes
par source (AD-6) : une source qui échoue ne doit jamais interrompre la
collecte des autres.

Rend compte **par source** : une isolation de panne silencieuse transforme
toute défaillance en sortie vide indiscernable d'une nuit calme. Le rapport
distingue trois états — collectée, muette (zéro item sans erreur), en échec.
"""

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from veille.config import SourceConfig, load_sources
from veille.connectors import json_connector, rss_connector, scrape_connector
from veille.dedup import RapportDedoublonnage, dedupliquer
from veille.filter import (
    DEFAULT_QUOTAS_PATH,
    DEFAULT_SCORING_PATH,
    ItemScore,
    RapportClassement,
    RapportFiltrageSignal,
    RapportQuotas,
    charger_ponderations,
    charger_quotas,
    classer,
    filtrer_par_signal,
    rapport_classement,
    rapport_quotas,
    repartir_par_quotas,
)
from veille.models import Item
from veille.profil import DEFAULT_PROFIL_PATH, charger_profil

logger = logging.getLogger(__name__)

DEFAULT_SOURCES_PATH = Path("config/sources.yaml")

# Marge sous laquelle une date de publication est considérée comme ayant été
# posée par défaut à l'heure de collecte, faute d'avoir pu être lue.
MARGE_DATE_APPROXIMATIVE = timedelta(seconds=90)

# Dispatch par type de source. Ajouter un connecteur ne modifie que cette
# table, jamais la boucle d'orchestration ci-dessous ; ajouter une source
# d'un type déjà présent ne modifie aucun code, seulement la configuration.
CONNECTORS = {
    "rss": rss_connector.fetch,
    "json": json_connector.fetch,
    "scrape": scrape_connector.fetch,
}


@dataclass(frozen=True)
class RapportSource:
    """Ce qu'une source a réellement produit pendant un run.

    Deux comptes distincts, parce qu'ils répondent à deux questions
    différentes : ce que la source a **collecté**, et ce qui a **survécu**
    pour atteindre le digest — dédoublonnage, seuil de signal, scoring par
    profil et quotas par registre confondus (`nb_retenus` désigne la
    contribution finale, redéfini en Story 1.4 puis étendu aux quotas en
    Story 1.5 — un seul sens à ce champ, jamais deux qui coexistent).
    """

    source_id: str
    type: str
    nb_items: int
    nb_retenus: int = 0
    nb_dates_approximatives: int = 0
    echec: str = ""

    @property
    def est_muette(self) -> bool:
        """N'a rien collecté du tout, sans erreur — panne insidieuse."""
        return not self.echec and self.nb_items == 0

    @property
    def est_absorbee(self) -> bool:
        """A collecté, mais rien n'a atteint le digest.

        Le motif peut être le dédoublonnage, le seuil de signal, le scoring
        ou un quota de registre dépassé : `nb_retenus` les agrège tous.
        C'est au journal de nommer la cause — la déduire du seul
        dédoublonnage enverrait chercher un doublon qui n'existe pas.
        """
        return not self.echec and self.nb_items > 0 and self.nb_retenus == 0


@dataclass(frozen=True)
class ResultatCollecte:
    """Items collectés, accompagnés de ce qui s'est passé pour chaque source."""

    items: list[Item] = field(default_factory=list)
    rapports: list[RapportSource] = field(default_factory=list)
    dedoublonnage: RapportDedoublonnage = field(default_factory=RapportDedoublonnage)
    filtrage_signal: RapportFiltrageSignal = field(default_factory=RapportFiltrageSignal)
    classement: RapportClassement = field(default_factory=RapportClassement)
    quotas: RapportQuotas = field(default_factory=RapportQuotas)

    # Le classement filtré par quota, exposé tel quel (Story 1.8) : sans ce
    # champ, `pipeline.py` n'a aucun moyen de fournir un `classement` à
    # `enrich.llm.marquer_recommandation` (FR-8), qui exige explicitement la
    # population filtrée par quota, pas le classement brut de `classer()`
    # (précisé en revue de la Story 1.7). Ferme la dette « Score.valeur/motifs
    # calculé puis jeté » documentée depuis la revue de la Story 1.4.
    resultats_repartis: list[ItemScore] = field(default_factory=list)

    # Un profil sans le moindre mot-clé neutralise le classement en entier.
    # Le récapitulatif d'une telle nuit est sinon indiscernable de celui
    # d'une nuit filtrée normalement.
    profil_neutre: bool = False

    @property
    def sources_en_echec(self) -> list[RapportSource]:
        return [r for r in self.rapports if r.echec]

    @property
    def sources_muettes(self) -> list[RapportSource]:
        return [r for r in self.rapports if r.est_muette]

    @property
    def sources_absorbees(self) -> list[RapportSource]:
        return [r for r in self.rapports if r.est_absorbee]

    def resume(self) -> str:
        """Récapitulatif lisible et autosuffisant, anomalies en évidence.

        Les colonnes indiquent la contribution **au digest**, et le détail
        du dédoublonnage figure ici plutôt que dans un journal séparé : le
        récapitulatif doit se lire seul.
        """
        if not self.rapports:
            return "Aucune source configurée."

        entete = f"Collecte : {len(self.items)} item(s) depuis {len(self.rapports)} source(s)"
        collectes = sum(r.nb_items for r in self.rapports)
        # Le total collecté figure dès qu'il diffère du total retenu, quelle
        # que soit l'étape responsable : le rapporter seulement en cas de
        # doublon masquait les pertes dues au seuil de signal et au bruit.
        if collectes != len(self.items):
            pertes = []
            if self.dedoublonnage.total_ecartes:
                pertes.append(f"{self.dedoublonnage.total_ecartes} doublon(s)")
            if self.filtrage_signal.total_ecartes:
                pertes.append(f"{self.filtrage_signal.total_ecartes} sous le seuil")
            if self.classement.total_ecartes:
                pertes.append(f"{self.classement.total_ecartes} bruit")
            if self.quotas.total_ecartes:
                pertes.append(f"{self.quotas.total_ecartes} hors quota")
            entete += f" — {collectes} collecté(s)"
            if pertes:
                entete += f", écartés : {', '.join(pertes)}"
        lignes = [entete]

        for rapport in sorted(self.rapports, key=lambda r: (-r.nb_retenus, -r.nb_items)):
            if rapport.echec:
                etat = f"ÉCHEC — {rapport.echec}"
            elif rapport.est_muette:
                etat = "MUETTE — aucun item, sans erreur"
            elif rapport.est_absorbee:
                etat = f"ABSORBÉE — {rapport.nb_items} collecté(s), 0 retenu(s)"
            else:
                etat = f"{rapport.nb_retenus} item(s)"
                if rapport.nb_retenus != rapport.nb_items:
                    etat += f" ({rapport.nb_items} collecté(s))"
                if rapport.nb_dates_approximatives:
                    etat += (
                        f" (dont {rapport.nb_dates_approximatives} "
                        "sans date exploitable)"
                    )
            lignes.append(f"  {rapport.source_id:22s} [{rapport.type:6s}] {etat}")

        if self.dedoublonnage.total_ecartes:
            lignes.append(f"  {self.dedoublonnage.resume()}")

        if self.filtrage_signal.total_ecartes:
            lignes.append(f"  {self.filtrage_signal.resume()}")

        if self.classement.total_ecartes or self.classement.scores_retenus:
            lignes.append(f"  {self.classement.resume()}")

        if self.quotas.retenus_par_registre or self.quotas.total_ecartes:
            lignes.append(f"  {self.quotas.resume()}")

        if self.profil_neutre:
            lignes.append(
                "  ⚠ Profil neutre : aucun mot-clé chargé — le classement "
                "par pertinence n'a PAS été appliqué."
            )

        return "\n".join(lignes)


def collecter(
    sources_path: str | Path | None = None,
    profil_path: str | Path | None = None,
    scoring_path: str | Path | None = None,
    quotas_path: str | Path | None = None,
) -> ResultatCollecte:
    """Collecte le socle et rend compte de ce que chaque source a produit.

    L'isolation de panne (AD-6) couvre aussi le chargement de la
    configuration : un `sources.yaml` absent ou illisible produit une
    collecte vide et journalisée, jamais un plantage du run entier.

    Pipeline complet (Story 1.5) : collecte → **seuil de signal** →
    dédoublonnage → **scoring par profil** → **quotas par registre**. Le
    profil, les pondérations et les quotas se chargent après la boucle
    protégée par source : `charger_profil`, `charger_ponderations` et
    `charger_quotas` ne lèvent jamais, une configuration absente ou
    illisible dégrade plutôt que de faire perdre la nuit.

    Les chemins de configuration sont résolus **à l'appel** et non à
    l'import : leur valeur par défaut reste ainsi substituable, ce qui
    empêche un test de se coupler par inadvertance au profil de production.

    `ResultatCollecte.resultats_repartis` (Story 1.8) expose le classement
    filtré par quota tel quel — c'est ce que `pipeline.py` doit passer à
    `enrich.llm.marquer_recommandation`, pas `.items` (qui a déjà perdu le
    `Score`).
    """
    sources_path = DEFAULT_SOURCES_PATH if sources_path is None else sources_path
    profil_path = DEFAULT_PROFIL_PATH if profil_path is None else profil_path
    scoring_path = DEFAULT_SCORING_PATH if scoring_path is None else scoring_path
    quotas_path = DEFAULT_QUOTAS_PATH if quotas_path is None else quotas_path

    try:
        sources = load_sources(sources_path)
    except Exception as e:  # noqa: BLE001 — isolation de panne (AD-6)
        logger.exception(
            "Impossible de charger la configuration des sources (%s) — "
            "collecte vide pour cette nuit.",
            sources_path,
        )
        return ResultatCollecte(items=[], rapports=[])

    debut = datetime.now(timezone.utc)
    items: list[Item] = []
    collecte_par_source: list[tuple[SourceConfig, list[Item], str]] = []

    for source_config in sources:
        items_source, echec = _fetch_one(source_config)
        items.extend(items_source)
        collecte_par_source.append((source_config, items_source, echec))

    # Le seuil de signal passe **avant** le dédoublonnage : il est déclaré
    # par source, donc chaque item doit être jugé sur le seuil de la sienne.
    # Dans l'ordre inverse, l'élection d'un gagnant pouvait faire disparaître
    # un article auquel aucun seuil ne s'appliquait, parce que la copie
    # retenue venait d'une source qui, elle, en portait un.
    items, rapport_signal = filtrer_par_signal(
        items, sources={s.id: s for s in sources}
    )

    items, rapport_dedup = dedupliquer(
        items, priorites={s.id: s.priorite for s in sources}
    )

    profil = charger_profil(profil_path)
    ponderations = charger_ponderations(scoring_path)
    items_avant_classement = items
    resultats_classement = classer(items, profil, ponderations)
    rapport_classement_obtenu = rapport_classement(items_avant_classement, resultats_classement)

    quotas = charger_quotas(quotas_path)
    resultats_repartis = repartir_par_quotas(resultats_classement, quotas)
    rapport_quotas_obtenu = rapport_quotas(resultats_classement, resultats_repartis)
    items = [item_score.item for item_score in resultats_repartis]

    # Contribution réelle au digest, une fois doublons, seuil de signal,
    # bruit et quotas écartés.
    retenus_par_source = Counter(item.source_id for item in items)

    rapports = [
        RapportSource(
            source_id=source_config.id,
            type=source_config.type,
            nb_items=len(items_source),
            nb_retenus=retenus_par_source.get(source_config.id, 0),
            nb_dates_approximatives=_compter_dates_approximatives(items_source, debut),
            echec=echec,
        )
        for source_config, items_source, echec in collecte_par_source
    ]

    resultat = ResultatCollecte(
        items=items,
        rapports=rapports,
        dedoublonnage=rapport_dedup,
        filtrage_signal=rapport_signal,
        classement=rapport_classement_obtenu,
        quotas=rapport_quotas_obtenu,
        profil_neutre=profil.est_vide,
        resultats_repartis=resultats_repartis,
    )
    _journaliser(resultat)
    return resultat


def run(sources_path: str | Path | None = None) -> list[Item]:
    """Collecte les Items de toutes les sources actives du socle."""
    return collecter(sources_path).items


def _fetch_one(source_config: SourceConfig) -> tuple[list[Item], str]:
    """Retourne les items d'une source, et la raison d'un éventuel échec."""
    connector = CONNECTORS.get(source_config.type)
    if connector is None:
        raison = f"type de source '{source_config.type}' non reconnu"
        logger.warning("%s — source '%s' ignorée.", raison, source_config.id)
        return [], raison

    try:
        return connector(source_config), ""
    except Exception as e:  # noqa: BLE001 — isolation de panne par source (AD-6)
        logger.exception(
            "Échec de la collecte pour la source '%s' — ignorée cette nuit.",
            source_config.id,
        )
        return [], _raison_courte(e)


def _raison_courte(erreur: Exception) -> str:
    """Première ligne du message, pour que le récapitulatif reste tabulaire.

    La trace complète est déjà journalisée par `logger.exception`.
    """
    premiere_ligne = str(erreur).split("\n")[0].strip()
    if len(premiere_ligne) > 110:
        premiere_ligne = premiere_ligne[:107] + "..."
    return f"{type(erreur).__name__}: {premiere_ligne}"


def _compter_dates_approximatives(items: list[Item], debut: datetime) -> int:
    """Compte les items horodatés à l'heure de collecte faute de date lisible.

    Sans ce signal, un article d'archive et une annonce d'hier soir sont
    indiscernables — et le tri par fraîcheur remonte le mauvais.
    """
    return sum(
        1 for item in items if abs(item.date_publication - debut) <= MARGE_DATE_APPROXIMATIVE
    )


def _journaliser(resultat: ResultatCollecte) -> None:
    """Publie le récapitulatif à un niveau réellement visible en production."""
    logger.info("%s", resultat.resume())

    for rapport in resultat.sources_muettes:
        logger.warning(
            "Source '%s' muette : aucun item, sans erreur — structure de la "
            "source probablement modifiée.",
            rapport.source_id,
        )

    for rapport in resultat.sources_absorbees:
        # Nommer l'étape responsable : les trois causes appellent des
        # corrections opposées (retirer une source redondante, abaisser un
        # seuil, revoir le profil).
        motifs = []
        if resultat.dedoublonnage.ecartes_par_source.get(rapport.source_id):
            motifs.append("doublons")
        if resultat.filtrage_signal.ecartes_par_source.get(rapport.source_id):
            motifs.append("seuil de signal")
        if resultat.classement.ecartes_par_source.get(rapport.source_id):
            motifs.append("bruit du profil")
        if resultat.quotas.ecartes_par_source.get(rapport.source_id):
            motifs.append("quota de registre dépassé")

        logger.warning(
            "Source '%s' absorbée : %d item(s) collecté(s), aucun retenu — %s.",
            rapport.source_id,
            rapport.nb_items,
            f"écartés par : {', '.join(motifs)}" if motifs else "cause indéterminée",
        )

    for rapport in resultat.rapports:
        if rapport.nb_dates_approximatives and rapport.nb_dates_approximatives == rapport.nb_items:
            logger.warning(
                "Source '%s' : aucune date exploitable sur %d item(s) — "
                "tout paraîtra publié aujourd'hui.",
                rapport.source_id,
                rapport.nb_items,
            )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # httpx journalise chaque requête en INFO : du bruit qui noie le
    # récapitulatif, seul message réellement destiné à l'opérateur.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    collecter()


if __name__ == "__main__":
    main()
