---
baseline_commit: 375f9c5
---

# Story 4.3: Voir un récapitulatif des sources à surveiller

Status: done

## Story

As a Abdoulaye,
I want un endroit où voir d'un coup d'œil quelles sources sont suspectes ou en sommeil,
so that je décide si je les répare ou les retire.

## Acceptance Criteria

1. **[FR-13, epics.md#Story-4.3]** Étant donné au moins une source à l'état `suspecte` ou `en_sommeil`, quand le contrôle hebdomadaire se termine, alors un récapitulatif liste ces sources avec leur état et la raison (âge de `dernier_item_vu` et/ou dates suspectes détectées, Story 4.2).
2. **[FR-13, epics.md#Story-4.3]** Ce récapitulatif est **consultable sans avoir à interroger la base directement** — publié comme un panneau sur la page du digest déjà publiée (`index.html`, dépôt de sortie), pas seulement dans les logs GitHub Actions du run hebdomadaire (éphémères, non consultables après coup sans revenir dans l'historique Actions).
3. **[Idempotence, cohérent avec la Story 3.2]** Un contrôle hebdomadaire qui se répète (aucun changement d'une semaine à l'autre) ne doit jamais empiler plusieurs panneaux — remplacement entre marqueurs stables, même mécanisme que le bandeau d'échec.
4. **[Honnêteté]** Si plus aucune source n'est `suspecte`/`en_sommeil` (tout s'est rétabli), le panneau existant est **retiré** de la page au contrôle suivant — un panneau périmé listant des problèmes déjà résolus serait trompeur.
5. **[Isolation, AD-6]** La lecture des sources à surveiller et la publication du récapitulatif ne lèvent jamais — une panne dégrade (rien de publié/modifié) sans jamais faire échouer le contrôle de fraîcheur lui-même.
6. Aucune régression sur les Stories 4.1/4.2 (états, transitions, `dates_suspectes`) ; suite complète verte.

## Tasks / Subtasks

- [x] Task 1 : Lecture des sources à surveiller (AC: 1, 5)
  - [x] `health.SourceASurveiller` (dataclass frozen) : `source_id`, `etat`, `raison` (texte reconstruit à partir des données déjà stockées — âge de `dernier_item_vu` si au-delà du seuil, et/ou `dates_suspectes` — **pas** une nouvelle colonne « raison » séparée, une seule source de vérité pour ces deux observations déjà persistées par les Stories 4.1/4.2).
  - [x] `health.lister_sources_a_surveiller(conn, aujourdhui) -> list[SourceASurveiller]` — lit toutes les lignes `sante_source` dont `etat != 'active'`. Isolée globalement **et** par ligne (même patron qu'`evaluer_fraicheur`, Story 4.1 : une ligne corrompue ne doit jamais empêcher de lister les autres). `aujourdhui` explicite, jamais `datetime.now()` interne (même discipline que le reste de `health.py`).
  - [x] Tests (6 nouveaux — corrigé en revue, la story en annonçait 7 par erreur de décompte) : une source `suspecte` (âge seul) → raison mentionne l'âge ; une source `suspecte` par `dates_suspectes` seul (fraîche par ailleurs) → raison le mentionne ; une source avec les deux causes → raison mentionne les deux ; aucune source à surveiller → liste vide ; isolation sur connexion cassée et sur une ligne corrompue.

- [x] Task 2 : Rendu du panneau (AC: 1)
  - [x] `render.rendre_recapitulatif_sante(sources: list[SourceASurveiller]) -> str` — fragment HTML délimité par de nouveaux marqueurs stables (`RECAPITULATIF_SANTE_DEBUT`/`FIN`, même patron que `BANDEAU_ECHEC_DEBUT`/`FIN`, Story 3.2), un panneau listant chaque source (id, état, raison), couleurs thématisées via de nouvelles variables CSS `--recapitulatif-bg`/`--recapitulatif-fg` (clair/sombre, ajoutées à `digest.html.j2`, même système que `--bandeau-echec-bg`/`--recommandee-bg`). Ne prend jamais une liste vide en entrée (la fonction appelante décide de ne pas l'appeler ou de retirer le panneau existant — voir Task 3).
  - [x] Tests (3 nouveaux — corrigé en revue, la story en annonçait 4 par erreur de décompte) : contenu HTML échappé (un `source_id`/`raison` ne doivent jamais casser le HTML), les deux marqueurs présents, chaque source listée avec son état et sa raison, fragment jamais un document complet.

- [x] Task 3 : Publication idempotente, retrait si plus rien à signaler (AC: 2, 3, 4, 5)
  - [x] Généralisé `publish._inserer_bandeau` en `publish._inserer_fragment(html, motif, fragment) -> str` (même logique — remplace entre marqueurs si présents, sinon insère après `<body...>`, sinon en tête). Le call site de `publier_bandeau_echec` appelle directement `_inserer_fragment(..., _MOTIF_BANDEAU_ECHEC, ...)` (l'ancienne fonction `_inserer_bandeau` a été retirée plutôt que gardée comme enveloppe fine — aucun appelant externe ne la référençait) — **zéro changement de comportement observable**, refactor pur confirmé par les 30 tests existants de `test_publish.py` toujours verts sans modification.
  - [x] `publish.publier_recapitulatif_sante(sources: list[SourceASurveiller], client=None) -> bool | None` — même patron à trois états que `publier_bandeau_echec` (Story 3.2) : `None` si rien à changer (page absente, ou aucun panneau existant **et** `sources` vide), `False` sur panne réelle, `True` si publié/retiré avec succès. Si `sources` est vide et qu'un panneau existe déjà dans le HTML publié, il est **retiré** (marqueurs + contenu remplacés par une chaîne vide) plutôt que laissé périmé (AC4). Si `sources` est non vide, le fragment (`render.rendre_recapitulatif_sante`) est construit et inséré/remplacé via `_inserer_fragment`.
  - [x] Tests (10 nouveaux) : page sans panneau + sources vides → `None`, rien publié ; page avec panneau existant + sources vides → panneau retiré, `True` ; page sans panneau + sources non vides → panneau inséré ; page avec panneau existant + sources non vides (différentes) → panneau remplacé, jamais empilé (AC3) ; page absente → `None` ; contenu illisible → `False` ; sans jeton/panne réseau → `False` ; bout en bout avec le vrai fragment rendu.

- [x] Task 4 : Câblage dans le contrôle hebdomadaire (AC: 1, 2, 5)
  - [x] `pipeline.controler_fraicheur()` gagne un paramètre `publish_client: httpx.Client | None = None` (même convention d'injection que `executer()`) — **distinct** de `store_client` : ce nouveau paramètre vise le **dépôt de sortie** (digest publié, `DIGEST_PUBLISH_TOKEN`), pas le dépôt source (`SOURCE_GITHUB_TOKEN`) que `store_client` vise déjà.
  - [x] Après `evaluer_fraicheur(...)` : `health.lister_sources_a_surveiller(conn, aujourdhui)` puis `publish.publier_recapitulatif_sante(sources, client=publish_client)`. Isolé de son propre `try/except` (même discipline que le marquage déjà-vu dans `executer()`, Story 3.4) : une panne ici ne fait jamais échouer le contrôle de fraîcheur lui-même (le retour de `controler_fraicheur()` reste gouverné par le retéléversement de l'état de santé).
  - [x] `.github/workflows/controle-hebdomadaire.yml` : ajouté `GITHUB_TOKEN: ${{ secrets.DIGEST_PUBLISH_TOKEN }}` au step d'exécution (même secret que `pipeline-nocturne.yml`) — nouveau prérequis réel documenté en tête du fichier.
  - [x] Tests (2 nouveaux) : le contrôle hebdomadaire publie le récapitulatif après une évaluation qui produit des sources à surveiller ; une panne de publication du récapitulatif ne fait pas échouer `controler_fraicheur()`.
  - [x] **Trouvé pendant l'implémentation (pas en revue formelle)** : sans isolation, chaque test existant de `controler_fraicheur()` (Story 4.1) aurait désormais résolu un vrai jeton (`gh auth token`) et fait un vrai appel réseau en lecture vers l'API GitHub du dépôt de sortie, faute de neutraliser `publish._jeton` dans la fixture `autouse` de `test_pipeline.py` (qui ne neutralisait jusqu'ici que `store._jeton`). Corrigé immédiatement : `publish._jeton` ajouté à la même fixture. Sans ce correctif, la suite de tests aurait silencieusement fait des appels réseau réels à chaque exécution.

- [x] Task 5 : Validation (AC: 5, 6)
  - [x] Suite complète (`uv run pytest`) rejouée sans régression.
  - [x] Validation YAML du workflow modifié.

## Dev Notes

### Précédent directement réutilisable : le bandeau d'échec (Story 3.2)

Cette story reproduit presque exactement le mécanisme déjà construit et testé pour le bandeau d'échec : un fragment HTML délimité par des marqueurs stables, inséré/remplacé après coup dans le HTML **déjà publié** (pas régénéré depuis zéro), via le même upsert par `sha`. La seule vraie nouveauté par rapport au bandeau : le retrait du panneau quand `sources` devient vide (AC4) — le bandeau d'échec n'a jamais eu ce besoin symétrique (il n'existe pas de mécanisme qui « retire » un bandeau d'échec explicitement, une nuit réussie le remplace juste par du nouveau contenu via `rendre()`/`publier()` normal). Ce besoin de retrait est propre à cette story, à construire.

### Pourquoi le récapitulatif vit sur la page du digest, pas ailleurs

L'AC2 exige « consultable sans avoir à interroger la base directement ». Options considérées : (a) panneau sur `index.html` (retenu), (b) fichier Markdown séparé dans le dépôt de sortie, (c) uniquement les logs du run GitHub Actions. (c) est rejeté explicitement par l'AC (« sans avoir à » rouvrir l'historique Actions). (b) créerait un second artefact à consulter séparément de l'habitude déjà prise (Abdoulaye ouvre la page du digest chaque matin) — (a) réutilise l'endroit qu'il regarde déjà, cohérent avec l'esprit du bandeau d'échec (même page, même réflexe de consultation).

### Un jeton de plus pour le contrôle hebdomadaire — prérequis réel nouveau

`controle-hebdomadaire.yml` (Story 4.1) n'avait besoin que de `SOURCE_GITHUB_TOKEN` (dépôt source, état de santé). Cette story lui ajoute un vrai besoin d'écriture sur le **dépôt de sortie** (`DIGEST_PUBLISH_TOKEN`, le même secret que `pipeline-nocturne.yml` utilise déjà) — à documenter explicitement en tête du workflow, pas un détail à sous-entendre. Aucun nouveau secret à créer si le dépôt de sortie a déjà été configuré pour la Story 1.8 ; sinon, même prérequis déjà documenté et différé depuis cette story-là (voir `rapport-projet.md` §9).

### Précédents à réutiliser, pas à réinventer

- **`publish._charge_existante`/upsert par `sha`** (Stories 1.8/3.2) — réutilisés tels quels par `publier_recapitulatif_sante`.
- **`publish._inserer_bandeau`/`_MOTIF_BALISE_BODY`** (Story 3.2) — généralisés en `_inserer_fragment`, réutilisés par les deux fragments (bandeau, récapitulatif) sans dupliquer la logique de remplacement/insertion.
- **`health.evaluer_fraicheur`** (Story 4.1) — patron d'isolation par ligne, directement reproduit par `lister_sources_a_surveiller`.
- **Variables CSS thématisées** (`--bandeau-echec-bg`/`--recommandee-bg`, `digest.html.j2`) — même système réutilisé pour `--recapitulatif-bg`/`-fg`.
- **Retour à trois états** (`True`/`False`/`None`, décision #46 du journal) — même discipline reproduite pour `publier_recapitulatif_sante`.

### Hors périmètre — ne pas anticiper

- **Story 4.4** (découverte de nouvelles sources) — sans lien direct.
- **Historique des transitions** — le panneau reflète l'état **courant** (toutes les sources actuellement suspectes/en sommeil), pas un journal des changements passés ; `RapportSante.transitions` (Story 4.1) reste un rapport de run, pas la source du panneau.
- **Action de réactivation depuis la page** — le récapitulatif est en lecture seule ; « il décide s'il les répare ou les retire » (édition de `sources.yaml`) reste manuel, hors périmètre de cette story.

### Testing Standards

`pytest` via `uv run pytest`. Aucun appel réseau réel — client HTTP simulé pour `publish.py` (mêmes patrons `_FakeResponse`/clients à état que `test_publish.py`), connexions SQLite réelles sur fichier temporaire pour `health.py`.

### Previous Story Intelligence

- Story 4.2 : `sante_source` porte désormais `dernier_item_vu`/`etat`/`dates_suspectes` — tout ce dont `lister_sources_a_surveiller` a besoin existe déjà, aucune nouvelle colonne à ajouter.
- Story 3.2 : `_inserer_bandeau`/`publier_bandeau_echec` — patron complet à généraliser, pas à dupliquer une seconde fois à l'identique.

### Git Intelligence Summary

Commits récents (locaux, non encore poussés — blocage `gh auth` `workflow` scope toujours en cours, 5 tentatives de device flow depuis la Story 3.1) : Story 4.2 (`72cbcb3` impl+revue, `375f9c5` docs).

### Project Structure Notes

Aucun nouveau fichier : `health.py`, `render.py`, `publish.py`, `pipeline.py` modifiés ; `templates/digest.html.j2` modifié (2 nouvelles variables CSS) ; `.github/workflows/controle-hebdomadaire.yml` modifié (secret supplémentaire).

### References

- [Source: epics.md#Story-4.3] — story d'origine et critères d'acceptation
- [Source: 3-2-reprendre-apres-echec.md] — mécanisme de fragment idempotent (bandeau d'échec), généralisé ici
- [Source: 4-1-detecter-source-arretee.md] — `sante_source`, `evaluer_fraicheur` (patron d'isolation par ligne)
- [Source: 4-2-detecter-source-mensongere.md] — `dates_suspectes`, disponible en lecture pour la raison du panneau

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5 (`claude-sonnet-5`)

### Debug Log References

- `uv run pytest tests/test_health.py -q` : 38 passed (32 avant + 6 nouveaux) — avant revue.
- `uv run pytest tests/test_render.py -q` : 37 passed (33 avant + 3 nouveaux — pas 4, corrigé dans les Tasks ci-dessus) — avant revue.
- `uv run pytest tests/test_publish.py -q` : 39 passed (30 avant + 9 nouveaux) — avant revue.
- `uv run pytest tests/test_pipeline.py -q` : 30 passed (28 avant + 2 nouveaux) — avant revue — **et un temps d'exécution passé de 3.30s à 0.93s après le correctif d'isolation `publish._jeton`**, confirmant qu'un vrai appel réseau avait bien lieu avant ce correctif.
- Suite complète (avant revue) : `uv run pytest -q` → 477 passed (457 avant cette story + 20 nouveaux), aucune régression.
- Suite complète (après revue) : `uv run pytest -q` → 479 passed (477 + 2 nouveaux tests de revue : réapplication du récapitulatif après publication nocturne, retrait via `controler_fraicheur()`).
- Validation YAML du workflow modifié : `python -c "import yaml; yaml.safe_load(...)"` → OK.

### Review Findings

> Revue de code du 2026-09-16 (skill `bmad-code-review`, 3 couches adversariales, sur
> Sonnet 5 — même modèle que l'implémentation). Base de diff `375f9c5` (= `baseline_commit`,
> changements non commités). Le Blind Hunter a trouvé le constat le plus sérieux de toute
> cette session de revue : la publication nocturne normale (`rendre()`/`publier()`, qui
> régénère `index.html` depuis zéro) efface silencieusement le panneau récapitulatif publié
> par le contrôle hebdomadaire, dès la nuit suivante — le panneau ne restait visible que
> quelques heures par semaine au lieu de toute la semaine, contredisant directement l'AC2
> (« consultable »). Convergence avec l'Edge Case Hunter sur un second constat réel : le
> retour `False` de `publier_recapitulatif_sante()` n'était vérifié nulle part dans
> `controler_fraicheur()`, et une valeur non-chaîne dans `dernier_item_vu` faisait
> disparaître toute la ligne du récapitulatif plutôt que de dégrader sur la seule raison
> par âge.

**Correctifs appliqués (6) :**

- [x] [Review][Patch] La publication nocturne normale (`executer()`) effaçait le panneau récapitulatif à chaque republication réussie de la page — `rendre()` ignore tout des marqueurs `RECAPITULATIF-SANTE`, et `publier()` republie le contenu intégralement. Corrigé : `executer()` réapplique désormais le récapitulatif (relecture de `sante_source` via `health.lister_sources_a_surveiller`, republication via `publish.publier_recapitulatif_sante`) juste après ses propres publications, indépendamment de `page_ok`/`archive_ok` — le panneau reste ainsi visible tant que les sources concernées ne sont pas réellement rétablies, pas seulement entre le contrôle hebdomadaire et la nuit suivante. Constat le plus sérieux de la revue (Blind Hunter) [src/veille/pipeline.py]
- [x] [Review][Patch] Une source retirée de `sources.yaml` (le remède même que la story documente — « il décide s'il les répare ou les retire ») restait affichée indéfiniment dans le récapitulatif : `evaluer_fraicheur` ne visite plus que les sources encore configurées, donc son `etat` reste figé pour toujours une fois la source retirée, sans qu'aucun mécanisme ne l'efface. Corrigé : `lister_sources_a_surveiller` accepte un paramètre optionnel `sources_configurees`, qui exclut du résultat toute ligne dont le `source_id` n'y figure plus. Constat (Blind Hunter) [src/veille/health.py, src/veille/pipeline.py]
- [x] [Review][Patch] Le retour `False` de `publier_recapitulatif_sante()` (panne réelle réseau/HTTP) n'était vérifié nulle part dans `controler_fraicheur()` — seul le cas où l'appel lève une exception était géré/testé, pas le cas documenté où il renvoie simplement `False`. Corrigé : le retour est désormais vérifié, un `logger.warning` explicite si `False`. Constat (Edge Case Hunter) [src/veille/pipeline.py]
- [x] [Review][Patch] Une valeur non-chaîne dans `dernier_item_vu` (corruption/migration future) levait `TypeError`, non capturé par le `except ValueError` interne à `lister_sources_a_surveiller` — la source disparaissait entièrement du récapitulatif (capturée par l'`except Exception` englobant par ligne) plutôt que de dégrader sur la seule raison par âge. Corrigé : `except (ValueError, TypeError)`. Constat (Edge Case Hunter) [src/veille/health.py]
- [x] [Review][Patch] `rendre_recapitulatif_sante([])` ne faisait respecter son contrat (« jamais appelée avec une liste vide ») que par la discipline du seul appelant existant, jamais par la fonction elle-même. Corrigé : lève `ValueError` explicitement si appelée avec une liste vide. Constat convergent (Blind Hunter + Edge Case Hunter) [src/veille/render.py]
- [x] [Review][Patch] Décompte de tests erroné dans les Tasks/Debug Log de cette story elle-même (7/4 annoncés pour `test_health.py`/`test_render.py`, 6/3 réellement ajoutés) — corrigé. Clarification de docstring ajoutée à `publier_recapitulatif_sante` sur le typage non explicite de `sources` (même raison que `render.rendre_recapitulatif_sante`, jusque-là seulement expliquée côté `render.py`). Constat (Acceptance Auditor) [story, src/veille/publish.py]

**Reporté (0) — dismiss/défère ci-dessous plutôt que reporté formellement**, aucune entrée `deferred-work.md` pour cette story : les constats restants ont été jugés soit déjà couverts par un correctif ci-dessus, soit du bruit à cette échelle (voir ci-dessous).

**Rejeté comme bruit (6) :**

- « `publier_recapitulatif_sante` duplique ~40 lignes de `publier_bandeau_echec` plutôt que de partager la logique GET/décodage/PUT » (Blind Hunter, simplification) — constat juste, mais report délibéré : un refactor supplémentaire (extraire un second niveau de partage au-delà d'`_inserer_fragment`, déjà fait) n'est pas nécessaire à la correction du comportement, et le risque de régression sur les 30 tests existants de `publier_bandeau_echec` pour un gain de maintenabilité pure ne justifiait pas de l'entreprendre dans cette même passe. À reconsidérer si une troisième fonction de ce type apparaît.
- « Aucun court-circuit d'égalité de contenu avant le `PUT` hebdomadaire — commits répétés même sans changement » (Blind Hunter) — cohérent avec le reste du projet (`televerser_vers_distant` n'a pas non plus ce court-circuit) ; pas une régression propre à cette story.
- « Marqueurs orphelins (`DEBUT` sans `FIN`) jamais nettoyés » (Edge Case Hunter) — suppose une corruption externe déjà hors périmètre pour le mécanisme équivalent du bandeau d'échec (Story 3.2), pas une régression introduite ici.
- « Aucun test de coexistence bandeau d'échec + récapitulatif sur la même page » (Edge Case Hunter) — les deux mécanismes sont indépendants et déjà testés isolément avec le même `_inserer_fragment` ; un test combiné apporterait une confirmation, pas une garantie supplémentaire absente du code.
- « `try/except` autour d'appels qui s'isolent déjà eux-mêmes dans `controler_fraicheur()` » (Blind Hunter) — défense en profondeur délibérée, même style que le bloc de marquage déjà-vu d'`executer()` (Story 3.4).
- « `raison` conflate deux signaux sans indiquer leur ancienneté relative » (Blind Hunter) — nuance réelle mais mineure ; la Story 4.4/un futur ajustement du texte pourrait l'affiner si un besoin réel se manifeste.

### Completion Notes List

- **AC1** : confirmé — `health.lister_sources_a_surveiller` liste chaque source `suspecte`/`en_sommeil` avec une raison reconstruite (âge, dates suspectes, ou les deux).
- **AC2** : confirmé — le récapitulatif est publié comme panneau sur `index.html` (dépôt de sortie), consultable à chaque visite du digest sans jamais rouvrir l'historique Actions ni interroger la base.
- **AC3** : confirmé — `_inserer_fragment` remplace entre marqueurs stables, jamais n'empile (test dédié, deux publications consécutives avec des sources différentes).
- **AC4** : confirmé — `publier_recapitulatif_sante([], ...)` retire le panneau existant plutôt que de le laisser périmé (test dédié) ; ne fait rien si aucun panneau n'existait déjà.
- **AC5** : confirmé — toutes les nouvelles fonctions publiques de `health.py` isolées (globalement et par ligne) ; la publication du récapitulatif dans `controler_fraicheur()` isolée de son propre `try/except`, ne change jamais le retour de la fonction.
- **AC6** : confirmé — 479 tests passent après revue, tous les tests existants des Stories 4.1/4.2 verts sans modification (en dehors de la fixture d'isolation étendue, nécessaire — voir ci-dessous).
- **AC2, renforcé en revue** : le récapitulatif reste désormais visible tant que les sources concernées ne sont pas réellement rétablies — pas seulement entre le contrôle hebdomadaire et la prochaine publication nocturne réussie, qui l'aurait sinon effacé (correctif le plus important de la revue, voir Review Findings).
- **Trouvé pendant l'implémentation, corrigé avant la revue formelle** : sans étendre la fixture `autouse` de `test_pipeline.py`, chaque test existant de `controler_fraicheur()` aurait résolu un vrai jeton GitHub (`gh auth token`, présent sur cette machine) et fait un vrai appel réseau en lecture vers l'API du dépôt de sortie à chaque exécution de la suite — un problème de sécurité/hygiène de test réel, pas hypothétique (temps d'exécution mesuré : 3.30s avant, 0.93s après correctif). Documenté explicitement plutôt que corrigé silencieusement, pour que la piste d'audit reste honnête sur ce qui s'est réellement passé.
- `_inserer_bandeau` (Story 3.2) retirée plutôt que gardée comme enveloppe fine autour de `_inserer_fragment` — aucun appelant externe (code ou test) ne la référençait directement, une enveloppe aurait été de l'indirection sans bénéfice.

### File List

- `src/veille/health.py` — modifié : `SourceASurveiller` (dataclass), `lister_sources_a_surveiller()` ; modifié en revue : paramètre `sources_configurees` (exclut les sources retirées de `sources.yaml`), `except (ValueError, TypeError)` (dégrade sans perdre toute la ligne).
- `src/veille/render.py` — modifié : `import html`, `RECAPITULATIF_SANTE_DEBUT`/`FIN`, `rendre_recapitulatif_sante()` ; modifié en revue : lève `ValueError` sur liste vide (contrat imposé, pas seulement documenté).
- `src/veille/publish.py` — modifié : `_inserer_bandeau` généralisée en `_inserer_fragment` (réutilisée par `publier_bandeau_echec`), nouveau `_MOTIF_RECAPITULATIF_SANTE`, `publier_recapitulatif_sante()` ; modifié en revue : clarification docstring sur le typage de `sources`.
- `src/veille/pipeline.py` — modifié : import `publier_recapitulatif_sante`, `controler_fraicheur()` gagne `publish_client`, appelle `lister_sources_a_surveiller`/`publier_recapitulatif_sante` après `evaluer_fraicheur`, isolé de son propre `try/except` ; modifié en revue : **`executer()` réapplique désormais le récapitulatif après ses propres publications** (correctif le plus important de la revue — sans lui, la publication nocturne normale effaçait le panneau à chaque run réussi), retour `False` de la publication du récapitulatif désormais vérifié dans `controler_fraicheur()`, `sources_configurees` propagé aux deux call sites.
- `templates/digest.html.j2` — modifié : variables CSS `--recapitulatif-bg`/`-fg` (clair/sombre).
- `.github/workflows/controle-hebdomadaire.yml` — modifié : secret `DIGEST_PUBLISH_TOKEN` ajouté, prérequis documentés.
- `tests/test_health.py` — modifié : 6 nouveaux tests.
- `tests/test_render.py` — modifié : 3 nouveaux tests.
- `tests/test_publish.py` — modifié : 9 nouveaux tests.
- `tests/test_pipeline.py` — modifié : fixture `autouse` étendue (`publish._jeton` neutralisé), 2 nouveaux tests à l'implémentation ; +2 en revue (réapplication du récapitulatif par `executer()`, retrait via `controler_fraicheur()`).
- `_bmad-output/implementation-artifacts/4-3-recapitulatif-sources.md` — ce fichier (story).

### Change Log

| Date | Changement |
|---|---|
| 2026-09-15 | Story créée (`create-story`) et implémentée en une passe (Tasks 1-5) : `SourceASurveiller`/`lister_sources_a_surveiller` (`health.py`), `rendre_recapitulatif_sante` (`render.py`), `_inserer_fragment`/`publier_recapitulatif_sante` (`publish.py`, refactor + nouvelle fonction), câblage dans `controler_fraicheur()`, workflow étendu. Bug d'hygiène de test réel trouvé et corrigé en cours d'implémentation (appels réseau réels dans les tests existants de la Story 4.1, faute d'isolation de `publish._jeton`). 20 nouveaux tests, 477 passed, aucune régression. Statut → review. |
| 2026-09-16 | Revue (3 couches, Sonnet) : 6 correctifs appliqués — le plus sérieux de toute la session (Blind Hunter) : la publication nocturne normale effaçait silencieusement le panneau récapitulatif à chaque run réussi (`rendre()` ignore ses marqueurs), corrigé par une réapplication systématique dans `executer()` après ses propres publications ; sources retirées de `sources.yaml` restant affichées indéfiniment (`sources_configurees`) ; retour `False` de la publication du récapitulatif non vérifié dans `controler_fraicheur()` ; valeur non-chaîne dans `dernier_item_vu` faisant disparaître toute la ligne au lieu de dégrader ; contrat « jamais de liste vide » de `rendre_recapitulatif_sante` désormais imposé, pas seulement documenté ; décompte de tests corrigé. 6 rejets comme bruit (dont un refactor de duplication reporté, jugé non prioritaire). 4 nouveaux tests de revue, 479 passed. Statut → done. |
