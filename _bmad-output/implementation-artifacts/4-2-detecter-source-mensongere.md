---
baseline_commit: a394379
---

# Story 4.2: Détecter une source qui ment sur sa fraîcheur

Status: done

## Story

As a Abdoulaye,
I want être protégé contre les flux qui répondent normalement mais servent des dates fausses ou du contenu périmé,
so that je ne fais pas confiance à une source qui a en réalité arrêté de publier (cas observé sur ActuIA et VentureBeat pendant la cartographie).

## Acceptance Criteria

1. **[FR-13, epics.md#Story-4.2]** Étant donné une source dont plusieurs items de la même collecte partagent la même date de publication à la minute près, quand le contrôle de fraîcheur s'exécute, alors la source est marquée `suspecte` — **même si elle répond correctement** (200 OK, `dernier_item_vu` par ailleurs récent). Ce signal l'emporte sur un calcul d'âge qui, seul, la déclarerait `active`.
2. **[Précision]** Une source dont les items partagent la même date **à la seconde/minute par pure coïncidence isolée** (un seul doublon parmi de nombreux items à horaires distincts) n'est **pas** considérée mensongère — le signal porte sur un **motif répété** (**au moins 3** items strictement identiques à la minute — corrigé en revue : un seuil de 2 aurait signalé exactement le cas d'« un seul doublon » que cet AC exclut explicitement, contradiction trouvée par l'Acceptance Auditor), pas sur une seule paire fortuite.
3. **[Cohérence avec la Story 4.1]** Une source déjà `en_sommeil` (silencieuse depuis plus de 90 jours) reste `en_sommeil` même si son dernier lot d'items (avant l'endormissement) portait des dates suspectes — l'endormissement est un état plus sévère et plus récent dans le raisonnement, il ne doit jamais être rétrogradé par un signal plus ancien.
4. **[Isolation, AD-6]** La détection ne lève jamais — une liste d'items vide, ou dont les dates sont malformées, ne doit jamais faire échouer la collecte ni le contrôle hebdomadaire.
5. Aucune régression sur la Story 4.1 (états `active`/`suspecte`/`en_sommeil` existants, `sources_en_sommeil`, `enregistrer_activite`, `taux_echec`/`anomalie_pannes`) ; suite complète verte.

## Tasks / Subtasks

