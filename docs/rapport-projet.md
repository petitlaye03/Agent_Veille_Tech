# Rapport de projet — Agent de veille tech

> **Ce document est vivant.** Il est mis à jour à la fin de chaque story (dev
> + revue de code), pour qu'on puisse toujours reconstituer d'où on part,
> même après une longue coupure — et pour servir de référence technique
> fichier par fichier, pas seulement de suivi d'avancement. Ne pas le
> laisser dériver : chaque section doit refléter le dernier état réel du
> code, pas un instantané figé. La §10 (Référence technique) en particulier
> doit être corrigée dès qu'un fichier qu'elle décrit change de comportement.
>
> **Dernière mise à jour :** 2026-08-28, fin de la Story 1.5 (dev + revue).
> **Story courante :** aucune (1.5 terminée, `done`).
> **Prochaine story :** 1.6 — Générer une accroche en français pour chaque entrée.

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

L'étape « filtrage/scoring » se décompose en réalité en trois sous-étapes, dans cet ordre exact (voir §10.7 pour le détail) :

```
… → seuil de signal → scoring par profil → quotas par registre → …
```

et se **branche avant** le dédoublonnage pour le seuil de signal (corrigé en revue de la Story 1.4 — un seuil par source appliqué après l'élection d'un gagnant de dédoublonnage pouvait faire disparaître un article auquel aucun seuil ne s'appliquait) :

```
collecte → seuil de signal → dédoublonnage → scoring par profil → quotas par registre → (accroches, rendu, publication)
```

### Décisions structurantes (AD-1 à AD-11)

Document de référence : [ARCHITECTURE-SPINE.md](../_bmad-output/planning-artifacts/architecture/architecture-agent-veille-emploi-ia-2026-07-24/ARCHITECTURE-SPINE.md).

| AD | Règle | État |
|---|---|---|
| AD-1 | Paradigme pipeline ; aucune dépendance ne remonte, seul l'orchestrateur ordonne | ⚠️ En tension assumée — `collect.py` orchestre déjà 4 étapes (collecte, dédup, filter, quotas) faute de `pipeline.py`. Reporté à la Story 1.8 (voir §8) |
| AD-2 | Connecteurs derrière `Connector.fetch() -> list[Item]`, un module par type | ✅ RSS, JSON, scrape |
| AD-3 | Sources et Profil en configuration, jamais en dur | ✅ `sources.yaml`, `profil.md`, `scoring.yaml`, `quotas.yaml` |
| AD-4 | `Item` = forme interne canonique | ✅ 9 champs depuis l'amendement du 2026-08-27 (ajout de `signal`, voir §7.6) |
| AD-5 | SQLite, propriétaire unique de l'état | ⏳ Pas encore construit — prévu quand une story en aura réellement besoin (dédup cross-nuit Story 3.4, santé des sources Epic 4) |
| AD-6 | Isolation des pannes par source, jamais d'exception qui interrompt le run | ✅ Éprouvé en conditions réelles (Story 1.2) et durci à plusieurs reprises en revue |
| AD-7 | Frontière LLM unique (`enrich.llm`, Claude Haiku) | ⏳ Pas encore construit (Story 1.6 — prochaine) |
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

**Revue de code** : trois couches adversariales en parallèle (Blind Hunter, Edge Case Hunter, Acceptance Auditor), triage manuel avant d'agir. Le modèle utilisé pour la revue a varié selon la story (Opus 5 pour la 1.4, Sonnet 5 — même modèle que l'implémentation — pour la 1.5, sur demande explicite d'Abdoulaye) : la recommandation par défaut reste un modèle différent de celui qui a implémenté, mais ce n'est pas une règle absolue.

## 5. État d'avancement — vue d'ensemble

| Epic | Contenu | État |
|---|---|---|
| **Epic 1** | Un premier digest, réel, bout en bout (3-5 sources) | 🟡 En cours — Stories 1.1-1.5 `done`, 1.6-1.9 à faire |
| **Epic 2** | Socle élargi (15-20 sources) et robustesse aux pannes | ⏳ Pas commencé |
| **Epic 3** | Génération nocturne automatique | ⏳ Pas commencé |
| **Epic 4** | Santé des sources et découverte de nouvelles sources | ⏳ Pas commencé |

### Détail Epic 1

| Story | Titre | Statut | Tests |
|---|---|---|---|
| 1.1 | Collecte d'une première source RSS | ✅ `done` | 20 |
| 1.2 | Connecteurs API JSON et scraping | ✅ *(fichier dit `review` ; travail de revue en réalité terminé — voir note ⚠️ ci-dessous)* | 31 → 44 |
| 1.3 | Dédoublonnage inter/intra-source | ✅ *(idem — `review` au frontmatter, revue terminée)* | 70 → 97 |
| 1.4 | Filtrage par signal + scoring par profil | ✅ `done` | 147 → 189 |
| 1.5 | Quotas par section (Apprendre/Ce qui bouge/Pour le métier) | ✅ `done` | 213 → **221** |
| 1.6 | Accroches en français (frontière LLM) | ⏳ à faire — **prochaine** | — |
| 1.7 | Signaler les entrées à ne pas manquer | ⏳ à faire | — |
| 1.8 | Publier une page à URL fixe (rendu + publication + `pipeline.py`) | ⏳ à faire | — |
| 1.9 | Archiver chaque digest en Markdown | ⏳ à faire | — |

> ⚠️ **Note d'hygiène à traiter** : les fichiers de story 1.2 et 1.3 portent encore `Status: review` dans leur frontmatter, alors que leurs Change Log respectifs démontrent une revue menée et conclue (correctifs appliqués, suites vertes). Seules les Stories 1.4 et 1.5 ont été explicitement repassées à `done`. À corriger mécaniquement (`review` → `done`) la prochaine fois qu'on touche à ces fichiers.

**Total tests actuel : 221, tous verts** (`uv run pytest`).

## 6. Ce qui est livré, story par story

### 6.1 — Story 1.1 : collecte d'une première source RSS

Premier connecteur (`rss_connector.py`), modèle `Item` canonique (8 champs), chargement de `sources.yaml`, orchestration `collect.py`. Validé en conditions réelles contre le flux OpenAI : 1051 items.

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

### 6.5 — Story 1.5 : quotas par section

Extension de `filter.py` (troisième mécanisme du module, après signal et scoring) : `Quotas`/`charger_quotas` sur le patron exact de `Ponderations`/`charger_ponderations`, `repartir_par_quotas` en un seul passage sur un classement déjà trié (jamais retrié), `RapportQuotas` pour rendre compte par registre. Branché en dernière étape du pipeline de filtrage. `config/quotas.yaml` nouveau (3/3/2 par défaut). 213 tests, statut `review`.

**Revue de code (Sonnet 5, même modèle que l'implémentation, sur demande explicite)** : la trouvaille la plus sérieuse concernait mon propre travail — **la note de plausibilité de la Task 4 était fausse**, exactement la même erreur que la Story 1.4 avait déjà dû corriger. Elle affirmait « par le chemin de production, sans override de chemin », alors qu'un socle fabriqué avait en réalité été utilisé (`openai-news` ré-étiqueté à tort en `pour_le_metier`, registre qu'il ne porte jamais réellement). Rejoué honnêtement contre le vrai `config/sources.yaml` (réseau réel, aucun override) : le mécanisme fonctionne correctement sur les deux registres réellement peuplés (`apprendre`, `ce_qui_bouge`) ; `pour_le_metier` n'apparaît dans aucune ligne du récapitulatif pour une raison structurelle **préexistante et non liée à cette story** — aucune source du socle actuel ne déclare ce registre (reporté à l'Epic 2).

Même audit par mutation d'abord incomplet qu'en Story 1.4, et pour la même raison structurelle : `conftest.py` fournissait toujours un fichier de quotas explicite aux tests, donc les *défauts de la dataclass* `Quotas` n'étaient exercés par aucune assertion absolue — 2 mutants de défauts + 1 de configuration (`quotas.yaml` supprimé) survivaient à la première passe malgré l'avertissement explicite laissé dans les Dev Notes de la story elle-même. Comblé par un test d'assertion en dur sur les défauts et un garde-fou sur le fichier réel (miroir de celui de `scoring.yaml`).

4 autres correctifs, plus mineurs : un formatage cassé dans `RapportQuotas.resume()` (quota à 0 vidant un registre), deux asymétries de validation dans `charger_quotas`**et** `charger_ponderations` (valeur falsy mal typée non signalée, clé de config inconnue perdue en silence — corrigées dans les deux fonctions par cohérence), et deux contrats rompus (`charger_quotas(None)`/`charger_ponderations(None)` levaient au lieu de dégrader).

6 décisions tranchées, 5 correctifs, 2 reports, 3 rejets. 213 → 221 tests. Détail complet : [1-5-quotas-par-section.md](../_bmad-output/implementation-artifacts/1-5-quotas-par-section.md).

## 7. Journal des décisions structurantes (cumulatif)

Ce journal ne répète pas le détail des stories (§6) ; il ne garde que ce qui **contraint les stories suivantes**.

1. **Identité d'un `Item` (guid)** — priorité à l'identifiant natif du flux, puis URL, puis hash `(source_id + titre)`. Un identifiant natif est permanent ; une URL peut dériver sans que le contenu change (Story 1.1).
2. **Priorité de dédoublonnage = champ explicite en configuration**, pas l'ordre du fichier ni une heuristique de qualité. Plus haut gagne, égalité → premier rencontré, jamais aléatoire (Story 1.3).
3. **Identité de dédoublonnage = union-find**, pas deux vérifications successives : garantit la transitivité (A≡B, B≡C ⇒ A≡B≡C) et l'indépendance à l'ordre d'arrivée (Story 1.3).
4. **AC3 de la Story 1.2 reformulé honnêtement** : seuls RSS et API JSON simple se branchent sans code ; scraping/pagination/auth en demandent.
5. **Aucune fonction du pipeline ne doit lever hors de sa boucle protégée par source** — leçon tirée quatre fois maintenant (Story 1.1 : dates malformées ; Story 1.3 : URL malformée ; Story 1.4 : configuration mal typée, `UnicodeDecodeError` ; Story 1.5 : `TypeError` sur chemin `None`). Devenu un réflexe de revue systématique — et une catégorie de correctif appliquée « par cohérence » à tout code voisin partageant le même motif, pas seulement au code touché par la story en cours.
6. **`Item` porte 9 champs, pas 8** — amendement AD-4 du 2026-08-27 : `signal: float | None = None`, optionnel et neutre par défaut (Story 1.4).
7. **Ordre réel du sous-pipeline de filtrage : seuil de signal AVANT dédoublonnage**, pas après. Le seuil est déclaré *par source* ; appliqué après l'élection d'un gagnant de dédoublonnage, il pouvait faire disparaître un article dont la source réelle n'avait aucun seuil (Story 1.4, corrigé en revue).
8. **Règles de cumul du scoring par profil** : un thème compté dans deux catégories du profil ne compte qu'une fois, au poids de la catégorie la plus élevée ; les mots-clés suivants d'une même catégorie sont atténués (½, ¼…) pour qu'empiler des termes génériques ne batte pas un item en plein cœur de cible (Story 1.4, tranché en revue).
9. **Correspondance de mots-clés tolérante au singulier/pluriel** (`s` final optionnel), frontières de mot conditionnelles (ne s'ancrent que contre un caractère alphanumérique, sinon un mot-clé bordé de ponctuation devient inerte) (Story 1.4).
10. **Les tests ne doivent jamais dépendre implicitement de la configuration de production** (`config/profil.md`, `config/scoring.yaml`, et depuis la Story 1.5 `config/quotas.yaml`) — `tests/conftest.py` neutralise ces trois fichiers par défaut pour tous les tests, sauf ceux qui testent explicitement le fichier réel.
11. **`pipeline.py` n'existe pas encore** : `collect.py` orchestre pour l'instant collecte + dédup + filtrage + quotas, en tension assumée avec AD-1. Reporté à la Story 1.8, quand rendu et publication existeront et donneront tout son sens à un orchestrateur dédié.
12. **`repartir_par_quotas` en un seul passage sur un classement déjà trié** : garder les N premiers items d'un registre revient à garder ses N mieux notés, sans second tri — même principe que `filtrer_par_signal` (Story 1.5).
13. **Un registre/réglage absent de la configuration est conservé, jamais écarté silencieusement** — principe posé pour le signal absent (Story 1.4, AC2) et reconduit à l'identique pour un registre absent de `quotas.yaml` (Story 1.5, AC6). Devenu la règle par défaut face à toute configuration incomplète : dégrader en conservant, jamais en supprimant.
14. **L'exécution réelle de plausibilité doit être vérifiée deux fois** : une fois par l'implémenteur, une fois — indépendamment — par le relecteur. Une affirmation « par le chemin de production, sans override » a été fausse deux stories de suite (1.4 puis 1.5), la seconde fois malgré un avertissement explicite écrit par l'implémenteur lui-même dans les Dev Notes de la story. La vérification doit s'appuyer sur `grep`/lecture directe du fichier de configuration réel, pas sur la mémoire de ce qu'il contient.
15. **Un correctif trouvé dans une fonction est appliqué par cohérence aux fonctions sœurs qui partagent le même motif**, même hors du fichier ou de la story nominalement en cause — ex. les correctifs de validation YAML de `charger_quotas` (Story 1.5) appliqués aussi à `charger_ponderations` (Story 1.4) dans le même passage de revue.

## 8. Dette technique et travail reporté

Liste vivante complète : [deferred-work.md](../_bmad-output/implementation-artifacts/deferred-work.md). Résumé de ce qui reste ouvert, par destination :

**Epic 2 (socle élargi, robustesse)** — timeout réseau sur `feedparser`/`httpx`, distinction 404 vs flux malformé, retry/backoff sur 429/5xx, plafond de taille des réponses HTTP, mode d'extraction « carte » pour le scraping (titre/date en frères de l'ancre, pas en descendants — bloque l'ajout de la plupart des blogs WordPress), en-têtes/authentification pour les API JSON (bloque Kaggle, prévu au socle v1), `url_modele` limité à `{guid}`, **`config/sources.yaml` ne déclare aucune source en registre `pour_le_metier`** (la 3ᵉ section du digest sera structurellement vide tant que cette lacune n'est pas comblée — trouvé en revue de la Story 1.5).

**Epic 3 (nocturne automatique)** — `pipeline.py` comme orchestrateur dédié (AD-1), délai d'attente global sur `feedparser`.

**Epic 4 (santé des sources)** — distinction diagnostique fine des échecs, racine JSON vide non signalée, bornes de plausibilité sur les dates aberrantes.

**Story 1.8 (rendu)** — échappement de `contenu_brut` (risque XSS, s'assurer que Jinja2 échappe automatiquement, jamais `|safe` sur ce champ), `models.py` qui ne valide que la non-nullité de `date_publication` (pas les autres champs), `Score.motifs` calculé mais jamais consommé (aucun lecteur avant l'affichage d'une entrée), `pipeline.py` (voir Epic 3/AD-1 ci-dessus).

**Non priorisé / précondition documentée, pas corrigée** — `rapport_quotas`/`rapport_classement` sur-comptent en théorie si le même objet `Item` apparaît deux fois dans leur entrée (non atteignable via `collecter()`, `dedup.py` garantit l'unicité — Story 1.5) ; `SourceConfig` non hashable ; `_resoudre_chemin` ne traverse pas les listes ; validation du `type`/champs requis par source au chargement ; formats de date US ambigus (`%m/%d/%Y`) ; garde de domaine sensible à la casse (scraping).

## 9. Environnement et infrastructure

**Migration Windows → Mac (2026-08-27)** : le dossier a été copié tel quel depuis l'ancien PC. Deux corrections faites à la reprise :
- le `.git` était resté à la racine de `Projets_Perso/` (englobant à tort `Saas_chatbots/`, un projet distinct) — déplacé dans `Agent_veille_tech/.git` pour que ce dossier soit son propre dépôt, aligné sur le remote `petitlaye03/Agent_Veille_Tech` ;
- `.venv` était un venv Windows inutilisable (`home = C:\Program Files\Python311`) — supprimé et reconstruit avec `uv sync` (`uv` installé via Homebrew, absent du Mac).

**État actuel** : dépôt propre (Stories 1.4 et 1.5 committées et poussées). Aucun commit n'est fait automatiquement — décision du 2026-08-27 : les commits restent à la demande explicite d'Abdoulaye.

## 10. Référence technique — fichier par fichier

Cette section documente **ce que fait chaque fichier**, en détail — pas seulement son existence. Elle est le complément technique de la narration par story (§6) : celle-ci raconte *comment* le code a évolué, celle-ci décrit *ce qu'il fait aujourd'hui*.

### 10.1 Vue d'ensemble

```text
src/veille/
  models.py               Le contrat de données canonique (Item)
  config.py               Chargement de sources.yaml, utilitaires de validation partagés
  connectors/
    rss_connector.py      Flux RSS/Atom
    json_connector.py     API JSON (mapping déclaratif)
    scrape_connector.py   Scraping HTML (sélecteurs sémantiques, robots.txt)
  dedup.py                Dédoublonnage inter/intra-source
  profil.py               Chargement et analyse de profil.md
  filter.py               Seuil de signal, scoring par profil, quotas par registre
  collect.py              Orchestrateur : enchaîne tout ce qui précède

config/
  sources.yaml            Socle de sources (4 aujourd'hui)
  profil.md               Profil de filtrage d'Abdoulaye (thèmes, bruit)
  scoring.yaml            Pondérations du scoring
  quotas.yaml             Quotas par registre

tests/
  conftest.py             Neutralise profil/pondérations/quotas par défaut
  test_*.py               14 fichiers, 221 tests (détail §10.10)
```

### 10.2 `src/veille/models.py` — le contrat canonique

Un seul type : `Item`, dataclass **frozen** (immuable) portant 9 champs :

| Champ | Type | Rôle |
|---|---|---|
| `source_id` | `str` | identifiant de la source déclarée dans `sources.yaml` |
| `guid` | `str` | identité au sein de la source (voir §7.1 pour la convention de calcul) |
| `titre` | `str` | titre de l'article |
| `date_publication` | `datetime` | **doit** être timezone-aware et en UTC — validé dans `__post_init__`, sinon `ValueError` |
| `langue` | `str` | langue déclarée par la source |
| `registre` | `str` | section cible (`apprendre` / `ce_qui_bouge` / `pour_le_metier`) |
| `url` | `str` | lien vers l'original |
| `contenu_brut` | `str` | résumé/extrait, non échappé (voir dette §8, Story 1.8) |
| `signal` | `float \| None` | votes/points de la source, optionnel — ajouté par l'amendement AD-4 (Story 1.4) |

C'est le **seul** point de couplage entre la collecte et tout ce qui suit : aucune étape avale ne doit consommer un champ qui n'y figure pas.

### 10.3 `src/veille/config.py` — configuration des sources et utilitaires partagés

- **`RACINE_PROJET`** / **`chemin_config(nom)`** — résout un fichier `config/<nom>` depuis la racine du dépôt (déduite de l'emplacement du module), et non depuis le répertoire courant. Utilisé par `profil.py` et `filter.py` pour leurs chemins par défaut : indispensable pour un run lancé par un planificateur de tâches (Epic 3), où le CWD n'est pas garanti.
- **`SourceConfig`** — dataclass frozen décrivant une source : `id`, `type`, `url`, `langue`, `registre` (communs), puis `priorite` (dédoublonnage), `seuil_signal` (FR-4), et des champs propres à chaque type de connecteur (`racine`, `mapping`, `url_modele` pour JSON ; `selecteur`, `base_url` pour le scraping).
- **`load_sources(path)`** — lit `sources.yaml`, isole chaque entrée : une source mal formée est journalisée et ignorée, les autres survivent.
- **`_normaliser(entry)`** — corrige `seuil_signal` avant construction de `SourceConfig`, via `to_float_fini`.
- **`to_float_fini(valeur)`** — utilitaire partagé (aussi utilisé par `filter.py` pour les pondérations) : convertit en `float` fini, rejette les booléens (`yes` → `True` → `1.0` silencieux évité) et `nan`/`inf` (toute comparaison à `nan` est fausse — un seuil `nan` laisserait tout passer sans le moindre signe).

### 10.4 `src/veille/connectors/` — un module par type de source, même contrat

Les trois connecteurs partagent le contrat `fetch(source_config: SourceConfig) -> list[Item]` (AD-2). Aucun autre module n'a besoin de savoir lequel est utilisé — `collect.CONNECTORS` fait le dispatch.

**`rss_connector.py`** — flux RSS/Atom via `feedparser`.
- Tolère un flux `bozo` (imparfait) tant qu'il expose des entrées exploitables ; ne renvoie une liste vide que si aucune entrée n'est récupérable.
- `guid` : identifiant natif du flux en priorité, puis URL, puis hash SHA-256 `(source_id + titre)` — convention posée en Story 1.1.
- `_extract_contenu` : repli en cascade `summary` → `content[0].value` (Atom) → `description`, pour ne jamais renvoyer un contenu vide alors que le flux en porte.
- Dates converties via `calendar.timegm` (pas `time.mktime`, qui appliquerait le fuseau local).
- Isolation par entrée : une entrée corrompue n'emporte pas les autres.

**`json_connector.py`** — API JSON, forme entièrement déclarée en configuration (`mapping`, chemins pointés type `paper.summary`).
- `_resoudre_chemin`/`_champ` : navigation dans une structure imbriquée ; un champ absent du mapping vaut `None`, jamais l'entrée entière.
- `guid` : `0` et `False` sont des identifiants valides (seuls `None`/`""` sont rejetés) ; un identifiant non scalaire (dict/list) lève une erreur explicite plutôt que de produire une URL corrompue.
- `url_modele` : gabarit avec le `guid` encodé (`quote`) avant insertion.
- `_to_signal` : convertit le signal en `float`, dégrade vers `None` sur toute valeur non numérique (jamais de plantage — le signal est une donnée d'appoint, Story 1.4).
- `_to_utc_datetime` : accepte ISO 8601 et horodatages Unix (secondes ou millisecondes, seuil de bascule à 1e11).

**`scrape_connector.py`** — scraping HTML, réservé aux sources sans flux ni API.
- `_collecte_autorisee` : consulte `robots.txt` **avant toute requête** (AD-10) ; absent ou injoignable → collecte autorisée par défaut, présent et restrictif → respecté.
- Extraction exclusivement par balises sémantiques (`h1`-`h4`, `time`, `p`) — jamais par classe CSS, qui change à chaque build d'un site moderne.
- `_extraire_titre` : repli structurel quand aucun titre sémantique n'existe — identifie le bloc de métadonnées par la balise `<time>` qu'il contient, et prend le premier `span` **hors** de ce bloc.
- `_extraire_date` : indépendant de la locale du système (table de mois explicite, formats numériques, regex) — `%b`/`%B` de `strptime` auraient échoué silencieusement sur un système en français.
- `_extraire_extrait` : écarte les libellés d'appel à l'action (« Read more », « Lire la suite »…) et la répétition du titre.
- Garde de domaine : un lien externe contenant le motif de sélection n'est jamais attribué à la source.

### 10.5 `src/veille/dedup.py` — dédoublonnage inter/intra-source (FR-3)

- **`normaliser_url(url)`** — canonicalise une URL : neutralise schéma, `www.`, port par défaut, barre oblique finale, fragment, encodage-pourcent, et une liste de paramètres de suivi (`PARAMETRES_DE_SUIVI` : `utm_*`, `fbclid`, `gclid`…). **Conserve** les autres paramètres de requête — sur certains sites `?id=42` est l'identité même de l'article. Ne lève jamais (hors isolation de panne) : une URL illisible retourne `""`, l'item retombant sur son `guid`.
- **`dedupliquer(items, priorites)`** — identité par union-find : chaque item porte une ou plusieurs clés (URL normalisée, `(source_id, guid)`), unies entre elles pour que la relation reste transitive. Un gagnant est élu par classe d'équivalence (priorité la plus haute, puis position la plus ancienne), l'ordre global suit la première apparition — **indépendant de l'ordre d'arrivée**.
- **`RapportDedoublonnage`** — compte les perdants **et** les gagnants par source (savoir qui absorbe est aussi important que savoir qui est absorbé).

### 10.6 `src/veille/profil.py` — chargement et analyse de `profil.md` (FR-5)

- **`Profil`** — 5 catégories de mots-clés en tuples (`prioritaire`, `signal_fort`, `domaine`, `secondaire`, `bruit`) ; `est_vide` détecte un profil neutre.
- **`charger_profil(chemin)`** — ne lève jamais : fichier absent/illisible → `Profil()` neutre, journalisé.
- **`_analyser(texte)`** — retire d'abord tout commentaire HTML (`<!-- ... -->`), puis parcourt les titres `##`/`###` : chaque titre ferme la section précédente (y compris un `#` de niveau 1, pour ne jamais laisser un mot-clé atterrir dans la mauvaise catégorie).
- **`_categorie(titre)`** — correspondance par **préfixe** normalisé (sans accent, apostrophe typographique convertie), pas égalité stricte : la fin d'un titre peut être reformulée sans casser le parseur. `Posture` est une section connue mais ignorée sans avertissement ; un titre vraiment inconnu, lui, avertit.
- **`_extraire_mots_cles(ligne)`** — pipeline de nettoyage : retire l'aside italique `*(...)*` (prose), tronque après un tiret cadratin/demi-cadratin (prose descriptive), retire la puce (`-`, `*`, `+`, `1.`) et le gras (`**`), découpe sur `[,:()&/]`, puis strip la ponctuation décorative de bordure de chaque mot-clé (sans quoi un mot-clé comme `Qwen…` ne matcherait même pas son propre texte).
- **`sans_accents(texte)`** — utilitaire partagé avec `filter.py` (même normalisation pour l'analyse du profil et pour le scoring).

### 10.7 `src/veille/filter.py` — le plus gros module : signal, scoring, quotas (FR-4/5/6)

Trois mécanismes indépendants, dans cet ordre d'exécution (voir §3) :

**1. Seuil de signal** — `filtrer_par_signal(items, sources)` écarte un item dont le `signal` est sous le `seuil_signal` de sa source. Deux garde-fous : une source sans seuil laisse tout passer (jamais implicite) ; un item **sans signal** face à une source qui en déclare un est conservé (l'absence de donnée n'est pas une insuffisance). `_avertir_seuils_inertes` signale un seuil qui ne peut rien filtrer (source dont aucun item ne porte de signal — RSS/scrape, ou JSON sans `mapping.signal`). Rapport : `RapportFiltrageSignal` (par source).

**2. Scoring par profil** — `scorer(item, profil, ponderations) -> Score` : recherche de mots-clés sur titre + contenu, insensible casse/accents, sur mot entier tolérant au singulier/pluriel (`_contient_mot_cle`, `s` final optionnel, frontières conditionnelles qui ne s'ancrent que contre un caractère alphanumérique). Deux règles de cumul (tranchées en revue Story 1.4) : un thème compté dans deux catégories du profil ne compte qu'une fois (au poids le plus fort), et les mots-clés suivants d'une même catégorie sont atténués (`_ATTENUATION_PAR_RANG = 0.5` : ½, ¼…). `classer(items, profil, ponderations) -> list[ItemScore]` score tout, écarte sous `seuil_bruit`, trie par score décroissant (tri stable — égalité de score préserve l'ordre d'arrivée). `charger_ponderations(chemin) -> Ponderations` lit `config/scoring.yaml` : repli par valeur (une clé invalide ne réinitialise pas les autres), rejette les clés inconnues (`_avertir_cles_inconnues`) et les valeurs falsy mal typées. Rapport : `RapportClassement`/`rapport_classement` (diff par identité d'objet entre l'entrée et la sortie de `classer`).

**3. Quotas par registre** — `repartir_par_quotas(classement, quotas) -> list[ItemScore]` : un seul passage sur un classement déjà trié (`classer()` l'a fait), compteur par registre, jamais de second tri. Un registre absent de `Quotas` est conservé sans limite (même principe que le signal absent). `charger_quotas(chemin) -> Quotas` : même patron exact que `charger_ponderations`. Rapport : `RapportQuotas`/`rapport_quotas` (par registre, plus un détail interne `ecartes_par_source` pour le diagnostic « source absorbée » de `collect.py`).

Utilitaires partagés entre les trois mécanismes : `_ventilation(comptes)` (formatage `"clé (-n)"` générique, utilisé par les trois rapports) et `_avertir_cles_inconnues` (partagé entre `charger_ponderations` et `charger_quotas`).

### 10.8 `src/veille/collect.py` — l'orchestrateur

- **`CONNECTORS`** — table de dispatch `type → fetch`, seul point à modifier pour ajouter un connecteur.
- **`RapportSource`** — par source : `nb_items` (collecté) vs `nb_retenus` (contribution finale au digest, agrégeant dédoublonnage + seuil de signal + scoring + quotas). `est_muette` (zéro item sans erreur) et `est_absorbee` (a collecté mais rien n'a survécu) sont des diagnostics distincts d'`echec` (une vraie erreur).
- **`ResultatCollecte`** — `items` (liste finale), un rapport par mécanisme (`dedoublonnage`, `filtrage_signal`, `classement`, `quotas`), `profil_neutre` (alerte si le profil n'a aucun mot-clé). `resume()` produit un récapitulatif texte auto-suffisant : total collecté vs retenu dès qu'ils diffèrent, détail de chaque mécanisme qui a écarté quelque chose.
- **`collecter(sources_path, profil_path, scoring_path, quotas_path)`** — la fonction centrale. Charge les sources (isolé, AD-6), collecte chaque source (`_fetch_one`, isolé par source), puis enchaîne signal → dédoublonnage → scoring → quotas dans cet ordre exact. Les 4 chemins de configuration sont résolus **à l'appel**, pas à l'import — ce qui permet à `tests/conftest.py` de les substituer sans toucher au code.
- **`run(sources_path)`** — enveloppe fine : `collecter(...).items`, pour les appelants qui ne veulent que la liste.
- **`_journaliser`** — publie le récapitulatif en `INFO` (réellement visible en prod), et pour chaque source absorbée, nomme **toutes** les causes possibles (doublons / seuil de signal / bruit du profil / quota dépassé) plutôt que d'en présumer une seule.

### 10.9 Fichiers de configuration

- **`config/sources.yaml`** — 4 sources aujourd'hui : `openai-news` (RSS, `ce_qui_bouge`), `huggingface-blog` (RSS, `apprendre`), `hf-daily-papers` (JSON, `apprendre`, `seuil_signal: 15`), `anthropic-news` (scrape, `ce_qui_bouge`). **Aucune source en `pour_le_metier`** (dette, §8).
- **`config/profil.md`** — profil de filtrage d'Abdoulaye : 5 sections de mots-clés (`Thèmes prioritaires`, `Signal fort`, `Domaines d'application`, `Thèmes secondaires`, `Bruit`) + une section `Posture` (prose, ignorée par le parseur). Réécrite en Story 1.5 (revue) pour que la section Bruit ne contienne que des mots-clés atomiques, pas des phrases.
- **`config/scoring.yaml`** — pondérations : `prioritaire: 10`, `signal_fort: 15`, `domaine: 5`, `secondaire: 2`, `bruit: -20`, `seuil_bruit: -5`.
- **`config/quotas.yaml`** — quotas : `apprendre: 3`, `ce_qui_bouge: 3`, `pour_le_metier: 2`.

### 10.10 Tests

221 tests, aucun appel réseau (fixtures locales pour tout ce qui touche le réseau réel). `tests/conftest.py` neutralise `profil.md`/`scoring.yaml`/`quotas.yaml` par défaut pour tous les tests (fixture `autouse`), afin qu'aucun test ne dépende implicitement de la configuration de production.

| Fichier | Périmètre | ~Tests |
|---|---|---|
| `test_models.py` | `Item`, validation de `date_publication` | 5 |
| `test_config.py` | `load_sources`, validation de `seuil_signal` | 11 |
| `test_socle_reel.py` | Garde-fous sur les fichiers de config **réels** (`sources.yaml`, `scoring.yaml`, `quotas.yaml`) | 14 |
| `test_rss_connector.py` | Connecteur RSS | 6 |
| `test_json_connector.py` | Connecteur JSON, extraction du signal | 8 |
| `test_scrape_connector.py` | Connecteur scraping, `robots.txt` | 9 |
| `test_dedup.py` | Dédoublonnage unitaire | 20 |
| `test_dedup_regressions.py` | Régressions de la revue Story 1.3 | 16 |
| `test_profil.py` | Parseur de profil, robustesse aux éditions manuelles | 28 |
| `test_filter.py` | Signal, scoring, quotas — le plus gros fichier | 64 |
| `test_collect.py` | `run()`, cas d'erreur de haut niveau | 7 |
| `test_rapport_collecte.py` | Observabilité (`RapportSource`, états muette/échec) | 6 |
| `test_collecte_integration.py` | **Chemin réel** config → `collecter()` → rapport, pour chaque mécanisme | 25 |

## 11. Prochaine étape

**Story 1.6 — Générer une accroche en français pour chaque entrée** (frontière LLM unique, AD-7 : un seul module `enrich.llm` appelle l'API Claude Haiku ; aucun autre module ne doit l'appeler). À lancer via `bmad-create-story` (elle n'est pas encore rédigée en détail dans `implementation-artifacts/`) puis `bmad-dev-story`, revue via `bmad-code-review`.

Points d'attention déjà identifiés pour les stories à venir (§7, §8) :
- **Story 1.6** : `Score.motifs` existe déjà (calculé par `filter.py`) mais n'est consommé par rien — pourrait nourrir l'explicabilité de l'accroche, à évaluer.
- **Epic 2** : le registre `pour_le_metier` est structurellement vide dans le socle actuel — une source emploi/carrière le comblerait.
- **Story 1.8** : `pipeline.py` (orchestrateur dédié, AD-1) et l'échappement de `contenu_brut` au rendu.
