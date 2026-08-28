---
title: Agent de veille IA
status: final
created: 2026-07-24
updated: 2026-07-24
---

# PRD : Agent de veille IA
*Titre de travail — à confirmer.*

## Sources amont

- Brief figé : `../briefs/brief-agent-veille-emploi-ia-2026-07-20/brief.md` (status: ready)
- Addendum technique : `../briefs/brief-agent-veille-emploi-ia-2026-07-20/addendum.md` — socle de ~280 sources vérifiées, URL de flux, stratégies de filtrage, pièges, démarches admin. **Le PRD ne duplique pas l'addendum : il s'y réfère.**

## 0. Objet du document

Ce PRD s'adresse d'abord à Abdoulaye (seul utilisateur et constructeur), puis à Winston pour l'architecture et au découpage en epics/stories. Il décrit *ce que* l'agent fait — les capacités, pas leur implémentation. Les choix techniques (langage, bibliothèques, transport) vivent dans l'addendum et seront tranchés à l'architecture. Vocabulaire ancré par le Glossaire (§3) ; fonctionnalités groupées avec exigences (FR) numérotées globalement ; hypothèses taguées `[HYPOTHÈSE]` en ligne et indexées en §9.

## 1. Vision

Un agent qui produit chaque nuit une page de veille — IA, data, informatique — prête au réveil sur le téléphone d'Abdoulaye. Une seule URL, un seul favori, à jour sans qu'il lance quoi que ce soit. La page n'est pas un flux brut : c'est une couche d'aiguillage qui trie l'écosystème (des centaines de sources) jusqu'à huit items par jour, répartis en trois registres — apprendre, suivre l'actualité, rester employable — et pointe vers l'original pour qui veut approfondir.

Le produit répond à un échec précis et documenté : Abdoulaye s'était abonné à un digest quotidien (Ben's Bites) et l'a abandonné. Pas par manque de discipline — ses podcasts, plus exigeants, ont tenu — mais par manque d'ancrage : une newsletter est un moment à créer chaque jour, un podcast se greffe sur un trajet existant. Toute la conception découle de là : la page doit coûter le moins d'effort possible à consulter, et zéro effort à produire.

La valeur de l'agent est exactement ce qu'il apporte qu'Abdoulaye n'a pas déjà. Ses cinq ou six podcasts actuels sont tous de l'actualité grand public francophone ; l'agent ouvre l'ingénierie, la recherche, les communautés techniques, et l'anglais restitué en français. Français et anglais sont traités à égalité.

## 2. Utilisateur cible

### 2.1 Jobs To Be Done

- **Fonctionnel** — savoir chaque jour, en moins de cinq minutes, ce qui mérite mon attention dans l'IA/data/info, sans ouvrir dix apps ni lire l'anglais toute la matinée.
- **Fonctionnel** — combler l'écart entre mon profil de Data Scientist junior et les postes que je vise, en repérant ce qu'il faut apprendre avant novembre 2026.
- **Émotionnel** — ne plus culpabiliser de « rater » l'actualité IA ; avoir la conscience tranquille d'un tri fiable fait à ma place.
- **Social** — avoir de quoi parler avec justesse en entretien et entre pairs, au bon niveau technique.
- **Constructeur** — c'est aussi mon projet : un système agentique réel, que j'utilise tous les jours, qui vaut mieux qu'un projet d'école sur un CV.

### 2.2 Non-utilisateurs (v1)

- Toute autre personne qu'Abdoulaye. Pas de multi-utilisateur, pas de comptes, pas d'interface d'administration. L'architecture reste *orientable* (le profil qui pilote le filtrage est une donnée, pas du code en dur), mais l'ouverture à d'autres est explicitement hors v1.

### 2.3 Parcours utilisateur

