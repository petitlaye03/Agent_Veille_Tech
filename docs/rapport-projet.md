# Rapport de projet — Agent de veille tech

> **Ce document est vivant.** Il est mis à jour à la fin de chaque story (dev
> + revue de code), pour qu'on puisse toujours reconstituer d'où on part,
> même après une longue coupure. Ne pas le laisser dériver : chaque section
> « État d'avancement » et « Journal des décisions » doit refléter le
> dernier état réel, pas un instantané figé.
>
> **Dernière mise à jour :** 2026-08-28, fin de la Story 1.4 (dev + revue).
> **Story courante :** aucune (1.4 terminée, `done`).
> **Prochaine story :** 1.5 — Répartir en trois sections à quotas.

---

## 1. Le projet en une phrase

Un pipeline Python qui collecte, filtre et résume chaque nuit l'actualité IA/data/emploi d'Abdoulaye en une page web — huit accroches en français maximum, prête à consulter au réveil, sans qu'il ait rien à faire pour la produire.

## 2. Pourquoi

Suivre l'IA en 2026 est matériellement impossible : il se publie chaque jour plus que ce qu'on peut lire en un mois. Les digests existants échouent pour une raison précise — ils exigent de créer un nouveau moment dans la journée pour les lire, et un moment qu'il faut créer finit toujours par ne pas l'être.

Le projet part de là : la page doit coûter le moins d'effort possible à consulter (URL fixe, en favori), et **zéro effort à produire** (générée automatiquement la veille au soir). Objectif personnel derrière l'objectif produit : Abdoulaye est Junior Data Scientist à Dakar, en fin de premier stage (nov. 2026), et vise des postes AI/LLM Engineer, ML Engineer, Data Scientist, Data Engineer — la veille doit combler l'écart entre son profil et ces postes, pas seulement l'informer.

Sources : [brief.md](../_bmad-output/planning-artifacts/briefs/brief-agent-veille-emploi-ia-2026-07-20/brief.md), [prd.md](../_bmad-output/planning-artifacts/prds/prd-agent-veille-emploi-ia-2026-07-24/prd.md).

## 3. Architecture

Pipeline **pipes-and-filters**, six étapes isolées :

```
collecte → dédoublonnage → filtrage/scoring → accroches FR → rendu → publication
```

*(Note : la Story 1.4 a corrigé l'ordre réel du sous-pipeline — voir §7.4. L'ordre livré est : collecte → **seuil de signal** → dédoublonnage → **scoring** → …)*

### Décisions structurantes (AD-1 à AD-11)

Document de référence : [ARCHITECTURE-SPINE.md](../_bmad-output/planning-artifacts/architecture/architecture-agent-veille-emploi-ia-2026-07-24/ARCHITECTURE-SPINE.md).

| AD | Règle | État |
|---|---|---|
| AD-1 | Paradigme pipeline ; aucune dépendance ne remonte, seul l'orchestrateur ordonne | ⚠️ En tension assumée — `collect.py` orchestre déjà 3 étapes (collecte, dédup, filter) faute de `pipeline.py`. Reporté à la Story 1.8 (voir §8) |
| AD-2 | Connecteurs derrière `Connector.fetch() -> list[Item]`, un module par type | ✅ RSS, JSON, scrape |
| AD-3 | Sources et Profil en configuration, jamais en dur | ✅ `sources.yaml`, `profil.md`, `scoring.yaml` |
| AD-4 | `Item` = forme interne canonique | ✅ 9 champs depuis l'amendement du 2026-08-27 (ajout de `signal`, voir §7.4) |
| AD-5 | SQLite, propriétaire unique de l'état | ⏳ Pas encore construit — prévu quand une story en aura réellement besoin (dédup cross-nuit Story 3.4, santé des sources Epic 4) |
| AD-6 | Isolation des pannes par source, jamais d'exception qui interrompt le run | ✅ Éprouvé en conditions réelles (Story 1.2) et durci à plusieurs reprises en revue |
| AD-7 | Frontière LLM unique (`enrich.llm`, Claude Haiku) | ⏳ Pas encore construit (Story 1.6) |
| AD-8 | Publication par commit git vers GitHub Pages | ⏳ Pas encore construit (Story 1.8) |
| AD-9 | Idempotence du job nocturne (upsert par date) | ⏳ Epic 3 |
| AD-10 | Aucune source en violation de CGU ; `robots.txt` vérifié avant scraping | ✅ Vérification runtime implémentée (Story 1.2, seconde passe de revue) |
| AD-11 | « Déjà vu » validé seulement après publication réussie | ⏳ Epic 3 |

