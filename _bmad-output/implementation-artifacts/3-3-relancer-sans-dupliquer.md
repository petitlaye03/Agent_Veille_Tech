---
baseline_commit: 8bf6303
---

# Story 3.3: Relancer sans jamais dupliquer

Status: done

## Story

As a Abdoulaye,
I want pouvoir relancer le pipeline pour une même nuit sans risque,
so that je ne me retrouve jamais avec deux digests ou une archive dupliquée.

## Acceptance Criteria

1. **[FR-11, AD-9]** Étant donné un digest déjà publié pour la date du jour, relancer le pipeline pour cette même date **écrase** le digest existant (page **et** archive) — jamais un second fichier. Vérifié par un test qui relance réellement `pipeline.executer()` deux fois pour la même date (horodatage figé, correctif de revue), avec un client simulé qui se comporte comme le ferait réellement l'API Contents de GitHub (état qui persiste entre les deux appels, `sha` renvoyé par le premier `PUT` réutilisé par le `GET` du second run) — pas seulement une seule invocation qui simule un état « déjà publié ». Complété en revue par un scénario plus réaliste : un échec **partiel** (archive en échec, page publiée) suivi d'une reprise.
2. **[FR-11, AD-9]** L'archive ne contient qu'une seule entrée pour cette date — le chemin `site/archive/{date}.md` est dérivé de la date, donc structurellement impossible d'en produire deux pour un même jour ; vérifié de bout en bout par le même test (précision de revue : « vérifié explicitement » aurait surévalué ce que l'assertion apporte au-delà de cette garantie déjà structurelle — reformulé).
3. Les garde-fous existants (`test_publish.py`, `test_pipeline.py`) continuent de passer sans modification ; les nouveaux tests s'ajoutent sans en modifier aucun.

## Tasks / Subtasks

