---
baseline_commit: ab09b2f
---

# Story 2.3: Respecter les sources sensibles au débit

Status: done

## Story

As a Abdoulaye,
I want que mon agent ne se fasse pas bloquer par une source à cause de requêtes trop rapprochées,
so that je ne perde pas définitivement l'accès à une source utile.

## Acceptance Criteria

1. **[FR-2]** Étant donné une source qui répond `429` (limite de débit dépassée), l'agent respecte un délai de backoff avant de retenter — l'en-tête `Retry-After` du serveur est honoré quand il est présent (secondes uniquement) ; à défaut, un backoff exponentiel part d'un délai par défaut.
2. **[FR-2]** Le mécanisme de backoff est **partagé par les trois connecteurs** (`rss`, `json`, `scrape`) plutôt que triplé — un `429` sur n'importe laquelle des 17 sources actuelles, ou une future source réellement sensible au débit (ex. Reddit, cf. addendum, explicitement pas dans ce socle), en bénéficie sans code spécifique par source.
3. **[FR-2]** Après un nombre de tentatives borné (`MAX_TENTATIVES`), un `429` persistant redevient une panne normale — `RapportSource.echec` la porte avec sa cause, exactement comme toute autre panne HTTP (Story 2.2). Le backoff donne sa chance à la source, il ne remplace jamais l'isolation de panne existante (AD-6).
4. **[FR-2]** Un blocage temporaire d'une source (429 persistant après backoff) n'interrompt jamais la collecte des autres sources du socle — comportement déjà éprouvé (AD-6, Stories 1.1/1.2/2.1/2.2), à confirmer explicitement pour ce nouveau chemin.
5. Les garde-fous existants (`test_rss_connector.py`, `test_json_connector.py`, `test_scrape_connector.py`, `test_rapport_collecte.py`, `test_socle_reel.py`) continuent de passer sans modification ; de nouveaux tests verrouillent le backoff, sans jamais faire réellement attendre la suite (`time.sleep` monkeypatché).

## Tasks / Subtasks

