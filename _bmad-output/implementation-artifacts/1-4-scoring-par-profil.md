---
baseline_commit: 6fc68aa
---

# Story 1.4: Filtrer par signal de source et classer par pertinence

Status: done

> **Périmètre élargi le 2026-07-29.** L'analyse de création a révélé que **FR-4 (seuils de signal par source) n'était couvert par aucune story** : il figure dans la couverture de l'Epic 1 et dans la ligne « FRs covered » de l'épic, mais aucune des neuf stories ne l'implémentait. Décision de l'utilisateur : l'intégrer ici plutôt que d'en faire une story séparée ou de le reporter — les deux mécanismes vivent dans `filter.py` et le seuil de signal fait un travail que le scoring par profil ferait mal.

## Story

As a Abdoulaye,
I want que les items soient d'abord filtrés par le signal de leur source, puis classés selon mon profil de centres d'intérêt,
so that les items les plus pertinents remontent en premier sans que le tri ait à trancher dans du bruit évitable.

## Acceptance Criteria

1. **[FR-4]** Une Source peut déclarer un seuil de signal en configuration ; un item dont le signal est sous le seuil est écarté avant tout scoring.
2. **[FR-4]** Une Source sans seuil déclaré voit tous ses items conservés — le filtrage par signal est optionnel, jamais implicite.
3. **[FR-5]** Étant donné le fichier `profil.md` (thèmes prioritaires, bruit) et un jeu d'items collectés, l'exécution du scoring attribue un score de pertinence à chaque item.
4. **[FR-5]** Un item touchant un thème prioritaire (RAG, agents, evals…) est classé **devant** un item générique.
5. **[FR-5]** Un item relevant du bruit (crypto, hype, actu conso) est **fortement pénalisé ou écarté**.
6. **[FR-4/5]** Modifier `profil.md` ou un seuil dans `sources.yaml` change le résultat **sans toucher au code**.
7. Le récapitulatif rend compte de ce qui a été écarté, par source et par motif (signal insuffisant / bruit) — sans quoi un filtrage excessif serait invisible.

## Tasks / Subtasks

- [x] Task 0 : Capturer le signal de source (AC: 1,2) — **prérequis, à traiter en premier**
  - [x] ~~⚠️ Décision d'architecture requise avant de coder~~ — **tranché le 2026-08-27 : Option A retenue.** AD-4 amendé dans `ARCHITECTURE-SPINE.md` pour autoriser `signal` comme 9ᵉ champ optionnel d'`Item`. Voir la note d'amendement sous AD-4.
  - [x] Ajouter `signal: float | None = None` à `Item`, optionnel et neutre par défaut
  - [x] `json_connector` extrait le signal via `mapping.signal` quand il est déclaré
  - [x] Déclarer `mapping.signal: paper.upvotes` sur `hf-daily-papers` dans `sources.yaml`
  - [x] Vérifier qu'aucun connecteur existant ne casse : un `Item` sans signal reste valide
  - [x] Tests : signal extrait quand déclaré, `None` sinon, valeur non numérique ignorée sans lever

- [x] Task 1 : Déplacer le profil en configuration (AC: 3,6)
  - [x] Copier `_bmad-output/planning-artifacts/prds/prd-agent-veille-emploi-ia-2026-07-24/profil-draft.md` vers `config/profil.md`
  - [x] Le fichier source reste en artefact de planification ; `config/profil.md` devient la version vivante lue par le code (AD-3)
  - [x] Ajouter un en-tête expliquant qu'éditer ce fichier suffit à changer le classement

- [x] Task 2 : Analyser le profil en règles de scoring (AC: 1,4)
  - [x] Créer `src/veille/profil.py` avec `charger_profil(chemin) -> Profil`
  - [x] Extraire les mots-clés par catégorie à partir des titres `##` connus (voir mapping en Dev Notes)
  - [x] Ne **jamais lever** : un profil absent ou illisible doit produire un profil neutre et un avertissement, pas un plantage (leçon Story 1.3)
  - [x] Tests : profil réel, profil vide, profil malformé, section inconnue ignorée

- [x] Task 2bis : Filtrer par seuil de signal (AC: 1,2,7)
  - [x] Ajouter `seuil_signal: float | None = None` à `SourceConfig`
  - [x] Dans `filter.py`, écarter les items dont `signal` est sous le seuil de leur source
  - [x] **Un item sans signal face à une source qui en déclare un seuil est conservé, pas écarté** — l'absence de donnée n'est pas une insuffisance ; l'écarter supprimerait silencieusement du contenu légitime
  - [x] Déclarer `seuil_signal: 15` sur `hf-daily-papers` (voir justification en Dev Notes)
  - [x] Tests : seuil respecté, source sans seuil intacte, item sans signal conservé

