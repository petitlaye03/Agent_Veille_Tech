---
stepsCompleted: [step-01, step-01-confirmed, step-02-approved, step-03-stories-approved, step-04-validated]
inputDocuments: ["_bmad-output/planning-artifacts/prds/prd-agent-veille-emploi-ia-2026-07-24/prd.md", "_bmad-output/planning-artifacts/architecture/architecture-agent-veille-emploi-ia-2026-07-24/ARCHITECTURE-SPINE.md"]
---

# Agent de veille IA - Epic Breakdown

## Overview

Ce document découpe en epics et stories les exigences du PRD et les décisions de l'Architecture pour l'agent de veille IA.

## Requirements Inventory

### Functional Requirements

FR1: L'agent peut récupérer les Items d'une Source quel que soit son type (RSS, API, scraping), via un connecteur par type. Socle v1 de 15-20 Sources, extensible par configuration sans modifier le code de collecte.

FR2: L'agent continue la collecte si une Source échoue, et journalise l'échec. Backoff sur les Sources sensibles au débit. La génération est produite même si une part significative des Sources échoue, avec signalement de l'anomalie.

FR3: L'agent dédoublonne : deux Items pointant vers la même URL cible produisent au plus une Entrée. Une même annonce reprise par plusieurs médias produit une seule Entrée (celle de la Source la mieux classée).

FR4: L'agent applique un seuil de signal spécifique à chaque Source avant de considérer un Item (ex. votes HF Daily Papers, points Hacker News). arXiv n'est jamais collecté en flux brut.

FR5: L'agent classe les Items retenus selon leur proximité avec le Profil (fichier éditable de thèmes/mots-clés), sans modification de code pour changer le classement.

FR6: L'agent répartit les Items retenus par Quotas de Section (≈3 Apprendre / ≈3 Ce qui bouge / ≈2 Pour le métier), configurables. Jamais de remplissage un jour creux.

FR7: L'agent rédige une Accroche courte en français pour chaque Entrée, même depuis une Source anglophone, avec la Source et un lien vers l'original. Génération via API Claude.

FR8: L'agent signale les Entrées à prioriser (recommandation explicite) quand le contenu le justifie.

FR9: L'agent publie le Digest du jour à une URL stable, lisible sur mobile, avec indication de la date/heure de génération réussie et un bandeau honnête en cas d'échec nocturne.

FR10: L'agent archive chaque Digest en Markdown versionné, un fichier par jour, cherchable sur l'ensemble de l'historique.

FR11: Le pipeline (collecte → filtrage → accroches → publication) s'exécute automatiquement chaque nuit, sans intervention, pour que la page soit prête avant 7h38 (génération la veille au soir). Reprise tentée en cas d'échec.

FR12: L'agent évalue périodiquement la fraîcheur de chaque Source (item le plus récent, dates suspectes) et marque son État (`active`, `suspecte`, `en sommeil`).

FR13: L'agent rend visible un récapitulatif des Sources suspectes/en sommeil.

FR14: L'agent propose périodiquement une Source candidate hors du socle (podcast, newsletter, blog), avec justification, vérifiée active avant suggestion.

### NonFunctional Requirements

NFR1: Coût de génération des accroches maîtrisé — cible < 2 €/mois à volume nominal (≈8 accroches/jour).
NFR2: Fiabilité de livraison — page à jour avant 7h38, viser ≥ 6 jours/7.
NFR3: Fraîcheur du socle — aucune Source suspecte non traitée depuis plus de 2 semaines.
NFR4: Lisibilité mobile de la page publiée (responsive).
NFR5: Non-abandon — la page doit rester consultée dans la durée (cible : usage ≥ 4 jours/7 à 6 semaines), ce qui contraint la conception à la sobriété (pas de remplissage, pas de survalorisation du volume).

NFR6: Qualité visuelle — la page doit être soignée et agréable à consulter : palette de couleurs, typographie, mise en page travaillées ; ni page blanche par défaut du navigateur, ni design extravagant. Présentable, sobre, plaisant. S'applique aussi bien en clair qu'en sombre si le téléphone d'Abdoulaye a un thème sombre.

