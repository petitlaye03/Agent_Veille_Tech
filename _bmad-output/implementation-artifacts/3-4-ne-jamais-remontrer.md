---
baseline_commit: 3a19f7b
---

# Story 3.4: Ne jamais remontrer un item déjà publié

Status: done

## Story

As a Abdoulaye,
I want ne jamais revoir dans mon digest un item déjà publié un jour précédent,
so that chaque matin m'apporte vraiment du neuf plutôt que des redites.

## Acceptance Criteria

1. **[FR3, AD-5, AD-11]** Étant donné un item déjà publié dans un digest antérieur, dont l'état « déjà vu » a été validé **après** cette publication réussie, quand ce même item réapparaît dans la collecte d'une nuit suivante, alors il est écarté **avant d'atteindre le filtrage** (seuil de signal, dédoublonnage, scoring, quotas) — et un item jamais publié auparavant reste éligible normalement.
2. **[AD-5]** L'état « déjà vu » est persistant : un fichier SQLite local (stdlib `sqlite3`) en est la seule source de vérité, et il survit à l'exécution éphémère d'un run GitHub Actions (Story 3.1) — synchronisé depuis le dépôt source avant chaque collecte, retéléversé après chaque publication réussie.
3. **[AD-11]** Un item n'est marqué « vu » qu'**après** une publication réussie (page **et** archive) — jamais avant, jamais sur un échec partiel : un run qui échoue après collecte mais avant publication doit pouvoir retenter les mêmes items à la prochaine reprise, sans qu'aucun n'ait été perdu entre-temps.
4. Les garde-fous existants continuent de passer sans modification ; les nouveaux tests s'ajoutent sans en modifier aucun.

## Tasks / Subtasks

