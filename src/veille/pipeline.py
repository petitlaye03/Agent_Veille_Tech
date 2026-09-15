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

from veille import collect, health, store
from veille.enrich.llm import enrichir, marquer_recommandation
from veille.filter import CHAMPS_QUOTAS, charger_ponderations
from veille.publish import publier, publier_archive, publier_bandeau_echec
from veille.render import rendre, rendre_bandeau_echec, rendre_markdown

logger = logging.getLogger(__name__)


def executer(
    sources_path: str | Path | None = None,
    profil_path: str | Path | None = None,
    scoring_path: str | Path | None = None,
    quotas_path: str | Path | None = None,
    llm_client: object | None = None,
    publish_client: httpx.Client | None = None,
    deja_vus_path: str | Path | None = None,
    store_client: httpx.Client | None = None,
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

    État « déjà vu » (AD-5, AD-11, Story 3.4) : synchronisé depuis le
    dépôt source **avant** la collecte (`store.synchroniser_depuis_distant`),
    passé à `collect.collecter` pour écarter ce qui a déjà été publié une
    nuit précédente, puis — **seulement si `page_ok and archive_ok`** —
    marqué comme vu et retéléversé vers le dépôt source. Marquer avant
    d'avoir confirmé la publication romprait AD-11 : un run qui échoue
    après collecte mais avant publication perdrait silencieusement les
    items de la nuit, jamais retentés. `store.ouvrir`/`marquer_vus`/
    `televerser_vers_distant` ne lèvent jamais de leur côté (mêmes
    garanties que `collecter`/`publier`), donc leur échec ne fait pas
    échouer le run — seul `page_ok and archive_ok` en décide.
    `deja_vus_path`/`store_client` suivent la même convention
    d'injection que les autres chemins/clients : `None` par défaut
    (chemin/jeton réels), substituables par les tests pour ne jamais
    toucher le vrai `data/deja-vu.sqlite3` du dépôt ni le réseau.

    Ne lève jamais : `collecter`, `enrichir`, `marquer_recommandation`,
    `publier`, `publier_archive` et les fonctions de synchronisation de
    `store.py` (`synchroniser_depuis_distant`/`televerser_vers_distant`)
    dégradent déjà proprement de leur côté ; `store.ouvrir()`, lui, peut
    légitimement lever (fichier local corrompu — voir sa propre
    docstring), donc cette fonction l'isole explicitement elle-même
    (trouvé en revue) plutôt que de laisser une panne locale à ce seul
    sous-système faire échouer toute la nuit : dégrade en désactivant le
    filtrage/marquage « déjà vu » pour ce run, sans jamais abandonner la
    collecte/publication elles-mêmes. Le marquage/retéléversement après
    succès est isolé de la même façon (voir plus bas) : une panne à cette
    étape ne doit jamais transformer une publication pourtant réussie en
    run déclaré en échec. `rendre()`/`rendre_markdown()` n'ont pas de
    garantie de non-levée qui leur soit propre (aucun appel réseau à
    isoler, mais un template manquant ou corrompu lèverait — trouvé en
    revue). L'intégralité du corps de cette fonction est donc enveloppée
    d'un filet de sécurité de dernier recours. Retourne `True` si la page
    **et** l'archive ont été publiées avec succès, `False` sinon — jamais
    d'exception qui remonterait jusqu'à l'appelant.
    """
    try:
        scoring_path_resolu = (
            collect.DEFAULT_SCORING_PATH if scoring_path is None else scoring_path
        )

        store.synchroniser_depuis_distant(deja_vus_path, client=store_client)
        try:
            store_conn = store.ouvrir(deja_vus_path)
        except Exception:  # noqa: BLE001 — isolation dédiée (trouvé en revue) :
            # une panne d'ouverture locale (fichier corrompu, disque plein…)
            # ne doit dégrader que le filtrage « déjà vu »/la santé des
            # sources de ce run, jamais faire perdre la collecte/publication
            # elles-mêmes.
            logger.exception(
                "Impossible d'ouvrir l'état local (déjà vu / santé des "
                "sources) — collecte sans ces mécanismes pour cette nuit."
            )
            store_conn = None
        try:
            resultat_collecte = collect.collecter(
                sources_path,
                profil_path,
                scoring_path,
                quotas_path,
                store_conn=store_conn,
            )
            entrees = enrichir(resultat_collecte.items, client=llm_client)

            ponderations = charger_ponderations(scoring_path_resolu)
            entrees = marquer_recommandation(entrees, resultat_collecte.resultats_repartis, ponderations)

            maintenant = datetime.now(timezone.utc)

            html = rendre(entrees, maintenant)
            page_ok = publier(html, client=publish_client)

            markdown = rendre_markdown(entrees, maintenant)
            archive_ok = publier_archive(markdown, maintenant.date(), client=publish_client)

            if page_ok and archive_ok and store_conn is not None:
                # Isolé de son propre `try` (trouvé en revue) : la publication
                # a déjà réussi à ce stade — une panne de marquage/
                # retéléversement ne doit jamais requalifier ce succès en
                # échec (ce que le filet de sécurité englobant ferait sinon).
                try:
                    # Un item dont le `registre` n'est reconnu par aucune
                    # section publiée (`render._grouper_par_registre`,
                    # dégradation pré-existante documentée depuis la Story
                    # 1.8) n'a en réalité jamais été montré à l'utilisateur —
                    # le marquer « vu » le ferait disparaître en permanence
                    # de toute collecte future sans avoir jamais été publié
                    # une seule fois (trouvé en revue). Seuls les items dont
                    # le registre correspond à une section réellement rendue
                    # sont marqués.
                    items_publies = [
                        item for item in resultat_collecte.items if item.registre in CHAMPS_QUOTAS
                    ]
                    store.marquer_vus(items_publies, store_conn)
                    if not store.televerser_vers_distant(deja_vus_path, client=store_client):
                        # Trouvé en revue (convergence des 3 couches) : sans ce
                        # log, un échec de retéléversement était totalement
                        # silencieux — les marques restent locales à ce run
                        # éphémère, jamais vues du prochain, qui peut donc
                        # republier les mêmes items. Le log ne corrige pas ce
                        # risque résiduel (pas de nouvelle tentative — même
                        # discipline que `publish.py`, qui ne relance jamais
                        # non plus), mais il rend l'échec visible dans les
                        # logs du run au lieu de disparaître sans trace.
                        logger.warning(
                            "Retéléversement de l'état « déjà vu » en échec — "
                            "les items de cette nuit ne seront pas exclus des "
                            "collectes futures tant que l'état distant n'aura "
                            "pas été resynchronisé avec succès."
                        )
                except Exception:  # noqa: BLE001 — voir commentaire ci-dessus
                    logger.exception(
                        "Échec du marquage/retéléversement de l'état « déjà "
                        "vu » après une publication pourtant réussie — la nuit "
                        "reste un succès (digest publié), mais certains items "
                        "pourraient réapparaître une prochaine nuit."
                    )

            return page_ok and archive_ok
        finally:
            if store_conn is not None:
                store_conn.close()
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


def main_bandeau_echec() -> None:
    """Point d'entrée dédié (Story 3.2) : publie un bandeau honnête sur la
    page déjà publiée, signalant l'absence de mise à jour cette nuit-là.

    Invoqué **uniquement** par le step `if: failure() || cancelled()` du
    workflow GitHub Actions (`.github/workflows/pipeline-nocturne.yml`),
    jamais par `executer()`/`main()` eux-mêmes — un run qui échoue avant
    `rendre()` n'a par construction aucune `Entree` à rendre, le bandeau
    doit donc être ajouté après coup, sur le HTML déjà publié, par un
    chemin entièrement distinct de celui du pipeline principal. Ne lève
    jamais (même filet de sécurité que `executer()`).

    Code de sortie (corrigé en revue — `publier_bandeau_echec` renvoie
    maintenant `True`/`False`/`None`, trois états distincts) : non nul
    seulement sur une **vraie** panne de publication (`False`) — visibilité
    dans l'onglet Actions, comme pour le pipeline principal. `None`
    (aucune page déjà publiée à annoter — probablement la toute première
    nuit) sort avec **0** : ce n'est pas une panne au sens de
    `publish.publier_bandeau_echec`, en faire un run rouge produirait une
    fausse alerte systématique la toute première fois que le pipeline
    échoue avant d'avoir jamais publié avec succès.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    try:
        aujourdhui = datetime.now(timezone.utc).date()
        bandeau = rendre_bandeau_echec(aujourdhui)
        resultat = publier_bandeau_echec(bandeau)
    except Exception:  # noqa: BLE001 — filet de sécurité, même réflexe que executer()
        logger.exception("Échec inattendu lors de la publication du bandeau d'échec.")
        resultat = False

    if resultat is None:
        logger.info("Rien à annoter (aucune page déjà publiée) — pas une panne.")
    elif not resultat:
        logger.warning("Bandeau d'échec non publié.")

    reussite = resultat is not False
    sys.exit(0 if reussite else 1)


def controler_fraicheur(
    sources_path: str | Path | None = None,
    deja_vus_path: str | Path | None = None,
    store_client: httpx.Client | None = None,
) -> bool:
    """Contrôle de fraîcheur hebdomadaire (FR-12/13, Story 4.1) : synchronise
    l'état depuis le dépôt source, réévalue chaque source configurée
    (`health.evaluer_fraicheur`), journalise le résumé, retéléverse l'état.

    Point d'entrée distinct d'`executer()` (voir `main_controle_sante`,
    invoqué par un second workflow GitHub Actions, `controle-hebdomadaire.yml`,
    indépendant de `pipeline-nocturne.yml`) : une panne de l'un ne doit
    jamais affecter l'autre.

    Ne lève jamais (même filet de sécurité qu'`executer()`). Retourne
    `True` si le contrôle a pu s'exécuter et l'état a été retéléversé avec
    succès, `False` sinon — un retour `False` **n'indique jamais** qu'une
    source est en panne (ça, `RapportSante.resume()` le journalise déjà en
    détail), seulement que le mécanisme lui-même (ouverture locale,
    retéléversement) a échoué.
    """
    try:
        store.synchroniser_depuis_distant(deja_vus_path, client=store_client)
        try:
            conn = store.ouvrir(deja_vus_path)
        except Exception:  # noqa: BLE001 — isolation dédiée, même réflexe qu'executer()
            logger.exception(
                "Impossible d'ouvrir l'état local — contrôle de fraîcheur "
                "annulé pour cette exécution."
            )
            return False

        try:
            sources_path_resolu = (
                collect.DEFAULT_SOURCES_PATH if sources_path is None else sources_path
            )
            sources = collect.load_sources(sources_path_resolu)
            aujourdhui = datetime.now(timezone.utc).date()
            rapport = health.evaluer_fraicheur(sources, conn, aujourdhui)
            logger.info(rapport.resume())

            reussite = store.televerser_vers_distant(deja_vus_path, client=store_client)
            if not reussite:
                # Même discipline que le retéléversement « déjà vu » dans
                # executer() (trouvé en revue de la Story 3.4) : jamais
                # silencieux, même sans nouvelle tentative automatique.
                logger.warning(
                    "Retéléversement de l'état de santé en échec — les "
                    "transitions calculées cette semaine ne seront pas "
                    "visibles du prochain contrôle tant que l'état distant "
                    "n'aura pas été resynchronisé avec succès."
                )
            return reussite
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 — filet de sécurité de dernier recours
        logger.exception("Échec inattendu du contrôle de fraîcheur.")
        return False


def main_controle_sante() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    reussite = controler_fraicheur()
    if not reussite:
        logger.warning("Contrôle de fraîcheur hebdomadaire en échec.")
    sys.exit(0 if reussite else 1)


if __name__ == "__main__":
    if "--bandeau-echec" in sys.argv[1:]:
        main_bandeau_echec()
    elif "--controle-sante" in sys.argv[1:]:
        main_controle_sante()
    else:
        main()
