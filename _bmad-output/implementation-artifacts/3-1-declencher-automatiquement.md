---
baseline_commit: 2c25018
---

# Story 3.1: Déclencher le pipeline automatiquement chaque nuit

Status: done

## Story

As a Abdoulaye,
I want ne plus avoir à lancer quoi que ce soit,
so that le digest est prêt avant que je sorte le matin.

## Acceptance Criteria

1. **[FR-11, amendement d'architecture]** Le pipeline se déclenche seul chaque soir vers 22h heure de Dakar (UTC+0, pas de changement d'heure) — via **GitHub Actions** (`cron`), pas le Planificateur de tâches Windows prévu à l'origine par le PRD/l'architecture : le projet a migré sur Mac depuis (`rapport-projet.md` §9), et la contrainte « PC allumé la nuit » que le PRD lui-même identifiait comme fragile (`[NOTE FOR PM]`) est réelle sur un ordinateur portable personnel. La bascule vers GitHub Actions était déjà documentée comme repli explicite dans `ARCHITECTURE-SPINE.md` (« si le PC allumé la nuit devient une contrainte ») — confirmée par Abdoulaye pour cette story.
2. **[FR-11]** **La page publiée est à jour avant 7h38 le lendemain matin** (critère explicite d'`epics.md#Story-3.1`) — non testable en conditions réelles tant que les prérequis de l'AC3 ne sont pas résolus, mais raisonné explicitement : le pipeline réel (Story 2.4) collecte+traite en moins de 2 minutes ; même avec le retard de déclenchement documenté par GitHub pour les `schedule` au sommet de l'heure (quelques minutes, rarement plus), la marge entre 22h17 et 7h38 (~9h20) l'absorbe très largement. Risque résiduel non contournable par la configuration : GitHub désactive silencieusement un déclencheur `schedule` après 60 jours sans activité de commit sur le dépôt — voir Dev Notes et `deferred-work.md`.
3. **[FR-11]** Le workflow exécute `uv run python -m veille.pipeline` dans un environnement propre (checkout + `uv sync --locked`), avec `ANTHROPIC_API_KEY` et un jeton GitHub à droits d'écriture sur le **dépôt de sortie** (`petitlaye03/agent-veille-tech-digest`) fournis en secrets du dépôt — jamais en dur dans le workflow.
4. **[Sûreté]** Le workflow peut aussi être déclenché manuellement (`workflow_dispatch`) — indispensable pour valider/déboguer sans attendre 22h, et pour un rattrapage ponctuel. Un `concurrency` group empêche qu'un déclenchement manuel chevauche le run programmé (upsert par `sha` sur le dépôt de sortie, non réentrant en parallèle).
5. **[Observabilité]** Un run en échec (code de sortie non nul de `main()`, déjà en place depuis la Story 1.8) est visible comme tel dans l'onglet Actions de GitHub — pas de mécanisme applicatif supplémentaire nécessaire. **Limite assumée** : un run qui *réussit* mais dégrade silencieusement (ex. `ANTHROPIC_API_KEY` absente → accroches en repli, `exit 0`) reste invisible dans l'onglet Actions — problème d'observabilité applicative, pas de déclenchement ; hors périmètre de cette story (déjà une dette connue, `rapport-projet.md` §8, liée à AD-5/Epic 3).
6. Aucune modification du pipeline lui-même (`collect.py`/`enrich/llm.py`/`render.py`/`publish.py`/`pipeline.py`) — cette story ajoute un déclencheur externe, elle ne change aucun comportement interne. Garde-fous existants inchangés.

## Tasks / Subtasks

- [x] Task 1 : Écrire le workflow GitHub Actions (AC: 1, 2, 3, 4)
  - [x] `.github/workflows/pipeline-nocturne.yml` : déclencheurs `schedule` (`cron: '17 22 * * *'` — 22h17 UTC = 22h17 Dakar ; décalé du sommet de l'heure en revue, voir Review Findings) et `workflow_dispatch`, `concurrency` group (ajouté en revue)
  - [x] Job unique : `actions/checkout`/`astral-sh/setup-uv` épinglés par SHA de commit réel (correctif de revue, tags flottants initialement), `uv sync --locked` (`--frozen` initialement, corrigé en revue), puis `uv run python -m veille.pipeline` ; `permissions: contents: read` et `timeout-minutes: 30` ajoutés en revue
  - [x] `ANTHROPIC_API_KEY`/`GITHUB_TOKEN` injectés en variables d'environnement du step d'exécution, depuis `secrets.ANTHROPIC_API_KEY`/`secrets.DIGEST_PUBLISH_TOKEN` (nom distinct de `GITHUB_TOKEN`, réservé par Actions et scopé au dépôt courant — insuffisant pour écrire sur le dépôt de sortie, voir Dev Notes) — mappé sur la variable d'environnement `GITHUB_TOKEN` attendue par `publish.py`, sans modifier ce fichier
  - [x] Version Python : `.python-version` (3.11) à la racine du dépôt suffit, déjà lu automatiquement par `uv` — l'input `python-version` explicite de `setup-uv` retiré en revue (doublon)

- [x] Task 2 : Documenter le prérequis réel (secrets du dépôt) sans les créer soi-même (AC: 3)
  - [x] `.env.example` non modifié — décision délibérée : `DIGEST_PUBLISH_TOKEN` est un secret de dépôt GitHub Actions (`Settings → Secrets and variables → Actions`), pas une variable `.env` locale ; l'ajouter à `.env.example` aurait suggéré à tort qu'il se configure en local. Le commentaire existant sur `GITHUB_TOKEN` (« futur repli GitHub Actions ») couvrait déjà ce cas.
  - [x] Documenté en tête du workflow lui-même et dans les Dev Notes/Completion Notes : ce workflow ne peut pas tourner avec succès tant que (a) `ANTHROPIC_API_KEY` et `DIGEST_PUBLISH_TOKEN` ne sont pas ajoutés comme secrets du dépôt `Agent_Veille_Tech` (action réelle, sous le compte d'Abdoulaye, non faite par l'agent), et (b) le dépôt de sortie public lui-même n'existe pas encore. Risque de désactivation silencieuse à 60 jours d'inactivité ajouté en revue (`deferred-work.md`).

- [x] Task 3 : Vérifier que rien d'autre n'a besoin de changer (AC: 5, 6)
  - [x] Confirmé : `main()` (`pipeline.py:115`, `sys.exit(0 if reussite else 1)`) sort déjà avec un code non nul sur échec (Story 1.8) — GitHub Actions marque nativement un step en échec sur un code de sortie non nul.
  - [x] Confirmé : `RACINE_PROJET`/résolution de chemins de config (`config.py`) résolue depuis l'emplacement du module, pas le `cwd` — compatible avec le répertoire de travail d'un runner GitHub Actions après `checkout`.
  - [x] Suite complète (`uv run pytest`) rejouée : 353 passed, aucune régression — aucune ligne de `src/veille/` ou `tests/` modifiée, seul le workflow a été ajouté.

### Review Findings

> Revue de code du 2026-09-14 (skill `bmad-code-review`, 3 couches adversariales, sur
> Sonnet 5 — même modèle que l'implémentation, convention établie). Base de diff
> `2c25018` (= `baseline_commit`, changements non commités). Revue substantielle malgré
> un diff réduit à un seul fichier YAML : les 3 couches ont indépendamment identifié le
> même trio de manques de durcissement CI (`concurrency`, `timeout-minutes`, désactivation
> silencieuse à 60 jours d'inactivité), et l'Acceptance Auditor a trouvé un vrai critère
> d'acceptation de la story source (`epics.md`) disparu de la liste finale de cette story.

**Correctifs appliqués (8) :**

- [x] [Review][Patch] Le critère « page publiée à jour avant 7h38 » (`epics.md#Story-3.1`, cité dans les References de cette story) avait disparu de la liste d'AC finale, sans mention ni descope explicite. Réintégré comme AC2, avec le raisonnement de marge (22h17 → 7h38, ~9h20, très large face au retard documenté de GitHub sur les `schedule` à l'heure ronde) — non vérifiable en conditions réelles tant que les prérequis de l'AC3 ne sont pas résolus, mais explicitement raisonné plutôt que silencieusement omis. Constat (Acceptance Auditor) [story, AC]
- [x] [Review][Patch] Aucun `concurrency` group — un `workflow_dispatch` manuel (ajouté précisément pour « valider/déboguer sans attendre ») pouvait chevaucher un run programmé, les deux écrivant en parallèle sur le même upsert par `sha` du dépôt de sortie. Corrigé (`group: pipeline-nocturne`). Constat convergent (Blind Hunter + Edge Case Hunter) [.github/workflows/pipeline-nocturne.yml]
- [x] [Review][Patch] Aucun `timeout-minutes` — un run bloqué (réseau, source qui ne répond jamais) pouvait occuper le plafond par défaut de GitHub Actions (plusieurs heures), le risque même que `rapport-projet.md` §8 documente déjà pour ce pipeline (« budget de temps global »). Corrigé (30 minutes). Constat convergent (Blind Hunter + Edge Case Hunter) [.github/workflows/pipeline-nocturne.yml]
- [x] [Review][Patch] `uv sync --frozen` installe le verrou tel quel sans vérifier sa cohérence avec `pyproject.toml` ; `--locked` (documenté par `uv` comme le choix CI) échoue explicitement en cas de dérive plutôt que d'installer silencieusement un verrou périmé. Corrigé et vérifié (`uv sync --locked` passe localement, le verrou est à jour). Constat (Blind Hunter) [.github/workflows/pipeline-nocturne.yml]
- [x] [Review][Patch] `actions/checkout@v4`/`astral-sh/setup-uv@v4` référencés par tag flottant plutôt que par SHA de commit — ce job manipule un jeton à droits d'écriture sur un second dépôt (`DIGEST_PUBLISH_TOKEN`) ; un tag mutable re-pointé exécuterait avec ce jeton sans qu'aucun changement n'apparaisse dans ce fichier. Épinglés aux SHA réels du tag `v4` de chaque action (vérifiés par `git ls-remote --tags` au moment de la revue, pas inventés). Constat (Blind Hunter) [.github/workflows/pipeline-nocturne.yml]
- [x] [Review][Patch] Aucun bloc `permissions:` — le job tournait avec les permissions par défaut du dépôt plutôt qu'un octroi explicite minimal. Ajouté `contents: read` (ce job ne modifie jamais le dépôt courant, seulement le dépôt de sortie via le jeton dédié). Constat (Blind Hunter) [.github/workflows/pipeline-nocturne.yml]
- [x] [Review][Patch] Le `cron` au sommet exact de l'heure (`0 22 * * *`) tombait dans la fenêtre que GitHub documente comme la plus chargée pour les déclencheurs `schedule`, donc la plus sujette au retard. Décalé à `17 22 * * *` — la marge jusqu'à 7h38 (~9h20) absorbe largement ce risque documenté, mais autant ne pas le provoquer inutilement. Constat (Blind Hunter) [.github/workflows/pipeline-nocturne.yml]
- [x] [Review][Patch] `setup-uv` recevait un `python-version: "3.11"` explicite, doublon de `.python-version` à la racine du dépôt (déjà lu automatiquement par `uv`, déjà cohérent avec `pyproject.toml`) — deuxième source de vérité à resynchroniser manuellement pour rien. Retiré. Constat (Blind Hunter) [.github/workflows/pipeline-nocturne.yml]

**Reporté (1) :**

- [x] [Review][Defer] GitHub désactive silencieusement un déclencheur `schedule` après 60 jours sans activité de commit sur le dépôt — aucun contournement propre par la configuration de ce fichier seul (une « fausse » activité périodique serait un artifice plus fragile que le problème qu'il résout). Documenté en tête du workflow, dans l'AC2 et dans `deferred-work.md` — à surveiller si le dépôt reste inactif longtemps une fois les stories en cours terminées. Constat convergent (Blind Hunter + Edge Case Hunter + Acceptance Auditor) [.github/workflows/pipeline-nocturne.yml, deferred-work.md]

**Rejeté comme bruit (3) :**

- « Réutiliser le nom `GITHUB_TOKEN` pour le PAT personnalisé est un piège pour un futur step qui s'attendrait au jeton ambiant » — le mapping est déjà scopé au seul step qui en a besoin (pas le job entier) : un futur step n'hérite de rien tant qu'il ne redéclare pas explicitement ce nom. Commentaire renforcé dans le fichier plutôt que restructuré.
- « Aucun problème de tracking (issue GitHub) pour les 3 prérequis externes non résolus » — déjà documenté à 3 endroits (en-tête du workflow, Dev Notes, Completion Notes) ; créer une issue GitHub serait une action réelle et sortante sous le compte d'Abdoulaye, hors périmètre de cette story sans confirmation explicite.
- « FR-11 mentionne aussi une reprise automatique dans la nuit, absente de cette story » — déjà explicitement la Story 3.2 dans `epics.md`, pas un oubli de celle-ci.

## Dev Notes

### Amendement d'architecture : GitHub Actions plutôt que le Planificateur Windows

`ARCHITECTURE-SPINE.md` (§ordonnancement) et `prd.md` (§FR-11) prévoyaient le Planificateur de tâches Windows sur le PC d'Abdoulaye, avec un repli explicitement documenté vers GitHub Actions « si le PC allumé la nuit devient une contrainte ». Le PC de développement a migré vers Mac le 2026-08-27 (`rapport-projet.md` §9) — le Planificateur Windows n'a donc plus de sens tel quel, et l'équivalent macOS (`launchd`/`cron`) souffrirait de la même fragilité que le PRD anticipait déjà pour Windows (« dépendance au PC allumé la nuit »), aggravée par le fait qu'il s'agit désormais d'un ordinateur portable personnel plutôt que potentiellement une machine dédiée. Confirmé explicitement par Abdoulaye (2026-09-14) : GitHub Actions, le repli déjà prévu par l'architecture elle-même — aucun nouvel AD à écrire, seulement le déclencheur (`sched` dans le diagramme de l'architecture) change, exactement comme l'architecture l'avait anticipé.

### Le jeton `GITHUB_TOKEN` par défaut de GitHub Actions ne suffit pas

GitHub Actions fournit automatiquement un `secrets.GITHUB_TOKEN` à chaque run, mais **scopé au dépôt courant** (`Agent_Veille_Tech`, privé). `publish.py` cible un **second dépôt** (`petitlaye03/agent-veille-tech-digest`, public, dédié à la sortie) — ce jeton par défaut n'a aucun droit d'écriture dessus. Il faut donc un jeton d'accès personnel (PAT), avec droit d'écriture sur ce second dépôt, stocké comme secret **distinct** (nom proposé : `DIGEST_PUBLISH_TOKEN` — `GITHUB_TOKEN` est un nom réservé par Actions, non redéfinissable comme secret custom) puis mappé sur la variable d'environnement `GITHUB_TOKEN` au moment d'exécuter le pipeline, pour que `publish._jeton()` (inchangé) le trouve exactement comme en local. Ce point était déjà anticipé dans `.env.example` (Story 1.8 : « à renseigner seulement si le run doit un jour se faire sans elle (ex. futur repli GitHub Actions) ») — cette story confirme enfin ce « futur ».

### Ce que cette story NE valide PAS en conditions réelles, et pourquoi

Ce workflow ne peut pas être validé par une exécution réelle réussie tant que deux prérequis externes, tous deux déjà différés depuis l'Epic 1, ne sont pas résolus :
- **`ANTHROPIC_API_KEY`** — jamais fournie à ce jour (Story 1.6). Sans elle, `enrich/llm.py` dégrade proprement (titre en repli, pas de plantage — comportement déjà éprouvé), donc le workflow *pourrait* techniquement tourner sans lever, mais produirait des accroches dégradées.
- **Le dépôt de sortie public** (`petitlaye03/agent-veille-tech-digest`) — n'existe toujours pas (Story 1.8/1.9). Sans lui (et sans `DIGEST_PUBLISH_TOKEN`), `publish.py` dégrade proprement (`False`, pas de plantage), donc le workflow tournerait mais ne publierait rien.

Cette story livre donc un déclencheur **correct et testable manuellement** (`workflow_dispatch`), mais la première exécution programmée réellement utile suppose ces deux actions réelles, hors périmètre de cette story (à confirmer explicitement avec Abdoulaye avant de les faire, comme chaque fois qu'une action réelle et irréversible sous son compte est en jeu).

### Précédents à réutiliser, pas à réinventer

- **Code de sortie de `main()`** (`pipeline.py`, Story 1.8) — déjà non nul sur échec, exactement ce dont GitHub Actions a besoin pour marquer un run en échec ; aucun changement de code.
- **Résolution de chemins indépendante du `cwd`** (`config.py`, `RACINE_PROJET`, Story 1.1/1.2) — déjà compatible avec n'importe quel répertoire de travail, y compris celui d'un runner GitHub Actions après `checkout`.
- **`load_dotenv()` sans effet si aucun `.env` n'existe** (`enrich/llm.py`, `publish.py`) — les secrets GitHub Actions sont injectés directement dans l'environnement du process (`env:` du step), donc `os.environ.get(...)` les trouve normalement, sans qu'un fichier `.env` littéral existe sur le runner.
- **Convention de secrets déjà anticipée** (`.env.example`, Story 1.8) — le commentaire sur `GITHUB_TOKEN` mentionnait déjà « futur repli GitHub Actions » avant que cette story n'existe.

### Hors périmètre — ne pas anticiper

- **Créer le dépôt de sortie ou ajouter les secrets réels** — actions réelles sous le compte d'Abdoulaye, à confirmer explicitement avant exécution, pas à faire silencieusement dans cette story.
- **Story 3.2 (reprise après échec)/3.3 (idempotence par relance)/3.4 (déjà-vu persistant)** — cette story ne fait que déclencher le pipeline existant ; aucune logique de reprise, d'upsert renforcé ou d'état persistant n'est ajoutée ici.
- **Notification (email/Slack) en cas d'échec** — non demandé par l'AC ; GitHub envoie déjà un e-mail natif sur l'échec d'un workflow programmé aux paramètres par défaut du compte, suffisant pour cette story.
- **Optimisation du temps de run GitHub Actions** (cache `uv`, etc.) — prématuré tant que le workflow n'a jamais tourné en conditions réelles.

### Testing Standards

- `pytest`, via `uv run pytest` — cette story n'ajoute aucun test Python : le fichier produit est un YAML de workflow, pas du code applicatif. La validation se fait par relecture (syntaxe, secrets référencés par leur nom, pas de valeur en dur) et, une fois les prérequis réels résolus, par un déclenchement manuel (`workflow_dispatch`) réellement observé dans l'onglet Actions de GitHub — hors périmètre de cette story tant que les secrets n'existent pas.
- Suite `pytest` existante rejouée pour confirmer l'absence de régression (aucune modification de `src/veille/` attendue).

### Previous Story Intelligence

- Story 2.4 (dernière de l'Epic 2) : convention de commit (implémentation+revue, puis rapport séparé), `git add -A` pour couvrir `_bmad-output/`.
- `publish.py`/`enrich/llm.py` déjà conçus depuis l'Epic 1 pour dégrader proprement sans clé/jeton — aucune surprise attendue si les secrets manquent encore au premier run programmé.

### Git Intelligence Summary

Commits récents : Story 2.4 (implémentation + revue, `9310e86`), rapport de projet (commit séparé, `2c25018`). Même convention à reproduire ici.

### Project Structure Notes

Écart mineur mais réel au Structural Seed : premier fichier hors `src/`/`tests/`/`config/`/`templates/`/`_bmad-output/`/`docs/` de ce projet — `.github/workflows/`, dossier standard GitHub, pas une déviation d'architecture.

### References

- [Source: epics.md#Story-3.1] — story d'origine et critères d'acceptation
- [Source: ARCHITECTURE-SPINE.md#Ordonnancement] — Planificateur Windows + repli GitHub Actions déjà documenté
- [Source: prd.md#FR-11] — génération nocturne, dépendance au PC allumé déjà identifiée comme risque
- [Source: rapport-projet.md §9] — migration Windows → Mac (2026-08-27)
- Décision utilisateur (2026-09-14, `AskUserQuestion`) : GitHub Actions confirmé comme mécanisme de déclenchement pour Epic 3

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5 (`claude-sonnet-5`)

### Debug Log References

- `uv run python3 -c "import yaml; yaml.safe_load(...)"` : YAML valide (le `on:` bare est interprété comme la clé booléenne `True` par PyYAML — artefact connu de YAML 1.1, sans effet sur le parseur réel de GitHub Actions, qui traite `on` comme une clé spéciale ; convention standard de tout workflow GitHub Actions).
- `uv run pytest -q` : 353 passed, identique à avant cette story (aucun code Python touché).

### Completion Notes List

- **AC1** : workflow GitHub Actions (`cron: '17 22 * * *'`, UTC = heure de Dakar toute l'année) remplace le Planificateur Windows prévu à l'origine — amendement confirmé explicitement par Abdoulaye (`AskUserQuestion`, 2026-09-14), cohérent avec le repli déjà documenté dans `ARCHITECTURE-SPINE.md`.
- **AC2** : critère « avant 7h38 » raisonné explicitement (marge ~9h20, très large face au pipeline réel mesuré en Story 2.4 et au retard documenté par GitHub sur les `schedule` — correctif de revue, ce critère avait été omis de la première rédaction).
- **AC3** : `ANTHROPIC_API_KEY` et un jeton distinct (`DIGEST_PUBLISH_TOKEN`, à créer par Abdoulaye) injectés en secrets, jamais en dur. Le `secrets.GITHUB_TOKEN` natif d'Actions ne suffit pas : scopé au dépôt courant, pas au dépôt de sortie que `publish.py` cible — point non trivial, documenté en tête du workflow pour ne pas être redécouvert plus tard. `uv sync --locked` (pas `--frozen`, correctif de revue) pour échouer explicitement sur toute dérive du verrou.
- **AC4** : `workflow_dispatch: {}` ajouté — permet un déclenchement manuel pour valider sans attendre 22h. `concurrency` group ajouté en revue pour qu'un tel déclenchement manuel ne chevauche jamais le run programmé.
- **AC5** : aucun code applicatif ajouté — le code de sortie non nul de `main()` (déjà en place depuis la Story 1.8) suffit à ce que GitHub Actions marque nativement le run en échec. Limite du « succès dégradé » (clé absente → digest dégradé mais `exit 0`) documentée explicitement comme hors périmètre, pas silencieusement ignorée.
- **AC6** : confirmé — zéro ligne de `src/veille/`/`tests/` modifiée, `git diff --stat` ne montre que le fichier de workflow et la story.
- **Durcissement CI ajouté en revue, au-delà des AC initiales** : `permissions: contents: read` (moindre privilège), `timeout-minutes: 30` (filet contre un run bloqué), actions épinglées par SHA de commit réel (pas un tag flottant — jeton à droits d'écriture cross-repo en jeu), suppression d'un doublon de version Python déjà couvert par `.python-version`.
- **Limite assumée, documentée en tête du workflow et dans les Dev Notes** : ce workflow ne peut pas être validé par une exécution programmée réellement réussie tant que (a) les deux secrets ne sont pas ajoutés au dépôt (action réelle sous le compte d'Abdoulaye, non faite ici) et (b) le dépôt de sortie public n'existe pas encore (différé depuis la Story 1.8). `enrich/llm.py`/`publish.py` dégradent tous deux proprement en leur absence (déjà éprouvé), donc le workflow ne plante pas — il ne publie simplement rien d'utile tant que ces deux actions réelles ne sont pas faites. Risque supplémentaire trouvé en revue et documenté (pas corrigé, non contournable par la configuration seule) : désactivation silencieuse du `schedule` après 60 jours d'inactivité du dépôt.
- Convention de commit reproduite (Stories 1.4-2.4) : commit implémentation+revue, puis commit séparé pour `docs/rapport-projet.md`, tous deux poussés sur `origin/main`.

### File List

- `.github/workflows/pipeline-nocturne.yml` — nouveau : déclencheur nocturne (`cron`) + manuel (`workflow_dispatch`), `concurrency`/`permissions`/`timeout-minutes`, actions épinglées par SHA, exécute `uv run python -m veille.pipeline` avec les secrets du dépôt.
- `_bmad-output/implementation-artifacts/deferred-work.md` — modifié : nouvelle entrée (désactivation silencieuse du `schedule` GitHub Actions après 60 jours d'inactivité).
- `_bmad-output/implementation-artifacts/3-1-declencher-automatiquement.md` — ce fichier (story).

### Change Log

| Date | Changement |
|---|---|
| 2026-09-14 | Amendement d'architecture confirmé (GitHub Actions plutôt que Planificateur Windows, `AskUserQuestion`). Story créée et implémentée en une passe (Tasks 1-3) : workflow écrit, prérequis documentés, aucune régression. Statut → review. |
| 2026-09-14 | Revue (3 couches, Sonnet) : 8 correctifs appliqués (AC 7h38 réintégrée, `concurrency`, `timeout-minutes`, `uv sync --locked`, actions épinglées par SHA vérifié, `permissions` minimales, cron décalé du sommet de l'heure, doublon de version Python retiré), 1 report (désactivation à 60 jours, documenté), 3 rejetés comme bruit. 353 passed (inchangé, aucun code Python touché). Statut → done. |
