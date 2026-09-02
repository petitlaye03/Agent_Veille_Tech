---
baseline_commit: c448b0f
---

# Story 2.2: Continuer à fonctionner quand une source tombe en panne

Status: done

## Story

As a Abdoulaye,
I want ne jamais me retrouver sans digest parce qu'une seule source a eu un problème cette nuit-là,
so that mon agent reste fiable même quand l'écosystème ne l'est pas.

## Acceptance Criteria

1. **[FR-2]** Étant donné une source qui répond en erreur (timeout, 403, 429, ou toute autre panne réseau/HTTP) pendant la collecte, les autres sources sont tout de même collectées et le digest est produit — comportement déjà éprouvé (AD-6, Stories 1.1/1.2/2.1) pour les connecteurs `json`/`scrape`, à combler pour `rss` (voir AC2).
2. **[FR-2, dette fermée]** `rss_connector.py` applique un délai d'attente réseau explicite (`TIMEOUT_SECONDES`, même valeur que `json_connector.py`/`scrape_connector.py` ; même **esprit** de dispatch réseau vs local — la condition de branchement est nécessairement inversée par rapport aux deux autres, voir Dev Notes) — une source RSS qui ne répond jamais ne doit plus pouvoir bloquer indéfiniment tout le run. Dette suivie depuis la Story 1.1, explicitement fléchée vers cette story.
3. **[FR-2]** Une panne HTTP réelle (403, 429, 500…) sur une source RSS est **journalisée avec sa cause** dans `RapportSource.echec` — pas absorbée silencieusement dans le mécanisme `bozo` de `feedparser` (qui la rend aujourd'hui indiscernable d'un flux simplement vide).
4. **[FR-2]** Si plus de la moitié des sources du socle échouent la même nuit **par panne réseau/HTTP réelle** (ni « muette », ni « absorbée », ni une source dont le `type` est mal orthographié — voir Dev Notes), le digest est quand même produit à partir de ce qui a pu être collecté, et l'anomalie est signalée par un journal `ERROR` agrégé et nommant les sources concernées, distinct des traces `logger.exception` déjà émises individuellement par source (elles aussi au niveau `ERROR`, mais noyées dans le journal d'une nuit chargée).
5. Les garde-fous existants (`test_socle_reel.py`, `test_rss_connector.py`, `test_rapport_collecte.py`, `test_collecte_integration.py`) continuent de passer sans modification pour les invariants déjà couverts ; de nouveaux tests verrouillent les AC2/AC3/AC4.

## Tasks / Subtasks