**Stack :** Python 3.11 · uv · feedparser · httpx · beautifulsoup4 · PyYAML · Jinja2 (à venir) · SQLite stdlib (à venir) · API Claude Haiku (à venir).

## 4. Méthode de travail

Projet mené en méthode **BMAD** : brief → PRD → architecture → epics/stories → dev → revue, tous les artefacts vivant sous `_bmad-output/`.

**Convention actée le 2026-08-27** : tout le cycle de développement passe systématiquement par les skills BMad dédiés, jamais en freestyle :
- créer une story → `bmad-create-story`
- coder une story → `bmad-dev-story`
- revue de code → `bmad-code-review`

**Recommandation suivie depuis la Story 1.4** : la revue de code tourne sur un modèle différent de celui qui a implémenté (ex. implémentation sur Sonnet 5, revue sur Opus 5) — trois couches adversariales en parallèle (Blind Hunter, Edge Case Hunter, Acceptance Auditor).

## 5. État d'avancement — vue d'ensemble

| Epic | Contenu | État |
|---|---|---|
| **Epic 1** | Un premier digest, réel, bout en bout (3-5 sources) | 🟡 En cours — Stories 1.1-1.4 `done`, 1.5-1.9 à faire |
| **Epic 2** | Socle élargi (15-20 sources) et robustesse aux pannes | ⏳ Pas commencé |
| **Epic 3** | Génération nocturne automatique | ⏳ Pas commencé |
| **Epic 4** | Santé des sources et découverte de nouvelles sources | ⏳ Pas commencé |

### Détail Epic 1

| Story | Titre | Statut | Tests |
|---|---|---|---|
| 1.1 | Collecte d'une première source RSS | ✅ `done` | 20 |
| 1.2 | Connecteurs API JSON et scraping | ✅ *(fichier dit `review` ; travail de revue en réalité terminé — voir note ⚠️ ci-dessous)* | 31 → 44 |
| 1.3 | Dédoublonnage inter/intra-source | ✅ *(idem — `review` au frontmatter, revue terminée)* | 70 → 97 |
| 1.4 | Filtrage par signal + scoring par profil | ✅ `done` | 147 → **189** |
| 1.5 | Quotas par section (Apprendre/Ce qui bouge/Pour le métier) | ⏳ à faire | — |
| 1.6 | Accroches en français (frontière LLM) | ⏳ à faire | — |
| 1.7 | Signaler les entrées à ne pas manquer | ⏳ à faire | — |
| 1.8 | Publier une page à URL fixe (rendu + publication + `pipeline.py`) | ⏳ à faire | — |
| 1.9 | Archiver chaque digest en Markdown | ⏳ à faire | — |

> ⚠️ **Note d'hygiène à traiter** : les fichiers de story 1.2 et 1.3 portent encore `Status: review` dans leur frontmatter, alors que leurs Change Log respectifs démontrent une revue menée et conclue (correctifs appliqués, suites vertes). Seule la Story 1.4 a été explicitement repassée à `done`. À corriger mécaniquement (`review` → `done`) la prochaine fois qu'on touche à ces fichiers, sans quoi un outil qui scanne les statuts pourrait les compter comme encore en attente.

**Total tests actuel : 189, tous verts** (`uv run pytest`).