- **UJ-1. Abdoulaye écoute sa veille en partant au travail.**
  Abdoulaye, Data Scientist junior à Dakar, sort de chez lui à 7h38, AirPods aux oreilles. La page a été générée la nuit précédente. Il ouvre son favori : trois sections courtes, huit items maximum, chacun avec une accroche en français et un lien. Il lit en diagonale « Apprendre », repère un papier sur le reranking RAG qui touche à son propre projet, garde l'onglet ouvert pour le soir. Il descend, voit dans « Pour le métier » une compétition Kaggle NLP. Trente secondes, il sait ce qui compte aujourd'hui. **Cas limite :** nuit sans génération réussie → la page affiche la date de dernière mise à jour réussie et un bandeau honnête « pas de mise à jour cette nuit », plutôt qu'une page vide ou périmée présentée comme fraîche.

- **UJ-2. Le dimanche, l'agent lui propose une nouvelle source.**
  Une fois par semaine `[HYPOTHÈSE: hebdomadaire, le dimanche]`, une section « À découvrir » apparaît en bas de page : un podcast ou une newsletter hors de son socle, avec une phrase sur ce qu'il apporte. Abdoulaye peut l'ignorer, ou décider de l'ajouter à ses sources suivies. La veille s'élargit à son rythme, sans qu'il ait à chercher.

## 3. Glossaire

- **Digest** — la page de veille produite pour une date donnée. Un digest = une génération nocturne = une entrée d'archive.
- **Source** — un flux d'où l'agent tire du contenu (flux RSS, API, page scrapée). Identifiée par une URL et des métadonnées (langue, type, registre, état).
- **Item** — une unité de contenu candidate issue d'une Source (un article, un épisode, un papier, une release). Après filtrage, un Item retenu devient une Entrée du Digest.
- **Entrée** — un Item sélectionné, enrichi de son Accroche et de son lien, placé dans une Section du Digest.
- **Accroche** — texte court en français rédigé par l'agent pour une Entrée : de quoi comprendre l'enjeu et décider d'aller à l'original. Ni titre brut, ni résumé complet.
- **Section** — un des trois registres du Digest : **Apprendre**, **Ce qui bouge**, **Pour le métier**. Chacune a un Quota.
- **Quota** — nombre cible d'Entrées par Section (≈3 / ≈3 / ≈2). Plafond, pas plancher.
- **Registre** — l'intention d'une Section (technique / actualité / employabilité). Chaque Source est rattachée à un Registre par défaut.
- **Score de pertinence** — valeur attribuée à un Item pour le classer, combinant signal de la Source (votes, points) et proximité avec le Profil.
- **Profil** — description des centres d'intérêt et objectifs d'Abdoulaye qui pilote le filtrage. Donnée éditable, non codée en dur.
- **Archive** — collection Markdown versionnée des Digests passés, cherchable, une entrée par jour.
- **État d'une Source** — `active`, `suspecte` (fraîcheur douteuse) ou `en sommeil` (silencieuse au-delà du seuil).

## 4. Fonctionnalités

### 4.1 Collecte multi-sources

**Description :** chaque nuit, l'agent interroge le socle de Sources actives et récupère les Items publiés depuis la dernière exécution. Il gère des Sources hétérogènes (RSS, API JSON, pages scrapées) derrière une interface uniforme. La collecte est tolérante à la panne : une Source qui échoue (timeout, 403, 429) est ignorée pour cette nuit sans interrompre les autres. Réalise UJ-1.

**Functional Requirements:**

#### FR-1 : Collecter depuis des sources hétérogènes
L'agent peut récupérer les Items d'une Source quel que soit son type (RSS, API, scraping), via un connecteur par type.

**Conséquences (testables) :**
- Une Source RSS, une Source API (HF Daily Papers) et une Source scrapée (page news Anthropic) produisent toutes des Items dans le même format interne.
- Le socle v1 compte 15 à 20 Sources `[HYPOTHÈSE: liste initiale proposée en §6.1]`, extensible sans modifier le code de collecte (ajout par configuration).

#### FR-2 : Tolérer les échecs de source
L'agent continue la collecte si une Source échoue, et journalise l'échec.