- [x] Task 1 : Détection pure + persistance de l'observation (AC: 1, 2, 4)
  - [x] `health.detecter_dates_suspectes(items: list[Item]) -> bool` — vrai si **au moins 2 items** du lot partagent `date_publication` tronquée à la minute (`replace(second=0, microsecond=0)`). Fonction pure, aucune I/O, ne lève jamais (isolée par son propre `try/except`, dégrade en `False`).
  - [x] Étendre le schéma `sante_source` (dans `store.ouvrir()`, migration additive) : nouvelle colonne `dates_suspectes INTEGER NOT NULL DEFAULT 0` via `ALTER TABLE ... ADD COLUMN`, capturant explicitement `OperationalError` « duplicate column name » pour un fichier déjà à jour.
  - [x] `enregistrer_activite` calcule et persiste `dates_suspectes` pour **ce lot de la nuit** (recalculé à chaque appel, pas cumulatif — un lot sain efface un signal isolé d'une nuit précédente). Ne touche toujours pas `etat`.
  - [x] Tests unitaires (7 nouveaux) : lot avec 2 items à la même minute exacte → vrai ; lot avec des secondes différentes mais même minute → vrai (troncature à la minute) ; lot sans doublon → faux ; lot vide → faux ; un seul item → faux ; persistance vérifiée par relecture SQL ; lot sain efface un signal précédent.

- [x] Task 2 : Incorporer le signal dans `evaluer_fraicheur` (AC: 1, 3)
  - [x] Règle de précédence explicite : `en_sommeil` (âge > 90 jours) l'emporte toujours ; sinon, `suspecte` si (âge > 30 jours) **ou** (`dates_suspectes` vrai) ; sinon `active`.
  - [x] Tests (3 nouveaux) : une source avec `dernier_item_vu` très récent mais `dates_suspectes` vrai passe `active → suspecte` (AC1) ; une source `en_sommeil` avec `dates_suspectes` vrai reste `en_sommeil`, jamais rétrogradée (AC3) ; une source sans `dates_suspectes` et fraîche reste `active` (non-régression Story 4.1).

- [x] Task 3 : Validation (AC: 4, 5)
  - [x] Suite complète (`uv run pytest`) rejouée sans régression — 454 passed (444 avant cette story + 10 nouveaux) ; tous les tests existants de `test_health.py`/`test_collect.py`/`test_rapport_collecte.py` (Story 4.1) inchangés et verts.
  - [x] Vérifié par lecture de code (précision de revue : « confirmé explicitement » aurait surévalué ce qu'aucun test ne démontre — reformulé) : `dates_suspectes`/`etat` n'interagissent avec aucun autre calcul du projet — `taux_echec`/`anomalie_pannes` (Story 2.2/4.1) portent uniquement sur `RapportSource.echec`/`ignoree_sommeil`, jamais sur `sante_source.etat`.

## Dev Notes

### Pourquoi « au moins 3 items » (corrigé en revue) et pas un seuil proportionnel

L'AC parle de « plusieurs items » qui « partagent la même date » — un motif répété, pas un simple hasard — et l'AC2 exclut explicitement « un seul doublon parmi de nombreux items à horaires distincts ». Deux approches possibles : (a) seuil absolu (≥N items identiques à la minute, quel que soit la taille du lot), (b) seuil proportionnel (ex. ≥30 % du lot). Choix retenu : **(a), seuil absolu**. Justification : le cas cité en exemple (ActuIA/VentureBeat, « cartographie ») décrit des flux qui **rejouent une même date figée** sur plusieurs articles distincts — un phénomène binaire (le flux ment ou ne ment pas sur ses horodatages), pas une question de proportion. Un seuil proportionnel introduirait un paramètre supplémentaire à régler sans donnée réelle pour le calibrer, et pourrait laisser passer un petit lot entièrement mensonger simplement parce que le lot est trop petit pour atteindre un pourcentage.

**Valeur du seuil, corrigée en revue** : la première version de cette story fixait le seuil à 2 — l'Acceptance Auditor a trouvé que ce choix contredisait directement l'AC2 lui-même (« un seul doublon » **est** un groupe de 2 items identiques ; un seuil de 2 l'aurait donc signalé à tort). Corrigé à **3** : une simple paire fortuite (2 items) ne suffit plus, il faut un vrai groupe d'au moins 3 dates identiques pour constituer le « motif répété » que l'AC2 distingue de la coïncidence. Réévaluer si l'exécution réelle (une fois cette story déployée) révèle des faux négatifs (motif réel de seulement 2 items sur un tout petit lot) ou des faux positifs (3 coïncidences sur un très grand lot).

### Ce qui est déjà vrai, à ne pas reconstruire (Story 4.1)

- `sante_source(source_id, dernier_item_vu, etat)` — table déjà créée par `store.ouvrir()`. Cette story y **ajoute** une colonne, ne crée pas de nouvelle table (la détection de dates mensongères est une observation par source, exactement comme `dernier_item_vu` — même table, même propriétaire de schéma, AD-5).
- `enregistrer_activite(source_id, items, conn, maintenant=None)` — déjà appelée chaque nuit par `collect.collecter()` avec le lot brut de la source (`items_source`, avant tout filtrage). C'est le seul endroit du pipeline qui voit encore les items bruts d'une source **avant** dédoublonnage/filtrage — la détection doit se brancher ici, pas ailleurs (le contrôle hebdomadaire, `evaluer_fraicheur`, ne voit plus jamais d'`Item`, seulement l'état déjà persisté).
- `evaluer_fraicheur(sources, conn, aujourdhui)` — déjà isolée par source (corrigé en revue de la Story 4.1) ; cette story ajoute une lecture supplémentaire (`dates_suspectes`) à la même requête `SELECT` déjà présente, pas une requête séparée.
- **Aucun changement de `collect.collecter()` lui-même** : `enregistrer_activite` reçoit déjà `items_source` complet à l'endroit exact où cette story a besoin de brancher — zéro nouveau paramètre, zéro nouveau point d'appel.

### Précédents à réutiliser, pas à réinventer

- **Isolation par sous-système (AD-6)** — `detecter_dates_suspectes` suit le même réflexe que tout le reste de `health.py` : ne lève jamais, dégrade en `False` (aucune anomalie présumée) plutôt que de faire perdre la collecte.
- **Migration de schéma additive** — même patron que l'ajout de la table `sante_source` elle-même en Story 4.1 (`CREATE TABLE IF NOT EXISTS`) : ici, `ALTER TABLE ... ADD COLUMN` (SQLite l'autorise pour une colonne avec valeur par défaut), toujours dans `store.ouvrir()`, jamais dans `health.py`.
- **`aujourdhui`/`maintenant` explicites, jamais `datetime.now()` interne** — même discipline que toute la Story 4.1, pour un contrôle testable déterministe.

### Hors périmètre — ne pas anticiper

- **Story 4.3** (récapitulatif consultable) — le `RapportSante` existant suffit à signaler la transition ; aucune surface de consultation nouvelle à construire ici, et pas de message distinct « pourquoi suspecte » à exposer à l'utilisateur (juste l'état lui-même).
- **Contenu périmé sans date mensongère** (mentionné dans le « so that » de la story mais pas dans l'AC formel) — cette story ne détecte que le motif de dates, pas une comparaison de contenu (hash, similarité de texte). Hors AC, non construit.
- **Seuil configurable** — pas de nouveau fichier de configuration ; `2` reste une constante de code (comme `SEUIL_SUSPECTE_JOURS`/`SEUIL_SOMMEIL_JOURS`), à extraire en configuration seulement si un besoin réel de réglage par source apparaît.

### Testing Standards

`pytest` via `uv run pytest`. Aucun appel réseau ni horloge réelle — `detecter_dates_suspectes` est une fonction pure testée directement sur des listes d'`Item` construites en mémoire ; `evaluer_fraicheur` continue de recevoir `aujourdhui` en paramètre explicite (Story 4.1).

### Previous Story Intelligence

- Story 4.1 : `health.py` construit et revu (isolation par source dans `evaluer_fraicheur`, filtre anti-date-future dans `enregistrer_activite`, `sources_tentees`/`taux_echec` corrigés) — tous ces correctifs restent en place, cette story ne les touche pas. Convention de revue à reproduire : lancer les 3 couches adversariales même sur un diff réduit (la Story 4.1 en a tiré 6 correctifs malgré un périmètre initial modeste).
- Story 4.1 (leçon de revue, journal des décisions #53) : toute nouvelle catégorie d'état introduite doit être vérifiée contre les ratios/calculs préexistants qui présument encore l'ancien comportement — vérifier ici si `dates_suspectes` interagit avec `taux_echec`/`anomalie_pannes` (a priori non : ces deux propriétés portent sur les pannes réseau/HTTP, pas sur l'état de fraîcheur, mais à confirmer explicitement en implémentation plutôt que présumé).

### Git Intelligence Summary

Commits récents (locaux, non encore poussés — blocage `gh auth` `workflow` scope toujours en cours, 4 tentatives de device flow depuis la Story 3.1) : Story 4.1 (`91a8ebc` impl+revue, `a394379` docs — Epic 4 démarré).

### Project Structure Notes

Aucun nouveau fichier : `src/veille/health.py` (nouvelle fonction + logique étendue), `src/veille/store.py` (colonne supplémentaire dans `ouvrir()`). Conforme à la structure déjà établie par la Story 4.1.

### References

- [Source: epics.md#Story-4.2] — story d'origine et critère d'acceptation
- [Source: ARCHITECTURE-SPINE.md#AD-5] — fichier SQLite unique, source de vérité pour l'État d'une Source
- [Source: ARCHITECTURE-SPINE.md#AD-6] — isolation des pannes, étendue à `health.py` depuis la Story 4.1
- [Source: 4-1-detecter-source-arretee.md] — `health.py`/`sante_source` construits, réutilisés tels quels

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5 (`claude-sonnet-5`)

### Debug Log References

- `uv run pytest tests/test_health.py -q` : 30 passed (20 avant + 10 nouveaux) — avant revue.
- Suite complète (avant revue) : `uv run pytest -q` → 454 passed (444 avant cette story + 10 nouveaux), aucune régression.
- Suite complète (après revue) : `uv run pytest -q` → 457 passed (454 avant revue + 3 nouveaux : 1 `test_store.py`, 2 `test_health.py`).

### Review Findings

> Revue de code du 2026-09-15 (skill `bmad-code-review`, 3 couches adversariales, sur
> Sonnet 5 — même modèle que l'implémentation). Base de diff `a394379` (= `baseline_commit`,
> changements non commités). L'Acceptance Auditor a trouvé une contradiction directe entre
> l'AC2 de cette story elle-même (rédigé lors de `create-story`) et le seuil choisi à
> l'implémentation — l'AC excluait explicitement le cas qu'un seuil de 2 aurait signalé.
> Convergence blind+edge sur un second constat réel : le signal de dates suspectes pouvait
> être silencieusement perdu quand le lot entier était à date future.

**Correctifs appliqués (4) :**

- [x] [Review][Patch] `SEUIL_DATES_SUSPECTES` fixé à 2 contredisait directement l'AC2 de la story elle-même — « un seul doublon parmi de nombreux items à horaires distincts » (un groupe de 2 items identiques) est explicitement exclu du signal par cet AC, mais un seuil de 2 l'aurait signalé. Corrigé à **3** — une simple paire fortuite ne suffit plus, un vrai motif répété est désormais requis. Constat (Acceptance Auditor), auto-infligé lors de la rédaction de la story elle-même — pas un défaut d'implémentation, une incohérence entre deux parties du même document [src/veille/health.py, story]
- [x] [Review][Patch] `dates_suspectes` était calculé mais jamais persisté quand le lot entier était à date future (`if not candidats: return` sortait avant le premier `INSERT`) — un lot dont **toutes** les dates sont à la fois futures et identiques (le mensonge le plus flagrant possible) échappait totalement à sa propre détection, et un signal `True` d'une nuit précédente aurait pu rester figé indéfiniment sans jamais être réévalué. Corrigé : le signal est désormais toujours persisté, indépendamment de la plausibilité des dates pour `dernier_item_vu`. Constat convergent (Blind Hunter + Edge Case Hunter) [src/veille/health.py]
- [x] [Review][Patch] Migration de schéma (`ALTER TABLE ... ADD COLUMN`) dépendait d'un `try/except` sur le texte exact de l'erreur SQLite (`"duplicate column name"`), et s'exécutait à **chaque** appel d'`ouvrir()` — un message d'erreur différent (ex. verrou de fichier) aurait fait planter le chemin nocturne normal, pas seulement la migration ponctuelle. Corrigé : vérification explicite via `PRAGMA table_info` avant d'exécuter `ALTER TABLE`, qui ne s'exécute plus qu'une seule fois, quand la colonne manque réellement. Constat (Edge Case Hunter) [src/veille/store.py]
- [x] [Review][Patch] Fixture de test `_item_a` renommée `_item_avec_date` (nom qui ne véhiculait rien, à distinguer de `_item` sans lire les deux corps). Constat (Blind Hunter, nitpick) [tests/test_health.py]

**Reporté (1)** — voir `deferred-work.md`, section « Deferred from: code review of 4-2-detecter-source-mensongere » :

- `detecter_dates_suspectes` ne déduplique pas par identité d'item avant de compter — un connecteur qui renverrait accidentellement 3 copies du même article (pagination, retry) resterait indiscernable d'un vrai motif de dates mensongères. Risque jugé faible, correctif reporté (coupage nouveau avec `dedup.py`).

**Rejeté comme bruit (2) :**

- « `dates_suspectes` peut rester bloqué à `True` un nombre indéfini de semaines si la source se tait après un mauvais lot » (Blind Hunter) — comportement cohérent avec `dernier_item_vu` (Story 4.1), qui gèle exactement de la même façon sur une nuit silencieuse ; pas une incohérence nouvelle introduite par cette story.
- « Confirmation de non-interaction avec `taux_echec`/`anomalie_pannes` non backée par un test dédié » (Blind Hunter, procédural) — traité par une reformulation de la story (« vérifié par lecture de code » plutôt que « confirmé explicitement »), pas par un nouveau test artificiel qui testerait l'absence d'un couplage qui n'existe simplement pas.

### Completion Notes List

- **AC1** : confirmé — une source dont le dernier lot enregistré porte ≥3 items à la même minute (seuil corrigé en revue, voir Review Findings) passe `suspecte` au contrôle suivant, même si `dernier_item_vu` est très récent (test dédié).
- **AC2** : confirmé — seuil absolu (`SEUIL_DATES_SUSPECTES = 3`, documenté en Dev Notes comme un choix délibéré plutôt qu'un seuil proportionnel) ; un lot avec un seul item, sans aucun doublon, ou avec un seul doublon isolé parmi de nombreux items à horaires distincts ne déclenche jamais le signal (test dédié ajouté en revue pour ce dernier cas précis, exactement celui que l'AC exclut).
- **AC3** : confirmé — une source `en_sommeil` reste `en_sommeil` même si son dernier lot enregistré (avant l'endormissement) portait des dates suspectes (précédence explicite dans `evaluer_fraicheur`, test dédié).
- **AC4** : confirmé — `detecter_dates_suspectes` isolée par son propre `try/except`, dégrade en `False`, jamais de levée.
- **AC5** : confirmé — 454 tests passent, tous les tests existants de la Story 4.1 inchangés et verts.
- Zéro nouveau fichier : `health.py` (fonction + logique étendue) et `store.py` (colonne supplémentaire), conforme aux Dev Notes.

### File List

- `src/veille/health.py` — modifié : `SEUIL_DATES_SUSPECTES` (=3, corrigé en revue), `detecter_dates_suspectes()`, `enregistrer_activite()` calcule et persiste `dates_suspectes` (toujours, même sans item plausible — corrigé en revue), `evaluer_fraicheur()` incorpore le signal avec précédence explicite.
- `src/veille/store.py` — modifié : `ouvrir()` ajoute la colonne `dates_suspectes` par migration additive, vérifiée via `PRAGMA table_info` (corrigé en revue, plutôt qu'un `try/except` sur le message d'erreur).
- `tests/test_health.py` — modifié : 10 nouveaux tests à l'implémentation, +2 en revue (lot futur persiste le signal, lot avec un seul doublon isolé parmi de nombreux items ne déclenche pas) ; fixture `_item_a` renommée `_item_avec_date`.
- `tests/test_store.py` — modifié en revue : +1 nouveau test (migration réelle d'un fichier pré-Story-4.2).
- `_bmad-output/implementation-artifacts/deferred-work.md` — modifié en revue : nouvelle section pour le constat reporté.
- `_bmad-output/implementation-artifacts/4-2-detecter-source-mensongere.md` — ce fichier (story).

### Change Log

| Date | Changement |
|---|---|
| 2026-09-15 | Story créée (`create-story`) et implémentée en une passe (Tasks 1-3) : `detecter_dates_suspectes` ajoutée, `enregistrer_activite`/`evaluer_fraicheur` étendus, colonne `dates_suspectes` migrée dans `sante_source`, 10 nouveaux tests, 454 passed, aucune régression. Statut → review. |
| 2026-09-15 | Revue (3 couches, Sonnet) : 4 correctifs appliqués (seuil corrigé de 2 à 3 — contradiction avec l'AC2 de la story elle-même, trouvée par l'Acceptance Auditor —, signal persisté même sans item plausible — convergence blind+edge —, migration de schéma robuste via `PRAGMA table_info`, fixture de test renommée), 1 reporté (déduplication par identité dans `detecter_dates_suspectes`, `deferred-work.md`), 2 rejetés comme bruit. 3 nouveaux tests, 457 passed. Statut → done. |
