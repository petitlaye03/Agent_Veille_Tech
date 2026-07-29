"""Dédoublonnage inter-sources et intra-source (FR-3).

Deux sources relayant la même actualité ne doivent produire qu'une entrée.
Un article possède **plusieurs identités** — son URL cible et son `guid` au
sein de sa source — et deux items sont le même article dès que **l'une**
d'elles coïncide.

Cette relation est **transitive** : si A et B partagent une URL, et B et C
un `guid`, alors A, B et C sont le même article. Comparer les identités
l'une après l'autre laisserait passer des doublons ; les items sont donc
regroupés en classes d'équivalence (union-find) avant qu'un gagnant ne soit
élu par classe. Le partitionnement obtenu ne dépend pas de l'ordre d'arrivée.

Le dédoublonnage **sémantique** (deux titres différents pour la même
annonce) reste explicitement hors périmètre v1.
"""

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit

from veille.models import Item

logger = logging.getLogger(__name__)

# Paramètres purement analytiques : présents ou absents, ils désignent le
# même article. `source`, `ref` et `referrer` en sont volontairement absents :
# ils portent l'identité de l'article sur certains sites, et les neutraliser
# confondrait des articles distincts — une perte silencieuse bien pire qu'un
# doublon conservé.
PARAMETRES_DE_SUIVI = frozenset(
    {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "utm_id", "utm_name", "utm_reader", "utm_brand", "utm_social",
        "fbclid", "gclid", "dclid", "msclkid", "twclid", "igshid",
        "mc_cid", "mc_eid", "_hsenc", "_hsmi", "vero_id", "yclid",
    }
)

PORTS_PAR_DEFAUT = {"http": 80, "https": 443, "": None}


@dataclass(frozen=True)
class RapportDedoublonnage:
    """Ce que le dédoublonnage a écarté, et au profit de qui.

    Compter les perdants ne suffit pas : quand le tri mange un article
    légitime, il faut pouvoir remonter à ce qui l'a absorbé.
    """

    ecartes_par_source: dict[str, int] = field(default_factory=dict)
    gagnants_par_source: dict[str, int] = field(default_factory=dict)

    @property
    def total_ecartes(self) -> int:
        return sum(self.ecartes_par_source.values())

    def resume(self) -> str:
        if not self.total_ecartes:
            return "Dédoublonnage : aucun doublon."

        perdants = ", ".join(
            f"{source} (-{n})"
            for source, n in sorted(self.ecartes_par_source.items(), key=lambda x: (-x[1], x[0]))
        )
        gagnants = ", ".join(
            f"{source} (+{n})"
            for source, n in sorted(self.gagnants_par_source.items(), key=lambda x: (-x[1], x[0]))
        )
        return (
            f"Dédoublonnage : {self.total_ecartes} doublon(s) écarté(s) — "
            f"écartés : {perdants} | absorbés par : {gagnants}"
        )


def normaliser_url(url) -> str:
    """Ramène à une forme canonique les variantes d'une même URL.

    Ne lève **jamais** : cette fonction s'exécute en dehors de l'isolation de
    panne par source (AD-6), une exception ici ferait perdre la nuit entière,
    sources saines comprises. Une URL illisible retourne simplement `""`,
    l'item retombant alors sur son `guid` comme identité.

    Neutralise schéma, `www.`, port par défaut, barre oblique finale,
    fragment, encodage-pourcent et paramètres analytiques. **Conserve les
    autres paramètres** : sur certains sites `?id=42` est l'identité même de
    l'article.
    """
    if not url or not isinstance(url, str):
        return ""

    try:
        decoupe = urlsplit(url.strip())
        hote = (decoupe.hostname or "").lower()
        port = decoupe.port  # lève si le port n'est pas numérique
    except ValueError:
        logger.debug("URL illisible, ignorée pour le dédoublonnage : %r", url)
        return ""

    # Sans hôte, la clé se réduirait à un chemin : deux sites publiant
    # `/news/article` seraient confondus. Mieux vaut aucune clé d'URL.
    if not hote:
        return ""

    while hote.startswith("www."):
        hote = hote[4:]

    if port is not None and port != PORTS_PAR_DEFAUT.get(decoupe.scheme.lower()):
        hote = f"{hote}:{port}"

    chemin = unquote(decoupe.path).rstrip("/")

    parametres = [
        (cle, valeur)
        for cle, valeur in parse_qsl(decoupe.query, keep_blank_values=True)
        if cle.lower() not in PARAMETRES_DE_SUIVI
    ]
    requete = urlencode(sorted(parametres))

    # Schéma et fragment volontairement absents : ils ne distinguent pas
    # deux adresses du même article.
    return f"{hote}{chemin}?{requete}" if requete else f"{hote}{chemin}"