- [x] Task 1 : Ajouter un délai d'attente réseau explicite à `rss_connector.py` (AC: 2, 3)
  - [x] Introduire `TIMEOUT_SECONDES = 30` (même valeur que `json_connector.py`/`scrape_connector.py`)
  - [x] Récupérer le flux via `httpx.get(url, timeout=TIMEOUT_SECONDES, follow_redirects=True, headers={"User-Agent": ...})` pour toute URL `http(s)://`, puis passer le contenu récupéré (`reponse.content`) à `feedparser.parse()` — jamais l'URL directement pour une source réseau
  - [x] `reponse.raise_for_status()` avant de passer la main à `feedparser` : une erreur HTTP (403/429/500…) doit lever, pas être avalée par le mécanisme `bozo`
  - [x] Préserver le chemin **local** (chemin de fichier brut ou `file://`, utilisés par tous les tests existants) : `feedparser.parse(url)` directement, sans passer par `httpx` — comportement strictement inchangé pour ces cas (vérifié : `test_chemin_local_ne_passe_pas_par_httpx`, les 6 tests locaux préexistants passent sans modification)
  - [x] Par cohérence avec `scrape_connector.py` (décision #15 du journal, `rapport-projet.md` §7), envoyer le même `User-Agent` explicite sur la requête réseau — ferme au passage la dette « aucun User-Agent envoyé par feedparser » (Story 1.1, Epic 2)

- [x] Task 2 : Vérifier que l'isolation de panne AD-6 tient réellement pour `rss_connector.py` (AC: 1, 3)
  - [x] Nouveau test : une réponse HTTP 403/500 simulée sur une source RSS produit un `RapportSource.echec` non vide (pas « muette »), sans lever hors de l'isolation de `collect._fetch_one` (`test_erreur_http_leve_pour_etre_capturee_par_l_isolation_de_panne`, + confirmation au niveau `collect.py` dans Task 3)
  - [x] Nouveau test : un dépassement de délai d'attente réseau simulé sur une source RSS est capturé par la même isolation, cause renseignée (`test_timeout_reseau_leve_pour_etre_capture_par_l_isolation_de_panne`)
  - [x] Confirmer que les tests existants de `test_rss_connector.py` (6 tests, chemins locaux) passent sans modification — 10/10 passent (6 existants + 4 nouveaux)
  - [x] **Vérification réseau réelle, avant/après** : rejouée contre `tldr-ai` (20 items, identique à la Story 2.1), `lemonde-informatique` (20 items, même contenu, même avertissement `bozo` de structure XML) et `openai-news` (1162 items, identique). Aucune perte d'entrée. **Trouvaille documentée** : pour `tldr-ai` précisément, le passage par `httpx` (bytes) fait disparaître l'avertissement `bozo` d'encodage (« document declared as us-ascii, but parsed as utf-8 ») que `feedparser` produisait avec sa propre récupération directe — `feedparser` retombe correctement sur la détection d'encodage du contenu plutôt que sur l'en-tête `Content-Type` erroné du serveur. Effet positif, pas une régression : mêmes 20 entrées obtenues dans les deux cas, voir Completion Notes.

- [x] Task 3 : Détecter et signaler une nuit où plus de la moitié des sources échouent (AC: 4)
  - [x] `ResultatCollecte` expose `taux_echec` (propriété calculée à partir de `sources_en_echec`/`rapports`, pas un champ stocké redondant) et `anomalie_pannes` (`taux_echec > 0.5`, égalité exacte à 50 % explicitement exclue)
  - [x] `_journaliser` (`collect.py`) émet un journal de niveau `ERROR` distinct quand `anomalie_pannes` est vrai, mentionnant le compte exact (« N/M sources en échec (X%) »)
  - [x] Le digest continue d'être produit normalement dans ce cas — confirmé par test (`resultat.items` non vide alors que 3/4 sources échouent)
  - [x] Nouveau test dans `test_rapport_collecte.py` : `test_anomalie_signalee_quand_plus_de_la_moitie_des_sources_echouent` (3/4 en échec → anomalie active, digest produit, journal ERROR contenant « 3/4 ») et `test_pas_d_anomalie_quand_la_moitie_ou_moins_des_sources_echouent` (1/2 en échec = 50 % exactement → pas d'anomalie)

- [x] Task 4 : Validation (AC: 5)
  - [x] Suite complète (`uv run pytest`) rejouée sans régression — 335 passed après revue (324 avant cette story + 11 nouveaux, dont 4 ajoutés en revue)
  - [x] Aucune modification des tests existants de `test_rss_connector.py`/`test_rapport_collecte.py`/`test_socle_reel.py`/`test_collecte_integration.py` — confirmé par `git diff --stat` : uniquement des insertions, zéro suppression/modification de ligne existante

### Review Findings

> Revue de code du 2026-09-02 (skill `bmad-code-review`, 3 couches adversariales, sur
> Sonnet 5 — même modèle que l'implémentation, convention établie). Base de diff
> `c448b0f` (= `baseline_commit`, changements non commités). Les 3 couches ont
> chacune trouvé des angles différents, sans recouvrement direct — signe d'une
> revue qui a réellement exploré plutôt que de converger sur un seul défaut.

**Correctifs appliqués (7) :**

- [x] [Review][Patch] `rss_connector._charger` dispatchait sur `str.startswith(("http://", "https://"))`, sensible à la casse et à un espace de tête — contrairement à `scrape_connector._collecte_autorisee`, qui utilise déjà `urlparse(...).scheme`. Un schéma `HTTP://` (ou une URL mal formée) retombait silencieusement sur la branche locale, réintroduisant pour cette seule URL exactement la panne que cette story ferme (pas de timeout, erreur HTTP avalée par `bozo`). Corrigé par `urlparse(url).scheme not in ("http", "https")`. Constat (Edge Case Hunter) [src/veille/connectors/rss_connector.py, `_charger`]
- [x] [Review][Patch] `taux_echec`/`anomalie_pannes` comptaient une source dont le `type` est mal orthographié dans `sources.yaml` (ex. `type: rrs`) comme une panne réseau/HTTP — alors que c'est une erreur de configuration statique, jamais tentée par un connecteur. Quelques fautes de frappe dans le socle auraient pu déclencher à tort l'anomalie « >50% de pannes », qui se lit comme un incident réseau de la nuit. Corrigé : nouvelle propriété `sources_en_panne_reseau` (filtre `sources_en_echec` sur `type in CONNECTORS`), utilisée par `taux_echec`/`anomalie_pannes` et par le journal `ERROR`. Constat convergent (Edge Case Hunter + Blind Hunter) [src/veille/collect.py]
- [x] [Review][Patch] Le journal `ERROR` d'anomalie ne nommait pas les sources en panne — un opérateur devait recorréler avec les traces individuelles éparses de `_fetch_one` pour savoir lesquelles. Corrigé : les `source_id` concernés sont désormais listés dans le message. Constat (Blind Hunter) [src/veille/collect.py, `_journaliser`]
- [x] [Review][Patch] AC4/Dev Notes affirmaient que le nouveau journal `ERROR` est « distinct du WARNING par source déjà existant » — imprécis : une panne par source était déjà journalisée en `ERROR` (via `logger.exception` dans `_fetch_one`, Story 1.1), pas en `WARNING`. Corrigé : la story décrit maintenant le nouveau journal comme une ligne **agrégée**, distincte des traces individuelles déjà au niveau `ERROR`, pas comme le premier signal `ERROR`. Constat (Blind Hunter) [story, AC4 + Dev Notes]
- [x] [Review][Patch] AC2/Dev Notes affirmaient que `rss_connector._charger` suit « le patron exact » de `json_connector._charger`/`scrape_connector._charger` — en réalité la condition de branchement est inversée (les deux autres dispatchent sur `file://` → local ; `rss_connector` dispatche sur `http(s)://` → réseau), une nécessité déjà justifiée dans les Dev Notes mais que le mot « exact » masquait. Corrigé : la story parle maintenant de « même esprit », avec la justification de l'inversion mise en avant plutôt qu'en aparté. Constat convergent (Acceptance Auditor + Blind Hunter) [story, AC2 + Dev Notes]
- [x] [Review][Patch] AC1 (« les autres sources sont tout de même collectées ») n'était testé pour `rss_connector.py` qu'associé à des sources d'un **autre** type (json cassé + rss vivante) ou avec un socle à une seule source RSS — jamais deux sources RSS dans le même run, l'une en panne HTTP, l'autre vivante. Nouveau test ajouté : `test_une_source_rss_en_panne_http_n_empeche_pas_la_collecte_d_une_autre_source_rss`. Constat (Acceptance Auditor) [tests/test_rapport_collecte.py]
- [x] [Review][Patch] La vérification réseau réelle (Task 2) ne comparait que le **nombre** d'items avant/après le changement — insuffisant pour détecter un mauvais décodage silencieux (accents corrompus) qui préserverait le compte. Nouveau test automatisé et reproductible ajouté, simulant un en-tête `Content-Type: charset=us-ascii` menteur sur un corps réellement UTF-8 accentué (même désaccord que `tldr-ai` en réel) : `test_encodage_reste_correct_malgre_un_en_tete_content_type_menteur`. Constat (Blind Hunter) [tests/test_rss_connector.py]

**Reporté (1) :**

- [x] [Review][Defer] `httpx.get(..., follow_redirects=True)` n'impose aucune limite au nombre/à la durée totale des sauts de redirection, sur les trois connecteurs — un chaînage de redirections pourrait faire durer une source bien au-delà des 30s nominaux. Motif préexistant (déjà dans `json_connector.py`/`scrape_connector.py` depuis la Story 1.2), pas introduit par cette story — cette story ne fait que reproduire le même motif pour `rss_connector.py`, par cohérence. Ajouté à `deferred-work.md`. Constat (Edge Case Hunter) [src/veille/connectors/*.py]

**Rejeté comme bruit (6) :**

- « Les sources "muettes" (200 OK, structure inexploitable) ne comptent jamais dans `anomalie_pannes` » — choix délibéré, pas un oubli : l'AC4 et FR-2 parlent explicitement de sources « qui répondent en erreur », une source muette a répondu avec succès. Déjà couvert séparément (`WARNING` par source muette). Clarifié en Dev Notes plutôt que corrigé en code.
- « Le seuil de 50 % reste une hypothèse PRD non confirmée par Abdoulaye, verrouillée sans validation » — correspond mot pour mot à la formulation de `epics.md` (« plus de la moitié »), le relecteur lui-même note que cela atténue le risque ; aucune action.
- « Les doublures de test pour `httpx.get` codent en dur la signature exacte de l'appel (`url, timeout, follow_redirects, headers`), dupliquée dans 4 tests » — dette de qualité de test mineure, cohérente avec le style déjà en place ailleurs dans la suite (pas de fixture partagée pour les doubles HTTP dans ce projet) ; refactoring disproportionné pour cette story.
- « Aucun test n'exerce `_charger()` directement, seulement via `fetch()` » — cohérent avec le style de test déjà établi pour `json_connector`/`scrape_connector`, dont les `_charger()` respectifs ne sont pas non plus testés isolément.
- « Le compte "7 nouveaux tests" gonfle le nombre de garanties réellement indépendantes (chevauchement unitaire/intégration) » — remarque sur la présentation, pas un défaut ; le chevauchement unitaire/intégration est une pratique délibérée du projet (voir Story 1.3, décision journal #3).
- « La boucle de collecte reste séquentielle : plusieurs sources qui expirent chacune sous 30s peuvent quand même cumuler N×30s » — hors périmètre explicite de cette story (parallélisation/backoff = Story 2.3), le correctif ne prétend borner que la panne d'**une** source, jamais la durée totale du run.

## Dev Notes

### État actuel de `src/veille/connectors/rss_connector.py` — ce que cette story change

Fichier lu en entier avant l'écriture de cette story. Aujourd'hui :

```python
def fetch(source_config: SourceConfig) -> list[Item]:
    feed = feedparser.parse(source_config.url)   # <-- pas de timeout, pas de statut HTTP vérifié
    if feed.bozo:
        ...
```

`feedparser.parse(url)` fait sa propre récupération réseau en interne (`urllib` sous le capot), sans paramètre de timeout exposé par ce connecteur, et sans jamais lever d'exception réseau observable : une erreur HTTP ou un flux inaccessible se traduit uniquement par `feed.bozo=1` + `feed.entries` vide, déjà géré (retourne `[]`), **mais sans que `collect._fetch_one` ne le voie comme un échec** — la source remonte comme **« MUETTE »** (zéro item, sans erreur) dans `RapportSource`, pas comme **« ÉCHEC »** avec une cause. Une vraie panne HTTP (403/429/500) et un flux simplement vide sont donc aujourd'hui indiscernables pour `rss_connector.py`, alors qu'ils le sont déjà pour `json_connector.py`/`scrape_connector.py` (tous deux lèvent une exception HTTP via `raise_for_status()`, capturée par l'isolation générique de `_fetch_one`).

**Ce que cette story change** : `rss_connector.py` récupère lui-même le flux via `httpx` (timeout + `raise_for_status()`) pour toute URL réseau, exactement comme les deux autres connecteurs le font déjà dans leur propre `_charger()` — puis passe le **contenu** récupéré (pas l'URL) à `feedparser.parse()`. Une panne HTTP devient alors une exception réelle, capturée par l'isolation déjà existante de `_fetch_one` (`collect.py:318-325`), avec une cause lisible dans `RapportSource.echec` — sans qu'aucune modification de `collect.py` ne soit nécessaire pour ce point précis : l'isolation générique par source existe déjà et suffit.

**Ce qui doit rester identique** : le comportement `bozo` (flux imparfait mais exploitable) reste inchangé — il concerne un contenu récupéré avec succès mais mal formé, pas une panne réseau/HTTP. Et surtout : **tous les tests existants de `test_rss_connector.py` passent une URL locale** (chemin de fichier brut, ex. `str(FIXTURE_DIR / "sample_feed.xml")`) — ces chemins doivent continuer à être traités directement par `feedparser.parse()`, sans passer par `httpx` (qui échouerait sur un chemin qui n'est pas une URL réseau). Le dispatch doit donc se faire sur le **schéma** de l'URL (`http://`/`https://` → réseau via `httpx` ; tout le reste, y compris `file://` et les chemins bruts → `feedparser.parse()` direct, inchangé), même patron de branchement que `json_connector._charger`/`scrape_connector._charger`, qui distinguent déjà `file://` du réseau — sauf que `rss_connector.py` n'a en pratique jamais besoin du cas `file://` en production (ses sources sont toujours `http(s)`), seulement pour les tests, qui utilisent des chemins bruts plutôt que des URI `file://`.

**Risque technique identifié à vérifier (pas seulement en théorie)** : `feedparser.parse(url)` fait aujourd'hui sa propre requête HTTP en interne et a donc accès à l'en-tête `Content-Type`/charset de la réponse comme indice d'encodage supplémentaire. En passant plutôt `reponse.content` (bytes déjà récupérés par `httpx`) à `feedparser.parse()`, ce indice d'en-tête HTTP est perdu — `feedparser` retombe sur la déclaration d'encodage du prologue XML et la détection de BOM, ce qui est généralement fiable mais pas rigoureusement identique. Le socle réel compte au moins une source dont l'avertissement `bozo` est précisément un désaccord d'encodage (`tldr-ai` : « document declared as us-ascii, but parsed as utf-8 ») — à revérifier en conditions réelles après le changement (Task 2, dernière sous-tâche), pas supposé sans risque.

### État actuel de `src/veille/collect.py` — ce qui existe déjà et ce qui manque

Lu en entier avant l'écriture de cette story (`collect.py:199-386`).

- **Déjà construit et éprouvé (AD-6)** : `_fetch_one` encapsule chaque `connector(source_config)` dans un `try/except Exception` générique, ne lève jamais, retourne `([], cause)` sur panne. `RapportSource.echec`/`est_muette`/`est_absorbee` distinguent déjà trois états. `_journaliser` journalise déjà chaque source muette/absorbée en détail (avec les causes précises pour « absorbée »). Ce mécanisme a été validé en conditions réelles à trois reprises (Story 1.2 : 1946 items, Story 2.1 : 2800 items sur 17 sources, zéro exception hors isolation).
- **Ce qui manque, et que cette story ajoute** : aucun mécanisme n'agrège le **taux d'échec global** de la nuit, ni ne le signale au-delà du détail par source déjà journalisé. Rien dans `ResultatCollecte`/`_journaliser` ne répond aujourd'hui à « est-ce qu'on est dans une nuit où la majorité du socle est en panne ? ». C'est le seul ajout réel de logique dans `collect.py` pour cette story.

### Portée volontairement limitée du signal d'anomalie (AC4)

« L'anomalie est signalée » est délibérément interprété ici comme **un journal de niveau `ERROR`** (visible en production), pas comme un bandeau visible sur la page publiée. Un bandeau visible sur `index.html` a déjà été explicitement écarté en revue de la Story 1.8 et tracé comme dette **Epic 3** (`rapport-projet.md` §8) : distinguer sur la page « nuit calme » de « collecte en panne » suppose un état persistant (`store.py`/SQLite, AD-5) qui n'existe pas encore, et l'architecture elle-même (AD-6) évoque une « journalisation dans l'état de santé » qui relève de `health.py` (Epic 4, pas encore construit). Cette story se limite donc au signal réellement disponible aujourd'hui : le journal. Documenté ici pour ne pas être re-questionné à chaque revue.

**Précision (trouvée en revue) : le journal `ERROR` par source existait déjà.** `_fetch_one` journalise chaque panne individuelle via `logger.exception` (déjà niveau `ERROR`, pas `WARNING`) depuis la Story 1.1 — ce que cette story ajoute n'est donc pas « le premier signal `ERROR` », mais une **ligne agrégée** distincte de ces traces individuelles, qui nomme les sources concernées et donne le taux global en un coup d'œil, plutôt que d'obliger à recompter des tracebacks épars dans un journal d'une nuit chargée.

**Précision (trouvée en revue) : une source « muette » (200 OK mais structure inexploitable) ne compte jamais dans `anomalie_pannes`, même si les 17 sources du socle le sont la même nuit.** C'est un choix délibéré, pas un oubli : l'AC4 (et FR-2 lui-même) parle explicitement de sources « qui répondent en erreur » — une source muette n'en est pas une, elle a répondu avec succès mais produit une structure vide ou changée (déjà journalisée séparément, en `WARNING`, par `_journaliser`). Un socle entièrement silencieux sans la moindre erreur HTTP reste un scénario distinct (le contenu des sources a peut-être changé de format), hors du périmètre de cette story et déjà partiellement couvert par la dette Epic 4 (santé des sources).

**Précision (trouvée en revue) : une source dont le `type` est mal orthographié n'est plus comptée dans le taux de panne.** `sources_en_panne_reseau` filtre `sources_en_echec` sur `r.type in CONNECTORS` — une faute de frappe dans `sources.yaml` (ex. `type: rrs`) est une erreur de configuration statique, jamais tentée par un connecteur, à ne pas confondre avec une vraie panne réseau/HTTP de la nuit (verrouillé par `test_un_type_de_source_mal_orthographie_ne_compte_pas_comme_panne_reseau`).

### Précédents à réutiliser, pas à réinventer

- **`json_connector._charger`/`scrape_connector._charger`** (déjà en place) — même **esprit** à reproduire pour `rss_connector.py` (délai d'attente explicite, `raise_for_status()`, dispatch réseau/local), pas la même condition de branchement littérale : les deux dispatchent sur `file://` → local, sinon → réseau, alors que `rss_connector._charger` dispatche sur `http(s)://` → réseau, sinon → local (`urlparse(...).scheme`, insensible à la casse — trouvé en revue : un `str.startswith` littéral aurait laissé passer un schéma `HTTP://` sur la branche locale, réintroduisant la panne que cette story ferme pour cette seule URL). L'inversion est nécessaire : les tests de `rss_connector.py` passent des chemins bruts sans schéma (jamais `file://`), que `feedparser.parse()` sait déjà lire nativement — une source réelle de ce projet n'a de toute façon jamais besoin du cas `file://` (voir Dev Notes ci-dessus, section sur ce qui change).
- **`_fetch_one` (`collect.py`)** — l'isolation de panne générique par source existe déjà et n'a besoin d'aucune modification pour que la nouvelle exception HTTP de `rss_connector.py` soit correctement capturée et journalisée avec sa cause.
- **`sources_en_echec`** (`ResultatCollecte`, déjà défini) — base directe pour calculer le taux d'échec de l'AC4 ; pas de nouveau champ de comptage à réinventer.
- **`_ecrire_socle`/pattern de `test_rapport_collecte.py`** (Story 1.1, éprouvé depuis) — socle YAML réel écrit dans `tmp_path`, sources cassées via des chemins `file://` inexistants pour déclencher un vrai échec sans mock de réseau. À reproduire pour le nouveau test de majorité de pannes.
- **User-Agent explicite** (`scrape_connector.USER_AGENT`) — même valeur/patron à reprendre pour la requête `httpx` de `rss_connector.py` (décision de cohérence #15 du journal des décisions).

### Hors périmètre — ne pas anticiper

- **Backoff sur les sources sensibles au débit** (429, rate-limiting) — explicitement une story séparée dans `epics.md` (**Story 2.3** : « Respecter les sources sensibles au débit »). Cette story se contente de journaliser une panne 429 comme n'importe quelle autre panne, sans retry ni délai.
- **Distinction fine 404 vs flux malformé** — dette déjà tracée vers **Epic 4** (santé des sources, FR-12/13), pas cette story : ici, toute panne HTTP devient simplement une `échec` avec sa cause textuelle (déjà suffisant pour l'AC3), pas une taxonomie de causes.
- **Bandeau visible sur la page publiée** — voir section dédiée ci-dessus, explicitement Epic 3.
- **`health.py`/`store.py`** — Epic 4/Epic 3, pas construits ici ; le signal de cette story reste un journal, pas un état persistant.
- **Timeout/User-Agent sur `json_connector.py`/`scrape_connector.py`** — déjà en place depuis la Story 1.2, rien à changer.

### Testing Standards

- `pytest`, via `uv run pytest`. Aucun mock de réseau réel (`respx`/`pytest-httpx`) disponible ni nécessaire : les pannes HTTP peuvent être simulées par des fixtures locales qui lèvent (ex. un serveur `http.server` local éphémère serait disproportionné ; suivre plutôt le patron déjà établi par `test_rapport_collecte.py`, qui déclenche un vrai `échec` via un chemin `file://` inexistant — même principe applicable à une source RSS pointant sur un chemin inexistant pour vérifier que l'exception `httpx`/réseau, une fois introduite, reste bien capturée par l'isolation existante). Si un test unitaire de `rss_connector.py` a besoin de vérifier précisément le comportement HTTP (403/500/timeout), `monkeypatch` sur `httpx.get` (ou sur la fonction interne de récupération du connecteur) reste préférable à un vrai serveur — cohérent avec `test_une_entree_cassee_ne_fait_pas_perdre_les_autres` (`test_rss_connector.py`), qui monkeypatche déjà une fonction interne du module pour simuler une panne ciblée.

### Previous Story Intelligence

- **Story 2.1** (précédente) : a étendu le socle à 17 sources et, en exécutant réellement la collecte contre ce socle (Task 4), a confirmé qu'aucune des 17 sources ne lève hors de l'isolation AD-6 — mais n'a texté aucun scénario de panne réseau/HTTP réelle (toutes les 17 sources ont répondu). Cette story comble ce point précis : la robustesse aux pannes n'a encore jamais été testée en conditions réelles de panne, seulement en conditions réelles de succès.
- **Dette explicitement fléchée vers cette story** (`deferred-work.md`, entrées de la Story 1.1) : « Aucun timeout réseau sur `feedparser.parse()` » et « Aucun User-Agent explicite envoyé par `feedparser` » — les deux fermées par cette story (Task 1).
- Convention de commit établie (Stories 1.4-2.1) : un commit implémentation+revue, un commit séparé pour `docs/rapport-projet.md`, tous deux poussés.
- `_bmad/`, `.claude/`, `_bmad-output/` sont suivis par git depuis la Story 1.7/1.8 — `git add -A` couvre tout.

### Git Intelligence Summary

Commits récents : Story 2.1 (implémentation + revue, `eef0e1b`), rapport de projet (commit séparé, `c448b0f`). Même convention à reproduire ici.

### Project Structure Notes

Aucun écart avec le Structural Seed : cette story ne touche que `src/veille/connectors/rss_connector.py` et `src/veille/collect.py`, tous deux déjà prévus pour porter respectivement la récupération réseau par type de connecteur (AD-2) et l'isolation de panne (AD-6).

### References

- [Source: epics.md#Story-2.2] — story d'origine et critères d'acceptation (Given/When/Then)
- [Source: prd.md#FR-2] — Tolérer les échecs de source (timeout/403/429, seuil d'anomalie à 50 %)
- [Source: ARCHITECTURE-SPINE.md#AD-6] — isolation des pannes de source
- [Source: deferred-work.md] — timeout réseau absent sur `feedparser` (Story 1.1), User-Agent absent (Story 1.1), bandeau d'échec nocturne différé à l'Epic 3 (Story 1.8)
- [Source: 2-1-etendre-le-socle.md] — précédent immédiat, socle à 17 sources jamais testé en conditions réelles de panne

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5 (`claude-sonnet-5`)

### Debug Log References

- `uv run pytest tests/test_rss_connector.py -q` avant implémentation : 4 échecs (`AttributeError: module 'veille.connectors.rss_connector' has no attribute 'httpx'`) — RED confirmé pour la bonne raison, avant tout code de production.
- Après Task 1 : `uv run pytest tests/test_rss_connector.py -q` → 10 passed (6 existants + 4 nouveaux).
- Après Task 2 : `uv run pytest tests/test_rapport_collecte.py -q` → 7 passed dès le premier essai (le correctif de Task 1 suffisait déjà à faire lever l'erreur HTTP jusqu'à `collect._fetch_one`, sans changement supplémentaire).
- Après Task 3 : `uv run pytest tests/test_rapport_collecte.py -q` → 9 passed (RED confirmé au préalable : `AttributeError: 'ResultatCollecte' object has no attribute 'anomalie_pannes'`).
- Vérification réseau réelle (Task 2, dernière sous-tâche) : `tldr-ai` (20 items), `lemonde-informatique` (20 items, même contenu), `openai-news` (1162 items) — tous identiques aux comptes de la Story 2.1, aucune perte d'entrée après le passage à `httpx`.
- Suite complète finale (avant revue) : `uv run pytest -q` → 331 passed.
- Après application des 7 correctifs de revue (2026-09-02) : `uv run pytest -q` → 335 passed.

### Completion Notes List

- **AC1/AC3** : confirmé par test d'intégration (`test_une_panne_http_rss_est_capturee_avec_sa_cause`) — une panne HTTP (403) sur une source RSS produit désormais un `RapportSource.echec` non vide (« 403 » présent dans la cause), plus jamais une source « MUETTE » indiscernable d'un flux simplement vide. Les autres sources du socle restent collectées, le digest est produit (AD-6 inchangé, déjà éprouvé — cette story ferme le seul trou restant, propre à `rss_connector.py`).
- **AC2** : `rss_connector.py` applique désormais `TIMEOUT_SECONDES = 30` (même valeur que `json_connector.py`/`scrape_connector.py`) via une récupération explicite par `httpx` pour toute URL réseau — une source RSS qui ne répond jamais lève `httpx.TimeoutException` au lieu de bloquer indéfiniment le run. Fermeture de la dette suivie depuis la Story 1.1 (`deferred-work.md`).
- **Bonus, même correctif** : un `User-Agent` explicite (`veille-ia/0.1 (personal news aggregator)`, identique à `scrape_connector.py`) est désormais envoyé sur les requêtes RSS — ferme au passage une seconde dette de la Story 1.1 (« aucun User-Agent explicite envoyé par feedparser »), à coût marginal nul puisque la requête `httpx` était de toute façon réécrite.
- **AC4** : `ResultatCollecte.taux_echec`/`anomalie_pannes` (nouvelles propriétés calculées, pas de champ stocké redondant) détectent une nuit où plus de la moitié des sources échouent **par panne réseau/HTTP réelle** (strictement > 50 %, égalité exacte non incluse — vérifié par test dédié ; correctif de revue : exclut désormais les sources dont le `type` est mal orthographié, voir Review Findings). `_journaliser` émet alors un journal `ERROR` agrégé nommant les sources concernées (« ANOMALIE : N/M sources en panne réseau/HTTP (X%) — id1, id2… »). Le digest continue d'être produit normalement (vérifié : `resultat.items` non vide avec 3/4 sources en échec dans le test).
- **Chemin local préservé à l'identique** : tous les tests existants de `test_rss_connector.py` (6, chemins de fichiers bruts, jamais `file://`) passent sans aucune modification — le dispatch se fait sur le schéma de l'URL (`http(s)://` → réseau via `httpx` ; tout le reste → `feedparser.parse()` direct, inchangé).
- **Risque technique identifié en Dev Notes, vérifié réellement, sans régression** : passer par `httpx` (bytes) plutôt que par la récupération interne de `feedparser` change la détection d'encodage pour `tldr-ai` — l'avertissement `bozo` d'encodage (« document declared as us-ascii, but parsed as utf-8 ») **disparaît** avec le nouveau chemin (`feedparser` retombe correctement sur son propre algorithme de détection plutôt que sur l'en-tête `Content-Type` erroné du serveur). Effet positif, pas une régression : 20 entrées obtenues dans les deux cas (avant/après), aucune perte. Documenté ici plutôt que découvert en revue.
- **Portée du signal d'anomalie (AC4) délibérément limitée au journal** — pas de bandeau sur la page publiée : décision actée en Dev Notes avant le code (nécessiterait un état persistant, `store.py`/SQLite, Epic 3 ; déjà tracé comme tel depuis la revue de la Story 1.8). Pas re-questionné pendant l'implémentation.
- **Hors périmètre confirmé non touché** : aucun backoff/retry ajouté (Story 2.3), aucune distinction fine des causes d'échec au-delà de la chaîne `str(exception)` déjà existante (Epic 4), aucun fichier sous `src/veille/` autre que `collect.py`/`rss_connector.py` modifié.
- Convention de commit reproduite (Stories 1.4-2.1) : commit implémentation+revue, puis commit séparé pour `docs/rapport-projet.md`, tous deux poussés sur `origin/main`.

### File List

- `src/veille/connectors/rss_connector.py` — modifié : `TIMEOUT_SECONDES`/`USER_AGENT` ajoutés, nouvelle fonction `_charger()` (dispatch réseau/local sur `urlparse(...).scheme`), `fetch()` appelle désormais `feedparser.parse(_charger(source_config.url))` au lieu de `feedparser.parse(source_config.url)`.
- `src/veille/collect.py` — modifié : `ResultatCollecte.sources_en_panne_reseau`/`taux_echec`/`anomalie_pannes` (nouvelles propriétés), `_journaliser` émet un journal `ERROR` agrégé nommant les sources en panne réseau/HTTP.
- `tests/test_rss_connector.py` — modifié : 6 nouveaux tests (timeout/statut HTTP explicites, dispatch réseau vs local, insensibilité à la casse du schéma, encodage sous en-tête `Content-Type` menteur).
- `tests/test_rapport_collecte.py` — modifié : 5 nouveaux tests (panne HTTP RSS capturée avec sa cause, anomalie à >50 % de pannes, absence d'anomalie à 50 % exactement, type de source invalide exclu du taux de panne, deux sources RSS dans le même run — une en panne, une vivante).
- `_bmad-output/implementation-artifacts/deferred-work.md` — modifié : nouvelle entrée (redirections HTTP non plafonnées, les 3 connecteurs).
- `_bmad-output/implementation-artifacts/2-2-continuer-en-panne.md` — ce fichier (story).

### Change Log

| Date | Changement |
|---|---|
| 2026-09-01 | Story créée (Task 1-4 planifiées). |
| 2026-09-01 | Task 1 : `rss_connector.py` gagne un timeout réseau explicite + `raise_for_status()` via `httpx`, chemin local préservé à l'identique. User-Agent explicite ajouté par cohérence. |
| 2026-09-01 | Task 2 : isolation de panne AD-6 confirmée réellement pour `rss_connector.py` (unitaire + intégration) ; vérification réseau réelle sans régression (encodage `tldr-ai` amélioré, pas dégradé). |
| 2026-09-01 | Task 3 : détection et journalisation d'une nuit à >50 % de sources en échec (`ResultatCollecte.anomalie_pannes`/`taux_echec`), digest toujours produit. |
| 2026-09-01 | Task 4 : suite complète rejouée (331 passed), aucune régression, aucune modification de test existant. Statut → review. |
| 2026-09-02 | Revue (3 couches, Sonnet) : 7 correctifs appliqués (schéma insensible à la casse, type de source invalide exclu du taux de panne, sources nommées dans le journal ANOMALIE, précisions AC2/AC4, test RSS-vs-RSS ajouté, test d'encodage sous en-tête menteur ajouté), 1 report (redirections non plafonnées, pré-existant aux 3 connecteurs), 6 rejetés comme bruit. 335 passed. Statut → done. |
