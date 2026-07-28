"""Modèle de données canonique du pipeline (AD-4).

Tout connecteur produit des `Item` respectant exactement ces champs ;
les étapes en aval du pipeline ne consomment que ce contrat.
"""

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Item:
    """Unité de contenu candidate issue d'une Source (AD-4)."""

    source_id: str
    guid: str
    titre: str
    date_publication: datetime
    langue: str
    registre: str
    url: str
    contenu_brut: str

    def __post_init__(self) -> None:
        if self.date_publication.tzinfo is None:
            raise ValueError(
                "date_publication doit être timezone-aware (voir Consistency "
                "Conventions de la spine : dates en UTC)."
            )
        if self.date_publication.utcoffset() != timezone.utc.utcoffset(None):
            raise ValueError(
                "date_publication doit être en UTC (voir Consistency "
                "Conventions de la spine)."
            )