- [x] Task 1 : Créer le mécanisme de backoff partagé (AC: 1, 2, 3)
  - [x] Nouveau module `src/veille/connectors/_reseau.py` (préfixe `_` : détail d'implémentation partagé entre connecteurs, pas un connecteur au sens d'AD-2 — ne casse pas le contrat `fetch(source_config) -> list[Item]`)
  - [x] `get_avec_backoff(url, *, timeout, headers=None, follow_redirects=True) -> httpx.Response` : appelle `httpx.get`, retente sur `429` jusqu'à `MAX_TENTATIVES` (défaut 3), respecte `Retry-After` (secondes ; un format illisible ou absent retombe sur le backoff exponentiel, jamais une exception) sinon un backoff exponentiel parti de `DELAI_DEFAUT_SECONDES` (5.0 — cohérent avec « espacer de 5-8s minimum » recommandé par l'addendum du brief pour Reddit). Au-delà de `MAX_TENTATIVES`, `raise_for_status()` lève normalement sur la dernière réponse 429.
  - [x] Toute autre erreur HTTP (403, 500…) lève immédiatement, sans retry — le backoff ne concerne que `429`, pas les pannes générales (déjà couvertes par l'isolation existante, Story 2.2)
  - [x] `time.sleep` appelé directement (pas de paramètre injectable) — les tests monkeypatchent `veille.connectors._reseau.time.sleep`, cohérent avec le patron déjà établi (Story 2.2 monkeypatche `module.httpx.get`) — 8 tests dans `tests/test_reseau.py`, tous verts

- [x] Task 2 : Brancher les trois connecteurs sur le mécanisme partagé (AC: 2)
  - [x] `rss_connector._charger` : remplace son appel direct à `httpx.get(...)` + `raise_for_status()` par `get_avec_backoff(...)` — `import httpx` conservé (non appelé directement, gardé pour que les tests existants de la Story 2.2 (`monkeypatch.setattr(module.httpx, "get", ...)`) continuent de fonctionner : `httpx` est un module singleton, muter son attribut `get` depuis n'importe quelle référence affecte l'appel réel fait dans `_reseau`, vérifié)
  - [x] `json_connector._charger` : idem (import `httpx` retiré ici, plus rien ne l'utilise directement dans ce fichier)
  - [x] `scrape_connector._charger` (récupération de la **page**, pas `robots.txt`) : idem
  - [x] `scrape_connector._collecte_autorisee` (requête `robots.txt`) **n'a volontairement pas été branchée** — inchangée, toujours son propre `httpx.get` direct
  - [x] Aucun changement de `TIMEOUT_SECONDES`/`USER_AGENT` par connecteur — confirmé, seul l'appel HTTP lui-même a été délégué (343 tests passent sans régression, y compris les 8 tests de la Story 2.2 qui monkeypatchent `httpx.get`)

- [x] Task 3 : Vérifier l'isolation de panne et l'absence de blocage inter-sources (AC: 3, 4)
  - [x] Nouveau test : un `429` persistant (au-delà de `MAX_TENTATIVES`) sur une source produit un `RapportSource.echec` normal, les autres sources du socle restent collectées (`test_un_429_persistant_devient_une_panne_normale_sans_bloquer_les_autres`, même patron que la Story 2.2)
  - [x] Nouveau test : un `429` qui réussit à la 2ᵉ tentative produit des items normalement, sans erreur remontée (`test_un_429_qui_reussit_apres_backoff_produit_des_items_normalement`)
  - [x] Nouveau test : l'en-tête `Retry-After` est respecté quand présent (délai exact passé à `time.sleep`) ; un backoff exponentiel est utilisé sinon — déjà verrouillé par `test_retry_after_est_respecte`/`test_retry_after_illisible_retombe_sur_le_backoff_exponentiel`/`test_backoff_exponentiel_sans_retry_after` (Task 1, `tests/test_reseau.py`)
  - [x] Nouveau test : une autre erreur HTTP (403/500) ne déclenche aucun retry, lève immédiatement — déjà verrouillé par `test_autre_erreur_http_leve_immediatement_sans_retry` (Task 1) ; confirmé aussi au niveau connecteur par le test existant inchangé de la Story 2.2 (`test_erreur_http_leve_pour_etre_capturee_par_l_isolation_de_panne`), toujours vert après le branchement sur `get_avec_backoff`

- [x] Task 4 : Validation (AC: 5)
  - [x] Suite complète (`uv run pytest`) rejouée sans régression, exécution rapide (1.41s pour 350 tests après revue — aucun test n'attend réellement, confirmé par `--durations=5`)
  - [x] Aucune modification des tests existants de `test_rss_connector.py`/`test_json_connector.py`/`test_scrape_connector.py`/`test_rapport_collecte.py`/`test_socle_reel.py` — confirmé par `git diff --stat` : seul `test_rapport_collecte.py` a des insertions, zéro suppression/modification sur les 5 fichiers

### Review Findings

> Revue de code du 2026-09-07 (skill `bmad-code-review`, 3 couches adversariales, sur
> Sonnet 5 — même modèle que l'implémentation, convention établie). Base de diff
> `ab09b2f` (= `baseline_commit`, changements non commités). Les 3 couches ont
> convergé indépendamment sur le même constat le plus sérieux : `Retry-After` n'était
> ni plafonné ni protégé contre les valeurs non finies (`inf`), ce qui contredisait
> à la fois la promesse de la docstring et, en théorie, l'esprit de l'AC4 (collecte
> séquentielle, un délai non borné pour une source retarderait toutes celles qui la
> suivent). L'Edge Case Hunter a confirmé empiriquement qu'un `Retry-After: inf`
> ferait planter `time.sleep` (`OverflowError`).

**Correctifs appliqués (4) :**

- [x] [Review][Patch] `_delai_depuis_retry_after` n'imposait aucun plafond à un `Retry-After` serveur légitime mais énorme (heures, jours) — la collecte étant strictement séquentielle (`collect.py`), un tel délai aurait retardé toutes les sources suivantes de `sources.yaml` pour la durée entière, en tension avec l'esprit de l'AC4. Corrigé par `DELAI_MAX_SECONDES = 60.0`. Constat convergent (Blind Hunter + Acceptance Auditor + Edge Case Hunter) [src/veille/connectors/_reseau.py]
- [x] [Review][Patch] `float()` accepte `"inf"`/`"1e300"` sans lever, mais `time.sleep` plante dessus (`OverflowError`, vérifié empiriquement par l'Edge Case Hunter) — contredisait la docstring de la fonction (« jamais une exception »). Corrigé : `math.isfinite(delai)` rejette explicitement `inf`/`nan` avant le plafonnement, retombe sur le backoff exponentiel comme tout en-tête illisible. Constat (Edge Case Hunter) [src/veille/connectors/_reseau.py]
- [x] [Review][Patch] `json_connector.py`/`scrape_connector.py` n'étaient jamais exercés de bout en bout avec un vrai 429 — seul `rss_connector.py` l'était, alors que l'AC2 affirme le backoff « partagé par les trois connecteurs ». Deux tests d'intégration ajoutés (`test_le_backoff_429_fonctionne_aussi_pour_une_source_json`, `test_le_backoff_429_fonctionne_aussi_pour_une_source_scrape` — ce dernier route aussi la requête `robots.txt`, interceptée par le même monkeypatch de module singleton, pour ne pas la confondre avec la requête de page). Constat convergent (Blind Hunter + Acceptance Auditor) [tests/test_rapport_collecte.py]
- [x] [Review][Patch] Les deux tests d'intégration de Task 3 monkeypatchaient `rss_connector.httpx.get` plutôt que `_reseau.httpx.get` — fonctionnait seulement parce que `httpx` est un module singleton partagé (couplage fragile signalé par le Blind Hunter : casserait silencieusement si `_reseau.py` passait un jour à un `httpx.Client()` persistant). Reciblé sur `_reseau.httpx.get` directement, sans ambiguïté. N'affecte pas les tests **existants** de la Story 2.2 (`test_rss_connector.py`), qui doivent rester inchangés (AC5) et pour lesquels ce couplage reste documenté et vérifié. Constat (Blind Hunter) [tests/test_rapport_collecte.py]

**Reporté (0) :** aucun.

**Rejeté comme bruit (6) :**

- « Pas de jitter sur le backoff exponentiel, risque de retry en lockstep si plusieurs sources partagent un hôte » — le jitter répond à une contention entre clients **concurrents** frappant le même hôte en même temps ; la collecte de ce projet est strictement séquentielle (une source à la fois), donc deux sources du même hôte ne peuvent jamais se retrouver en compétition temporelle réelle — le problème que le jitter résout ne se pose pas ici.
- « `scrape_connector._collecte_autorisee` (robots.txt) non branchée sur le backoff, un 429 y est traité comme "pas de robots.txt" » — déjà une décision délibérée et documentée (Task 2, Dev Notes) : une requête par source et par nuit, dégradation déjà propre. La contre-objection (« un 429 sur robots.txt juste avant la page pourrait aggraver la situation ») est réelle en théorie mais spéculative ici : rien dans ce socle ni dans les scénarios documentés ne l'observe, et brancher le backoff sur `_collecte_autorisee` referait aussi de cette fonction — actuellement conçue pour ne jamais lever — une source potentielle de délai. Non corrigé.
- « `MAX_TENTATIVES`/`DELAI_DEFAUT_SECONDES` codés en dur, sans réglage par source » — déjà une décision délibérée et documentée (Dev Notes, « Hors périmètre ») : aucune source actuelle n'a de besoin réel différent, un réglage par source serait de la généralité spéculative.
- « La story s'auto-évalue (cases cochées, chiffres) sans vérification indépendante intégrée au diff » — c'est précisément la raison d'être de cette étape de revue indépendante ; les chiffres cités (345 tests, fichiers de test inchangés) ont été vérifiés et confirmés exacts par les 3 couches elles-mêmes.
- « `docs/rapport-projet.md` non mis à jour dans ce diff » — attendu, commit séparé après la revue, convention établie depuis la Story 1.4.
- « Le type de `timeout` est `float` alors que tous les appelants passent un `int` » — sans conséquence (Python ne distingue pas les deux à l'exécution pour cet usage), non corrigé.

## Dev Notes

### Pourquoi cette story construit un mécanisme général plutôt que d'attendre une vraie source rate-limitée

Aucune des 17 sources actuelles de `config/sources.yaml` n'est aujourd'hui identifiée comme sensible au débit — l'addendum du brief documente précisément Reddit comme le cas le plus contraint (« `.json` → 403, `.rss` → 429 dès la 3ᵉ requête. Espacer de 5-8 s minimum, prévoir un backoff exponentiel ») et Reddit n'est **pas** dans ce socle (bloqué par une démarche OAuth de 2-4 semaines, hors périmètre — voir `addendum.md`). Le FR-2 du PRD demande pourtant explicitement ce mécanisme, et l'AC de cette story (`epics.md`) le formule en toute généralité (« une source connue pour limiter le débit »), pas pour une source précise. L'addendum lui-même le confirme : « Limites de débit — aucune API gratuite ne publie de quota chiffré... à découvrir empiriquement, prévoir du backoff **dès la v1** ». Cette story construit donc la capacité réactive (respecter un `429` quand il survient), pas une liste de sources pré-marquées « sensibles » en config — la première option ne demande aucune donnée de configuration nouvelle, la seconde serait de la généralité spéculative sans cas d'usage réel aujourd'hui.

### État actuel des trois connecteurs — ce que cette story change

Les trois fichiers ont été lus en entier avant l'écriture de cette story.

- **`rss_connector._charger`** (Story 2.2) : `httpx.get(url, timeout=TIMEOUT_SECONDES, follow_redirects=True, headers={"User-Agent": USER_AGENT})` puis `reponse.raise_for_status()`. Un `429` lève immédiatement aujourd'hui — aucune tentative de nouvelle requête.
- **`json_connector._charger`** (Story 1.2) : `httpx.get(url, timeout=TIMEOUT_SECONDES, follow_redirects=True)` (pas de `User-Agent`, inchangé — hors périmètre) puis `reponse.raise_for_status()`. Même limitation.
- **`scrape_connector._charger`** (Story 1.2) : `httpx.get(url, timeout=TIMEOUT_SECONDES, follow_redirects=True, headers={"User-Agent": USER_AGENT})` puis `reponse.raise_for_status()`. Même limitation. **Distinct** de `_collecte_autorisee` (requête `robots.txt`), qui a son propre `httpx.get` et son propre `try/except Exception` — ne pas confondre les deux fonctions en branchant le backoff par erreur sur `_collecte_autorisee`.

**Ce que cette story change** : les trois `_charger` (page/flux/API, jamais `robots.txt`) délèguent leur appel HTTP à `get_avec_backoff` (nouveau module `_reseau.py`) plutôt que d'appeler `httpx.get` directement. Le comportement pour tout code de statut autre que `429` reste strictement identique (une seule tentative, lève immédiatement). Aucun changement de signature publique — `fetch(source_config) -> list[Item]` (AD-2) est intact sur les trois connecteurs.

### Pourquoi un module partagé plutôt que trois copies

Après la Story 2.2, les trois connecteurs partagent déjà la même forme (`httpx.get` + `timeout` + `raise_for_status`), mais chacun sa propre copie. Ajouter une boucle de retry avec backoff à chacune séparément tripleraient une logique non triviale (lecture de `Retry-After`, calcul exponentiel, journalisation) — un bug corrigé dans une copie ne le serait pas dans les deux autres, contrairement à l'esprit de la décision #15 du journal (« un correctif trouvé... appliqué par cohérence aux fonctions sœurs »). Un module `_reseau.py` (préfixé `_`, jamais importé par autre chose que les trois connecteurs) centralise la logique une seule fois, sans toucher au contrat public `fetch()` d'AD-2 ni introduire de nouvelle dépendance (aucune bibliothèque de retry externe — `httpx` seul suffit, la boucle est simple).

### Précédents à réutiliser, pas à réinventer

- **`_fetch_one` (`collect.py`, AD-6)** — l'isolation de panne par source existe déjà et n'a besoin d'aucune modification : un `429` qui épuise ses tentatives lève comme n'importe quelle autre exception HTTP, déjà capturée et journalisée avec sa cause depuis la Story 2.2.
- **Monkeypatcher `httpx.get`/`time.sleep`, jamais de vrai réseau ni de vraie attente** (patron établi Story 2.2 : `monkeypatch.setattr(module.httpx, "get", ...)`) — à reproduire à l'identique pour `_reseau.py`, plus `monkeypatch.setattr(reseau_module.time, "sleep", ...)` pour intercepter les délais sans jamais ralentir la suite.
- **`httpx.Response(status_code, headers=..., request=...)` réel** (pas un mock) pour simuler une réponse HTTP dans les tests, déjà utilisé dans `test_rss_connector.py`/`test_rapport_collecte.py` (Story 2.2) — même construction pour simuler un `429` avec ou sans `Retry-After`.
- **`sources_en_panne_reseau`/`taux_echec`/`anomalie_pannes`** (`collect.py`, Story 2.2) — un `429` épuisé après backoff est un `RapportSource.echec` de type reconnu (`type in CONNECTORS`), donc compté normalement dans le taux de panne réseau ; aucune modification nécessaire à ce mécanisme.

### Hors périmètre — ne pas anticiper

- **Reddit lui-même** — nécessite une démarche OAuth (2-4 semaines, addendum) et n'est pas dans le socle actuel ; cette story construit la capacité, pas l'ajout de la source (qui resterait de toute façon hors du « sans modification de code » si elle demandait une authentification, comme Kaggle en Story 2.1).
- **Marquer certaines sources comme « sensibles au débit » dans `sources.yaml`** — pas nécessaire : le mécanisme réagit à un vrai `429` reçu, quelle que soit la source, sans configuration supplémentaire (voir section dédiée ci-dessus).
- **Backoff sur `503`/autres codes transitoires** — l'AC ne parle que de limite de débit (`429`) ; élargir à `503` sans cas d'usage documenté serait spéculatif. À reconsidérer si un jour une source réelle du socle le justifie.
- **`Retry-After` au format date HTTP** (`Retry-After: Wed, 21 Oct 2026 07:28:00 GMT`) — seul le format numérique (secondes) est géré ; le format date existe dans la RFC mais aucune source connue de ce projet ne l'utilise. Un en-tête illisible retombe silencieusement sur le backoff exponentiel, jamais une exception.
- **Backoff sur la requête `robots.txt`** (`scrape_connector._collecte_autorisee`) — voir Task 2, déjà une dégradation propre et peu coûteuse (une requête par source et par nuit), pas le scénario que cette story vise.
- **Story 2.4** (dédoublonnage à l'échelle) — sans lien avec cette story.

### Testing Standards

- `pytest`, via `uv run pytest`. Aucun test ne doit réellement attendre — `time.sleep` est systématiquement monkeypatché dans `_reseau.py`, jamais appelé pour de vrai pendant la suite. Simuler les réponses HTTP via de vrais objets `httpx.Response` (statut, en-têtes, `request=httpx.Request(...)`), comme la Story 2.2 l'a déjà établi — pas de nouvelle bibliothèque de mock HTTP.
- Aucune vérification réseau réelle requise pour cette story (contrairement aux Stories 1.1/1.2/2.1/2.2) : aucune source du socle actuel n'est connue pour émettre un vrai `429` en usage normal, donc rien à observer en conditions réelles qui ne soit pas déjà simulable par un `httpx.Response(429, ...)` construit à la main.

### Previous Story Intelligence

- **Story 2.2** a fermé le dernier trou de timeout réseau (`rss_connector.py`) et introduit le patron `httpx.get(...) + raise_for_status()` désormais identique sur les trois connecteurs — précondition directe pour que cette story puisse factoriser un point d'appel commun sans devoir d'abord harmoniser les trois `_charger`.
- Revue de la Story 2.2 : convergence sur l'importance de tester le contenu réel des réponses simulées (pas seulement des comptes), et sur la nécessité de nommer explicitement ce qu'un mécanisme *ne* couvre *pas* (ex. `robots.txt` non branché ici, à documenter aussi clairement que ce qui l'est).
- Convention de commit établie (Stories 1.4-2.2) : un commit implémentation+revue, un commit séparé pour `docs/rapport-projet.md`, tous deux poussés.
- `_bmad/`, `.claude/`, `_bmad-output/` suivis par git — `git add -A` couvre tout.

### Git Intelligence Summary

Commits récents : Story 2.2 (implémentation + revue, `0de7939`), rapport de projet (commit séparé, `ab09b2f`). Même convention à reproduire ici.

### Project Structure Notes

Léger écart au Structural Seed, documenté et justifié ci-dessus : introduction de `src/veille/connectors/_reseau.py`, un module de détail partagé entre connecteurs (préfixé `_`, jamais exposé hors du dossier `connectors/`), pas un connecteur au sens d'AD-2. Le contrat public `fetch(source_config) -> list[Item]` de chaque connecteur reste inchangé.

### References

- [Source: epics.md#Story-2.3] — story d'origine et critères d'acceptation (Given/When/Then)
- [Source: prd.md#FR-2] — tolérance aux pannes, backoff sur sources sensibles au débit
- [Source: brief-agent-veille-emploi-ia-2026-07-20/addendum.md] — Reddit (429 dès la 3ᵉ requête, backoff 5-8s recommandé), Semantic Scholar (429 sans clé), limites de débit à découvrir empiriquement
- [Source: 2-2-continuer-en-panne.md] — précédent immédiat : timeout réseau harmonisé sur les trois connecteurs, patron `httpx.get + raise_for_status`, isolation de panne AD-6 exercée en conditions simulées

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5 (`claude-sonnet-5`)

### Debug Log References

- `uv run pytest tests/test_reseau.py -q` avant implémentation : `ImportError: cannot import name '_reseau' from 'veille.connectors'` — RED confirmé pour la bonne raison.
- Après Task 1 : `uv run pytest tests/test_reseau.py -q` → 8 passed.
- Après Task 2 : `uv run pytest tests/test_rss_connector.py tests/test_rapport_collecte.py tests/test_json_connector.py tests/test_scrape_connector.py -q` → 62 passed, y compris les 8 tests de la Story 2.2 qui monkeypatchent `module.httpx.get` directement (vérifié que le partage du module singleton `httpx` entre `rss_connector`/`scrape_connector` et `_reseau` laisse ces monkeypatchs opérants sur l'appel réel).
- Après Task 3 : `uv run pytest tests/test_rapport_collecte.py -q` → 13 passed.
- Suite complète finale : `uv run pytest -q --durations=5` → 345 passed en 1.53s, aucun test parmi les plus lents n'est lié au backoff (confirme qu'aucun `time.sleep` réel n'a eu lieu).

### Completion Notes List

- **AC1/AC2/AC3** : `src/veille/connectors/_reseau.py` (nouveau) centralise `get_avec_backoff` — retry sur `429` uniquement (jusqu'à `MAX_TENTATIVES=3`), `Retry-After` respecté (secondes, plafonné à `DELAI_MAX_SECONDES=60` et rejeté s'il n'est pas fini — correctif de revue ; illisible → backoff exponentiel), toute autre erreur HTTP lève immédiatement sans retry. Branché sur les trois `_charger` (`rss_connector.py`, `json_connector.py`, `scrape_connector.py`, chacun désormais vérifié de bout en bout avec un vrai 429 — correctif de revue) — jamais sur `scrape_connector._collecte_autorisee` (robots.txt), conformément à la décision actée en Dev Notes.
- **AC4** : confirmé par test d'intégration (`test_un_429_persistant_devient_une_panne_normale_sans_bloquer_les_autres`) — un 429 persistant devient un `RapportSource.echec` normal (cause « 429 » présente), la source vivante du même socle reste collectée normalement. AD-6 inchangé, aucune modification de `collect.py` n'a été nécessaire pour ce point.
- **Écart trouvé et documenté pendant Task 2, pas un défaut** : `rss_connector.py` doit conserver `import httpx` alors que son code ne l'appelle plus directement (délégué à `_reseau`) — sans quoi les 8 tests existants de la Story 2.2 qui font `monkeypatch.setattr(module.httpx, "get", ...)` échoueraient avec une `AttributeError`, une erreur de test sans rapport avec le comportement réellement changé. Vérifié empiriquement que `httpx` étant un module singleton (`sys.modules`), muter son attribut `get` depuis n'importe quelle référence (`rss_connector.httpx` ou `_reseau.httpx`) affecte l'appel réel où qu'il ait lieu — les 8 tests passent sans aucune modification. Documenté par un commentaire dans le code, pas seulement ici.
- **`json_connector.py`** : `import httpx` entièrement retiré (plus aucun appel direct dans ce fichier, contrairement à `rss_connector.py`/`scrape_connector.py` qui gardent chacun une raison de le conserver — voir ci-dessus et robots.txt).
- **Aucune vérification réseau réelle effectuée** — cohérent avec les Dev Notes de la story : aucune source du socle actuel n'est connue pour émettre un vrai `429`, rien à observer en conditions réelles qui ne soit pas déjà simulable par un `httpx.Response(429, ...)` construit à la main (déjà fait dans les 10 tests ajoutés).
- **Hors périmètre confirmé non touché** : aucune source marquée « sensible au débit » dans `sources.yaml` ; aucun retry sur `503` ; `Retry-After` au format date HTTP non géré (retombe sur le backoff exponentiel, pas une exception) ; `scrape_connector._collecte_autorisee` non branchée sur le backoff.
- Convention de commit reproduite (Stories 1.4-2.2) : commit implémentation+revue, puis commit séparé pour `docs/rapport-projet.md`, tous deux poussés sur `origin/main`.

### File List

- `src/veille/connectors/_reseau.py` — nouveau : `get_avec_backoff`, backoff partagé sur 429 (`MAX_TENTATIVES`, `DELAI_DEFAUT_SECONDES`, `DELAI_MAX_SECONDES`, respect plafonné de `Retry-After`).
- `src/veille/connectors/rss_connector.py` — modifié : `_charger` délègue à `get_avec_backoff` ; `import httpx` conservé (raison documentée en commentaire) ; `raise_for_status()` retiré (géré par `_reseau`).
- `src/veille/connectors/json_connector.py` — modifié : `_charger` délègue à `get_avec_backoff` ; `import httpx` retiré (plus utilisé directement).
- `src/veille/connectors/scrape_connector.py` — modifié : `_charger` (page) délègue à `get_avec_backoff` ; `_collecte_autorisee` (robots.txt) inchangée, toujours son propre `httpx.get`.
- `tests/test_reseau.py` — nouveau puis étendu en revue : 11 tests unitaires de `get_avec_backoff` (succès direct, retry puis succès, épuisement après `MAX_TENTATIVES`, `Retry-After` respecté/illisible/plafonné/infini, backoff exponentiel, autre erreur HTTP sans retry, panne réseau pendant le backoff non avalée, transmission des paramètres).
- `tests/test_rapport_collecte.py` — modifié : 4 nouveaux tests d'intégration (429 persistant isolé sans bloquer les autres sources, 429 qui réussit après backoff pour `rss`/`json`/`scrape`) ; les 2 premiers reciblés en revue sur `_reseau.httpx` plutôt que `rss_connector.httpx`.
- `_bmad-output/implementation-artifacts/2-3-respecter-le-debit.md` — ce fichier (story).

### Change Log

| Date | Changement |
|---|---|
| 2026-09-07 | Story créée (Tasks 1-4 planifiées). |
| 2026-09-07 | Task 1 : module `_reseau.py` créé (`get_avec_backoff`), 8 tests unitaires. |
| 2026-09-07 | Task 2 : les trois connecteurs branchés sur le mécanisme partagé ; écart trouvé et documenté (conserver `import httpx` dans `rss_connector.py` pour la compatibilité des tests existants de la Story 2.2, vérifié sans risque — module singleton). |
| 2026-09-07 | Task 3 : isolation de panne confirmée pour un 429 persistant (n'empêche pas la collecte des autres sources) et pour un 429 qui réussit après backoff (aucune trace d'échec). |
| 2026-09-07 | Task 4 : suite complète rejouée (345 passed, 1.53s), aucune régression, aucune modification de test existant. Statut → review. |
| 2026-09-07 | Revue (3 couches, Sonnet) : 4 correctifs appliqués (`Retry-After` plafonné à 60s et protégé contre `inf`/`nan`, backoff vérifié de bout en bout pour `json`/`scrape` en plus de `rss`, tests reciblés sur `_reseau.httpx` plutôt que sur le couplage fragile via `rss_connector.httpx`), 0 report, 6 rejetés comme bruit. 350 passed. Statut → done. |