def dedupliquer(
    items: list[Item], priorites: dict[str, int]
) -> tuple[list[Item], RapportDedoublonnage]:
    """Retire les doublons, en conservant la version de la source la mieux classée.

    Priorité plus élevée = gagne. À égalité, le premier rencontré est
    conservé. L'ordre des items retenus suit celui de leur première
    apparition.
    """
    if not items:
        return [], RapportDedoublonnage()

    cles_par_item = [_cles_identite(position, item) for position, item in enumerate(items)]

    # 1. Regrouper en classes d'équivalence : toutes les clés d'un item sont
    #    unies entre elles, ce qui propage l'identité de proche en proche.
    parent: dict[str, str] = {}
    for cles in cles_par_item:
        for cle in cles[1:]:
            _unir(parent, cles[0], cle)

    # 2. Rassembler les items par classe.
    classes: dict[str, list[tuple[int, Item]]] = defaultdict(list)
    for position, (item, cles) in enumerate(zip(items, cles_par_item)):
        classes[_trouver(parent, cles[0])].append((position, item))

    # 3. Élire un gagnant par classe.
    retenus: list[tuple[int, Item]] = []
    ecartes: Counter[str] = Counter()
    gagnants: Counter[str] = Counter()

    for membres in classes.values():
        position_gagnante, gagnant = max(
            membres, key=lambda m: (priorites.get(m[1].source_id, 0), -m[0])
        )
        # La classe garde la place de son premier membre : l'ordre global
        # ne dépend pas de qui a gagné l'arbitrage.
        retenus.append((min(position for position, _ in membres), gagnant))

        if len(membres) > 1:
            gagnants[gagnant.source_id] += 1
            for position, item in membres:
                if position != position_gagnante:
                    ecartes[item.source_id] += 1

    ordonnes = [item for _, item in sorted(retenus, key=lambda x: x[0])]
    rapport = RapportDedoublonnage(
        ecartes_par_source=dict(ecartes), gagnants_par_source=dict(gagnants)
    )
    return ordonnes, rapport


def _cles_identite(position: int, item: Item) -> list[str]:
    """Toutes les identités d'un item ; la première sert de représentant.

    Un `guid` vide ne peut pas servir d'identité : sans clé de repli unique,
    tous les items sans identifiant d'une même source s'effondreraient en un
    seul.
    """
    cles = []
    url_normalisee = normaliser_url(item.url)
    if url_normalisee:
        cles.append(f"url:{url_normalisee}")

    if item.guid:
        cles.append(f"guid:{item.source_id}:{item.guid}")

    if not cles:
        cles.append(f"position:{position}")

    return cles


def _trouver(parent: dict[str, str], cle: str) -> str:
    racine = cle
    while parent.get(racine, racine) != racine:
        racine = parent[racine]
    # Compression de chemin : garde les recherches suivantes rapides.
    while parent.get(cle, cle) != cle:
        parent[cle], cle = racine, parent[cle]
    return racine


def _unir(parent: dict[str, str], a: str, b: str) -> None:
    racine_a, racine_b = _trouver(parent, a), _trouver(parent, b)
    if racine_a != racine_b:
        parent[racine_b] = racine_a
