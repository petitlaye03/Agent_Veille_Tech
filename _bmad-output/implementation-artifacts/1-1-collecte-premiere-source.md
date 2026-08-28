---
baseline_commit: NO_COMMITS_YET
---

# Story 1.1: Brancher une première source et voir ses items collectés

Status: done

## Story

As a Abdoulaye,
I want connecter une première source RSS et récupérer ses items,
so that je vérifie que le pipeline de collecte fonctionne de bout en bout sur un cas réel.

## Acceptance Criteria

1. Étant donné un fichier `config/sources.yaml` contenant une source RSS valide (le flux OpenAI news, `https://openai.com/news/rss.xml`), exécuter le script de collecte produit une liste d'objets `Item` respectant le format canonique.
2. Chaque `Item` produit porte au minimum les champs : `source_id`, `guid`, `titre`, `date_publication` (datetime UTC, timezone-aware), `langue`, `registre`, `url`, `contenu_brut`.
3. Chaque `Item` est traçable jusqu'à sa Source d'origine via `source_id`, qui correspond à une clé déclarée dans `sources.yaml`.
4. Relancer le script de collecte immédiatement après une première exécution ne lève aucune exception et produit un résultat cohérent.

## Tasks / Subtasks

- [x] Task 1 : Initialiser le projet Python selon la Structural Seed (AC: 1,2,3,4)
  - [x] Exécuter `uv init --package` à la racine pour créer le layout `src/veille/` avec `pyproject.toml` (le nom du package doit être `veille`)
  - [x] Ajouter les dépendances runtime : `uv add feedparser pyyaml`
  - [x] Ajouter `pytest` comme dépendance de développement : `uv add --dev pytest` (voir Dev Notes — absent de la Stack de la spine, ajouté ici comme outillage de test standard)
  - [x] Créer les dossiers vides prévus par la Structural Seed non encore utilisés : `config/`, `templates/`, `site/archive/` (avec un `.gitkeep` si nécessaire)

- [x] Task 2 : Définir le modèle `Item` canonique (AC: 1,2)
  - [x] Créer `src/veille/models.py` avec une dataclass (ou NamedTuple) `Item` portant exactement les champs invariants d'AD-4 : `source_id: str`, `guid: str`, `titre: str`, `date_publication: datetime`, `langue: str`, `registre: str`, `url: str`, `contenu_brut: str`
  - [x] Écrire un test unitaire (`tests/test_models.py`) vérifiant la construction d'un `Item` et le typage de `date_publication` (doit être `datetime` timezone-aware en UTC)

- [x] Task 3 : Charger la configuration des sources (AC: 3)
  - [x] Créer `config/sources.yaml` avec une entrée pour la source OpenAI news (voir schéma en Dev Notes)
  - [x] Créer `src/veille/config.py` avec une fonction `load_sources(path) -> list[SourceConfig]` qui lit `sources.yaml` et retourne des descripteurs de sources typés (id, type, url, langue, registre)
  - [x] Écrire un test unitaire (`tests/test_config.py`) : un `sources.yaml` valide produit la liste attendue de sources ; chaque source expose un `id` non vide

- [x] Task 4 : Implémenter le connecteur RSS (AC: 1,2,3,4)
  - [x] Créer `src/veille/connectors/rss_connector.py` avec une fonction `fetch(source_config) -> list[Item]` respectant le contrat d'AD-2
  - [x] Utiliser `feedparser.parse(url)` pour récupérer et parser le flux ; mapper chaque entrée vers un `Item` canonique (voir mapping détaillé en Dev Notes)
  - [x] Vérifier `feed.bozo` après le parsing : si `True` (flux malformé), journaliser un avertissement et retourner une liste vide plutôt que de lever une exception non gérée
  - [x] Calculer `guid` selon la convention de la spine : identifiant natif du flux (`entry.id`/`<guid>`) si présent, sinon URL canonique de l'entrée, sinon hash SHA-256 de `(source_id + titre)` — décision confirmée en revue de code du 2026-07-28 (voir Review Findings)
  - [x] Créer une fixture de test `tests/fixtures/sample_feed.xml` (flux RSS minimal, 2-3 entrées, hors réseau) et écrire `tests/test_rss_connector.py` vérifiant que `fetch()` sur cette fixture produit des `Item` conformes au format canonique

