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

from veille import collect, discover, health, store
from veille.enrich.llm import enrichir, marquer_recommandation
from veille.filter import CHAMPS_QUOTAS, charger_ponderations
from veille.profil import charger_profil
from veille.publish import (
    publier,
    publier_a_decouvrir,
    publier_archive,
    publier_bandeau_echec,
    publier_recapitulatif_sante,
)
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
    candidats_path: str | Path | None = None,
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
    `candidats_path` (Story 4.4) suit la même convention : passé tel quel
    à `discover.proposer_source` lors de la réapplication du panneau « À
    découvrir » (voir plus bas), jamais résolu ici lui-même.

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
        sources_path_resolu = (
            collect.DEFAULT_SOURCES_PATH if sources_path is None else sources_path
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
            # Le profil atteint désormais la **rédaction**, pas seulement le
            # tri (audit du 2026-09-22) : `enrich/llm.py` écrivait ses
            # accroches sans rien savoir du lecteur. Rechargé ici plutôt que
            # remonté depuis `collecter()` — `ResultatCollecte` n'expose que
            # `profil_neutre`, un booléen, et lui faire porter le profil
            # entier couplerait la collecte au rendu pour un seul appelant.
            # `charger_profil` ne lève jamais (profil neutre si illisible).
            profil_redaction = charger_profil(
                collect.DEFAULT_PROFIL_PATH if profil_path is None else profil_path
            )
            entrees = enrichir(
                resultat_collecte.items, client=llm_client, profil=profil_redaction
            )

            ponderations = charger_ponderations(scoring_path_resolu)
            entrees = marquer_recommandation(entrees, resultat_collecte.resultats_repartis, ponderations)

            maintenant = datetime.now(timezone.utc)

            # Index des sources passé au rendu (audit du 2026-09-22) : la
            # page et l'archive affichent désormais le nom lisible de la
            # source et la nature du contenu, deux informations qui ne
            # vivent que dans `sources.yaml` (AD-3) — `Item` ne porte que
            # l'`id` technique. Chargé dans son propre `try` : une
            # configuration illisible doit coûter les métadonnées
            # d'affichage (repli sur l'`id`), jamais la publication entière.
            try:
                sources_affichage = {s.id: s for s in collect.load_sources(sources_path_resolu)}
            except Exception:  # noqa: BLE001 — isolation de panne (AD-6)
                logger.exception(
                    "Métadonnées d'affichage des sources illisibles (%s) — "
                    "rendu replié sur les identifiants techniques.",
                    sources_path_resolu,
                )
                sources_affichage = {}

            html = rendre(entrees, maintenant, sources_affichage)
            page_ok = publier(html, client=publish_client)

            markdown = rendre_markdown(entrees, maintenant, sources_affichage)
            archive_ok = publier_archive(markdown, maintenant.date(), client=publish_client)

            if store_conn is not None:
                # Isolé de son propre `try` (trouvé en revue de la Story 4.3,
                # Blind Hunter, constat le plus sérieux de cette revue) : la
                # page vient d'être régénérée depuis zéro par `rendre()`, qui
                # ignore tout des marqueurs du récapitulatif de santé — sans
                # cette réapplication, la publication nocturne normale
                # effacerait silencieusement le panneau publié par le
                # contrôle hebdomadaire, dès la nuit suivante, alors même que
                # les sources concernées restent réellement `suspecte`/
                # `en_sommeil`. Toujours tentée, indépendamment de `page_ok`/
                # `archive_ok` : `publier_recapitulatif_sante` patche la page
                # actuellement publiée (celle-ci ou une précédente), pas
                # seulement le contenu de ce run — aucune des garanties
                # AD-11 (marquage après succès) ne s'applique ici, ce
                # panneau est purement idempotent, jamais un état à protéger
                # d'une reprise.
                try:
                    sources_config = collect.load_sources(sources_path_resolu)
                    a_surveiller = health.lister_sources_a_surveiller(
                        store_conn, maintenant.date(), sources_configurees=sources_config
                    )
                    if publier_recapitulatif_sante(a_surveiller, client=publish_client) is False:
                        logger.warning(
                            "Republication du récapitulatif des sources à "
                            "surveiller en échec après la collecte nocturne."
                        )
                except Exception:  # noqa: BLE001 — voir commentaire ci-dessus
                    logger.exception(
                        "Échec de la republication du récapitulatif des "
                        "sources à surveiller après la collecte nocturne — "
                        "le digest reste publié normalement."
                    )

            # Réapplication du panneau « À découvrir » (Story 4.4) — même
            # correctif que ci-dessus pour le récapitulatif de santé, mais
            # construit dès l'implémentation cette fois plutôt que trouvé en
            # revue : `rendre()` vient de régénérer la page depuis zéro,
            # ignorant tout des marqueurs du panneau « À découvrir » ; sans
            # cette réapplication, la publication nocturne normale
            # l'effacerait silencieusement dès la nuit suivante. Contrairement
            # au bloc ci-dessus, **indépendant de `store_conn`** : ce cycle ne
            # touche jamais l'état « déjà vu »/santé (SQLite), seulement
            # `sources.yaml`/`config/candidats.yaml` — toujours tentée, y
            # compris quand `store_conn` est `None` (état local indisponible
            # cette nuit). `discover.proposer_source` est déterministe par
            # semaine ISO (`aujourdhui.isocalendar().week`) : rejouée chaque
            # nuit de la même semaine, elle reproduit le même candidat tant
            # qu'il reste vérifié actif — la réapplication nocturne ne fait
            # donc jamais que corroborer/rafraîchir la proposition en cours,
            # jamais dévier du rythme hebdomadaire voulu par l'AC1.
            try:
                candidat = discover.proposer_source(
                    candidats_path=candidats_path, sources_path=sources_path_resolu
                )
                if publier_a_decouvrir(candidat, client=publish_client) is False:
                    logger.warning(
                        "Republication du panneau « À découvrir » en échec "
                        "après la collecte nocturne."
                    )
            except Exception:  # noqa: BLE001 — voir commentaire ci-dessus
                logger.exception(
                    "Échec de la republication du panneau « À découvrir » "
                    "après la collecte nocturne — le digest reste publié "
                    "normalement."
                )

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
    publish_client: httpx.Client | None = None,
) -> bool:
    """Contrôle de fraîcheur hebdomadaire (FR-12/13, Stories 4.1/4.3) :
    synchronise l'état depuis le dépôt source, réévalue chaque source
    configurée (`health.evaluer_fraicheur`), journalise le résumé,
    retéléverse l'état, puis publie un récapitulatif consultable des
    sources à surveiller sur la page du digest déjà publiée (Story 4.3).

    Point d'entrée distinct d'`executer()` (voir `main_controle_sante`,
    invoqué par un second workflow GitHub Actions, `controle-hebdomadaire.yml`,
    indépendant de `pipeline-nocturne.yml`) : une panne de l'un ne doit
    jamais affecter l'autre.

    `publish_client` (Story 4.3) est **distinct** de `store_client` : il
    vise le **dépôt de sortie** (digest publié) via l'env var `GITHUB_TOKEN`,
    pas le dépôt source via `SOURCE_GITHUB_TOKEN` que `store_client` vise
    déjà — même distinction que `store_conn`/`publish_client` dans
    `executer()`. Les deux ciblent le même dépôt GitHub depuis le
    2026-09-18 (voir docstrings de `publish.py`/`store.py`), mais restent
    deux paramètres et deux env vars séparés : chaque module reste
    indépendamment testable (AD-2), et un futur retour à deux dépôts
    distincts n'aurait rien à changer ici.

    Ne lève jamais (même filet de sécurité qu'`executer()`). Retourne
    `True` si le contrôle a pu s'exécuter et l'état a été retéléversé avec
    succès, `False` sinon — un retour `False` **n'indique jamais** qu'une
    source est en panne (ça, `RapportSante.resume()` le journalise déjà en
    détail), seulement que le mécanisme lui-même (ouverture locale,
    retéléversement) a échoué. La publication du récapitulatif (Story 4.3)
    est isolée de son propre `try/except` : une panne de cette étape
    annexe ne doit jamais changer ce que retourne cette fonction, qui
    reste gouverné par la synchronisation/le retéléversement de l'état de
    santé (même discipline que le marquage déjà-vu dans `executer()`,
    Story 3.4).
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

            try:
                a_surveiller = health.lister_sources_a_surveiller(
                    conn, aujourdhui, sources_configurees=sources
                )
                if publier_recapitulatif_sante(a_surveiller, client=publish_client) is False:
                    # Trouvé en revue (Edge Case Hunter) : le retour `False`
                    # (panne réelle, distincte d'une exception) n'était
                    # vérifié nulle part — un échec silencieux de plus.
                    logger.warning(
                        "Publication du récapitulatif des sources à "
                        "surveiller en échec."
                    )
            except Exception:  # noqa: BLE001 — voir docstring : n'affecte jamais le retour
                logger.exception(
                    "Échec de la publication du récapitulatif des sources à "
                    "surveiller — le contrôle de fraîcheur lui-même reste "
                    "inchangé."
                )

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


def decouvrir_nouvelle_source(
    candidats_path: str | Path | None = None,
    sources_path: str | Path | None = None,
    publish_client: httpx.Client | None = None,
) -> bool:
    """Cycle de découverte hebdomadaire (FR-14, Story 4.4) : propose une
    source candidate vérifiée active (`discover.proposer_source`), publie
    (ou retire, si aucun candidat vivant) le panneau « À découvrir » sur
    la page déjà publiée.

    Point d'entrée distinct d'`executer()`/`controler_fraicheur()` (voir
    `main_decouverte_source`, invoqué par un step indépendant du même
    workflow `controle-hebdomadaire.yml`, `if: always()` — une panne de
    l'un ne doit jamais empêcher la tentative de l'autre, ni réciproquement).

    Contrairement à `controler_fraicheur()`, ne touche jamais l'état
    « déjà vu »/santé des sources (AD-5) : ce cycle ne lit ni n'écrit
    `data/deja-vu.sqlite3` — seul le dépôt de sortie (`publish_client`,
    env var `GITHUB_TOKEN`) est concerné, aucun jeton de dépôt source
    nécessaire ici (`SOURCE_GITHUB_TOKEN`, requis par `store.py`, hors de
    portée de cette fonction).

    Ne lève jamais (même filet de sécurité qu'`executer()`/
    `controler_fraicheur()`). Retourne `True` si la publication (insertion,
    remplacement ou retrait du panneau) a réussi ou n'avait rien à faire
    (`None` de `publier_a_decouvrir` — aucune page déjà publiée à annoter,
    ou rien à retirer ; pas une panne, même discipline que
    `main_bandeau_echec`). Retourne `False` seulement sur une vraie panne
    de publication.
    """
    try:
        candidat = discover.proposer_source(candidats_path=candidats_path, sources_path=sources_path)
        resultat = publier_a_decouvrir(candidat, client=publish_client)
        if resultat is False:
            logger.warning("Publication du panneau « À découvrir » en échec.")
            return False
        return True
    except Exception:  # noqa: BLE001 — filet de sécurité de dernier recours
        logger.exception("Échec inattendu du cycle de découverte de nouvelle source.")
        return False


def main_decouverte_source() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    reussite = decouvrir_nouvelle_source()
    if not reussite:
        logger.warning("Cycle de découverte de nouvelle source en échec.")
    sys.exit(0 if reussite else 1)


if __name__ == "__main__":
    if "--bandeau-echec" in sys.argv[1:]:
        main_bandeau_echec()
    elif "--controle-sante" in sys.argv[1:]:
        main_controle_sante()
    elif "--decouvrir-source" in sys.argv[1:]:
        main_decouverte_source()
    else:
        main()
