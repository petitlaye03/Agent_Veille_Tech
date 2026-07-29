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
from veille.models import Item

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
    au dédoublonnage pour atteindre le digest.
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

        Une source entièrement absorbée par le dédoublonnage n'apporte
        rien : c'est soit un doublon intégral d'une autre, soit un tri
        excessif. Dans les deux cas, il faut le voir.
        """
        return not self.echec and self.nb_items > 0 and self.nb_retenus == 0


@dataclass(frozen=True)
class ResultatCollecte:
    """Items collectés, accompagnés de ce qui s'est passé pour chaque source."""

    items: list[Item] = field(default_factory=list)
    rapports: list[RapportSource] = field(default_factory=list)
    dedoublonnage: RapportDedoublonnage = field(default_factory=RapportDedoublonnage)

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
        if self.dedoublonnage.total_ecartes:
            collectes = sum(r.nb_items for r in self.rapports)
            entete += (
                f" — {collectes} collecté(s), "
                f"{self.dedoublonnage.total_ecartes} doublon(s) écarté(s)"
            )
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

        return "\n".join(lignes)


def collecter(sources_path: str | Path = DEFAULT_SOURCES_PATH) -> ResultatCollecte:
    """Collecte le socle et rend compte de ce que chaque source a produit.

    L'isolation de panne (AD-6) couvre aussi le chargement de la
    configuration : un `sources.yaml` absent ou illisible produit une
    collecte vide et journalisée, jamais un plantage du run entier.
    """
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

    items, rapport_dedup = dedupliquer(
        items, priorites={s.id: s.priorite for s in sources}
    )

    # Contribution réelle au digest, une fois les doublons écartés.
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
        items=items, rapports=rapports, dedoublonnage=rapport_dedup
    )
    _journaliser(resultat)
    return resultat


def run(sources_path: str | Path = DEFAULT_SOURCES_PATH) -> list[Item]:
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
        logger.warning(
            "Source '%s' absorbée : %d item(s) collecté(s), aucun retenu après "
            "dédoublonnage — doublon intégral d'une autre source, ou tri excessif.",
            rapport.source_id,
            rapport.nb_items,
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
