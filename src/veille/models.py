"""Modèle de données canonique du pipeline (AD-4).

Tout connecteur produit des `Item` respectant ce contrat ; les étapes en
aval du pipeline ne consomment que ces champs.
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

    # Signal de la source (votes, points…), optionnel et neutre par défaut
    # (amendement AD-4, Story 1.4) : seules les sources qui le déclarent en
    # configuration le renseignent ; les autres connecteurs n'en remarquent
    # rien. Consommé par `filter.py` pour le seuil de signal (FR-4).
    signal: float | None = None

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


@dataclass(frozen=True)
class Entree:
    """Ce qu'un `Item` retenu devient une fois enrichi (Story 1.6, FR-7).

    Volontairement minimal : seulement l'item d'origine et son accroche en
    français. Ne pas ajouter de champ `recommandee` ici — c'est FR-8
    (Story 1.7), qui n'est pas encore écrite ; l'anticiper serait de la
    généralité spéculative.
    """

    item: Item
    accroche: str