## 6. Ce qui est livré, story par story

### 6.1 — Story 1.1 : collecte d'une première source RSS

Premher connecteur (`rss_connector.py`), modèle `Item` canonique (8 champs), chargement de `sources.yaml`, orchestration `collect.py`. Validé en conditions réelles contre le flux OpenAI : 1051 items.

Revue (2026-07-28) : 2 décisions tranchées, 5 correctifs (isolation de panne étendue au chargement de config, assouplissement du traitement `bozo` de feedparser, isolation par entrée, repli d'extraction du contenu, `templates/.gitkeep` manquant), 7 reports. 11 → 20 tests.

### 6.2 — Story 1.2 : connecteurs API JSON et scraping

Ajout de `json_connector.py` (mapping déclaratif, générique) et `scrape_connector.py` (sélecteurs sémantiques, pas de classes CSS générées). Socle porté à 4 sources / 3 types. `robots.txt` vérifié pour Anthropic.

**AC3 reformulé après audit** — l'énoncé initial (« ajouter une source ne modifie aucun code ») était sur-vendu : seuls un flux RSS et une API JSON publique simple se branchent par pure configuration ; scraping, pagination, authentification exigent du code. Une affirmation « zéro champ manquant » a aussi été rectifiée : 949/1946 items (48,8 %) ont en réalité un `contenu_brut` vide — propriété des sources elles-mêmes (HF blog n'expose aucun contenu), pas un défaut du code.

