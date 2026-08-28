---
baseline_commit: 4a92a4f
---

# Story 1.7: Signaler les entrées à ne pas manquer

Status: done

## Story

As a Abdoulaye,
I want qu'une entrée soit mise en avant quand elle le mérite vraiment,
so that je sais où porter mon attention en priorité.

## Acceptance Criteria

1. **[FR-8]** Étant donné un classement du jour (`list[ItemScore]`, sortie de `classer()`/`repartir_par_quotas()` — Story 1.4/1.5), si le score du meilleur item dépasse celui du second d'au moins une marge configurée, l'`Entree` correspondante porte `recommandee=True`.
2. **[FR-8]** Si aucun item ne dépasse le second d'au moins cette marge (scores proches, égalité, ou moins de deux items), **aucune** entrée n'est recommandée — « aucune recommandation n'est forcée un jour où rien ne le justifie vraiment ».
3. **[FR-8]** Au plus **une** entrée est recommandée par jour.
4. **[FR-8]** La marge est déclarée en configuration (`config/scoring.yaml`), modifiable sans toucher au code.
5. Le mécanisme n'appelle **jamais** l'API Claude — purement déterministe, basé sur le `Score.valeur` déjà calculé par `filter.py` (Story 1.4). Cohérent avec AD-7 : le seul point d'appel LLM reste `generer_accroche` (Story 1.6), inchangé par cette story.
6. `enrichir()` (Story 1.6) **n'est pas modifié dans sa signature** — aucune régression sur ses 19 tests existants. La recommandation est déterminée par une fonction séparée, appliquée après coup sur les `Entree` déjà produites.

## Tasks / Subtasks

- [x] Task 1 : Ajouter `recommandee` au type `Entrée` (AC: 1, 2, 3)
  - [x] Ajouter `recommandee: bool = False` à `Entree` (`src/veille/models.py`) — défaut `False`, jamais forcé
  - [x] Tests : construction avec et sans `recommandee`, immutabilité inchangée

- [x] Task 2 : Étendre `Ponderations` avec la marge de recommandation (AC: 4)
  - [x] Ajouter `marge_recommandation: float = 10.0` à `Ponderations` (`src/veille/filter.py`) — voir Dev Notes pour la justification de la valeur
  - [x] Étendre `charger_ponderations` pour lire `marge_recommandation` à la racine de `scoring.yaml` (même emplacement que `seuil_bruit`), même patron de repli par valeur
  - [x] Documenter le nouveau champ dans `config/scoring.yaml`
  - [x] Tests : absent → défaut ; présent et valide → pris en compte ; invalide → repli sans affecter les autres champs

- [x] Task 3 : Déterminer l'entrée recommandée du jour (AC: 1, 2, 3, 5)
  - [x] `determiner_recommandation(classement: list[ItemScore], ponderations: Ponderations = Ponderations()) -> ItemScore | None` dans `src/veille/enrich/llm.py`
  - [x] Règle : `classement` supposé déjà trié par `classer()`, jamais retrié ; s'il y a au moins 2 items et que `premier.score.valeur - second.score.valeur >= ponderations.marge_recommandation`, retourner le premier ; sinon `None`
  - [x] Moins de 2 items → toujours `None`
  - [x] Aucun appel API — fonction pure, déterministe, testée sans client
  - [x] Tests : marge dépassée, marge non dépassée, scores égaux, un seul item, liste vide, égalité exacte à la marge (`>=`), marge personnalisée, non-retri vérifié explicitement

