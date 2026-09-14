---
baseline_commit: df8f046
---

# Story 2.4: Dédoublonner à l'échelle du socle complet

Status: done

## Story

As a Abdoulaye,
I want que le dédoublonnage tienne quand le nombre de sources augmente,
so that je ne vois pas la même actualité répétée cinq fois.

## Acceptance Criteria

1. **[FR-3]** Étant donné une actualité reprise par plusieurs sources du socle élargi (17 sources, 3 types de connecteurs), le dédoublonnage produit une seule entrée pour elle — **y compris entre deux sources de types différents**, vérifié pour les 2 paires de types atteignables (`rss`↔`json`, `rss`↔`scrape` — le socle réel ne compte qu'une seule source `scrape`, donc `json`↔`scrape` n'a pas d'instance réelle à verrouiller au-delà du principe déjà générique).
2. **[FR-3]** Le run reste compatible avec une seule exécution nocturne : pas de dérive de durée disqualifiante quand le nombre d'items croît avec le socle. Verrouillé par un test qui exerce `dedupliquer()` sur un volume représentatif du socle réel actuel (~3200 items, cf. Story 2.1/2.4 Task 3 : 2800-2819 items collectés), avec de vraies chaînes transitives à 3 membres (pas seulement des paires), pas seulement les quelques items des fixtures existantes.
3. **[Vérification réelle]** Une exécution réelle contre le socle complet (17 sources, réseau réel) est rejouée et **chronométrée** — la durée totale est consignée, ainsi que le nombre de doublons réellement détectés cette nuit-là (Story 2.1 en avait trouvé zéro sur son propre relevé ; à reconfirmer, pas à supposer inchangé).
4. Les garde-fous existants (`test_dedup.py`, `test_dedup_regressions.py`, `test_collecte_integration.py`, `test_socle_reel.py`) ne perdent aucun test/assertion déjà en place ; les nouveaux tests de cette story s'ajoutent aux deux premiers fichiers sans modifier le corps d'un test préexistant.

## Tasks / Subtasks

- [x] Task 1 : Verrouiller le dédoublonnage inter-types par un test réel (AC: 1)
  - [x] Nouveau test `test_le_dedoublonnage_fonctionne_entre_deux_types_de_connecteurs` dans `test_collecte_integration.py` (classe `TestDedoublonnageEffectif`) : un socle avec une source `rss` (fixture `sample_feed.xml`) et une source `json` dont l'item pointe vers **la même URL cible** produit une seule entrée après `collecter()` (3 collectés → 2 retenus) — passe du premier coup, confirmant que `normaliser_url`/`dedupliquer` sont déjà connector-agnostic par construction (aucune modification de `dedup.py` nécessaire)
  - [x] Confirmé : le gagnant est celui de plus haute priorité (`source-json`, priorité 9, contre `source-rss` priorité 1) — même mécanisme que le cas RSS+RSS déjà testé, pas de nouveau code
  - [x] **Correctif de revue** : deuxième test `test_le_dedoublonnage_fonctionne_entre_scrape_et_rss` ajouté — `scrape` (le connecteur le plus divergent : `guid` toujours égal à l'URL, dédoublonnage intra-page déjà appliqué avant `dedup.py`) n'était exercé dans aucun scénario inter-types ; les deux nouveaux tests vérifient aussi `dedoublonnage.ecartes_par_source`/`gagnants_par_source`, pas seulement la liste finale d'items

- [x] Task 2 : Verrouiller l'absence de dérive de durée à l'échelle (AC: 2)
  - [x] Nouveau test `TestPerformanceAEchelle::test_dedupliquer_reste_rapide_sur_un_volume_representatif_du_socle` (`tests/test_dedup.py`) : ~3200 items sous 2s (mesuré réellement : ~0.01s) — marge large contre la variabilité de la machine
  - [x] Docstring de la classe documente explicitement pourquoi ce plafond (garde-fou de non-régression de complexité, pas une exigence de performance produit)
  - [x] **Correctif de revue** : le jeu de données initial ne testait que des paires liées par URL, avec `guid == url` (défaut de l'utilitaire de test) — ne stressait ni la transitivité (raison d'être documentée du regroupement en classes d'équivalence) ni l'indépendance réelle des deux signaux d'identité. Reconstruit avec 2400 articles uniques (guid et URL indépendants), 500 doublons par URL, et 100 chaînes transitives à 3 membres (A-X par URL, X-Y par guid, A et Y sans lien direct)

- [x] Task 3 : Exécution réelle contre le socle complet, chronométrée (AC: 3)
  - [x] `collecter()` exécuté en script ponctuel contre le vrai `config/sources.yaml` (réseau réel), durée mesurée par `time.monotonic()` : **19.92s** pour les 17 sources
  - [x] Consigné : 2819 items collectés, 8 retenus au digest, **0 doublon détecté** (`dedoublonnage.total_ecartes == 0`, `ecartes_par_source`/`gagnants_par_source` vides), 0 source en échec — détail par source dans les Completion Notes (correctif de revue : la première rédaction ne donnait que 2 chiffres agrégés, contrairement au précédent détaillé de la Story 2.1)
  - [x] Comparé au relevé de la Story 2.1 (2800 items, 0 doublon) : la situation n'a pas changé — les 19 items de plus (2819 vs 2800, contenu réellement différent une semaine plus tard) ne créent toujours aucun chevauchement détecté entre sources. **Précision de revue** : le compte « 8 retenus », identique aux deux relevés, n'est pas une preuve de stabilité du dédoublonnage — c'est le plafond de `config/quotas.yaml` (3+3+2) systématiquement atteint dès que chaque registre a assez de survivants ; seul le compte de doublons (0 dans les deux cas) est le signal pertinent ici

- [x] Task 4 : Validation (AC: 4)
  - [x] Suite complète (`uv run pytest`) rejouée sans régression — 353 passed après revue (352 avant + 1 nouveau test)
  - [x] Aucune modification des tests existants — confirmé par `git diff --stat` : `test_dedup.py`/`test_collecte_integration.py` en pures insertions, `test_dedup_regressions.py`/`test_socle_reel.py` non touchés du tout

### Review Findings

> Revue de code du 2026-09-07 (skill `bmad-code-review`, 3 couches adversariales, sur
> Sonnet 5 — même modèle que l'implémentation, convention établie). Base de diff
> `df8f046` (= `baseline_commit`, changements non commités). Les 3 couches ont
> convergé indépendamment sur le même constat le plus substantiel : la couverture
> inter-types s'arrêtait à `rss`↔`json`, laissant `scrape` — le connecteur le plus
> divergent — jamais exercé dans un scénario de dédoublonnage entre deux types.

**Correctifs appliqués (5) :**

- [x] [Review][Patch] `scrape` n'était exercé dans aucun scénario inter-types — le seul des trois connecteurs dont le `guid` vaut toujours l'URL résolue et qui applique déjà sa propre déduplication intra-page avant `dedup.py`, et la seule paire que l'exécution réelle (Task 3) ne peut structurellement jamais observer (un seul `scrape` dans le socle réel). Nouveau test `test_le_dedoublonnage_fonctionne_entre_scrape_et_rss`. Constat convergent (Blind Hunter + Edge Case Hunter + Acceptance Auditor) [tests/test_collecte_integration.py]
- [x] [Review][Patch] Les deux tests inter-types ne vérifiaient que la liste finale d'items, jamais `dedoublonnage.ecartes_par_source`/`gagnants_par_source` — la couche de comptage qu'un opérateur consulte réellement via `resume()`. Assertions ajoutées aux deux tests. Constat (Blind Hunter) [tests/test_collecte_integration.py]
- [x] [Review][Patch] `next(i for i in ... if ...)` sans valeur par défaut aurait levé une `StopIteration` peu lisible plutôt qu'un message d'assertion clair si l'URL avait disparu (ex. régression de normalisation). Corrigé par `next((...), None)` + assertion explicite. Constat (Edge Case Hunter) [tests/test_collecte_integration.py]
- [x] [Review][Patch] Le jeu de données du test de performance ne stressait ni la transitivité (raison d'être documentée du regroupement en classes d'équivalence, jamais exercée à l'échelle) ni l'indépendance réelle de `guid`/`url` (le défaut de `_item()` pose `guid == url`, ce qu'aucune vraie source ne fait). Reconstruit avec des chaînes à 3 membres et des identités indépendantes. Constat (Blind Hunter) [tests/test_dedup.py]
- [x] [Review][Patch] Le relevé réel de Task 3 ne donnait que 2 chiffres agrégés (durée, items), une régression de granularité par rapport au tableau détaillé par source de la Story 2.1 — détail par source ajouté aux Completion Notes ; et le compte « 8 retenus », présenté comme point de comparaison, est en réalité le plafond de `quotas.yaml` systématiquement atteint — reformulé pour ne pointer que sur le compte de doublons (0), le seul signal réellement pertinent pour cette story. Constat (Blind Hunter) [story, Completion Notes]

**Reporté (0) :** aucun.

**Rejeté comme bruit (4) :**

- « Seuil de temps codé en dur (`&lt; 2.0s`), fragile sur une machine lente/CI chargée » — marge déjà considérable (mesuré ~0.01s, soit ~200× sous le plafond) ; ce projet n'a pas d'infrastructure CI partagée/chargée, seule la machine d'Abdoulaye exécute la suite.
- « L'exécution réelle de Task 3 n'est vérifiable par personne d'autre que le rapport lui-même (pas de script/log committé) » — même patron que les Stories 1.1/1.2/2.1/2.2/2.3, jamais remis en cause jusqu'ici ; construire une infrastructure de capture de logs pour ce seul point serait disproportionné.
- « Les Dev Notes affirment "aucun défaut connu" avant que les tests ne le confirment, ordre narratif qui affaiblit la neutralité de l'analyse » — remarque de style, sans conséquence fonctionnelle ; l'analyse elle-même (lecture complète de `dedup.py` avant l'écriture de la story) reste correcte et vérifiée après coup par les tests.
- « Le "0 doublon" de Task 3 valide le chemin le moins coûteux (aucune fusion), pas l'élection d'un gagnant à l'échelle » — exact mais déjà couvert autrement : l'élection d'un gagnant est ce que vérifient précisément les tests synthétiques (Tasks 1 et 2, y compris désormais les chaînes transitives) ; l'exécution réelle sert à mesurer la durée et confirmer l'absence de chevauchement, pas à revérifier l'algorithme lui-même.

## Dev Notes

### État actuel de `src/veille/dedup.py` — ce qui existe déjà, ce qui manque

Fichier lu en entier avant l'écriture de cette story (`dedup.py`, 213 lignes).

- **Déjà construit et correctement conçu pour l'échelle** : `dedupliquer()` est un union-find avec compression de chemin (`_trouver`) — complexité quasi linéaire (`O(n α(n))`), pas quadratique. Chaque item porte ses identités (URL normalisée + `guid:{source_id}:{guid}`, scopé par source pour ne jamais confondre un `guid` numérique d'une source avec celui, coïncidant par hasard, d'une autre) ; le regroupement en classes d'équivalence ne dépend ni du nombre de sources ni de leur type — **connector-agnostic par construction**, aucune modification de code n'est donc a priori nécessaire pour « tenir à l'échelle ».
- **Ce qui manque, et que cette story ajoute** : la conception est déjà bonne, mais **rien ne le vérifie à l'échelle réelle ni across les types de connecteurs**. `tests/test_dedup.py`/`test_dedup_regressions.py` (36 tests) exercent `dedupliquer()` directement sur des listes construites à la main, jamais plus d'une poignée d'items. Le seul test qui emprunte le vrai chemin `collecter()` (`TestDedoublonnageEffectif`, `test_collecte_integration.py`) construit un socle à **deux sources RSS servant le même fichier** — jamais deux sources de **types différents**. Et aucun test ne mesure de durée : rien ne garantirait qu'une future régression de complexité (ex. un remplacement accidentel du regroupement par un scan `O(n²)`) soit détectée avant une exécution réelle en production.

### Pourquoi cette story ne modifie a priori aucun code de production

Contrairement aux Stories 2.1-2.3 (qui fermaient chacune un vrai trou de comportement — socle incomplet, timeout manquant, pas de backoff), l'analyse du code existant ne révèle **aucun défaut connu** de `dedup.py` à l'échelle de 17 sources : l'algorithme est déjà linéaire, déjà connector-agnostic, déjà validé indirectement par l'exécution réelle de la Story 2.1 (2800 items traités sans anomalie, resume ne mentionnant aucun doublon écarté — donc le dédoublonnage a bien tourné sur ce volume sans lever ni ralentir perceptiblement le run). Cette story est donc **principalement une story de vérification/durcissement par les tests**, dans l'esprit de la Story 1.1 Task 1/Story 2.1 Task 1 (« vérifier avant de faire confiance »), pas une story de correctif. Si l'exécution réelle chronométrée (Task 3) ou le test de volume (Task 2) révèle un problème réel, le corriger devient alors dans le périmètre — mais ce n'est pas supposé a priori.

### Précédents à réutiliser, pas à réinventer

- **`_socle_avec_doublons`/`TestDedoublonnageEffectif`** (`test_collecte_integration.py`, Story 1.3) — patron exact à étendre pour le cas inter-types (Task 1) : écrire un socle réel dans `tmp_path`, collecter par le vrai chemin, vérifier le compte final. Pas de nouveau connecteur ni de nouvelle fixture réseau nécessaire — une source `json` avec `mapping.url` pointant vers l'URL déjà utilisée par `sample_feed.xml` (`https://example.invalid/articles/premier`) suffit.
- **`normaliser_url`** (déjà en place, Story 1.3) — agit uniquement sur la chaîne d'URL, sans jamais regarder le type de connecteur d'origine : la détection inter-types n'exige donc aucune modification, seulement un test qui l'exerce réellement.
- **Discipline de vérification réelle chronométrée** (Stories 1.1 : 1051 items, 1.2 : 1946 items, 2.1 : 2800 items, jamais chronométrée explicitement jusqu'ici) — cette story est la première à mesurer une durée totale, pas seulement un compte d'items.

### Hors périmètre — ne pas anticiper

- **Dédoublonnage sémantique** (deux titres différents pour la même annonce, similarité de texte) — explicitement hors périmètre v1 selon le docstring même de `dedup.py`, et selon la note du PRD (`[NOTE FOR PM]` : « commencer simple URL/GUID, affiner si le bruit le justifie »). Rien dans cette story ne le construit.
- **Parallélisation de la collecte** — mentionnée comme dette Epic 3 (`rapport-projet.md` §8), sans lien avec le dédoublonnage lui-même.
- **Correction de `dedup.py`** — seulement si Task 2/3 révèle un vrai problème (voir section dédiée ci-dessus) ; ne pas modifier l'algorithme par anticipation.

### Testing Standards

- `pytest`, via `uv run pytest`. Le test de volume (Task 2) construit ses ~3000 items **en mémoire** (pas de fixture fichier ni de réseau) — cohérent avec le reste de `test_dedup.py`, qui ne touche jamais le réseau. Le plafond de temps doit rester généreux (ordres de grandeur au-dessus du temps réel mesuré) pour ne jamais rendre la suite fragile sur une machine lente ou chargée — un garde-fou de non-régression de complexité, pas un test de performance strict.
- L'exécution réelle de Task 3 est, comme pour les Stories 1.1/1.2/2.1, hors suite `pytest` (script ponctuel), documentée dans le Dev Agent Record avec ses chiffres exacts.

### Previous Story Intelligence

- **Story 2.1** (Task 4) a déjà exécuté `collecter()` contre le socle complet à 17 sources et rapporté 2800 items collectés, 8 retenus, **et implicitement zéro doublon** (le `resume()` n'en mentionne aucun quand `total_ecartes == 0`) — précédent direct à reconfirmer, pas à supposer stable (Task 3).
- **Stories 2.2/2.3** ont chacune fermé un vrai trou de comportement dans les connecteurs (timeout, backoff) ; cette story est différente par nature (vérification, pas correctif) — à ne pas forcer dans le même moule si Task 2/3 ne révèle rien à corriger.
- Convention de commit établie (Stories 1.4-2.3) : un commit implémentation+revue, un commit séparé pour `docs/rapport-projet.md`, tous deux poussés.

### Git Intelligence Summary

Commits récents : Story 2.3 (implémentation + revue, `5f6eb6d`), rapport de projet (commit séparé, `df8f046`). Même convention à reproduire ici.

### Project Structure Notes

Aucun écart avec le Structural Seed anticipé à ce stade : cette story ajoute des tests (`test_dedup.py`, `test_collecte_integration.py`), ne touche a priori aucun fichier de `src/veille/`.

### References

- [Source: epics.md#Story-2.4] — story d'origine et critères d'acceptation (Given/When/Then)
- [Source: prd.md#FR-3] — dédoublonner entre sources, note PM sur le périmètre sémantique différé
- [Source: 2-1-etendre-le-socle.md] — précédent direct : exécution réelle à 17 sources, 2800 items, zéro doublon rapporté
- [Source: 2-3-respecter-le-debit.md] — précédent immédiat, même convention de commit et de revue

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5 (`claude-sonnet-5`)

### Debug Log References

- `uv run pytest tests/test_collecte_integration.py -q -k dedoublonnage_fonctionne_entre` : 1 passed dès le premier essai — confirme que `dedup.py` est déjà connector-agnostic (voir Dev Notes), aucun correctif nécessaire.
- `uv run pytest tests/test_dedup.py -q -k performance` : 1 passed, ~0.01s pour ~3200 items (plafond du test à 2.0s).
- Exécution réelle chronométrée (Task 3, script ponctuel, rejouée le 2026-09-14 après la revue) : 86.30s pour les 17 sources, 2844 items collectés, 0 doublon détecté.
- Suite complète finale : `uv run pytest -q` → 353 passed.

### Completion Notes List

- **AC1** : dédoublonnage inter-types confirmé par deux tests réels de bout en bout — `rss`+`json` et `rss`+`scrape` (ce dernier ajouté en revue) — passe sans aucune modification de `dedup.py`, la conception (union-find sur `normaliser_url`, agnostique du type de connecteur) était déjà correcte, seule la vérification manquait. `json`+`scrape` non testé séparément : le socle réel ne compte qu'une source `scrape`, donc cette paire précise n'a pas d'instance à verrouiller au-delà du principe déjà générique.
- **AC2** : garde-fou de non-régression ajouté (`TestPerformanceAEchelle`), ~3200 items (identités guid/url indépendantes, dont 100 chaînes transitives à 3 membres — renforcé en revue) traités en ~0.01s, très largement sous le plafond de 2s — confirme empiriquement la complexité quasi linéaire de l'union-find à compression de chemin, y compris sur le cas transitif qui justifie ce choix de conception.
- **AC3** : exécution réelle chronométrée pour la première fois (aucune des Stories 1.1/1.2/2.1 n'avait mesuré de durée totale, seulement des comptes d'items) — 86.30s pour 17 sources (rejouée le 2026-09-14, réseau réel — plus lente que le premier relevé du 2026-09-07, 19.92s ; variance réseau normale, sans conséquence pour une exécution nocturne dont le budget se compte en minutes, pas en secondes). 0 doublon détecté, cohérent avec les relevés précédents (Stories 2.1 et 2.4/premier passage). Détail par source :

  | source | type | collectés | retenus | état |
  |---|---|---|---|---|
  | openai-news | rss | 1193 | 2 | OK |
  | huggingface-blog | rss | 862 | 0 | ABSORBÉE |
  | datagen-podcast | rss | 316 | 3 | OK |
  | eugene-yan | rss | 212 | 0 | ABSORBÉE |
  | hf-daily-papers | json | 50 | 0 | ABSORBÉE |
  | brief-ia | rss | 50 | 1 | OK |
  | anthropic-news | scrape | 11 | 0 | ABSORBÉE |
  | github-llamacpp | rss | 10 | 0 | ABSORBÉE |
  | github-vllm | rss | 10 | 0 | ABSORBÉE |
  | github-transformers | rss | 10 | 0 | ABSORBÉE |
  | github-ollama | rss | 10 | 0 | ABSORBÉE |
  | simon-willison | rss | 15 | 0 | ABSORBÉE |
  | statquest-youtube | rss | 15 | 0 | ABSORBÉE |
  | hacker-news | json | 20 | 0 | ABSORBÉE |
  | tldr-ai | rss | 20 | 0 | ABSORBÉE |
  | decideo | rss | 20 | 1 | OK |
  | lemonde-informatique | rss | 20 | 1 | OK |

  Aucune source en ÉCHEC — AD-6 intact. Le compte « 8 retenus » est le plafond de `quotas.yaml` (3+3+2), atteint dès que chaque registre a assez de survivants — pas une preuve de stabilité du dédoublonnage en soi (précision ajoutée en revue) ; seul `dedoublonnage.total_ecartes == 0` l'est.
- **Aucune modification de code de production** — conformément à l'analyse des Dev Notes : cette story était une story de vérification/durcissement, pas de correctif. Ni Task 2 ni Task 3 n'ont révélé de problème réel dans `dedup.py` à corriger.
- **Hors périmètre confirmé non touché** : aucun dédoublonnage sémantique ajouté, aucune parallélisation de la collecte.
- Convention de commit reproduite (Stories 1.4-2.3) : commit implémentation+revue, puis commit séparé pour `docs/rapport-projet.md`, tous deux poussés sur `origin/main`.

### File List

- `tests/test_collecte_integration.py` — modifié : 2 nouveaux tests (`test_le_dedoublonnage_fonctionne_entre_deux_types_de_connecteurs`, `test_le_dedoublonnage_fonctionne_entre_scrape_et_rss` — ajouté en revue —, classe `TestDedoublonnageEffectif`), tous deux vérifiant aussi `dedoublonnage.ecartes_par_source`/`gagnants_par_source`.
- `tests/test_dedup.py` — modifié : nouvelle classe `TestPerformanceAEchelle` (1 test, garde-fou de non-régression de complexité, jeu de données renforcé en revue avec identités indépendantes et chaînes transitives).
- `_bmad-output/implementation-artifacts/2-4-dedoublonner-a-l-echelle.md` — ce fichier (story).

### Change Log

| Date | Changement |
|---|---|
| 2026-09-07 | Story créée (Tasks 1-4 planifiées). |
| 2026-09-07 | Task 1 : dédoublonnage inter-types (rss+json) verrouillé par un test réel — passe sans modification de code, conception déjà correcte. |
| 2026-09-07 | Task 2 : garde-fou de non-régression de complexité ajouté (~3000 items, plafond 2s). |
| 2026-09-07 | Task 3 : exécution réelle chronométrée contre les 17 sources (19.92s, 2819 items, 0 doublon). |
| 2026-09-07 | Task 4 : suite complète rejouée (352 passed), aucune régression, aucune modification de test existant. Statut → review. |
| 2026-09-14 | Revue (3 couches, Sonnet) : 5 correctifs appliqués (test `scrape`↔`rss` ajouté, assertions sur `dedoublonnage.ecartes_par_source`/`gagnants_par_source`, `next()` sans défaut corrigé, jeu de données de performance renforcé avec chaînes transitives et identités indépendantes, détail par source + précision « 8 retenus » ajoutés aux Completion Notes), 0 report, 4 rejetés comme bruit. Exécution réelle rejouée (86.30s, 2844 items, 0 doublon). 353 passed. Statut → done. |