### Additional Requirements (Architecture)

- **Pas de starter/template greenfield imposé** — projet Python nouveau, structure de dossiers fixée par la spine (§ Structural Seed).
- **Paradigme pipes-and-filters** : 6 étapes isolées (collect, dedup, filter, enrich, render, publish) orchestrées séquentiellement ; aucune dépendance ne remonte (AD-1).
- **Connecteurs de sources derrière une interface uniforme** (`Connector.fetch() -> list[Item]`), un module par type — RSS, API JSON, scraping (AD-2).
- **Sources et Profil = configuration** (`sources.yaml`, `profil.md`), jamais codés en dur (AD-3).
- **`Item` = forme interne canonique** avec champs invariants (source_id, guid, titre, date_publication ISO 8601 UTC, langue, registre, url, contenu_brut) (AD-4).
- **SQLite (stdlib) = propriétaire unique de l'état** : « déjà vu » par source et santé des Sources (AD-5).
- **Isolation des pannes** : try/except par Source, jamais d'exception qui interrompt le run (AD-6).
- **Frontière LLM unique** : un seul module `enrich.llm` appelle l'API Claude (modèle claude-haiku-4-5-20251001) (AD-7).
- **Publication par commit git vers GitHub Pages** : page HTML + archive Markdown dans le même dépôt (AD-8).
- **Idempotence du job nocturne** : upsert par date, reprise sûre (AD-9).
- **Aucune source en violation de CGU** (LinkedIn, emploisenegal.com, Wellfound exclus) ; secrets en `.env` non versionné, jamais dans la sortie publiée (AD-10).
- **L'état « déjà vu » n'est validé qu'après publication réussie**, dans la même transaction — prévient la perte silencieuse d'items sur échec en milieu de pipeline (AD-11).
- **Ordonnancement** : Planificateur de tâches Windows, exécution locale (~22h heure de Dakar).
- **Stack fixée** : Python 3.11, uv, feedparser 6.0.12, httpx, anthropic 0.119.0, Jinja2, PyYAML, python-dotenv, SQLite stdlib.
- **Structure de code fixée** (Structural Seed) : `src/veille/{pipeline,models,store,collect,connectors/,dedup,filter,enrich/,render,publish,health,discover}.py`, `config/{sources.yaml,profil.md}`, `templates/`, `site/` (sortie publiée).

### UX Design Requirements

Aucun document UX formel — pas d'interface interactive à concevoir (pas de flux, pas d'états applicatifs). La sortie est une page rendue à partir de templates (Jinja2) et consultée en lecture seule, mais l'identité visuelle est une exigence réelle, capturée légèrement ici faute de spine UX dédiée :

UX-DR1: Palette de couleurs et typographie définies (pas les styles par défaut du navigateur) — cohérentes entre la page HTML et, si pertinent, l'archive.
UX-DR2: Mise en page claire par Section (Apprendre / Ce qui bouge / Pour le métier), hiérarchie visuelle nette entre titre, accroche, source et lien.
UX-DR3: Responsive mobile-first — c'est le support de lecture principal (FR9, NFR4).
UX-DR4: Support du thème sombre si le terminal le demande (`prefers-color-scheme`).
UX-DR5: Sobriété : pas d'animation ou de fioriture qui ralentit la lecture en 5 minutes (cohérent avec NFR5, l'anti-Ben's-Bites).

### FR Coverage Map

| FR | Epic | Description |
| --- | --- | --- |
| FR1 | Epic 1 (partiel) → Epic 2 (complet) | Collecte hétérogène : socle réduit puis étendu |
| FR2 | Epic 2 | Tolérance aux pannes de source |
| FR3 | Epic 1 (même run) → Epic 2 (échelle) → Epic 3.4 (cross-nuit, persistant) | Dédoublonnage |
| FR4 | Epic 1 — **Story 1.4** | Seuils de signal par source (rattaché le 2026-07-29 : aucune story ne le couvrait) |
| FR5 | Epic 1 — Story 1.4 | Scoring par Profil |
| FR6 | Epic 1 — Story 1.5 | Quotas par Section |
| FR7 | Epic 1 | Accroches en français |
| FR8 | Epic 1 | Recommandations explicites |
| FR9 | Epic 1 | Page à URL stable |
| FR10 | Epic 1 | Archive Markdown |
| FR11 | Epic 3 | Exécution nocturne automatique |
| FR12 | Epic 4 | Détection de sources défaillantes |
| FR13 | Epic 4 | Signalement à l'utilisateur |
| FR14 | Epic 4 | Découverte de nouvelles sources |

