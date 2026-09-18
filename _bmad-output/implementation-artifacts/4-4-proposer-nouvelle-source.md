---
baseline_commit: 7094baf
---

# Story 4.4: Recevoir une proposition de nouvelle source chaque semaine

Status: done

## Story

As a Abdoulaye,
I want que mon agent me propose régulièrement une source que je ne suis pas encore,
so that ma veille s'élargit sans que j'aie à chercher moi-même.

## Acceptance Criteria

1. **[FR-14, epics.md#Story-4.4]** Étant donné le socle actuel de sources suivies, quand le cycle de découverte hebdomadaire s'exécute, alors au moins une source candidate hors du socle est proposée, en français ou en anglais, avec une phrase justifiant son apport.
2. **[FR-14, PRD §4.7]** La source proposée a été **vérifiée active** (flux valide, publication récente) **au moment même de la proposition** — jamais une simple liste statique resservie sans contrôle. Un candidat mort (flux cassé, silencieux depuis longtemps) n'est jamais proposé ; un autre candidat du pool est essayé à la place.
3. **[FR-14, epics.md#Story-4.4]** La proposition apparaît dans une section « À découvrir » de la page du digest (`index.html`), séparée des sections habituelles — **consultable en permanence**, pas seulement le jour où le cycle hebdomadaire s'est exécuté (même piège que la Story 4.3 : la publication nocturne normale régénère la page depuis zéro, la réapplication doit donc suivre le même mécanisme déjà construit et corrigé en revue).
4. **[PRD §4.7, Non-Goals]** **Aucune adoption automatique** — une source proposée ne rejoint jamais `sources.yaml` toute seule ; « v1 = édition manuelle du fichier de sources » est une décision produit déjà actée dans le PRD, pas une limitation à contourner ici.
5. **[AD-7]** Aucun appel LLM pour générer ou choisir un candidat — le pool de candidats est une liste déjà vérifiée manuellement pendant la cartographie du brief (`addendum.md`), pas une génération à la volée. Cohérent avec le mapping `FR-14 → AD-2/AD-3` de l'architecture (connecteur + configuration), pas `AD-7` (frontière LLM, réservée à `enrich/llm.py`).
6. **[Isolation, AD-6]** Aucune fonction de découverte ne lève — un candidat injoignable, un pool vide ou malformé dégradent en « rien à proposer cette semaine », jamais un plantage du contrôle hebdomadaire.
7. Aucune régression sur les Stories 4.1/4.2/4.3 ; suite complète verte.

## Tasks / Subtasks

- [x] Task 1 : Pool de candidats en configuration (AC: 1, 5)
  - [x] Nouveau fichier `config/candidats.yaml` — 10 candidats réels, puisés dans `addendum.md` (déjà vérifiés par requête HTTP réelle pendant la cartographie, jamais inventés), hors du socle actuel de 17 sources. Structure par entrée : `justification` (une phrase, écrite ici, pas générée) + `source` (mêmes champs qu'une entrée de `sources.yaml` — `id`/`type`/`url`/`langue`/`registre`, exploitable tel quel par les connecteurs existants). Diversité de registres (5 apprendre, 3 ce_qui_bouge, 2 pour_le_metier) et de langues (9 en, 1 fr — l'AC exige « en français ou en anglais », les deux sont couverts par le pool).
  - [x] Aucune modification de `SourceConfig`/`config.load_sources()` — la clé `justification` vit à côté de `source`, pas dedans.

- [x] Task 2 : Module `discover.py` — chargement, vérification, sélection (AC: 1, 2, 4, 5, 6)
  - [x] `discover.CandidatSource` (dataclass frozen) : `source: SourceConfig`, `justification: str`.
  - [x] `discover.charger_candidats(path=None) -> list[CandidatSource]` — parseur dédié pour `config/candidats.yaml` (ne réutilise pas `config.load_sources`, forme YAML différente). Isolation de panne (AD-6) : fichier absent/illisible/malformé → liste vide, journalisé ; une entrée individuellement malformée est ignorée, pas tout le pool.
  - [x] `discover.verifier_candidat(candidat, maintenant=None) -> bool` — appelle le connecteur réel (`collect.CONNECTORS[candidat.source.type]`, réutilisé tel quel, AD-2) sur `candidat.source` ; vrai si le fetch réussit, produit au moins un item, et l'item le plus récent date de moins de `SEUIL_RECENCE_JOURS` jours (= 30, même valeur que `health.SEUIL_SUSPECTE_JOURS` — dupliquée, pas importée, même principe d'indépendance de module que `store.py`/`publish.py`). `maintenant` explicite, jamais `datetime.now()` interne (même discipline que `health.py`).
  - [x] `discover.proposer_source(candidats_path=None, sources_path=None, aujourdhui=None) -> CandidatSource | None` — exclut les candidats déjà présents dans `sources.yaml` (même `id`, cas où Abdoulaye a adopté un candidat déjà proposé) ; **rotation déterministe** par numéro de semaine ISO (`aujourdhui.isocalendar().week % len(candidats)`) sur le pool restant, essaie chaque candidat à partir de ce point de départ (en bouclant) jusqu'à en trouver un qui passe `verifier_candidat` ; `None` si aucun ne passe ou si le pool est vide après exclusion. Aucun état persistant nécessaire — la rotation ne dépend que de la date et de la taille du pool, testable par simple injection de date. **Trouvé pendant l'implémentation** : `config.load_sources()` **lève** (pas de garde interne) sur un `sources.yaml` absent/illisible — l'isolation est la responsabilité de l'appelant (même contrat que `collect.collecter()`) ; `proposer_source` l'isole à son tour dans son propre `try/except` englobant, dégrade en `None` pour toute la semaine plutôt que de laisser lever.
  - [x] Tests unitaires (19 tests, `tests/test_discover.py`) : pool avec un candidat déjà adopté (exclu) ; rotation qui change de candidat selon la semaine ISO simulée ; un candidat dont le connecteur échoue est ignoré, le suivant de la rotation est essayé ; un candidat dont le dernier item date de plus de 30 jours est rejeté (limite exacte incluse testée séparément) ; pool entièrement mort → `None` ; fichier de candidats absent/malformé/racine invalide/clé manquante → dégrade sans lever ; `sources.yaml` illisible → dégrade en `None`.

- [x] Task 3 : Rendu et publication du panneau « À découvrir » (AC: 1, 3, 4)
  - [x] `render.rendre_a_decouvrir(candidat: CandidatSource) -> str` — fragment HTML délimité par de nouveaux marqueurs stables (`A_DECOUVRIR_DEBUT`/`FIN`, même patron que le bandeau d'échec/le récapitulatif de santé), section visuellement distincte (« À découvrir », variables CSS `--a-decouvrir-bg`/`-fg` dédiées dans `digest.html.j2`), affiche `justification` + un lien vers `candidat.source.url` (via `_url_surs`, mêmes garde-fous que le reste de `render.py` — schéma `http(s)` uniquement, dégrade en texte seul sinon). Lève `ValueError` si appelé avec `candidat=None` — pas de rendu « rien à découvrir » silencieux (même discipline que `rendre_recapitulatif_sante`).
  - [x] `publish.publier_a_decouvrir(candidat: CandidatSource | None, client=None) -> bool | None` — même patron à trois états que `publier_recapitulatif_sante` (Story 4.3), réutilise `_inserer_fragment`. `candidat=None` **retire** la section existante si elle y est (aucun candidat vivant cette semaine — honnêteté, même principe que l'AC4 de la Story 4.3), ne fait rien si elle n'existait pas déjà.
  - [x] Tests (`tests/test_render.py`, `tests/test_publish.py`) : insertion/remplacement/retrait, jamais empilé, bout en bout avec le vrai fragment rendu, dégradation sans jeton/sur panne réseau, échappement du contenu, URL non-http(s) sans lien, candidat manquant lève.

- [x] Task 4 : Câblage hebdomadaire (AC: 1, 2, 3, 4)
  - [x] Nouvelle fonction `pipeline.decouvrir_nouvelle_source(candidats_path=None, sources_path=None, publish_client=None) -> bool` et `pipeline.main_decouverte_source()` (point d'entrée CLI, `python -m veille.pipeline --decouvrir-source`) — même filet de sécurité que les autres points d'entrée (`executer`/`controler_fraicheur`), ne lève jamais.
  - [x] `.github/workflows/controle-hebdomadaire.yml` : nouveau step indépendant (`if: always()`, pour qu'une panne du contrôle de fraîcheur n'empêche pas la tentative de découverte, et réciproquement) appelant `--decouvrir-source` — **aucun nouveau secret** : `DIGEST_PUBLISH_TOKEN` est déjà présent depuis la Story 4.3 (seul jeton nécessaire, ce module ne touche jamais l'état de santé ni le dépôt source).
  - [x] **Réapplication à chaque publication nocturne (même correctif que la Story 4.3, appliqué dès l'implémentation cette fois, pas seulement en revue)** : `pipeline.executer()` (nouveau paramètre `candidats_path`, même convention d'injection que les autres chemins de configuration) réapplique le panneau « À découvrir » actuellement valide (relit `sources.yaml`/`config/candidats.yaml` via `discover.proposer_source`, revérifie en direct, republie) après ses propres publications, **indépendamment de `store_conn`** (ce cycle ne touche jamais l'état SQLite « déjà vu »/santé) — sans quoi `rendre()` régénérant `index.html` depuis zéro l'effacerait dès la nuit suivante, exactement le piège trouvé en revue de la Story 4.3. Le calcul étant déterministe par semaine ISO, la réapplication nocturne reproduit le même candidat tant qu'il reste vérifié actif — jamais de dérive par rapport au rythme hebdomadaire voulu par l'AC1.
  - [x] **Trouvé pendant l'implémentation** : sans `candidats_path` explicite, `discover.proposer_source()` résout le **vrai** `config/candidats.yaml` du dépôt — chaque test préexistant de `executer()` aurait donc réellement vérifié (requêtes HTTP réelles) les candidats du pool réel. Corrigé en neutralisant `discover.CONNECTORS` à `{}` dans l'autouse fixture d'isolation de `test_pipeline.py` (même réflexe que la neutralisation de `publish._jeton` trouvée en implémentation de la Story 4.3) — un `CONNECTORS` vide fait dégrader `proposer_source` en `None` sans aucun appel réseau, comportement par défaut neutre pour tous les tests qui ne s'intéressent pas spécifiquement à la découverte.
  - [x] Tests (`tests/test_pipeline.py`) : le cycle de découverte publie une proposition vérifiée ; sans candidat vivant, retire un panneau déjà publié ; une panne de la publication (levée ou retour `False`) fait échouer `decouvrir_nouvelle_source()` sans jamais lever ; `main_decouverte_source()` — codes de sortie 0/1 ; `executer()` réapplique la proposition après sa propre publication nocturne ; une panne inattendue de la réapplication (`discover.proposer_source` qui lève) n'affecte jamais le retour de `executer()`.

- [x] Task 5 : Validation (AC: 6, 7)
  - [x] Suite complète (`uv run pytest`) rejouée sans régression — 521 tests, tous verts (479 avant cette story + 19 `test_discover.py` + tests ajoutés à `test_render.py`/`test_publish.py`/`test_pipeline.py`).
  - [x] Validation YAML du workflow modifié (`yaml.safe_load`, step `--decouvrir-source` bien présent) et de `config/candidats.yaml` (déjà validé à la Task 1).

## Dev Notes

### Pourquoi un pool de configuration, pas une génération LLM

L'architecture mappe `FR-14 → discover.py → AD-2, AD-3` (connecteur, configuration) — **pas** `AD-7` (frontière LLM unique, `enrich/llm.py`). Générer un candidat à la volée par LLM romprait cet invariant (vérifié mécaniquement par `grep`, un seul point d'import du SDK `anthropic`) et risquerait de suggérer une URL inventée. Le PRD confirme explicitement l'esprit v1 : « Adoption automatisée des sources découvertes — v1 = édition manuelle du fichier de sources » (§Out of Scope) — la sophistication attendue ici est minimale, pas un système de recommandation. La cartographie du brief (`addendum.md`, ~280 sources testées par requête HTTP réelle en juillet 2026) fournit déjà un vivier bien plus riche que le socle actuel (17 sources) : `config/candidats.yaml` en reprend une sélection telle quelle, avec la justification déjà présente dans l'addendum pour chacune (résumée en une phrase), jamais réinventée.

### Pourquoi une vérification en direct à chaque proposition, pas une liste figée

L'AC2/PRD sont explicites : « une Source proposée est vérifiée active... avant d'être suggérée ». Un flux qui répondait 200 en juillet 2026 (date de la cartographie) peut être mort au moment où le cycle hebdomadaire tourne, des mois plus tard — même risque que celui déjà découvert pour les sources du socle lui-même (Story 4.1/4.2 : silence prolongé, dates figées). `verifier_candidat` réutilise donc le **même mécanisme de connecteur** (`collect.CONNECTORS`) que la collecte nocturne, pas une requête ad hoc distincte — un candidat qui échouerait à ce fetch échouerait de la même façon s'il était adopté demain.

### Pourquoi une rotation déterministe par semaine ISO, pas un état persistant

Proposer indéfiniment le même premier candidat du fichier serait une expérience pauvre (jamais rien de neuf), mais construire un état persistant dédié (une nouvelle table SQLite, « derniers candidats proposés ») serait disproportionné pour ce besoin : la rotation par `aujourdhui.isocalendar().week % len(pool)` change de point de départ chaque semaine, sans écrire nulle part, entièrement déterministe et donc trivialement testable par simple injection de date. Réévaluer si le pool devient un jour assez petit pour que la rotation boucle de façon perceptible (pas le cas avec ~10 candidats et 52 semaines/an).

### Précédents à réutiliser, pas à réinventer

- **Mécanisme de fragment idempotent** (`_inserer_fragment`, Story 3.2/4.3) — réutilisé tel quel pour le panneau « À découvrir », troisième usage de ce mécanisme (aucune généralisation supplémentaire nécessaire, déjà assez générique).
- **Réapplication après publication nocturne** (Story 4.3, trouvé en revue) — le piège est déjà connu avant même d'écrire le code cette fois : à construire dès l'implémentation, pas à corriger après coup en revue.
- **`collect.CONNECTORS`** — dispatch par type déjà construit, réutilisé directement par `verifier_candidat` sans aucune modification de `collect.py`.
- **Isolation par ligne/par candidat** (`health.evaluer_fraicheur`/`lister_sources_a_surveiller`, Story 4.1/4.3) — même discipline reproduite dans `charger_candidats`/`proposer_source`.
- **Retour à trois états** (`True`/`False`/`None`, décision #46) — même discipline reproduite pour `publier_a_decouvrir`.

### Hors périmètre — ne pas anticiper

- **Adoption automatique d'un candidat** — jamais construit ici (PRD, Non-Goals explicites).
- **Section « À découvrir » dans l'archive Markdown** — seule la page HTML (`index.html`) est concernée ; l'archive reste un instantané du digest du jour, pas un endroit pour une proposition qui doit rester visible en continu.
- **Enrichissement du pool par une source externe (API de découverte, LLM, etc.)** — le pool reste un fichier de configuration édité à la main (AD-3), comme `sources.yaml` lui-même.
- **Retrait automatique d'un candidat de `config/candidats.yaml` une fois adopté** — `proposer_source` l'exclut déjà dynamiquement (même `id` présent dans `sources.yaml`), nettoyer le fichier de candidats reste un geste manuel d'Abdoulaye, pas construit ici.

### Testing Standards

`pytest` via `uv run pytest`. Aucun appel réseau réel : `verifier_candidat` testée avec des connecteurs simulés (monkeypatch de `collect.CONNECTORS`), jamais les vraies URL de `config/candidats.yaml`. `aujourdhui`/`maintenant` toujours injectés explicitement.

### Previous Story Intelligence

- Story 4.3 (leçon de revue, journal des décisions #60) : un fragment patché après coup sur une page régénérée par un chemin indépendant doit être réappliqué à chaque régénération. Cette story applique directement cette leçon dès l'implémentation.
- Story 4.1 (leçon #49-50) : un retour à plusieurs états doit être vérifié à chaque branche ; l'isolation par sous-système doit s'étendre à tout nouveau sous-système.

### Git Intelligence Summary

Commits récents (locaux, non encore poussés — blocage `gh auth` `workflow` scope toujours en cours) : Story 4.3 (`9ba0363` impl+revue, `7094baf` docs — Epic 4 ne laisse plus que cette story).

### Project Structure Notes

Nouveau fichier `src/veille/discover.py` (déjà anticipé par `ARCHITECTURE-SPINE.md`) et `config/candidats.yaml`. `render.py`/`publish.py`/`pipeline.py` modifiés (nouvelles fonctions, pas de restructuration). `.github/workflows/controle-hebdomadaire.yml` modifié (nouveau step, aucun nouveau secret).

### References

- [Source: epics.md#Story-4.4] — story d'origine et critères d'acceptation
- [Source: prd.md#4.7] — FR-14, non-goals (« v1 = édition manuelle »), conséquences testables
- [Source: architecture/ARCHITECTURE-SPINE.md] — `discover.py` nommé dans la structure cible, mapping FR-14 → AD-2/AD-3
- [Source: briefs/brief-agent-veille-emploi-ia-2026-07-20/addendum.md] — cartographie réelle, source du pool de candidats
- [Source: 4-3-recapitulatif-sources.md] — mécanisme de fragment idempotent + réapplication, réutilisés tels quels

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5 (`claude-sonnet-5`)

### Debug Log References

- `uv run python -m pytest tests/test_discover.py -q` : 19 passed — avant revue.
- `uv run python -m pytest tests/test_render.py tests/test_publish.py -q` : 91 passed (72 avant + 19 nouveaux : 6 render « À découvrir »/récapitulatif liste vide, 13 publish) — avant revue.
- `uv run python -m pytest tests/test_pipeline.py -q` : 40 passed (30 avant + 10 nouveaux) — avant revue, après correctif d'isolation `discover.CONNECTORS` (voir Completion Notes) — **temps d'exécution passé de 8.21s à 1.04s** après ce correctif, confirmant que de vrais appels réseau avaient lieu avant lui (même symptôme que le correctif `publish._jeton` de la Story 4.3).
- Suite complète (avant revue) : `uv run pytest -q` → 521 passed (479 avant cette story + 42 nouveaux : 19 discover, 6 render, 13 publish, 10 pipeline — écart de 6 explicable par des tests groupés différemment qu'anticipé dans les Tasks, aucune perte), aucune régression.
- Validation YAML du workflow modifié : `python -c "import yaml; yaml.safe_load(...)"` → OK, step `--decouvrir-source` présent avec ses clés attendues.
- Suite complète (après revue) : `uv run pytest -q` → 527 passed (521 + 6 nouveaux tests de revue), aucune régression. Un vrai bug introduit par un correctif de revue (voir Review Findings) a été trouvé et corrigé **avant** ce comptage final, pas après — capturé ici pour l'honnêteté de la piste d'audit.

### Review Findings

> Revue de code du 2026-09-18 (skill `bmad-code-review`, 3 couches adversariales, sur
> Sonnet 5 — même modèle que l'implémentation). Base de diff `7094baf` (= `baseline_commit`,
> changements non commités). Constat le plus sérieux (Blind Hunter) : la rotation
> déterministe recalculait son point de départ sur la taille du pool **après** exclusion
> des candidats déjà adoptés — adopter n'importe quel candidat en cours de semaine, même
> sans rapport avec celui affiché, pouvait silencieusement faire changer le candidat mis en
> avant avant la fin de la semaine, contredisant l'invariant documenté du module. Convergence
> partielle avec l'Edge Case Hunter sur l'exclusion trop étroite (uniquement par `id`, jamais
> par `url`) et sur l'absence de garde-fou contre un `id` dupliqué dans `config/candidats.yaml`.
> L'Acceptance Auditor n'a trouvé aucune violation d'AC réelle, seulement un défaut de
> robustesse mineur (encodage invalide non isolé). Un des correctifs appliqués pour traiter
> un autre constat (borne basse sur l'âge d'un item) a lui-même introduit un vrai bug — trouvé
> immédiatement en rejouant la suite, avant tout commit — corrigé dans la même passe.

**Correctifs appliqués (9) :**

- [x] [Review][Patch] La rotation déterministe (`aujourdhui.isocalendar().week % len(pool)`) se recalculait sur la taille du pool **après** exclusion des candidats déjà adoptés — adopter n'importe quel candidat en cours de semaine (même sans rapport avec celui affiché) pouvait décaler le point de départ et faire silencieusement changer le candidat proposé avant la fin de la semaine, contredisant l'invariant documenté (« reproduit le même candidat tant qu'il reste vérifié actif »). Corrigé : le calcul du point de départ et le parcours se font désormais sur le pool **complet** (`candidats`, jamais `disponibles`), les candidats déjà adoptés étant ignorés (`continue`) à l'intérieur de la boucle plutôt qu'exclus avant elle. Constat le plus sérieux de la revue (Blind Hunter) [src/veille/discover.py]
- [x] [Review][Patch] L'exclusion des candidats déjà adoptés ne comparait que l'`id` — un candidat adopté sous un `id` différent de celui de `config/candidats.yaml` (rien ne l'en empêche) continuerait d'être « redécouvert » indéfiniment. Corrigé : exclusion aussi par `url` (le flux, lui, ne ment pas). Constat (Edge Case Hunter) [src/veille/discover.py]
- [x] [Review][Patch] Deux entrées de `config/candidats.yaml` partageant le même `id` survivaient toutes les deux dans le pool sans avertissement, doublant silencieusement les chances de ce candidat dans la rotation. Corrigé : `charger_candidats` ignore et journalise tout doublon d'`id`. Constat (Edge Case Hunter) [src/veille/discover.py]
- [x] [Review][Patch] `justification` non-chaîne (liste, mapping, nombre — copier-coller malheureux) était silencieusement coercée par `str(...)` plutôt que rejetée comme toute autre entrée malformée, contrairement à `source` (validé par `SourceConfig`). Corrigé : type vérifié explicitement, entrée rejetée sinon (même chemin `except` que les autres malformations). Constat (Blind Hunter) [src/veille/discover.py]
- [x] [Review][Patch] Un item daté dans le futur par rapport à `maintenant` (horloge décalée, ou repli `datetime.now()` d'un connecteur — Story 2.1) produisait un `age_jours` négatif, toujours `<= SEUIL_RECENCE_JOURS`, donc accepté comme « frais » sans jamais être questionné. Corrigé : `0 <= age_jours <= SEUIL_RECENCE_JOURS`. Constat (Blind Hunter) [src/veille/discover.py]
- [x] [Review][Patch] **Bug introduit par le correctif précédent, trouvé en rejouant la suite avant tout commit** : `maintenant` était capturé **avant** le fetch réseau — un item daté par le connecteur via son propre `datetime.now()` interne se retrouvait donc mécaniquement postérieur à ce `maintenant` déjà figé (le fetch prend un temps non nul), rejeté à tort comme « daté dans le futur » par la borne basse ajoutée ci-dessus. Corrigé : `maintenant` n'est capturé qu'**après** le fetch, juste avant le calcul de fraîcheur. [src/veille/discover.py]
- [x] [Review][Patch] `UnicodeDecodeError` (levée par la lecture du fichier avant même `yaml.safe_load`) était absente du tuple `except` de `charger_candidats`, contrairement à ce que sa docstring promettait déjà (« absent/illisible/malformé »). Corrigé : ajoutée au tuple. Constat (Acceptance Auditor) [src/veille/discover.py]
- [x] [Review][Patch] `.github/workflows/controle-hebdomadaire.yml` : le commentaire au-dessus de `timeout-minutes: 10` affirmait encore « ce job ne fait ni collecte réseau par source ni appel LLM », rendu faux par le nouveau step de découverte ajouté par cette même story. Corrigé : commentaire mis à jour, plafond relevé à 15 minutes par prudence (vraies requêtes réseau désormais présentes). Constat (Blind Hunter) [.github/workflows/controle-hebdomadaire.yml]
- [x] [Review][Patch] Le nouveau step de découverte (`if: always()`) s'exécuterait même si le `checkout`/l'installation des dépendances avait échoué — bypassant le garde-fou par défaut de GitHub Actions (un step sans condition explicite est sauté si un step précédent échoue), pour un échec alors visible pour la mauvaise raison (« commande introuvable » plutôt que « checkout en échec »). Corrigé : `if: always() && steps.installer-dependances.outcome == 'success'`, `id` ajoutés aux steps de préparation. Constat (Edge Case Hunter) [.github/workflows/controle-hebdomadaire.yml]

**Reporté (2)**, ajoutés à `deferred-work.md` :

- La réapplication nocturne du panneau « À découvrir » (dans `pipeline.executer()`) revérifie en direct le pool de candidats chaque nuit, en plus du step hebdomadaire dédié — jusqu'à ~8 vérifications réseau par semaine au lieu d'une seule pour une fonctionnalité que la story qualifie elle-même d'hebdomadaire, avec une latence non bornée (le connecteur peut attendre jusqu'à 60s par tentative de repli sur 429) ajoutée au pipeline nocturne principal. Compromis de conception assumé (garantit l'honnêteté du panneau même si un candidat meurt en cours de semaine), coût non chiffré avant la revue — corriger proprement demanderait un nouvel état persistant (cache du dernier candidat vérifié) que la story évite délibérément. Constat (Blind Hunter).
- Une troisième écriture indépendante (GET+PUT, sans gestion de conflit 409/`sha` périmé) rejoint désormais `publier()`/`publier_recapitulatif_sante()` sur le même `index.html` — risque déjà identifié et sciemment non traité pour le récapitulatif de santé (Story 4.1, entrée du 2026-09-15), cette story ajoute un troisième écrivain au même schéma déjà accepté sans aggravation qualitative. Constat (Blind Hunter).

**Rejeté comme bruit (4)** :

- « Les deux CLI flags `--controle-sante`/`--decouvrir-source` dans le même `argv` ne déclenchent que le premier de la chaîne `elif` » (Edge Case Hunter) — chemin d'appel purement théorique : chaque step du workflow n'invoque jamais qu'un seul flag à la fois, aucun autre appelant n'existe.
- « `SEUIL_RECENCE_JOURS` dupliqué depuis `health.SEUIL_SUSPECTE_JOURS` sans rien garantissant leur synchronisation » (Blind Hunter) — cohérent avec le principe d'indépendance de module déjà établi et documenté à plusieurs reprises dans ce projet (AD-2, `store.py`/`publish.py`), pas une régression propre à cette story.
- « Isolation totale par `except Exception` sur chaque nouvelle fonction, rendant un vrai bug indiscernable d'une semaine calme » (Blind Hunter) — c'est très exactement AD-6 (« ne jamais lever »), appliqué ici avec la même discipline que partout ailleurs dans le projet depuis l'Epic 1 ; pas un défaut introduit par cette story.
- « Le panneau « À découvrir », inséré après le récapitulatif de santé lors de la réapplication nocturne, se retrouve visuellement au-dessus de lui plutôt qu'en dessous » (Edge Case Hunter) — purement cosmétique (ordre d'affichage de deux panneaux, aucune AC ne spécifie d'ordre entre eux), stable et déterministe d'une nuit à l'autre (jamais un flip aléatoire), sans perte d'information.

### Completion Notes List

- **AC1** : confirmé — `discover.proposer_source` propose au moins une source hors du socle (exclusion par `id` déjà adopté) avec sa `justification` (une phrase, portée dans `config/candidats.yaml`) ; pool couvrant les deux langues (9 en, 1 fr).
- **AC2** : confirmé — `verifier_candidat` revérifie en direct (vrai connecteur, `collect.CONNECTORS`) au moment même de la proposition, jamais une resserve d'une liste statique ; un candidat mort est sauté au profit du suivant de la rotation (`proposer_source`, testé).
- **AC3** : confirmé — panneau « À découvrir » publié sur `index.html` via `_inserer_fragment` (même mécanisme idempotent que le bandeau d'échec/le récapitulatif de santé) ; **réapplication nocturne par `executer()`** (construite dès l'implémentation, pas trouvée en revue cette fois) garantit la visibilité continue malgré la régénération complète de la page chaque nuit par `rendre()`/`publier()`.
- **AC4** : confirmé — aucune écriture sur `sources.yaml` nulle part dans `discover.py`/`pipeline.py` ; seule lecture (`config.load_sources`) pour exclure les candidats déjà adoptés.
- **AC5** : confirmé — `grep -rn "^import anthropic\|^from anthropic" src/` ne remonte toujours que `src/veille/enrich/llm.py` (invariant AD-7 inchangé) ; `discover.py` n'importe que `collect.CONNECTORS`/`config.load_sources`, jamais de LLM.
- **AC6** : confirmé — `charger_candidats`/`verifier_candidat`/`proposer_source` ne lèvent jamais (testé : fichier absent/malformé/encodage invalide, connecteur inconnu/qui lève, pool entièrement mort, `sources.yaml` illisible) ; `decouvrir_nouvelle_source`/la réapplication dans `executer()` isolées par leur propre `try/except`.
- **AC7** : confirmé — 527 tests passent après revue, aucune régression sur les Stories 4.1/4.2/4.3 (en dehors de la fixture d'isolation étendue de `test_pipeline.py`, nécessaire — voir ci-dessous).
- **Trouvé et corrigé en revue, avant tout commit** : la rotation déterministe recalculait son point de départ sur le pool **après** exclusion des candidats adoptés — adopter un candidat sans rapport avec celui affiché pouvait silencieusement le faire changer avant la fin de la semaine (constat le plus sérieux de la revue, voir Review Findings). Un correctif ultérieur de la même revue (borne basse sur l'âge d'un item) a lui-même introduit un vrai bug (`maintenant` capturé avant le fetch réseau) — trouvé immédiatement en rejouant la suite, corrigé dans la même passe, jamais commité en l'état.
- **Trouvé pendant l'implémentation, corrigé avant la revue formelle** : `config.load_sources()` lève `FileNotFoundError` sur un `sources.yaml` absent (pas de garde interne, contrat identique à `collect.collecter()`) — un premier brouillon de test supposait à tort une dégradation interne ; corrigé en réécrivant le test pour vérifier que `proposer_source()` isole cette exception à son tour (dégrade en `None`).
- **Trouvé pendant l'implémentation, corrigé avant la revue formelle — problème d'hygiène de test réel, pas hypothétique** : sans `candidats_path` explicite, `discover.proposer_source()` résout le **vrai** `config/candidats.yaml` du dépôt (10 candidats réels) — chaque test préexistant de `pipeline.executer()` (qui n'appelle jamais `proposer_source` avec un chemin explicite) aurait donc déclenché de vraies requêtes HTTP vers interconnects.ai, hamel.dev, deepmind.google, etc. à chaque exécution de la suite, en plus de casser deux assertions de comptage de `PUT` (un candidat vérifié avec succès ajoutait un panneau imprévu). Corrigé en neutralisant `discover.CONNECTORS` à `{}` dans la fixture `autouse` de `test_pipeline.py` (même réflexe que la neutralisation de `publish._jeton` trouvée en implémentation de la Story 4.3) — temps d'exécution mesuré : 8.21s avant, 1.04s après. Documenté explicitement plutôt que corrigé silencieusement.
- Nouveau paramètre `candidats_path` sur `pipeline.executer()` (non explicitement demandé par les Tasks, ajouté pour cohérence) : même convention d'injection que `sources_path`/`profil_path`/`deja_vus_path`, nécessaire pour que la réapplication nocturne du panneau « À découvrir » soit testable sans jamais dépendre du vrai `config/candidats.yaml` ni du réseau réel.

### File List

- `config/candidats.yaml` — nouveau : pool de 10 candidats réels (5 apprendre, 3 ce_qui_bouge, 2 pour_le_metier ; 9 en, 1 fr), puisés dans `addendum.md`.
- `src/veille/discover.py` — nouveau : `CandidatSource`, `charger_candidats()`, `verifier_candidat()`, `proposer_source()` ; modifié en revue : rotation basée sur le pool complet (pas le pool filtré, correctif le plus important de la revue), exclusion aussi par `url`, dédoublonnage des `id` à la lecture, `justification` non-chaîne rejetée, `UnicodeDecodeError` isolée, borne basse sur l'âge d'un item (et son propre correctif de suivi : `maintenant` capturé après le fetch, pas avant).
- `src/veille/render.py` — modifié : `A_DECOUVRIR_DEBUT`/`FIN`, `rendre_a_decouvrir()` (lève `ValueError` si `candidat=None`, échappement + `_url_surs` réutilisé tel quel) ; ajout au passage : `rendre_recapitulatif_sante([])` couverte par un test explicite de son `ValueError` (Story 4.3, jamais testé directement jusqu'ici).
- `src/veille/publish.py` — modifié : import `A_DECOUVRIR_DEBUT/FIN`/`rendre_a_decouvrir`, `_MOTIF_A_DECOUVRIR`, `publier_a_decouvrir()` (même patron à trois états que `publier_recapitulatif_sante`).
- `src/veille/pipeline.py` — modifié : import `discover`/`publier_a_decouvrir` ; `executer()` gagne le paramètre `candidats_path` et réapplique le panneau « À découvrir » après ses publications, indépendamment de `store_conn` ; nouvelles fonctions `decouvrir_nouvelle_source()`/`main_decouverte_source()` ; dispatch CLI `--decouvrir-source`.
- `templates/digest.html.j2` — modifié : variables CSS `--a-decouvrir-bg`/`-fg` (clair/sombre).
- `.github/workflows/controle-hebdomadaire.yml` — modifié : nouveau step `if: always()` appelant `--decouvrir-source`, réutilise `DIGEST_PUBLISH_TOKEN` (aucun nouveau secret), en-tête documenté ; modifié en revue : commentaire de plafond corrigé, `timeout-minutes` 10 → 15, `id` sur les steps de préparation, condition du nouveau step resserrée (`&& steps.installer-dependances.outcome == 'success'`).
- `tests/test_discover.py` — nouveau : 19 tests ; +6 en revue (encodage invalide, justification non-chaîne, id dupliqué, item du futur, exclusion par url, stabilité de la rotation).
- `tests/test_render.py` — modifié : 6 nouveaux tests (« À découvrir » + `ValueError` sur récapitulatif de santé vide).
- `tests/test_publish.py` — modifié : 13 nouveaux tests (panneau « À découvrir »).
- `tests/test_pipeline.py` — modifié : fixture `autouse` étendue (`discover.CONNECTORS` neutralisé), 10 nouveaux tests.
- `_bmad-output/implementation-artifacts/deferred-work.md` — modifié en revue : 2 nouvelles entrées différées (coût réseau/latence de la réapplication nocturne, troisième écrivain concurrent sur `index.html`).
- `_bmad-output/implementation-artifacts/4-4-proposer-nouvelle-source.md` — ce fichier (story).

### Change Log

| Date | Changement |
|---|---|
| 2026-09-18 | Story créée (`create-story`) et implémentée en une passe (Tasks 1-5) : `config/candidats.yaml` (10 candidats réels), `discover.py` (chargement/vérification/rotation déterministe), `rendre_a_decouvrir`/`publier_a_decouvrir` (même patron à trois états que la Story 4.3), câblage `decouvrir_nouvelle_source`/`main_decouverte_source`/`--decouvrir-source`, nouveau step de workflow `if: always()`, et — construite dès l'implémentation cette fois, pas trouvée en revue — réapplication nocturne du panneau par `executer()` (nouveau paramètre `candidats_path`). Deux bugs réels trouvés et corrigés en cours d'implémentation : hypothèse erronée sur la dégradation de `config.load_sources()` (lève, ne dégrade pas), et appels réseau réels dans les tests préexistants de `pipeline.executer()` faute d'isolation de `discover.CONNECTORS`. 42 nouveaux tests, 521 passed, aucune régression. Statut → review. |
| 2026-09-18 | Revue (3 couches, Sonnet) : 9 correctifs appliqués — le plus sérieux (Blind Hunter) : la rotation déterministe se recalculait sur le pool **après** exclusion des candidats adoptés, pouvant faire silencieusement changer le candidat proposé en cours de semaine en cas d'adoption d'un candidat sans rapport ; corrigé en basant le calcul sur le pool complet. Exclusion étendue à l'`url` (pas seulement l'`id`) ; `id` dupliqué désormais détecté et ignoré ; `justification` non-chaîne désormais rejetée comme toute autre entrée malformée ; borne basse ajoutée sur l'âge d'un item (rejette un item daté dans le futur) — correctif qui a lui-même introduit un vrai bug (`maintenant` capturé avant le fetch réseau), trouvé en rejouant la suite avant tout commit et corrigé dans la même passe ; `UnicodeDecodeError` désormais isolée dans `charger_candidats` ; commentaire/plafond du workflow hebdomadaire mis à jour ; condition du nouveau step resserrée pour ne pas s'exécuter si le checkout/l'installation échoue. 2 constats reportés (`deferred-work.md`) : coût réseau/latence de la réapplication nocturne (compromis de conception assumé), troisième écrivain concurrent sur `index.html` (risque déjà accepté depuis la Story 4.1). 4 rejets comme bruit. 6 nouveaux tests de revue, 527 passed. Statut → done. |
