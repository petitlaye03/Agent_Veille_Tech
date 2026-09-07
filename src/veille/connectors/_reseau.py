"""Récupération réseau partagée par les trois connecteurs (Story 2.3, FR-2).

Un backoff sur `429` (limite de débit) est un besoin commun aux trois
connecteurs — centralisé ici plutôt que triplé, pour qu'un correctif ne
doive être fait qu'une fois (voir décision #15 du journal des décisions).
Module de détail interne (préfixé `_`) : ne fait pas partie du contrat
public `fetch(source_config) -> list[Item]` d'AD-2, seuls les trois
connecteurs l'importent.

Ne couvre volontairement PAS `scrape_connector._collecte_autorisee` (requête
`robots.txt`) : cette fonction dégrade déjà en « collecte autorisée » sur
toute exception (y compris un 429), une seule requête par source et par
nuit — y ajouter un backoff ralentirait sans bénéfice réel.
"""

import logging
import math
import time

import httpx

logger = logging.getLogger(__name__)

# Nombre total de tentatives (pas de retries) avant d'abandonner et de
# laisser la dernière réponse 429 lever normalement.
MAX_TENTATIVES = 3

# Départ du backoff exponentiel quand le serveur ne fournit pas de
# `Retry-After` exploitable — cohérent avec « espacer de 5-8s minimum »
# recommandé par l'addendum du brief pour Reddit, la source la plus
# contrainte documentée à ce jour (pas dans ce socle, voir Dev Notes de
# la story).
DELAI_DEFAUT_SECONDES = 5.0

# Plafond appliqué à un `Retry-After` fourni par le serveur (trouvé en
# revue) : la collecte est séquentielle (`collect.py`), donc un délai non
# borné pour une seule source retarderait toutes celles qui la suivent dans
# `sources.yaml` pour la même durée — un `Retry-After` légitime mais énorme
# (heures, jours) ne doit pas pouvoir immobiliser tout le run nocturne pour
# une seule source. Choisi au-delà du pire cas du backoff exponentiel par
# défaut (5 + 10 = 15s) sans être disproportionné pour un job nocturne.
DELAI_MAX_SECONDES = 60.0


def get_avec_backoff(
    url: str,
    *,
    timeout: float,
    headers: dict[str, str] | None = None,
    follow_redirects: bool = True,
) -> httpx.Response:
    """`httpx.get` avec un backoff sur `429` (source qui limite le débit).

    Respecte l'en-tête `Retry-After` du serveur quand il est présent et
    lisible (secondes uniquement — le format date HTTP n'est pas géré, voir
    Dev Notes de la story) ; sinon retombe sur un backoff exponentiel
    (`DELAI_DEFAUT_SECONDES`, `×2`, `×4`...). Toute autre erreur HTTP
    (403, 500...) lève immédiatement, sans retry — le backoff ne concerne
    que `429`, les autres pannes sont déjà couvertes par l'isolation
    existante (Story 2.2).

    Après `MAX_TENTATIVES` tentatives sur 429, la dernière réponse lève
    normalement (`httpx.HTTPStatusError`) : `_fetch_one` (`collect.py`)
    isole la panne comme n'importe quelle autre (AD-6). Le backoff donne
    sa chance à la source, il ne remplace jamais l'isolation de panne.
    """
    tentative = 0
    while True:
        reponse = httpx.get(url, timeout=timeout, follow_redirects=follow_redirects, headers=headers)
        tentative += 1

        if reponse.status_code != 429 or tentative >= MAX_TENTATIVES:
            reponse.raise_for_status()
            return reponse

        delai = _delai_depuis_retry_after(reponse)
        if delai is None:
            delai = DELAI_DEFAUT_SECONDES * (2 ** (tentative - 1))

        logger.warning(
            "429 (limite de débit) pour %s — tentative %d/%d, nouvel essai dans %.1fs.",
            url,
            tentative,
            MAX_TENTATIVES,
            delai,
        )
        time.sleep(delai)


def _delai_depuis_retry_after(reponse: httpx.Response) -> float | None:
    """Analyse l'en-tête `Retry-After` (secondes uniquement), plafonné.

    Un en-tête absent ou illisible (format date HTTP, valeur non numérique,
    `inf`/`nan` — `float()` les accepte sans lever, mais `time.sleep`
    plante dessus, trouvé en revue) retombe sur `None` plutôt que de lever
    ou de bloquer indéfiniment — le backoff exponentiel prend le relais.
    Une valeur finie mais énorme est plafonnée à `DELAI_MAX_SECONDES`,
    jamais rejetée : le serveur a quand même donné un signal valide, on le
    respecte autant que raisonnable plutôt que de l'ignorer.
    """
    valeur = reponse.headers.get("Retry-After")
    if valeur is None:
        return None
    try:
        delai = float(valeur)
    except ValueError:
        return None
    if not math.isfinite(delai):
        return None
    return min(max(0.0, delai), DELAI_MAX_SECONDES)
