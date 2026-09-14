---
baseline_commit: 2a5b02a
---

# Story 3.2: Reprendre proprement après un échec, sans perdre d'items

Status: done

## Story

As a Abdoulaye,
I want qu'un plantage en pleine nuit ne me fasse perdre aucune actualité,
so that le dernier digest réussi reste visible en attendant la reprise.

## Acceptance Criteria

1. **[FR-11, AD-11]** Étant donné un run qui échoue avant que la publication de la page/archive ne réussisse (collecte, enrichissement, rendu ou publication elle-même), **aucun item n'est marqué « déjà vu »** — non applicable aujourd'hui à la lettre (aucun état « déjà vu » n'existe encore, Story 3.4), mais posé ici comme contrainte de conception à respecter par la Story 3.4 quand elle construira ce mécanisme : le principe AD-11 (« déjà vu validé seulement après publication réussie ») doit gouverner sa conception dès le départ, pas être ajouté après coup.
2. **[FR-11]** Étant donné un run qui échoue à n'importe quelle étape avant la publication, **le dernier digest publié avec succès reste affiché tel quel** sur la page — verrouillé par un test réel qui force un échec à plusieurs points du pipeline (`collecter`, `enrichir`, `rendre`) et confirme qu'aucun appel de publication n'est jamais atteint.
3. **[FR-11]** Étant donné un run qui échoue (à n'importe quelle étape, y compris une panne d'infrastructure du runner CI lui-même — timeout, `uv sync` en échec), **un bandeau honnête indique l'absence de mise à jour cette nuit-là**, ajouté à la page déjà publiée sans en perdre le contenu. Le bandeau disparaît automatiquement dès la prochaine publication réussie (`rendre()` régénère la page entière à partir de zéro).
4. **[Idempotence du bandeau]** Deux nuits d'échec consécutives ne doivent jamais empiler deux bandeaux ni produire un HTML invalide — le mécanisme remplace le bandeau existant s'il y en a déjà un, plutôt que d'en ajouter un second.
5. Les garde-fous existants (`test_pipeline.py`, `test_publish.py`, `test_render.py`) continuent de passer sans modification ; les nouveaux tests s'ajoutent sans en modifier aucun.

## Tasks / Subtasks

- [x] Task 1 : Verrouiller par un test réel que l'échec avant publication ne touche jamais la page existante (AC: 2)
  - [x] 3 nouveaux tests dans `test_pipeline.py` (`collecter`/`enrichir`/`rendre` forcés à lever via monkeypatch) confirment que `publier`/`publier_archive` (client simulé) ne sont jamais appelés dans les trois cas — verrouille ce que le filet de sécurité de `executer()` garantissait déjà par construction ; zéro modification de `pipeline.py` pour cette Task, comme prévu

- [x] Task 2 : Publier un bandeau honnête sur échec (AC: 3, 4)
  - [x] `render.py` : `rendre_bandeau_echec(date_echec) -> str` — fragment HTML minimal, délimité par `BANDEAU_ECHEC_DEBUT`/`BANDEAU_ECHEC_FIN` (`<!-- BANDEAU-ECHEC:DEBUT/FIN -->`)
  - [x] `publish.py` : `publier_bandeau_echec(bandeau, client=None) -> bool` — signature légèrement différente du plan initial (prend le **fragment déjà rendu**, pas la date) : sépare proprement « rendre » (render.py) de « publier » (publish.py), même séparation de responsabilités que `rendre()`/`publier()` pour le pipeline normal. Récupère contenu+`sha` actuels de `index.html`, insère après `<body>` si aucun marqueur, **remplace** entre marqueurs sinon (`_inserer_bandeau`, idempotence AC4), republie par upsert
  - [x] `pipeline.py` : `main_bandeau_echec()` — point d'entrée CLI dédié (`python -m veille.pipeline --bandeau-echec`), jamais appelé par `executer()`/`main()` ; dégrade proprement, code de sortie non nul si la publication échoue
  - [x] `.github/workflows/pipeline-nocturne.yml` : nouveau step `if: failure()` après le step d'exécution — couvre uniformément échec applicatif et panne d'infrastructure du runner

- [x] Task 3 : Tests du bandeau (AC: 3, 4)
  - [x] `test_render.py` : 2 tests (`rendre_bandeau_echec` — marqueurs + date, pas un document complet)
  - [x] `test_publish.py` : 5 tests (`publier_bandeau_echec`/`_inserer_bandeau` — insertion, remplacement idempotent, page inexistante, sans jeton, panne réseau)
  - [x] `test_pipeline.py` : 3 tests (`main_bandeau_echec` — appelle render puis publish, code de sortie sur échec de publication, ne lève jamais)

- [x] Task 4 : Validation (AC: 5)
  - [x] Suite complète (`uv run pytest`) rejouée sans régression — 373 passed après revue (353 avant cette story + 20 nouveaux)
  - [x] Aucun **corps** de test existant modifié — confirmé par `git diff --stat` : uniquement des ajouts, à l'exception d'une ligne d'import mise à jour dans `test_render.py` (nouveaux noms exportés par `render.py`), pas le comportement d'un test existant

### Review Findings

> Revue de code du 2026-09-14 (skill `bmad-code-review`, 3 couches adversariales, sur
> Sonnet 5 — même modèle que l'implémentation, convention établie). Base de diff
> `2a5b02a` (= `baseline_commit`, changements non commités). Les 3 couches ont
> convergé indépendamment sur le constat le plus sérieux : `if: failure()` ne couvre
> pas un job annulé par `timeout-minutes` (conclusion `cancelled`, pas `failed`) —
> précisément le scénario de panne d'infrastructure que l'AC3 nomme explicitement.

**Correctifs appliqués (10) :**

- [x] [Review][Patch] `if: failure()` ne se déclenche pas quand `timeout-minutes` annule le job (conclusion `cancelled`, distincte de `failed` dans le modèle de GitHub Actions) — le seul scénario d'infrastructure nommé explicitement par l'AC3 (« timeout ») n'était donc pas couvert par le step censé le couvrir. Corrigé : `if: failure() || cancelled()`. Constat convergent (Blind Hunter + Edge Case Hunter + Acceptance Auditor) [.github/workflows/pipeline-nocturne.yml]
- [x] [Review][Patch] `_inserer_bandeau` passait `bandeau` comme chaîne de remplacement brute à `re.sub`, qui interprète `\1`/`\g<0>` — un bandeau contenant un antislash aurait pu lever `re.error` ou corrompre le HTML publié, silencieusement avalé par le `except Exception` englobant. Corrigé par une fonction de remplacement (`lambda _m: bandeau`), vérifié par un test avec un antislash littéral. Constat (Acceptance Auditor, reproduit) [src/veille/publish.py]
- [x] [Review][Patch] `main_bandeau_echec` traitait « aucune page à annoter » (cas explicitement documenté comme « pas une panne » dans la docstring de `publier_bandeau_echec`) exactement comme une vraie panne — même code de sortie non nul, fausse alerte systématique la toute première nuit où le pipeline échoue avant d'avoir jamais publié. Corrigé : `publier_bandeau_echec` renvoie désormais `True`/`False`/`None` (trois états), `main_bandeau_echec` sort avec 0 pour `None`. Constat convergent (Edge Case Hunter + Acceptance Auditor) [src/veille/publish.py, src/veille/pipeline.py]
- [x] [Review][Patch] `corps["sha"] = charge.get("sha")` envoyait `"sha": null` explicite si absent, contrairement à la garde déjà en place dans `_publier()` (`if sha: ...`) — incohérence non expliquée entre deux fonctions du même module. Corrigé pour suivre la même garde. Constat convergent (Edge Case Hunter + Blind Hunter) [src/veille/publish.py]
- [x] [Review][Patch] L'insertion après `<body>` ne matchait que la balise nue littérale (`str.replace("<body>", ...)`) — une balise avec attributs (`<body class="...">`) aurait raté l'insertion et fait tomber sur le repli « pas de `<body>` », produisant un HTML invalide (bandeau avant `<!doctype html>`). Corrigé par une regex tolérant les attributs, testée. Constat (Edge Case Hunter) [src/veille/publish.py]
- [x] [Review][Patch] Le repli « pas de `<body>` du tout » n'avait aucun test, malgré un raisonnement explicite dans la docstring. Nouveau test ajouté. Constat (Blind Hunter) [tests/test_publish.py]
- [x] [Review][Patch] Un `content` absent/vidé par l'API GitHub (ex. fichier trop volumineux pour une réponse en ligne) aurait levé une `KeyError` avalée par le `except Exception` générique, journalisée comme une panne générique plutôt que sa cause réelle. Corrigé par une vérification explicite avant décodage. Constat (Edge Case Hunter) [src/veille/publish.py]
- [x] [Review][Patch] Les Dev Notes affirmaient que `publier_bandeau_echec` « réutilise `_sha_existant` » — faux, le code dupliquait une troisième fois le patron GET/404/`raise_for_status`. Corrigé par un vrai partage : nouvelle fonction `_charge_existante`, dont `_sha_existant` et `publier_bandeau_echec` dépendent désormais toutes les deux. Constat (Blind Hunter) [src/veille/publish.py]
- [x] [Review][Patch] Le bandeau utilisait `date_echec.isoformat()` (`AAAA-MM-JJ`) et des couleurs codées en dur, alors que le reste du site utilise `%d/%m/%Y` (`digest.html.j2`) et un système de variables CSS clair/sombre déjà en place (`--recommandee-bg`/`--border`/etc.). Corrigé : format de date aligné, deux nouvelles variables `--bandeau-echec-bg`/`--bandeau-echec-fg` ajoutées au `:root`/bloc sombre existant. Constat (Blind Hunter) [src/veille/render.py, templates/digest.html.j2]
- [x] [Review][Patch] Aucun test ne combinait le vrai `render.rendre_bandeau_echec()` avec `publish.publier_bandeau_echec()` — les deux étaient couplés par les marqueurs (`BANDEAU_ECHEC_DEBUT`/`FIN`) mais testés uniquement avec des chaînes écrites à la main de chaque côté, une dérive de format entre les deux modules serait passée inaperçue. Nouveau test bout en bout ajouté. Constat (Blind Hunter) [tests/test_publish.py]

**Reporté (0) :** aucun.

**Rejeté comme bruit (4) :**

- « `main_bandeau_echec` calcule la date du jour indépendamment (`datetime.now()`) plutôt que de recevoir la date exacte de l'échec — un run qui franchirait minuit UTC afficherait la mauvaise nuit » — vrai en théorie, mais structurellement quasi inatteignable avec le déclencheur actuel : le `cron` est fixé à 22h17 UTC et le job est plafonné à 30 minutes (Story 3.1), donc le step d'échec s'exécute au plus tard vers 22h47 UTC — largement avant minuit. Resterait atteignable seulement via un `workflow_dispatch` manuel déclenché très près de minuit suivi d'un quasi-timeout complet — assez rare pour ne pas justifier le passage explicite de l'horodatage du run à travers le contexte GitHub Actions. Documenté comme limite acceptée plutôt que corrigé.
- « L'AC1 (contrainte de conception pour la Story 3.4) n'a aucun mécanisme d'application — rien ne l'imposera si la Story 3.4 l'oublie » — inhérent à poser une contrainte de conception pour une fonctionnalité qui n'existe pas encore (aucun code, donc aucun test possible aujourd'hui) ; la meilleure garantie disponible est la documentation explicite, déjà faite.
- « Risque de compétition (TOCTOU) entre un `workflow_dispatch` de reprise et le step de bandeau d'un run précédent encore en cours » — déjà couvert : le `concurrency: group: pipeline-nocturne` de la Story 3.1 s'applique à l'ensemble du workflow (les deux déclencheurs partagent le même groupe), donc un nouveau run se met en file plutôt que de s'exécuter en parallèle d'un run (bandeau compris) encore actif. Vérifié, pas un trou nouveau.
- « `publier_bandeau_echec` duplique encore le patron complet résolution-client/try-except-finally de `_publier()`, malgré le partage de `_charge_existante` » — réduction de duplication réelle mais partielle acceptée : les deux fonctions ont une forme différente (`_publier` écrit un contenu déjà en main ; `publier_bandeau_echec` doit d'abord lire puis patcher) qui ne se laisse pas réduire à un seul appelant commun sans complexifier `_publier()` pour un seul appelant supplémentaire — jugé disproportionné pour cette story.

## Dev Notes

### Ce qui est déjà vrai aujourd'hui, vérifié en lisant `pipeline.py` avant d'écrire cette story

`pipeline.executer()` (lu en entier, Story 1.8/1.9) enchaîne `collecter()` → `enrichir()` → `marquer_recommandation()` → `rendre()` → `publier()` → `rendre_markdown()` → `publier_archive()`, **dans cet ordre séquentiel strict**, et l'intégralité du corps est enveloppée d'un `try/except Exception` de dernier recours qui ne relance jamais (retourne `False`). Conséquence directe, déjà vraie **sans aucun changement de code** : si `collecter()`, `enrichir()` ou `rendre()` lève, `publier()` n'est **jamais atteint** — la page déjà publiée les nuits précédentes reste donc intacte sur le dépôt de sortie, par construction. L'AC2 de cette story ne demande donc aucun correctif à `pipeline.py`, seulement un test réel qui le démontre — jusqu'ici, cette garantie n'était vérifiée par aucun test, seulement affirmée dans la docstring de `executer()`.

### Pourquoi le bandeau ne peut pas passer par le chemin de rendu normal

`rendre()`/`render.py` produisent la page **à partir d'`Entree`** collectées avec succès cette nuit-là — un run qui échoue avant `rendre()` n'a par définition aucune `Entree` à lui donner (ou lève avant même d'y arriver). Le bandeau doit donc être ajouté **après coup**, sur le HTML déjà publié, par un mécanisme distinct qui ne dépend d'aucune étape du pipeline principal — d'où la fonction dédiée `publier_bandeau_echec`, invoquée par un point d'entrée CLI séparé (`main_bandeau_echec`), lui-même appelé uniquement par le step `if: failure()` du workflow GitHub Actions (Story 3.1). Premier endroit de ce projet où du HTML déjà publié est modifié par édition de texte plutôt que régénéré intégralement par Jinja2 — délibéré et borné (un seul fragment, délimité par des marqueurs stables), pas un précédent pour généraliser cette pratique ailleurs.

### Pourquoi l'idempotence du bandeau (AC4) n'est pas un cas théorique

Un run peut échouer plusieurs nuits de suite (ex. `ANTHROPIC_API_KEY` expirée, source majoritairement en panne). Sans remplacement idempotent, chaque nuit d'échec ajouterait un second bandeau au-dessus du premier — accumulation silencieuse jusqu'à un HTML dégradé. Les marqueurs `<!-- BANDEAU-ECHEC:DEBUT -->`/`FIN` rendent le bloc reconnaissable et remplaçable en une passe, sans dépendre d'un état persistant (`store.py`) : le HTML publié lui-même porte l'information de présence du bandeau.

### Précédents à réutiliser, pas à réinventer

- **`_sha_existant`/`_publier`** (`publish.py`, Story 1.8/1.9) — patron d'upsert déjà en place (`GET` pour le `sha`, puis `PUT`) ; `publier_bandeau_echec` le réutilise pour le `GET` initial (récupérer le contenu existant à patcher) avant de suivre le même chemin de `PUT`.
- **`_url_surs`/échappement** (`render.py`) — la date insérée dans le bandeau passe par le même échappement HTML que le reste du rendu (jamais de contenu utilisateur non fiable dans ce cas précis — la date vient de `datetime.now()`, mais la discipline reste la même par cohérence).
- **Filet de sécurité de dernier recours** (`pipeline.executer()`, Story 1.9) — `main_bandeau_echec()` reprend le même réflexe : ne jamais lever, dégrader proprement, code de sortie non nul seulement en cas d'échec réel de cette étape elle-même.
- **`if: failure()`** (patron standard GitHub Actions, pas un besoin Python) — couvre uniformément un échec applicatif (`main()` sort avec 1) et une panne d'infrastructure du runner (timeout, `uv sync` en échec) sans distinction de code, exactement le besoin de l'AC3.

### Hors périmètre — ne pas anticiper

- **`store.py`/SQLite (AD-5)** — cette story n'en a pas besoin : ni la préservation de la page existante (déjà vraie structurellement), ni le bandeau (patch de texte sur le HTML publié) ne dépendent d'un état persistant. Reste le prérequis de la Story 3.4 (déjà-vu inter-nuits), pas de celle-ci.
- **Retry/reprise automatique dans la même nuit** — l'AC d'`epics.md` parle de « reprise tentée dans la nuit », mais ni cette story ni le workflow de la Story 3.1 n'implémentent de nouvelle tentative automatique après échec (`workflow_dispatch` reste le mécanisme de reprise manuelle, déjà livré en 3.1). Un retry automatique (ex. un second `cron` quelques heures plus tard, ou une action `retry` dans le workflow) serait un ajout distinct, non demandé explicitement par l'AC de cette story telle que reformulée ci-dessus, et risquerait de dupliquer un digest si le premier run avait en fait réussi partiellement — à ne pas ajouter sans y réfléchir dans une story dédiée.
- **Story 3.3/3.4** — sans lien direct avec cette story.

### Testing Standards

- `pytest`, via `uv run pytest`. Le bandeau se teste par assertions de contenu (marqueurs présents, ancien contenu préservé, date correcte) sur du HTML simulé, jamais de vrai réseau — même patron que `test_publish.py` déjà en place (clients HTTP simulés).
- Le test de préservation (Task 1) doit forcer un vrai échec via `monkeypatch` sur chacune des trois fonctions (`collect.collecter`, `enrich.llm.enrichir`, `render.rendre`) plutôt que de supposer le comportement — cohérent avec la discipline du projet (vérifier, pas supposer).

### Previous Story Intelligence

- Story 3.1 : `.github/workflows/pipeline-nocturne.yml` existe déjà, avec un step unique d'exécution du pipeline — cette story y ajoute un second step conditionnel, sans toucher au premier.
- `publish.py`/`render.py` inchangés depuis la Story 1.9 ; leurs patrons d'upsert et d'échappement sont directement réutilisables.

### Git Intelligence Summary

Commits récents : Story 3.1 (implémentation + revue, `5097795`), rapport de projet (commit séparé, `2a5b02a`). Même convention à reproduire ici.

### Project Structure Notes

Aucun écart avec le Structural Seed : `render.py`/`publish.py`/`pipeline.py` sont déjà les fichiers prévus pour porter respectivement le rendu, la publication et l'orchestration.

### References

- [Source: epics.md#Story-3.2] — story d'origine et critères d'acceptation
- [Source: prd.md#FR-11] — génération nocturne, reprise
- [Source: ARCHITECTURE-SPINE.md#AD-11] — « déjà vu » validé seulement après publication réussie
- [Source: 3-1-declencher-automatiquement.md] — workflow GitHub Actions à étendre avec le step `if: failure()`

## Dev Agent Record

### Agent Model Used

### Debug Log References

- `uv run pytest tests/test_render.py tests/test_publish.py tests/test_pipeline.py -q` : 70 passed dès le premier essai pour l'ensemble des tests nouveaux — aucun aller-retour rouge/vert nécessaire au-delà de la RED initiale (imports manquants avant l'implémentation).
- Suite complète finale : `uv run pytest -q` → 366 passed (353 avant + 13 nouveaux).
- `uv run python3 -c "import yaml; yaml.safe_load(...)"` : workflow YAML valide après ajout du step `if: failure()`.

### Completion Notes List

- **AC1** : posé comme contrainte de conception pour la Story 3.4 (aucun état « déjà vu » n'existe encore) — rien à construire ici, documenté explicitement plutôt que silencieusement ignoré.
- **AC2** : confirmé par 3 nouveaux tests réels (`collecter`/`enrichir`/`rendre` forcés à lever) — `publier`/`publier_archive` ne sont jamais appelés dans ces trois cas. Zéro modification de `pipeline.py` : la garantie tenait déjà par construction (ordre séquentiel strict + filet de sécurité de dernier recours), seul le test manquait.
- **AC3** : bandeau honnête livré via un chemin entièrement distinct du pipeline principal — `render.rendre_bandeau_echec` (fragment, thématisé clair/sombre, date `%d/%m/%Y`) + `publish.publier_bandeau_echec` (patch du HTML déjà publié, upsert par `sha`, retour à 3 états) + `pipeline.main_bandeau_echec` (point d'entrée CLI dédié) + un step `if: failure() || cancelled()` dans le workflow de la Story 3.1 — corrigé en revue pour couvrir réellement le cas de timeout que l'AC nomme explicitement.
- **AC4** : idempotence vérifiée par test dédié (`test_bandeau_echec_remplace_plutot_que_d_empiler`) — deux nuits d'échec consécutives remplacent le bandeau existant (marqueurs stables), jamais n'en empilent un second ; renforcé en revue pour tolérer un bandeau contenant un antislash sans lever ni corrompre le HTML.
- **AC5** : confirmé — aucun corps de test existant modifié (une ligne d'import mise à jour dans `test_render.py`, pas un comportement testé).
- **Nouvelle direction de dépendance, documentée** : `publish.py` importe désormais deux constantes de `render.py` (`BANDEAU_ECHEC_DEBUT`/`FIN`) — première fois que `publish.py` dépend de `render.py` (jusqu'ici, `pipeline.py` était seul à appeler les deux, jamais l'un l'autre). Justifié : `publish.py` a besoin des marqueurs pour l'idempotence du remplacement, `render.py` reste le seul à savoir comment les items sont formatés en HTML.
- **`publier_bandeau_echec` renvoie `True`/`False`/`None`** (pas un simple `bool`, correctif de revue) — `None` signifie « rien à annoter, pas une panne » (première nuit jamais publiée), distinct d'une vraie panne (`False`). `main_bandeau_echec` sort avec 0 pour `None`, jamais un faux run rouge.
- **Limite assumée, documentée dans les Dev Notes** : si le step `if: failure() || cancelled()` lui-même échoue à cause d'une panne d'infrastructure catastrophique (ex. `actions/checkout` échoue, aucun code disponible), le bandeau ne peut pas non plus être publié — résidu non couvert par cette story, jugé disproportionné à corriger. De même, `main_bandeau_echec` calcule la date du jour indépendamment plutôt que de recevoir l'horodatage exact du run échoué — structurellement quasi inatteignable avec le `cron` fixé à 22h17 UTC et un plafond de 30 min (voir Review Findings).
- Convention de commit reproduite (Stories 1.4-3.1) : commit implémentation+revue, puis commit séparé pour `docs/rapport-projet.md`, tous deux poussés sur `origin/main`.

### File List

- `src/veille/render.py` — modifié : `rendre_bandeau_echec` (date `%d/%m/%Y`, couleurs via variables CSS), `BANDEAU_ECHEC_DEBUT`/`BANDEAU_ECHEC_FIN`.
- `src/veille/publish.py` — modifié : `publier_bandeau_echec` (retour à 3 états), `_inserer_bandeau` (idempotent, regex tolérante aux attributs de `<body>`, remplacement sûr contre les antislashs), `_charge_existante` (GET partagé, réutilisé aussi par `_sha_existant`), import des marqueurs depuis `render.py`.
- `src/veille/pipeline.py` — modifié : `main_bandeau_echec` (gère le retour à 3 états), dispatch `--bandeau-echec` dans `if __name__ == "__main__"`.
- `.github/workflows/pipeline-nocturne.yml` — modifié : nouveau step `if: failure() || cancelled()`.
- `templates/digest.html.j2` — modifié : variables CSS `--bandeau-echec-bg`/`--bandeau-echec-fg` (clair + sombre).
- `tests/test_render.py` — modifié : 2 nouveaux tests + import mis à jour.
- `tests/test_publish.py` — modifié : 11 nouveaux tests (5 initiaux + 6 en revue).
- `tests/test_pipeline.py` — modifié : 7 nouveaux tests (3 Task 1 + 4 Task 3, dont 1 ajouté en revue).
- `_bmad-output/implementation-artifacts/3-2-reprendre-apres-echec.md` — ce fichier (story).

### Change Log

| Date | Changement |
|---|---|
| 2026-09-14 | Story créée et implémentée en une passe (Tasks 1-4) : préservation de la page existante verrouillée par test, bandeau d'échec livré (render + publish + pipeline + workflow), aucune régression. Statut → review. |
| 2026-09-14 | Revue (3 couches, Sonnet) : 10 correctifs appliqués (`if: failure()` → `failure() || cancelled()` pour couvrir le timeout — convergence 3/3 — remplacement `re.sub` sûr contre les antislashs, retour à 3 états pour distinguer « rien à annoter » d'une vraie panne, garde `sha` alignée sur `_publier()`, regex tolérante aux attributs de `<body>`, test du repli sans `<body>`, détection du contenu illisible, `_charge_existante` partagé (corrige une affirmation de réutilisation fausse dans les Dev Notes), thème/format de date alignés sur le reste du site, test bout en bout render+publish), 0 report, 4 rejetés comme bruit. 373 passed. Statut → done. |
