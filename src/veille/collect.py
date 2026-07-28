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
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from veille.config import SourceConfig, load_sources
from veille.connectors import json_connector, rss_connector, scrape_connector
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
    """Ce qu'une source a réellement produit pendant un run."""

    source_id: str
    type: str
    nb_items: int
    nb_dates_approximatives: int = 0
    echec: str = ""

    @property
    def est_muette(self) -> bool:
        """Zéro item sans erreur — le mode de panne le plus insidieux."""
        return not self.echec and self.nb_items == 0


@dataclass(frozen=True)
class ResultatCollecte:
    """Items collectés, accompagnés de ce qui s'est passé pour chaque source."""

    items: list[Item] = field(default_factory=list)
    rapports: list[RapportSource] = field(default_factory=list)

    @property
    def sources_en_echec(self) -> list[RapportSource]:
        return [r for r in self.rapports if r.echec]

    @property
    def sources_muettes(self) -> list[RapportSource]:
        return [r for r in self.rapports if r.est_muette]

    def resume(self) -> str:
        """Récapitulatif lisible, anomalies en évidence."""
        if not self.rapports:
            return "Aucune source configurée."

        lignes = [f"Collecte : {len(self.items)} item(s) depuis {len(self.rapports)} source(s)"]
        for rapport in sorted(self.rapports, key=lambda r: -r.nb_items):
            if rapport.echec:
                etat = f"ÉCHEC — {rapport.echec}"
            elif rapport.est_muette:
                etat = "MUETTE — aucun item, sans erreur"
            else:
                etat = f"{rapport.nb_items} item(s)"
                if rapport.nb_dates_approximatives:
                    etat += (
                        f" (dont {rapport.nb_dates_approximatives} "
                        "sans date exploitable)"
                    )
            lignes.append(f"  {rapport.source_id:22s} [{rapport.type:6s}] {etat}")

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
    rapports: list[RapportSource] = []

    for source_config in sources:
        items_source, echec = _fetch_one(source_config)
        items.extend(items_source)
        rapports.append(
            RapportSource(
                source_id=source_config.id,
                type=source_config.type,
                nb_items=len(items_source),
                nb_dates_approximatives=_compter_dates_approximatives(items_source, debut),
                echec=echec,
            )
        )

    resultat = ResultatCollecte(items=items, rapports=rapports)
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
