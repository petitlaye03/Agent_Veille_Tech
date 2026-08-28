---
baseline_commit: 5b59e64
---

# Story 1.5: Répartir en trois sections à quotas

Status: done

## Story

As a Abdoulaye,
I want voir mon digest organisé en trois sections (Apprendre / Ce qui bouge / Pour le métier) à quotas,
so that j'équilibre chaque jour progression, actualité et employabilité, sans jamais recevoir un digest gonflé artificiellement.

## Acceptance Criteria

1. **[FR-6]** Étant donné un classement déjà scoré et trié (sortie de `classer()`, Story 1.4), la répartition retient au plus le quota configuré par registre — défaut ≈3 `apprendre` / ≈3 `ce_qui_bouge` / ≈2 `pour_le_metier`.
2. **[FR-6]** À l'intérieur d'un registre, les items retenus sont ceux au score le plus haut parmi ceux de ce registre — l'ordre par score de `classer()` est préservé, jamais retrié.
3. **[FR-6]** Un registre disposant de moins d'items que son quota affiche moins d'entrées : **aucun remplissage artificiel**, jamais d'item générique ou dupliqué ajouté pour combler.
4. **[FR-6]** Les quotas sont déclarés en configuration (`config/quotas.yaml`) et modifiables **sans toucher au code**.
5. Le récapitulatif rend compte de la répartition : combien d'items retenus et combien écartés par dépassement de quota, **par registre**.
6. Un registre absent de la configuration de quotas (faute de frappe, section oubliée) est **conservé, pas supprimé silencieusement** — avec un avertissement. Cohérent avec la règle déjà posée en Story 1.4 AC2 : l'absence de réglage n'est pas une insuffisance de contenu.

## Tasks / Subtasks

