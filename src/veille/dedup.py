"""Dédoublonnage inter-sources et intra-source (FR-3).

Deux sources relayant la même actualité ne doivent produire qu'une entrée.
L'identité repose sur le `guid` (AD-4) et sur l'URL cible normalisée — le
dédoublonnage **sémantique** (deux titres différents pour la même annonce)
reste explicitement hors périmètre v1.
"""

import logging
from collections import Counter
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from veille.models import Item

logger = logging.getLogger(__name__)

# Paramètres de suivi : présents ou absents, ils désignent le même article.
PARAMETRES_DE_SUIVI = frozenset(
    {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "utm_id", "utm_name", "ref", "referrer", "source", "fbclid", "gclid",
        "mc_cid", "mc_eid", "igshid", "_hsenc", "_hsmi",
    }
)


@dataclass(frozen=True)
class RapportDedoublonnage:
    """Ce que le dédoublonnage a écarté — un tri excessif doit rester visible."""

    ecartes_par_source: dict[str, int] = field(default_factory=dict)

    @property
    def total_ecartes(self) -> int:
        return sum(self.ecartes_par_source.values())

    def resume(self) -> str:
        if not self.total_ecartes:
            return "Dédoublonnage : aucun doublon."

        detail = ", ".join(
            f"{source} ({n})"
            for source, n in sorted(self.ecartes_par_source.items(), key=lambda x: -x[1])
        )
        return f"Dédoublonnage : {self.total_ecartes} doublon(s) écarté(s) — {detail}"


def normaliser_url(url: str) -> str:
    """Ramène à une forme canonique les variantes d'une même URL.

    Neutralise schéma, `www.`, barre oblique finale, fragment et paramètres
    de suivi. **Conserve les autres paramètres** : sur certains sites,
    `?id=42` est l'identité même de l'article — le supprimer confondrait des
    articles distincts, une perte bien pire qu'un doublon.
    """
    if not url:
        return ""

    decoupe = urlsplit(url.strip())

    hote = decoupe.netloc.lower()
    if hote.startswith("www."):
        hote = hote[4:]

    chemin = decoupe.path.rstrip("/")

    parametres = [
        (cle, valeur)
        for cle, valeur in parse_qsl(decoupe.query, keep_blank_values=True)
        if cle.lower() not in PARAMETRES_DE_SUIVI
    ]
    requete = urlencode(sorted(parametres))

    # Schéma et fragment volontairement vidés : ils ne distinguent pas
    # deux adresses du même article.
    return urlunsplit(("", hote, chemin, requete, ""))


def dedupliquer(
    items: list[Item], priorites: dict[str, int]
) -> tuple[list[Item], RapportDedoublonnage]:
    """Retire les doublons, en conservant la version de la source la mieux classée.

    Deux critères d'identité coexistent, et un item est un doublon dès que
    **l'un** des deux correspond :

    - **URL normalisée**, qui rapproche deux sources relayant le même article ;
    - **`guid` au sein de sa source**, qui rattrape un flux republiant le même
      contenu sous des URL différentes.

    Priorité plus élevée = gagne. À égalité, le premier rencontré est conservé
    (départage stable). L'ordre des items retenus est préservé.
    """
    # identifiant interne -> (position d'origine, item)
    retenus: dict[int, tuple[int, Item]] = {}
    index_url: dict[str, int] = {}
    index_guid: dict[tuple[str, str], int] = {}
    ecartes: Counter[str] = Counter()
    prochain_id = 0

    for position, item in enumerate(items):
        cle_url = normaliser_url(item.url)
        cle_guid = (item.source_id, item.guid)

        identifiant = index_url.get(cle_url) if cle_url else None
        if identifiant is None:
            identifiant = index_guid.get(cle_guid)

        if identifiant is None:
            retenus[prochain_id] = (position, item)
            if cle_url:
                index_url[cle_url] = prochain_id
            index_guid[cle_guid] = prochain_id
            prochain_id += 1
            continue

        position_retenue, item_retenu = retenus[identifiant]
        if priorites.get(item.source_id, 0) > priorites.get(item_retenu.source_id, 0):
            # Le nouvel item gagne, mais garde la place du premier trouvé
            # pour que l'ordre global reste stable.
            retenus[identifiant] = (position_retenue, item)
            if cle_url:
                index_url[cle_url] = identifiant
            index_guid[cle_guid] = identifiant
            ecartes[item_retenu.source_id] += 1
        else:
            ecartes[item.source_id] += 1

    ordonnes = [item for _, item in sorted(retenus.values(), key=lambda x: x[0])]
    rapport = RapportDedoublonnage(ecartes_par_source=dict(ecartes))

    if rapport.total_ecartes:
        logger.info("%s", rapport.resume())

    return ordonnes, rapport