Deux passes de revue (première par manque de session) : 8 puis 5 correctifs supplémentaires — dont l'ajout du contrôle runtime `robots.txt` (la case avait été cochée à tort pour une vérification manuelle unique), et l'ajout de `test_socle_reel.py` (le socle réel n'était gardé par aucun test). Ajout hors périmètre décidé par l'utilisateur : l'observabilité de la collecte (`RapportSource` à 3 états : collectée / MUETTE / ÉCHEC), jugée trop importante pour attendre. 1946 items validés en conditions réelles. 31 → 44 tests.

### 6.3 — Story 1.3 : dédoublonnage inter/intra-source

`dedup.py` : identité par URL normalisée **ou** `guid`, regroupement en classes d'équivalence (union-find) pour respecter la transitivité. Priorité de source déclarée en configuration (`priorite`, défaut 0, plus haut gagne).

Revue marquante — **un push avait eu lieu à tort avant la revue**. Un audit par mutation a montré que la suite (70 tests) restait verte même en vidant les priorités, en les inversant, ou en **court-circuitant le dédoublonnage lui-même** : `collecter()` pouvait retourner la liste non dédoublonnée tout en annonçant « N doublons écartés ». Cause : tous les tests appelaient `dedupliquer()` en direct, jamais par le chemin réel depuis `sources.yaml`. Correctif le plus important : `tests/test_collecte_integration.py` créé pour emprunter le vrai chemin config → collecte → rapport — un principe repris depuis dans toutes les stories suivantes. Un défaut critique corrigé : une URL malformée levait hors de l'isolation de panne AD-6 et faisait perdre la nuit entière. 70 → 97 tests.

### 6.4 — Story 1.4 : filtrage par signal + scoring par profil

La plus grosse à ce jour, en deux temps.

**Amendement d'architecture préalable (2026-08-27)** : AD-4 limitait `Item` à 8 champs et interdisait aux étapes avales d'en consommer un neuvième — incompatible avec FR-4 (seuil de signal par source). Décision (option A) : ajouter `signal: float | None = None` comme 9ᵉ champ optionnel, neutre par défaut. Acté dans `ARCHITECTURE-SPINE.md` avant tout code.

**Implémentation (Sonnet 5)** : `profil.py` (parseur de `config/profil.md`), `filter.py` (seuil de signal, scoring lexical par mots-clés, classement), branchement dans `collecter()`. 147 tests, statut `review`.

**Revue de code (Opus 5, 2026-08-28)** — la plus instructive à ce jour : **l'AC5 n'était en réalité pas satisfait**, alors que la story le déclarait coché. Le parseur de profil ne découpait les mots-clés que sur `,:()&/` et le tiret cadratin ; une puce rédigée en phrase (`Levées de fonds et actualité business pure sans contenu technique`) devenait un mot-clé égal à la phrase entière — introuvable dans un article. Conséquence mesurée : une levée de fonds obtenait **+2** (promue) au lieu d'être pénalisée. Sur les trois exemples cités par l'AC5 (crypto, hype, actu conso), seul `crypto` fonctionnait.

Deux plantages **hors isolation de panne** ont aussi été trouvés (un `scoring.yaml` non-UTF-8, un `seuil_signal` non numérique) — la même classe de défaut que la Story 1.3 avait déjà dû corriger. Et l'audit par mutation initial ne portait que sur le code : refait en incluant la **configuration**, 4 mutants supplémentaires sont morts (dont « retirer `seuil_signal` de `sources.yaml` », qui ne faisait échouer aucun test).

6 décisions tranchées, 20 correctifs appliqués, 3 reports, 1 rejet. 147 → 189 tests. Détail complet : [1-4-scoring-par-profil.md](../_bmad-output/implementation-artifacts/1-4-scoring-par-profil.md).

## 7. Journal des décisions structurantes (cumulatif)

Ce journal ne répète pas le détail des stories (§6) ; il ne garde que ce qui **contraint les stories suivantes**.

1. **Identité d'un `Item` (guid)** — priorité à l'identifiant natif du flux, puis URL, puis hash `(source_id + titre)`. Un identifiant natif est permanent ; une URL peut dériver sans que le contenu change (Story 1.1).
2. **Priorité de dédoublonnage = champ explicite en configuration**, pas l'ordre du fichier ni une heuristique de qualité. Plus haut gagne, égalité → premier rencontré, jamais aléatoire (Story 1.3).
3. **Identité de dédoublonnage = union-find**, pas deux vérifications successives : garantit la transitivité (A≡B, B≡C ⇒ A≡B≡C) et l'indépendance à l'ordre d'arrivée (Story 1.3).
4. **AC3 de la Story 1.2 reformulé honnêtement** : seuls RSS et API JSON simple se branchent sans code ; scraping/pagination/auth en demandent.
5. **Aucune fonction du pipeline ne doit lever hors de sa boucle protégée par source** — leçon tirée trois fois (Story 1.1 : dates malformées ; Story 1.3 : URL malformée ; Story 1.4 : configuration mal typée). Devenu un réflexe de revue systématique.
6. **`Item` porte 9 champs, pas 8** — amendement AD-4 du 2026-08-27 : `signal: float | None = None`, optionnel et neutre par défaut (Story 1.4).
7. **Ordre réel du sous-pipeline de filtrage : seuil de signal AVANT dédoublonnage**, pas après. Le seuil est déclaré *par source* ; appliqué après l'élection d'un gagnant de dédoublonnage, il pouvait faire disparaître un article dont la source réelle n'avait aucun seuil (Story 1.4, corrigé en revue).
8. **Règles de cumul du scoring par profil** : un thème compté dans deux catégories du profil ne compte qu'une fois, au poids de la catégorie la plus élevée ; les mots-clés suivants d'une même catégorie sont atténués (½, ¼…) pour qu'empiler des termes génériques ne batte pas un item en plein cœur de cible (Story 1.4, tranché en revue).
9. **Correspondance de mots-clés tolérante au singulier/pluriel** (`s` final optionnel), frontières de mot conditionnelles (ne s'ancrent que contre un caractère alphanumérique, sinon un mot-clé bordé de ponctuation devient inerte) (Story 1.4).
10. **Les tests ne doivent jamais dépendre implicitement de la configuration de production** (`config/profil.md`, `config/scoring.yaml`) — un `conftest.py` neutralise ces valeurs par défaut pour tous les tests, sauf ceux qui testent explicitement le fichier réel (Story 1.4, suite à la revue).
11. **`pipeline.py` n'existe pas encore** : `collect.py` orchestre pour l'instant collecte + dédup + filtrage, en tension assumée avec AD-1. Reporté à la Story 1.8, quand rendu et publication existeront et donneront tout son sens à un orchestrateur dédié.

## 8. Dette technique et travail reporté

Liste vivante complète : [deferred-work.md](../_bmad-output/implementation-artifacts/deferred-work.md). Résumé de ce qui reste ouvert, par destination :

**Epic 2 (socle élargi, robustesse)** — timeout réseau sur `feedparser`/`httpx`, distinction 404 vs flux malformé, retry/backoff sur 429/5xx, plafond de taille des réponses HTTP, mode d'extraction « carte » pour le scraping (titre/date en frères de l'ancre, pas en descendants — bloque l'ajout de la plupart des blogs WordPress), en-têtes/authentification pour les API JSON (bloque Kaggle, prévu au socle v1), `url_modele` limité à `{guid}`.

**Epic 3 (nocturne automatique)** — `pipeline.py` comme orchestrateur dédié (AD-1), délai d'attente global sur `feedparser`.

**Epic 4 (santé des sources)** — distinction diagnostique fine des échecs, racine JSON vide non signalée, bornes de plausibilité sur les dates aberrantes.

**Story 1.8 (rendu)** — échappement de `contenu_brut` (risque XSS, s'assurer que Jinja2 échappe automatiquement, jamais `|safe` sur ce champ), `models.py` qui ne valide que la non-nullité de `date_publication` (pas les autres champs), `Score.motifs` calculé mais jamais consommé (aucun lecteur avant l'affichage d'une entrée).

**Story 1.5 (quotas)** — le dédoublonnage réassigne `langue`/`registre` de l'article gagnant : comportement voulu, à revérifier à l'arrivée des quotas par section. Le tri final est désormais exclusivement par score (Story 1.4) ; il n'y a plus de tri par fraîcheur — la question « à score égal, quoi en premier ? » se pose de toute façon aux quotas.

**Non priorisé** — `SourceConfig` non hashable, `_resoudre_chemin` ne traverse pas les listes, validation du `type`/champs requis par source au chargement, formats de date US ambigus (`%m/%d/%Y`), garde de domaine sensible à la casse.

## 9. Environnement et infrastructure

**Migration Windows → Mac (2026-08-27)** : le dossier a été copié tel quel depuis l'ancien PC. Deux corrections faites à la reprise :
- le `.git` était resté à la racine de `Projets_Perso/` (englobant à tort `Saas_chatbots/`, un projet distinct) — déplacé dans `Agent_veille_tech/.git` pour que ce dossier soit son propre dépôt, aligné sur le remote `petitlaye03/Agent_Veille_Tech` ;
- `.venv` était un venv Windows inutilisable (`home = C:\Program Files\Python311`) — supprimé et reconstruit avec `uv sync` (`uv` installé via Homebrew, absent du Mac).

**État actuel** : dépôt propre à part le travail non commité de la Story 1.4 (voir `git status`). Aucun commit n'est fait automatiquement — décision du 2026-08-27 : les commits restent à la demande explicite d'Abdoulaye.

## 10. Prochaine étape

**Story 1.5 — Répartir en trois sections à quotas** (≈3 Apprendre / ≈3 Ce qui bouge / ≈2 Pour le métier, configurables, jamais de remplissage un jour creux). À lancer via `bmad-create-story` (elle n'est pas encore rédigée en détail dans `implementation-artifacts/`) puis `bmad-dev-story`, revue via `bmad-code-review` sur un modèle différent de celui qui code.

Point d'attention déjà identifié pour cette story (§8) : la réassignation de `langue`/`registre` par le dédoublonnage, et l'absence de tri par fraîcheur.