- [x] Task 3 : Scorer un item (AC: 3,4,5)
  - [x] Créer `src/veille/filter.py` avec `scorer(item, profil) -> Score`
  - [x] Recherche de mots-clés sur titre + contenu, insensible à la casse et aux accents
  - [x] Correspondance sur **mot entier** — voir le piège documenté en Dev Notes
  - [x] Pondérations par catégorie, déclarées en configuration et non en dur (`config/scoring.yaml`)
  - [x] Tests couvrant chaque catégorie et le cumul

- [x] Task 4 : Classer et écarter le bruit (AC: 2,3)
  - [x] `classer(items, profil) -> list[ItemScore]` trié par score décroissant
  - [x] Un item sous le seuil de bruit est écarté, pas seulement rétrogradé
  - [x] Départage stable à score égal (pas d'ordre aléatoire — leçon Story 1.3)
  - [x] Tests : un item prioritaire précède un générique ; un item bruit est écarté

- [x] Task 5 : Brancher dans la collecte et rendre compte (AC: 1,3)
  - [x] Intégrer le classement après le dédoublonnage dans `collecter()` — *l'ordre a été corrigé en revue : le seuil de signal passe désormais **avant** le dédoublonnage, le classement reste en dernier*
  - [x] Étendre le récapitulatif : combien d'items écartés comme bruit, et la répartition des scores — *complété en revue : ventilation **par source**, et non plus totaux seuls (AC7)*
  - [x] **Tests d'intégration empruntant le chemin réel** depuis `config/profil.md` — pas seulement des appels directs

- [x] Task 6 : Validation (AC: 1,2,3,4)
  - [x] Suite complète verte — **189 tests** après revue (147 avant)
  - [x] **Audit par mutation — refait après revue, 9 mutants tués.** ⚠️ Le premier audit ne portait que sur le **code** : il déclarait 3 mutants tués mais laissait survivre 4 mutants de **configuration**, ce qui a laissé passer l'échec de l'AC5. Audit complet : pondérations neutralisées (19 échecs), signe du bruit inversé (9), classement court-circuité (10), `seuil_signal` retiré de `sources.yaml` (2), `mapping.signal` retiré (1), section Bruit du profil vidée (3), lecture des pondérations neutralisée (1), ordre du pipeline réinversé (1), `scoring.yaml` supprimé (1). Suite restaurée et revérifiée verte à chaque fois.
  - [x] Exécution réelle **par le chemin de production** — ⚠️ *rectifie une note erronée du premier passage : elle affirmait que le papier « TRACE » remontait en tête, alors que ses 0 vote l'éliminent avant tout scoring sous le `seuil_signal: 15` réel ; la vérification avait en fait utilisé un socle ad hoc à seuil 0, donc elle ne validait pas le chemin qu'elle prétendait valider.* Nouveau relevé, socle calqué sur la production : sur 10 items collectés, 3 sont écartés par le seuil (11, 3 et 0 votes) et 3 le franchissent (45, 24, 15) ; en tête viennent le papier retrieval/reranking (25), la quantization/fine-tuning (17,5), puis l'évaluation d'agents (15), les annonces de modèles (10) et les billets génériques (0). Le récapitulatif nomme la source écartée (`hf-daily-papers (-3)`).

### Review Findings

> Revue de code du 2026-08-28 (skill `bmad-code-review`, 3 couches adversariales sur Opus 5 ;
> implémentation faite sur Sonnet 5). Base de diff `6fc68aa`. Tous les constats ci-dessous ont
> été **revérifiés par exécution** avant classement, pas repris sur parole des relecteurs.

**Décisions — tranchées le 2026-08-28**

- [x] [Review][Decision] **AC5 non satisfait : 6 des 14 mots-clés de bruit sont des phrases mortes** — `_extraire_mots_cles` ne découpe que sur `[,:()&/]` et le tiret cadratin, donc une puce rédigée en phrase devient un mot-clé égal à la phrase entière : `'Levées de fonds et actualité business pure sans contenu technique'`, `'Hype et prédictions vagues'`, `"Produits SaaS commerciaux sans intérêt d'apprentissage"`, `"Contenu purement marketing des blogs d'éditeurs"`, `'sans substance'`, `"« l'IA va tout changer »"`. Mesuré : `"Anthropic raises 3B in new funding round"` → **+2.0** (promu !), `"The AI hype is real"` → 0.0. Sur les trois exemples que l'AC5 nomme, seul `crypto` fonctionne. → **Décision : réécrire la section Bruit de `config/profil.md` en mots-clés atomiques**, parseur inchangé. [src/veille/profil.py:138-155, config/profil.md]
- [x] [Review][Decision] **Le dédoublonnage s'exécute avant le seuil de signal : le seuil d'une source ampute une autre** — le seuil est déclaré *par source* mais s'applique après l'élection du gagnant. → **Décision : inverser l'ordre — seuil de signal AVANT dédoublonnage**, et mettre à jour les Dev Notes et le schéma de pipeline en conséquence. [src/veille/collect.py:196-202]
- [x] [Review][Decision] **Double comptage inter-catégories** — `retrieval` figure en prioritaire *et* en signal_fort → 10+15 = 25 pour un seul thème. → **Décision : défaut. Un thème ne compte qu'une fois, au poids de sa catégorie la plus élevée.** [src/veille/profil.py:98]
- [x] [Review][Decision] **Cumul additif sans plafond** — `"Cloud infrastructure monitoring"` → 30 pts devance `"Retrieval-augmented generation"` → 25 pts. → **Décision : rendements décroissants par catégorie** (2ᵉ mot-clé d'une catégorie à moitié, 3ᵉ au quart…). [src/veille/filter.py:165-172]
- [x] [Review][Decision] **Aucune variante singulier/pluriel** — `"AI agents"` → 10.0 mais `"An AI agent"` → 0.0. → **Décision : tolérer un `s` final optionnel** sur la correspondance mot entier ; pas de racinisation (elle rouvrirait les faux positifs que les Dev Notes écartent). [src/veille/filter.py:179]
- [x] [Review][Decision] **AD-1 : `collect.py` orchestre trois étapes, `pipeline.py` n'existe pas** → **Décision : reporté à la Story 1.8** — voir la section Reportés.

**Correctifs**

- [x] [Review][Patch] [décision] Réécrire la section « Bruit » de `config/profil.md` en mots-clés atomiques (levée de fonds, funding, hype, marketing, SaaS, smartphone, gadget…) — sans quoi l'AC5 reste non satisfait [config/profil.md]
- [x] [Review][Patch] [décision] Inverser l'ordre du pipeline : seuil de signal **avant** dédoublonnage, + mise à jour des Dev Notes et du schéma [src/veille/collect.py:196-202]
- [x] [Review][Patch] [décision] Un thème ne compte qu'une fois, au poids de sa catégorie la plus élevée (fin du double comptage inter-catégories) [src/veille/filter.py:165-172]
- [x] [Review][Patch] [décision] Rendements décroissants par catégorie dans le cumul du score [src/veille/filter.py:165-172]
- [x] [Review][Patch] [décision] Tolérer un `s` final optionnel dans la correspondance sur mot entier [src/veille/filter.py:179]

- [x] [Review][Patch] `charger_ponderations` lève `UnicodeDecodeError` et fait perdre la nuit entière, alors que sa docstring promet « ne lève jamais » — `charger_profil` attrape les deux, celle-ci a oublié la moitié ; s'exécute hors de l'isolation AD-6 [src/veille/filter.py:98]
- [x] [Review][Patch] Un `seuil_signal` non numérique dans `sources.yaml` lève `TypeError` et fait perdre la nuit entière — `SourceConfig(**entry)` ne valide aucun type ; couvrir aussi `.nan`/`inf` (comparaison toujours fausse → digest vidé en silence) et les booléens YAML (`prioritaire: yes` → 1.0 silencieux) [src/veille/config.py:42, src/veille/filter.py:67, 120-128]
- [x] [Review][Patch] Frontière `\b` inatteignable sur un mot-clé à ponctuation initiale ou finale : `'Qwen…'` et `"« l'IA va tout changer »"` ne matchent même pas leur propre texte littéral — mots-clés morts, sans avertissement [src/veille/filter.py:179]
- [x] [Review][Patch] AC7 « par source » non rendu : `ecartes_par_source` est calculé dans les deux nouveaux rapports puis jamais imprimé — seuls les totaux sortent, contrairement à `dedup.resume()` qui nomme les sources [src/veille/collect.py:148-155, src/veille/filter.py:225]
- [x] [Review][Patch] L'alerte « source absorbée … après dédoublonnage » accuse le mauvais motif quand la perte vient du seuil ou du bruit — vérifié en exécution : `dedoublonnage.total_ecartes == 0` et le log envoie pourtant chercher un doublon inexistant [src/veille/collect.py:76-83, 294-300]
- [x] [Review][Patch] `config/scoring.yaml` n'a aucun effet observable : supprimer le fichier → 147 passed ; neutraliser sa lecture → 147 passed. Ses valeurs sont identiques aux défauts en dur, donc rien ne distingue les deux chemins. AD-3/AC6 satisfaits en apparence seulement [tests]
- [x] [Review][Patch] Fixture `hf_daily_papers_votes.json` jamais créée alors que la Task 2bis est cochée — le seul test d'intégration du seuil n'éprouve que le côté « tout écarté » ; aucun test ne montre un item survivant au-dessus du seuil par le socle [tests/fixtures/]
- [x] [Review][Patch] `test_socle_reel.py` non modifié malgré la Structure de fichiers de la story — retirer `seuil_signal: 15` *et* `mapping.signal` de `sources.yaml` → 147 passed ; les deux livrables de config des Tasks 0 et 2bis peuvent disparaître sans qu'un test bronche [tests/test_socle_reel.py]
- [x] [Review][Patch] Dev Agent Record inexact : la note de plausibilité affirme que le papier « TRACE » remonte en tête, or ses 0 vote l'éliminent avant tout scoring sous le `seuil_signal: 15` de production (la vérification avait utilisé un seuil à 0). Corriger aussi la mention de `test_scoring_integration.py`, replié dans `TestScoringEffectif` sans être signalé [story:76, Completion Notes]
- [x] [Review][Patch] `DEFAULT_PROFIL_PATH` est relatif au CWD : lancé par le planificateur (le mode d'exécution visé en Epic 3), le profil est introuvable, le filtre est entièrement désactivé et le récapitulatif se lit comme une nuit saine. Aucun champ ne signale « profil neutre » [src/veille/profil.py:17, 92]
- [x] [Review][Patch] Une dizaine de tests appellent `collecter(socle)` sans `profil_path` et lisent donc le `config/profil.md` de production — ajouter un mot-clé de bruit touchant une fixture casserait des tests sans rapport, alors que ce fichier est justement celui qu'Abdoulaye est invité à éditer [tests/test_collecte_integration.py, tests/test_rapport_collecte.py]
- [x] [Review][Patch] Fragilités du parseur de profil sur des éditions plausibles d'un fichier utilisateur : apostrophe typographique dans `## Domaines d'application` → section entière perdue en silence ; titres `###` → profil vide sans le moindre avertissement ; puces `*`/`+`/numérotées non reconnues ; tiret demi-cadratin non traité ; aside italique à parenthèse imbriquée ; catégorie non réinitialisée après un `# ` [src/veille/profil.py:91-102, 138-155]
- [x] [Review][Patch] Un `seuil_signal` déclaré sur une source `rss`/`scrape` (ou une source JSON sans `mapping.signal`) est totalement inerte et muet — le rapport affiche « 0 écarté », qui se lit « rien n'était sous le seuil » alors que le filtre n'a jamais tourné [src/veille/filter.py:63-70]
- [x] [Review][Patch] L'en-tête de `config/profil.md` documente de faux poids relatifs : « domaine » y est dit peser modérément (il pèse moitié moins que prioritaire) et « secondaire » un peu moins (il pèse 5× moins). Trompeur dans un fichier dont la raison d'être est l'auto-service [config/profil.md:7-9]
- [x] [Review][Patch] Import mort `from typing import Any` [src/veille/filter.py:22]

**Reportés**

- [x] [Review][Defer] AD-1 : `collect.py` orchestre trois étapes du pipeline, `pipeline.py` n'existe pas [src/veille/collect.py:22-32, 200-209] — reporté : l'orchestrateur prend son sens quand les étapes rendu et publication existent (Story 1.8) ; l'extraire maintenant pour deux appels serait prématuré
- [x] [Review][Defer] `Score.motifs` est calculé pour chaque item puis intégralement jeté — l'explicabilité annoncée n'est livrée à personne [src/veille/filter.py:143, src/veille/collect.py:208] — reporté : aucun consommateur avant le rendu (Story 1.8)
- [x] [Review][Defer] Le tri final est exclusivement par score ; il n'existe plus aucun tri par fraîcheur [src/veille/filter.py:204] — reporté : l'ordonnancement final relève des quotas (Story 1.5)

## Dev Notes

### ✅ Amendement AD-4 — tranché le 2026-08-27

FR-4 impose de filtrer sur un signal fourni par la source (votes HF, points Hacker News). **Ce signal n'existe nulle part dans le code** : `Item` porte huit champs, aucun ne le capture.

AD-4 dit : *« tout connecteur produit des `Item` portant **au moins** : … Les étapes aval ne consomment que ces champs. »*

- La première partie autorise un champ supplémentaire (« au moins »).
- **La seconde l'interdit** : l'étape de filtrage consommerait un neuvième champ.

Deux options, avec un vrai arbitrage :

| Option | Pour | Contre |
|---|---|---|
| **A. Ajouter `signal` à `Item`** et amender la seconde phrase d'AD-4 | Seuil déclaré en configuration (AD-3), filtrage visible dans le récapitulatif, uniforme entre sources | Modifie le contrat canonique |
| **B. Filtrer dans le connecteur**, avant création de l'`Item` | Aucun changement d'architecture | Le seuil retourne dans le code du connecteur (contraire à AD-3), le filtrage devient invisible au rapport, et chaque connecteur réinvente la règle |

**Recommandation : option A.** L'intention d'AD-4 était d'empêcher des connecteurs d'émettre des formes incompatibles ; un champ optionnel, défini une seule fois et laissé à `None` par défaut, ne crée aucune incompatibilité. L'option B viole AD-3, qui est l'invariant que cette story sert précisément.

**Amendement acté — Task 0 débloquée**, voir `ARCHITECTURE-SPINE.md#AD-4`.

### Seuil de signal : pourquoi 15 sur Hugging Face

La cartographie initiale (addendum du brief) a mesuré la distribution réelle des votes sur HF Daily Papers : `45, 29, 24, 18, 11, 10, 9, 4…`, **médiane 3**. Un seuil à 15 retenait 4 papiers sur 26 le jour du relevé — exactement la cible « 3-5 papiers marquants » du PRD.

⚠️ **Un seuil fixe est fragile** : les volumes gonflent le lundi et avant les échéances de conférences. L'addendum recommandait un seuil dynamique — `max(10, p80 des votes du jour)`. Commencer par le seuil fixe (simple, testable, déclaré en configuration), et garder le dynamique en évolution documentée plutôt qu'en dette cachée.

⚠️ **Piège de calendrier déjà identifié** : les votes s'accumulent au fil de la journée alors que `submittedOnDailyAt` est fixé à minuit UTC. Générer la nuit capte la journée complète ; générer à l'aube verrait des compteurs à zéro et le seuil écarterait tout. Cohérent avec le choix d'horaire déjà acté (~22h heure de Dakar).

⚠️ **La fixture de test actuelle est inadaptée** : `tests/fixtures/hf_daily_papers.json` contient des papiers à 1 et 0 votes. Il faut une fixture aux votes variés pour éprouver le seuil des deux côtés.

### Ordre des étapes : signal puis profil

Le filtrage par signal s'exécute **avant** le scoring par profil. Deux raisons :

1. **Coût** — inutile de scorer un item qu'on va écarter.
2. **Qualité** — le seuil de signal utilise le jugement d'une communauté entière ; le scoring par profil ne connaît que des mots-clés. Laisser le second trancher dans du bruit que le premier élimine proprement dégraderait le résultat.

Pipeline complet après cette story : collecte → dédoublonnage → **seuil de signal → scoring par profil** → (quotas, Story 1.5).

> **Rectifié en revue le 2026-08-28.** L'ordre livré est en réalité :
> collecte → **seuil de signal** → dédoublonnage → **scoring par profil**.
> Le seuil est déclaré *par source* : placé après le dédoublonnage, il jugeait
> l'article sur le seuil de la source ayant remporté l'arbitrage, et pouvait
> ainsi faire disparaître un item auquel aucun seuil ne s'appliquait. Les deux
> raisons énoncées ci-dessus (coût, qualité) restent valables et inchangées —
> seule la position relative au dédoublonnage a bougé.

### Décision structurante : scoring local, jamais par LLM

**1948 items sont collectés chaque nuit** (mesuré sur le socle réel). Deux conséquences non négociables :

- **AD-7 réserve l'API Claude à la seule génération d'accroches.** Aucun autre module ne l'appelle. Scorer par LLM violerait directement cette règle.
- Le budget cible est de **moins de 2 €/mois**. Un appel par item ferait exploser cet ordre de grandeur d'un facteur considérable.

Le scoring est donc **lexical et local** : recherche de mots-clés, coût nul, instantané, et surtout **explicable** — Abdoulaye doit pouvoir comprendre pourquoi un item est remonté. Un scoring sémantique par embeddings est une évolution possible (v2), pas un prérequis.

### Piège à éviter absolument : la correspondance partielle

Chercher un mot-clé par simple sous-chaîne produit des faux positifs qui décrédibilisent tout le classement :

| Mot-clé | Faux positif si sous-chaîne |
|---|---|
| `rag` | « st**rag**egy », « f**rag**ment », « d**rag** » |
| `ia` | « med**ia** », « soc**ia**l », « Austral**ia** » |
| `agents` | « m**anagents** » (rare), mais surtout `agent` dans « agentur » |

**Exiger une correspondance sur mot entier** (frontières de mot), après normalisation de la casse et des accents. Les mots-clés multi-mots (« hybrid search », « vector database ») se cherchent comme séquences.

### Structure du profil et correspondance des sections

`config/profil.md` conserve sa forme lisible par un humain. Le parseur s'appuie sur les titres `##`, dont l'intitulé porte déjà l'intention :

| Titre dans le fichier | Catégorie | Effet sur le score |
|---|---|---|
| `## Thèmes prioritaires — font monter le score` | `prioritaire` | fort bonus |
| `## Signal fort — à privilégier quand ça apparaît` | `signal_fort` | bonus maximal |
| `## Domaines d'application privilégiés` | `domaine` | bonus modéré |
| `## Thèmes secondaires — intéressants, score modéré` | `secondaire` | bonus faible |
| `## Bruit — fait descendre ou disparaître` | `bruit` | forte pénalité |
| `## Posture` | — | ignorée (prose, pas des mots-clés) |

**Correspondance sur préfixe de titre**, pas sur la chaîne exacte : Abdoulaye doit pouvoir reformuler la fin d'un titre sans casser le parseur. Une section inconnue est ignorée avec un avertissement, jamais une erreur.

Extraction des mots-clés dans une section : les lignes de liste (`- ...`) et les termes en gras (`**...**`) qui introduisent un thème. Les commentaires en italique entre parenthèses sont de la prose — les exclure.

### Pondérations en configuration, pas en dur

AC4 exige que modifier le profil change le classement sans toucher au code. Les pondérations elles-mêmes doivent suivre la même règle : les déclarer dans `config/scoring.yaml` (ou une section dédiée du profil), avec des valeurs par défaut si le fichier est absent. Coder `PRIORITAIRE = 10` en dur violerait AD-3 au même titre qu'une source codée en dur.

### Leçons de la Story 1.3 — à ne pas répéter

La revue de la Story 1.3 a trouvé quatre défauts dont trois sont directement transposables ici :

1. **Ne jamais lever hors de l'isolation de panne.** `normaliser_url` levait sur une URL malformée et faisait perdre la nuit entière. Le chargement du profil et le scoring s'exécutent au même endroit du pipeline — après la boucle protégée par source. Un profil malformé doit dégrader, pas planter.
2. **Tester le chemin réel, pas seulement l'unité.** Un audit par mutation a montré que 70 tests verts ne détectaient ni des priorités vidées, ni un dédoublonnage entièrement court-circuité, parce que tous appelaient la fonction en direct sans passer par `sources.yaml`. **Prévoir dès l'écriture des tests qui partent de `config/profil.md` et traversent `collecter()`.**
3. **Le rapport ne doit jamais annoncer un tri qu'il n'a pas fait.** Une source entièrement absorbée passait pour saine. Ici : si le scoring écarte massivement, cela doit être visible dans le récapitulatif, pas déductible.
4. **Départage stable.** Le dédoublonnage donnait des résultats variables selon l'ordre d'entrée. À score égal, l'ordre doit être déterministe.

### Structure de fichiers

```text
config/
  profil.md              # NOUVEAU — profil vivant, édité par l'utilisateur
  scoring.yaml           # NOUVEAU — pondérations par catégorie
  sources.yaml           # MODIFIÉ — seuil_signal + mapping.signal sur hf-daily-papers
src/veille/
  models.py              # MODIFIÉ — champ `signal` optionnel (cf. amendement AD-4)
  config.py              # MODIFIÉ — champ `seuil_signal`
  connectors/json_connector.py  # MODIFIÉ — extraction du signal
  profil.py              # NOUVEAU — chargement et analyse du profil
  filter.py              # NOUVEAU — seuil de signal, scoring, classement
  collect.py             # MODIFIÉ — brancher le filtrage après le dédoublonnage
tests/
  fixtures/hf_daily_papers_votes.json  # NOUVEAU — votes variés pour éprouver le seuil
  test_profil.py         # NOUVEAU
  test_filter.py         # NOUVEAU
  test_scoring_integration.py  # NOUVEAU — chemin réel config → classement
  test_socle_reel.py     # MODIFIÉ — garde-fou sur profil.md et les seuils
```

`filter.py` est prévu par la Structural Seed pour couvrir FR-4/5/6. Cette story livre **FR-4 et FR-5** ; les quotas (FR-6) arrivent en Story 1.5. Ne pas anticiper.

### État actuel du code à ne pas casser

`collecter()` (`src/veille/collect.py`) enchaîne aujourd'hui : collecte par source → dédoublonnage → rapport. Le classement s'insère **après le dédoublonnage** — inutile de scorer des doublons.

`ResultatCollecte` porte `items`, `rapports` (par source) et `dedoublonnage`. Y ajouter le compte-rendu du scoring sans casser les appelants existants : `run()` doit continuer de retourner `list[Item]`.

⚠️ **`RapportSource.nb_retenus` compte la contribution après dédoublonnage.** Si le scoring écarte aussi, ce compte devient ambigu — décider explicitement ce qu'il désigne et le documenter, plutôt que de laisser deux sens coexister.

### Testing Standards

- `pytest`, via `uv run pytest`. Aucun appel réseau.
- **Tests d'intégration obligatoires** depuis `config/profil.md` réel (voir leçon 2 ci-dessus).
- **Audit par mutation en Task 6** : la suite doit échouer quand on neutralise les pondérations, inverse le signe du bruit, ou court-circuite le classement.
- Un garde-fou sur le profil réel dans `tests/test_socle_reel.py` : le fichier existe, ses sections attendues sont présentes, et il produit des mots-clés non vides.

### References

- [Source: epics.md#Story-1.4] — story d'origine et critères d'acceptation
- [Source: prd.md#FR-5] — scoring par pertinence au profil
- [Source: ARCHITECTURE-SPINE.md#AD-3] — sources et profil en configuration, jamais en code
- [Source: ARCHITECTURE-SPINE.md#AD-7] — frontière LLM unique, réservée aux accroches
- [Source: ARCHITECTURE-SPINE.md#Structural-Seed] — `filter.py` couvre FR-4/5/6
- [Source: 1-3-dedoublonnage.md#Review-Findings] — les quatre leçons transposées ci-dessus
- [Source: profil-draft.md] — contenu du profil, co-écrit avec Abdoulaye le 2026-07-24

## Dev Agent Record

### Agent Model Used

Implémentation : Claude Sonnet 5 (`claude-sonnet-5`), via le skill `bmad-dev-story`.
Revue de code : Claude Opus 5 (`claude-opus-5`), via le skill `bmad-code-review` — trois couches adversariales parallèles (Blind Hunter, Edge Case Hunter, Acceptance Auditor), conformément à la recommandation de relire avec un modèle différent de celui qui a écrit le code.

### Change Log

| Date | Passage | Résumé |
|---|---|---|
| 2026-08-27 | Implémentation | Tasks 0 à 6 : champ `signal`, profil en configuration, seuil de signal, scoring lexical, classement, branchement dans `collecter()`. 147 tests. Statut `review`. |
| 2026-08-28 | Revue de code | 24 findings triés : 6 décisions tranchées, 20 correctifs appliqués, 3 reportés, 1 rejeté. **AC5 rétabli** (il n'était pas satisfait), 2 plantages hors isolation de panne corrigés, audit par mutation refait configuration comprise (9 mutants tués), Dev Agent Record rectifié. 189 tests. Statut `done`. |

### Debug Log References

Aucun échec de test irrécupérable en cours de route. Audit par mutation (Task 6) journalisé dans les Tasks/Subtasks ci-dessus avec le nombre d'échecs par mutant.

### Completion Notes List

> **Second passage — après revue de code du 2026-08-28.** La revue a établi que
> l'**AC5 n'était pas satisfait** (6 des 14 mots-clés de bruit étaient des phrases
> introuvables dans un article : une levée de fonds obtenait +2 au lieu d'être
> écartée), que deux chemins d'erreur levaient **hors de l'isolation de panne**
> — au prix de la nuit entière — et que l'audit par mutation initial avait ignoré
> la configuration. Les notes ci-dessous intègrent les 20 correctifs appliqués.

- Amendement AD-4 (signal comme 9ᵉ champ optionnel d'`Item`) tranché et acté dans `ARCHITECTURE-SPINE.md` avant le début de la Task 0, conformément au garde-fou de la story.
- Pipeline après revue : collecte → **seuil de signal** → dédoublonnage → **scoring par profil**. Le seuil précède désormais le dédoublonnage : étant déclaré *par source*, il doit juger chaque item sur le seuil de la sienne, sans quoi l'élection d'un gagnant pouvait faire disparaître un article auquel aucun seuil ne s'appliquait. `filter.py` couvre FR-4 et FR-5 ; les quotas (FR-6) restent hors périmètre pour la Story 1.5.
- **Règles de cumul du score** (tranchées en revue) : un thème ne compte qu'une fois, au poids de sa catégorie la plus lourde ; les mots-clés suivants d'une même catégorie sont atténués (½, ¼…). Sans quoi répéter un terme dans deux sections doublait son poids à l'insu de l'éditeur du profil, et empiler des termes génériques battait le cœur de cible.
- **Correspondance** : frontières de mot rendues conditionnelles (elles ne peuvent s'ancrer que contre un caractère alphanumérique — posées inconditionnellement, elles rendaient inerte tout mot-clé bordé de ponctuation), et `s` final optionnel pour réconcilier un profil rédigé au pluriel avec des titres au singulier.
- **Robustesse de la configuration** : `sources.yaml` et `scoring.yaml` sont édités à la main (AD-3), donc une faute de frappe y est un incident attendu. Les valeurs non numériques, booléennes (`yes` → `True` en YAML) et non finies (`nan`) retombent désormais sur leur défaut avec un avertissement, valeur par valeur. `charger_ponderations` attrape `UnicodeDecodeError`, que sa docstring promettait déjà de ne jamais laisser filer.
- **Chemins de configuration** résolus depuis la racine du dépôt et non le répertoire courant : le pipeline est destiné au planificateur de tâches (Epic 3), où le CWD n'est pas garanti — un profil introuvable désactivait tout le classement en silence. Le récapitulatif porte maintenant un avertissement « Profil neutre » explicite.
- **Observabilité (AC7)** : les rapports de signal et de classement nomment les sources écartées, sur le modèle du dédoublonnage ; l'en-tête rend le total collecté dès qu'il diffère du total retenu ; et l'alerte « source absorbée » nomme l'étape responsable au lieu d'accuser systématiquement le dédoublonnage.
- **Tests découplés de la production** : un `conftest.py` neutralise le profil et les pondérations par défaut. Éditer `config/profil.md` — ce que la story invite précisément à faire — ne peut plus casser des tests sans rapport. Les tests qui portent sur la configuration livrée la désignent explicitement par son chemin.
- `nb_retenus` (dans `RapportSource`) désigne désormais la contribution finale au digest (après dédoublonnage, seuil de signal *et* scoring), pas seulement la survie au dédoublonnage — ambiguïté explicitement levée par les Dev Notes.
- `config/profil.md` copie le contenu réel co-écrit avec Abdoulaye (`profil-draft.md`) ; le fichier source reste en artefact de planification.
- Pondérations déclarées en configuration (`config/scoring.yaml`), avec repli sur des valeurs par défaut si le fichier est absent/illisible/malformé — jamais codées en dur (AD-3).
- Correspondance par mot entier et insensible aux accents/casse ; testée explicitement contre les faux positifs documentés dans les Dev Notes (`ia`/`media`, `rag`/`fragment`), y compris après l'ajout du `s` optionnel.
- Départage stable à score égal obtenu par un tri Python stable (`list.sort(reverse=True)`), sans clé de désambiguïsation supplémentaire — pas d'ordre aléatoire.
- **Parseur de profil durci** contre les éditions manuelles plausibles d'un fichier utilisateur : apostrophe typographique dans un titre de section (qui faisait perdre la section entière), titres `###`, puces `*`/`+`/numérotées, tiret demi-cadratin, aside italique à parenthèse imbriquée, commentaires HTML, ponctuation de bordure (`Qwen…`), tiret isolé, et réinitialisation de catégorie sur tout titre.
- Audit par mutation refait de bout en bout, **configuration comprise** : 9 mutants, tous tués. Détail dans la Task 6.
- Exécution réelle de plausibilité refaite par le chemin de production, sur fixtures locales (aucun appel réseau) : voir la note rectificative en Task 6.
- **189 tests passent** (102 avant cette story, 147 au premier passage, +42 ajoutés en revue — dont la fixture `hf_daily_papers_votes.json` qui manquait et qui éprouve enfin le seuil **des deux côtés**).

### File List

**Code :**
- `src/veille/models.py` — modifié : champ `signal: float | None = None` sur `Item`
- `src/veille/config.py` — modifié : champ `seuil_signal: float | None = None` sur `SourceConfig` ; **(revue)** `chemin_config()` résolu depuis la racine du dépôt, validation numérique (`to_float_fini`, `_normaliser`)
- `src/veille/connectors/json_connector.py` — modifié : extraction et conversion du signal (`_to_signal`)
- `src/veille/profil.py` — nouveau : `Profil`, `charger_profil`, `sans_accents`
- `src/veille/filter.py` — nouveau : `filtrer_par_signal`, `Ponderations`, `charger_ponderations`, `Score`, `scorer`, `ItemScore`, `classer`, `RapportClassement`, `rapport_classement`
- `src/veille/collect.py` — modifié : branchement du filtrage par signal et du classement après le dédoublonnage dans `collecter()` ; `ResultatCollecte` étendu (`filtrage_signal`, `classement`) ; `nb_retenus` redéfini

**Configuration :**
- `config/profil.md` — nouveau : profil vivant (copié depuis `profil-draft.md`)
- `config/scoring.yaml` — nouveau : pondérations du scoring
- `config/sources.yaml` — modifié : `mapping.signal` et `seuil_signal: 15` sur `hf-daily-papers`

**Tests :**
- `tests/conftest.py` — **nouveau (revue)** : neutralise profil et pondérations par défaut, pour qu'aucun test ne se couple à la configuration de production
- `tests/fixtures/hf_daily_papers_votes.json` — **nouveau (revue)** : votes 45/24/15/11/3/0, pour éprouver le seuil des deux côtés
- `tests/test_models.py` — modifié : tests du champ `signal`
- `tests/test_json_connector.py` — modifié : tests d'extraction du signal
- `tests/test_config.py` — **modifié (revue)** : validation de `seuil_signal` (non numérique, booléen, `nan`)
- `tests/test_profil.py` — nouveau ; **étendu en revue** : robustesse aux éditions manuelles, garde-fous AC5 sur la section Bruit réelle
- `tests/test_filter.py` — nouveau ; **étendu en revue** : règles de cumul, correspondance singulier/pluriel et ponctuation, robustesse du chargement des pondérations, ventilation par source
- `tests/test_socle_reel.py` — **modifié (revue)** : garde-fous sur `seuil_signal`, `mapping.signal` et l'existence de `scoring.yaml`
- `tests/test_collecte_integration.py` — modifié : `TestScoringEffectif`, chemin réel `config/profil.md` → `collecter()` ; **étendu en revue** : `TestSeuilDeSignalSurLeSocle`, `TestOrdreDuPipeline`, effet réel de `scoring.yaml`, signalement du profil neutre

**Documentation / architecture :**
- `_bmad-output/planning-artifacts/architecture/architecture-agent-veille-emploi-ia-2026-07-24/ARCHITECTURE-SPINE.md` — modifié : amendement AD-4
- `_bmad-output/implementation-artifacts/deferred-work.md` — **modifié (revue)** : 3 éléments reportés à la Story 1.8