**Conséquences (testables) :**
- Une Source renvoyant 403/429/timeout n'interrompt pas la génération ; les autres Sources sont collectées.
- Un backoff est appliqué aux Sources sensibles au débit (ex. Reddit si activé) ; un échec est enregistré avec sa cause.
- Si plus de `[HYPOTHÈSE: 50 %]` des Sources échouent la même nuit, le Digest est quand même produit mais signale l'anomalie.

#### FR-3 : Dédoublonner entre sources
L'agent reconnaît qu'un même sujet couvert par plusieurs Sources ne doit apparaître qu'une fois.

**Conséquences (testables) :**
- Deux Items pointant vers la même URL cible produisent au plus une Entrée.
- Une même annonce reprise par plusieurs médias `[HYPOTHÈSE: détectée par similarité de titre/URL]` produit une seule Entrée, celle de la Source la mieux classée.

**Notes :** `[NOTE FOR PM]` la robustesse du dédoublonnage sémantique (au-delà de l'URL identique) est un point à valider à l'architecture — commencer simple (URL/GUID), affiner si le bruit le justifie.

### 4.2 Filtrage et scoring

**Description :** le cœur du produit. L'agent réduit des dizaines à des centaines d'Items candidats à huit Entrées maximum. Il applique d'abord des seuils de signal propres à chaque Source (votes, points), puis un Score de pertinence par rapport au Profil, puis les Quotas par Section. Le filtrage est agressif par conception : mieux vaut une page maigre qu'une page bruyante. Réalise UJ-1.

**Functional Requirements:**

#### FR-4 : Filtrer par signal de source
L'agent applique un seuil de signal spécifique avant de considérer un Item.

**Conséquences (testables) :**
- Les papiers HF Daily Papers sous le seuil de votes (`[HYPOTHÈSE: upvotes ≥ 15, ou seuil dynamique max(10, p80 du jour)]`) sont écartés.
- Les items Hacker News sous `[HYPOTHÈSE: 150 points]` sont écartés.
- arXiv n'est jamais collecté en flux brut ; il ne sert qu'à enrichir un Item déjà retenu ou sur requête ciblée.

#### FR-5 : Scorer par pertinence au profil
L'agent classe les Items retenus selon leur proximité avec le Profil.

**Conséquences (testables) :**
- Le Profil est un fichier éditable (thèmes, mots-clés, objectifs) ; le modifier change le classement sans toucher au code.
- À volume égal, un Item proche du Profil (ex. RAG, retrieval, MLOps) est classé devant un Item générique.

#### FR-6 : Répartir par quotas de section
L'agent remplit chaque Section jusqu'à son Quota, sans le dépasser.

**Conséquences (testables) :**
- Le Digest contient au plus ≈8 Entrées : ≈3 Apprendre, ≈3 Ce qui bouge, ≈2 Pour le métier.
- Les Quotas sont configurables sans modifier le code.
- Un jour creux, une Section peut contenir moins que son Quota — **jamais de remplissage** : pas de contenu de fond injecté pour atteindre le Quota.

**Out of Scope :**
- Baisser automatiquement les seuils un jour creux pour « remplir » (explicitement rejeté — cf. §5).

### 4.3 Génération des accroches en français

**Description :** pour chaque Entrée, l'agent rédige une Accroche en français — quelle que soit la langue de la Source. L'Accroche donne l'enjeu et invite à l'original ; elle ne le remplace pas. Certaines Entrées portent une recommandation explicite (« celui-là, écoute-le »). Réalise UJ-1.

**Functional Requirements:**

#### FR-7 : Rédiger une accroche par entrée
L'agent produit une Accroche courte en français pour chaque Entrée, à partir du contenu de l'Item.

**Conséquences (testables) :**
- L'Accroche fait `[HYPOTHÈSE: 1 à 3 phrases]`, en français, même pour une Source anglophone.
- Chaque Entrée affiche sa Source et un lien direct vers l'original.
- La génération utilise l'API Claude `[HYPOTHÈSE: modèle éco type Haiku pour le coût]` ; le champ `tldr` de Semantic Scholar sert d'appui pour les papiers.

#### FR-8 : Signaler les entrées à prioriser
L'agent met en avant les Entrées qui méritent le détour.

**Conséquences (testables) :**
- Au moins `[HYPOTHÈSE: une]` Entrée par Digest porte une marque de recommandation quand le contenu le justifie.
- Aucune recommandation forcée un jour faible.

**Feature-specific NFRs:**
- Coût de génération maîtrisé : cible `[HYPOTHÈSE: < 2 €/mois]` à volume nominal (≈8 accroches/jour).

### 4.4 Publication de la page et archive

**Description :** l'agent publie le Digest en une page HTML à URL stable, lisible sur mobile, et l'ajoute à l'Archive Markdown versionnée. La page est la vitrine (un favori, toujours la même URL) ; l'Archive est la mémoire (cherchable, versionnée). Réalise UJ-1.

**Functional Requirements:**

#### FR-9 : Publier une page à URL stable
L'agent publie le Digest du jour à une URL qui ne change pas d'un jour à l'autre.

**Conséquences (testables) :**
- Le même favori affiche toujours le dernier Digest.
- La page est lisible sur mobile (mise en page responsive), les trois Sections visibles sans effort.
- La page indique la date/heure de génération réussie ; en cas d'échec nocturne, un bandeau honnête l'affiche (cf. UJ-1 cas limite).

#### FR-10 : Archiver chaque digest en Markdown
L'agent écrit chaque Digest dans l'Archive versionnée.

**Conséquences (testables) :**
- Un fichier Markdown par jour, horodaté, committé.
- L'Archive est cherchable par texte (grep/recherche fichier) sur l'ensemble de l'historique.

### 4.5 Génération nocturne automatique

**Description :** tout le pipeline (collecte → filtrage → accroches → publication) tourne sans intervention, la veille au soir, pour que la page soit prête avant 7h38. Réalise UJ-1.

**Functional Requirements:**

#### FR-11 : S'exécuter automatiquement chaque nuit
Le pipeline se déclenche seul, une fois par nuit.

**Conséquences (testables) :**
- Déclenchement via le planificateur de tâches Windows sur le PC d'Abdoulaye `[HYPOTHÈSE: exécution en soirée, ex. 22h heure de Dakar, pour capter la journée complète de votes et laisser une marge de reprise]`.
- Le Digest est disponible avant 7h38, la génération ayant eu lieu la veille.
- En cas d'échec, une reprise est tentée `[HYPOTHÈSE: nouvelle tentative automatique dans la nuit]` ; le dernier Digest réussi reste affiché entre-temps.

**Notes :** `[NOTE FOR PM]` dépendance au PC allumé la nuit. Si contrainte trop forte à l'usage, bascule vers une exécution cloud gratuite (GitHub Actions) — envisagée puis écartée en v1 pour la simplicité, à garder comme repli documenté.

### 4.6 Surveillance de la santé des sources

**Description :** l'agent surveille ses propres Sources, parce qu'un flux qui répond « 200 OK » peut servir des dates factices, zéro item, ou du contenu périmé. Sans cela, le socle pourrit en silence. Réalise UJ-1 (indirectement : garantit que la page reste fiable dans la durée).

**Functional Requirements:**

#### FR-12 : Détecter les sources défaillantes
L'agent évalue périodiquement la fraîcheur de chaque Source et marque son État.

**Conséquences (testables) :**
- Une Source dont l'item le plus récent dépasse `[HYPOTHÈSE: 30 jours]` passe en `suspecte`.
- Une Source dont plusieurs items partagent la même date à la minute près est marquée `suspecte` (cas ActuIA).
- Une Source silencieuse au-delà de `[HYPOTHÈSE: 3 mois]` passe `en sommeil` et n'est plus interrogée jusqu'à révision.
- Le contrôle tourne `[HYPOTHÈSE: une fois par semaine]`.

#### FR-13 : Signaler l'état à l'utilisateur
L'agent rend visibles les Sources suspectes ou en sommeil.

**Conséquences (testables) :**
- Un récapitulatif `[HYPOTHÈSE: hebdomadaire, en pied de page ou fichier dédié]` liste les Sources passées `suspecte`/`en sommeil`.

### 4.7 Découverte de nouvelles sources

**Description :** périodiquement, l'agent propose une Source hors du socle, pour que la veille s'élargisse au lieu de tourner en rond. Réalise UJ-2.

**Functional Requirements:**

#### FR-14 : Proposer de nouvelles sources
L'agent suggère périodiquement une Source candidate, avec une justification.

**Conséquences (testables) :**
- `[HYPOTHÈSE: une fois par semaine]`, une section « À découvrir » présente au moins une Source candidate (podcast, newsletter, blog) absente du socle, en français ou anglais, avec une phrase sur son apport.
- Abdoulaye peut adopter une Source proposée (elle rejoint le socle) ou l'ignorer `[HYPOTHÈSE: mécanisme d'adoption à définir — édition manuelle du fichier de sources en v1]`.
- Une Source proposée est vérifiée active (flux valide, publication récente) avant d'être suggérée.

## 5. Non-Goals (explicites)

- **Pas de digest audio en v1.** Reporté (pas de matériel pour un TTS local, budget quasi-nul). Repli documenté : Kokoro sur CPU. `[NOTE FOR PM]` émotionnellement important — l'audio est le format de confort réel d'Abdoulaye ; à revisiter en v2.
- **Pas d'agent de recherche d'emploi.** Abandonné le 2026-07-23 ; besoin traité en mode assisté. Matière conservée dans l'addendum du brief.
- **Pas de multi-utilisateur, pas de comptes, pas d'interface web d'administration.**
- **Pas d'envoi par email.**
- **Pas de transcription intégrale des podcasts** (coût de calcul disproportionné) ; l'agent exploite titres, descriptions et notes d'épisode des flux.
- **Pas de remplissage les jours creux** : la page reflète honnêtement ce qui existe.
- **Pas de collecte en violation de CGU** (LinkedIn, emploisenegal.com, Wellfound, etc.).

## 6. Périmètre MVP

### 6.1 Dans le périmètre

- Collecte d'un socle resserré de 15-20 Sources à fort signal. Proposition `[HYPOTHÈSE]` :
  - **Apprendre :** HF Daily Papers (API), GitHub releases.atom (panier de ~10 dépôts compté comme 1 Source), 1-2 blogs de praticiens (Eugene Yan, Simon Willison), 1 podcast d'ingénierie (DataGen ou The AI Engineer Podcast), 1 chaîne vidéo (StatQuest ou 3Blue1Brown).
  - **Ce qui bouge :** OpenAI news, Anthropic (via miroir Turing + secours scraping), Hugging Face blog, Brief IA (FR), Hacker News (Algolia, seuil points), TLDR AI.
  - **Pour le métier :** Kaggle competitions (API, clé gratuite), 1 source data FR (Décideo ou Le Monde Informatique section IA).
- Filtrage par signal + scoring par Profil + Quotas par Section.
- Accroches françaises via API Claude.
- Page HTML à URL stable, responsive, + Archive Markdown versionnée.
- Génération nocturne planifiée en local, avec bandeau d'échec honnête.
- Surveillance de fraîcheur des Sources + mise en sommeil.
- Découverte hebdomadaire d'une nouvelle Source.

### 6.2 Hors périmètre MVP

- Reddit — mis en attente (démarche OAuth non aboutie, 2-4 semaines). Hacker News + Lobsters couvrent le besoin communautaire sans authentification. `[NOTE FOR PM]` réactivable dès obtention de la clé.
- Sources à fort volume nécessitant un filtrage lourd (arXiv en balayage, TechCrunch, LeBigData) — reportées après rodage du pipeline.
- Conférences (JSON `virtual/data`) — ingestion ponctuelle, hors cycle quotidien ; v2.
- Dédoublonnage sémantique avancé — v1 s'en tient à URL/GUID.
- Adoption automatisée des sources découvertes — v1 = édition manuelle du fichier de sources.
- Digest audio, agent emploi, multi-utilisateur — cf. Non-Goals.

## 7. Métriques de succès

**Primaire**
- **SM-1 : Non-abandon.** La page est encore consultée après 6 semaines d'usage — le seuil où Ben's Bites avait décroché. Valide la finalité de tout le produit (FR-9, FR-11). Mesure : `[HYPOTHÈSE: nombre de jours d'ouverture de la page sur les 7 derniers jours, relevé manuellement ou via un compteur de visites simple ; succès = usage ≥ 4 jours/semaine à S+6]`.

**Secondaires**
- **SM-2 : Utilité quotidienne.** Au moins une Entrée par jour donne envie d'aller à l'original. Valide FR-7, FR-8. Mesure : `[HYPOTHÈSE: auto-évaluation hebdomadaire, ou compteur de clics sortants si instrumenté]`.
- **SM-3 : Fiabilité de livraison.** Page à jour avant 7h38, ≥ `[HYPOTHÈSE: 6 jours/7]`. Valide FR-11.
- **SM-4 : Fraîcheur du socle.** Aucune Source `suspecte` non traitée depuis plus de `[HYPOTHÈSE: 2 semaines]`. Valide FR-12.
- **SM-5 : Élargissement.** Au moins une nouvelle Source adoptée par mois. Valide FR-14.

**Contre-métriques (à ne pas optimiser)**
- **SM-C1 : Volume d'Entrées.** Ne pas maximiser le nombre d'items par Digest. Contrebalance SM-2 : gonfler la page tue le non-abandon (SM-1). Un jour à 3 Entrées honnêtes vaut mieux qu'un jour à 8 gonflées.
- **SM-C2 : Temps passé sur la page.** Ne pas chercher à augmenter le temps de lecture. Contrebalance SM-2 : le produit réussit s'il fait gagner du temps, pas s'il en consomme. Cible implicite : lecture sous 5 minutes.

## 8. Questions ouvertes

1. Heure exacte de génération nocturne, compte tenu du fuseau de Dakar (UTC+0) et de l'accumulation des votes HF (minuit UTC). `[HYPOTHÈSE: 22h locale]` à valider.
2. Fréquence réelle de la découverte de sources (FR-14) et de la surveillance de fraîcheur (FR-12) — hebdomadaire posé par hypothèse.
3. Mécanisme concret d'« adoption » d'une source découverte : édition manuelle en v1, mais quelle ergonomie ?
4. Comment mesurer SM-1 sans instrumentation lourde ? Compteur de visites minimal vs. auto-relevé.
5. Le seuil de votes HF doit-il être fixe ou dynamique ? (les volumes gonflent le lundi et en période pré-deadline de conférences.)
6. Contenu exact du Profil (§ Glossaire) : quels thèmes, quels mots-clés au départ ? À co-écrire avec Abdoulaye.
7. Gestion des secrets (clé API Claude, clés Kaggle/Semantic Scholar) sur une machine locale — à cadrer à l'architecture.

## 9. Index des hypothèses

- §2.3 UJ-2 — découverte hebdomadaire, le dimanche.
- §4.1 FR-1 — socle initial de 15-20 sources ; liste en §6.1.
- §4.1 FR-2 — seuil d'anomalie à 50 % de sources en échec.
- §4.1 FR-3 — dédoublonnage par similarité titre/URL.
- §4.2 FR-4 — seuils HF (upvotes ≥ 15 ou dynamique) et HN (150 points).
- §4.3 FR-7 — accroche de 1 à 3 phrases ; modèle éco type Haiku.
- §4.3 FR-8 — au moins une recommandation par digest quand justifié.
- §4.3 NFR — coût < 2 €/mois.
- §4.5 FR-11 — exécution ~22h locale ; reprise automatique dans la nuit.
- §4.6 FR-12 — fraîcheur 30 jours (suspecte), 3 mois (sommeil), contrôle hebdomadaire.
- §4.7 FR-14 — proposition hebdomadaire ; adoption par édition manuelle en v1.
- §6.1 — composition précise du socle v1.
- §7 SM-1 à SM-5 — cibles chiffrées et méthodes de mesure.