- [x] Task 1 : Charger les quotas depuis la configuration (AC: 4, 6)
  - [x] Créer `Quotas` (dataclass frozen) dans `src/veille/filter.py` avec trois champs entiers : `apprendre: int = 3`, `ce_qui_bouge: int = 3`, `pour_le_metier: int = 2`
  - [x] `charger_quotas(chemin: str | Path = DEFAULT_QUOTAS_PATH) -> Quotas`, sur le modèle exact de `charger_ponderations` : fichier absent/illisible/malformé → `Quotas()` par défaut, **repli par valeur et non global** (une seule clé invalide ne doit pas réinitialiser les deux autres), jamais lever
  - [x] Créer `config/quotas.yaml` (voir Dev Notes pour le contenu)
  - [x] Tests : fichier absent, fichier malformé (liste au lieu d'un mapping), valeur non entière isolée (repli par valeur, les autres quotas sont conservés), valeur booléenne (`apprendre: yes` ne doit pas donner un quota de 1)

- [x] Task 2 : Répartir un classement par quotas (AC: 1, 2, 3, 6)
  - [x] `repartir_par_quotas(classement: list[ItemScore], quotas: Quotas) -> list[ItemScore]` dans `src/veille/filter.py`
  - [x] Un seul passage sur `classement` (déjà trié par score décroissant par `classer()`) : compter les items retenus par registre au fur et à mesure, garder tant que le compte est sous le quota du registre — **ne jamais retrier**, l'ordre global de `classement` reste celui produit par `classer()`
  - [x] Un `item.registre` absent de `Quotas` (ne correspond à aucun des trois champs) est **conservé sans être compté contre aucun quota**, avec un avertissement journalisé une fois — jamais écarté silencieusement (AC6)
  - [x] `RapportQuotas` (dataclass frozen) : `retenus_par_registre: dict[str, int]`, `ecartes_par_registre: dict[str, int]`, méthode `resume()` — la fonction `_par_source` existante a été généralisée en `_ventilation` (elle ne dépendait d'aucun nom de champ), réutilisée pour les écarts par registre
  - [x] Tests : quota respecté par registre, jour creux (moins d'items qu'un quota → moins d'entrées, jamais de remplissage), ordre par score préservé à l'intérieur d'un registre, registre inconnu conservé + avertissement journalisé, égalité de score départagée de façon stable (aucun ordre aléatoire — leçon Story 1.3/1.4)

- [x] Task 3 : Brancher dans la collecte et rendre compte (AC: 1, 4, 5)
  - [x] Insérer l'appel à `repartir_par_quotas` juste après `classer()` dans `collecter()` (`src/veille/collect.py`) — dernière étape du pipeline de filtrage pour cette story
  - [x] Étendre `ResultatCollecte` d'un champ `quotas: RapportQuotas`, et `resume()` pour l'afficher (sur le modèle de la section `classement` déjà présente)
  - [x] `nb_retenus` de `RapportSource` doit continuer de refléter la contribution **finale** au digest (après quotas compris) — cohérent avec sa redéfinition en Story 1.4, ne pas laisser deux sens coexister
  - [x] ⚠️ **Point critique, appris en revue de la Story 1.4** : `tests/conftest.py` étendu pour neutraliser aussi `config/quotas.yaml` (quotas 1000/1000/1000), dans le même mouvement que le branchement — pas dans un correctif de revue séparé
  - [x] **Tests d'intégration empruntant le chemin réel** depuis `config/quotas.yaml`, à l'image de `TestScoringEffectif`/`TestSeuilDeSignalSurLeSocle` de la Story 1.4 (`tests/test_collecte_integration.py::TestQuotasEffectifs`) — pas seulement des appels directs à `repartir_par_quotas`
  - [x] Consigner en Completion Notes la confirmation du comportement de réassignation `langue`/`registre` par le dédoublonnage (pointeur explicite laissé par la revue de la Story 1.3 — voir Dev Notes) : comportement conservé tel quel, ou changement décidé et justifié — voir Completion Notes
  - [x] *(ajout, hors périmètre initial mais nécessaire)* Diagnostic « source absorbée » étendu pour nommer un quota de registre dépassé comme cause possible — `RapportQuotas` porte désormais aussi `ecartes_par_source` (détail interne, non exigé par l'AC qui ne demande que « par registre »), sans quoi ce diagnostic aurait régressé vers « cause indéterminée » pour une cause pourtant connue

- [x] Task 4 : Validation (AC: 1, 2, 3, 4, 6)
  - [x] Suite complète verte — **213 tests**
  - [x] **Audit par mutation, configuration comprise** — 4 mutants éprouvés. **Deux ont d'abord survécu** (quota neutralisé à 0, quota rendu très large : `211 passed` chacun, sans échec) : `conftest.py` fournit toujours un fichier de quotas explicite, donc les *défauts de la dataclass* `Quotas` n'étaient exercés par aucun test avec une assertion absolue — exactement la classe de trou signalée en Dev Notes, reproduite malgré l'avertissement. Comblé par un test d'assertion en dur sur les défauts (`Quotas().apprendre == 3`, etc.) et un garde-fou sur `config/quotas.yaml` réel (miroir de celui de `scoring.yaml`, Story 1.4) — un troisième mutant (`config/quotas.yaml` supprimé) survivait aussi avant ce garde-fou. Les 4 mutants meurent maintenant (`repartir_par_quotas` court-circuitée : 9 échecs ; les trois autres : 1 échec chacun). Suite restaurée et revérifiée verte.
  - [x] Exécution réelle de plausibilité — ⚠️ **rectifie une affirmation fausse du premier passage**, trouvée en revue : ce point prétendait « par le chemin de production, sans override de chemin », alors qu'un `sources_path` fabriqué avait en réalité été passé (3 sources, avec `openai-news` ré-étiqueté à tort en `pour_le_metier` — sa vraie valeur en production est `ce_qui_bouge`). **Répétition exacte du défaut déjà corrigé en Story 1.4.** Rejoué honnêtement via `collecter()` **sans aucun override**, contre le vrai `config/sources.yaml` (réseau réel) : `apprendre=3, ce_qui_bouge=3 retenu(s)` — le quota s'applique correctement sur les deux registres réellement peuplés. `pour_le_metier` n'apparaît dans aucune ligne du récapitulatif, pour une raison structurelle et non liée à cette story : **`config/sources.yaml` (inchangé ici) ne déclare aucune source dans ce registre** — vérifié (`grep registre: config/sources.yaml`), reporté dans `deferred-work.md`

### Review Findings

> Revue de code du 2026-08-28 (skill `bmad-code-review`, 3 couches adversariales, **sur
> Sonnet 5** — implémentation et revue faites par le même modèle cette fois, sur demande
> explicite d'Abdoulaye). Base de diff `5b59e64`. Tous les constats ont été **revérifiés par
> exécution** avant classement, y compris ceux qui me concernaient directement.

**Le plus sérieux : ma propre note de plausibilité était fausse — répétition d'un défaut déjà corrigé en Story 1.4.**
L'Acceptance Auditor a démontré, par exécution réelle contre le vrai `config/sources.yaml`, que la note de Task 4 affirmant « par le chemin de production, sans override de chemin » décrivait en fait un socle fabriqué (3 sources ad hoc, `openai-news` ré-étiqueté à tort en `pour_le_metier`). Revérifié moi-même : `grep registre: config/sources.yaml` confirme que ce fichier — inchangé par cette story — ne déclare **aucune** source en `pour_le_metier`, sur aucun commit. Corrigé en Task 4 (voir ci-dessus) : la note décrit maintenant honnêtement une exécution réelle sans aucun override, et signale la cause structurelle (reportée ci-dessous).

**Correctifs appliqués (5) :**

- [x] [Review][Patch] `RapportQuotas.resume()` produit une chaîne cassée (`'Quotas :  retenu(s)'`, champ vide) quand un quota à `0` vide entièrement un registre présent cette nuit-là (`retenus_par_registre` vide mais `total_ecartes` non nul) — corrigé : message dédié « aucun item retenu » dans ce cas [src/veille/filter.py, `RapportQuotas.resume()`]
- [x] [Review][Patch] `quotas: 0`/`[]`/`false`/`''` (valeur falsy mais mal typée) ne déclenchait aucun avertissement, contrairement à une valeur truthy tout aussi mal typée (`quotas: 5`) — cause : `.get("quotas") or {}` masquait la valeur falsy avant le contrôle de type. Corrigé (`.get("quotas", {})`), **et le même défaut corrigé par cohérence dans `charger_ponderations`** (`ponderations: 0`), qui partageait exactement le même motif [src/veille/filter.py, `charger_quotas`/`charger_ponderations`]
- [x] [Review][Patch] Une clé inconnue sous `quotas:` (faute de frappe dans le nom d'un registre) était perdue sans le moindre avertissement, contrairement à une valeur mal typée pour une clé reconnue — asymétrie corrigée par `_avertir_cles_inconnues`, **appliquée aussi à `charger_ponderations`** par cohérence [src/veille/filter.py]
- [x] [Review][Patch] `charger_quotas(None)`/`charger_ponderations(None)` levaient `TypeError` non interceptée, contredisant leur propre docstring (« ne lève jamais ») — non atteignable via `collecter()` aujourd'hui, mais fonctions publiques dont le contrat était rompu ; `TypeError` ajoutée aux exceptions capturées dans les deux fonctions [src/veille/filter.py]
- [x] [Review][Patch] `item.registre is None` produisait le même message qu'un registre valide mais non configuré (« Registre 'None' absent... »), ne permettant pas de distinguer une donnée mal formée en amont d'une absence de réglage volontaire — message dédié ajouté, comportement (conservé sans limite) inchangé [src/veille/filter.py, `repartir_par_quotas`]

**Reporté (1) :**

- [x] [Review][Defer] `rapport_quotas`/`rapport_classement` sur-comptent si le même objet `Item` apparaît plusieurs fois dans `classement` (diffing par `id()`) — non atteignable via `collecter()` (`dedup.py` garantit l'unicité d'un `Item` gagnant), précondition non documentée avant cette revue. Reporté : redesign (diffing par position plutôt que par identité) hors périmètre de cette story pour un cas non exploitable aujourd'hui ; précondition documentée dans les deux docstrings dans l'intervalle. Ajouté à `deferred-work.md`.

**Rejetés comme bruit (3) :**

- `Quotas` fixe 3 champs en dur plutôt qu'un mapping ouvert (tension apparente avec AD-3) — le relecteur lui-même l'a correctement identifié comme probablement intentionnel : FR-6 fixe une taxonomie à 3 registres (Apprendre/Ce qui bouge/Pour le métier), ce n'est pas un réglage à ouvrir.
- Nuance sur le compte exact de mutants selon où précisément `repartir_par_quotas` est court-circuitée (corps de fonction vs site d'appel) — la story n'affirmait rien de faux pour le mutant réellement testé (corps de fonction, 9 échecs reproduits à l'identique par l'auditeur).
- Tension AD-1 (`collect.py` appelle directement `filter.py`) — déjà identifiée et explicitement différée à la Story 1.8 dans les Dev Notes de cette story avant même la revue ; confirmée non aggravée par ce diff.

**Décision produit non actionnable ici, reportée (1) :**

- [x] [Review][Defer] `pour_le_metier` est structurellement toujours vide dans le socle réel actuel (`config/sources.yaml` : 4 sources, 0 en `pour_le_metier`) — pré-existant, non introduit par cette story (ni par cette story ni par le mécanisme de quotas, qui fonctionne correctement sur les registres réellement peuplés). `RapportQuotas.resume()` ne peut pas signaler cette absence structurelle : elle n'a aucune ligne à produire pour un registre qui ne reçoit jamais d'item, à la différence d'AC6 (registre inconnu de `quotas.yaml`, lui bien signalé). Reporté à l'**Epic 2** (élargissement du socle à 15-20 sources), où une source relevant de l'emploi/carrière devrait naturellement combler ce registre. Ajouté à `deferred-work.md`.

Suite complète revérifiée verte après application des correctifs : **221 tests** (213 avant revue).

## Dev Notes

### Où s'insère cette story dans le pipeline

Pipeline de filtrage tel qu'il existe après la Story 1.4 (voir [1-4-scoring-par-profil.md](1-4-scoring-par-profil.md) et son amendement du 2026-08-28 à l'ordre des étapes) :

```
collecte → seuil de signal → dédoublonnage → scoring par profil (classer()) → [CETTE STORY : quotas]
```

`classer()` retourne déjà un `list[ItemScore]` trié par score décroissant, bruit déjà écarté. Cette story ajoute la **dernière** étape de filtrage avant les accroches (Story 1.6) : répartir ce classement unique en (au plus) trois sous-listes bornées par registre, sans jamais retrier ni dupliquer.

### `filter.py` est le bon fichier, pas un nouveau module

La Structural Seed de l'architecture assigne explicitement `filter.py` à FR-4/5/6 (« signal → pertinence → quotas »). Les Stories 1.4 (FR-4/5) ont déjà posé `Ponderations`/`charger_ponderations`, `Score`/`scorer`, `ItemScore`/`classer` dans ce module. Cette story (FR-6) suit exactement le même patron plutôt que d'introduire un module `quotas.py` séparé — cohérence avec l'intention originale de la spine, et réutilisation directe des types déjà en place (`ItemScore`, `Item.registre`).

### Modèle à reproduire : `charger_ponderations` / `Ponderations`

`charger_quotas`/`Quotas` doit suivre *exactement* le même patron que `charger_ponderations`/`Ponderations` (`src/veille/filter.py`), qui a déjà résolu tous les pièges applicables ici :
- valeurs par défaut sur la dataclass elle-même (pas codées ailleurs) ;
- lecture YAML tolérante : fichier absent, illisible (y compris `UnicodeDecodeError` — piège trouvé en revue de la Story 1.4, coûteux car hors isolation de panne), malformé (racine non-mapping) → objet par défaut ;
- **repli par valeur, pas global** : une seule clé invalide ne doit pas réinitialiser les autres (voir `_ponderation()` et son usage dans `charger_ponderations`) ;
- rejeter les booléens (`apprendre: yes` vaut `True` en YAML 1.1) et les valeurs non finies — réutiliser `to_float_fini` de `config.py` n'est pas directement adapté ici (les quotas sont des `int`, pas des `float`), donc écrire l'équivalent entier ou adapter la validation en conséquence : un quota négatif ou non entier doit aussi retomber sur le défaut.

### Hors périmètre — ne pas anticiper

`filter.py` couvre FR-4/5/6 en totalité après cette story ; **FR-6 (quotas) est tout ce qu'elle livre**. Restent explicitement hors périmètre :
- les accroches en français et tout appel LLM (FR-7/8, frontière LLM unique AD-7) — Story 1.6 ;
- le rendu HTML/Markdown et la publication — Story 1.8, où `pipeline.py` sera aussi créé (voir `deferred-work.md`, item AD-1 reporté à cette story) ;
- `Score.motifs` (explicabilité) — déjà reporté à la Story 1.8, aucun changement à apporter ici.

### Pointeur explicite laissé par la Story 1.3 : la réassignation `langue`/`registre` par le dédoublonnage

`dedupliquer()` (`src/veille/dedup.py`) fait porter à l'entrée retenue la `langue` et le `registre` de la source **gagnante** de l'arbitrage, pas nécessairement ceux de l'article original. La revue de la Story 1.3 avait explicitement noté ce point comme comportement voulu mais **« à revérifier quand les quotas par section arriveront (Story 1.5) »** — c'est cette story. Implication concrète : le `registre` sur lequel `repartir_par_quotas` compte un item est celui de la source qui a remporté le dédoublonnage, pas forcément celui de la source primaire qui a publié l'article en premier. Comportement à conserver tel quel (aucune AC ne le remet en cause), mais à consigner explicitement dans les Completion Notes de cette story — ne pas laisser ce pointeur sans réponse une deuxième fois.

### Ne jamais retrier — un seul passage suffit

`classer()` a déjà trié tout le classement par score décroissant, tous registres confondus. Pour répartir par quotas sans perdre cet ordre ni le recalculer : itérer une seule fois sur `classement` dans l'ordre où il arrive, incrémenter un compteur par registre, garder l'item tant que son compteur est strictement sous le quota de son registre. Le sous-ensemble des items d'un même registre, pris dans l'ordre d'itération, reste trié par score décroissant — sans second tri, sans clé de comparaison supplémentaire. C'est la même logique de « filtre à un seul passage » que `filtrer_par_signal` (Story 1.4).

### Piège déjà rencontré deux fois : ne jamais faire disparaître silencieusement du contenu légitime

AC2 de la Story 1.4 posait la règle pour le signal absent (« l'absence de donnée n'est pas une insuffisance ») ; AC6 de cette story pose son équivalent pour les quotas. Un `item.registre` qui ne correspondrait à aucun des trois champs de `Quotas` — cas limite improbable puisque `SourceConfig.registre` est déjà validé par `test_socle_reel.py::test_les_registres_sont_valides`, mais qui doit rester géré défensivement, car le code de `filter.py` ne doit pas supposer que cette garantie amont tiendra indéfiniment — doit être **conservé** dans le résultat final, pas supprimé, avec un avertissement journalisé.

### ⚠️ Risque de régression majeur : `conftest.py`

`tests/conftest.py` (créé en revue de la Story 1.4) neutralise aujourd'hui `DEFAULT_PROFIL_PATH` et `DEFAULT_SCORING_PATH` par défaut pour tous les tests, via une fixture `autouse`. Le jour où `repartir_par_quotas` est branché dans `collecter()` avec un défaut de 3/3/2, **tout test existant qui compte des items exacts sans préciser de configuration de quotas se mettra à échouer** — pas parce que son comportement testé est cassé, mais parce que le résultat est tronqué par une étape dont ce test n'a jamais entendu parler. C'est exactement la classe de défaut que la revue de la Story 1.4 a dû corriger après coup pour le profil et les pondérations ; ne pas la répéter une troisième fois. `conftest.py` doit neutraliser `DEFAULT_QUOTAS_PATH` (quotas très larges, ex. 1000 par registre) **dans le même mouvement** que cette story introduit le nouveau chemin par défaut — pas dans un correctif de revue séparé.

### Leçon la plus coûteuse de la Story 1.4 : l'audit par mutation doit couvrir la configuration

Le premier audit par mutation de la Story 1.4 ne portait que sur le code (`filter.py`) et déclarait la suite robuste, alors que 4 mutants de **configuration** survivaient (`seuil_signal`/`mapping.signal` retirés de `sources.yaml`, `scoring.yaml` supprimé, sa lecture neutralisée) — ce qui a directement permis à un défaut réel (AC5 non satisfait) de passer inaperçu jusqu'à la revue. Cette story introduit un nouveau fichier de configuration (`quotas.yaml`) : l'audit par mutation de la Task 4 doit le couvrir dès la première passe, pas après une revue qui le découvre.

### Structure de fichiers

```text
config/
  quotas.yaml            # NOUVEAU — quotas par registre
src/veille/
  filter.py               # MODIFIÉ — Quotas, charger_quotas, repartir_par_quotas, RapportQuotas
  collect.py              # MODIFIÉ — quotas branchés après classer(), ResultatCollecte étendu
tests/
  conftest.py             # MODIFIÉ — neutralise aussi les quotas par défaut
  test_filter.py          # MODIFIÉ — tests de charger_quotas et repartir_par_quotas
  test_collecte_integration.py  # MODIFIÉ — chemin réel config/quotas.yaml → collecter()
```

### Contenu indicatif de `config/quotas.yaml`

```yaml
# Quotas par section du digest (AD-3, Story 1.5).
#
# Modifier une valeur ici change la répartition sans toucher au code. Un
# registre avec moins d'items disponibles que son quota affiche moins
# d'entrées — jamais de remplissage artificiel.

quotas:
  apprendre: 3
  ce_qui_bouge: 3
  pour_le_metier: 2
```

### Testing Standards

- `pytest`, via `uv run pytest`. Aucun appel réseau.
- **Tests d'intégration obligatoires** depuis `config/quotas.yaml` réel, en plus des tests unitaires directs sur `repartir_par_quotas` (leçon Story 1.3, réaffirmée à chaque story depuis).
- **Audit par mutation en Task 4, configuration comprise** — voir Dev Notes ci-dessus.
- Vérifier explicitement que `tests/conftest.py` neutralise bien les trois fichiers de configuration (`profil.md`, `scoring.yaml`, `quotas.yaml`) avant de considérer la Task 3 terminée : lancer la suite complète après le branchement et confirmer qu'aucun test préexistant ne régresse sur un compte d'items.

### Previous Story Intelligence (Story 1.4)

- Pipeline final : collecte → seuil de signal → dédoublonnage → scoring. Cette story ajoute l'étape suivante, pas une réorganisation.
- `ItemScore(item: Item, score: Score)` est le type produit par `classer()` ; `Item.registre` est directement accessible sans passer par `Score`.
- `charger_ponderations`/`Ponderations` est le patron de référence pour tout chargement de configuration numérique tolérant aux fautes de frappe (voir Dev Notes ci-dessus) — ne pas réinventer une autre convention.
- `tests/conftest.py` existe déjà et neutralise `profil.md`/`scoring.yaml` — à étendre, pas à contourner.
- Convention de revue désormais actée : la revue de code tourne sur un modèle différent de celui qui implémente, et l'audit par mutation doit couvrir la configuration dès la première passe.
- Rapport de projet vivant : `docs/rapport-projet.md` à mettre à jour à la fin de cette story (dev + revue) — voir sa section 10 « Prochaine étape » qui pointe déjà vers cette story.

### Git Intelligence Summary

Commits récents (`git log --oneline -6`) : `Story 1.4 — filtrage par signal et scoring par profil` (implémentation + correctifs de revue en un seul commit) suivi de `Documentation : rapport de projet vivant` (commit séparé). Convention à reproduire pour cette story : un commit pour l'implémentation + revue de la Story 1.5, un commit séparé si `docs/rapport-projet.md` est mis à jour dans la foulée.

### Project Structure Notes

Aucun conflit détecté avec la Structural Seed : `filter.py` est le fichier prévu pour FR-6, `config/quotas.yaml` suit la convention déjà en place (`profil.md`, `scoring.yaml`).

### References

- [Source: epics.md#Story-1.5] — story d'origine et critères d'acceptation
- [Source: prd.md#FR-6] — quotas par section, configurables, jamais de remplissage
- [Source: ARCHITECTURE-SPINE.md#AD-3] — configuration jamais en dur
- [Source: ARCHITECTURE-SPINE.md#Structural-Seed] — `filter.py` couvre FR-4/5/6
- [Source: 1-4-scoring-par-profil.md] — patron `charger_ponderations`/`Ponderations`, pipeline de filtrage, leçon sur l'audit par mutation et `conftest.py`
- [Source: 1-3-dedoublonnage.md#Review-Findings] — pointeur explicite sur la réassignation `langue`/`registre` par le dédoublonnage, adressé à cette story
- [Source: deferred-work.md#code-review-of-1-4] — absence de tri par fraîcheur reportée aux quotas ; `Score.motifs` et `pipeline.py` reportés à la Story 1.8, hors périmètre ici
- [Source: docs/rapport-projet.md#10] — prochaine étape déjà annoncée, points d'attention

## Dev Agent Record

### Agent Model Used

Implémentation **et** revue de code : Claude Sonnet 5 (`claude-sonnet-5`), via les skills `bmad-dev-story` puis `bmad-code-review` — sur demande explicite d'Abdoulaye de rester sur Sonnet pour cette story plutôt que de changer de modèle pour la revue.

### Debug Log References

Aucun blocage à l'implémentation. Audit par mutation (Task 4) : 2 mutants survivants à la première passe (défauts de `Quotas` neutralisés à 0 ou rendus très larges — 211 passed chacun, aucun échec) et un troisième latent (`config/quotas.yaml` supprimé, également 211 passed) ; comblés par un test d'assertion en dur sur les défauts et un garde-fou sur le fichier réel, avant de reconfirmer les 4 mutants tués.

Revue de code : 3 couches adversariales, 9 findings normalisés → 5 correctifs, 2 reports, 3 rejets. Le plus sérieux concernait ma propre note de plausibilité (Task 4), fausse — voir Review Findings et Completion Notes.

### Completion Notes List

- **Patron `charger_ponderations`/`Ponderations` reproduit à l'identique** pour `charger_quotas`/`Quotas` : repli par valeur (pas global), rejet des booléens, `UnicodeDecodeError` couverte. Différence : les quotas sont des `int`, validés par un helper dédié `_to_int_positif` (rejette aussi les valeurs négatives et non entières, ce qu'un simple `to_float_fini` de `config.py` n'aurait pas couvert correctement).
- **`repartir_par_quotas` en un seul passage** sur `classement` (déjà trié par `classer()`), jamais retrié — un compteur par registre suffit. Suit le rapport séparément (`rapport_quotas`, diff par identité d'objet) plutôt qu'un tuple `(liste, rapport)`, pour rester cohérent avec la paire `classer`/`rapport_classement` de la Story 1.4.
- **`_par_source` généralisée en `_ventilation`** : la fonction ne dépendait d'aucun nom de champ, elle sert désormais aussi bien aux pertes par source (signal, bruit) qu'aux pertes par registre (quotas).
- **`conftest.py` étendu dans le même mouvement** que le branchement des quotas dans `collecter()` (neutralisation à 1000/1000/1000) — pas laissé pour une revue ultérieure, contrairement à ce qui s'était passé pour le profil et les pondérations en Story 1.4.
- **`RapportQuotas` porte un champ de plus que ce que l'AC exige** (`ecartes_par_source`, en plus de `retenus_par_registre`/`ecartes_par_registre`) : sans lui, le diagnostic « source absorbée » de `collect.py` (qui nomme désormais aussi « quota de registre dépassé » comme cause possible) n'aurait pas pu attribuer une perte de quota à une source précise, et aurait régressé vers « cause indéterminée » — une cause pourtant connue.
- **Pointeur de la Story 1.3 traité** : `dedupliquer()` fait toujours porter à l'entrée retenue la `langue`/le `registre` de la source gagnante de l'arbitrage (l'Item entier de la source gagnante est conservé tel quel, aucun champ n'est fusionné depuis un autre). Comportement **conservé sans changement** — c'est exactement ce que `repartir_par_quotas` doit lire pour compter un item dans le bon registre, et aucune AC de cette story ne le remet en cause.
- **Audit par mutation initialement incomplet, comme en Story 1.4** : les mutants sur les valeurs par défaut de `Quotas` et sur la suppression de `config/quotas.yaml` survivaient tous deux à la première passe, parce que `conftest.py` fournit systématiquement un fichier de quotas explicite aux tests — les défauts de la dataclass n'étaient donc exercés par aucune assertion absolue. Comblé avant de considérer la Task 4 terminée (voir Debug Log References). Averti dans les Dev Notes de la story, reproduit quand même une fois — signe que ce type de garde-fou doit devenir un réflexe systématique dès l'écriture des tests, pas seulement au moment de l'audit.
- **213 tests passent** (189 avant cette story, 24 nouveaux/étendus pour la Story 1.5) — **221 après revue** (+8 tests de régression sur les correctifs).

> **Après revue (2026-08-28), même modèle.** La revue a trouvé que ma propre note de plausibilité (ci-dessus, Task 4) était **fausse** — elle prétendait « aucun override de chemin » alors qu'un socle fabriqué avait été utilisé, avec `openai-news` ré-étiqueté à tort en `pour_le_metier`. C'est exactement le défaut déjà corrigé en Story 1.4 (« ne pas répéter l'erreur… où la première vérification avait utilisé un socle ad hoc ») — répété malgré l'avoir explicitement écrit dans mes propres Dev Notes comme piège à éviter. Rejoué honnêtement sans aucun override : le vrai `config/sources.yaml` ne déclare aucune source `pour_le_metier`, un fait structurel préexistant, pas un défaut du mécanisme de quotas (qui fonctionne correctement sur les deux registres réellement peuplés). Corrigé dans Task 4 et reporté dans `deferred-work.md` (Epic 2).
> Cinq autres correctifs appliqués : un formatage cassé dans `RapportQuotas.resume()` (quota à 0 vidant tout un registre), deux asymétries de validation dans `charger_quotas`/`charger_ponderations` (valeur falsy mal typée non signalée, clé inconnue perdue en silence — corrigées dans les deux fonctions par cohérence), un contrat rompu (`charger_quotas(None)`/`charger_ponderations(None)` levaient au lieu de dégrader), et un message de diagnostic ambigu (`registre=None`). Un point reporté : `rapport_quotas`/`rapport_classement` sur-comptent en théorie si le même objet `Item` apparaît deux fois dans leur entrée (non atteignable via `collecter()`, précondition désormais documentée).

### File List

**Code :**
- `src/veille/filter.py` — modifié : `Quotas`, `charger_quotas`, `_quota`, `_to_int_positif`, `repartir_par_quotas`, `RapportQuotas`, `rapport_quotas` ; `_par_source` renommée `_ventilation` (généralisée) ; **(revue)** `_avertir_cles_inconnues`, correctifs sur `charger_quotas`/`charger_ponderations` (valeur falsy, clé inconnue, `None`, formatage `resume()`, message `registre=None`)
- `src/veille/collect.py` — modifié : quotas branchés après `classer()` dans `collecter()` (nouveau paramètre `quotas_path`) ; `ResultatCollecte` étendu (`quotas: RapportQuotas`) ; `resume()` étendu ; diagnostic « source absorbée » étendu au motif « quota de registre dépassé »

**Configuration :**
- `config/quotas.yaml` — nouveau : quotas par registre (3/3/2)

**Tests :**
- `tests/conftest.py` — modifié : neutralise aussi `DEFAULT_QUOTAS_PATH` (1000/1000/1000)
- `tests/test_filter.py` — étendu : chargement des quotas, répartition, rapport, garde-fou sur les valeurs par défaut ; **(revue)** 8 tests de régression sur les correctifs
- `tests/test_socle_reel.py` — étendu : garde-fou sur `config/quotas.yaml` réel
- `tests/test_collecte_integration.py` — étendu : `TestQuotasEffectifs` (chemin réel `config/quotas.yaml` → `collecter()`, diagnostic de source absorbée par quota)

**Documentation :**
- `_bmad-output/implementation-artifacts/deferred-work.md` — modifié (revue) : 2 éléments reportés (registre `pour_le_metier` structurellement vide ; précondition d'identité de `rapport_quotas`/`rapport_classement`)

### Change Log

| Date | Résumé |
|---|---|
| 2026-08-28 | Implémentation complète (Tasks 1-4) : `Quotas`/`charger_quotas` sur le patron de `Ponderations`, `repartir_par_quotas` à un seul passage, branchement dans `collecter()`, `conftest.py` étendu dans le même mouvement. Audit par mutation initialement incomplet (2 mutants de défauts + 1 de configuration survivants), comblé avant complétion. 213 tests. Statut `review`. |
| 2026-08-28 | Revue de code (Sonnet 5, 3 couches). 5 correctifs, 2 reportés, 3 rejetés. **Trouvaille principale : ma propre note de plausibilité était fausse** (socle fabriqué présenté comme chemin de production) — corrigée, rejouée honnêtement contre le vrai socle. 221 tests. Statut `done`. |