- [x] Task 1 : Vérifier la relance de bout en bout par un test réel (AC: 1, 2)
  - [x] Nouveau client de publication simulé **avec état** (`_ClientPublicationAvecEtat`) dans `test_pipeline.py` : contrairement à `_ClientPublicationSimule` (toujours 404 au `GET`, aucune mémoire entre appels), celui-ci retient contenu + `sha` par chemin après chaque `PUT`, et les rend au `GET` suivant — statuts HTTP réalistes (201 création / 200 mise à jour, corrigé en revue) ; `sha` reste un compteur global, pas un vrai hash de contenu, documenté comme simplification délibérée
  - [x] Nouveau test `test_relancer_pour_la_meme_date_ecrase_au_lieu_de_dupliquer` : `pipeline.executer()` appelé deux fois de suite avec la **même** instance de ce client, horodatage figé (correctif de revue — convergence des 3 couches sur le risque de chevauchement de minuit UTC, latent mais réel pour un test censé prouver l'absence de duplication) — confirme que le second appel envoie un `PUT` avec le `sha` renvoyé par le premier (mise à jour, pas création) pour la page **et** l'archive, exactement 2 `PUT` par chemin au total ; renforcé en revue par un espion sur `collect.collecter` (preuve d'une vraie recollecte, pas d'une sortie rejouée) et une assertion `client.closed is False`
  - [x] Nouveau test `test_relancer_apres_un_echec_partiel_n_ecrase_que_ce_qui_manquait` (ajouté en revue) : la page se publie mais l'archive échoue au premier run — la reprise met à jour la page et **crée** l'archive manquante, sans dupliquer ni l'une ni l'autre
  - [x] Confirmé : zéro changement de `pipeline.py` nécessaire — le mécanisme d'upsert par `sha` (Stories 1.8/1.9, AD-9) tient réellement à l'échelle d'une relance complète du pipeline. `publish.py` a reçu un correctif mineur en revue (voir Review Findings), pas lié à l'upsert lui-même

- [x] Task 2 : Validation (AC: 3)
  - [x] Suite complète (`uv run pytest`) rejouée sans régression — 375 passed après revue (373 avant cette story + 2 nouveaux)
  - [x] Aucune modification des tests existants de `test_publish.py`/`test_pipeline.py` — confirmé par `git diff --stat` : uniquement des ajouts

## Dev Notes

### Ce qui est déjà vrai aujourd'hui, vérifié en lisant `publish.py` avant d'écrire cette story

Le mécanisme d'upsert par `sha` (AD-9) existe déjà et couvre déjà, **au niveau unitaire**, exactement le scénario de cette story :
- `_publier`/`_charge_existante` : un `GET` préalable résout le `sha` existant (`None` si absent) ; le `PUT` suivant l'inclut si présent — mise à jour, pas création.
- `publier_archive(markdown, date_digest, ...)` : chemin `f"site/archive/{date_digest.isoformat()}.md"`, **dérivé de la date** — deux runs pour la même date visent structurellement le même chemin, donc le même mécanisme d'upsert s'applique. Impossible par construction d'obtenir deux fichiers d'archive pour un même jour tant que `date_digest` est bien la date réelle du run (déjà garanti : `pipeline.executer()` calcule `maintenant.date()` une seule fois par run et le passe à `publier_archive`).
- Déjà testé au niveau unitaire de `publish.py` : `test_publier_met_a_jour_le_fichier_existant` et `test_publier_archive_met_a_jour_l_archive_existante_du_meme_jour` (celui-ci explicitement annoté « AC3 (AD-9) : relancer pour la même date écrase, jamais un second fichier » depuis la Story 1.9).

**Ce qui manque, et que cette story ferme** : aucun test ne relance réellement `pipeline.executer()` deux fois de suite pour vérifier que ce mécanisme tient à l'échelle de l'orchestrateur complet — les tests existants de `test_pipeline.py` utilisent un client simulé (`_ClientPublicationSimule`) qui renvoie toujours 404 au `GET`, donc ne peut jamais exercer le chemin « mise à jour ». Une régression qui casserait le passage du `sha` entre `collecter()`/`rendre()`/`publier()` (ex. un `client` reconstruit à chaque appel au lieu d'être réutilisé, ou un chemin recalculé différemment d'un run à l'autre) ne serait détectée par aucun test actuel.

### Précédents à réutiliser, pas à réinventer

- **`_ClientPublicationSimule`/`_FakeResponse`** (`test_pipeline.py`, Story 1.8/1.9) — patron de client HTTP simulé déjà en place ; le nouveau `_ClientPublicationAvecEtat` en est une variante avec mémoire, pas un nouveau patron.
- **`_page_publiee`** (`test_publish.py`, Story 3.2) — construit une réponse `GET` simulant un fichier déjà publié (contenu + `sha`) ; même idée reprise côté `test_pipeline.py` pour le nouveau client à état.
- **AD-9** (upsert par `sha`) — déjà implémenté (Stories 1.8/1.9), cette story vérifie, ne construit pas.

### Hors périmètre — ne pas anticiper

- **`store.py`/SQLite (AD-5)** — pas nécessaire : l'upsert par `sha` sur l'API Contents de GitHub ne dépend d'aucun état persistant côté agent, GitHub fait déjà foi. Reste le prérequis de la Story 3.4 (déjà-vu inter-nuits), toujours pas de celle-ci.
- **Story 3.4** — sans lien direct avec cette story.

### Testing Standards

- `pytest`, via `uv run pytest`. Le nouveau client simulé à état ne fait toujours aucun appel réseau réel — même discipline que le reste du projet.

### Previous Story Intelligence

- Story 3.2 : `_page_publiee` (`test_publish.py`) construit déjà une réponse GET avec contenu+sha — patron directement réutilisable pour le nouveau client à état de cette story.
- Convention de commit établie (Stories 1.4-3.2) : un commit implémentation+revue, un commit séparé pour `docs/rapport-projet.md`, tous deux poussés.

### Git Intelligence Summary

Commits récents (locaux, non encore poussés — blocage `gh auth` en cours de résolution) : Story 3.2 (implémentation + revue, `f4a42da`), rapport de projet (commit séparé, `8bf6303`).

### Project Structure Notes

Aucun écart avec le Structural Seed : cette story ne touche que `tests/test_pipeline.py`.

### References

- [Source: epics.md#Story-3.3] — story d'origine et critères d'acceptation
- [Source: ARCHITECTURE-SPINE.md#AD-9] — idempotence du job nocturne (upsert par date)
- [Source: 1-9-archive-markdown.md] — mécanisme d'upsert par `sha` déjà construit et testé au niveau unitaire

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5 (`claude-sonnet-5`)

### Debug Log References

- `uv run pytest tests/test_pipeline.py -q -k relancer` : 1 passed dès le premier essai — confirme que le mécanisme d'upsert (Stories 1.8/1.9) tenait déjà à l'échelle du pipeline complet, aucun correctif nécessaire.
- Suite complète (avant revue) : `uv run pytest -q` → 374 passed (373 avant + 1 nouveau).
- Suite complète (après revue) : `uv run pytest -q` → 375 passed (2 nouveaux tests dans `test_pipeline.py` au total).

### Review Findings

> Revue de code du 2026-09-14 (skill `bmad-code-review`, 3 couches adversariales, sur
> Sonnet 5 — même modèle que l'implémentation, convention établie). Base de diff
> `8bf6303` (= `baseline_commit`, changements non commités). Diff réduit (test-only),
> revue tout de même substantielle : les 3 couches ont convergé sur le même constat —
> l'horodatage non figé rendait le test dépendant d'une coïncidence (ne jamais
> chevaucher minuit UTC), un risque de fragilité rare mais réel pour un test censé
> prouver précisément l'absence de duplication.

**Correctifs appliqués (6) :**

- [x] [Review][Patch] `datetime.now()` non figé dans le test de relance — un chevauchement de minuit UTC entre les deux appels à `pipeline.executer()` viserait deux chemins d'archive différents, invalidant la prémisse « même date » sans que rien ne le signale. Corrigé par une horloge figée (`_HorlogeFigee`, monkeypatchée sur `pipeline.datetime`). Constat convergent (Blind Hunter + Edge Case Hunter + Acceptance Auditor) [tests/test_pipeline.py]
- [x] [Review][Patch] `_ClientPublicationAvecEtat.put()` renvoyait toujours 201, y compris pour une mise à jour — la docstring affirmait pourtant reproduire fidèlement l'API Contents de GitHub, qui renvoie 200 sur une mise à jour. Corrigé (201 création / 200 mise à jour) ; `sha` en simple compteur global (pas un vrai hash) explicitement documenté comme simplification délibérée plutôt que laissé comme une fidélité implicite surévaluée. Constat (Blind Hunter) [tests/test_pipeline.py]
- [x] [Review][Patch] Scénario manquant, plus proche de l'usage réel de l'AC (« un run échoue, on relance ») que « succès puis succès » : nouveau test où l'archive échoue au premier run (page publiée avec succès) — la reprise met à jour la page et **crée** l'archive manquante, sans dupliquer ni l'une ni l'autre. Constat (Blind Hunter) [tests/test_pipeline.py]
- [x] [Review][Patch] Rien ne prouvait que le second run recollectait réellement plutôt que de rejouer une sortie mise en cache (les deux runs produisent un contenu identique par construction — une régression de ce type serait passée inaperçue). Espion ajouté sur `collect.collecter`, confirme 2 appels réels. Constat (Blind Hunter) [tests/test_pipeline.py]
- [x] [Review][Patch] `client.closed is False` non réévalué après le second run — exactement le scénario (client réutilisé entre deux runs) où une fermeture accidentelle serait la plus grave. Assertion ajoutée. Constat (Blind Hunter) [tests/test_pipeline.py]
- [x] [Review][Patch] `_publier` (`publish.py`, code préexistant, pas introduit par cette story) journalisait « Mise à jour » comme message de commit même pour une toute première création — trompeur dans l'historique du dépôt de sortie. Corrigé par cohérence (décision #15 du journal des décisions), sans rapport avec l'upsert lui-même que cette story vérifie. Constat (Blind Hunter) [src/veille/publish.py]

**Reporté (0) :** aucun.

**Rejeté comme bruit (3) :**

- « `_chemin()` réimplémente l'extraction de chemin à la main plutôt que de réutiliser des constantes de `publish.py` » — un simple split sur `/contents/`, générique par construction ; réutiliser `CHEMIN_PAGE`/`PUBLISH_REPO` n'apporterait rien de plus robuste pour un découpage aussi direct.
- « Aucune garde sur `json`/`json["content"]` absent dans le client simulé — lèverait `TypeError`/`KeyError` plutôt qu'une erreur diagnosticable » — un double de test qui échoue bruyamment sur un mauvais usage (jamais observé ici) est un comportement acceptable, pas un défaut à corriger par une garde supplémentaire.
- « Aucun troisième run ni variante à contenu divergent » — l'AC porte sur l'absence de duplication d'un artefact, pas sur la détection d'une différence de contenu entre deux nuits ; le scénario « échec partiel puis reprise » (ajouté ci-dessus) couvre le cas réellement motivant de l'AC, un contenu divergent n'y ajouterait rien de plus au regard de cette story précise.

### Completion Notes List

- **AC1/AC2** : confirmé par un test réel qui relance `pipeline.executer()` deux fois de suite avec un client de publication à état (mémoire entre appels, contrairement au client simulé existant) — le second run réutilise correctement le `sha` renvoyé par le premier pour la page **et** l'archive (mise à jour, pas création), exactement 2 `PUT` par chemin sur les deux runs combinés. Complété en revue par un scénario d'échec partiel + reprise, plus proche de l'usage réel. Zéro modification de `pipeline.py` : l'upsert par `sha` (AD-9) tenait déjà, seule la vérification de bout en bout manquait — les tests unitaires existants de `publish.py` (Stories 1.8/1.9) ne couvraient que la fonction isolée, jamais le chemin complet depuis l'orchestrateur.
- **AC3** : confirmé — aucun corps de test existant modifié ; `publish.py` a reçu un correctif d'une ligne en revue (message de commit), sans rapport avec les garde-fous d'upsert eux-mêmes, tous verts.
- Convention de commit reproduite (Stories 1.4-3.2) : commit implémentation+revue, puis commit séparé pour `docs/rapport-projet.md`, à pousser sur `origin/main` dès la résolution du blocage `gh auth` en cours (voir Stories 3.1/3.2 — 6 commits locaux en attente après celle-ci).

### File List

- `tests/test_pipeline.py` — modifié : `_ClientPublicationAvecEtat` (client simulé à état, statuts HTTP corrigés en revue), `_HorlogeFigee` (ajoutée en revue), 2 nouveaux tests (1 initial, renforcé en revue ; 1 ajouté en revue).
- `src/veille/publish.py` — modifié en revue : message de commit distingue création/mise à jour dans `_publier`.
- `_bmad-output/implementation-artifacts/3-3-relancer-sans-dupliquer.md` — ce fichier (story).

### Change Log

| Date | Changement |
|---|---|
| 2026-09-14 | Story créée et implémentée en une passe (Tasks 1-2) : relance de bout en bout vérifiée par un test réel avec client à état, aucune régression, aucune modification de code de production. Statut → review. |
| 2026-09-14 | Revue (3 couches, Sonnet) : 6 correctifs appliqués (horloge figée — convergence 3/3 —, statuts HTTP 200/201 réalistes, scénario d'échec partiel + reprise ajouté, espion de recollecte, assertion `closed`, message de commit création/mise à jour distingué dans `publish.py`), 0 report, 3 rejetés comme bruit. 375 passed. Statut → done. |
