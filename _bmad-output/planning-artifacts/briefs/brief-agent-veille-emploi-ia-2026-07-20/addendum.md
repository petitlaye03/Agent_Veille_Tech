---
title: "Addendum — Agent de veille IA"
status: draft
created: 2026-07-23
updated: 2026-07-24
---

# Addendum

Matière technique destinée au PRD et à l'architecture. Non nécessaire à la lecture du brief.

Trois campagnes de vérification menées les 20 et 23-24 juillet 2026, environ 280 sources testées par requêtes HTTP réelles (code retour, nombre d'items, dates de publication effectives). **Aucune URL n'est reprise d'une documentation sans test.** Les dates marquées ✅ proviennent du flux lui-même, pas d'un annuaire.

---

## 1. Socle de sources v1

### 1.1 Publications de recherche

| Source | Accès | Volume | Filtrage |
|---|---|---|---|
| **HF Daily Papers** | `https://huggingface.co/api/daily_papers` — JSON, sans auth | 19-26/jour | **Seuil `upvotes >= 15` → 4 papiers/jour.** Variante robuste : `max(10, p80 du jour)` |
| **arXiv API** | `https://export.arxiv.org/api/query` — ⚠️ HTTPS obligatoire (HTTP → 301) | **880/jour bruts** | Jamais en balayage. Uniquement enrichissement d'un ID déjà retenu, ou requête ciblée. Dans le RSS, ne garder que `announce_type = new` |
| **Semantic Scholar** | `/graph/v1/paper/` — clé gratuite requise (429 sans clé) | — | **Enrichisseur, pas source.** Le champ `tldr` (résumé en une phrase) est excellent pour générer les accroches |
| **Conférences** | `https://{conf}.cc/static/virtual/data/{conf}-{année}-orals-posters.json` | ICML 2026 : 7173 papiers | **Non documenté, sans auth.** Filtrer `eventtype == "Oral"`. Ingestion ponctuelle à la publication des actes |

Champs utiles de HF Daily Papers : `paper.summary` (abstract complet), `paper.id` (= ID arXiv), `upvotes`, `submittedOnDailyAt`.

⚠️ **Piège de timing** : `submittedOnDailyAt` est à minuit UTC mais les votes s'accumulent toute la journée. La génération nocturne capte la journée complète ; une génération matinale verrait des compteurs à zéro. **Le choix d'horaire pris pour la fiabilité est aussi le bon pour la qualité du tri.**

### 1.2 Écosystème du code

| Source | Accès | Volume |
|---|---|---|
| **GitHub Releases** | `https://github.com/{owner}/{repo}/releases.atom` — Atom, sans auth | 0-3/jour sur 15 dépôts |
| **GitHub Search** | `api.github.com/search/repositories?q=created:>J-30+stars:>500` | 60 req/h sans auth, 5000 avec PAT gratuit |
| **HF Models trending** | `https://huggingface.co/api/models?sort=trendingScore&direction=-1` | Seuil ~200 + filtre `pipeline_tag` |

Dépôts vérifiés pour `releases.atom` : `huggingface/transformers`, `langchain-ai/langchain`, **`ggml-org/llama.cpp`** (⚠️ migré depuis `ggerganov/`), `vllm-project/vllm`, `pytorch/pytorch`, `duckdb/duckdb`, `pola-rs/polars`, `dbt-labs/dbt-core`, `ollama/ollama`, `unslothai/unsloth`, `apache/spark`.

C'est **le meilleur rapport signal/bruit de toute la cartographie** : zéro bruit, zéro authentification, et précède l'actualité de plusieurs semaines. Affiner en ignorant les patch releases (`x.y.Z`) et en extrayant la section « Breaking changes ».

⚠️ Ne pas utiliser **HF Spaces** dans le digest : pollué par des clones et du contenu NSFW.

### 1.3 Communautés

| Source | Accès | Volume filtré |
|---|---|---|
| **Hacker News (Algolia)** | `https://hn.algolia.com/api/v1/search_by_date?tags=story&numericFilters=points>150,created_at_i>{J-1}` | **14 items/jour** (`points>250` → ~5) |
| **Lobsters** | `https://lobste.rs/t/ai.json` — sans auth | Quelques-uns/jour, modération stricte |
| **Reddit** | ⚠️ voir démarches §4 | 2 sous-reddits max en RSS |

⚠️ **Reddit est le plus contraint** : `.json` → 403, `.rss` → 429 dès la 3ᵉ requête. Espacer de 5-8 s minimum, prévoir un backoff exponentiel et un cache. **Un échec Reddit ne doit jamais casser le digest.**

### 1.4 Podcasts — ce qui manque à la liste actuelle

**Diagnostic** : les dix podcasts déjà écoutés sont tous des sources d'actualité et de commentaire. Aucun ne fait d'ingénierie. Les ajouts ci-dessous sont de **nature différente**, pas simplement supplémentaires.

| Podcast | Langue | Angle | RSS | Dernier ép. |
|---|---|---|---|---|
| **DataGen** | FR | ⭐ Data/IA, praticiens, 304 ép. | `https://feeds.acast.com/public/shows/5fa58959e64011214fbf140d` | ✅ 23/07/26 |
| **Big Data Hebdo** | FR | Data engineering technique | `https://www.spreaker.com/show/1952874/episodes/feed` | ✅ 23/07/26 |
| **IFTTD** | FR | Dev/archi, 732 ép. | `https://feeds.audiomeans.fr/feed/03d88297-85c1-475f-a491-a6c7a443ffca.xml` | ✅ 22/07/26 |
| **Data Driven 101** | FR | IA appliquée | `https://feed.ausha.co/Zg3aMSGpk5Om` | ✅ 21/07/26 |
| **The AI Engineer Podcast** | EN | Ingénierie IA appliquée | `https://rss.art19.com/the-ai-engineer-podcast` | ✅ 22/07/26 |
| **MLOps.community** | EN | ML en production | `https://anchor.fm/s/174cb1b8/podcast/rss` | ✅ 20/07/26 |
| **Data Engineering Podcast** | EN | Stack data | `https://serve.podhome.fm/rss/1c0357c0-6aba-5766-a2d5-2090d8dab6bc` | ✅ 08/07/26 |
| **Latent Space** | EN | AI engineering, référence | `https://api.substack.com/feed/podcast/1084089.rss` | 21/07/26 |
| **Interconnects** | EN | Post-training, RLHF | `https://api.substack.com/feed/podcast/48206.rss` | ✅ 22/07/26 |
| **Vanishing Gradients** | EN | Data science/LLM en pratique | `https://api.substack.com/feed/podcast/2632531.rss` | ✅ 17/07/26 |
| **Weaviate Podcast** | EN | ⭐ RAG, vector search | `https://anchor.fm/s/cffc3468/podcast/rss` | ✅ 01/06/26 |
| **Practical AI** | EN | ML appliqué, pédagogique | `https://feeds.transistor.fm/practical-ai-machine-learning-data-science-llm` | ✅ 23/07/26 |
| **The AI Daily Brief** | EN | Actu quotidienne, 10-20 min | `https://anchor.fm/s/f7cac464/podcast/rss` | ✅ 23/07/26 |
| **ThursdAI** | EN | Récap hebdo très technique | `https://api.substack.com/feed/podcast/1801228.rss` | ✅ 17/07/26 |

Quotidiens courts FR utilisables comme repère de rythme : **Culture IA** (`https://feeds.simplecast.com/yRFCMe21`), **ZD Tech** (`https://feed.ausha.co/bPAr5h5jxxlD`), **Choses à Savoir TECH** (`https://feeds.acast.com/public/shows/660681b953b2df00165f1c32`) — tous ✅ 23/07/26.

### 1.5 Vidéo — montée en compétence

Flux : `https://www.youtube.com/feeds/videos.xml?channel_id=<ID>`

| Chaîne | Langue | Angle | channel_id |
|---|---|---|---|
| **StatQuest** | EN | ⭐ Stats/ML pas à pas | `UCtYLUTtgS3k1Fg4y5tAhLbw` |
| **3Blue1Brown** | EN | Maths visuelles | `UCYO_jab_esuFRV4b17AJtAw` |
| **ArjanCodes** | EN | ⭐ Design logiciel Python | `UCVhQ2NnY5Rskt6UjCUkJ_DA` |
| **AI Explained** | EN | Analyse d'actu, anti-hype | `UCNJ1Ymd5yFuUPtn21xtRbbw` |
| **Hugging Face** | EN | Tutos, agents | `UCHlNU7kIZhRgSbhHvFoy72w` |
| **AI Engineer** | EN | Talks de conférence | `UCLKPca3kwwd-B59HNr-_lvA` |
| **IBM Technology** | EN | Pédagogique | `UCKWaEZ-_VweaEx1j62do_vQ` |
| **Fireship** | EN | Tech en 100 s | `UCsBjURrPoezykLs9EqgamOA` |
| **Computerphile** | EN | Informatique fondamentale | `UC9-y-6csu5WGm29I7JiwpnA` |
| **Defend Intelligence** | FR | IA vulgarisée par un ingénieur | `UCnEHCrot2HkySxMTmDPhZyg` |
| **Grafikart.fr** | FR | Tutos dev concrets | `UCj_iGliGCkLcHSZ8eqVNPDQ` |
| **Micode** | FR | Vulgarisation info/sécu | `UCYnvxJ-PKiGXo_tYXpWAC-w` |
| **PyData** | EN | Talks data science | `UCOjD18EJYcsBog4IozkF_7w` |
| **Devoxx France** | FR | Captations Devoxx | `UCsVPQfo5RZErDL41LoWvk0A` |

### 1.6 Newsletters et blogs — socle

**Analyse IA (EN)**

| Source | Flux | Rythme |
|---|---|---|
| Import AI (Jack Clark) | `https://jack-clark.net/feed/` | 1-2/mois |
| TLDR AI | `https://tldr.tech/api/rss/ai` | Quotidien |
| Ahead of AI (Raschka) | `https://magazine.sebastianraschka.com/feed` | ~1/mois |
| Interconnects | `https://www.interconnects.ai/feed` | 2-3/sem |
| Deep Learning Weekly | `https://www.deeplearningweekly.com/feed` | Hebdo |
| Latent Space | `https://www.latent.space/feed` | Quasi-quotidien |
| Simon Willison | `https://simonwillison.net/atom/entries/` | ⚠️ `/entries/` et non `/everything/` |

**Praticiens (EN)** — haute valeur pour un profil junior

| Source | Flux |
|---|---|
| Eugene Yan — ML appliqué, evals, RAG | `https://eugeneyan.com/rss/` |
| Hamel Husain — evals LLM, fine-tuning | `https://hamel.dev/index.xml` |
| Lil'Log (Lilian Weng) | `https://lilianweng.github.io/index.xml` |
| Vicki Boykis — embeddings | `https://vickiboykis.com/index.xml` |
| Maarten Grootendorst — guides visuels LLM | `https://newsletter.maartengrootendorst.com/feed` |
| Andrej Karpathy | `https://karpathy.bearblog.dev/feed/` |

**Data engineering / MLOps**

| Source | Flux |
|---|---|
| Data Engineering Weekly | `https://www.dataengineeringweekly.com/feed` |
| Data Engineering Central | `https://dataengineeringcentral.substack.com/feed` |
| Gradient Flow (Ben Lorica) | `https://gradientflow.substack.com/feed` |
| dbt blog | `https://www.getdbt.com/blog/rss.xml` |
| DuckDB | `https://duckdb.org/feed.xml` |

**Laboratoires**

| Labo | Flux |
|---|---|
| OpenAI | `https://openai.com/news/rss.xml` |
| Google DeepMind | `https://deepmind.google/blog/rss.xml` |
| Google Research | `https://research.google/blog/rss/` |
| Hugging Face | `https://huggingface.co/blog/feed.xml` ⭐ meilleur ratio technique/accessible |
| NVIDIA Developer | `https://developer.nvidia.com/blog/feed/` |
| Microsoft Research | `https://www.microsoft.com/en-us/research/feed/` |

**Ingénierie de plateforme** — Netflix (`https://netflixtechblog.com/feed`), Meta (`https://engineering.fb.com/feed/`), Airbnb (`https://medium.com/feed/airbnb-engineering`), Pinterest (`https://medium.com/feed/pinterest-engineering`), Grab (`https://engineering.grab.com/feed.xml`), GitHub (`https://github.blog/engineering/feed/`).

**Médias EN** — Ars Technica AI (`https://arstechnica.com/ai/feed/`), MIT Tech Review AI (`https://www.technologyreview.com/topic/artificial-intelligence/feed`), InfoQ AI/ML/Data (`https://feed.infoq.com/ai-ml-data-eng/`), IEEE Spectrum AI (`https://spectrum.ieee.org/feeds/topic/artificial-intelligence.rss`).

**FR** — Brief IA (`https://www.briefia.fr/rss.xml`, ⭐ quotidien gratuit), Next (`https://next.ink/feed/`, ⚠️ paywall partiel), Le Monde Informatique (`https://www.lemondeinformatique.fr/thematique/intelligence-artificielle/rss.xml`), Silicon.fr (`https://www.silicon.fr/feed`), Décideo (`https://www.decideo.fr/xml/syndication.rss`, quasi seul sur la data FR), JDN section IA (`https://www.journaldunet.com/intelligence-artificielle/rss/`), CNIL (`https://www.cnil.fr/fr/rss.xml`, angle AI Act).

### 1.7 Signal marché

| Source | Accès | Intérêt |
|---|---|---|
| **Kaggle competitions** | `/api/v1/competitions/list` — token gratuit requis | ⭐ Le seul flux qui dit **ce qu'il faut savoir faire** plutôt que ce qui s'est passé. 3-6 mois d'avance sur les offres d'emploi |
| **OpenRouter** | `https://openrouter.ai/api/v1/models` — sans auth, 343 modèles | Diff quotidien des `id` → nouveaux modèles et changements de prix. Reflète l'usage payant réel |

---

## 2. Sources sans flux officiel — contournements

Le dépôt **`alan-turing-institute/ai-rss-feeds`** génère des flux pour une douzaine de sites qui n'en exposent pas : Anthropic (news et research), Claude blog, Mistral, Cohere, The Batch, TLDR AI, AllenAI, AISI, Mila, Turing. Adossé à une institution publique, donc plus pérenne qu'un miroir personnel. Chemin : `https://raw.githubusercontent.com/alan-turing-institute/ai-rss-feeds/main/feeds/{nom}.xml`.

⚠️ Les items y sont **non triés chronologiquement** — trier soi-même.

| Cible | Solution retenue | Réserve |
|---|---|---|
| **Anthropic** | `https://tim-hilde.github.io/anthropic-rss/rss.xml` (plus frais) **+** repo Turing (`anthropic-news.xml`, `anthropic-research.xml`) | Dépôt personnel pour le premier → prévoir un scraper de secours sur `anthropic.com/news`, page rendue côté serveur donc extractible |
| **Mistral** | Repo Turing (`mistral-news.xml`) | — |
| **Cohere** | Repo Turing (`cohere-blog.xml`) | `cohere.com/blog/rss.xml` renvoie du HTML |
| **The Batch** | Repo Turing (`the-batch.xml`) | ⚠️ Retard d'environ 3 semaines |
| **Meta AI** | `https://engineering.fb.com/feed/` — substitut partiel | Ne couvre pas les annonces FAIR/Llama |

**Non résolus** : Uber Engineering (406 systématique, protection Akamai — perte réelle, c'est un des meilleurs blogs data engineering), LinkedIn Engineering (flux semble définitivement supprimé), DoorDash (403 Cloudflare). Une instance RSSHub auto-hébergée serait la piste la plus robuste, non testée.

---

## 3. Pièges vérifiés — à ne pas répéter

**Un code HTTP 200 ne prouve rien.** C'est le constat le plus important de la cartographie.

| Piège | Constat |
|---|---|
| **Open LLM Leaderboard** | Le Space tourne (14 000 mentions « j'aime ») mais le dataset est **figé depuis mars 2025**. Un agent naïf publierait des classements vieux de 16 mois |
| **ActuIA** | 200 avec 16 items, mais **les 16 `pubDate` sont identiques à la seconde** (migration WordPress → Laravel du 07/07/2026). Cadence réelle ≈ mensuelle. **Dédoublonner par URL/GUID, jamais par date** |
| **VentureBeat `/category/ai/feed/`** | Items de janvier à mai 2026 avec un `lastBuildDate` du jour. Cassé — prendre le flux principal, qui ne contient que **6 items** (poller toutes les 1-2 h) |
| **Métadonnées iTunes** | Annonce Data Driven 101 mort depuis juillet 2025 alors que son flux publiait le 21/07/2026. Et l'inverse arrive |
| **Flux non triés** | Developer Voices semble arrêté en 2023 si l'on lit le premier `<item>`. Toujours prendre le `max(pubDate)` |
| **Flux vides** | Papers with Code, Shopify Engineering, W&B Fully Connected, Deep Papers : 200 avec zéro item |

**Morts ou dépréciés** : Papers with Code (302 → HF Papers), OpenReview `/notes` (403 depuis l'incident de sécurité ICLR 2026), alphaXiv REST (n'existe pas ; seul le MCP, quota-based), High Scalability (mai 2024), Sebastian Ruder (mai 2024), Chip Huyen (janv. 2025), Jay Alammar (nov. 2025), The Gradient (quasi-mort), Inria FR (sept. 2024), `abhshkdz/ai-deadlines` (figé en 2025 — utiliser le fork Hugging Face).

**Podcasts arrêtés** : Le Fil IA (juin 2026), L'IA aujourd'hui (janv. 2026, après 400 épisodes), Go Time, JS Party, Ship It, Electro Monkeys, Le Comptoir Sécu, L'Octet Vert, The Robot Brains.

**YouTube dormant** : Machine Learnia (oct. 2024) et Thibault Neveu (juin 2024) — la vulgarisation ML technique francophone n'a plus de flux vivant. Andrej Karpathy (fév. 2025), Yannic Kilcher (mars 2026, très ralenti). Archives précieuses, rien à surveiller.

### Règles de découverte de flux confirmées

- **Substack** `/feed` — 100 % de réussite (12/12 testés)
- **WordPress** `/feed/`, **Ghost** `/rss/` — fiables
- **Beehiiv** — ⚠️ l'exception : le domaine custom échoue souvent (`therundown.ai/feed` → 404) alors que `rss.beehiiv.com/feeds/<id>.xml` fonctionne. L'ID est dans le HTML de la page
- **Chemins non standards** : Dropbox = `/feed` (pas `/feed.xml`), The Neuron = `/rss.xml` (pas `/feed`)
- **Podcasts** : résoudre via `https://itunes.apple.com/search?term=NOM&country=FR&media=podcast`, champ `feedUrl` — puis **vérifier le XML**, l'annuaire ment
- **The Register** : `headlines.atom` renvoie un 302 cross-host, il faut suivre la redirection

---

## 4. Démarches administratives à lancer tôt

| Démarche | Délai | Coût | Enjeu |
|---|---|---|---|
| **Reddit OAuth** | ⚠️ **2 à 4 semaines** (pré-approbation obligatoire depuis la Responsible Builder Policy de nov. 2025, auto-inscription fermée) | Gratuit en usage non commercial, 100 req/min | Sans cela, le RSS tombe en 429. Seule démarche réellement bloquante |
| **Clé Semantic Scholar** | Immédiat | Gratuit, 1 req/s | Le champ `tldr` sert à générer les accroches |
| **Token Kaggle** | Immédiat (compte → Create New API Token) | Gratuit | Signal marché unique |
| **PAT GitHub** | Immédiat | Gratuit | Passe de 60 à 5000 req/h |

---

## 5. Volumes à maîtriser

| Source | Volume brut | Mitigation |
|---|---|---|
| arXiv cs.AI | **240-322/jour** | ⛔ Jamais brut — passer par HF Daily Papers |
| arXiv cs.CL / cs.LG | 105 / 40-268 par jour | Filtrer par mots-clés ciblés |
| ThoughtWorks Insights | **2 714 items** dans le flux | Parser une fois, puis incrémental strict sur GUID |
| Semafor | 261 items, toutes sections | Filtrer la catégorie Technology |
| LeBigData | Publication horaire | ⚠️ Malgré le nom, c'est du SEO grand public. Priorité basse |
| Zvi | 10-20k mots/post, quasi-quotidien | Titre + résumé seulement |
| TechCrunch AI, The New Stack, Developpez | Plusieurs/heure | **Dédoublonnage inter-sources indispensable** — une même annonce est couverte par quinze flux |
| AWS ML, Databricks, Google Cloud | Quotidien, très marketing | Filtrer sur mots-clés techniques |

---

## 6. Synthèse vocale — pour une éventuelle v2

Écarté de la v1 faute de matériel et de budget.

Volume estimé : 5 minutes ≈ 750-900 mots ≈ ~5 000 caractères/jour ≈ 150 000 caractères/mois.

| Solution | Coût mensuel estimé |
|---|---|
| **Kokoro-82M (local)** | **0 €** — Apache 2.0, tourne sur CPU, français natif |
| Azure Neural / OpenAI TTS | ~2,25 $ |
| ElevenLabs | ~18-25 $ |

Tarifs issus de comparatifs tiers, non vérifiés sur les pages officielles.

**Point non levé** : la qualité du français de Kokoro n'a pas été évaluée à l'écoute. Les modèles multilingues compacts sont souvent bons en anglais et faibles en français (prosodie, liaisons, sigles type « GPT-5 », « LLM »). Test A/B préalable à toute reprise de cet axe. Alternative : Chatterbox (Resemble AI, MIT). À éviter : XTTS v2 (licence non commerciale).

---

## 7. Agent emploi — matière conservée, périmètre abandonné

Abandonné le 2026-07-23. Conservé ici parce que le besoin ressurgira et que refaire cette cartographie coûterait cher.

**Ce qui rendait le terrain difficile.** Aucun job board sénégalais n'expose d'API ni de flux. **emploisenegal.com**, la source la plus riche du marché local (pages taxonomiques `/emploi-intelligence-artificielle`, `/recrutement-big-data`), interdit nommément `ClaudeBot` en robots.txt, pose un signal `Content-Signal: ai-train=no` (réservation de droits au titre de l'article 4 de la directive UE 2019/790) et renvoie `403` derrière Cloudflare. Recommandation actée : consultation manuelle et alertes email natives, jamais d'automatisation.

Limite structurelle : ~60 % du recrutement sénégalais passe par le bouche-à-oreille, Dakar concentre ~80 % des offres du pays. Le stock d'offres strictement « data science » à Dakar se compte probablement en unités par mois — non mesuré, la source principale étant inaccessible.

**Les deux canaux qui tenaient debout**, et que le chiffre des 60 % ne concernait pas :

- **ReliefWeb API v2** (`/jobs`) — réagrège PNUD, UNICEF, GIZ et le circuit ONG en une seule intégration, filtrable par pays. Meilleur alignement avec le profil : organisations très présentes à Dakar, postes data, travail en français. ⚠️ v1 décommissionnée (`410 Gone`) ; v2 exige un `appname` approuvé, enregistrement gratuit via `apidoc.reliefweb.int`. Jamais testée fonctionnellement.
- **Himalayas API** (`/jobs/api/search`) — 99 748 offres, sans clé. Seul canal remote exposant `locationRestrictions` et `timezoneRestrictions`, donc le seul où l'éligibilité géographique est filtrable en amont plutôt que découverte à la candidature.

Autres sources retenues au moment de l'abandon : **aijobs.net** (100 % IA/ML, robots permissif, aucune API), **senjob.com** (seul board sénégalais collectable), **Remotive API**, **WeWorkRemotely RSS**.

Écartés : RemoteOK (plafond 100 offres, CGU de backlink), JSearch (payant, scraper tiers), Arbeitnow (biais germanophone, pas de champ visa dans l'API), Wellfound (CGU anti-scraping), Banque Mondiale et BAD (authentification navigateur), LinkedIn (CGU).

**Relocalisation — appréciation franche.** La sponsorisation de visa pour un data scientist *junior* reste difficile : les employeurs sponsorisent surtout à partir de 3-5 ans d'expérience. Pays-Bas (régime *kennismigrant*, seuil salarial abaissé pour les moins de 30 ans, sponsors agréés listés par l'IND) et Allemagne (Opportunity Card sur points) sont les régimes les plus favorables. Golfe : sponsorisation quasi systématique mais exigence d'anglais professionnel élevée. Canada : délais incompatibles avec une disponibilité novembre 2026.

---

## 8. Angles morts

- **Une trentaine de podcasts** validés seulement par la date iTunes, sans lecture du XML — risque faible pour ceux datés de juillet 2026, mais réel
- **Le « niveau » et l'« angle éditorial »** attribués aux podcasts reposent sur leur description, pas sur une écoute d'épisodes récents : ce sont des jugements, pas des mesures
- **Uber, DoorDash, LinkedIn Engineering** — bloqués depuis cet environnement ; un navigateur headless ou un RSSHub privé pourrait changer le verdict
- **RSSHub auto-hébergé** — les deux instances publiques testées renvoient 403, l'auto-hébergement n'a pas pu être testé
- **Stabilité du pattern `virtual/data`** des conférences — non documenté, donc sans garantie. Prévoir un repli
- **Limites de débit** — aucune API gratuite ne publie de quota chiffré (« generous », « please do not abuse »). À découvrir empiriquement, prévoir du backoff dès la v1
- **Volumes hors jour de test** — les comptages arXiv et HF datent du 23/07/2026. Le lundi et les périodes pré-deadline NeurIPS/ICLR les gonflent fortement : **le seuil de votes doit être dynamique, pas fixe**
- **Reddit OAuth** — délai de 2-4 semaines issu de sources secondaires, pas de la documentation officielle
- **Pérennité des miroirs GitHub** — actifs aujourd'hui, mais dépendances fragiles par nature
- **« L'IA du Capitaine »** — introuvable sous ce nom, possible confusion. **« Café Croissant »** — aucun podcast tech FR de ce nom ; probable confusion également
- **« Le Code a changé »** (France Inter) — actif, mais Radio France n'expose pas le flux via l'API iTunes ; à résoudre manuellement
- **Statut du successeur de Papers with Code** — non vérifié au-delà de la redirection vers HF
