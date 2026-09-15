---
baseline_commit: 46a9967
---

# Story 4.1: Détecter une source qui a arrêté de publier

Status: done

## Story

As a Abdoulaye,
I want savoir quand une source de mon socle s'est tue,
so that je ne découvre pas six mois plus tard qu'elle ne m'apportait plus rien.

## Acceptance Criteria

1. **[FR-12, AD-5]** Un état persistant par source (`active` / `suspecte` / `en_sommeil`) vit dans le même fichier SQLite que l'état « déjà vu » (AD-5 : « un fichier SQLite local est la seule source de vérité pour... l'`État d'une Source` » — même fichier, nouvelle table, pas un second store).
2. **[FR-12]** Chaque collecte nocturne (`collect.collecter()`) met à jour, pour chaque source **effectivement interrogée**, la date de publication la plus récente jamais vue pour cette source (`dernier_item_vu`) — de façon monotone (ne recule jamais sur une nuit sans nouvel item). Une source jamais encore collectée n'a pas d'anomalie présumée (même principe que le seuil de signal, Story 1.4 : l'absence de donnée n'est pas une présomption de problème).
3. **[FR-12, epics.md#Story-4.1]** Un contrôle de fraîcheur **hebdomadaire**, distinct de la collecte nocturne, évalue chaque source configurée à partir de `dernier_item_vu` : plus de 30 jours → `suspecte` ; plus de 90 jours (« 3 mois ») → `en_sommeil`. Une source qui redevient fraîche (nouvel item vu depuis) repasse `suspecte` → `active` au contrôle suivant.
4. **[FR-12, epics.md#Story-4.1]** Une source à l'état `en_sommeil` **n'est plus interrogée** par la collecte nocturne suivante — ni requête réseau, ni tentative de connecteur — jusqu'à une intervention humaine (édition de `sources.yaml`, hors périmètre de cette story). Le fait qu'elle soit ignorée est journalisé et compté dans le récapitulatif de collecte (`ResultatCollecte`), jamais silencieux.
5. **[Isolation, AD-6]** Aucune fonction de `health.py` ne lève hors de son propre `try/except` — une panne de lecture/écriture de l'état de santé dégrade (source traitée comme si elle n'avait pas d'état connu) sans jamais faire perdre la collecte ou la publication.
6. Le mécanisme de déclenchement hebdomadaire est un second workflow GitHub Actions (`schedule` + `workflow_dispatch`, même durcissement que `pipeline-nocturne.yml` — actions épinglées par SHA, `permissions` minimales, `timeout-minutes`), indépendant du pipeline nocturne : une panne du contrôle de fraîcheur ne doit jamais empêcher la publication du digest, et réciproquement.
7. Garde-fous existants inchangés ; suite complète verte sans régression.

## Tasks / Subtasks

- [x] Task 1 : Schéma et logique pure de `health.py` (AC: 1, 2, 3, 5)
  - [x] Étendre `store.ouvrir()` : `CREATE TABLE IF NOT EXISTS sante_source (source_id TEXT PRIMARY KEY, dernier_item_vu TEXT, etat TEXT NOT NULL DEFAULT 'active')` — même fichier, même fonction d'ouverture que `deja_vu` (AD-5, un seul propriétaire du schéma SQLite).
  - [x] Nouveau module `src/veille/health.py` : `enregistrer_activite(source_id, items, conn)` — met à jour `dernier_item_vu` avec `max(dernier_item_vu existant, max(item.date_publication for item in items))`, ne régresse jamais, ne fait rien si `items` est vide.
  - [x] `evaluer_fraicheur(sources, conn, aujourdhui) -> RapportSante` — pour chaque source configurée, lit `dernier_item_vu`, calcule l'âge en jours, transitionne l'`etat` (`SEUIL_SUSPECTE_JOURS = 30`, `SEUIL_SOMMEIL_JOURS = 90`), écrit le nouvel état, retourne un rapport (source → ancien/nouvel état) pour la Story 4.3 à venir. Une source sans `dernier_item_vu` connu reste `active` (donnée insuffisante ≠ anomalie).
  - [x] `sources_en_sommeil(conn) -> set[str]` — lecture seule, utilisée par `collect.collecter()`.
  - [x] Toute fonction publique de `health.py` isolée par son propre `try/except` (AD-6) : dégrade en ne modifiant rien / en renvoyant un ensemble vide, journalise, ne lève jamais.
  - [x] Tests unitaires (`tests/test_health.py`, 17 tests) : mise à jour monotone, transitions `active→suspecte→en_sommeil` et retour `suspecte→active`, source sans historique jamais marquée anomale, isolation sur connexion cassée.

- [x] Task 2 : Câbler dans `collect.collecter()` (AC: 2, 4, 7)
  - [x] Le paramètre `deja_vus_conn` de `collecter()`/`executer()` sert désormais une seconde fin (santé des sources, même fichier SQLite) — renommé en `store_conn` dans les deux fonctions et dans tous les appels/tests existants pour ne pas laisser un nom qui ne décrit plus qu'une moitié de son usage réel.
  - [x] Avant `_fetch_one(source_config)` dans la boucle par source : si `source_config.id` ∈ `health.sources_en_sommeil(store_conn)`, le connecteur n'est pas appelé — comptabilisé via un nouveau champ `ignoree_sommeil: bool` sur `RapportSource` (jamais un simple silence : nouvelle propriété `ResultatCollecte.sources_ignorees_sommeil`, ligne dédiée dans `resume()`, `est_muette` mis à jour pour ne plus confondre les deux états).
  - [x] Après une collecte réussie d'une source (qu'elle ait produit 0 ou N items) : `health.enregistrer_activite(source_config.id, items_source, store_conn)`.
  - [x] Tests d'intégration (`test_collect.py`, 3 nouveaux) : sans connexion, toutes les sources restent interrogées (non-régression) ; une source `en_sommeil` n'est pas interrogée (connecteur jamais appelé, vérifié par espion qui lève si appelé) et apparaît dans le rapport/`resume()` ; une source active voit `dernier_item_vu` mis à jour après collecte.

- [x] Task 3 : Déclencheur hebdomadaire (AC: 3, 6)
  - [x] Nouveau point d'entrée `pipeline.controler_fraicheur()`/`main_controle_sante()` (`python -m veille.pipeline --controle-sante`, même patron que `--bandeau-echec`) : synchronise l'état depuis le dépôt source, ouvre la connexion, charge `sources.yaml`, appelle `health.evaluer_fraicheur`, journalise le résumé, retéléverse l'état — réutilise `store.synchroniser_depuis_distant`/`televerser_vers_distant` tel quel, rien de dupliqué. Isolation dédiée sur l'ouverture (dégrade en `False`, jamais de levée) et sur le retéléversement (retour vérifié, `logger.warning` explicite si `False` — même discipline que le déjà-vu de la Story 3.4).
  - [x] Nouveau workflow `.github/workflows/controle-hebdomadaire.yml` : `schedule` hebdomadaire (dimanche 6h00 UTC, choix documenté en tête de fichier — aucune contrainte d'heure connue), `workflow_dispatch`, actions épinglées par SHA, `permissions: contents: write`, `SOURCE_GITHUB_TOKEN` mappé sur le jeton ambiant, `timeout-minutes: 10` (pas de collecte réseau ni d'appel LLM, plafond nettement plus bas que le pipeline nocturne). Indépendant de `pipeline-nocturne.yml` — `concurrency` group distinct (`controle-hebdomadaire`), pas de verrou partagé (la protection contre l'écrasement concurrent du fichier SQLite existe déjà côté `store.televerser_vers_distant`, upsert par `sha`).
  - [x] Prérequis réels documentés en tête du nouveau workflow : aucun secret supplémentaire (même `SOURCE_GITHUB_TOKEN` que la Story 3.4), ni `ANTHROPIC_API_KEY` ni `DIGEST_PUBLISH_TOKEN` nécessaires (ce job ne rend/n'enrichit/ne publie rien).

- [x] Task 4 : Validation (AC: 5, 7)
  - [x] Suite complète (`uv run pytest`) rejouée sans régression — 439 passed (413 avant cette story + 26 nouveaux : 17 `test_health.py` + 3 `test_collect.py` + 6 `test_pipeline.py`).
  - [x] Validation YAML du nouveau workflow (`python -c "import yaml; yaml.safe_load(...)"` → OK).

## Dev Notes

### Ce que l'architecture impose déjà (à ne pas réinventer)

`ARCHITECTURE-SPINE.md` nomme déjà ce module et sa place : `health.py — fraîcheur & mise en sommeil des sources (FR-12/13)`, lié à `AD-5`/`AD-6`. AD-5 est explicite : *« un fichier SQLite local est la seule source de vérité pour le "déjà vu par source" et l'État d'une Source. Seuls le contrôle de santé et l'étape publish... écrivent le store »* — c'est-à-dire que `health.py` a vocation à écrire l'état de santé dans le **même** fichier que `store.py` gère déjà depuis la Story 3.4, pas un second fichier ni un second mécanisme de synchronisation. Cette story réutilise donc tel quel : le fichier `data/deja-vu.sqlite3` (une seule table de plus, `sante_source` — renommer le fichier serait cosmétique et casserait le chemin distant déjà synchronisé, pas fait ici, noté comme dette mineure), `store.ouvrir()` (schéma étendu, pas dupliqué), `store.synchroniser_depuis_distant`/`televerser_vers_distant` (aucune nouvelle fonction de sync à écrire), le jeton `SOURCE_GITHUB_TOKEN` (déjà en place).

### Décisions prises pour cette story (pas dans l'AC brut d'epics.md, tranchées ici)

- **« 3 mois » = 90 jours** — aucune notion de mois n'existe ailleurs dans le code (toutes les fenêtres temporelles du projet sont en jours/secondes) ; 90 jours est l'équivalence la plus directe et reste facilement testable.
- **Une source `suspecte` reste collectée normalement** — seule `en_sommeil` arrête la collecte (c'est la formulation littérale de l'AC : « n'est plus interrogée » n'est associée qu'à l'état sommeil). Une source `suspecte` peut donc redevenir `active` au contrôle suivant si elle recommence à publier ; une source `en_sommeil`, elle, ne peut **pas** s'auto-réveiller — plus aucune collecte ne peut jamais mettre à jour `dernier_item_vu` une fois interrogée. C'est délibéré et cohérent avec la Story 4.3 à venir (« Abdoulaye... décide s'il les répare ou les retire ») : la réactivation est une décision humaine (édition de `sources.yaml`), pas un mécanisme automatique — n'en construire aucun ici serait de la généralité spéculative.
- **Renommage de `deja_vus_conn` → `store_conn`** — ce paramètre de `collecter()`/`executer()` sert désormais deux fins (déjà-vu, Story 3.4 ; santé des sources, cette story) sur la même connexion SQLite. Le garder nommé pour une seule de ses deux fins serait trompeur pour quiconque lit la signature sans le contexte complet des deux stories.
- **Second workflow GitHub Actions, pas une extension de `pipeline-nocturne.yml`** — le contrôle de fraîcheur a une cadence différente (hebdomadaire vs nocturne) et une panne de l'un ne doit jamais affecter l'autre (AC6). Mirroring direct du patron déjà validé et durci en revue par la Story 3.1 (actions épinglées par SHA, `permissions` minimales, `timeout-minutes`, `workflow_dispatch`) — pas de nouvelle réflexion architecturale nécessaire, seulement une application cohérente.

### Précédents à réutiliser, pas à réinventer

- **Isolation par sous-système (AD-6)** — même discipline que `store.py` (Story 3.4, renforcée en revue) : toute fonction de `health.py` isolée par son propre `try/except`, dégrade plutôt que de faire perdre la nuit.
- **« Donnée absente ≠ anomalie »** — principe déjà posé pour le seuil de signal (Story 1.4, décision #13 du journal) et pour l'identité déjà-vu (Story 3.4) : une source sans `dernier_item_vu` connu (jamais encore collectée) n'est jamais présumée `suspecte`/`en_sommeil`.
- **`RapportSource`/`ResultatCollecte.resume()`** (`collect.py`) — patron déjà établi pour exposer un diagnostic par source sans jamais le laisser silencieux (`est_muette`, `est_absorbee`, et depuis la Story 3.4 `ecartes_par_source` du déjà-vu) ; `ignoree_sommeil` suit exactement ce même patron.
- **`store.synchroniser_depuis_distant`/`televerser_vers_distant`** (Story 3.4) — mécanisme de persistance à travers les runners GitHub Actions éphémères déjà construit et testé ; le contrôle hebdomadaire le réutilise tel quel, pas de nouvelle logique de sync.

### Hors périmètre — ne pas anticiper

- **Story 4.2** (dates mensongères, items à la même minute) — mécanisme de détection distinct, pas construit ici.
- **Story 4.3** (récapitulatif consultable) — `evaluer_fraicheur` retourne déjà un rapport structuré (`RapportSante`) pour que 4.3 n'ait qu'à le consommer, mais aucune surface de consultation (section du digest, fichier séparé...) n'est construite dans cette story.
- **Story 4.4** (découverte de nouvelles sources) — sans lien direct avec cette story, mais partagera probablement le même workflow hebdomadaire (à voir lors de cette story-là — ne pas préjuger de sa forme ici).
- **Réactivation d'une source `en_sommeil`** — décision humaine hors périmètre (voir ci-dessus).

### Testing Standards

`pytest` via `uv run pytest`. Aucun appel réseau ni subprocess réel — mêmes conventions que `test_store.py` (Story 3.4) : connexions SQLite réelles sur fichier temporaire (`tmp_path`), horloge injectée explicitement (`aujourdhui` en paramètre de `evaluer_fraicheur`, jamais `datetime.now()` interne à la fonction — cohérent avec la leçon #47 du journal des décisions : un test de logique temporelle doit être déterministe, pas dépendre de l'horloge réelle).

### Previous Story Intelligence

- Story 3.4 : `store.py` au complet (identité, isolation, sync/upload, `PRAGMA journal_mode=DELETE`, découpage en lots pour les requêtes `IN (...)` à l'échelle) — tous les précédents directement réutilisables ici, rien à reconstruire.
- Story 3.4 (déviation notée) : cette story-ci **a** été créée via `create-story` avant implémentation — retour à la convention normale après l'écart ponctuel de la 3.4.
- Story 3.1 : patron de workflow GitHub Actions durci (concurrency, timeout, permissions minimales, actions épinglées par SHA) — appliqué tel quel au nouveau `controle-hebdomadaire.yml`.

### Git Intelligence Summary

Commits récents (locaux, non encore poussés — blocage `gh auth` `workflow` scope toujours en cours, 3 tentatives de device flow depuis le début de la Story 3.1) : Story 3.4 (`2e5e23c` impl+revue, `46a9967` docs — Epic 3 entièrement terminé).

### Project Structure Notes

Nouveau fichier `src/veille/health.py` (aux côtés de `store.py`, `dedup.py`, `filter.py`) et `.github/workflows/controle-hebdomadaire.yml` (aux côtés de `pipeline-nocturne.yml`) — conformes à la structure déjà anticipée par `ARCHITECTURE-SPINE.md`. `collect.py`/`pipeline.py` modifiés (renommage de paramètre + câblage), pas restructurés.

### References

- [Source: epics.md#Story-4.1] — story d'origine et critères d'acceptation
- [Source: ARCHITECTURE-SPINE.md#AD-5] — fichier SQLite unique, source de vérité pour le déjà-vu ET l'État d'une Source
- [Source: ARCHITECTURE-SPINE.md#AD-6] — isolation des pannes de source, étendue explicitement à `health.py`
- [Source: ARCHITECTURE-SPINE.md] — `health.py` nommé dans la structure de fichiers cible (FR-12/13)
- [Source: 3-4-ne-jamais-remontrer.md] — `store.py`, mécanisme de persistance/sync réutilisé tel quel
- [Source: 3-1-declencher-automatiquement.md] — patron de workflow GitHub Actions durci, réutilisé pour le contrôle hebdomadaire

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5 (`claude-sonnet-5`)

### Debug Log References

- `uv run pytest tests/test_health.py -q` : 17 passed.
- `uv run pytest tests/test_collect.py -q` : 16 passed (13 avant + 3 nouveaux).
- `uv run pytest tests/test_pipeline.py -q` : 28 passed (22 avant + 6 nouveaux).
- Suite complète (avant revue) : `uv run pytest -q` → 439 passed (413 avant cette story + 26 nouveaux), aucune régression.
- Validation YAML du nouveau workflow : `python -c "import yaml; yaml.safe_load(...)"` → OK.
- Suite complète (après revue) : `uv run pytest -q` → 444 passed (439 avant revue + 5 nouveaux).

### Review Findings

> Revue de code du 2026-09-14/15 (skill `bmad-code-review`, 3 couches adversariales, sur
> Sonnet 5 — même modèle que l'implémentation). Base de diff `46a9967` (= `baseline_commit`,
> changements non commités). Deux tentatives de lancement des 3 sous-agents ont buté sur
> une limite de session (HTTP 429) — retentées avec succès à la seconde fois, sans perte de
> contexte (les fichiers de diff/story étaient déjà écrits sur disque). Convergence
> blind+edge sur le constat le plus sérieux : `taux_echec`/`anomalie_pannes` (Story 2.2),
> non revisités par cette story, se dilue mécaniquement à mesure que des sources
> s'endorment — rendant l'alarme FR-2 de moins en moins sensible avec le temps, l'exact
> inverse de l'effet voulu par cette histoire.

**Correctifs appliqués (6) :**

- [x] [Review][Patch] `taux_echec`/`anomalie_pannes` divisaient par `len(self.rapports)`, qui inclut désormais les sources `en_sommeil` jamais tentées (Story 4.1) — une nuit où toutes les sources réellement interrogées échouent pouvait rester sous le seuil de 50 % simplement parce que le socle comptait aussi des sources endormies, gonflant artificiellement le dénominateur. Plus des sources s'endorment (l'issue même que cette story produit), moins l'alarme FR-2 devient sensible — l'inverse de l'effet voulu. Corrigé : nouvelle propriété `sources_tentees` (exclut `ignoree_sommeil`), `taux_echec` divise désormais par ce sous-ensemble. Constat convergent (Blind Hunter + Edge Case Hunter) [src/veille/collect.py]
- [x] [Review][Patch] `evaluer_fraicheur` n'isolait qu'au niveau global (un seul `try/except` autour de toute la boucle) — une seule ligne corrompue (`dernier_item_vu` illisible) aurait bloqué l'évaluation de **toutes** les sources du lot, chaque semaine, indéfiniment, sans qu'aucun journal ne nomme la source fautive. Corrigé : isolation par source (même philosophie qu'AD-6 pour `_fetch_one`, jamais appliquée jusqu'ici à ce module) — une ligne corrompue n'affecte plus que sa propre source. Constat (Blind Hunter) [src/veille/health.py]
- [x] [Review][Patch] Un item à date future (bug d'horloge côté source, flux malformé) aurait figé `dernier_item_vu` dans le futur de façon permanente — la règle « ne régresse jamais » (délibérée) empêchait alors toute correction ultérieure, et la source serait restée `active` indéfiniment même si elle s'était réellement tue depuis. Corrigé : `enregistrer_activite` ignore désormais tout item dont `date_publication > maintenant` (nouveau paramètre explicite, jamais lu en interne via `datetime.now()` — testable déterministe, `collect.py` lui passe l'horodatage déjà calculé en début de run). Constat (Edge Case Hunter) [src/veille/health.py, src/veille/collect.py]
- [x] [Review][Patch] Aucun test ne protégeait l'invariant explicitement documenté dans les Dev Notes (« une source `suspecte` reste collectée normalement, contrairement à `en_sommeil` ») — une future confusion des deux états (ex. skip sur `etat != ETAT_ACTIF` au lieu de `etat == ETAT_SOMMEIL`) serait passée inaperçue. Nouveau test ajouté. Constat (Blind Hunter, test-coverage gap) [tests/test_collect.py]
- [x] [Review][Patch] Clarification documentaire (pas un changement de comportement) : le module docstring de `health.py` précise désormais explicitement quelle lecture d'AD-5 est retenue — « l'État d'une Source » désigne le jugement (`etat`), pas la donnée brute qui l'alimente (`dernier_item_vu`) — pour lever l'ambiguïté soulevée par l'Acceptance Auditor sur le fait que `collect.collecter()` appelle une fonction qui écrit dans le même fichier que « le contrôle de santé ». Constat (Acceptance Auditor, PLAUSIBLE) [src/veille/health.py]
- [x] [Review][Patch] Tests ajoutés pour les 3 correctifs de comportement ci-dessus (item futur ignoré, item futur exclu d'un lot mixte, isolation par source sur une ligne corrompue) et pour la dilution de `taux_echec` (socle avec 3 sources en sommeil + 1 en échec : 100 % des sources tentées, pas 25 % du socle total). [tests/test_health.py, tests/test_rapport_collecte.py]

**Reporté (2)** — voir `deferred-work.md`, section « Deferred from: code review of 4-1-detecter-source-arretee » :

- Course entre `controle-hebdomadaire.yml` et `pipeline-nocturne.yml` sur le même fichier SQLite distant (upsert par `sha`, sans nouvelle tentative sur conflit) — risque narrow (déclenchements manuels rapprochés), déjà partiellement visible (log, pas silencieux), disproportionné à corriger pour un système mono-opérateur.
- AD-6 (« toute erreur de fetch journalisée dans l'état de santé ») satisfait seulement au niveau du run (`RapportSource.echec`), pas dans `sante_source` lui-même — hors périmètre littéral de l'AC de cette story (fraîcheur du contenu, pas codes d'erreur HTTP), probablement Story 4.2/enrichissement futur.

**Rejeté comme bruit (3) :**

- « Une source `en_sommeil` ne peut jamais se réveiller automatiquement » (Edge Case Hunter, noté « High ») — comportement **délibéré**, déjà documenté explicitement dans les Dev Notes de cette story avant la revue : l'AC dit littéralement « n'est plus interrogée », et la réactivation est une décision humaine (Story 4.3 : « il décide s'il les répare ou les retire »), pas un mécanisme automatique à construire ici.
- « `enregistrer_activite` commet à chaque source plutôt que de grouper les commits » (Blind Hunter, « Low », lui-même qualifié de « dwarfed by per-source network I/O ») — un commit SQLite supplémentaire par source est négligeable face au coût réseau déjà engagé par la collecte elle-même ; grouper les commits ajouterait de la complexité pour un gain non mesurable à cette échelle.
- « `--controle-sante` combiné à `--bandeau-echec` sur la même invocation exécute seulement le premier, sans avertissement » (Edge Case Hunter, « Low ») — même limite déjà acceptée pour `--bandeau-echec` seul face à l'absence de flag (dispatch `if/elif` volontairement simple, Story 3.2) ; les deux flags ne sont jamais combinés en usage réel (deux workflows distincts, jamais le même step).

### Completion Notes List

- **AC1** : confirmé — `sante_source` vit dans le même fichier SQLite que `deja_vu` (`store.ouvrir()` étendu, pas un second fichier), conformément à AD-5. Précisé en revue (Acceptance Auditor) : la portée exacte du texte AD-5 (« seuls le contrôle de santé et l'étape publish écrivent le store ») est désormais explicitée dans la docstring de `health.py` — « l'État d'une Source » y désigne le jugement (`etat`), écrit uniquement par `evaluer_fraicheur` (le contrôle de santé au sens strict), pas la donnée brute (`dernier_item_vu`) qu'`enregistrer_activite` met à jour chaque nuit.
- **AC2** : confirmé par `test_health.py`/`test_collect.py` — `enregistrer_activite` met à jour `dernier_item_vu` de façon monotone (jamais de régression sur une nuit sans nouvel item, vérifié explicitement) ; une source jamais collectée n'a aucune ligne, donc aucune anomalie présumée.
- **AC3** : confirmé — `evaluer_fraicheur` transitionne `active→suspecte` (>30j), `→en_sommeil` (>90j), et `suspecte→active` si à nouveau fraîche ; `aujourdhui` toujours injecté explicitement, jamais lu en interne (déterminisme des tests garanti).
- **AC4** : confirmé — une source `en_sommeil` n'est jamais passée à `_fetch_one` (vérifié par un espion qui lève si le connecteur est appelé) ; comptée dans `RapportSource.ignoree_sommeil`/`ResultatCollecte.sources_ignorees_sommeil`, visible dans `resume()`.
- **AC5** : confirmé — les 3 fonctions publiques de `health.py` sont chacune isolées par leur propre `try/except`, dégradent (rien de modifié / ensemble vide) sans jamais lever ; testé explicitement sur connexion cassée pour chacune.
- **AC6** : confirmé — nouveau workflow `controle-hebdomadaire.yml`, entièrement indépendant de `pipeline-nocturne.yml` (déclencheur, `concurrency` group, job propres) ; aucun des deux n'appelle l'autre.
- **AC7** : confirmé — 444 tests passent après revue, aucune modification de test existant en dehors du renommage mécanique `deja_vus_conn` → `store_conn` (paramètre + docstrings), imposé par la Task 2 elle-même et documenté comme tel.
- Renommage `deja_vus_conn` → `store_conn` appliqué partout (`collect.py`, `pipeline.py`, `tests/test_collect.py`) — aucune occurrence oubliée (vérifié par `grep -rn deja_vus_conn src/ tests/` après coup, ne reste que dans un commentaire de `collect.py` qui documente explicitement l'ancien nom).

### File List

- `src/veille/health.py` — nouveau : santé des sources (AD-5, AD-6, FR-12/13) ; modifié en revue : isolation par source dans `evaluer_fraicheur`, `enregistrer_activite` ignore les items à date future (`maintenant` explicite), clarification docstring sur la portée d'AD-5.
- `src/veille/store.py` — modifié : `ouvrir()` crée aussi la table `sante_source`.
- `src/veille/collect.py` — modifié : import `health`, paramètre `deja_vus_conn` renommé `store_conn`, sources en sommeil ignorées avant `_fetch_one`, `enregistrer_activite` appelée après chaque collecte active, `RapportSource.ignoree_sommeil` + `ResultatCollecte.sources_ignorees_sommeil`, `resume()`/`est_muette` mis à jour ; modifié en revue : `sources_tentees` (nouvelle propriété), `taux_echec` corrigé pour ne plus se diluer avec les sources en sommeil.
- `src/veille/pipeline.py` — modifié : import `health`, `deja_vus_conn` local renommé `store_conn`, nouvelles fonctions `controler_fraicheur()`/`main_controle_sante()`, dispatch CLI étendu (`--controle-sante`).
- `.github/workflows/controle-hebdomadaire.yml` — nouveau : déclencheur hebdomadaire.
- `tests/test_health.py` — nouveau : 17 tests ; +3 en revue (item futur ignoré, item futur exclu d'un lot mixte, isolation par source).
- `tests/test_collect.py` — modifié : import `store` (déjà présent), renommage `deja_vus_conn=` → `store_conn=`, 3 nouveaux tests ; +1 en revue (source `suspecte` toujours collectée).
- `tests/test_pipeline.py` — modifié : 6 nouveaux tests (`controler_fraicheur`/`main_controle_sante`).
- `tests/test_rapport_collecte.py` — modifié en revue : +1 nouveau test (dilution de `taux_echec` par des sources en sommeil).
- `_bmad-output/implementation-artifacts/deferred-work.md` — modifié en revue : nouvelle section pour les 2 constats reportés.
- `_bmad-output/implementation-artifacts/4-1-detecter-source-arretee.md` — ce fichier (story).

### Change Log

| Date | Changement |
|---|---|
| 2026-09-14 | Story créée (`create-story`) et implémentée en une passe (Tasks 1-4) : `health.py` créé, câblé dans `collect.py`/`pipeline.py` (renommage `deja_vus_conn`→`store_conn`), nouveau workflow hebdomadaire, 26 nouveaux tests, 439 passed, aucune régression. Statut → review. |
| 2026-09-15 | Revue (3 couches, Sonnet — 2 tentatives, la première ayant buté sur une limite de session HTTP 429) : 6 correctifs appliqués (dilution de `taux_echec`/`anomalie_pannes` par les sources en sommeil — convergence blind+edge —, isolation par source dans `evaluer_fraicheur`, item à date future ignoré dans `enregistrer_activite`, test manquant sur l'invariant `suspecte` toujours collectée, clarification docstring sur la portée d'AD-5, tests des correctifs), 2 reportés (`deferred-work.md`), 3 rejetés comme bruit. 5 nouveaux tests, 444 passed. Statut → done. |
