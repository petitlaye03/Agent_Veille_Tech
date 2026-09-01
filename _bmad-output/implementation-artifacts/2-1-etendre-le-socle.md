---
baseline_commit: 20849dc
---

# Story 2.1: Étendre le socle aux 15-20 sources visées

Status: done

## Story

As a Abdoulaye,
I want que mon socle couvre les 15-20 sources vérifiées de l'addendum,
so that mon digest reflète vraiment l'étendue de l'écosystème IA/data.

## Acceptance Criteria

1. **[FR-1]** Étant donné la liste des sources vérifiées de l'addendum du brief et la proposition de socle du PRD (§6.1), `config/sources.yaml` passe de 4 à **17 sources**, dans la fourchette visée (15-20) — **sans modification de code** : uniquement des entrées de configuration sur les types déjà implémentés (`rss`, `json`, `scrape`).
2. **[FR-1]** Chaque source ajoutée produit des `Item` respectant le format canonique (`source_id`, `guid`, `titre`, `date_publication` UTC, `langue`, `registre`, `url`, `contenu_brut`) — vérifié par une collecte réelle contre le réseau, pas seulement par la configuration déclarée.
3. **[Dette fermée]** Le registre `pour_le_metier`, structurellement vide depuis la Story 1.5 (trouvée en revue, reconduite dans `deferred-work.md` à chaque story depuis), reçoit ses deux premières sources.
4. **[Sûreté]** Chaque URL candidate est vérifiée par une requête HTTP réelle avant d'entrer dans `sources.yaml`, pas reprise telle quelle de la documentation — même discipline que l'addendum lui-même revendique (« aucune URL n'est reprise sans test ») et que la Story 1.1 a établie pour ce projet.
5. Les garde-fous existants sur le socle réel (`tests/test_socle_reel.py`) continuent de passer sans modification pour les invariants déjà couverts (types, registres valides, priorité déclarée, seuil de signal cohérent avec son mapping) ; un nouveau garde-fou verrouille la fermeture de la dette de l'AC3 (au moins une source en `pour_le_metier`).

## Tasks / Subtasks

- [x] Task 1 : Vérifier chaque URL candidate par une requête réelle (AC: 4)
  - [x] Les 13 URL candidates confirmées HTTP 200 par requête réelle (deux passes, à la création de la story et juste avant l'implémentation)
  - [x] `feedparser.parse()` réel confirme des entrées exploitables pour tous les flux RSS/Atom (YouTube, Le Monde Informatique en RDF `bozo=1` toléré, dépôts GitHub, blogs, podcast)
  - [x] Structure réelle de la réponse Hacker News/Algolia confirmée (`hits[].objectID/title/created_at/url/points`)
  - [x] Une URL morte trouvée et corrigée : `lemonde-informatique.fr/thematique/intelligence-artificielle/rss.xml` (addendum) → 404 réel, remplacée par `lemonde-informatique.fr/rss/rss.xml` (flux général, RDF, HTTP 200 confirmé) — voir Dev Notes

- [x] Task 2 : Étendre `config/sources.yaml` (AC: 1, 2, 3)
  - [x] Ajouter les 13 nouvelles sources (voir Dev Notes pour la liste exacte : id, type, url, langue, registre, priorité, mapping le cas échéant) réparties : **Apprendre** (+8), **Ce qui bouge** (+3), **Pour le métier** (+2)
  - [x] Chaque entrée déclare une `priorite` explicite (échelle déjà en vigueur : 10 primaire / 5 curation / 0 agrégateur — cf. commentaire d'en-tête du fichier) — écart trouvé et corrigé pour `hacker-news` : voir note ci-dessous
  - [x] La source Hacker News (JSON) déclare `seuil_signal` (le filtrage par seuil, déjà existant depuis la Story 1.4, fait le travail — pas de logique nouvelle)
  - [x] Aucune modification de `src/veille/` — l'AC1 l'exige explicitement (confirmé : seul `config/sources.yaml` a été touché)

- [x] Task 3 : Garde-fous et validation (AC: 3, 5)
  - [x] Nouveau test dans `tests/test_socle_reel.py` : au moins une source du socle réel déclare `registre: pour_le_metier` — verrouille la fermeture de la dette (AC3), même esprit que `test_le_socle_declare_au_moins_un_seuil_de_signal` (Story 1.4)
  - [x] Suite existante de `test_socle_reel.py` rejouée sans modification — tous les garde-fous déjà en place (types, registres, priorité, cohérence seuil/mapping) restent verts sur le socle élargi (14 tests, dont le nouveau : 15)
  - [x] Aucune régression sur le reste de la suite (324 tests passent, 323 + 1 nouveau)

- [x] Task 4 : Exécution réelle contre le socle complet (AC: 2)
  - [x] `collecter()` exécuté en script ponctuel contre le vrai `config/sources.yaml`, réseau réel — 2800 items collectés au total sur 17 sources (cf. Completion Notes pour le détail)
  - [x] Consigné dans les Completion Notes : nombre total d'items collectés, répartition par source, toute source muette ou en échec et sa cause
  - [x] Aucune exception n'est remontée hors de l'isolation de panne par source (AD-6) — les 17 sources rapportent un état (`OK` ou `ABSORBÉE`), aucune en `ÉCHEC`

### Review Findings

> Revue de code du 2026-09-01 (skill `bmad-code-review`, 3 couches adversariales, sur
> Sonnet 5 — même modèle que l'implémentation, convention établie sur ce projet).
> Base de diff `20849dc` (= `baseline_commit`, changements non commités). Les trois
> couches ont convergé indépendamment sur le même défaut le plus sérieux (`rss_connector`
> ne retombe jamais sur `updated_parsed`) — déjà trouvé et documenté par cette story
> elle-même en Task 4, confirmé réel et non nouveau. Le Blind Hunter et l'Acceptance
> Auditor ont aussi convergé indépendamment sur un second constat, celui-ci nouveau :
> l'URL Le Monde Informatique vérifiée en Task 1 répond en réalité par une redirection
> 301, pas un 200 littéral.

**Correctifs appliqués (4) :**

- [x] [Review][Patch] L'URL `lemonde-informatique` retenue (`.../rss/rss.xml`) répond en réalité **HTTP 301** vers `.../flux-rss/rss.xml` (200) — l'affirmation « HTTP 200 confirmé » de l'AC4 était imprécise pour cette URL précise (`curl` sans `-L` la révèle, la vérification de Task 1 avait suivi la redirection sans le signaler). Sans conséquence fonctionnelle (`httpx`/`feedparser` suivent les redirections), mais corrigé pour pointer directement sur la destination canonique plutôt que de dépendre d'une redirection maintenue par l'éditeur. Constat convergent (Blind Hunter + Acceptance Auditor) [config/sources.yaml, entrée `lemonde-informatique`]
- [x] [Review][Patch] Le commentaire d'en-tête partagé de `sources.yaml` ne documentait ni le piège « `priorite: 0` est en pratique inutilisable » (le garde-fou existant ne distingue pas priorité absente et priorité explicitement nulle) ni le piège « `racine` requise si la réponse JSON n'est pas une liste à la racine » — les deux n'étaient visibles que dans le commentaire inline de `hacker-news`, obligeant une future source à les redécouvrir par essai-erreur. Corrigé : les deux sont maintenant documentés dans l'en-tête partagé. Constat convergent (Blind Hunter + Acceptance Auditor) [config/sources.yaml, commentaire d'en-tête]
- [x] [Review][Patch] `deferred-work.md` formulait le défaut `published_parsed`/`updated_parsed` comme s'il s'agissait d'une anomalie mesurée « cette nuit-là » plutôt que d'un défaut structurel permanent (ces 5 sources n'ont jamais de `published_parsed`, donc chaque nuit sera mal-datée tant que le correctif n'est pas fait) — portée sous-estimée par la formulation, pas par les chiffres. Corrigé : précision ajoutée. Constat (Blind Hunter) [deferred-work.md]
- [x] [Review][Patch] Aucune note ne signalait que le rendement réel de `pour_le_metier` (2 items, tous via `decideo`) et de Hacker News (0 item retenu) reposait sur un seul relevé, ni le risque de désalignement lexical entre `profil.md` et la presse IT généraliste FR — observations réelles mais non actionnables dans cette story (peupler le socle, pas retoucher le profil/les seuils). Corrigé : deux notes de dette ajoutées pour surveillance en Epic 3. Constat (Blind Hunter) [deferred-work.md]

**Reporté (1) :**

- [x] [Review][Defer] `rss_connector._to_utc_datetime` ne retombe jamais sur `entry.get("updated_parsed")` quand `published_parsed` est absent — mal-date silencieusement 50/2800 items (4 dépôts GitHub + `lemonde-informatique`), en permanence, chaque nuit. Défaut réel dans du code préexistant, non introduit par cette story, mais rendu atteignable par les nouvelles sources — hors périmètre explicite de l'AC1 (« sans modification de code »). Déjà documenté en détail (Dev Notes, Completion Notes, `deferred-work.md`) avant même la revue ; confirmé indépendamment par les 3 couches (Blind Hunter, Edge Case Hunter, Acceptance Auditor) — deferred, pre-existing [src/veille/connectors/rss_connector.py:107-116]

**Rejeté comme bruit (2) :**

- « Les 4 dépôts GitHub héritent de `priorite: 10`, la même que les annonces officielles OpenAI/Anthropic, sans filtrage du bruit des patch releases » — déjà traité explicitement comme hors périmètre dans les Dev Notes de cette story (« Extraction Breaking changes / filtrage patch releases — pas exigé par l'AC ») ; choix délibéré, pas un oubli.
- « `datagen-podcast` (312 entrées) et `eugene-yan` (212 entrées) renvoient l'intégralité de leur archive à chaque run, coût de calcul non mesuré » — déjà documenté comme dette connue (section Dev Notes « Deux sources renvoient un flux plus large... », rattachée à l'Epic 3) depuis la création de cette story ; aucun élément nouveau apporté par la revue.

## Dev Notes

### Sources candidates — vérifiées par requête réelle avant l'écriture de cette story

Chaque URL ci-dessous a été confirmée par une vraie requête HTTP (code 200) et, pour les flux, une passe `feedparser.parse()` réelle confirmant des entrées exploitables, **pendant la création de cette story** — pas reprise telle quelle de l'addendum. Une URL s'est révélée morte (voir correction ci-dessous) : la vérification n'était donc pas superflue.

**Apprendre (+8)** — cohérent avec la proposition du PRD §6.1 (« GitHub releases.atom, 1-2 blogs de praticiens, 1 podcast d'ingénierie, 1 chaîne vidéo ») :

| id | type | url | langue | priorité |
|---|---|---|---|---|
| `github-llamacpp` | rss | `https://github.com/ggml-org/llama.cpp/releases.atom` | en | 10 |
| `github-vllm` | rss | `https://github.com/vllm-project/vllm/releases.atom` | en | 10 |
| `github-transformers` | rss | `https://github.com/huggingface/transformers/releases.atom` | en | 10 |
| `github-ollama` | rss | `https://github.com/ollama/ollama/releases.atom` | en | 10 |
| `eugene-yan` | rss | `https://eugeneyan.com/rss/` | en | 10 |
| `simon-willison` | rss | `https://simonwillison.net/atom/entries/` | en | 10 |
| `statquest-youtube` | rss | `https://www.youtube.com/feeds/videos.xml?channel_id=UCtYLUTtgS3k1Fg4y5tAhLbw` | en | 10 |
| `datagen-podcast` | rss | `https://feeds.acast.com/public/shows/5fa58959e64011214fbf140d` | fr | 10 |

**Ce qui bouge (+3)** :

| id | type | url | langue | priorité |
|---|---|---|---|---|
| `brief-ia` | rss | `https://www.briefia.fr/rss.xml` | fr | 5 |
| `hacker-news` | json | `https://hn.algolia.com/api/v1/search_by_date?tags=story&numericFilters=points%3E100` | en | 0 (`seuil_signal: 250`, `mapping: {guid: objectID, titre: title, date_publication: created_at, url: url, signal: points}`) |
| `tldr-ai` | rss | `https://tldr.tech/api/rss/ai` | en | 5 |

**Pour le métier (+2, ferme la dette de l'AC3)** :

| id | type | url | langue | priorité |
|---|---|---|---|---|
| `decideo` | rss | `https://www.decideo.fr/xml/syndication.rss` | fr | 10 |
| `lemonde-informatique` | rss | `https://www.lemondeinformatique.fr/rss/rss.xml` | fr | 10 |

### Documentation étendue en revue : les deux pièges de cette story n'étaient visibles que localement

Trouvé indépendamment par le Blind Hunter et l'Acceptance Auditor : ni le piège « `priorite: 0` inutilisable » ni le piège « `racine` requise pour une API JSON dont la racine n'est pas une liste » n'étaient documentés ailleurs que dans le commentaire inline de l'entrée concernée (`hacker-news`) — le commentaire d'en-tête partagé de `sources.yaml` (échelle de priorité, types/registres) ne les mentionnait pas, obligeant quiconque ajouterait une future source à re-découvrir ces deux contraintes par essai-erreur. Corrigé : le commentaire d'en-tête de `config/sources.yaml` documente maintenant explicitement les deux, avec renvoi vers `hacker-news` comme exemple.

### Écart trouvé en implémentant Task 2 : `hacker-news` ne peut pas prendre `priorite: 0`

Le plan initial (Dev Notes ci-dessus, table « Ce qui bouge ») prévoyait `priorite: 0` pour Hacker News, cohérent avec l'échelle documentée en en-tête du fichier (« 0 = agrégateur, défaut »). En écrivant l'entrée, `uv run pytest tests/test_socle_reel.py` a fait échouer `test_chaque_source_declare_une_priorite` : ce garde-fou existant (antérieur à cette story) interdit toute priorité à `0`, y compris déclarée explicitement, car `SourceConfig.priorite: int = 0` (`config.py`) rend une priorité absente et une priorité explicitement nulle indiscernables une fois le YAML chargé — le test ne peut donc que les traiter identiquement. Conformément à l'AC5 (« garde-fous existants... sans modification »), le garde-fou n'a pas été touché ; `hacker-news` a reçu `priorite: 1` à la place — la valeur explicite la plus basse restant sous le palier « curation » (5), préservant l'intention (Hacker News cède le pas à toute source primaire ou de curation en cas de doublon) sans littéralement utiliser `0`. Documenté ici et en commentaire YAML ; l'échelle 10/5/0 de l'en-tête reste correcte comme intention de conception, mais `0` n'est en pratique jamais assignable à une vraie source tant que ce garde-fou existe sous sa forme actuelle — à signaler si une future story retouche `test_socle_reel.py`.

### Pourquoi Hacker News a deux seuils (100 dans l'URL, 250 dans `seuil_signal`)

`numericFilters=points>100` dans l'URL est un pré-filtre côté serveur Algolia — large, juste pour limiter la charge utile renvoyée. Le vrai seuil éditorial (`points > 250`, réglage mesuré par l'addendum pour arriver à ~5 items/jour) vit dans `seuil_signal: 250`, le mécanisme déjà construit par `filter.py` depuis la Story 1.4 (`filtrer_par_signal`) — exactement le même patron que `hf-daily-papers` (pré-filtre large côté API, seuil éditorial réel côté config du projet). Aucune raison de dupliquer cette logique dans l'URL Algolia elle-même : le seuil éditorial doit rester réglable sans toucher à la configuration réseau, et inversement.

### Correction trouvée par vérification réelle : l'URL Le Monde Informatique de l'addendum est morte

L'addendum propose `https://www.lemondeinformatique.fr/thematique/intelligence-artificielle/rss.xml` — vérifiée en créant cette story : **HTTP 404** (« La page demandée n'existe pas »), probablement une réorganisation du site depuis la rédaction de l'addendum (juillet 2026). Le flux général (`https://www.lemondeinformatique.fr/rss/rss.xml`) répond avec du contenu réel et pertinent (vérifié : un article sur Anthropic était en tête au moment du test). C'est un flux RSS 1.0/RDF plutôt que RSS 2.0/Atom — `feedparser` le tolère (`bozo=1` mais entrées exploitables), même tolérance déjà établie pour tout flux imparfait depuis `rss_connector.py` (Story 1.1). Ce flux n'est pas filtré à l'IA à la source — le filtrage par profil (Story 1.4, déjà en place) fait ce travail, comme pour toute autre source de ce socle.

**Correction supplémentaire trouvée en revue de code (Blind Hunter + Acceptance Auditor, indépendamment)** : l'URL initialement retenue, `.../rss/rss.xml`, répond en réalité **HTTP 301** vers `.../flux-rss/rss.xml` (200) — la vérification de Task 1 avait suivi la redirection sans le remarquer explicitement (`curl` par défaut la suit), rendant l'affirmation « HTTP 200 confirmé » de l'AC4 imprécise pour cette URL précise. Sans conséquence fonctionnelle (`httpx`/`feedparser` suivent les redirections), mais `sources.yaml` a été corrigé pour pointer directement sur la destination canonique (`.../flux-rss/rss.xml`, contenu identique, vérifié) plutôt que de dépendre d'une redirection maintenue par l'éditeur.

### Pourquoi les dépôts GitHub sont 4 entrées de configuration, pas « 1 source à panier »

Le PRD (§6.1) propose « GitHub releases.atom (panier de ~10 dépôts compté comme 1 Source) ». Techniquement, chaque dépôt a son propre flux Atom (`github.com/{owner}/{repo}/releases.atom`) — regrouper plusieurs flux sous un seul `source_id` logique demanderait une nouvelle capacité (un connecteur qui agrège plusieurs URL), ce que l'AC1 interdit explicitement (« sans modification de code »). Cette story ajoute donc 4 dépôts comme 4 entrées `sources.yaml` distinctes (`ggml-org/llama.cpp`, `vllm-project/vllm`, `huggingface/transformers`, `ollama/ollama` — un sous-ensemble des ~10 cités par l'addendum, pas la totalité, pour garder le total du socle dans la fourchette visée) : zéro changement de code, cohérent avec AD-2 (« ajouter une source ne modifie que la configuration »). La divergence avec la formulation littérale du PRD est délibérée et documentée ici, pas une omission.

### Deux sources renvoient un flux plus large que « les items récents »

Trouvé en vérifiant réellement le contenu, pas seulement le code retour :

- **`datagen-podcast`** renvoie l'intégralité de l'archive du podcast (312 épisodes) à chaque requête, pas seulement les récents — contrairement aux flux déjà en place (`openai-news`, `huggingface-blog`…) qui exposent une fenêtre bornée. Sans conséquence sur la justesse du digest (`filter.py` classe et retient les mieux notés, `quotas.yaml` plafonne malgré tout la sortie), mais amplifie une limitation déjà connue et déjà tracée : sans état « déjà vu » persistant (`store.py`/SQLite, AD-5, toujours Epic 3), les mêmes anciens épisodes peuvent ressortir bien classés plusieurs nuits de suite. Pas corrigé ici — même dette, un peu plus visible.
- **`eugene-yan`** expose 212 entrées (tout l'historique du blog) pour la même raison structurelle.

Aucune des deux ne casse rien aujourd'hui (isolation de panne AD-6 intacte, scoring/quotas fonctionnent normalement sur un lot plus gros) — juste un peu plus de calcul par run, négligeable à cette échelle. Documenté dans `deferred-work.md`, à surveiller si le volume nocturne devient un problème réel.

### Pourquoi Kaggle (signal marché, §6.1 « Pour le métier ») n'est pas dans cette story

`https://www.kaggle.com/api/v1/competitions/list` exige une authentification (clé API gratuite, mais authentification tout de même) — `json_connector.py` ne sait aujourd'hui envoyer aucun en-tête d'authentification, seulement une requête `GET` anonyme. L'ajouter exigerait donc une vraie modification de code (support d'en-têtes/auth dans le connecteur), hors du périmètre « sans modification de code » de cette story — et c'est déjà une dette explicitement tracée depuis la Story 1.2 (`deferred-work.md` : « en-têtes/authentification pour les API JSON — bloque Kaggle, prévu au socle v1 »). `pour_le_metier` se ferme ici avec deux sources FR sans authentification (Décideo, Le Monde Informatique) ; Kaggle reste pour une story dédiée qui touchera réellement `json_connector.py`.

### Pourquoi OpenRouter (signal marché, addendum §1.7) n'est pas non plus dans cette story

`https://openrouter.ai/api/v1/models` ne nécessite aucune authentification, mais sa valeur documentée dans l'addendum (« diff quotidien des `id` → nouveaux modèles ») suppose de **comparer** l'instantané du jour à celui de la veille — un besoin d'état persistant que ce projet n'a pas encore (`store.py`/SQLite, Epic 3). Collecter les 343 modèles bruts chaque nuit sans diff produirait 343 « items » identiques chaque jour, tous perçus comme nouveaux par le pipeline — l'inverse de « signal, pas bruit » qui gouverne tout ce projet. Reporté à quand une comparaison jour-sur-jour sera possible.

### Précédents à réutiliser, pas à réinventer

- **`filtrer_par_signal`/`seuil_signal`** (Story 1.4) — déjà le bon outil pour « Hacker News, seuil de points » ; pas de logique de seuil à écrire dans le connecteur, juste `seuil_signal` en config, comme `hf-daily-papers` le fait déjà.
- **`mapping.url`** (`json_connector.py`, déjà supporté en repli quand `url_modele` n'est pas déclaré — vérifié dans le code avant d'écrire cette story) — utilisé pour Hacker News, dont chaque item porte sa propre URL cible, contrairement à `hf-daily-papers` qui construit son URL via un gabarit sur le `guid`.
- **Tolérance aux flux `bozo`** (`rss_connector.py`, Story 1.1) — le flux RDF de Le Monde Informatique en profite sans changement.
- **Isolation de panne par source** (AD-6, Story 1.1/1.2) — aucune des 13 nouvelles sources n'a besoin d'un traitement spécial : une source qui viendrait à échouer pendant l'exécution réelle (Task 4) doit être absorbée comme n'importe quelle autre, pas corrigée en dur ici.

### Hors périmètre — ne pas anticiper

- **Kaggle et OpenRouter** — voir ci-dessus, chacun bloqué par un besoin réel non encore construit (auth pour l'un, état persistant pour l'autre).
- **Extraction de la section « Breaking changes »** des releases GitHub, ou filtrage des patch releases (`x.y.z`) — raffinement mentionné par l'addendum, pas exigé par l'AC de cette story (qui demande seulement le format canonique `Item`, pas un filtrage éditorial du contenu des releases).
- **Robots.txt** — aucune des 13 nouvelles sources n'est de type `scrape` ; AD-10 ne s'applique donc à aucune d'entre elles ici.
- **Story 2.2/2.3/2.4** (isolation de panne renforcée, backoff, dédoublonnage à l'échelle) — cette story se limite à peupler le socle ; le comportement en cas de panne réelle sur ces nouvelles sources est déjà couvert par l'AD-6 existant, pas à renforcer ici.
- **`rss_connector._to_utc_datetime` ignore `updated_parsed`** — bug latent trouvé en Task 4 (voir Completion Notes et `deferred-work.md`), affectant 5 des 17 sources (4 dépôts GitHub + Le Monde Informatique). Une vraie correction de `src/veille/connectors/rss_connector.py`, explicitement hors du périmètre « sans modification de code » de l'AC1 — reportée à une story dédiée.

### Testing Standards

- `pytest`, via `uv run pytest`. Les 13 nouvelles sources ne demandent aucun nouveau test unitaire de connecteur (aucun connecteur modifié) — seulement l'extension des garde-fous de `test_socle_reel.py` (Task 3) et la validation réelle (Task 4, réseau réel assumé et documenté, à la différence du reste de la suite qui n'en fait jamais).
- Même discipline que les Stories 1.1/1.2 : une exécution réelle contre le vrai socle est **documentée avec ses chiffres exacts**, jamais approximée.

### Previous Story Intelligence

- Dette explicitement fléchée vers cette story depuis plusieurs revues : `pour_le_metier` structurellement vide (Story 1.5), `json_connector.py` sans en-têtes/auth (Story 1.2, bloque Kaggle).
- `_avertir_seuils_inertes`/`_avertir_cles_inconnues` et les garde-fous de `test_socle_reel.py` existent déjà et couvriront automatiquement les nouvelles entrées sans modification — vérifié en lisant `filter.py`/`config.py` avant d'écrire cette story.
- Convention de commit établie (Stories 1.4-1.9) : un commit implémentation+revue, un commit séparé pour `docs/rapport-projet.md`, tous deux poussés.
- `_bmad/`, `.claude/`, `_bmad-output/` sont suivis par git depuis la Story 1.7/1.8 — `git add -A` couvre tout.

### Git Intelligence Summary

Commits récents : Story 1.9 (implémentation + revue), rapport de projet (commit séparé). Même convention à reproduire ici.

### Project Structure Notes

Aucun écart avec le Structural Seed : cette story ne touche que `config/sources.yaml`, un fichier de configuration explicitement prévu pour grandir sans toucher au code (AD-3).

### References

- [Source: epics.md#Story-2.1] — story d'origine et critères d'acceptation
- [Source: prd.md#6.1] — proposition de socle 15-20 sources par registre
- [Source: brief-agent-veille-emploi-ia-2026-07-20/addendum.md] — cartographie complète des sources vérifiées (280 sources testées), pièges connus, sources mortes
- [Source: deferred-work.md] — `pour_le_metier` vide (Story 1.5), auth manquante dans `json_connector.py` (Story 1.2)
- [Source: 1-1-collecte-premiere-source.md], [Source: 1-2-sources-types-varies.md] — précédent de validation réelle contre le réseau, tolérance `bozo`

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5 (`claude-sonnet-5`)

### Debug Log References

- Vérification réelle des 13 URL candidates (`curl`, deux passes) et de leur structure (`feedparser.parse()` pour les flux, structure JSON pour Hacker News) — voir Dev Notes, Task 1.
- `uv run pytest tests/test_socle_reel.py -q` après extension de `sources.yaml` : 1 échec initial (`test_chaque_source_declare_une_priorite` sur `hacker-news priorite: 0`) → corrigé (`priorite: 1`) → 15 passed.
- `uv run pytest -q` (suite complète) : 324 passed après ajout du garde-fou `pour_le_metier` (Task 3).
- Exécution réelle de `collecter()` (script ponctuel, réseau réel) contre le socle à 17 sources : 1er passage révèle `hacker-news` MUETTE (« La racine '' ... ne désigne pas une liste ») → corrigé (`racine: hits` ajouté) → 2e passage propre, voir Completion Notes pour le détail complet.

### Completion Notes List

- **AC1** : `config/sources.yaml` passe de 4 à 17 sources (13 ajoutées), toutes de types déjà implémentés (`rss`, `json`) — `scrape` reste à 1 (Anthropic, inchangée). Aucune modification de `src/veille/` (seul fichier touché hors story/tests : `config/sources.yaml`).
- **AC2** : confirmé par exécution réelle (Task 4, ci-dessous) — les 17 sources produisent des `Item` canoniques, aucune exception ne remonte hors de l'isolation par source (AD-6).
- **AC3** : `pour_le_metier` reçoit 2 sources (`decideo`, `lemonde-informatique`) et, à l'exécution réelle, **2 items du registre atteignent effectivement le classement final** (via `decideo`) — la dette n'est pas seulement déclarative, elle est fonctionnellement fermée. Verrouillé par le nouveau test `test_le_socle_couvre_le_registre_pour_le_metier`.
- **AC4** : 13/13 URL candidates vérifiées par requête réelle avant écriture dans `sources.yaml` ; une (Le Monde Informatique, addendum) s'est révélée morte (404 réel) et a été remplacée avant même d'entrer dans le fichier — voir Dev Notes.
- **AC5** : les 14 tests existants de `test_socle_reel.py` passent sans modification contre le socle élargi ; 1 nouveau test ajouté (15 au total). Suite complète : 324 tests passent (323 + 1), zéro régression.
- **Écart trouvé et corrigé pendant l'implémentation (Task 2)** : `hacker-news` ne pouvait pas prendre `priorite: 0` comme prévu au plan initial — le garde-fou existant `test_chaque_source_declare_une_priorite` l'interdit (il ne distingue pas priorité absente et priorité explicitement nulle). Corrigé par `priorite: 1`, sans toucher au test. Voir Dev Notes pour le détail.
- **Écart trouvé et corrigé pendant l'implémentation (Task 4)** : `hacker-news` était MUETTE au premier passage d'exécution réelle — la réponse Algolia est un objet `{"hits": [...]}`, pas une liste à la racine, et l'entrée ne déclarait pas `racine: hits`. Corrigé en config (`racine: hits` ajouté), aucune modification de code. Reste dans le périmètre « sans modification de code » de l'AC1.
- **Résultat de l'exécution réelle contre le socle complet (Task 4, 17 sources)** :
  - Total collecté (avant dédoublonnage/seuil/scoring/quotas) : **2800 items**.
  - Total final retenu au digest (après dédoublonnage, seuil de signal, scoring par profil, quotas par registre) : **8 items**.
  - Détail par source (items collectés → retenus) :
    | source | type | collectés | retenus | état |
    |---|---|---|---|---|
    | openai-news | rss | 1162 | 2 | OK |
    | huggingface-blog | rss | 853 | 0 | ABSORBÉE (bruit + quota) |
    | eugene-yan | rss | 212 | 0 | ABSORBÉE (bruit + quota) |
    | hf-daily-papers | json | 50 | 0 | ABSORBÉE (seuil + bruit + quota) |
    | brief-ia | rss | 50 | 1 | OK |
    | anthropic-news | scrape | 11 | 0 | ABSORBÉE (bruit + quota) |
    | github-llamacpp | rss | 10 | 0 | ABSORBÉE (bruit + quota) ; 10/10 dates approximatives |
    | github-vllm | rss | 10 | 0 | ABSORBÉE (quota) ; 10/10 dates approximatives |
    | github-transformers | rss | 10 | 0 | ABSORBÉE (bruit + quota) ; 10/10 dates approximatives |
    | github-ollama | rss | 10 | 0 | ABSORBÉE (quota) ; 10/10 dates approximatives |
    | simon-willison | rss | 15 | 0 | ABSORBÉE (bruit + quota) |
    | statquest-youtube | rss | 15 | 0 | ABSORBÉE (bruit + quota) |
    | datagen-podcast | rss | 312 | 3 | OK |
    | hacker-news | json | 20 | 0 | ABSORBÉE (seuil + quota) |
    | tldr-ai | rss | 20 | 0 | ABSORBÉE (bruit + quota) |
    | decideo | rss | 20 | 2 | OK |
    | lemonde-informatique | rss | 20 | 0 | ABSORBÉE (bruit + quota) ; 20/20 dates approximatives |
  - **Aucune source en ÉCHEC** — toutes les 17 rapportent soit un état `OK`, soit `ABSORBÉE` (collectée mais rien retenu après scoring/quotas), jamais un échec réseau ou de parsing qui remonterait hors de l'isolation par source. AD-6 tient sur l'ensemble du socle élargi.
  - **Deux avertissements `bozo` bénins, sans perte d'entrées** : `tldr-ai` (encodage déclaré us-ascii, parsé utf-8) et `lemonde-informatique` (RDF légèrement malformé, `not well-formed` sur une ligne) — les deux flux restent intégralement exploitables (20 entrées chacun), tolérance déjà établie par `rss_connector.py` depuis la Story 1.1.
  - **Défaut trouvé, non corrigé ici (hors périmètre AC1)** : 50 items (4×10 GitHub + 20 Le Monde Informatique) reçoivent une date approximative (`datetime.now()`) au lieu de leur vraie date de publication — `rss_connector._to_utc_datetime` ne regarde que `published_parsed`, absent sur les flux Atom purs et RDF qui n'exposent que `updated_parsed`. Documenté en détail dans `deferred-work.md` (nouvelle entrée, 2026-09-01) et dans les Dev Notes ci-dessus.
- Convention de commit reproduite (Stories 1.4-1.9) : commit implémentation+revue, puis commit séparé pour `docs/rapport-projet.md`, tous deux poussés sur `origin/main`.

### File List

- `config/sources.yaml` — modifié : 13 sources ajoutées (8 apprendre, 3 ce qui bouge, 2 pour le métier), `racine: hits` sur `hacker-news`.
- `tests/test_socle_reel.py` — modifié : nouveau test `test_le_socle_couvre_le_registre_pour_le_metier` (AC3/AC5).
- `_bmad-output/implementation-artifacts/deferred-work.md` — modifié : nouvelle entrée documentant le défaut de `rss_connector._to_utc_datetime` trouvé en Task 4.
- `_bmad-output/implementation-artifacts/2-1-etendre-le-socle.md` — ce fichier (story).

### Change Log

| Date | Changement |
|---|---|
| 2026-09-01 | Story créée, Task 1 (vérification réelle des 13 URL) exécutée. |
| 2026-09-01 | Task 2 : 13 sources ajoutées à `sources.yaml` ; écart trouvé et corrigé (`hacker-news priorite: 0` → `1`, garde-fou existant). |
| 2026-09-01 | Task 3 : nouveau garde-fou `pour_le_metier` ajouté à `test_socle_reel.py` ; suite complète (324 tests) verte. |
| 2026-09-01 | Task 4 : exécution réelle contre les 17 sources ; écart trouvé et corrigé (`hacker-news` MUETTE → `racine: hits` ajouté) ; défaut de dates sur flux Atom/RDF trouvé et documenté (non corrigé, hors périmètre AC1). Statut → review. |