- [x] Task 5 : Assembler le script de collecte de bout en bout (AC: 1,2,3,4)
  - [x] Créer `src/veille/collect.py` avec une fonction `run() -> list[Item]` qui : charge `sources.yaml` via `config.load_sources`, itère sur les sources, appelle le connecteur correspondant au `type` de chaque source (pour cette story, seul `type: rss` existe), consolide et retourne la liste d'`Item`
  - [x] Structurer la boucle sur les sources pour qu'elle reste correcte avec plusieurs sources plus tard, même si `sources.yaml` n'en contient qu'une seule aujourd'hui — ne pas coder en dur un appel unique au connecteur RSS
  - [x] Exposer un point d'entrée exécutable (`uv run python -m veille.collect` ou équivalent) qui appelle `run()` et journalise le nombre d'`Item` récupérés
  - [x] Écrire un test d'intégration (`tests/test_collect.py`) qui exécute `run()` deux fois de suite sur la fixture locale et vérifie qu'aucune exception n'est levée la seconde fois (AC 4)

- [x] Task 6 : Valider les critères d'acceptation (AC: 1,2,3,4)
  - [x] Exécuter la suite de tests complète (`uv run pytest`) et confirmer 100 % de réussite
  - [x] Exécuter manuellement `collect.run()` contre le flux OpenAI news réel (`https://openai.com/news/rss.xml`) pour valider AC 1 en conditions réelles ; consigner le résultat (nombre d'items, exemple d'un `Item`) dans Dev Agent Record → Completion Notes

## Dev Notes

**Portée volontairement limitée.** Cette story ne construit ni le store SQLite (AD-5), ni le dédoublonnage (Story 1.3), ni l'isolation de panne multi-sources complète avec backoff (Epic 2). Une seule source, en mémoire, sans persistance entre exécutions : c'est le principe « créer uniquement ce dont la story a besoin ». Le store SQLite arrivera quand une story en aura réellement besoin (dédoublonnage cross-nuit en Story 3.4, santé des sources en Epic 4) — ne pas l'anticiper ici.

**`pytest` n'est pas dans la table Stack de la spine** (qui ne couvre pas l'outillage de test). Il est ajouté ici comme dépendance de développement standard pour un projet Python — à signaler si ce choix est contesté.

### Contrat du connecteur (AD-2)

Tout connecteur doit exposer `fetch(source_config) -> list[Item]`. Pour cette story, seul le type `rss` existe, mais la fonction `collect.run()` doit dispatcher par `type` de source (même si un seul type est branché) pour que l'ajout d'un connecteur API/scraping en Story 1.2 n'oblige pas à réécrire `collect.py`.

### Mapping flux RSS → `Item` canonique

Avec `feedparser`, pour chaque `entry` de `feed.entries` :