- [x] Task 4 : Marquer la recommandation sur les `Entree` (AC: 1, 2, 3, 6)
  - [x] `marquer_recommandation(entrees: list[Entree], classement: list[ItemScore], ponderations: Ponderations = Ponderations()) -> list[Entree]` dans `src/veille/enrich/llm.py`
  - [x] Correspondance par **identité d'objet** (`id(entree.item) == id(item_score.item)`)
  - [x] Retourne une nouvelle liste : `dataclasses.replace(entree, recommandee=True)` pour l'entrée gagnante, les autres `Entree` inchangées (mêmes objets)
  - [x] N'appelle ni ne modifie `enrichir()` — zéro régression sur la Story 1.6 (32 tests dans `test_llm.py`, dont les 19 de la Story 1.6 toujours verts)
  - [x] `None`/listes désynchronisées → `entrees` inchangée, ne lève jamais
  - [x] Tests : entrée marquée, aucune marquée, ordre différent entre `entrees`/`classement`, liste vide, non-modification des entrées non gagnantes (identité d'objet vérifiée)

- [x] Task 5 : Validation (AC: 1, 2, 3, 4, 5, 6)
  - [x] Suite complète verte, **aucune régression** sur les tests existants de `enrich/llm.py` (Story 1.6) ni d'ailleurs — 260 passed
  - [x] Aucun appel réseau/API dans les tests de cette story (fonction pure, pas besoin de client simulé)
  - [x] Audit par mutation : marge neutralisée à 0, marge rendue énorme, `determiner_recommandation` court-circuitée à `None`, et `config/scoring.yaml` sans `marge_recommandation` — les 3 premiers tuent la suite immédiatement ; le 4ᵉ (config) **a survécu à la première passe** (voir Completion Notes) et a été corrigé avant de cocher cette tâche
  - [x] Exécution réelle (sans API) : `determiner_recommandation`/`marquer_recommandation` exercées sur un classement construit à la main (3 `ItemScore`, via `charger_ponderations()` réel) — un jour avec un net leader (35 vs 10 vs 8, marge 25 ≥ 10) recommande exactement l'item attendu ; un jour sans standout (12 vs 8 vs 5, marge 4 < 10) ne recommande personne ; appliqué via `marquer_recommandation` sur des `Entree` produites par `enrichir()`, exactement une entrée ressort `recommandee=True`

### Review Findings

> Revue de code du 2026-08-28 (skill `bmad-code-review`, 3 couches adversariales, sur
> Sonnet 5 — même modèle que l'implémentation, sur demande explicite d'Abdoulaye).
> Base de diff `4a92a4f`. Les 3 couches ont convergé indépendamment sur le même
> constat le plus sérieux (absence de garde-fou de signe sur `marge_recommandation`),
> revérifié par exécution (rouge avant correctif, vert après) avant classement.

**Correctifs appliqués (6) :**

- [x] [Review][Patch] `marge_recommandation` acceptait silencieusement une valeur nulle ou négative — `premier.score.valeur - second.score.valeur >= 0` est toujours vrai (`classement` trié décroissant), donc une marge ≤ 0 aurait forcé une recommandation tous les jours, y compris à égalité exacte, en contradiction directe avec l'AC2 (« égalité jamais recommandée ») — constat convergent des 3 couches. Corrigé par un paramètre `positif_strict` sur `_ponderation`, activé seulement pour `marge_recommandation` (`bruit`/`seuil_bruit` restent légitimement négatifs) [src/veille/filter.py, `_ponderation`/`charger_ponderations`]
- [x] [Review][Patch] `marquer_recommandation` reprend la convention d'identité d'objet de `rapport_classement`/`rapport_quotas` (`filter.py`) sans reprendre leur mise en garde documentée sur la précondition non vérifiée (deux `Entree` référençant le même `Item` basculeraient toutes deux à `True`, au-delà de l'AC3) — la docstring citait ces deux fonctions comme patron à réutiliser mais omettait ce point ; caveat ajouté, mot pour mot dans le même esprit que l'original [src/veille/enrich/llm.py, `marquer_recommandation`]
- [x] [Review][Patch] `test_charger_ponderations_marge_invalide_retombe_sur_le_defaut_sans_affecter_le_reste` ne vérifiait que `bruit` alors que son nom promettait « sans affecter le reste » — étendu à `prioritaire`, `signal_fort`, `domaine`, `secondaire`, `seuil_bruit` [tests/test_filter.py]
- [x] [Review][Patch] Le repli documenté de `marquer_recommandation` sur listes désynchronisées (gagnant du `classement` sans `Entree` correspondante) n'était jamais exercé par un test — ajouté [tests/test_llm.py]
- [x] [Review][Patch] Le garde-fou de présence de `marge_recommandation:` ajouté en Task 5 (test de sous-chaîne) matchait aussi une ligne mise en commentaire (`# marge_recommandation: 10`), le vidant de son utilité — ancré en début de ligne via `re.search(r"^marge_recommandation:", ..., re.MULTILINE)` ; revérifié : le mutant « ligne commentée » échoue désormais comme attendu [tests/test_socle_reel.py]
- [x] [Review][Patch] Rien ne précisait, pour le câblage à venir en Story 1.8, si `determiner_recommandation` doit recevoir le classement brut (`classer()`) ou filtré par quota (`repartir_par_quotas()`) — précision ajoutée en docstring (le second : un gagnant écarté par quota n'a aucune `Entree` à marquer) [src/veille/enrich/llm.py, `determiner_recommandation`]

**Reporté (0) :** aucun.

**Rejeté comme bruit (8) :**

- « La fonctionnalité n'est branchée nulle part » (`collect.py`/`pipeline.py` n'appellent ni `enrichir()` ni les nouvelles fonctions) — par construction, documenté explicitement dans la section « Hors périmètre » de cette story : le branchement est le travail de `pipeline.py` (Story 1.8), même limite que la Story 1.6.
- « `docs/rapport-projet.md` non mis à jour » — séquencement normal : le rapport se met à jour à la fin de la revue (juste après), pas pendant. Pas un défaut du code.
- « Aucune story 1.7 localisable dans le dépôt » / « AC1-3 invérifiables » — faux positif : `_bmad-output/implementation-artifacts/1-7-recommandation-entree.md` existe bien (confirmé via `ls`), mais le dossier est gitignored (confirmé via `git check-ignore`) — invisible à une recherche limitée aux fichiers suivis par git.
- Comparaison de marge en virgule flottante sur des scores fractionnaires — vérifié contre `classer()` : `_ATTENUATION_PAR_RANG = 0.5` est une puissance de deux exacte, donc `poids * 0.5**rang` reste exactement représentable en binaire pour les poids entiers en jeu ; aucune dérive réaliste dans ce code. Ajouter une tolérance epsilon serait une complexité non justifiée, et risquerait de contredire le test d'égalité exacte à la marge (AC, `>=` strict).
- Garantie « au plus une par jour » non littéralement imposée par le code lui-même (`models.py`) — c'est un invariant d'usage en production (appeler `marquer_recommandation` une fois par run), au même titre qu'`enrichir()` ; aucune AC contredite.
- Comparaison inter-registres non examinée — choix de conception intentionnel, cohérent avec l'AC3 (« au plus une entrée par jour », pas par registre) ; aucune AC ne l'interdit.
- Absence de justification textuelle (`Score.motifs` non consommé) — déjà tranché dans les Dev Notes de cette story même (« Hors périmètre… ne pas l'ajouter maintenant ») ; répond au « à évaluer » laissé ouvert dans `rapport-projet.md` (décision à y consigner à la prochaine mise à jour).
- Justification de cohabitation de module (« la table de couverture de l'architecture ») jugée circulaire — critique de formulation d'un commentaire, sans conséquence fonctionnelle.

Suite complète revérifiée verte après application des correctifs : **263 tests** (260 avant revue).

## Dev Notes

### Pourquoi une fonction séparée plutôt qu'étendre `enrichir()`

FR-7 et FR-8 partagent la même ligne dans la table de couverture de l'architecture (`enrich/llm.py`), mais ce ne sont pas la même responsabilité : FR-7 génère un texte via l'API (un appel, un item, une panne possible) ; FR-8 compare des scores déjà connus, sur l'ensemble du lot, sans jamais toucher le réseau. Les regrouper dans la même fonction aurait forcé `enrichir()` à changer de signature (`list[Item]` → `list[ItemScore]`), cassant sans nécessité les 19 tests de la Story 1.6 pour un gain nul. Une fonction additive (`marquer_recommandation`), appliquée après `enrichir()`, obtient le même résultat sans toucher à du code qui fonctionne déjà.

### Pourquoi le score de `filter.py`, jamais un second appel LLM

Décision structurante de la Story 1.4, reconduite ici : *« Le scoring est donc lexical et local : recherche de mots-clés, coût nul, instantané, et surtout explicable… Un scoring sémantique par embeddings est une évolution possible (v2), pas un prérequis. »* Juger « nettement plus pertinente que les autres » avec un second appel LLM par jour serait un coût et une complexité que rien dans le PRD ne justifie — `Score.valeur` existe déjà, agrège déjà toutes les catégories du profil (y compris `signal_fort`, la pondération la plus élevée), et sert précisément à ça.

⚠️ **`Score.valeur` circule aujourd'hui jusqu'à `classer()`/`repartir_par_quotas()`, mais `collect.py` le jette** (`items = [item_score.item for item_score in resultats_repartis]`, `src/veille/collect.py`) — signalé comme dette dans `deferred-work.md` depuis la revue de la Story 1.4 (« `Score.motifs` calculé puis jeté »). Cette story **ne corrige pas ce point** : `enrich/llm.py` n'étant toujours pas branché dans `collect.py` (voir « Hors périmètre »), `determiner_recommandation`/`marquer_recommandation` sont testées directement sur des `list[ItemScore]` construites pour le test — exactement comme `enrichir()` l'a été en Story 1.6. Le branchement réel (collecte → filtrage → enrichissement, scores compris) reste le travail de `pipeline.py` (Story 1.8).

### Pourquoi une marge de 10, et où elle vit

`10.0` est le même ordre de grandeur qu'une seule correspondance `prioritaire` (poids 10) ou deux `domaine` (poids 5 chacun) — de sorte que l'entrée recommandée doit se démarquer par au moins l'équivalent d'un thème prioritaire de plus que la suivante, pas par un simple bruit de mesure. Valeur de départ raisonnable, pas mesurée sur données réelles (aucun volume réel de scores n'a encore été observé en production) — à ajuster dans `config/scoring.yaml` sans code si elle s'avère trop stricte ou trop permissive à l'usage.

`marge_recommandation` vit à la **racine** de `scoring.yaml`, comme `seuil_bruit` — ni l'un ni l'autre n'est une pondération par catégorie (`ponderations: {...}`), les deux sont des seuils globaux de comparaison :

```yaml
ponderations:
  prioritaire: 10
  signal_fort: 15
  domaine: 5
  secondaire: 2
  bruit: -20

seuil_bruit: -5
marge_recommandation: 10   # NOUVEAU (Story 1.7)
```

### Hors périmètre — ne pas anticiper

- **Aucun branchement dans `collect.py`/`collecter()`** — même limite que la Story 1.6 (voir ci-dessus). `pipeline.py` (Story 1.8) reliera collecte, filtrage et enrichissement (accroches + recommandation) en un seul run.
- **Aucun rendu de la marque de recommandation** (mise en forme visuelle, badge, etc.) — Story 1.8, rendu HTML/Markdown.
- **Aucune justification textuelle de la recommandation** (« pourquoi cette entrée ») — `Score.motifs` existe et pourrait nourrir ça un jour, mais aucune AC ne l'exige ici ; ne pas l'ajouter maintenant.

### Précédents à réutiliser, pas à réinventer

- **Correspondance par identité d'objet**, jamais par valeur ni par `guid` — `rapport_classement`/`rapport_quotas` (`src/veille/filter.py`, Stories 1.4/1.5) l'utilisent déjà pour comparer une entrée à sa sortie transformée. Même raison ici : deux `Item` distincts pourraient en théorie partager les mêmes champs.
- **Repli par valeur, jamais global**, pour toute nouvelle clé de configuration lue dans un fichier existant — patron déjà établi par `_ponderation`/`_quota` (Stories 1.4/1.5). Une valeur `marge_recommandation` invalide ne doit pas réinitialiser les pondérations par catégorie.
- **`_avertir_cles_inconnues`** existe déjà dans `filter.py` et couvre les clés inconnues sous `ponderations:` — `marge_recommandation` étant à la racine (comme `seuil_bruit`), elle n'a pas besoin de ce garde-fou spécifique, mais une clé mal orthographiée à la racine du fichier (`marge_recommandations` au pluriel, par exemple) ne sera pas plus détectée que ne l'était `seuil_bruit` mal orthographié avant cette story — limite préexistante, pas à corriger ici (scope creep).

### Structure de fichiers

```text
config/
  scoring.yaml            # MODIFIÉ — marge_recommandation: 10
src/veille/
  models.py               # MODIFIÉ — Entree.recommandee: bool = False
  filter.py               # MODIFIÉ — Ponderations.marge_recommandation, charger_ponderations étendu
  enrich/llm.py           # MODIFIÉ — determiner_recommandation, marquer_recommandation
tests/
  test_models.py          # MODIFIÉ
  test_filter.py           # MODIFIÉ — tests de marge_recommandation dans charger_ponderations
  test_llm.py              # MODIFIÉ — determiner_recommandation, marquer_recommandation
```

### Testing Standards

- `pytest`, via `uv run pytest`. Aucun appel réseau — cette story n'en a besoin d'aucun (à la différence de la Story 1.6).
- **Audit par mutation en Task 5, configuration comprise** — leçon des Stories 1.4/1.5, à ne pas répéter une troisième fois par omission.
- Départage stable / déterminisme : le calcul ne doit dépendre que des scores, jamais de l'ordre d'itération.

### Previous Story Intelligence (Story 1.6)

- `enrich/llm.py` existe : `_client`, `generer_accroche`, `enrichir`, plus les helpers de robustesse ajoutés en revue (`_avertir_echec_api`, bornage du titre, détection de `stop_reason`). Cette story y ajoute deux fonctions, sans toucher aux trois existantes.
- **Aucune clé `ANTHROPIC_API_KEY` n'est configurée** — sans conséquence pour cette story, qui n'appelle jamais l'API. Répond directement à la question posée par Abdoulaye : non, cette story n'a besoin d'aucune clé.
- Réflexe désormais systématique : ne jamais lever, dégrader et journaliser pour toute configuration incomplète (`charger_ponderations` l'applique déjà, à étendre au nouveau champ).
- `Entree` a été gardée volontairement minimale en Story 1.6 précisément pour laisser `recommandee` à cette story — pas de dette à rattraper de ce côté.

### Git Intelligence Summary

Commits récents : Story 1.6 (implémentation + revue en un commit), puis rapport de projet (commit séparé). Même convention à reproduire ici.

### Project Structure Notes

Aucun conflit avec la Structural Seed : `filter.py` reste le propriétaire des pondérations/seuils (FR-4/5/6 et maintenant le seuil de recommandation), `enrich/llm.py` reste le propriétaire de FR-7/8 comme la table de couverture de l'architecture l'assigne.

### References

- [Source: epics.md#Story-1.7] — story d'origine et critères d'acceptation
- [Source: prd.md#FR-8] — recommandation explicite quand le contenu le justifie
- [Source: ARCHITECTURE-SPINE.md#AD-7] — frontière LLM unique ; FR-7/8 assignées à `enrich/llm.py`
- [Source: ARCHITECTURE-SPINE.md#AD-3] — configuration, jamais en dur
- [Source: 1-4-scoring-par-profil.md] — décision « scoring lexical, jamais par LLM » ; patron `_ponderation`/repli par valeur
- [Source: 1-6-accroches-francaises.md] — `enrich/llm.py` existant, à ne pas régresser ; correspondance par identité déjà en usage dans `filter.py`
- [Source: deferred-work.md#code-review-of-1-4] — `Score.motifs`/scores jetés par `collect.py`, non corrigé ici, toujours en attente de la Story 1.8

## Dev Agent Record

### Agent Model Used

claude-sonnet-5 (Sonnet 5)

### Debug Log References

Aucun — aucune panne, aucun blocage. Le seul incident (mutant de configuration survivant) est documenté dans les Completion Notes ci-dessous, pas dans un log de debug séparé.

### Completion Notes List

- Tasks 1-4 implémentées en TDD strict (rouge confirmé par `AttributeError`/`TypeError` avant chaque implémentation, vert dès la première tentative pour chacune) : `Entree.recommandee`, `Ponderations.marge_recommandation` + lecture dans `charger_ponderations`, `determiner_recommandation`, `marquer_recommandation`.
- Décision de conception actée en Dev Notes et respectée à la lettre : `marquer_recommandation` est **additive**, appliquée après `enrichir()` — aucune modification de la signature d'`enrichir()`, donc zéro régression sur les 19 tests de la Story 1.6 (vérifié : ils sont toujours verts, inchangés).
- **Audit par mutation (Task 5)** — 4 mutants, comme prescrit par la story :
  1. `marge_recommandation` neutralisée à 0 → suite rouge (tout serait recommandé). Tué.
  2. `marge_recommandation` rendue énorme → suite rouge (rien ne serait jamais recommandé). Tué.
  3. `determiner_recommandation` court-circuitée pour toujours retourner `None` → suite rouge. Tué.
  4. `marge_recommandation: 10` retirée de `config/scoring.yaml` → **suite verte, 260 passed, aucun échec** au premier passage. **Survécu.** Cause : la valeur par défaut codée en dur dans `Ponderations` (10.0) coïncide exactement avec la valeur déclarée dans le fichier — la suppression du fichier redonne silencieusement la même valeur effective. C'est le même trou de couverture déjà trouvé en revue des Stories 1.4 et 1.5 (audit par mutation qui ne porte que sur le code, jamais sur la configuration livrée).
  - **Correctif appliqué avant de clore la tâche** : ajout d'une assertion de présence explicite de la chaîne `"marge_recommandation:"` dans le contenu brut de `config/scoring.yaml`, dans `test_le_fichier_de_ponderations_existe_et_se_charge` (`tests/test_socle_reel.py`) — détecte la suppression de la clé indépendamment de toute coïncidence de valeur par défaut. Re-testé : le mutant 4 échoue désormais (`1 failed, 259 passed`) ; fichier restauré, suite de nouveau à `260 passed`.
- **Exécution réelle sans API** (subtask dédiée de Task 5) : classement construit à la main avec 3 items via `ItemScore`/`Score`, pondérations chargées depuis le vrai `config/scoring.yaml` (`charger_ponderations()`, pas un `Ponderations()` de test) — un jour à net leader (35/10/8) recommande l'item attendu, un jour serré (12/8/5) ne recommande personne ; `marquer_recommandation` appliquée sur des `Entree` réelles produites par `enrichir()` marque exactement une entrée. Comportement plausible et conforme aux AC1-3.
- Aucun appel réseau/API dans les tests de cette story — cohérent avec AC5 (fonction pure sur des scores déjà calculés).
- Suite complète finale : `260 passed`, aucune régression.

### File List

- `config/scoring.yaml` — MODIFIÉ (ajout `marge_recommandation: 10` + commentaire)
- `src/veille/models.py` — MODIFIÉ (`Entree.recommandee: bool = False`)
- `src/veille/filter.py` — MODIFIÉ (`Ponderations.marge_recommandation`, lecture dans `charger_ponderations`)
- `src/veille/enrich/llm.py` — MODIFIÉ (`determiner_recommandation`, `marquer_recommandation`, docstring de module mise à jour)
- `tests/test_models.py` — MODIFIÉ (tests `Entree.recommandee`)
- `tests/test_filter.py` — MODIFIÉ (tests `marge_recommandation` : défaut, chargement, repli sur config invalide)
- `tests/test_llm.py` — MODIFIÉ (~13 tests `determiner_recommandation`/`marquer_recommandation`)
- `tests/test_socle_reel.py` — MODIFIÉ (garde-fou de présence explicite de `marge_recommandation:` dans `config/scoring.yaml`, trouvé nécessaire par l'audit par mutation de cette story)

### Change Log

| Date | Modification |
|------|--------------|
| 2026-08-28 | Implémentation initiale des Tasks 1-4 (`Entree.recommandee`, `Ponderations.marge_recommandation`, `determiner_recommandation`, `marquer_recommandation`), TDD rouge-vert-refactor. |
| 2026-08-28 | Task 5 : audit par mutation (4 mutants) ; gap de couverture de configuration trouvé et corrigé (`test_socle_reel.py`) ; exécution réelle sans API validée ; suite complète 260 passed. Statut → review. |
| 2026-08-28 | Revue de code (Sonnet 5, 3 couches, même modèle que l'implémentation). 6 correctifs, 0 reporté, 8 rejetés : garde-fou de signe sur `marge_recommandation` (constat convergent des 3 couches — une marge ≤ 0 aurait forcé une recommandation tous les jours), caveat de précondition d'identité sur `marquer_recommandation`, couverture de test étendue (« sans affecter le reste », listes désynchronisées), garde-fou de config durci contre une ligne commentée, précision de câblage pré/post-quota pour la Story 1.8. 263 tests. Statut → done. |
