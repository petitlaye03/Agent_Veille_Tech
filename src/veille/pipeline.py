"""Orchestrateur du pipeline complet (AD-1, Story 1.8).

Point d'entrée unique : collecte → enrichissement (accroches + recommandation,
FR-7/8) → rendu (FR-9, + archive Markdown FR-10 depuis la Story 1.9) →
publication (AD-8). Résout la partie de la tension AD-1 suivie depuis la
Story 1.4 qui a un AC réel ici — le chaînage interne de `collecter()`
(collecte → seuil de signal → dédoublonnage → scoring → quotas) n'est
volontairement pas défait, voir les Dev Notes de la story
1-8-publication-page.md pour la justification.
"""

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

from veille import collect
from veille.enrich.llm import enrichir, marquer_recommandation
from veille.filter import charger_ponderations
from veille.publish import publier, publier_archive
from veille.render import rendre, rendre_markdown

logger = logging.getLogger(__name__)


def executer(
    sources_path: str | Path | None = None,
    profil_path: str | Path | None = None,
    scoring_path: str | Path | None = None,
    quotas_path: str | Path | None = None,
    llm_client: object | None = None,
    publish_client: httpx.Client | None = None,
) -> bool:
    """Exécute le pipeline complet, un seul run.

    Les chemins de configuration suivent le même contrat que `collecter()`
    (résolus à l'appel, pas à l'import — substituables par les tests). Le
    classement passé à `marquer_recommandation` est celui **filtré par
    quota** (`resultat_collecte.resultats_repartis`, Story 1.8), pas le
    classement brut : un gagnant écarté par quota n'a aucune `Entree` à
    marquer (précisé en revue de la Story 1.7).

    `llm_client`/`publish_client` permettent d'injecter des clients simulés
    (tests) — mêmes conventions que `enrichir()`/`publier()`, jamais
    d'appel réseau réel si l'un des deux est fourni explicitement.
    `llm_client` n'est **volontairement pas** typé `anthropic.Anthropic |
    None` : importer `anthropic` ici, même pour une seule annotation,
    romprait l'invariant AD-7 vérifié mécaniquement par `grep` (un seul
    point d'import du SDK, `enrich/llm.py`) — trouvé en revue.

    Deux publications par run depuis la Story 1.9 : la page (`rendre` +
    `publier`) et l'archive Markdown du jour (`rendre_markdown` +
    `publier_archive`), à partir du **même** relevé d'horloge
    (`maintenant`) — une seule source de vérité temporelle par run, pas
    deux horodatages potentiellement décalés. Le run n'est un succès que
    si les deux le sont (`page_ok and archive_ok`).

    La page est **rendue et publiée avant** que l'archive soit même
    rendue (trouvé en revue) : sans cet ordre, un `rendre_markdown()` qui
    lève (aucune garantie de non-levée qui lui soit propre, voir plus bas)
    ferait perdre la page — alors qu'elle avait déjà été produite avec
    succès et n'attendait que d'être publiée. Une panne isolée sur l'une
    des deux étapes ne doit jamais faire perdre l'autre alors qu'elle
    aurait pu réussir.

    Ne lève jamais : `collecter`, `enrichir`, `marquer_recommandation`,
    `publier` et `publier_archive` dégradent déjà proprement de leur côté,
    mais `rendre()`/`rendre_markdown()` n'ont pas cette garantie qui leur
    soit propre (aucun appel réseau à isoler, mais un template manquant ou
    corrompu lèverait — trouvé en revue). L'intégralité du corps de cette
    fonction est donc enveloppée d'un filet de sécurité de dernier recours.
    Retourne `True` si la page **et** l'archive ont été publiées avec
    succès, `False` sinon — jamais d'exception qui remonterait jusqu'à
    l'appelant.
    """
    try:
        scoring_path_resolu = (
            collect.DEFAULT_SCORING_PATH if scoring_path is None else scoring_path
        )

        resultat_collecte = collect.collecter(sources_path, profil_path, scoring_path, quotas_path)
        entrees = enrichir(resultat_collecte.items, client=llm_client)

        ponderations = charger_ponderations(scoring_path_resolu)
        entrees = marquer_recommandation(entrees, resultat_collecte.resultats_repartis, ponderations)

        maintenant = datetime.now(timezone.utc)

        html = rendre(entrees, maintenant)
        page_ok = publier(html, client=publish_client)

        markdown = rendre_markdown(entrees, maintenant)
        archive_ok = publier_archive(markdown, maintenant.date(), client=publish_client)

        return page_ok and archive_ok
    except Exception:  # noqa: BLE001 — filet de sécurité de dernier recours (trouvé en revue)
        logger.exception("Échec inattendu du pipeline — nuit perdue, mais le run ne plante pas.")
        return False


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # Même raison que collect.py::main() : httpx journalise chaque requête
    # en INFO, du bruit qui noie le récapitulatif.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    reussite = executer()
    if not reussite:
        logger.warning("Publication du digest en échec cette nuit.")
    # Code de sortie non nul sur échec (trouvé en revue) : sans ça, un futur
    # planificateur de tâches (FR-11, Epic 3) n'aurait aucun moyen de
    # détecter une nuit en échec autrement qu'en analysant les logs.
    sys.exit(0 if reussite else 1)


if __name__ == "__main__":
    main()