- [x] Task 1 : État « déjà vu » persistant (AC: 1, 2)
  - [x] Nouveau module `src/veille/store.py` : `RapportDejaVu` (même patron que `filter.RapportFiltrageSignal`), `_cles_identite` (réutilise le format de `dedup._cles_identite` — `url:{normalisée}` / `guid:{source_id}:{guid}` — **sans** le repli par position de `dedup.py`, non pertinent d'une nuit à l'autre), `ouvrir` (SQLite local, table `deja_vu(cle TEXT PRIMARY KEY)`), `filtrer_deja_vus`, `marquer_vus`
  - [x] Câblage dans `collect.collecter()` : nouveau paramètre `deja_vus_conn: sqlite3.Connection | None = None`, filtrage appelé immédiatement après la boucle de collecte par source, **avant** `filtrer_par_signal` (littéralement « avant d'atteindre le filtrage », AC1) ; `None` par défaut → aucune régression pour les appelants existants (tests, `run()`)
  - [x] `ResultatCollecte.deja_vu: RapportDejaVu` exposé (positionné juste après `rapports`), surfacé dans `resume()` au même titre que `dedoublonnage`/`filtrage_signal`/`classement`/`quotas`

- [x] Task 2 : Persistance à travers les runs GitHub Actions éphémères (AC: 2)
  - [x] `store.py` committe le fichier SQLite lui-même dans le **dépôt source** (`petitlaye03/Agent_Veille_Tech`, privé — pas le dépôt de sortie public : cet état est un détail d'implémentation du pipeline, jamais publié), via l'API Contents de GitHub, réutilisant le même mécanisme d'upsert par `sha` que `publish.py` (`synchroniser_depuis_distant`/`televerser_vers_distant`)
  - [x] Jeton dédié `SOURCE_GITHUB_TOKEN` (repli sur `gh auth token` en local, même patron que `publish._jeton_depuis_gh_cli`, dupliqué plutôt que réutilisé — module volontairement indépendant, même esprit qu'AD-2 pour les connecteurs) — **distinct** de `DIGEST_PUBLISH_TOKEN` (scopé au dépôt de sortie, sans aucun droit sur le dépôt source)
  - [x] `.github/workflows/pipeline-nocturne.yml` : `permissions: contents: read` → `contents: write` (le job écrit désormais sur son propre dépôt) ; `SOURCE_GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}` ajouté à l'env du step d'exécution — mappé sur le jeton ambiant du job, aucun secret supplémentaire à configurer

- [x] Task 3 : Câblage dans l'orchestrateur, marquage après succès uniquement (AC: 3)
  - [x] `pipeline.executer()` : `store.synchroniser_depuis_distant()` avant la collecte, connexion ouverte (`store.ouvrir()`) et passée à `collecter(..., deja_vus_conn=...)`, fermée dans un `finally`
  - [x] `store.marquer_vus(resultat_collecte.items, deja_vus_conn)` puis `store.televerser_vers_distant()` appelés **seulement si `page_ok and archive_ok`** — jamais avant, jamais sur un échec (AD-11)
  - [x] Nouveaux paramètres `deja_vus_path`/`store_client` sur `executer()`, même convention d'injection que `sources_path`/`publish_client` — substituables par les tests, jamais de chemin/réseau réel touché sans injection explicite

- [x] Task 4 : Tests (AC: 1, 2, 3, 4)
  - [x] `tests/test_store.py` (25 tests, nouveau fichier) : `_cles_identite`, `RapportDejaVu.resume()`, `ouvrir`/`filtrer_deja_vus`/`marquer_vus` (dont idempotence, persistance à travers une réouverture, conservation d'un item sans identité vérifiable), résolution du jeton, `synchroniser_depuis_distant`/`televerser_vers_distant` (client simulé, mêmes patrons `_FakeResponse`/`_FakeClient` que `test_publish.py` — création 201/mise à jour 200, jamais de levée sur panne réseau)
  - [x] `tests/test_collect.py` (+3 tests) : sans connexion → aucun filtrage (non-régression) ; item marqué vu → écarté au passage suivant ; un item jamais vu reste éligible aux côtés d'un item écarté
  - [x] `tests/test_pipeline.py` (+3 tests, +fixture d'isolation autouse) : marquage+retéléversement seulement après succès ; rien n'est marqué ni retéléversé si la publication échoue ; bout en bout sur deux runs successifs (le second ne republie plus rien, tout est déjà vu)
  - [x] Fixture autouse `_isoler_le_stockage_deja_vu` (`test_pipeline.py`) : isole **tous** les tests existants du vrai `data/deja-vu.sqlite3` du dépôt de travail et de toute résolution de jeton réelle — sans elle, chaque test appelant `pipeline.executer()` aurait pollué le disque du dépôt et tenté de résoudre `gh auth token`

## Dev Notes

### Pourquoi SQLite committé dans le dépôt source, pas un service dédié

AD-5 mandate un fichier SQLite local comme seule source de vérité pour l'état persistant du pipeline. Un runner GitHub Actions est éphémère (Story 3.1) : rien n'y survit d'un run à l'autre sauf ce qui est explicitement synchronisé vers un stockage durable. Plutôt qu'un service de stockage tiers (coût, complexité, nouvelle dépendance), le fichier SQLite est lui-même committé dans le dépôt source (privé) via l'API Contents déjà construite et testée pour `publish.py` — le fichier reste minuscule à cette échelle (identifiants d'articles, pas leur contenu), et ce mécanisme est gratuit (NFR1).

**Dépôt source, pas dépôt de sortie** : décision délibérée — cet état est un détail d'implémentation du pipeline, jamais du contenu destiné à être publié. Le séparer strictement du dépôt de sortie public évite de mélanger deux préoccupations distinctes (état interne vs. contenu publié) et un jeton compromis sur l'un des deux dépôts n'expose jamais l'autre.

### Identité : réutiliser `dedup.py`, pas réinventer

`store._cles_identite` reprend exactement le format de `dedup._cles_identite` (`url:{normalisée}`, `guid:{source_id}:{guid}`) pour une raison de cohérence : « le même article » doit signifier la même chose partout dans le pipeline. Seul le repli par position de `dedup.py` est délibérément exclu — la position d'un item dans le lot d'une nuit n'a aucun sens d'une nuit à l'autre, contrairement à la position au sein d'un même run où elle sert de dernier repli pour des doublons sans URL ni guid exploitables.

Un item sans URL ni `guid` exploitable n'est simplement jamais reconnaissable comme « déjà vu » — conservé par défaut, jamais écarté sur une identité qu'on ne peut pas vérifier (même principe que `filtrer_par_signal`, Story 1.4 : l'absence de donnée n'est pas une présomption de doublon).

### Ordre exact dans `collect.collecter()`

L'AC dit littéralement « écarté avant d'atteindre le filtrage ». Le filtrage déjà vu est donc inséré **avant toute autre étape** de filtrage — immédiatement après la boucle de collecte par source, avant même `filtrer_par_signal` (qui passait déjà avant le dédoublonnage depuis la Story 1.5). Un item déjà publié une nuit précédente ne doit même pas être considéré par le seuil de signal, le dédoublonnage ou le scoring.

### AD-11 : marquer après succès, jamais avant

Contrainte de conception posée dès la Story 3.2 (bandeau d'échec) et appliquée ici : `marquer_vus()` n'est appelée par `pipeline.executer()` qu'une fois `page_ok and archive_ok` confirmés tous les deux. Marquer plus tôt (par exemple juste après la collecte) romprait la garantie de reprise : un run qui échoue après collecte mais avant publication perdrait silencieusement les items de la nuit — plus jamais retentés, alors qu'ils n'ont jamais été effectivement publiés.

### Isolation des tests du vrai `data/deja-vu.sqlite3`

Trouvé en cours d'implémentation (pas en revue formelle) : sans isolation explicite, chaque test de `test_pipeline.py` appelant `pipeline.executer()` sans `deja_vus_path` ouvrait/écrivait le fichier par défaut du dépôt de travail (`data/deja-vu.sqlite3`, déjà gitignoré mais polluant le disque local à chaque run de suite de tests) et tentait de résoudre un jeton réel via `gh auth token` (présent sur la machine de dev — risque d'appel réseau réel en test). Résolu par une fixture autouse qui monkeypatch `store.CHEMIN_LOCAL_DEFAUT` vers `tmp_path` et neutralise `store._jeton`, appliquée à tous les tests de `test_pipeline.py` par défaut ; les tests dédiés au câblage du stockage remplacent explicitement ce qu'il faut par-dessus (chemin/client simulé injectés).

### Précédents réutilisés, pas réinventés

- **`filter.RapportFiltrageSignal`** (Story 1.4) — patron de rapport par source réutilisé tel quel pour `RapportDejaVu`.
- **`dedup._cles_identite`** (Story 1.5) — format d'identité réutilisé (sans le repli par position).
- **API Contents de GitHub, upsert par `sha`** (`publish.py`, Stories 1.8/1.9) — mécanisme réutilisé par `store.py` pour un second dépôt, avec un second jeton.
- **`_FakeResponse`/`_FakeClient`** (`test_publish.py`) — patron de client HTTP simulé réutilisé pour `test_store.py`.
- **`publish._jeton_depuis_gh_cli`** — patron de repli dupliqué (pas importé) dans `store.py`, module volontairement indépendant.

### Testing Standards

`pytest`, via `uv run pytest`. Aucun appel réseau ni subprocess réel : `store._jeton` neutralisé par défaut dans `test_pipeline.py` (fixture autouse), clients HTTP toujours simulés dans `test_store.py`.

### Previous Story Intelligence

- Story 3.2 : `if: failure() || cancelled()`, marqueurs de commentaires HTML idempotents — patrons de robustesse pour du code qui tourne sans supervision, même discipline appliquée ici (dégradation propre partout dans `store.py`, jamais de levée).
- Story 3.3 : mécanisme d'upsert par `sha` déjà vérifié de bout en bout à l'échelle de l'orchestrateur — directement réutilisé par `store.televerser_vers_distant`.

### Git Intelligence Summary

Commits récents (locaux, non encore poussés — blocage `gh auth` `workflow` scope en cours de résolution, voir rapport-projet.md §9) : Story 3.1 (`5097795`/`2a5b02a`), Story 3.2 (`f4a42da`/`8bf6303`), Story 3.3 (`847f874`/`3a19f7b`).

### Project Structure Notes

Aucun écart avec le Structural Seed : nouveau module `src/veille/store.py` (aux côtés de `dedup.py`/`filter.py`/`publish.py`), `collect.py`/`pipeline.py` modifiés pour le câbler, `.github/workflows/pipeline-nocturne.yml` étendu (permissions + variable d'environnement).

### References

- [Source: epics.md#Story-3.4] — story d'origine et critères d'acceptation
- [Source: ARCHITECTURE-SPINE.md#AD-5] — fichier SQLite local, seule source de vérité pour l'état persistant
- [Source: ARCHITECTURE-SPINE.md#AD-11] — validation de l'état « déjà vu » uniquement après publication réussie
- [Source: 1-8-publication-page.md, 1-9-archive-markdown.md] — mécanisme d'upsert par `sha` déjà construit et testé
- [Source: 3-1-declencheur-nocturne.md] — runner GitHub Actions éphémère, contrainte à l'origine de la persistance par commit

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5 (`claude-sonnet-5`)

### Debug Log References

- `uv run pytest tests/test_store.py -q` : 25 passed.
- `uv run pytest tests/test_collect.py -q` : 13 passed (10 avant + 3 nouveaux).
- `uv run pytest tests/test_pipeline.py -q` : 18 passed (15 avant + 3 nouveaux).
- Suite complète (avant revue) : `uv run pytest -q` → 406 passed (375 avant cette story + 31 nouveaux : 25 `test_store.py` + 3 `test_collect.py` + 3 `test_pipeline.py`), aucune régression.
- Validation YAML du workflow modifié : `python -c "import yaml; yaml.safe_load(...)"` → OK.
- Suite complète (après revue) : `uv run pytest -q` → 413 passed (406 avant revue + 7 nouveaux : 3 `test_store.py` + 4 `test_pipeline.py`).

### Review Findings

> Revue de code du 2026-09-14 (skill `bmad-code-review`, 3 couches adversariales, sur
> Sonnet 5 — même modèle que l'implémentation, convention établie). Base de diff
> `3a19f7b` (= `baseline_commit`, changements non commités). Diff substantiel (nouveau
> module + câblage dans 2 fichiers existants + workflow) : les 3 couches ont convergé
> sur le même constat le plus sévère — le retour booléen de `televerser_vers_distant()`
> était silencieusement ignoré dans `pipeline.py`, un échec de retéléversement après une
> publication pourtant réussie pouvant faire réapparaître les items d'une nuit à la
> suivante sans la moindre trace dans les logs. Convergence blind+edge sur un second
> constat : une panne du sous-système « déjà vu » lui-même (ouverture SQLite, filtrage)
> n'était pas isolée de la même façon que le reste du pipeline (AD-6), risquant de faire
> perdre toute la nuit pour une panne d'un sous-système annexe.

**Correctifs appliqués (7) :**

- [x] [Review][Patch] Retour de `store.televerser_vers_distant()` silencieusement ignoré dans `pipeline.executer()` — un échec de retéléversement après une publication réussie (réseau, jeton expiré, `sha` périmé) laissait les marques « vu » strictement locales à ce run éphémère, jamais vues du prochain run, qui pouvait donc republier les mêmes items sans que rien ne le signale (le run était même rapporté comme un succès). Corrigé : le retour est vérifié, un `logger.warning` explicite rend l'échec visible dans les logs du run (pas de nouvelle tentative — même discipline que `publish.py`). Constat convergent (Blind Hunter + Edge Case Hunter + Acceptance Auditor, les 3 couches) [src/veille/pipeline.py]
- [x] [Review][Patch] Un item dont le `registre` n'est reconnu par aucune section rendue (`render._grouper_par_registre`, dégradation pré-existante documentée depuis la Story 1.8 — un registre inconnu de `filter.CHAMPS_QUOTAS` est journalisé puis absent de toute section publiée) était tout de même marqué « vu » par le nouveau code, car `marquer_vus` recevait tout `resultat_collecte.items` sans distinction. Un item jamais réellement montré à l'utilisateur disparaissait ainsi en permanence de toute collecte future. Corrigé : seuls les items dont le registre correspond à une section réellement rendue (`item.registre in CHAMPS_QUOTAS`) sont marqués. Constat (Acceptance Auditor) [src/veille/pipeline.py]
- [x] [Review][Patch] `store.ouvrir()` (peut légitimement lever — fichier local corrompu, disque plein) n'était isolé que par le filet de sécurité englobant de `executer()`, qui aurait alors fait échouer **toute** la nuit (collecte, enrichissement, publication comprises) pour une simple panne du sous-système « déjà vu » — contraire à l'esprit d'isolation par sous-système déjà établi ailleurs (AD-6). Corrigé : `store.ouvrir()` est isolé par son propre `try/except`, dégrade en désactivant le filtrage « déjà vu » pour ce run (`deja_vus_conn = None`) sans jamais faire perdre la collecte/publication. Constat convergent (Blind Hunter + Edge Case Hunter) [src/veille/pipeline.py]
- [x] [Review][Patch] Le marquage/retéléversement après succès n'était pas isolé de son propre `try` — une exception dans `marquer_vus`/`televerser_vers_distant` (ex. disque plein pendant l'insertion) aurait fait remonter jusqu'au filet de sécurité englobant de `executer()`, **requalifiant en échec un run dont la publication avait pourtant réellement réussi**. Corrigé : bloc dédié avec son propre `try/except`, la publication déjà réussie n'est jamais remise en cause par une panne à cette étape ultérieure. Constat (Blind Hunter, en lien avec la docstring de `pipeline.py` qui affirmait à tort que les fonctions de `store.py` « ne lèvent jamais ») [src/veille/pipeline.py]
- [x] [Review][Patch] `filtrer_deja_vus` construit une unique requête `IN (...)` avec un paramètre lié par clé d'identité (jusqu'à 2 par item), sans découpage — avec le socle à 17 sources (Story 2.1), une nuit à fort volume peut dépasser le plafond de paramètres liés de SQLite (`SQLITE_MAX_VARIABLE_NUMBER`) et lever `sqlite3.OperationalError`, non intercepté (perte de toute la nuit pour une raison purement liée au volume). Corrigé par un découpage en lots de 500 clés, combiné à une isolation totale (`try/except`, dégrade en absence de filtrage plutôt que de lever) — la fonction tient désormais réellement sa promesse de « ne jamais lever ». Constat (Edge Case Hunter, renforcé par Blind Hunter) [src/veille/store.py]
- [x] [Review][Patch] Mode journal SQLite non fixé explicitement dans `store.ouvrir()` — `televerser_vers_distant()` lit le fichier en octets bruts (`read_bytes()`), pas via SQL ; un mode WAL (persistant dans l'en-tête du fichier) laisserait des lignes commitées dans un fichier `-wal` compagnon jamais lu ni téléversé, une perte silencieuse de marques « vu ». Corrigé par `PRAGMA journal_mode=DELETE` explicite à l'ouverture. Constat (Edge Case Hunter) [src/veille/store.py]
- [x] [Review][Patch] Commentaire clarifiant ajouté : `CHEMIN_DISTANT` correspond au motif `*.sqlite3` exclu par `.gitignore`, sans contradiction réelle — l'API Contents écrit directement dans l'historique du dépôt sans jamais passer par une commande `git` locale, donc `.gitignore` ne s'y applique tout simplement pas. Trouvé comme un piège latent pour un futur contributeur (Blind Hunter), corrigé par documentation plutôt que par un changement de comportement [src/veille/store.py]

**Reporté (3)** — voir `deferred-work.md`, section « Deferred from: code review of 3-4-ne-jamais-remontrer » :

- `permissions: contents: write` élargit le rayon d'action de tout le job, pas seulement l'écriture du fichier « déjà vu » — compromis assumé, inhérent à l'architecture choisie (aucune réduction supplémentaire possible via la configuration GitHub Actions seule).
- Aucune stratégie de purge/rétention sur la table `deja_vu` — sans conséquence à l'échelle actuelle, aucun plan pour un horizon long.
- Plafond ~1 Mo du champ `content` de l'API Contents de GitHub, non surveillé — dégraderait silencieusement (mais sans planter) si le fichier synchronisé venait un jour à approcher ce seuil.

**Rejeté comme bruit (1) :**

- « Race TOCTOU entre le `GET` de résolution du `sha` et le `PUT` dans `televerser_vers_distant` » (Blind Hunter) — un vrai scénario, mais dont la conséquence (le `PUT` échoue, `televerser_vers_distant` renvoie `False`) est désormais entièrement couverte par le correctif du premier constat ci-dessus (le `False` est maintenant visible via le `logger.warning`) ; pas une action distincte à mener en plus.

### Completion Notes List

- **AC1** : confirmé par `test_collect.py` — un item marqué vu est écarté dès `collecter()`, avant même `filtrer_par_signal` ; un item jamais vu reste éligible aux côtés d'un item écarté dans le même lot.
- **AC2** : `store.py` construit et testé (28 tests unitaires après revue, synchronisation/retéléversement simulés, découpage en lots et mode journal explicite ajoutés en revue) ; persistance à travers une fermeture/réouverture de connexion vérifiée directement. La persistance **réelle** à travers un run GitHub Actions (jeton ambiant, dépôt source réel) ne peut être vérifiée qu'en production — hors de portée des tests unitaires par construction, cohérent avec le traitement déjà réservé aux autres mécanismes réseau du projet (Stories 3.1-3.3). Un échec de retéléversement (réseau, jeton, `sha` périmé) n'est plus silencieux depuis la revue : journalisé explicitement, sans nouvelle tentative (même discipline que `publish.py`).
- **AC3** : confirmé par `test_pipeline.py` — `marquer_vus`/`televerser_vers_distant` ne sont appelés que si `page_ok and archive_ok`, jamais sur un échec de publication (aucune ligne insérée en base dans ce cas). Renforcé en revue : seuls les items réellement rendus (registre reconnu) sont marqués, et une exception dans ce bloc ne requalifie plus un run par ailleurs réussi en échec.
- **AC4** : confirmé — 413 tests passent après revue, aucune modification de test existant (uniquement des ajouts + une fixture autouse d'isolation nécessaire pour que les tests existants restent hermétiques face au nouveau câblage).
- Cette story a été démarrée en implémentation directe, sans passer par le skill `create-story` en amont (déviation de la convention établie depuis la Story 1.1) — ce fichier est rédigé rétroactivement, immédiatement après l'implémentation et avant la revue, pour préserver la piste d'audit complète malgré cet écart d'ordre.
- Convention de commit à reproduire (Stories 1.4-3.3) : un commit implémentation+revue, un commit séparé pour `docs/rapport-projet.md`, tous deux à pousser sur `origin/main` dès la résolution du blocage `gh auth` (8 commits locaux en attente une fois cette story committée).

### File List

- `src/veille/store.py` — nouveau : état « déjà vu » persistant (AD-5, AD-11) ; modifié en revue : `PRAGMA journal_mode=DELETE` explicite, `filtrer_deja_vus` isolée et découpée en lots, commentaire clarifiant sur `.gitignore`.
- `src/veille/collect.py` — modifié : import `store`, paramètre `deja_vus_conn` sur `collecter()`, filtrage inséré avant `filtrer_par_signal`, champ `deja_vu` sur `ResultatCollecte` (dataclass + `resume()`).
- `src/veille/pipeline.py` — modifié : import `store`, synchronisation avant collecte, connexion passée à `collecter()`, marquage+retéléversement après succès uniquement, paramètres `deja_vus_path`/`store_client` sur `executer()` ; modifié en revue : `store.ouvrir()` isolé par son propre `try/except`, bloc marquage/retéléversement isolé de son propre `try/except`, retour de `televerser_vers_distant` vérifié et journalisé, filtrage par `CHAMPS_QUOTAS` avant marquage.
- `.github/workflows/pipeline-nocturne.yml` — modifié : `permissions: contents: write`, `SOURCE_GITHUB_TOKEN` ajouté au step d'exécution, commentaires d'en-tête étendus.
- `tests/test_store.py` — nouveau : 25 tests ; +3 en revue (découpage en lots, dégradation sans lever, mode journal).
- `tests/test_collect.py` — modifié : import `store`, 3 nouveaux tests.
- `tests/test_pipeline.py` — modifié : import `store`, fixture autouse `_isoler_le_stockage_deja_vu`, 3 nouveaux tests ; +4 en revue (échec de retéléversement journalisé sans faire échouer le run, exception de marquage isolée, panne d'ouverture isolée, item de registre inconnu jamais marqué).
- `_bmad-output/implementation-artifacts/deferred-work.md` — modifié en revue : nouvelle section pour les 3 constats reportés.
- `_bmad-output/implementation-artifacts/3-4-ne-jamais-remontrer.md` — ce fichier (story, rédigée rétroactivement).

### Change Log

| Date | Changement |
|---|---|
| 2026-09-14 | Story implémentée en une passe (Tasks 1-4), fichier de story rédigé rétroactivement immédiatement après (déviation notée dans Completion Notes) : `store.py` créé, câblé dans `collect.py`/`pipeline.py`, workflow étendu, 31 nouveaux tests, 406 passed, aucune régression. Statut → review. |
| 2026-09-14 | Revue (3 couches, Sonnet) : 7 correctifs appliqués (retour de `televerser_vers_distant` désormais vérifié et journalisé — convergence 3/3 —, item de registre inconnu jamais marqué vu, panne d'ouverture SQLite isolée, marquage/retéléversement isolé de son propre `try`, requête « déjà vu » découpée en lots + isolée totalement, mode journal SQLite fixé explicitement, commentaire `.gitignore` clarifié), 3 reportés (`deferred-work.md`), 1 rejeté comme bruit (couvert par le premier correctif). 7 nouveaux tests, 413 passed. Statut → done. |
