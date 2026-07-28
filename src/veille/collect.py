"""Orchestration de la collecte (FR-1, FR-2).

Charge le socle de sources, dispatche chaque source vers le connecteur
correspondant à son type, et consolide les résultats. Isole les pannes
par source (AD-6) : une source qui échoue ne doit jamais interrompre la
collecte des autres.
"""

import logging
from pathlib import Path

from veille.config import SourceConfig, load_sources
from veille.connectors import rss_connector
from veille.models import Item

logger = logging.getLogger(__name__)

DEFAULT_SOURCES_PATH = Path("config/sources.yaml")

# Dispatch par type de source. Ajouter un connecteur (API JSON, scraping)
# ne modifie que cette table, jamais la boucle d'orchestration ci-dessous.
CONNECTORS = {
    "rss": rss_connector.fetch,
}


def run(sources_path: str | Path = DEFAULT_SOURCES_PATH) -> list[Item]:
    """Collecte les Items de toutes les sources actives du socle.

    L'isolation de panne (AD-6) couvre aussi le chargement de la
    configuration : un `sources.yaml` absent ou illisible produit une
    collecte vide et journalisée, jamais un plantage du run entier.
    """
    try:
        sources = load_sources(sources_path)
    except Exception:  # noqa: BLE001 — isolation de panne (AD-6)
        logger.exception(
            "Impossible de charger la configuration des sources (%s) — "
            "collecte vide pour cette nuit.",
            sources_path,
        )
        return []

    items: list[Item] = []

    for source_config in sources:
        items.extend(_fetch_one(source_config))

    return items


def _fetch_one(source_config: SourceConfig) -> list[Item]:
    connector = CONNECTORS.get(source_config.type)
    if connector is None:
        logger.warning(
            "Type de source '%s' non reconnu pour '%s' — source ignorée.",
            source_config.type,
            source_config.id,
        )
        return []

    try:
        return connector(source_config)
    except Exception:  # noqa: BLE001 — isolation de panne par source (AD-6)
        logger.exception(
            "Échec de la collecte pour la source '%s' — ignorée cette nuit.",
            source_config.id,
        )
        return []


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    items = run()
    logger.info("Collecte terminée : %d item(s) récupéré(s).", len(items))


if __name__ == "__main__":
    main()
