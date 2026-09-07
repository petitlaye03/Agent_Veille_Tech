# Rapport de projet — Agent de veille tech

> **Ce document est vivant.** Il est mis à jour à la fin de chaque story (dev
> + revue de code), pour qu'on puisse toujours reconstituer d'où on part,
> même après une longue coupure — et pour servir de référence technique
> fichier par fichier, pas seulement de suivi d'avancement. Ne pas le
> laisser dériver : chaque section doit refléter le dernier état réel du
> code, pas un instantané figé. La §10 (Référence technique) en particulier
> doit être corrigée dès qu'un fichier qu'elle décrit change de comportement.
>
> **Dernière mise à jour :** 2026-09-07, fin de la Story 2.3 (dev + revue).
> **Story courante :** aucune (2.3 terminée, `done` — **Epic 2**, 3/4 stories faites).
> **Prochaine étape :** Story 2.4 (dédoublonner à l'échelle du socle complet) — voir §11.

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

Depuis la Story 1.6, le module d'accroche (`enrich/llm.py`, AD-7) existe ; depuis la Story 1.7, ce même module porte aussi la détermination de l'entrée recommandée du jour (FR-8, déterministe, sans appel API). Depuis la Story 1.8, les deux sont branchés dans un run réel : `pipeline.py` (AD-1) enchaîne `collecter()` → `enrichir()` → `marquer_recommandation()` → `rendre()`/`publier()` (page HTML), un seul point d'entrée (`uv run python -m veille.pipeline`). **Depuis la Story 1.9**, ce même point d'entrée publie aussi l'archive Markdown datée du jour (`rendre_markdown()`/`publier_archive()`, FR-10) — page et archive à partir du même relevé d'horloge, chacune tentée indépendamment de l'autre. Le pipeline complet, de la collecte à la double publication (page + archive), existe donc pour la première fois — même si la publication réelle contre GitHub reste non validée faute du second dépôt de sortie (voir §8, §9).

### Décisions structurantes (AD-1 à AD-11)

Document de référence : [ARCHITECTURE-SPINE.md](../_bmad-output/planning-artifacts/architecture/architecture-agent-veille-emploi-ia-2026-07-24/ARCHITECTURE-SPINE.md).

| AD | Règle | État |
|---|---|---|
| AD-1 | Paradigme pipeline ; aucune dépendance ne remonte, seul l'orchestrateur ordonne | 🟡 Partiellement résolu (Story 1.8) — `pipeline.py` existe désormais comme point d'entrée unique (collecte → enrichissement → rendu → publication). `collect.py` continue cependant d'orchestrer en interne 4 étapes (collecte, dédup, filter, quotas), décision délibérée pour ne pas toucher à du code déjà testé sans AC qui l'exige (voir §6.8) |
| AD-2 | Connecteurs derrière `Connector.fetch() -> list[Item]`, un module par type | ✅ RSS, JSON, scrape |
| AD-3 | Sources et Profil en configuration, jamais en dur | ✅ `sources.yaml`, `profil.md`, `scoring.yaml`, `quotas.yaml` |
| AD-4 | `Item` = forme interne canonique | ✅ 9 champs depuis l'amendement du 2026-08-27 (ajout de `signal`, voir §7.6) |
| AD-5 | SQLite, propriétaire unique de l'état | ⏳ Pas encore construit — prévu quand une story en aura réellement besoin (dédup cross-nuit Story 3.4, santé des sources Epic 4) |
| AD-6 | Isolation des pannes par source, jamais d'exception qui interrompt le run | ✅ Éprouvé en conditions réelles (Story 1.2) et durci à plusieurs reprises en revue. **Depuis la Story 2.2**, `rss_connector.py` applique enfin un timeout réseau explicite (dernier des 3 connecteurs à en manquer) et une panne HTTP y devient une vraie `échec`, plus une source « muette » indiscernable — et une nuit à >50 % de sources en panne réseau/HTTP est désormais détectée et journalisée (`ResultatCollecte.anomalie_pannes`) |
| AD-7 | Frontière LLM unique (`enrich.llm`, Claude Haiku) | ✅ Construit (Story 1.6, FR-7 : accroches) et étendu (Story 1.7, FR-8 : recommandation) — `enrich/llm.py`, seul point d'appel API vérifié mécaniquement (`grep`). **Branché dans un run réel depuis la Story 1.8** (`pipeline.py`), mais toujours pas validé contre l'API véritable (aucune clé fournie) — voir §8 |
| AD-8 | Publication par commit git vers GitHub Pages | 🟡 Construit (Story 1.8 : page HTML ; Story 1.9 : archive Markdown datée) — `publish.py`, via l'API Contents GitHub vers un **second dépôt public dédié** (variante explicitement anticipée par le Structural Seed, le dépôt de code reste privé). Page et archive partagent le même dépôt, comme l'exige la règle. Testé et validé en dégradation (sans jeton), **pas encore validé contre l'API réelle** : le dépôt de sortie n'a pas encore été créé (action réelle sous le compte d'Abdoulaye, différée) — voir §8, §9 |
| AD-9 | Idempotence du job nocturne (upsert par date) | 🟡 Le mécanisme d'upsert existe et est exercé (Story 1.9) — `publier_archive` écrase l'archive existante d'une même date via son `sha` plutôt que d'en créer une seconde. L'ordonnancement nocturne lui-même (déclencheur, reprise après échec) reste Epic 3 |
| AD-10 | Aucune source en violation de CGU ; `robots.txt` vérifié avant scraping | ✅ Vérification runtime implémentée (Story 1.2, seconde passe de revue). Secrets en `.env` (Story 1.6) : vérifié gitignoré, aucune fuite dans le dépôt |
| AD-11 | « Déjà vu » validé seulement après publication réussie | ⏳ Epic 3 |

**Stack :** Python 3.11 · uv · feedparser · httpx · beautifulsoup4 · PyYAML · Jinja2 3.1.6 (Story 1.8) · SQLite stdlib (à venir) · `anthropic` 1.2.0 (0.119.0 visé à l'origine — dérive de version sans impact constaté, voir §10.9) · `python-dotenv`.

## 4. Méthode de travail

Projet mené en méthode **BMAD** : brief → PRD → architecture → epics/stories → dev → revue, tous les artefacts vivant sous `_bmad-output/`.

**Convention actée le 2026-08-27** : tout le cycle de développement passe systématiquement par les skills BMad dédiés, jamais en freestyle :
- créer une story → `bmad-create-story`
- coder une story → `bmad-dev-story`
- revue de code → `bmad-code-review`

**Revue de code** : trois couches adversariales en parallèle (Blind Hunter, Edge Case Hunter, Acceptance Auditor), triage manuel avant d'agir. Le modèle utilisé pour la revue a varié selon la story (Opus 5 pour la 1.4, Sonnet 5 — même modèle que l'implémentation — pour les 1.5 et 1.6, sur demande explicite d'Abdoulaye) : la recommandation par défaut reste un modèle différent de celui qui a implémenté, mais ce n'est pas une règle absolue.

## 5. État d'avancement — vue d'ensemble

| Epic | Contenu | État |
|---|---|---|
| **Epic 1** | Un premier digest, réel, bout en bout (3-5 sources) | ✅ **Terminé** — Stories 1.1-1.9 toutes `done` |
| **Epic 2** | Socle élargi (15-20 sources) et robustesse aux pannes | 🟡 En cours — Stories 2.1/2.2/2.3 `done`, 2.4 à faire |
| **Epic 3** | Génération nocturne automatique | ⏳ Pas commencé |
| **Epic 4** | Santé des sources et découverte de nouvelles sources | ⏳ Pas commencé |

### Détail Epic 1

| Story | Titre | Statut | Tests |
|---|---|---|---|
| 1.1 | Collecte d'une première source RSS | ✅ `done` | 20 |
| 1.2 | Connecteurs API JSON et scraping | ✅ *(fichier dit `review` ; travail de revue en réalité terminé — voir note ⚠️ ci-dessous)* | 31 → 44 |
| 1.3 | Dédoublonnage inter/intra-source | ✅ *(idem — `review` au frontmatter, revue terminée)* | 70 → 97 |
| 1.4 | Filtrage par signal + scoring par profil | ✅ `done` | 147 → 189 |
| 1.5 | Quotas par section (Apprendre/Ce qui bouge/Pour le métier) | ✅ `done` | 213 → 221 |
| 1.6 | Accroches en français (frontière LLM) | ✅ `done` | 235 → 242 |
| 1.7 | Signaler les entrées à ne pas manquer | ✅ `done` | 260 → 263 |
| 1.8 | Publier une page à URL fixe (rendu + publication + `pipeline.py`) | ✅ `done` | 291 → 299 |
| 1.9 | Archiver chaque digest en Markdown | ✅ `done` | 314 → **323** |

> ⚠️ **Note d'hygiène à traiter** : les fichiers de story 1.2 et 1.3 portent encore `Status: review` dans leur frontmatter, alors que leurs Change Log respectifs démontrent une revue menée et conclue (correctifs appliqués, suites vertes). Seules les Stories 1.4 et 1.5 ont été explicitement repassées à `done`. À corriger mécaniquement (`review` → `done`) la prochaine fois qu'on touche à ces fichiers.

### Détail Epic 2

| Story | Titre | Statut | Tests |
|---|---|---|---|
| 2.1 | Étendre le socle aux 15-20 sources visées | ✅ `done` | 323 → **324** |
| 2.2 | Continuer à fonctionner quand une source tombe en panne | ✅ `done` | 324 → **335** |
| 2.3 | Respecter les sources sensibles au débit | ✅ `done` | 335 → **350** |

**Total tests actuel : 350, tous verts** (`uv run pytest`).

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

### 6.6 — Story 1.6 : accroches en français (frontière LLM unique)

Première story à appeler un service payant réel. `Entree` (type minimal : `item` + `accroche`) dans `models.py` ; `src/veille/enrich/llm.py` (AD-7) : `_client()`, `generer_accroche()`, `enrichir()`. Deux décisions produit tranchées avec Abdoulaye **avant** de coder (comme l'amendement AD-4 en Story 1.4) : un item dont l'accroche échoue est conservé avec son titre original en repli plutôt qu'écarté (un créneau de quota déjà rare ne doit pas disparaître pour une panne transitoire) ; la validation réelle contre l'API est différée faute de clé, signalée comme telle plutôt que simulée. 235 tests, statut `review`.

**Revue de code (Sonnet 5, même modèle que l'implémentation)** : aucune décision produit cette fois, mais 11 correctifs bien réels sur un module neuf face à un service externe. Les plus consé­quents : une clé API composée uniquement d'espaces était acceptée comme valide (chaque item aurait alors déclenché un appel voué à l'échec au lieu de l'unique avertissement voulu) ; `generer_accroche(...) or item.titre` renvoie `''` — pas `None` — quand le titre est lui-même vide (`None or "" == ""` en Python), corrigé par un dernier repli non vide ; une réponse tronquée par `max_tokens` en plein mot était publiée comme accroche valide, `stop_reason` n'étant jamais vérifié ; une panne API systémique aurait produit jusqu'à ~240 tracebacks quasi identiques, sans la déduplication déjà appliquée au cas « clé absente » ; le client était reconstruit à chaque item plutôt que résolu une fois ; aucun garde-fou contre l'injection de contenu tiers (RSS, scraping) dans le prompt.

Et deux corrections sur mes propres affirmations, dans la continuité directe de la leçon #14 (§7) : j'avais écrit avoir « vérifié que l'API anthropic 1.2.0 est équivalente à 0.119.0 » alors que 0.119.0 n'a jamais été installée pour comparaison — seule l'API de la version réellement installée a été inspectée. Et mes propres chiffres de tests étaient faux dans le Dev Agent Record (« 223 avant, 12 nouveaux » vs la réalité 221 avant, 14 nouveaux) — repéré et corrigé par le relecteur via `git stash` + `pytest --collect-only`.

11 correctifs, 1 report (état de module pas scopé « par run », sans conséquence tant qu'aucun autre code n'appelle `enrich.llm`), 1 rejet. 235 → 242 tests. Détail complet : [1-6-accroches-francaises.md](../_bmad-output/implementation-artifacts/1-6-accroches-francaises.md).

### 6.7 — Story 1.7 : signaler les entrées à ne pas manquer (recommandation, FR-8)

Ajout de `recommandee: bool = False` à `Entree` (`models.py`) et de `marge_recommandation: float = 10.0` à `Ponderations` (`filter.py`, lu à la racine de `scoring.yaml`, même emplacement que `seuil_bruit`). Deux nouvelles fonctions dans `enrich/llm.py` — `determiner_recommandation(classement, ponderations) -> ItemScore | None` et `marquer_recommandation(entrees, classement, ponderations) -> list[Entree]` — qui **n'appellent jamais l'API** : la recommandation est purement déterministe, sur le `Score.valeur` déjà calculé par `filter.py` (Story 1.4), pas un second jugement LLM. Règle : le premier item du classement (déjà trié, jamais retrié ici) est recommandé s'il dépasse le second d'au moins `marge_recommandation` ; sinon, ou avec moins de deux items, personne ne l'est.

**Décision de conception actée avant le code** : `marquer_recommandation` est une fonction **additive**, appliquée après `enrichir()` (Story 1.6), plutôt qu'une extension de sa signature — pour ne courir aucun risque de régression sur les 19 tests de la Story 1.6 (FR-7 génère un texte par appel API, un item à la fois ; FR-8 compare des scores déjà connus, sur tout le lot, sans jamais toucher le réseau : ce ne sont pas la même responsabilité malgré la même ligne dans la table de couverture de l'architecture).

Task 5 (validation) a reproduit **la même lacune qu'aux Stories 1.4 et 1.5**, une troisième fois : un audit par mutation à 4 mutants a laissé passer la suppression de `marge_recommandation` de `config/scoring.yaml` sans le moindre test en échec (260 passed), parce que le défaut codé en dur (10.0) coïncide exactement avec la valeur déclarée dans le fichier. Comblé par une assertion de présence explicite de la clé dans le fichier réel (`test_socle_reel.py`), qui a elle-même dû être durcie en revue (voir plus bas).

**Revue de code (Sonnet 5, même modèle que l'implémentation)** — les 3 couches adversariales ont convergé **indépendamment** sur le même constat le plus sérieux : `marge_recommandation` n'était protégée par aucun garde-fou de signe. Une valeur nulle ou négative dans `config/scoring.yaml` aurait forcé une recommandation *tous les jours*, y compris à égalité exacte des scores — contradiction directe avec l'AC2 (« égalité jamais recommandée »), le même risque structurel qu'un `seuil_bruit`/`bruit` négatif mais qui, eux, sont *légitimement* négatifs. Corrigé par un paramètre `positif_strict` sur `_ponderation`, activé seulement pour `marge_recommandation`.

5 autres correctifs, tous mineurs : un caveat de précondition d'identité manquant sur `marquer_recommandation` (repris de `rapport_classement`/`rapport_quotas` sans leur mise en garde documentée) ; un test « sans affecter le reste » qui ne vérifiait en réalité qu'un seul champ ; le chemin « listes désynchronisées » documenté mais jamais testé ; le garde-fou de présence de `marge_recommandation:` (ajouté en Task 5, cf. ci-dessus) qui matchait aussi une ligne mise en commentaire, désormais ancré en début de ligne ; une précision de câblage ajoutée en docstring pour la Story 1.8 (le classement à passer est celui filtré par quota, pas le classement brut — un gagnant écarté par quota n'a aucune `Entree` à marquer).

6 correctifs, 0 report, 8 rejets — dont un faux positif du Blind Hunter (n'a pas trouvé le fichier de story, qui existe bien mais est gitignored sous `_bmad-output/`) et un risque de virgule flottante vérifié infondé (`_ATTENUATION_PAR_RANG = 0.5` dans `classer()` est une puissance de deux exacte, donc les scores restent exactement représentables en binaire pour les poids entiers en jeu). 260 → 263 tests. Détail complet : [1-7-recommandation-entree.md](../_bmad-output/implementation-artifacts/1-7-recommandation-entree.md).

### 6.8 — Story 1.8 : publier une page à URL fixe (rendu, publication, `pipeline.py`)

La plus grosse story depuis la 1.4, et la première à toucher trois nouveaux modules d'un coup. `render.py` (Jinja2) rend la page HTML — palette et typographie explicites, mobile-first, thème sombre automatique (`prefers-color-scheme`), trois sections dans l'ordre canonique des quotas, marque visuelle sur l'entrée recommandée, message honnête si le digest est vide. `publish.py` publie via l'API Contents de GitHub. `pipeline.py` enchaîne enfin collecte → enrichissement → rendu → publication en un seul point d'entrée, fermant une partie de la tension AD-1 suivie depuis la Story 1.4.

**Décision produit prise avec Abdoulaye avant de coder** : GitHub Pages ne fonctionne pas sur un dépôt privé sans plan payant. Abdoulaye a choisi, parmi plusieurs options présentées, un **second dépôt GitHub public, dédié uniquement à la page publiée** — le code et les stories restent privés dans `Agent_Veille_Tech`. Ce choix ne contredit pas l'architecture : le Structural Seed anticipait déjà cette variante (« `site/` peut être un sous-module ou un repo distinct »). Simplification additionnelle actée pendant l'implémentation : plutôt que d'imposer à Abdoulaye la création immédiate d'un jeton d'accès personnel dédié, `publish.py` réutilise d'abord sa session `gh` déjà authentifiée localement (`gh auth token`), `GITHUB_TOKEN` en `.env` restant une option.

Deux dettes techniques fermées au passage, toutes deux explicitement fléchées vers cette story lors des revues précédentes : `ResultatCollecte` expose désormais `resultats_repartis` (le classement filtré par quota, jusque-là calculé puis jeté par `collect.py` — dette suivie depuis la Story 1.4) ; un `titre`/`url` vide ne produit plus un rendu visiblement cassé (repli sur l'accroche, pas de lien vers nulle part).

**Revue de code (Sonnet 5, même modèle que l'implémentation)** — les 3 couches ont convergé indépendamment sur deux constats sérieux. Le premier : `Item.url` (contenu de source externe non fiable) pouvait porter un schéma `javascript:`/`data:` — l'autoescaping HTML de Jinja2 neutralise les métacaractères mais ne valide jamais le **schéma** d'une URI ; un flux RSS compromis aurait donc pu produire un lien cliquable exécutable sur la page publiée, malgré l'échappement actif et malgré l'AC dédié à la sûreté du rendu. Corrigé par un garde-fou de schéma (`http(s)` uniquement, insensible à la casse). Le second : `digest_vide` était calculé sur la liste d'entrée reçue, pas sur le contenu réellement rendu — un registre mal orthographié dans `sources.yaml` (une simple faute de frappe, pas un cas théorique : `repartir_par_quotas`, Story 1.5, conserve sans limite un registre qu'il ne reconnaît pas) aurait fait disparaître une entrée sans déclencher le message honnête attendu quand rien n'est à afficher — la page aurait semblé cassée plutôt que vide. Corrigé, et le registre inconnu est désormais journalisé plutôt que silencieusement perdu.

5 autres correctifs : un filet de sécurité de dernier recours ajouté autour de `pipeline.executer()` (`rendre()` était la seule étape du pipeline sans garantie propre de non-levée) ; un code de sortie ajouté à `main()` (sinon aucun moyen pour un futur planificateur de détecter une nuit en échec) ; `_sha_existant` (`publish.py`) qui confondait tout code d'erreur HTTP non-200 avec « fichier absent », masquant une vraie panne (jeton invalide, quota épuisé) derrière un rejet générique de l'API ; des type hints ajoutés à `pipeline.executer()` ; et `.env.example` réellement mis à jour (le plan de la story l'annonçait, ce n'était pas fait).

8 correctifs, 0 report, 5 rejets — dont le bandeau d'échec nocturne (explicitement hors périmètre, un état de run persistant n'existe pas encore) et la portée non restreinte du jeton `gh auth token` (compromis déjà assumé dans les Dev Notes). 291 → 299 tests. Détail complet : [1-8-publication-page.md](../_bmad-output/implementation-artifacts/1-8-publication-page.md).

### 6.9 — Story 1.9 : archiver chaque digest en Markdown (FR-10) — Epic 1 terminé

Dernière story de l'Epic 1. `render.rendre_markdown()` + `templates/digest.md.j2` produisent l'archive Markdown du jour, en réutilisant le regroupement par registre de la page HTML (`_grouper_par_registre`, extrait de `rendre()` en refactor pur) pour que les deux sorties ne divergent jamais. `publish.publier_archive()` publie à un chemin daté (`site/archive/YYYY-MM-DD.md`), avec le même mécanisme d'upsert par `sha` que la page (AD-9 : relancer pour la même date écrase, jamais un doublon). `pipeline.py` publie désormais la page et l'archive à partir du même relevé d'horloge par run.

Deux refactors purs vérifiés avant tout ajout (`_grouper_par_registre`, et `_publier`/`_sha_existant(chemin)` extraits de `publish.publier()`) : suite existante rejouée verte sans modification avant d'écrire le moindre code neuf.

**Revue de code (Sonnet 5, même modèle que l'implémentation)** — les 3 couches ont convergé sur un couple de constats dans des directions opposées, résolus par le même correctif. D'un côté, l'ensemble de caractères échappés en Markdown (`_echapper_markdown`) omettait `<` : un titre `<img src=x onerror=...>` de source externe restait une vraie balise HTML brute dans l'archive, contournant l'AC de sûreté malgré l'échappement des autres caractères. De l'autre, ce même ensemble échappait aussi `#`/`-`/`+`/`.` — syntaxiquement actifs seulement en tout début de ligne, jamais atteignable ici puisque le texte est toujours inséré au milieu d'une puce déjà ouverte — ce qui cassait l'AC dédié à la recherche par texte (« cherchable sur l'ensemble de l'historique ») pour un cas aussi banal qu'un nom de modèle versionné (`GPT-5.2`). Corrigé dans les deux sens à la fois : `<` ajouté, les quatre autres retirés, et les sauts de ligne incorporés neutralisés (nécessaire pour que ce retrait reste sûr — sans ça, un saut de ligne aurait pu replacer un `-`/`#` en tout début d'une nouvelle ligne, où il redevient actif).

Correctif de robustesse le plus significatif : `pipeline.executer()` affirmait que la page et l'archive sont « toujours tentées, même si l'une échoue » — vrai seulement pour un échec côté publication. Si `rendre_markdown()` levait après que `rendre()` a réussi, la page déjà produite avec succès était perdue faute d'avoir été publiée avant l'échec de l'archive. Corrigé en publiant la page immédiatement après son rendu, avant même de tenter de rendre l'archive — vérifié par mutation manuelle (contenus HTML/Markdown inversés entre les deux publications, un test durci de corrélation contenu↔chemin l'attrape).

4 autres correctifs : trace complète par catégorie (page/archive) au lieu d'un booléen global partagé (sinon le second échec du run perdait sa trace de diagnostic) ; `_url_surs` rejette aussi les chevrons littéraux (cassaient l'enveloppe `<...>` du lien Markdown) ; libellé de section échappé par cohérence défensive ; couverture de test étendue pour la parité HTML/Markdown.

9 correctifs, 0 report, 4 rejets — dont le doublon de l'avertissement « registre inconnu » (un correctif propre exigerait un changement disproportionné ou introduirait un bug pire) et le risque `.nojekyll` qui s'étend maintenant à l'archive (déjà suivi comme prérequis d'infrastructure, pas du code). 314 → 323 tests. Détail complet : [1-9-archive-markdown.md](../_bmad-output/implementation-artifacts/1-9-archive-markdown.md).

### 6.10 — Story 2.1 : étendre le socle aux 15-20 sources visées — Epic 2 démarré

Première story de l'Epic 2. Pure extension de configuration : `config/sources.yaml` passe de 4 à **17 sources** (13 ajoutées : 8 `apprendre`, 3 `ce_qui_bouge`, 2 `pour_le_metier`), toutes de types déjà implémentés (`rss`, `json`) — **aucune modification de `src/veille/`**, conformément à l'AC1. Les 13 URL candidates ont été vérifiées par requête réelle avant d'entrer dans le fichier (discipline établie depuis la Story 1.1) : une (Le Monde Informatique, proposée par l'addendum du brief) s'est révélée **404 réel**, remplacée par le flux général du même site.

**Dette fermée** : le registre `pour_le_metier`, structurellement vide depuis la Story 1.5 (aucune source ne le déclarait), reçoit ses deux premières sources (`decideo`, `lemonde-informatique`) — verrouillé par un nouveau garde-fou (`test_le_socle_couvre_le_registre_pour_le_metier`). Confirmé fonctionnellement fermé, pas seulement déclaratif : l'exécution réelle de Task 4 montre 2 items du registre atteignant effectivement le classement final.

**Deux écarts trouvés et corrigés pendant l'implémentation elle-même** (avant même la revue) :
- `hacker-news` ne pouvait pas prendre la `priorite: 0` prévue au plan initial (garde-fou existant `test_chaque_source_declare_une_priorite`, qui ne distingue pas priorité absente et priorité explicitement nulle) — corrigé par `priorite: 1`, sans toucher au test.
- `hacker-news` était **MUETTE** au premier passage d'exécution réelle contre le socle complet (Task 4) : la réponse Algolia est un objet `{"hits": [...]}`, pas une liste à la racine, et l'entrée ne déclarait pas `racine: hits` — corrigé en configuration pure.

**Exécution réelle contre les 17 sources (Task 4)** : 2800 items collectés, 8 retenus au digest final, **aucune source en échec** (AD-6 intact sur l'ensemble du socle élargi). Défaut trouvé et **non corrigé ici** (hors périmètre « sans modification de code » de l'AC1) : `rss_connector._to_utc_datetime` ne retombe jamais sur `updated_parsed` quand `published_parsed` est absent — mal-date silencieusement, en permanence, les items de 5 sources (4 dépôts GitHub + Le Monde Informatique, flux Atom purs/RDF) avec la date de collecte plutôt que la vraie date de publication. Sans conséquence de justesse aujourd'hui (tri par score, pas par fraîcheur), mais consequential dès l'Epic 3 (état « déjà vu »). Documenté en détail dans `deferred-work.md`.

**Revue de code (Sonnet 5, même modèle que l'implémentation)** — les 3 couches ont convergé sur le même défaut le plus sérieux (le bug `updated_parsed` ci-dessus, déjà trouvé et documenté par la story elle-même), confirmant qu'il n'y avait rien de caché. Constat nouveau, convergent (Blind Hunter + Acceptance Auditor) : l'URL Le Monde Informatique retenue en Task 1 (`.../rss/rss.xml`) répond en réalité par une **redirection 301** vers `.../flux-rss/rss.xml` (200) — la vérification `curl` de Task 1 avait suivi la redirection sans le signaler explicitement. Sans conséquence fonctionnelle (`httpx`/`feedparser` suivent les redirections), corrigé pour pointer directement sur la destination canonique. Second constat convergent : le commentaire d'en-tête partagé de `sources.yaml` ne documentait ni le piège `priorite: 0` ni le piège `racine` — corrigé, les deux sont maintenant dans la documentation partagée plutôt que seulement dans le commentaire inline d'une source.

4 correctifs, 1 report (le bug `updated_parsed`, déjà tracé), 2 rejets — dont la critique sur la priorité uniforme des 4 dépôts GitHub (déjà actée comme délibérée dans les Dev Notes). 323 → 324 tests. Détail complet : [2-1-etendre-le-socle.md](../_bmad-output/implementation-artifacts/2-1-etendre-le-socle.md).

### 6.11 — Story 2.2 : continuer à fonctionner quand une source tombe en panne

`rss_connector.py` était le seul des trois connecteurs sans timeout réseau explicite (dette suivie depuis la Story 1.1) : `feedparser.parse(url)` faisait sa propre récupération HTTP en interne, sans limite de temps, et une panne HTTP (403/429/500) était avalée dans le mécanisme `bozo` plutôt que remontée comme un échec — la source apparaissait « MUETTE » (zéro item, sans erreur), indiscernable d'un flux simplement vide. Cette story ajoute une fonction `_charger()` qui récupère elle-même le flux via `httpx` (`TIMEOUT_SECONDES = 30`, `raise_for_status()`, `User-Agent` explicite — même patron que `json_connector.py`/`scrape_connector.py`, sauf que la condition de branchement est nécessairement inversée) pour toute URL réseau, et passe le contenu récupéré à `feedparser.parse()` plutôt que l'URL elle-même. Le chemin local (chemins bruts, utilisés par tous les tests) reste strictement inchangé. Ferme au passage une seconde dette de la Story 1.1 (aucun `User-Agent` explicite envoyé).

**Nouveau signal (FR-2, AC4)** : `ResultatCollecte.taux_echec`/`anomalie_pannes` détectent une nuit où plus de la moitié des sources échouent par panne réseau/HTTP réelle (seuil strict, égalité à 50 % exclue) — `_journaliser` émet alors un journal `ERROR` agrégé nommant les sources concernées, sans jamais empêcher la production du digest. Portée délibérément limitée au journal (pas de bandeau sur la page publiée, qui suppose un état persistant — Epic 3, déjà tracé depuis la revue de la Story 1.8).

**Revue de code (Sonnet 5)** — 3 constats trouvés indépendamment par plusieurs couches, tous corrigés : le dispatch réseau/local de `_charger` utilisait `str.startswith` (sensible à la casse) plutôt que `urlparse(...).scheme` comme `scrape_connector.py` — un schéma `HTTP://` aurait silencieusement réintroduit la panne que cette story ferme ; `taux_echec` comptait une source au `type` mal orthographié (faute de configuration statique) comme une panne réseau, ce qui aurait pu déclencher à tort l'anomalie ; le journal `ERROR` d'anomalie ne nommait pas les sources concernées. Deux corrections de précision documentaire (le nouveau journal n'est pas le premier signal `ERROR` — chaque panne par source l'était déjà, juste noyée dans le détail — et le « patron » repris des deux autres connecteurs a une condition de branchement inversée par nécessité). Deux tests ajoutés pour combler des trous de couverture trouvés en revue : deux sources RSS dans le même run (une en panne, une vivante — jusque-là seulement testé RSS+JSON), et un test d'encodage reproductible (en-tête `Content-Type` menteur) remplaçant une vérification manuelle qui ne comparait que le nombre d'items, pas le contenu décodé.

7 correctifs, 1 report (redirections HTTP non plafonnées — motif préexistant aux 3 connecteurs, pas introduit ici), 6 rejets — dont le choix délibéré de ne pas compter les sources « muettes » dans l'anomalie (déjà explicite dans l'AC4) et la séquentialité du run (hors périmètre, Story 2.3). 324 → 335 tests. Détail complet : [2-2-continuer-en-panne.md](../_bmad-output/implementation-artifacts/2-2-continuer-en-panne.md).

### 6.12 — Story 2.3 : respecter les sources sensibles au débit

Aucune des 17 sources actuelles n'est aujourd'hui connue pour limiter le débit — Reddit, le cas le plus documenté par l'addendum du brief (« `.rss` → 429 dès la 3ᵉ requête, espacer de 5-8s minimum, prévoir un backoff exponentiel »), n'est pas dans ce socle (bloqué par une démarche OAuth de 2-4 semaines, hors périmètre). Cette story construit donc une capacité générale et réactive plutôt que d'attendre une vraie source rate-limitée : l'addendum lui-même le demande (« prévoir du backoff dès la v1 »), et le FR-2 du PRD le formule en toute généralité.

Nouveau module `src/veille/connectors/_reseau.py` (`get_avec_backoff`), partagé par les trois connecteurs plutôt que triplé — devenu possible précisément parce que la Story 2.2 avait déjà harmonisé les trois `_charger` sur le même patron `httpx.get(...) + raise_for_status()`. Retry uniquement sur `429` (jusqu'à 3 tentatives), respecte l'en-tête `Retry-After` du serveur (secondes) sinon un backoff exponentiel parti de 5s ; toute autre erreur HTTP lève immédiatement, sans retry. Branché sur les trois `_charger` (page/flux/API), jamais sur `scrape_connector._collecte_autorisee` (requête `robots.txt`, une seule fois par source et par nuit, déjà dégradée proprement sur toute exception). Au-delà des tentatives, un 429 persistant redevient une panne normale (`RapportSource.echec`), sans aucune modification de `collect.py` — l'isolation AD-6 existante suffit.

**Revue de code (Sonnet 5)** — les 3 couches ont convergé indépendamment sur le même constat le plus sérieux, avec une gravité croissante à chaque couche : `Retry-After` n'était ni plafonné ni protégé contre une valeur non finie. Un serveur pouvait légitimement renvoyer un délai de plusieurs heures, que la collecte strictement séquentielle aurait alors respecté en bloquant toutes les sources suivantes du socle pour cette durée — en tension avec l'esprit même de l'AC visant à ne jamais bloquer les autres sources. Plus grave : l'Edge Case Hunter a vérifié empiriquement qu'un `Retry-After: inf` (valeur Python valide via `float()`) faisait planter `time.sleep` (`OverflowError`), contredisant la propre promesse de la fonction. Corrigé par un plafond (`DELAI_MAX_SECONDES = 60`) et un rejet explicite des valeurs non finies (`math.isfinite`). Second constat convergent : le backoff n'était vérifié de bout en bout (avec un vrai 429 simulé) que pour `rss_connector.py`, jamais pour `json_connector.py`/`scrape_connector.py`, alors que l'AC affirme le mécanisme « partagé par les trois connecteurs » — deux tests d'intégration ajoutés pour fermer ce trou. Troisième constat : les nouveaux tests d'intégration ciblaient `rss_connector.httpx` par un couplage fragile (fonctionne seulement parce que `httpx` est un module singleton) plutôt que `_reseau.httpx` directement — reciblé, sans toucher aux tests **existants** de la Story 2.2 qui, eux, doivent continuer de fonctionner via ce même couplage documenté.

4 correctifs, 0 report, 6 rejets — dont l'absence de jitter sur le backoff (le problème qu'il résout, la contention entre clients concurrents, ne se pose pas dans une collecte strictement séquentielle) et le choix délibéré de ne pas brancher le backoff sur la requête `robots.txt`. 335 → 350 tests. Détail complet : [2-3-respecter-le-debit.md](../_bmad-output/implementation-artifacts/2-3-respecter-le-debit.md).

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
16. **Un item conservé plutôt qu'écarté sur panne, y compris pour l'enrichissement LLM** : même principe que la décision #13, étendu explicitement au-delà de la configuration — un item dont l'accroche échoue publie son titre original en repli plutôt que de disparaître (Story 1.6, décision actée avant le code).
17. **Un module qui appelle un service externe ne lève jamais, dégrade et journalise** — `_client()`/`generer_accroche` (Story 1.6) suivent le même réflexe que `charger_profil`/`charger_ponderations`/`charger_quotas` (décision #5) ; la déduplication du warning « une fois par run » doit couvrir *toutes* les pannes répétitives d'un même run, pas seulement celle envisagée en premier (trouvé en revue : la panne API systémique n'était pas dédupliquée alors que la clé absente l'était déjà).
18. **Un correctif sur une affirmation de son propre Dev Agent Record se traite comme un correctif de code** : dès qu'un chiffre ou une méthode de vérification citée s'avère inexacte ou plus forte que ce qui a réellement été fait, elle est corrigée avec la même rigueur qu'un bug — pas laissée comme un détail cosmétique (leçon #14 étendue au-delà des seules « exécutions réelles » : Story 1.6, chiffres de tests et affirmation d'équivalence de version SDK).
19. **Un prompt qui incorpore du contenu de sources externes non fiables porte une consigne explicite anti-injection**, même quand l'impact d'une injection réussie reste borné (ici : influencer le texte d'une accroche affichée, pas d'exécution d'outil ni d'exfiltration) — coût de la précaution nul, absence de précaution jamais neutre (Story 1.6).
20. **Deux responsabilités qui partagent la même ligne dans une table de couverture d'architecture ne sont pas forcément la même fonction** — FR-7 (accroche, un appel API par item) et FR-8 (recommandation, comparaison de scores sur tout le lot, jamais d'appel réseau) vivent toutes deux dans `enrich/llm.py`, mais dans des fonctions séparées et additives plutôt que par extension de signature — pour ne jamais risquer de régresser une fonction qui marche déjà (Story 1.7).
21. **Un seuil de configuration numérique nouvellement introduit doit être examiné pour son signe, pas seulement pour son type** — leçon distincte de la #14 (audit par mutation côté configuration) : `marge_recommandation` acceptait silencieusement 0 ou une valeur négative, ce qui aurait forcé une recommandation tous les jours y compris à égalité exacte, en contradiction avec l'AC qu'il est censé garantir. Trouvé indépendamment par les 3 couches de revue en même temps (Story 1.7) — signal fort qu'un contrôle de plage doit être un réflexe systématique pour tout nouveau seuil, pas seulement pour ceux qui, comme `bruit`/`seuil_bruit`, sont légitimement négatifs.
22. **L'échappement HTML neutralise les métacaractères, jamais le schéma d'une URI** — l'autoescaping Jinja2 rend un `<script>` inerte mais laisse passer tel quel un `href="javascript:..."` : tout champ destiné à devenir un lien cliquable doit voir son schéma validé explicitement (`http(s)` uniquement), en plus de l'échappement générique (Story 1.8, trouvé indépendamment par 2 des 3 couches de revue).
23. **Un indicateur de repli (« rien à afficher »/« digest vide »…) doit se calculer sur ce qui a été réellement produit, pas sur la non-vacuité de l'entrée** — `render.py` calculait `digest_vide` à partir de la liste d'`Entree` reçue plutôt que des sections effectivement peuplées après regroupement ; une entrée valide mais mal routée (registre inconnu) disparaissait alors sans déclencher le message honnête censé couvrir précisément ce cas (Story 1.8, constat convergent des 3 couches de revue).
24. **Un dépôt de sortie séparé, public, dédié uniquement à un artefact publié, est une variante d'architecture légitime** quand l'hébergement (ici GitHub Pages) ne fonctionne pas sur le dépôt de code resté privé pour de bonnes raisons — à condition que l'architecture l'ait anticipé (ce qu'`ARCHITECTURE-SPINE.md` faisait déjà) ou, sinon, que ce soit acté explicitement comme un amendement (Story 1.8).
25. **Réutiliser une session d'outil déjà authentifiée (`gh auth token`) en repli avant d'imposer un nouveau secret dédié** — réduit la friction de mise en route sans bloquer un futur passage à un jeton restreint (`GITHUB_TOKEN`, déjà prévu en option) quand le contexte d'exécution changera (ex. GitHub Actions, Epic 3) (Story 1.8).
26. **Échapper un texte de sortie n'est pas binaire : le bon ensemble de caractères dépend de la position syntaxique, pas seulement du format cible** — `#`/`-`/`+`/`.` ne sont actifs qu'en tout début de ligne en Markdown ; les échapper partout, y compris en milieu de texte où ils sont inertes, protège de rien de plus mais casse la lisibilité/recherche du texte produit. Un échappement mal calibré peut être à la fois trop permissif (un `<` oublié) et trop restrictif (une ponctuation commune neutralisée sans raison) **au même endroit** — les deux doivent être vérifiés ensemble, pas seulement « est-ce que c'est bien échappé » (Story 1.9, constat convergent des 3 couches de revue dans les deux sens à la fois).
27. **Neutraliser les sauts de ligne incorporés avant d'alléger un ensemble de caractères échappés en fonction de leur position** — retirer l'échappement de caractères seulement actifs en début de ligne (décision #26) n'est sûr que si le texte inséré ne peut pas lui-même introduire une nouvelle ligne qui les y replacerait ; `Item.titre`/`Entree.accroche` n'ont aucune garantie de contenu mono-ligne (Story 1.9).
28. **Publier le premier des deux artefacts indépendants dès qu'il est prêt, pas après avoir tenté de produire les deux** — `pipeline.executer()` rendait la page et l'archive avant de publier l'une ou l'autre ; un échec de rendu du second faisait perdre le premier, pourtant déjà réussi. Un filet de sécurité englobant ne compense pas un mauvais ordonnancement des effets de bord qu'il protège (Story 1.9).
29. **Un drapeau « une fois par run » qui protège deux occurrences logiquement distinctes doit être scindé par catégorie, pas partagé** — le même réflexe qui a dédupliqué un avertissement (décision implicite depuis la Story 1.6) peut, mal appliqué, supprimer la trace de diagnostic d'un second échec réellement nouveau simplement parce qu'un premier a déjà eu lieu dans le même run (Story 1.9 : trace complète par catégorie page/archive, pas un booléen global).
30. **Un défaut par dataclass rend une valeur explicite indiscernable d'une valeur absente** — `SourceConfig.priorite: int = 0` fait qu'un `0` écrit à dessein dans `sources.yaml` et un champ simplement omis produisent le même objet chargé ; un garde-fou qui interdit « 0 » ne peut donc interdire que les deux à la fois, jamais l'un sans l'autre. Une échelle de configuration documentée (ici : « 0 = agrégateur ») doit être vérifiée contre les garde-fous existants avant d'être utilisée telle quelle — pas seulement contre le schéma du type (Story 2.1).
31. **Vérifier une URL par requête réelle doit inclure le premier code de statut, pas seulement la destination finale après redirection** — `curl`/`httpx`/`feedparser` suivent les redirections par défaut, donc une vérification qui ne regarde que le contenu final peut affirmer « HTTP 200 confirmé » pour une URL qui répond en réalité 301. Sans conséquence fonctionnelle ici (les clients de ce projet suivent tous les redirections), mais l'affirmation elle-même était imprécise — et la config doit pointer sur la destination canonique, pas sur un alias qui dépend de la bonne volonté continue de l'éditeur à le maintenir (Story 2.1, trouvé indépendamment par 2 des 3 couches de revue).
32. **Un connecteur générique qui suppose une forme de réponse par défaut doit voir cette hypothèse documentée à l'endroit où elle se vérifie, pas seulement dans le code** — `json_connector.fetch` suppose une liste à la racine sauf si `racine` est déclaré ; l'absence de ce champ ne lève aucune exception, seulement un avertissement et une source silencieusement vide (0 item, sans échec visible ailleurs qu'un log). Trouvé uniquement par l'exécution réelle de Task 4, pas par la configuration déclarée ni par un test unitaire — confirme la leçon #14 (vérifier deux fois, en conditions réelles) pour la configuration autant que pour le code (Story 2.1).
33. **Reproduire un patron d'un module sœur exige de vérifier la condition de branchement, pas seulement l'intention** — `rss_connector._charger` reprend l'esprit de `json_connector._charger`/`scrape_connector._charger` (dispatch réseau/local, timeout explicite), mais avec une condition inversée (`http(s)://` → réseau, plutôt que `file://` → local), nécessaire parce que les tests RSS passent des chemins bruts sans schéma. Affirmer « même patron exact » aurait été trompeur — trouvé en revue, corrigé en documentant l'écart plutôt qu'en le masquant (Story 2.2).
34. **Une nuance de casse ou de format dans une comparaison de schéma d'URL peut rouvrir silencieusement un trou déjà fermé** — `str.startswith(("http://", "https://"))` est sensible à la casse et à un espace de tête, contrairement à `urlparse(...).scheme` (déjà utilisé par `scrape_connector._collecte_autorisee`) qui normalise les deux. Un `HTTP://` littéral aurait fait retomber une source réseau sur la branche « locale », réintroduisant pour cette URL l'absence de timeout que la story visait justement à corriger (Story 2.2, trouvé en revue).
35. **Un taux d'anomalie agrégé doit filtrer les causes qu'il ne doit pas compter, pas seulement réutiliser un compteur existant tel quel** — `anomalie_pannes` (Story 2.2) réutilisait d'abord `sources_en_echec` tel quel, qui inclut aussi bien une vraie panne réseau/HTTP qu'une source dont le `type` est mal orthographié (jamais tentée par un connecteur). Une réutilisation directe aurait laissé une simple faute de frappe de configuration se faire passer pour une nuit de panne réseau — corrigé par un filtre explicite (`type in CONNECTORS`) avant de calculer le taux (Story 2.2, trouvé en revue).
36. **Une vérification réelle qui ne compare que des comptes (nombre d'items, de lignes) peut manquer une régression de contenu** — la vérification réseau de la Story 2.2 (avant/après le passage à `httpx`) confirmait le même nombre d'items sur 3 sources réelles, mais n'aurait pas détecté un mauvais décodage silencieux qui préserve le compte (accents corrompus). Un test automatisé et reproductible (en-tête `Content-Type` menteur simulé) verrouille désormais le **contenu** décodé, pas seulement le compte — leçon complémentaire à la #14, qui portait sur la fraîcheur de la vérification, pas sur ce qu'elle mesure réellement (Story 2.2, trouvé en revue).
37. **Une valeur fournie par un tiers (en-tête HTTP, config externe) doit être validée sur sa plausibilité, pas seulement sur son type** — `float("inf")`/`float("1e300")` sont des valeurs Python parfaitement valides, mais `time.sleep()` plante sur la première et la seconde immobiliserait le run pour une durée déraisonnable ; `isinstance`/`try-except ValueError` ne suffisent pas à eux seuls, il faut aussi une borne explicite (`math.isfinite` + plafond) quand la donnée pilote une attente ou une ressource. Distinct de la leçon #14 (fraîcheur de la vérification) et de la #36 (ce qu'elle mesure) : ici, c'est la **plage de validité** qui manquait, pas la présence d'un contrôle (Story 2.3, trouvé en revue — confirmé empiriquement par l'Edge Case Hunter, qui a reproduit le plantage).
38. **Un mécanisme neuf partagé par plusieurs points d'appel doit être vérifié de bout en bout à travers chacun, pas seulement à travers le premier qui vient à l'esprit** — le backoff de la Story 2.3 était exhaustivement testé en isolation (`_reseau.py`) et à travers `rss_connector.py`, mais jamais à travers `json_connector.py`/`scrape_connector.py`, alors que l'AC affirmait explicitement le mécanisme « partagé par les trois connecteurs ». Une couverture unitaire complète du composant partagé ne remplace pas une couverture d'intégration par appelant (Story 2.3, trouvé en revue — convergence Blind Hunter + Acceptance Auditor).
39. **Un test qui ne fonctionne que grâce à un détail d'implémentation non garanti (ici : que deux modules important la même bibliothèque partagent le même objet singleton) doit cibler directement le point où l'effet a lieu, pas un raccourci qui marche par accident aujourd'hui** — les tests d'intégration ajoutés en Story 2.3 monkeypatchaient `rss_connector.httpx` en s'appuyant implicitement sur le fait que `httpx` est un module `sys.modules` partagé avec `_reseau.py` ; reciblés sur `_reseau.httpx` directement, la référence réellement appelée. Les tests **existants** de la Story 2.2, eux, continuent légitimement de s'appuyer sur ce couplage (documenté, vérifié, nécessaire pour ne pas les modifier) — la distinction est entre *découvrir* qu'un raccourci fonctionne et *choisir délibérément* de le garder pour une raison précise (Story 2.3, trouvé en revue).

## 8. Dette technique et travail reporté

Liste vivante complète : [deferred-work.md](../_bmad-output/implementation-artifacts/deferred-work.md). Résumé de ce qui reste ouvert, par destination :

**Epic 2 (socle élargi, robustesse)** — distinction 404 vs flux malformé, plafond de taille des réponses HTTP, mode d'extraction « carte » pour le scraping (titre/date en frères de l'ancre, pas en descendants — bloque l'ajout de la plupart des blogs WordPress), en-têtes/authentification pour les API JSON (bloque Kaggle, prévu au socle v1 mais toujours pas construit — la Story 2.1 a explicitement laissé Kaggle de côté pour cette raison), `url_modele` limité à `{guid}`.

**Dette fermée en Story 2.1** : ~~`config/sources.yaml` ne déclare aucune source en registre `pour_le_metier`~~ — 2 sources ajoutées (`decideo`, `lemonde-informatique`), la 3ᵉ section du digest reçoit désormais des items réels.

**Dette fermée en Story 2.2** : ~~timeout réseau absent sur `feedparser`/`rss_connector.py`~~ — `TIMEOUT_SECONDES = 30` + `User-Agent` explicite ajoutés (même patron que les deux autres connecteurs) ; ~~une panne HTTP sur une source RSS est avalée par `bozo`, remonte comme « muette » plutôt qu'« échec »~~ — corrigé, `RapportSource.echec` porte désormais la vraie cause.

**Dette fermée en Story 2.3** : ~~retry/backoff sur 429~~ — `src/veille/connectors/_reseau.py` (`get_avec_backoff`), partagé par les trois connecteurs.

**Trouvé en Story 2.2, reporté** :
- **`httpx.get(..., follow_redirects=True)` n'impose aucune limite au nombre/à la durée totale des sauts de redirection**, sur les trois connecteurs (`json_connector.py`, `scrape_connector.py`, `rss_connector.py` depuis cette story). Le `timeout` de 30s borne chaque opération réseau, pas la chaîne complète de redirections d'une même source — atténue partiellement l'objectif « ne doit plus pouvoir bloquer indéfiniment ». Motif préexistant aux 3 connecteurs, pas introduit par cette story.

**Trouvé en Story 2.3, non corrigé (déjà hors périmètre, mais à surveiller)** :
- **Aucun retry/backoff sur `503`** (autre code souvent utilisé pour signaler une surcharge transitoire) — l'AC de cette story ne parle que de `429`, élargir sans cas d'usage documenté aurait été spéculatif.
- **Pas de jitter sur le backoff exponentiel** — sans conséquence tant que la collecte reste strictement séquentielle (le problème que le jitter résout — la contention entre clients concurrents sur le même hôte — ne se pose pas ici) ; à reconsidérer si la collecte devient un jour parallèle/concurrente (aucun plan actuel en ce sens).
- **`scrape_connector._collecte_autorisee` (requête `robots.txt`) n'est pas couverte par le backoff** — décision délibérée (une requête par source et par nuit, dégradation déjà propre sur toute exception y compris un 429), mais signifie qu'un domaine réellement en train de limiter le débit reçoit quand même cette requête non protégée juste avant la requête de page, elle protégée.

**Trouvé en Story 2.1, reporté** :
- **`rss_connector._to_utc_datetime` ne retombe jamais sur `updated_parsed` quand `published_parsed` est absent** — mal-date silencieusement, en permanence (pas seulement une nuit), les items des flux Atom purs et RDF (4 dépôts GitHub + Le Monde Informatique, 5/17 sources du socle actuel). Sans conséquence de justesse aujourd'hui (tri par score, pas par fraîcheur), mais consequential dès qu'une logique s'appuiera sur la date réelle (état « déjà vu » de l'Epic 3). Hors périmètre de la Story 2.1 (« sans modification de code ») — correctif proposé : replier sur `entry.get("updated_parsed")` avant le retour par défaut à `datetime.now()`.
- **`pour_le_metier` ferme la dette de présence, mais son rendement réel reste faible** — sur l'unique exécution réelle documentée, seul `decideo` a contribué au digest (`lemonde-informatique` : 20 collectés, 0 retenus, écarté comme bruit du profil). `config/profil.md` (vocabulaire dense en ingénierie ML/LLM) est probablement mal aligné lexicalement avec la presse IT généraliste FR — à surveiller si le registre reste creux sur plusieurs nuits une fois le pipeline nocturne actif (Epic 3), pourrait justifier un enrichissement ciblé de `profil.md` plutôt qu'une nouvelle source.
- **Le seuil `seuil_signal: 250` de Hacker News n'a produit aucun item retenu sur l'unique exécution réelle documentée** (20 collectés, 0 retenus) — cohérent avec le mécanisme, pas nécessairement avec la tendance « ~5 items/jour » de l'addendum du brief mesurée sur un tirage différent. Un seul relevé ne suffit pas à confirmer ou invalider le réglage ; à réévaluer une fois l'Epic 3 en place (plusieurs nuits consécutives).
- **OpenRouter (signal marché, addendum) n'a pas été ajouté** — ne nécessite aucune authentification, mais sa valeur documentée (diff quotidien des `id` de modèles) suppose un état persistant jour-sur-jour que ce projet n'a pas encore (`store.py`/SQLite, Epic 3). Collecter sans diffing produirait du bruit, pas du signal.
- **`datagen-podcast` (312 entrées) et `eugene-yan` (212 entrées) renvoient l'intégralité de leur archive à chaque run**, pas seulement les récents — amplifie la limitation déjà connue (pas d'état « déjà vu » persistant) : les mêmes anciens contenus peuvent ressortir bien classés plusieurs nuits de suite une fois le pipeline nocturne actif.

**Epic 3 (nocturne automatique)** — budget de temps global pour l'ensemble de la collecte (chaque source a désormais son propre timeout depuis la Story 2.2, mais rien ne borne la durée totale d'un run avec plusieurs sources lentes — la boucle de `collect.py` reste séquentielle) ; ordonnancement (Planificateur de tâches, FR-11) ; un bandeau d'échec nocturne sur la page publiée suppose un état de run persistant que `store.py`/SQLite (AD-5) ne fournit pas encore — trouvé en revue de la Story 1.8, le pipeline peut aujourd'hui publier un « rien à signaler » aussi bien pour une nuit calme que pour une collecte réellement en panne, sans les distinguer ; le chaînage interne de `collecter()` (collecte+dédup+filtre+quotas en une seule fonction, tension AD-1 non entièrement résolue par la Story 1.8, voir §7#24) pourrait être éclaté à cette occasion si un besoin réel apparaît ; `rendre()`/`rendre_markdown()` journalisent chacun indépendamment un éventuel « registre inconnu » via leur propre appel à `_grouper_par_registre` — un même run le journalise donc deux fois (trouvé en revue de la Story 1.9, non corrigé : un correctif propre exigerait de changer la signature publique des deux fonctions pour leur passer un regroupement déjà calculé, ou introduirait un drapeau persistant qui supprimerait à tort un avertissement réellement nouveau plus tard).

**Epic 4 (santé des sources)** — distinction diagnostique fine des échecs, racine JSON vide non signalée, bornes de plausibilité sur les dates aberrantes.

**Validation réelle contre l'API véritable (`enrich/llm.py`)** — langue de sortie, longueur réelle, coût réel mesuré via `usage.input_tokens`/`output_tokens` : différée faute de clé `ANTHROPIC_API_KEY` depuis la Story 1.6. `enrich/llm.py` est désormais branché dans un run réel (`pipeline.py`, Story 1.8), donc cette validation est maintenant la seule chose qui manque pour considérer FR-7/NFR1 pleinement éprouvés en conditions réelles.

**Validation réelle de la publication (`publish.py`, Stories 1.8/1.9)** — le second dépôt GitHub public dédié à la sortie (`petitlaye03/agent-veille-tech-digest` ou nom ajusté) n'a pas encore été créé, ni GitHub Pages activé dessus, ni le fichier `.nojekyll` qui devrait l'accompagner (trouvé en revue de la Story 1.8, concerne aussi bien `index.html` que l'archive Markdown de la Story 1.9 — Jekyll appliquerait son propre moteur de templates Liquid à l'un comme à l'autre) : action réelle sous le compte d'Abdoulaye, à confirmer explicitement avant de l'exécuter. `publish.py` (page **et** archive) est validé par tests (client HTTP simulé) et par exécution réelle en dégradation (sans jeton résolu), mais pas encore contre l'API GitHub véritable.

**Non priorisé / précondition documentée, pas corrigée** — `rapport_quotas`/`rapport_classement` (`filter.py`) et, depuis la Story 1.7, `marquer_recommandation` (`enrich/llm.py`) sur-comptent en théorie si le même objet `Item` apparaît deux fois dans leur entrée (non atteignable via `collecter()`, `dedup.py` garantit l'unicité) ; `SourceConfig` non hashable ; `_resoudre_chemin` ne traverse pas les listes ; validation du `type`/champs requis par source au chargement ; formats de date US ambigus (`%m/%d/%Y`) ; garde de domaine sensible à la casse (scraping) ; `ARCHITECTURE-SPINE.md` toujours à `anthropic 0.119.0` alors que `1.2.0` est installé (aucun AC ne l'exige, dérive sans impact constaté) ; `scoring.yaml` relu deux fois par run (`collecter()` puis `pipeline.executer()`, faute d'exposer `Ponderations` sur `ResultatCollecte`) — coût négligible, non corrigé (trouvé en revue de la Story 1.8) ; le jeton issu de `gh auth token` (`publish.py`) n'est ni restreint ni validé en portée avant un usage non surveillé — compromis assumé, un `GITHUB_TOKEN` dédié reste disponible en option ; l'API Contents de GitHub a un plafond de charge utile par fichier (~1 Mo) non anticipé, prématuré à l'échelle actuelle du projet ; `_sha_existant`/`_publier` (partagés par la page et l'archive depuis la Story 1.9) n'ont pas de logique de nouvelle tentative si le `sha` change entre le `GET` et le `PUT` (écriture concurrente) — non atteignable aujourd'hui, système mono-opérateur, un seul run par nuit.

**`Score.motifs` (`filter.py`) toujours calculé mais jamais consommé** — décidé hors périmètre pour justifier une recommandation en Story 1.7, confirmé toujours sans lecteur après le rendu HTML de la Story 1.8 (`render.py` ne l'utilise pas) ; resterait disponible si un besoin d'affichage l'exigeait plus tard.

## 9. Environnement et infrastructure

**Migration Windows → Mac (2026-08-27)** : le dossier a été copié tel quel depuis l'ancien PC. Deux corrections faites à la reprise :
- le `.git` était resté à la racine de `Projets_Perso/` (englobant à tort `Saas_chatbots/`, un projet distinct) — déplacé dans `Agent_veille_tech/.git` pour que ce dossier soit son propre dépôt, aligné sur le remote `petitlaye03/Agent_Veille_Tech` ;
- `.venv` était un venv Windows inutilisable (`home = C:\Program Files\Python311`) — supprimé et reconstruit avec `uv sync` (`uv` installé via Homebrew, absent du Mac).

**État actuel** : dépôt propre (Stories 1.4 à 1.9 committées et poussées — Epic 1 entièrement terminé ; Stories 2.1/2.2/2.3 committées et poussées — Epic 2 en cours). Aucun commit n'est fait automatiquement — décision du 2026-08-27 : les commits restent à la demande explicite d'Abdoulaye. Les dossiers `_bmad/`, `.claude/`, `_bmad-output/` sont suivis par git depuis le 2026-08-28 (réintégrés une fois le dépôt confirmé privé et le contenu relu — voir commit dédié entre les Stories 1.7 et 1.8).

**Secrets** : `ANTHROPIC_API_KEY` (`.env`, voir `.env.example`) — nécessaire pour que `enrich/llm.py` génère de vraies accroches. Aucune clé fournie à ce jour. `GITHUB_TOKEN` (Story 1.8, optionnel) — `publish.py` réutilise en repli la session `gh` déjà authentifiée localement (`gh auth token`) si cette variable est absente.

**Second dépôt de publication, pas encore créé** (Story 1.8) : `publish.py` cible `petitlaye03/agent-veille-tech-digest` (nom ajustable), un dépôt public dédié à la page publiée **et** à l'archive Markdown (Story 1.9) — le dépôt de code reste privé. Ni ce dépôt, ni GitHub Pages dessus, ni un fichier `.nojekyll` à sa racine (trouvé en revue de la Story 1.8, pertinent aussi pour l'archive — désactive le traitement Jekyll par défaut de GitHub Pages, qui appliquerait sinon son propre moteur Liquid à `index.html` et aux fichiers `.md` publiés) n'existent encore à ce jour ; création différée, action réelle sous le compte d'Abdoulaye à confirmer explicitement.

## 10. Référence technique — fichier par fichier

Cette section documente **ce que fait chaque fichier**, en détail — pas seulement son existence. Elle est le complément technique de la narration par story (§6) : celle-ci raconte *comment* le code a évolué, celle-ci décrit *ce qu'il fait aujourd'hui*.

### 10.1 Vue d'ensemble

```text
src/veille/
  models.py               Le contrat de données canonique (Item, Entree)
  config.py               Chargement de sources.yaml, utilitaires de validation partagés
  connectors/
    rss_connector.py      Flux RSS/Atom
    json_connector.py     API JSON (mapping déclaratif)
    scrape_connector.py   Scraping HTML (sélecteurs sémantiques, robots.txt)
    _reseau.py             Backoff HTTP partagé sur 429 (interne aux 3 connecteurs)
  dedup.py                Dédoublonnage inter/intra-source
  profil.py               Chargement et analyse de profil.md
  filter.py               Seuil de signal, scoring par profil, quotas par registre
  collect.py              Orchestrateur de la collecte (dédup+filtre+quotas inclus)
  enrich/
    llm.py                 Frontière LLM unique (AD-7) : accroches en français + recommandation
  render.py               Rendu HTML + Markdown du digest (Jinja2)
  publish.py              Publication (page + archive) via l'API Contents GitHub
  pipeline.py             Orchestrateur du pipeline complet (AD-1) : collecte → enrichissement → rendu → publication (page + archive)

config/
  sources.yaml            Socle de sources (4 aujourd'hui)
  profil.md               Profil de filtrage d'Abdoulaye (thèmes, bruit)
  scoring.yaml            Pondérations du scoring + marge de recommandation
  quotas.yaml             Quotas par registre

templates/
  digest.html.j2          Template Jinja2 de la page publiée
  digest.md.j2            Template Jinja2 de l'archive Markdown datée

.env.example              ANTHROPIC_API_KEY= et GITHUB_TOKEN= (optionnel) — le vrai .env n'est jamais versionné

tests/
  conftest.py             Neutralise profil/pondérations/quotas par défaut
  test_*.py               17 fichiers, 323 tests (détail §10.14)
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

**`Entree`** (Story 1.6, FR-7 ; étendue Story 1.7, FR-8) — dataclass frozen, `item: Item` + `accroche: str` + `recommandee: bool = False`. Ce qu'un `Item` retenu devient une fois enrichi. `recommandee` n'est jamais forcée : au plus une `Entree` par jour la porte à `True`, déterminée par `enrich.llm.marquer_recommandation` à partir des scores du jour — jamais par un appel LLM (voir §10.9).

### 10.3 `src/veille/config.py` — configuration des sources et utilitaires partagés

- **`RACINE_PROJET`** / **`chemin_config(nom)`** — résout un fichier `config/<nom>` depuis la racine du dépôt (déduite de l'emplacement du module), et non depuis le répertoire courant. Utilisé par `profil.py` et `filter.py` pour leurs chemins par défaut : indispensable pour un run lancé par un planificateur de tâches (Epic 3), où le CWD n'est pas garanti.
- **`SourceConfig`** — dataclass frozen décrivant une source : `id`, `type`, `url`, `langue`, `registre` (communs), puis `priorite` (dédoublonnage), `seuil_signal` (FR-4), et des champs propres à chaque type de connecteur (`racine`, `mapping`, `url_modele` pour JSON ; `selecteur`, `base_url` pour le scraping).
- **`load_sources(path)`** — lit `sources.yaml`, isole chaque entrée : une source mal formée est journalisée et ignorée, les autres survivent.
- **`_normaliser(entry)`** — corrige `seuil_signal` avant construction de `SourceConfig`, via `to_float_fini`.
- **`to_float_fini(valeur)`** — utilitaire partagé (aussi utilisé par `filter.py` pour les pondérations) : convertit en `float` fini, rejette les booléens (`yes` → `True` → `1.0` silencieux évité) et `nan`/`inf` (toute comparaison à `nan` est fausse — un seuil `nan` laisserait tout passer sans le moindre signe).

### 10.4 `src/veille/connectors/` — un module par type de source, même contrat

Les trois connecteurs partagent le contrat `fetch(source_config: SourceConfig) -> list[Item]` (AD-2). Aucun autre module n'a besoin de savoir lequel est utilisé — `collect.CONNECTORS` fait le dispatch.

**`_reseau.py`** (Story 2.3) — module de détail interne (préfixé `_`, hors du contrat public AD-2), partagé par les trois connecteurs ci-dessous plutôt que triplé.
- `get_avec_backoff(url, *, timeout, headers=None, follow_redirects=True) -> httpx.Response` : appelle `httpx.get`, retente sur `429` uniquement (jusqu'à `MAX_TENTATIVES = 3`) ; toute autre erreur HTTP lève immédiatement, sans retry. Respecte l'en-tête `Retry-After` du serveur (secondes) quand il est présent, lisible et fini ; sinon (ou au-delà de `DELAI_MAX_SECONDES = 60`, plafond ajouté en revue) retombe sur un backoff exponentiel parti de `DELAI_DEFAUT_SECONDES = 5.0`.
- `_delai_depuis_retry_after` : rejette explicitement les valeurs non finies (`inf`/`nan`, acceptées par `float()` mais qui feraient planter `time.sleep` — trouvé et vérifié empiriquement en revue) en plus des valeurs non numériques.
- Au-delà de `MAX_TENTATIVES`, la dernière réponse 429 lève normalement (`httpx.HTTPStatusError`) : `collect._fetch_one` isole la panne comme n'importe quelle autre (AD-6), sans aucune modification de `collect.py`.
- Volontairement **pas** branché sur `scrape_connector._collecte_autorisee` (requête `robots.txt`) — une seule requête par source et par nuit, déjà dégradée proprement sur toute exception.

**`rss_connector.py`** — flux RSS/Atom via `feedparser`.
- `_charger(url)` (Story 2.2, délègue à `get_avec_backoff` depuis la Story 2.3) : dispatch sur `urlparse(url).scheme` — `http(s)://` récupère le flux via le backoff partagé (`TIMEOUT_SECONDES = 30`, `User-Agent` explicite), tout le reste (chemin local, `file://`) est rendu tel quel à `feedparser.parse()`, inchangé depuis la Story 1.1. Une panne HTTP (403/429/500) ou un délai dépassé lève désormais une vraie exception, capturée par l'isolation de `collect._fetch_one` (AD-6) — avant la Story 2.2, elle était avalée par le mécanisme `bozo` et la source apparaissait « muette » plutôt qu'« en échec ». Condition de branchement délibérément inversée par rapport à `json_connector._charger`/`scrape_connector._charger` ci-dessous (voir §7#33). Conserve `import httpx` bien que non appelé directement (délégué), pour que les tests de la Story 2.2 qui monkeypatchent `module.httpx.get` restent valides (`httpx` est un module singleton partagé avec `_reseau.py` — voir §7#39).
- Tolère un flux `bozo` (imparfait) tant qu'il expose des entrées exploitables ; ne renvoie une liste vide que si aucune entrée n'est récupérable.
- `guid` : identifiant natif du flux en priorité, puis URL, puis hash SHA-256 `(source_id + titre)` — convention posée en Story 1.1.
- `_extract_contenu` : repli en cascade `summary` → `content[0].value` (Atom) → `description`, pour ne jamais renvoyer un contenu vide alors que le flux en porte.
- Dates converties via `calendar.timegm` (pas `time.mktime`, qui appliquerait le fuseau local). Encore affecté par le bug `published_parsed`/`updated_parsed` trouvé en Story 2.1 (dette, §8).
- Isolation par entrée : une entrée corrompue n'emporte pas les autres.

**`json_connector.py`** — API JSON, forme entièrement déclarée en configuration (`mapping`, chemins pointés type `paper.summary`).
- `_charger` délègue à `get_avec_backoff` depuis la Story 2.3 (`import httpx` retiré, plus utilisé directement dans ce fichier).
- `_resoudre_chemin`/`_champ` : navigation dans une structure imbriquée ; un champ absent du mapping vaut `None`, jamais l'entrée entière.
- `guid` : `0` et `False` sont des identifiants valides (seuls `None`/`""` sont rejetés) ; un identifiant non scalaire (dict/list) lève une erreur explicite plutôt que de produire une URL corrompue.
- `url_modele` : gabarit avec le `guid` encodé (`quote`) avant insertion.
- `_to_signal` : convertit le signal en `float`, dégrade vers `None` sur toute valeur non numérique (jamais de plantage — le signal est une donnée d'appoint, Story 1.4).
- `_to_utc_datetime` : accepte ISO 8601 et horodatages Unix (secondes ou millisecondes, seuil de bascule à 1e11).

**`scrape_connector.py`** — scraping HTML, réservé aux sources sans flux ni API.
- `_collecte_autorisee` : consulte `robots.txt` **avant toute requête** (AD-10) ; absent ou injoignable → collecte autorisée par défaut, présent et restrictif → respecté. Toujours son propre `httpx.get` direct, **pas** de backoff (voir `_reseau.py` ci-dessus).
- `_charger` (récupération de la **page**, distincte de `_collecte_autorisee`) délègue à `get_avec_backoff` depuis la Story 2.3.
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

**2. Scoring par profil** — `scorer(item, profil, ponderations) -> Score` : recherche de mots-clés sur titre + contenu, insensible casse/accents, sur mot entier tolérant au singulier/pluriel (`_contient_mot_cle`, `s` final optionnel, frontières conditionnelles qui ne s'ancrent que contre un caractère alphanumérique). Deux règles de cumul (tranchées en revue Story 1.4) : un thème compté dans deux catégories du profil ne compte qu'une fois (au poids le plus fort), et les mots-clés suivants d'une même catégorie sont atténués (`_ATTENUATION_PAR_RANG = 0.5` : ½, ¼… — une puissance de deux exacte, donc `Score.valeur` reste toujours exactement représentable en binaire pour les poids entiers du profil, point vérifié en revue de la Story 1.7). `classer(items, profil, ponderations) -> list[ItemScore]` score tout, écarte sous `seuil_bruit`, trie par score décroissant (tri stable — égalité de score préserve l'ordre d'arrivée). `charger_ponderations(chemin) -> Ponderations` lit `config/scoring.yaml` : repli par valeur (une clé invalide ne réinitialise pas les autres), rejette les clés inconnues (`_avertir_cles_inconnues`) et les valeurs falsy mal typées. Depuis la Story 1.7, `_ponderation` accepte un paramètre `positif_strict` (utilisé uniquement pour `marge_recommandation`, voir plus bas — `bruit`/`seuil_bruit` restent légitimement négatifs, pas soumis à ce contrôle). Rapport : `RapportClassement`/`rapport_classement` (diff par identité d'objet entre l'entrée et la sortie de `classer`).

**Recommandation du jour (FR-8, Story 1.7)** — `Ponderations` porte aussi `marge_recommandation: float = 10.0`, lue à la racine de `scoring.yaml` (comme `seuil_bruit`, pas sous `ponderations:` — ce n'est pas une pondération par catégorie) : l'écart minimal entre le meilleur score du jour et le second pour que l'entrée soit recommandée. Valeur rejetée si ≤ 0 (repli sur le défaut) — une marge nulle ou négative romprait la garantie « jamais de recommandation à égalité », trouvé en revue. La détermination elle-même (`determiner_recommandation`/`marquer_recommandation`) vit dans `enrich/llm.py`, pas ici — voir §10.9.

**3. Quotas par registre** — `repartir_par_quotas(classement, quotas) -> list[ItemScore]` : un seul passage sur un classement déjà trié (`classer()` l'a fait), compteur par registre, jamais de second tri. Un registre absent de `Quotas` est conservé sans limite (même principe que le signal absent — mais voir §10.10, `render.py` : ce même comportement rend un registre mal orthographié réellement atteignable jusqu'au rendu). `charger_quotas(chemin) -> Quotas` : même patron exact que `charger_ponderations`. Rapport : `RapportQuotas`/`rapport_quotas` (par registre, plus un détail interne `ecartes_par_source` pour le diagnostic « source absorbée » de `collect.py`).

**`CHAMPS_QUOTAS`** (renommé depuis `_CHAMPS_QUOTAS` en Story 1.8) — tuple `("apprendre", "ce_qui_bouge", "pour_le_metier")`, l'ordre canonique des registres. Rendu public précisément parce que `render.py` le réutilise désormais pour l'ordre d'affichage des sections — un contrat inter-module, plus un détail interne à ce fichier.

Utilitaires partagés entre les trois mécanismes : `_ventilation(comptes)` (formatage `"clé (-n)"` générique, utilisé par les trois rapports) et `_avertir_cles_inconnues` (partagé entre `charger_ponderations` et `charger_quotas`).

### 10.8 `src/veille/collect.py` — l'orchestrateur

- **`CONNECTORS`** — table de dispatch `type → fetch`, seul point à modifier pour ajouter un connecteur.
- **`RapportSource`** — par source : `nb_items` (collecté) vs `nb_retenus` (contribution finale au digest, agrégeant dédoublonnage + seuil de signal + scoring + quotas). `est_muette` (zéro item sans erreur) et `est_absorbee` (a collecté mais rien n'a survécu) sont des diagnostics distincts d'`echec` (une vraie erreur).
- **`ResultatCollecte`** — `items` (liste finale), un rapport par mécanisme (`dedoublonnage`, `filtrage_signal`, `classement`, `quotas`), `profil_neutre` (alerte si le profil n'a aucun mot-clé), et depuis la Story 1.8 **`resultats_repartis: list[ItemScore]`** — le classement filtré par quota exposé tel quel (champ additif, peuplé avec la variable déjà calculée en interne). Ferme la dette « `Score` calculé puis jeté » suivie depuis la Story 1.4 : sans ce champ, `pipeline.py` n'aurait eu aucun moyen de fournir un classement à `enrich.llm.marquer_recommandation`. `resume()` produit un récapitulatif texte auto-suffisant : total collecté vs retenu dès qu'ils diffèrent, détail de chaque mécanisme qui a écarté quelque chose. **Depuis la Story 2.2** : `sources_en_panne_reseau` (propriété) filtre `sources_en_echec` sur `type in CONNECTORS` — exclut une source dont le `type` est mal orthographié (jamais tentée par un connecteur, erreur de configuration statique, pas une panne réseau) ; `taux_echec`/`anomalie_pannes` (propriétés calculées) détectent une nuit où plus de la moitié du socle est en panne réseau/HTTP réelle (seuil strict, > 0.5).
- **`collecter(sources_path, profil_path, scoring_path, quotas_path)`** — la fonction centrale. Charge les sources (isolé, AD-6), collecte chaque source (`_fetch_one`, isolé par source), puis enchaîne signal → dédoublonnage → scoring → quotas dans cet ordre exact. Les 4 chemins de configuration sont résolus **à l'appel**, pas à l'import — ce qui permet à `tests/conftest.py` de les substituer sans toucher au code.
- **`run(sources_path)`** — enveloppe fine : `collecter(...).items`, pour les appelants qui ne veulent que la liste.
- **`_journaliser`** — publie le récapitulatif en `INFO` (réellement visible en prod), et pour chaque source absorbée, nomme **toutes** les causes possibles (doublons / seuil de signal / bruit du profil / quota dépassé) plutôt que d'en présumer une seule. **Depuis la Story 2.2** : émet en plus un journal `ERROR` agrégé (nommant les sources concernées) quand `anomalie_pannes` est vrai — distinct des traces `logger.exception` déjà émises individuellement par `_fetch_one` (elles aussi en `ERROR`, mais noyées dans le détail d'une nuit chargée). Ne bloque jamais la production du digest.

### 10.9 `src/veille/enrich/llm.py` — frontière LLM unique (AD-7, FR-7/8)

Seul module du projet qui importe `anthropic` (vérifié mécaniquement par `grep`, pas seulement par convention). Génère une accroche en français pour un item, même depuis une source anglophone — et, depuis la Story 1.7, détermine aussi l'entrée recommandée du jour, **sans jamais appeler l'API** pour cette seconde responsabilité.

- **`MODELE = "claude-haiku-4-5-20251001"`** — modèle éco (Stack de l'architecture) : c'est ce choix qui rend NFR1 (< 2 €/mois) atteignable, pas un modèle plus lourd.
- **`_client()`** — construit le client depuis `ANTHROPIC_API_KEY` (`.env`, via `python-dotenv`). Ne lève jamais : clé absente **ou composée uniquement d'espaces** (`.strip()` — trouvé en revue) → `None`, avertissement journalisé une seule fois par run (pas par item, un digest peut compter ~240 items).
- **`generer_accroche(item, client=None) -> str | None`** — prompt court : titre (borné à `LONGUEUR_TITRE=200`, trouvé en revue — seul l'extrait l'était initialement) + extrait de `contenu_brut` (borné à `LONGUEUR_EXTRAIT=500`). Isolation totale : `anthropic.AnthropicError` et toute autre exception capturées, `None` en retour. Une réponse tronquée par `max_tokens` (`stop_reason == "max_tokens"`, trouvé en revue) est traitée comme un échec plutôt que publiée telle quelle. `_PROMPT_SYSTEME` porte une consigne anti-injection (trouvé en revue) : le titre/extrait sont des sources externes non fiables, jamais des instructions.
- **`enrichir(items, client=None) -> list[Entree]`** — le client est résolu **une seule fois** (trouvé en revue — sinon reconstruit à chaque item). Un item dont l'accroche échoue est **conservé**, avec son `titre` en repli (décision actée avant le code, jamais `""` même si le titre est vide — repli ultime `"(titre indisponible)"`, trouvé en revue).
- **Limitation assumée** : AC1 (« 1 à 3 phrases en français ») n'est pas mécaniquement vérifié au-delà de la troncature — ni langue ni nombre de phrases ne sont validés par le code, seulement demandés au modèle. Une vérification complète exigerait un second appel LLM (contraire à AD-7) ou une détection de langue peu fiable.
- **`determiner_recommandation(classement, ponderations=Ponderations()) -> ItemScore | None`** (Story 1.7, FR-8) — purement déterministe, sur le `Score.valeur` déjà calculé par `filter.py`, **aucun appel API**. `classement` est supposé déjà trié par `classer()`, jamais retrié ici : le premier est recommandé s'il dépasse le second d'au moins `ponderations.marge_recommandation` (`>=`, égalité exacte incluse) ; avec moins de deux items, ou un écart insuffisant, jamais de recommandation. Le classement attendu en production est celui filtré par quota (`repartir_par_quotas()`), pas le classement brut — précisé en docstring en revue (Story 1.8 devra respecter ce contrat au câblage).
- **`marquer_recommandation(entrees, classement, ponderations=Ponderations()) -> list[Entree]`** (Story 1.7) — fonction **additive**, appliquée après `enrichir()` : ne change ni sa signature ni son comportement (décision de conception actée avant le code, voir §6.7). Correspondance par identité d'objet (`id(entree.item)`), même convention que `rapport_classement`/`rapport_quotas` (`filter.py`) — même précondition non vérifiée qu'eux, documentée dans la docstring depuis la revue (un même `Item` référencé par deux `Entree` les ferait toutes deux basculer à `True`, non atteignable via `collecter()` aujourd'hui). Ne lève jamais : gagnant introuvable ou listes désynchronisées → `entrees` inchangée (`Entree` étant frozen, seule l'entrée gagnante devient une nouvelle instance via `dataclasses.replace`).
- **Branché depuis la Story 1.8** dans `pipeline.py` — accroches (`enrichir`) et recommandation (`determiner_recommandation`/`marquer_recommandation`) sont désormais exercées dans un run réel, pas seulement testées sur des `Item`/`ItemScore` construits pour le test.

### 10.10 `src/veille/render.py` — rendu HTML et Markdown du digest (FR-9/10, Stories 1.8/1.9)

Regroupe les `Entree` par registre et produit la page publiée (HTML) et l'archive datée (Markdown) à partir de `templates/digest.html.j2`/`digest.md.j2` (Jinja2). Aucune logique de scoring ni d'appel réseau ici — seulement de la mise en forme.

- **`LIBELLES_REGISTRE`** — libellés d'affichage (`apprendre` → « Apprendre », etc.), dans l'ordre de `filter.CHAMPS_QUOTAS` (réutilisé tel quel, pas redéfini en second ordre parallèle).
- **`_url_surs(url) -> str | None`** — ne renvoie l'URL que si son schéma est `http(s)` **et** qu'elle ne porte aucun `<`/`>` littéral (ce second critère ajouté en revue de la Story 1.9), sinon `None`. L'autoescaping HTML de Jinja2 neutralise les métacaractères mais jamais le **schéma** d'une URI (trouvé en revue de la Story 1.8) ; le rejet des chevrons sert le template Markdown, où la destination est enveloppée `<...>` (une URL contenant elle-même un chevron fermerait cette enveloppe prématurément). Exposée comme fonction globale des deux environnements Jinja, appelée directement par les deux templates.
- **`_grouper_par_registre(entrees) -> tuple[sections, digest_vide]`** (extrait en Story 1.9) — regroupement par registre + calcul de `digest_vide`, **partagé** par `rendre()` et `rendre_markdown()` pour que les deux sorties ne divergent jamais. Un registre inconnu (typo dans `sources.yaml` — réellement atteignable, `repartir_par_quotas` conserve sans limite un registre qu'il ne reconnaît pas) est journalisé (`logger.warning`) plutôt que silencieusement perdu — journalisé **deux fois** par run puisque les deux fonctions de rendu y font chacune appel (dette mineure, §8). `digest_vide` se calcule sur les sections **réellement peuplées**, pas sur la seule non-vacuité de `entrees` (trouvé en revue de la Story 1.8).
- **`_environnement_jinja() -> Environment`** — autoescaping HTML **explicite** (`enabled_extensions=("html", "xml", "j2")`) : `select_autoescape()` sans argument ne reconnaît pas l'extension `.j2` du nom `digest.html.j2` — l'échappement serait sinon silencieusement désactivé.
- **`_echapper_markdown(texte) -> str`** (Story 1.9) — échappement Markdown explicite (Jinja2 n'a pas d'autoescape Markdown intégré). Échappe `` \`*_{}[]()!|~<> `` — caractères actifs **indépendamment de leur position**. `#`/`-`/`+`/`.` en sont **délibérément exclus** (trouvé en revue) : actifs seulement en tout début de ligne, jamais atteignable ici (texte toujours inséré au milieu d'une puce déjà ouverte), et les échapper casserait la recherche par texte (AC6) pour un cas courant (« GPT-5.2 »). Neutralise aussi les sauts de ligne incorporés (remplacés par un espace) — nécessaire pour que l'exclusion précédente reste sûre.
- **`_environnement_jinja_markdown() -> Environment`** (Story 1.9) — environnement **séparé** de `_environnement_jinja()`, `autoescape=False`, filtre `markdown_safe` = `_echapper_markdown`. Piège évité : `digest.md.j2` se termine aussi par `.j2`, donc réutiliser le premier environnement aurait appliqué l'autoescape HTML (entités `&amp;` erronées) à un fichier Markdown.
- **`rendre(entrees, date_generation) -> str`** — rend `digest.html.j2`. Titre vide → repli sur l'accroche ; URL vide/schéma refusé/chevrons → pas de lien cliquable.
- **`rendre_markdown(entrees, date_generation) -> str`** (Story 1.9) — rend `digest.md.j2` ; mêmes garde-fous que `rendre()`, plus l'échappement Markdown et l'enveloppe `<...>` des liens (une URL avec parenthèses, ex. Wikipédia, casserait `[texte](url)` sans elle).

### 10.11 `src/veille/publish.py` — publication de la page et de l'archive (AD-8, Stories 1.8/1.9)

Écrit/actualise `index.html` (page) et `site/archive/YYYY-MM-DD.md` (archive datée) dans un **second dépôt GitHub, public, dédié uniquement à la sortie publiée** — le dépôt de code reste privé (décision actée avec Abdoulaye, voir §6.8). Via l'API Contents de GitHub (`PUT /repos/{owner}/{repo}/contents/{path}`), jamais un clone local ni un `subprocess` vers `git`.

- **`PUBLISH_REPO`** — constante en dur (`petitlaye03/agent-veille-tech-digest`), même précédent que `MODELE` dans `enrich/llm.py`.
- **`CHEMIN_PAGE`** (renommé depuis `CHEMIN_FICHIER` en Story 1.9) — `"index.html"`, distinct du chemin de l'archive (daté, construit à la volée dans `publier_archive`).
- **`_jeton() -> str | None`** — résolution à deux niveaux : `GITHUB_TOKEN` (`.env`, nettoyé des espaces) en priorité, sinon repli sur `gh auth token`.
- **`_client() -> httpx.Client | None`** — `None` si aucun jeton résolu, avertissement journalisé une seule fois.
- **`_sha_existant(client, chemin) -> str | None`** (paramétrée par le chemin depuis la Story 1.9, sert la page **et** l'archive) — sha du fichier existant, `None` si absent. Seul un **404** vaut « absent » : tout autre code (401/403/5xx) lève via `raise_for_status()`, isolé comme toute autre panne.
- **`_publier(chemin, contenu, client, quoi, categorie) -> bool`** (extrait en Story 1.9, cœur partagé) — `GET` préalable pour le `sha`, puis `PUT` (création si absent, mise à jour sinon). Isolation totale, ne lève jamais, `False` sur échec. `categorie` (`"page"`/`"archive"`) sert uniquement à donner à chacune sa **propre** trace complète au premier échec (trouvé en revue — un booléen unique partagé aurait fait perdre la trace du second échec d'un même run).
- **`publier(html, client=None) -> bool`** — appelant fin de `_publier(CHEMIN_PAGE, ...)`.
- **`publier_archive(markdown, date_digest, client=None) -> bool`** (Story 1.9) — appelant fin de `_publier`, chemin `f"site/archive/{date_digest.isoformat()}.md"`. Relancer pour la même date écrase l'archive existante (upsert par `sha`, AD-9), jamais un doublon.
- **Non encore validé contre l'API réelle** : le dépôt de sortie n'existe pas encore, ni un `.nojekyll` à sa racine (voir §8, §9).

### 10.12 `src/veille/pipeline.py` — orchestrateur du pipeline complet (AD-1, Stories 1.8/1.9)

Point d'entrée unique : `collecter()` → `enrichir()` → `marquer_recommandation()` → `rendre()` + `publier()` (page) → `rendre_markdown()` + `publier_archive()` (archive).

- **`executer(sources_path=None, profil_path=None, scoring_path=None, quotas_path=None, llm_client=None, publish_client=None) -> bool`** — chemins de config résolus à l'appel ; `scoring_path` résolu via `collect.DEFAULT_SCORING_PATH` pour rester cohérent avec le chemin que `collecter()` a réellement utilisé. `llm_client` n'est volontairement pas typé `anthropic.Anthropic | None` (romprait l'invariant AD-7). **La page est rendue et publiée avant même que l'archive soit rendue** (trouvé en revue de la Story 1.9) : sans cet ordre, un `rendre_markdown()` qui lève après un `rendre()` réussi ferait perdre une page déjà prête. Retourne `True` seulement si la page **et** l'archive sont publiées avec succès (`page_ok and archive_ok`) — les deux toujours tentées, un échec de l'une n'empêchant jamais la tentative de l'autre. **Intégralité du corps enveloppée d'un filet de sécurité** : `collecter`/`enrichir`/`marquer_recommandation`/`publier`/`publier_archive` dégradent déjà proprement, mais `rendre()`/`rendre_markdown()` n'ont pas cette garantie propre (un template manquant lèverait `TemplateNotFound`).
- **`main()`** — même patron que `collect.py`. Code de sortie non nul sur échec (`sys.exit`) : sans lui, un futur planificateur de tâches (FR-11, Epic 3) n'aurait aucun moyen de détecter une nuit en échec.
- **Résout la partie d'AD-1 qui a un AC réel** (voir §7#24) — le chaînage interne de `collecter()` (collecte+dédup+filtre+quotas) n'est volontairement pas défait.

### 10.13 Fichiers de configuration

- **`config/sources.yaml`** — **17 sources depuis la Story 2.1** (4 à l'origine, +13). D'origine : `openai-news` (RSS, `ce_qui_bouge`), `huggingface-blog` (RSS, `apprendre`), `hf-daily-papers` (JSON, `apprendre`, `seuil_signal: 15`), `anthropic-news` (scrape, `ce_qui_bouge`). Ajoutées en Story 2.1 : 8 en `apprendre` (4 dépôts GitHub via `releases.atom` — `llama.cpp`, `vllm`, `transformers`, `ollama` — plus `eugene-yan`, `simon-willison`, `statquest-youtube`, `datagen-podcast`), 3 en `ce_qui_bouge` (`brief-ia`, `hacker-news` en JSON avec `racine: hits`/`seuil_signal: 250`, `tldr-ai`), 2 en `pour_le_metier` (`decideo`, `lemonde-informatique` — **dette fermée**, ce registre était vide depuis la Story 1.5). Deux pièges découverts et désormais documentés dans le commentaire d'en-tête du fichier : une `priorite: 0` explicite est indiscernable d'une priorité absente (garde-fou existant l'interdit ; utiliser `1` pour un agrégateur) ; une réponse JSON dont la racine n'est pas une liste (ex. `{"hits": [...]}`) exige `racine: <clé>`, sans quoi la source est silencieusement ignorée.
- **`config/profil.md`** — profil de filtrage d'Abdoulaye : 5 sections de mots-clés (`Thèmes prioritaires`, `Signal fort`, `Domaines d'application`, `Thèmes secondaires`, `Bruit`) + une section `Posture` (prose, ignorée par le parseur). Réécrite en Story 1.5 (revue) pour que la section Bruit ne contienne que des mots-clés atomiques, pas des phrases.
- **`config/scoring.yaml`** — pondérations : `prioritaire: 10`, `signal_fort: 15`, `domaine: 5`, `secondaire: 2`, `bruit: -20`, `seuil_bruit: -5`, `marge_recommandation: 10` (Story 1.7 — rejetée si ≤ 0, repli sur le défaut).
- **`config/quotas.yaml`** — quotas : `apprendre: 3`, `ce_qui_bouge: 3`, `pour_le_metier: 2`.
- **`templates/digest.html.j2`** (Story 1.8) — template Jinja2 de la page publiée : structure sémantique, viewport meta tag, CSS embarqué (palette + typographie + media query `prefers-color-scheme: dark`), section par registre, marque de recommandation, lien conditionné à `url_surs()`.
- **`templates/digest.md.j2`** (Story 1.9) — template Jinja2 de l'archive Markdown datée : mêmes sections/garde-fous que la page HTML, titre/accroche passés par le filtre `markdown_safe`, lien enveloppé `[texte](<url>)`.
- **`.env.example`** — `ANTHROPIC_API_KEY=` (Story 1.6) et `GITHUB_TOKEN=` (Story 1.8, optionnel — repli sur `gh auth token`) ; le vrai `.env` est gitignoré (`!.env.example` annule l'ignorance générique de `.env.*`), vérifié sans fuite dans le dépôt ni son historique.

### 10.14 Tests

350 tests, aucun appel réseau ni subprocess réel dans la suite automatisée (fixtures locales, clients simulés, `httpx.get`/`time.sleep` monkeypatchés, résolution de jeton monkeypatchée) — seules les Tasks 2/4 des Stories 2.1/2.2 ont fait des exécutions réelles ponctuelles, hors suite `pytest`, documentées dans leurs Dev Agent Record respectifs. `tests/conftest.py` neutralise `profil.md`/`scoring.yaml`/`quotas.yaml` par défaut pour tous les tests (fixture `autouse`), afin qu'aucun test ne dépende implicitement de la configuration de production.

| Fichier | Périmètre | Tests |
|---|---|---|
| `test_models.py` | `Item`, `Entree` (dont `recommandee`), validation de `date_publication` | 9 |
| `test_config.py` | `load_sources`, validation de `seuil_signal` | 11 |
| `test_socle_reel.py` | Garde-fous sur les fichiers de config **réels** (`sources.yaml`, `scoring.yaml`, `quotas.yaml`) — +1 en Story 2.1 (présence du registre `pour_le_metier`) | 15 |
| `test_rss_connector.py` | Connecteur RSS — timeout/statut HTTP explicites, dispatch réseau vs local, encodage (Story 2.2) | 12 |
| `test_json_connector.py` | Connecteur JSON, extraction du signal | 8 |
| `test_scrape_connector.py` | Connecteur scraping, `robots.txt` | 9 |
| `test_dedup.py` | Dédoublonnage unitaire | 20 |
| `test_dedup_regressions.py` | Régressions de la revue Story 1.3 | 18 |
| `test_profil.py` | Parseur de profil, robustesse aux éditions manuelles | 28 |
| `test_filter.py` | Signal, scoring, quotas, marge de recommandation — le plus gros fichier | 69 |
| `test_llm.py` | Frontière LLM (client simulé, isolation par item) + recommandation (`determiner_recommandation`/`marquer_recommandation`) | 33 |
| `test_collect.py` | `run()`, cas d'erreur de haut niveau, `resultats_repartis` | 10 |
| `test_rapport_collecte.py` | Observabilité (`RapportSource`, états muette/échec, anomalie de pannes réseau — Story 2.2 ; backoff 429 de bout en bout sur les 3 connecteurs — Story 2.3) | 15 |
| `test_reseau.py` | Backoff HTTP partagé sur 429 (`_reseau.get_avec_backoff`) — Story 2.3 | 11 |
| `test_collecte_integration.py` | **Chemin réel** config → `collecter()` → rapport, pour chaque mécanisme | 25 |
| `test_render.py` | Rendu HTML + Markdown : sections, palette, dark mode, échappement (HTML et Markdown), schéma/chevrons d'URI, registre inconnu | 32 |
| `test_publish.py` | Publication (page + archive) : résolution de jeton, création/mise à jour, isolation de panne, trace par catégorie | 19 |
| `test_pipeline.py` | Orchestrateur : chemin complet (page + archive), dégradation sans clé/jeton, filet de sécurité, corrélation contenu↔chemin | 6 |

## 11. Prochaine étape

**Epic 1 est entièrement terminé** (Stories 1.1 à 1.9, toutes `done`) : le pipeline complet existe, de la collecte à la double publication (page + archive), à l'échelle réduite visée (3-5 sources). **Epic 2 est en cours** : Story 2.1 (`done`) porte le socle à 17 sources et ferme la dette `pour_le_metier` ; Story 2.2 (`done`) ferme le timeout réseau manquant de `rss_connector.py` et détecte une nuit à majorité de pannes ; Story 2.3 (`done`) ajoute un backoff partagé sur 429. Reste à faire dans l'Epic 2 :

- **Story 2.4 — Dédoublonner à l'échelle.** `dedup.py` a été conçu et testé pour 4 sources ; vérifier son comportement (performance, transitivité) à 17 sources et plus.
- **Epic 3 — Génération nocturne automatique.** Rend le pipeline réellement autonome (ordonnancement, idempotence du job, état « déjà vu » validé après publication) — le bénéfice le plus visible au quotidien (Abdoulaye n'a plus rien à déclencher), mais suppose `store.py`/SQLite (AD-5) encore à construire. Prérequis aussi pour évaluer sur plusieurs nuits deux incertitudes trouvées en Story 2.1 (rendement réel de `pour_le_metier`, réglage du seuil Hacker News).
- **Epic 4 — Santé des sources et découverte.** Le moins urgent tant que le socle reste petit et géré manuellement.

**Avant l'un ou l'autre, ou en parallèle** : créer le second dépôt GitHub public de sortie et y activer GitHub Pages (+ `.nojekyll`) — seule chose qui manque pour valider `publish.py` (page et archive) contre l'API réelle plutôt qu'en dégradation simulée. Et dès qu'une clé `ANTHROPIC_API_KEY` sera fournie : valider `enrich/llm.py` contre l'API véritable (langue, longueur, coût mesuré) — déjà branché dans un run réel depuis la Story 1.8, seule la validation manque.

Autres points ouverts (§7, §8), non liés à un Epic en particulier :
- `Score.motifs` (`filter.py`) existe toujours et n'est consommé par rien — resterait disponible si un besoin d'affichage l'exigeait plus tard.
- Le doublon de l'avertissement « registre inconnu » (`render.py`, Story 1.9) — bruit de log mineur, pas fonctionnel, non corrigé faute d'un correctif proportionné.
- **`rss_connector._to_utc_datetime` mal-date silencieusement 5 des 17 sources du socle** (trouvé en Story 2.1) — la Story 2.2 a bien touché `rss_connector.py` (timeout/isolation de panne), mais délibérément pas ce point : une préoccupation distincte (parsing de date, pas récupération réseau), laissée pour une story dédiée ou un futur passage sur ce fichier.