| Champ `Item` | Source dans `entry` (feedparser) |
| --- | --- |
| `source_id` | `source_config.id` (déclaré dans `sources.yaml`, pas dans le flux) |
| `guid` | `entry.id` en priorité (identifiant natif, permanent), sinon `entry.link`, sinon SHA-256(`source_id` + `titre`) — cf. Consistency Conventions de la spine (corrigée le 2026-07-28) |
| `titre` | `entry.title` |
| `date_publication` | `entry.published_parsed` (struct_time) converti en `datetime` UTC timezone-aware |
| `langue` | `source_config.langue` (déclarée en config — feedparser n'infère pas fiablement la langue) |
| `registre` | `source_config.registre` (déclarée en config) |
| `url` | `entry.link` |
| `contenu_brut` | `entry.summary` (ou `entry.description` selon le flux) |

### Schéma `config/sources.yaml` pour cette story

```yaml
sources:
  - id: openai-news
    type: rss
    url: https://openai.com/news/rss.xml
    langue: en
    registre: ce_qui_bouge
```

Le format complet de `sources.yaml` (tous les champs possibles) est un Deferred de la spine — ce schéma minimal suffit à cette story et doit rester extensible (Story 1.2 y ajoutera des sources de types différents).

### Convention `registre`

Les trois sections du PRD (§3 Glossaire) sont *Apprendre*, *Ce qui bouge*, *Pour le métier*. En code (snake_case, cf. Consistency Conventions), utiliser les slugs `apprendre`, `ce_qui_bouge`, `pour_le_metier`. La source OpenAI news relève de `ce_qui_bouge` (actualité de laboratoire, cf. PRD §6.1). La traduction en libellés accentués pour l'affichage n'intervient qu'au rendu (Story 1.8), hors périmètre ici.

### Project Structure Notes

Conforme à la Structural Seed de la spine :

```text
veille-ia/
  pyproject.toml
  config/
    sources.yaml
  src/veille/
    models.py
    config.py
    collect.py
    connectors/
      rss_connector.py
  tests/
    fixtures/
      sample_feed.xml
    test_models.py
    test_config.py
    test_rss_connector.py
    test_collect.py
```

Pas de conflit détecté avec la Structural Seed : cette story pose les premiers fichiers réels dans une arborescence encore vide (aucun code existant à ce jour dans le dépôt).

### Testing Standards

- `pytest`, exécuté via `uv run pytest`.
- Le test du connecteur RSS utilise une fixture locale (`tests/fixtures/sample_feed.xml`) — **aucun appel réseau dans les tests automatisés**. La validation contre le flux réel OpenAI (AC 1 en conditions réelles) est une vérification manuelle documentée dans Completion Notes, pas un test automatisé.
- Couvrir explicitement le cas `feed.bozo = True` (flux malformé) dans les tests du connecteur.

### Latest Tech Information

`uv init --package` est la commande actuelle (vérifiée juillet 2026) pour créer un projet Python avec layout `src/<nom>/` et un `pyproject.toml` prêt à l'emploi — c'est exactement le layout attendu par la Structural Seed de la spine. [Source: docs.astral.sh/uv/concepts/projects/init](https://docs.astral.sh/uv/concepts/projects/init/)

### References

- [Source: _bmad-output/planning-artifacts/architecture/architecture-agent-veille-emploi-ia-2026-07-24/ARCHITECTURE-SPINE.md#AD-2] — contrat de connecteur uniforme
- [Source: _bmad-output/planning-artifacts/architecture/architecture-agent-veille-emploi-ia-2026-07-24/ARCHITECTURE-SPINE.md#AD-4] — champs invariants de `Item`
- [Source: _bmad-output/planning-artifacts/architecture/architecture-agent-veille-emploi-ia-2026-07-24/ARCHITECTURE-SPINE.md#Consistency-Conventions] — nommage, dates, identité d'item
- [Source: _bmad-output/planning-artifacts/architecture/architecture-agent-veille-emploi-ia-2026-07-24/ARCHITECTURE-SPINE.md#Structural-Seed] — arborescence de fichiers
- [Source: _bmad-output/planning-artifacts/epics.md#Story-1.1] — story d'origine et critères d'acceptation
- [Source: _bmad-output/planning-artifacts/prds/prd-agent-veille-emploi-ia-2026-07-24/prd.md#4.1] — FR-1, description de la collecte

## Dev Agent Record

### Agent Model Used

claude-sonnet-5

### Debug Log References

Aucun blocage rencontré — implémentation en TDD strict (rouge confirmé avant chaque module : `veille.models`, `veille.config`, `veille.connectors.rss_connector`, `veille.collect`), tous les tests verts dès la première tentative après écriture du code.

### Completion Notes List

- Projet initialisé via `uv init --package --name veille --vcs none` (dépôt git déjà présent, pas de réinitialisation). `feedparser` a résolu en 6.0.13 (plus récent que le 6.0.12 vérifié à l'architecture) — dérive normale, sans impact.
- **Portée tenue** : ni SQLite, ni dédoublonnage, ni backoff multi-source construits dans cette story — conformément au scoping explicite des Dev Notes.
- **Validation manuelle AC 1 en conditions réelles** (Task 6) : `uv run python -m veille.collect` contre `https://openai.com/news/rss.xml` → 1051 items récupérés, tous au format canonique. Exemple vérifié : `titre="How AI is expanding what people do at work"`, `date_publication` en UTC timezone-aware, `source_id="openai-news"`, `registre="ce_qui_bouge"`, `guid == url` (pas de `<guid>` distinct dans ce flux, repli sur le lien — comportement attendu).
- **Observation utile pour les stories suivantes** : le flux OpenAI news n'est pas limité aux articles récents — il expose l'historique complet (1051 entrées). Cette story ne filtre pas par date puisque ce n'est pas dans son périmètre (FR-4/5/6, Stories 1.4-1.6) ; à garder en tête pour le dimensionnement du filtrage à venir.
- 11/11 tests passent (`uv run pytest`), aucune régression.

### File List

- `pyproject.toml` (généré par `uv init`, dépendances ajoutées)
- `.python-version` (généré par `uv init`)
- `uv.lock` (généré par `uv add`)
- `README.md` (généré par `uv init`, non modifié)
- `config/sources.yaml`
- `site/archive/.gitkeep`
- `src/veille/__init__.py` (généré par `uv init`, non modifié)
- `src/veille/models.py`
- `src/veille/config.py`
- `src/veille/collect.py`
- `src/veille/connectors/__init__.py`
- `src/veille/connectors/rss_connector.py`
- `tests/fixtures/sample_feed.xml`
- `tests/test_models.py`
- `tests/test_config.py`
- `tests/test_rss_connector.py`
- `tests/test_collect.py`
- `templates/.gitkeep` (ajouté en revue de code)

## Review Findings

- [x] [Review][Résolu] Ordre de calcul du `guid` — tranché le 2026-07-28 : identifiant natif du flux (`entry.id`) en priorité, puis URL, puis hash. Un identifiant natif est conçu pour être permanent ; une URL peut dériver (tracking, migration) sans que le contenu change, ce qui casserait le dédoublonnage cross-nuit (Story 3.4). Le code implémentait déjà cette règle — seules la spine (Consistency Conventions) et cette story (Task 4, Dev Notes) le contredisaient ; corrigées. Aucun changement de code nécessaire.
- [x] [Review][Patch] `feed.bozo = True` jette tous les items, y compris les exploitables [src/veille/connectors/rss_connector.py:29] — tranché le 2026-07-28 : assouplir. Le principe « page maigre plutôt que bruyante » du PRD concerne le choix éditorial de ce qu'on *montre*, pas la fiabilité de ce qu'on *collecte* — les deux avaient été mélangés à tort en proposant ce point comme équilibré. `feedparser` est conçu pour rester tolérant : `bozo=1` signale une anomalie mineure et récupérable pendant que `feed.entries` reste souvent exploitable. Correctif : journaliser l'avertissement, mais traiter quand même les entrées si `feed.entries` n'est pas vide ; ne retourner `[]` que si `bozo` *et* aucune entrée récupérable.

- [x] [Review][Patch] `load_sources()` non protégée dans `run()` — un seul souci de configuration fait planter TOUTE la collecte, pas seulement une source [src/veille/collect.py:29] — Contredit directement AD-6 et la promesse du docstring de `collect.py` ("une source qui échoue ne doit jamais interrompre la collecte des autres"). Un fichier `sources.yaml` absent, mal formé, ou une seule entrée avec un champ manquant/en trop (`TypeError` sur `SourceConfig(**entry)`) fait planter l'exécution entière — alors que `_fetch_one` isole bien les pannes, mais seulement *après* le chargement. Sévérité haute : à mesure que le socle grossira (15-20 sources en Epic 2), la probabilité qu'une seule entrée YAML mal formée tue toute la nuit augmente fortement, silencieusement.
- [x] [Review][Patch] `contenu_brut` ne retombe jamais sur `entry.description` comme documenté [src/veille/connectors/rss_connector.py:53] — Les Dev Notes de cette story précisent explicitement `entry.summary` (ou `entry.description` selon le flux). Le code ne lit que `summary`. `feedparser` normalise le plus souvent `<description>` RSS vers `.summary`, ce qui masque le problème sur les flux RSS (dont OpenAI) — mais les flux Atom ont un champ `content` distinct de `summary`, et cette story se présente comme « connecteur RSS/Atom » sans le gérer.
- [x] [Review][Patch] Une seule entrée avec une date invalide fait perdre tous les items de sa source pour la nuit [src/veille/connectors/rss_connector.py:38] — `_to_item` est appelé dans une liste en compréhension ; si `_to_utc_datetime` lève sur une seule entrée (date hors limites, `struct_time` corrompu — ça arrive sur de vrais flux), toute la liste échoue. `_fetch_one` rattrape l'exception donc le run global survit (AD-6 tient au niveau macro), mais la source entière perd tous ses items ce soir-là pour la faute d'une seule entrée.
- [x] [Review][Patch] Sous-tâche Task 1 cochée mais dossier `templates/` jamais réellement créé de façon persistante [pas de `templates/.gitkeep`] — Le dossier existe sur disque mais est vide ; git ne suit pas les dossiers vides, donc `templates/` disparaîtra au premier commit/clone. Contrairement à `site/archive/.gitkeep`, aucun `.gitkeep` n'a été ajouté ici alors que la sous-tâche le prévoyait explicitement.

- [x] [Review][Defer] Collision de `guid` de repli sur `source_id + titre` — deferred, pre-existing pattern, consequence only materializes once Story 1.3 (dédoublonnage) exists to act on guid identity; deux entrées sans lien ni id partageant un titre générique collapsent aujourd'hui sans effet observable.
- [x] [Review][Defer] Aucun timeout réseau sur `feedparser.parse()` — deferred, explicitement du ressort d'Epic 2 (Story 2.2/2.3, tolérance aux pannes et sources sensibles au débit) selon le phasage déjà planifié.
- [x] [Review][Defer] Pas de distinction entre échec HTTP (404/500) et flux malformé — deferred, recoupe directement Epic 4 (FR-12/13, détection de sources défaillantes) qui est conçu pour ce diagnostic ; scope creep si ajouté maintenant.
- [x] [Review][Defer] `models.py` ne valide que `date_publication`, pas les autres champs requis non vides — deferred, l'AC2 tel qu'écrit exige seulement la présence des champs, pas leur non-vacuité ; à muscler quand Story 1.8 rendra les champs vides visiblement cassés.
- [x] [Review][Defer] Aucun User-Agent explicite envoyé — deferred, risque spéculatif non observé sur ce flux ; à surveiller quand le socle s'élargira (Epic 2).
- [x] [Review][Defer] Pas de requête conditionnelle (ETag/Last-Modified) — deferred, optimisation réseau pertinente seulement à l'échelle du socle complet tournant nuit après nuit (Epic 2/3).
- [x] [Review][Defer] `contenu_brut` est du contenu brut non échappé, risque XSS si affiché tel quel — deferred, aucun rendu HTML n'existe dans cette story ; à vérifier explicitement à la Story 1.8 (s'assurer que l'échappement automatique de Jinja2 reste actif, ne pas utiliser le filtre `|safe` sur ce champ).

## Change Log

- 2026-07-28 — Implémentation initiale de la Story 1.1 : modèle `Item` canonique, chargement de configuration des sources, connecteur RSS, orchestration de collecte avec isolation de panne. Toutes les ACs validées, 11/11 tests verts.
- 2026-07-28 — Revue de code (3 relecteurs parallèles) : 2 décisions tranchées, 5 correctifs appliqués, 7 points différés. Suite portée à 20/20 tests verts, aucune régression sur le flux réel.

### Détail des correctifs appliqués (2026-07-28)

1. **Isolation de panne étendue au chargement de configuration** (`collect.py`) — `run()` encapsule désormais `load_sources()`. Un `sources.yaml` absent ou illisible produit une collecte vide journalisée, plus un plantage du run entier. Complété par une isolation par entrée dans `config.py` : une seule entrée YAML mal formée est ignorée, les autres sources sont conservées. Robustesse également ajoutée sur les formes YAML inattendues (racine non-mapping, `sources:` vide, `sources` non-liste).
2. **Assouplissement du traitement `bozo`** (`rss_connector.py`) — vérifié empiriquement : une esperluette non échappée met `bozo=1` alors que feedparser récupère parfaitement toutes les entrées. Le flux est désormais exploité si des entrées existent ; seul un flux sans aucune entrée exploitable retourne une liste vide. L'avertissement reste journalisé (utile pour FR-12, santé des sources).
3. **Isolation au niveau de l'entrée** (`rss_connector.py`) — la compréhension de liste est remplacée par une boucle avec `try/except` par entrée. Une entrée corrompue (date hors limites, champ inattendu) est ignorée sans faire perdre les autres entrées de la même source.
4. **Repli d'extraction du contenu** (`rss_connector.py`) — `_extract_contenu()` essaie `summary`, puis `content[0].value` (Atom), puis `description`. **Correctif défensif, non curatif** : le test Atom passait déjà avant le correctif, feedparser normalisant `content` vers `summary` dans ce cas. Conservé car les Dev Notes le documentaient et le coût est nul.
5. **`templates/.gitkeep` ajouté** — le dossier existait sur disque mais vide, donc invisible pour git et destiné à disparaître au premier clone.