## Epic List

### Epic 1: Un premier digest, réel, du bout en bout
Abdoulaye peut déclencher le pipeline et voir apparaître, sur une vraie page publiée, un digest lisible, joli et fiable — à petite échelle (quelques sources) mais complet de la collecte à la publication. C'est le squelette qui prouve que l'idée marche avant qu'on l'étende.
**FRs covered:** FR1 (partiel — 3-5 sources de types variés), FR3, FR4, FR5, FR6, FR7, FR8, FR9, FR10.
**Implementation notes:** paradigme pipeline (AD-1), `Item` canonique (AD-4), connecteurs derrière interface uniforme dès le départ même si peu nombreux (AD-2), Sources et Profil en configuration (AD-3), frontière LLM unique (AD-7), SQLite pour l'état dès cette étape (AD-5), publication GitHub Pages (AD-8). Qualité visuelle (NFR6, UX-DR1-5) traitée dès ce premier rendu, pas différée.

### Epic 2: Un socle de sources riche et robuste aux pannes
Abdoulaye reçoit un digest qui reflète vraiment l'étendue de l'écosystème (le socle de 15-20 sources visé), et qui continue de fonctionner même quand une source tombe en panne un soir.
**FRs covered:** FR1 (complet), FR2, FR3 (renforcé — dédoublonnage inter-sources à plus grande échelle).
**Implementation notes:** ajout des connecteurs restants (RSS/API/scraping) ; isolation des pannes (AD-6) ; backoff sur sources sensibles au débit.

### Epic 3: Un digest qui arrive tout seul chaque matin
Abdoulaye n'a plus rien à déclencher : le pipeline tourne chaque nuit sans lui, la page est prête avant 7h38, et une panne une nuit ne lui fait perdre aucun item.
**FRs covered:** FR11.
**Implementation notes:** planificateur Windows (~22h Dakar) ; idempotence par upsert de date (AD-9) ; état « déjà vu » validé seulement après publication réussie (AD-11) — c'est l'épic où cette règle prend tout son sens.

### Epic 4: Un socle qui reste vivant et s'élargit de lui-même
Abdoulaye peut faire confiance à son socle dans la durée : les sources mortes ou suspectes sont détectées et signalées plutôt que de pourrir en silence, et l'agent lui propose régulièrement de nouvelles sources à explorer.
**FRs covered:** FR12, FR13, FR14.
**Implementation notes:** contrôle de fraîcheur périodique (item le plus récent, dates suspectes) ; mise en sommeil automatique ; découverte hebdomadaire vérifiée avant suggestion.

---

## Epic 1: Un premier digest, réel, du bout en bout

Abdoulaye peut déclencher le pipeline et voir apparaître, sur une vraie page publiée, un digest lisible, joli et fiable — à petite échelle mais complet de la collecte à la publication.

### Story 1.1: Brancher une première source et voir ses items collectés

As a Abdoulaye,
I want connecter une première source RSS et récupérer ses items,
So that je vérifie que le pipeline de collecte fonctionne de bout en bout sur un cas réel.

**Acceptance Criteria:**

**Given** un fichier `sources.yaml` contenant une source RSS valide (ex. OpenAI news)
**When** le script de collecte est exécuté
**Then** il produit une liste d'Items respectant le format canonique (source_id, guid, titre, date_publication ISO 8601 UTC, langue, registre, url, contenu_brut)
**And** chaque Item est associé à un identifiant de source traçable
**And** exécuter à nouveau ne plante pas

### Story 1.2: Ajouter des sources de types différents derrière la même interface

As a Abdoulaye,
I want ajouter une source API JSON (HF Daily Papers) et une source scrapée,
So that je vérifie que l'interface de connecteurs uniforme tient face à des sources hétérogènes.

**Acceptance Criteria:**

**Given** `sources.yaml` avec 3 à 5 sources de types RSS/API/scraping mélangés
**When** la collecte tourne
**Then** chaque connecteur produit des Items dans le même format canonique quel que soit son type
**And** ajouter une source ne modifie aucun fichier de code, seulement la configuration

### Story 1.3: Écarter les doublons entre sources

As a Abdoulaye,
I want ne jamais voir deux fois la même actualité relayée par plusieurs sources,
So that mon digest reste dense en information utile.

**Acceptance Criteria:**

**Given** deux Items de sources différentes pointant vers la même URL cible
**When** le dédoublonnage s'exécute
**Then** une seule Entrée en résulte, celle issue de la source la mieux classée
**And** deux items partageant la même URL/guid ne produisent jamais deux entrées

### Story 1.4: Filtrer par signal de source et classer par pertinence

As a Abdoulaye,
I want que les items soient classés selon mon profil de centres d'intérêt,
So that les items les plus pertinents remontent en premier.

**Acceptance Criteria:**

**Given** le fichier `profil.md` (thèmes prioritaires, bruit) et un jeu d'items collectés
**When** le scoring s'exécute
**Then** un item touchant un thème prioritaire (RAG, agents, evals…) est classé devant un item générique
**And** un item relevant du bruit (crypto, hype, actu conso) est fortement pénalisé ou écarté
**And** modifier `profil.md` change le classement sans toucher au code

### Story 1.5: Répartir en trois sections à quotas

As a Abdoulaye,
I want voir mon digest organisé en trois sections (Apprendre / Ce qui bouge / Pour le métier),
So that j'équilibre progression, actualité et employabilité chaque jour.

**Acceptance Criteria:**

**Given** des items scorés et classés par registre
**When** la répartition par quotas s'exécute
**Then** au plus ≈3 Apprendre, ≈3 Ce qui bouge, ≈2 Pour le métier sont retenus
**And** un jour avec moins d'items qu'un quota affiche moins d'entrées, jamais de remplissage artificiel
**And** les quotas sont configurables sans modifier le code

### Story 1.6: Générer une accroche en français pour chaque entrée

As a Abdoulaye,
I want une accroche courte en français pour chaque entrée retenue, même si la source est en anglais,
So that je comprends l'enjeu sans devoir lire l'anglais ni le texte complet.

**Acceptance Criteria:**

**Given** une Entrée retenue, quelle que soit sa langue source
**When** le module d'accroche (frontière LLM unique) traite l'entrée
**Then** une accroche de 1 à 3 phrases en français est produite
**And** l'entrée conserve un lien direct vers la source originale
**And** aucun autre module du code n'appelle l'API Claude directement
**And** le coût cumulé des appels reste compatible avec la cible de budget quasi-nul (< 2 €/mois à volume nominal)

### Story 1.7: Signaler les entrées à ne pas manquer

As a Abdoulaye,
I want qu'une entrée soit mise en avant quand elle le mérite vraiment,
So that je sais où porter mon attention en priorité.

**Acceptance Criteria:**

**Given** un digest du jour avec au moins une entrée nettement plus pertinente que les autres
**When** la génération d'accroches s'exécute
**Then** cette entrée porte une marque de recommandation visible
**And** aucune recommandation n'est forcée un jour où rien ne le justifie vraiment

### Story 1.8: Publier une page à URL fixe, jolie et lisible sur mobile

As a Abdoulaye,
I want consulter mon digest du jour sur une page à URL stable, agréable à lire sur mon téléphone,
So that je l'ouvre chaque matin sans réfléchir.

**Acceptance Criteria:**

**Given** un digest généré (sections + accroches)
**When** la page est rendue et publiée sur GitHub Pages
**Then** la même URL affiche toujours le dernier digest
**And** la page utilise une palette de couleurs et une typographie définies, pas le style par défaut du navigateur
**And** la mise en page est pensée mobile d'abord, avec une hiérarchie claire par section
**And** un thème sombre est appliqué si le terminal le demande (`prefers-color-scheme`)
**And** la page affiche la date/heure de la dernière génération réussie

### Story 1.9: Archiver chaque digest en Markdown

As a Abdoulaye,
I want que chaque digest soit conservé dans une archive versionnée,
So that je peux retrouver un sujet lu plusieurs semaines auparavant.

**Acceptance Criteria:**

**Given** un digest publié pour une date donnée
**When** l'étape d'archivage s'exécute
**Then** un fichier Markdown daté est ajouté au dépôt versionné
**And** le contenu de l'archive est cherchable par texte sur l'ensemble de l'historique

---

## Epic 2: Un socle de sources riche et robuste aux pannes

Abdoulaye reçoit un digest qui reflète vraiment l'étendue de l'écosystème, et qui continue de fonctionner même quand une source tombe en panne un soir.

### Story 2.1: Étendre le socle aux 15-20 sources visées

As a Abdoulaye,
I want que mon socle couvre les 15-20 sources vérifiées de l'addendum,
So that mon digest reflète vraiment l'étendue de l'écosystème IA/data.

**Acceptance Criteria:**

**Given** la liste des sources vérifiées (addendum du brief)
**When** `sources.yaml` est complété
**Then** le pipeline collecte sur l'ensemble du socle sans modification de code
**And** chaque source ajoutée respecte le format canonique Item

### Story 2.2: Continuer à fonctionner quand une source tombe en panne

As a Abdoulaye,
I want ne jamais me retrouver sans digest parce qu'une seule source a eu un problème cette nuit-là,
So that mon agent reste fiable même quand l'écosystème ne l'est pas.

**Acceptance Criteria:**

**Given** une source qui répond en erreur (timeout, 403, 429) pendant la collecte
**When** le pipeline s'exécute
**Then** les autres sources sont tout de même collectées et le digest est produit
**And** l'échec est journalisé avec sa cause
**And** si plus de la moitié des sources échouent la même nuit, le digest est quand même produit et l'anomalie est signalée

### Story 2.3: Respecter les sources sensibles au débit

As a Abdoulaye,
I want que mon agent ne se fasse pas bloquer par une source à cause de requêtes trop rapprochées,
So that je ne perde pas définitivement l'accès à une source utile.

**Acceptance Criteria:**

**Given** une source connue pour limiter le débit
**When** plusieurs requêtes sont nécessaires
**Then** un délai de backoff est respecté entre les appels
**And** un blocage temporaire de cette source n'interrompt pas la collecte des autres

### Story 2.4: Dédoublonner à l'échelle du socle complet

As a Abdoulaye,
I want que le dédoublonnage tienne quand le nombre de sources augmente,
So that je ne vois pas la même actualité répétée cinq fois.

**Acceptance Criteria:**

**Given** une actualité reprise par plusieurs sources du socle élargi
**When** le dédoublonnage s'exécute sur l'ensemble du socle
**Then** une seule entrée en résulte
**And** le run reste compatible avec une seule exécution nocturne (pas de dérive de durée disqualifiante)

---

## Epic 3: Un digest qui arrive tout seul chaque matin

Abdoulaye n'a plus rien à déclencher : le pipeline tourne chaque nuit sans lui, et une panne ne lui fait perdre aucun item.

### Story 3.1: Déclencher le pipeline automatiquement chaque nuit

As a Abdoulaye,
I want ne plus avoir à lancer quoi que ce soit,
So that le digest est prêt avant que je sorte le matin.

**Acceptance Criteria:**

**Given** le pipeline fonctionnel (Epic 1 et 2)
**When** le Planificateur de tâches Windows est configuré
**Then** le pipeline se déclenche seul chaque soir (~22h heure de Dakar)
**And** la page publiée est à jour avant 7h38 le lendemain matin

### Story 3.2: Reprendre proprement après un échec, sans perdre d'items

As a Abdoulaye,
I want qu'un plantage en pleine nuit ne me fasse perdre aucune actualité,
So that le dernier digest réussi reste visible en attendant la reprise.

**Acceptance Criteria:**

**Given** un run qui échoue après la collecte mais avant la publication
**When** une reprise est tentée dans la nuit
**Then** les mêmes items sont reconsidérés, car aucun n'a été marqué « déjà vu » avant la publication réussie
**And** tant qu'aucune reprise n'a réussi, le dernier digest publié avec succès reste affiché
**And** un bandeau honnête indique l'absence de mise à jour cette nuit-là

### Story 3.3: Relancer sans jamais dupliquer

As a Abdoulaye,
I want pouvoir relancer le pipeline pour une même nuit sans risque,
So that je ne me retrouve jamais avec deux digests ou une archive dupliquée.

**Acceptance Criteria:**

**Given** un digest déjà publié pour la date du jour
**When** le pipeline est relancé pour cette même date
**Then** le digest de cette date est écrasé (upsert), jamais dupliqué
**And** l'archive ne contient qu'une seule entrée pour cette date

### Story 3.4: Ne jamais remontrer un item déjà publié

As a Abdoulaye,
I want ne jamais revoir dans mon digest un item déjà publié un jour précédent,
So that chaque matin m'apporte vraiment du neuf plutôt que des redites.

**Acceptance Criteria:**

**Given** un item déjà publié dans un digest antérieur, dont l'état « déjà vu » a été validé après cette publication réussie
**When** ce même item réapparaît dans la collecte d'une nuit suivante
**Then** il est écarté avant d'atteindre le filtrage
**And** un item jamais publié auparavant reste éligible normalement

---

## Epic 4: Un socle qui reste vivant et s'élargit de lui-même

Abdoulaye peut faire confiance à son socle dans la durée : les sources mortes sont détectées, et l'agent lui propose régulièrement de nouvelles sources.

### Story 4.1: Détecter une source qui a arrêté de publier

As a Abdoulaye,
I want savoir quand une source de mon socle s'est tue,
So that je ne découvre pas six mois plus tard qu'elle ne m'apportait plus rien.

**Acceptance Criteria:**

**Given** une source dont l'item le plus récent dépasse 30 jours
**When** le contrôle de fraîcheur hebdomadaire s'exécute
**Then** la source passe à l'état « suspecte »
**And** une source silencieuse depuis plus de 3 mois passe à l'état « en sommeil » et n'est plus interrogée

### Story 4.2: Détecter une source qui ment sur sa fraîcheur

As a Abdoulaye,
I want être protégé contre les flux qui répondent normalement mais servent des dates fausses ou du contenu périmé,
So that je ne fais pas confiance à une source qui a en réalité arrêté de publier (cas observé sur ActuIA et VentureBeat pendant la cartographie).

**Acceptance Criteria:**

**Given** une source dont plusieurs items partagent la même date de publication à la minute près
**When** le contrôle de fraîcheur s'exécute
**Then** la source est marquée « suspecte » même si elle répond correctement (200 OK)

### Story 4.3: Voir un récapitulatif des sources à surveiller

As a Abdoulaye,
I want un endroit où voir d'un coup d'œil quelles sources sont suspectes ou en sommeil,
So that je décide si je les répare ou les retire.

**Acceptance Criteria:**

**Given** au moins une source à l'état « suspecte » ou « en sommeil »
**When** le contrôle hebdomadaire se termine
**Then** un récapitulatif liste ces sources avec leur état et la raison
**And** ce récapitulatif est consultable sans avoir à interroger la base directement

### Story 4.4: Recevoir une proposition de nouvelle source chaque semaine

As a Abdoulaye,
I want que mon agent me propose régulièrement une source que je ne suis pas encore,
So that ma veille s'élargit sans que j'aie à chercher moi-même.

**Acceptance Criteria:**

**Given** le socle actuel de sources suivies
**When** le cycle de découverte hebdomadaire s'exécute
**Then** au moins une source candidate hors du socle est proposée, en français ou en anglais, avec une phrase justifiant son apport
**And** la source proposée a été vérifiée active (flux valide, publication récente) avant d'être suggérée
**And** la proposition apparaît dans une section « À découvrir » du digest, séparée des sections habituelles
