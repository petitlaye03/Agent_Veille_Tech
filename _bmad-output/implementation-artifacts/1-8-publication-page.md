---
baseline_commit: 7b840d1
---

# Story 1.8: Publier une page à URL fixe, jolie et lisible sur mobile

Status: done

## Story

As a Abdoulaye,
I want consulter mon digest du jour sur une page à URL stable, agréable à lire sur mon téléphone,
so that je l'ouvre chaque matin sans réfléchir.

## Acceptance Criteria

1. **[FR-9]** Étant donné une liste d'`Entree` (Stories 1.6/1.7), regroupées par registre (`item.registre`), `render.rendre(entrees, date_generation)` produit une page HTML unique qui présente les trois sections dans l'ordre `apprendre` → `ce_qui_bouge` → `pour_le_metier` (même ordre que `filter.CHAMPS_QUOTAS`) ; chaque entrée affiche titre, accroche et lien vers l'`url` d'origine.
2. **[UX-DR1, NFR6]** La page embarque une palette de couleurs et une typographie explicites (CSS), jamais le rendu par défaut du navigateur.
3. **[UX-DR3, NFR4]** Mise en page mobile-first : `<meta name="viewport" content="width=device-width, initial-scale=1">`, layout à une colonne par défaut.
4. **[UX-DR4]** Thème sombre automatique via `@media (prefers-color-scheme: dark)` dans le CSS embarqué — pas de bascule manuelle (aucun JS de préférence utilisateur, cohérent avec la sobriété UX-DR5).
5. **[FR-9]** La page affiche la date/heure de la dernière génération réussie (UTC = heure de Dakar, cf. convention d'architecture — pas de conversion de fuseau nécessaire).
6. **[FR-9]** La même URL (`index.html`) affiche toujours le dernier digest : la publication **écrase** le fichier existant, jamais un fichier daté (l'archive datée par jour est la Story 1.9, hors périmètre ici).
7. **[FR-8]** Une `Entree.recommandee=True` (Story 1.7) porte une marque visuelle distincte sur la page — au plus une, cohérent avec l'invariant déjà garanti par `marquer_recommandation`.
8. **[Sûreté]** Aucun contenu de source externe (`titre`, `accroche`, `contenu_brut`) n'est jamais rendu non échappé dans le HTML — autoescaping Jinja2 actif **explicitement** (voir Dev Notes, piège du nom de fichier de template), jamais de filtre `|safe` sur ces champs. Referme la dette XSS documentée depuis la Story 1.6 (`docs/rapport-projet.md`, §8).
9. **[Robustesse]** Une liste d'`Entree` vide ne produit ni page cassée ni page vide silencieuse : un message honnête (« rien à signaler aujourd'hui ») est affiché à la place.
10. **[AD-8]** La publication écrit/actualise `index.html` dans un **second dépôt GitHub, public, dédié uniquement à la sortie publiée** (décision actée avec Abdoulaye le 2026-08-28 — le dépôt de code, `Agent_Veille_Tech`, reste privé) — via l'API Contents de GitHub (`PUT /repos/{owner}/{repo}/contents/{path}`), pas un clone local ni un appel `subprocess` à `git`.
11. **[AD-1]** `pipeline.py` devient l'orchestrateur dédié : `collecter()` → `enrichir()` → `marquer_recommandation()` → `rendre()` → `publier()`, un seul point d'entrée (`uv run python -m veille.pipeline`) — résout la tension AD-1 suivie depuis la Story 1.4 (« reporté à la Story 1.8, quand rendu et publication existeront »).
12. **[Dette fermée]** `ResultatCollecte` (`collect.py`) expose désormais `resultats_repartis: list[ItemScore]` (champ additif, ne casse aucun test existant) — ferme la dette « `Score.valeur`/`motifs` calculé puis jeté » documentée depuis la revue de la Story 1.4 et reconduite dans les Dev Notes de la Story 1.7. Sans ce champ, `pipeline.py` n'a aucun moyen de fournir un `classement` à `marquer_recommandation`.
13. **[Dette fermée]** Un `Item.titre` vide se replie sur `accroche` (déjà garantie non vide par `enrichir()`, Story 1.6) pour l'en-tête affiché ; un `Item.url` vide n'émet **aucun lien cliquable** (texte seul, jamais une ancre vers nulle part ni un self-link). Referme la dette « `models.py` ne valide que `date_publication`... à muscler quand la Story 1.8 rendra les champs vides visiblement cassés à l'écran » (`deferred-work.md`).

## Tasks / Subtasks

- [x] Task 1 : Fermer la dette du classement jeté (AC: 12)
  - [x] Ajouter `resultats_repartis: list[ItemScore] = field(default_factory=list)` à `ResultatCollecte` (`src/veille/collect.py`)
  - [x] Le peupler dans `collecter()` avec la variable locale déjà calculée (`resultats_repartis`, ligne où `items = [item_score.item for item_score in resultats_repartis]` est actuellement construite) — ne recalcule rien, expose seulement ce qui existe déjà
  - [x] Tests : le champ est bien peuplé et dans le même ordre que `.items` ; les 25 tests de `test_collecte_integration.py` et les tests de `test_collect.py` restent verts sans modification (champ additif, valeur par défaut `[]`)

- [x] Task 2 : Rendu HTML (AC: 1, 2, 3, 4, 5, 6, 7, 8, 9, 13)
  - [x] `templates/digest.html.j2` — template Jinja2 : structure sémantique, viewport meta tag, CSS embarqué (`<style>`) avec variables de palette + media query `prefers-color-scheme: dark`, section par registre dans l'ordre `CHAMPS_QUOTAS`, badge visuel sur l'entrée `recommandee=True`, état vide géré, pas de lien sur `url` vide
  - [x] `src/veille/render.py` :
    - `LIBELLES_REGISTRE: dict[str, str]` — `{"apprendre": "Apprendre", "ce_qui_bouge": "Ce qui bouge", "pour_le_metier": "Pour le métier"}`, dans l'ordre de `filter.CHAMPS_QUOTAS` (réutilisé, pas redéfini en second ordre parallèle)
    - `_environnement_jinja() -> Environment` — **autoescaping explicite**, voir Dev Notes (piège `.j2`)
    - `rendre(entrees: list[Entree], date_generation: datetime) -> str` — groupe par registre, rend le template, retourne le HTML complet en chaîne ; titre vide → repli sur `entree.accroche` pour l'en-tête ; url vide → pas de balise `<a>` (texte seul)
  - [x] Ajouté la dépendance `jinja2` (`uv add jinja2`, 3.1.6) — déjà dans la stack de l'architecture (§Stack), pas une dépendance hors périmètre
  - [x] Tests (11) : 3 sections dans le bon ordre ; contenu (titre/accroche/lien) présent ; palette/typo non par défaut (présence d'un `<style>` non vide) ; viewport meta tag présent ; media query dark présente ; timestamp présent et correctement formaté ; entrée recommandée porte une marque distincte, les autres non ; **contenu malveillant échappé** (`<script>` dans un titre ressort en `&lt;script&gt;`, jamais exécutable) ; liste vide → message honnête, pas de page cassée ; `titre=""` → l'accroche sert d'en-tête ; `url=""` → aucune balise `<a>` émise pour cette entrée

- [x] Task 3 : Publication (AC: 10)
  - [x] `src/veille/publish.py` :
    - `PUBLISH_REPO = "petitlaye03/agent-veille-tech-digest"` — constante en dur, même précédent que `MODELE` dans `enrich/llm.py`
    - `_jeton() -> str | None` — résolution **à deux niveaux** : `GITHUB_TOKEN` dans `.env` en priorité (nettoyé des espaces, même piège trouvé en revue Story 1.6) ; sinon repli sur `gh auth token` (subprocess capturé, jamais de plantage)
    - `_client() -> httpx.Client | None` — `None` si aucun jeton résolu, avertissement journalisé une seule fois
    - `publier(html, client=None) -> bool` — `PUT` vers l'API Contents (`GET` préalable pour le `sha`, absence de fichier → création) ; isolation totale, ne lève jamais, `False` sur échec ; un client fourni explicitement n'est jamais fermé par cette fonction
  - [x] Tests (11) : client HTTP simulé (`_FakeClient`/`_FakeResponse`), résolution de jeton monkeypatchée, **aucun appel réseau/subprocess réel**. Cas couverts : création, mise à jour (sha transmis), jeton absent des deux voies, échec réseau (`httpx.ConnectError`), réponse HTTP en erreur (500), priorité env > `gh auth token`, jeton blanc traité comme absent, client fourni non fermé

- [x] Task 4 : Orchestrateur (AC: 11)
  - [x] `src/veille/pipeline.py` : `executer(sources_path=None, profil_path=None, scoring_path=None, quotas_path=None, llm_client=None, publish_client=None) -> bool` — enchaîne `collect.collecter()` → `enrich.llm.enrichir()` → `enrich.llm.marquer_recommandation(entrees, resultats_repartis, ponderations)` → `render.rendre()` → `publish.publier()`. Chemins de config en paramètres (mêmes contrat que `collecter()`, substituables par les tests) ; `scoring_path` résolu via `collect.DEFAULT_SCORING_PATH` pour rester cohérent avec le chemin réellement utilisé par `collecter()` (respecte la neutralisation de `conftest.py`)
  - [x] `if __name__ == "__main__":` + `main()`, même patron que `collect.py` (`uv run python -m veille.pipeline`)
  - [x] Tests (3) : chemin complet exercé avec client LLM et client de publication simulés (aucun appel réseau réel) — HTML publié contient bien les entrées du socle ; client de publication fourni jamais fermé ; dégradation propre sans clé Anthropic ni jeton GitHub résolu (`False`, jamais de plantage). Confirmé par mutation manuelle (retour forcé à `True` en ignorant l'échec de `publier` → le test de dégradation échoue comme attendu, restauré ensuite)

- [x] Task 5 : Validation (AC: 1-13)
  - [x] Suite complète verte, **aucune régression** sur les tests existants — 291 passed
  - [x] Aucun appel réseau réel dans les tests de cette story (clients simulés pour LLM et pour la publication ; résolution de jeton monkeypatchée dans les tests d'orchestrateur)
  - [x] Audit par mutation, configuration comprise (5 mutants, tous tués) : (M1) autoescaping désactivé → test d'échappement en échec ; (M2) ordre de `CHAMPS_QUOTAS` inversé → test d'ordre des sections en échec ; (M3) marque de recommandation retirée du template → test de marque en échec ; (M4) `resultats_repartis` non peuplé dans `collecter()` → 2 tests de la Task 1 en échec ; (M5) fichier `templates/digest.html.j2` supprimé → les 11 tests de `test_render.py` en échec (`TemplateNotFound`). Note technique : un faux positif est apparu entre deux mutations à cause d'un bytecode `__pycache__` non invalidé par un `cp` de restauration trop rapide (même seconde) — resolu en vidant `__pycache__` après chaque restauration ; chaque mutant a été revérifié individuellement après coup
  - [x] Exécution réelle (sans clé API Anthropic, sans jeton GitHub résolu) : `rendre()` sur un lot d'`Entree` représentatif produit un HTML plausible (3087 caractères, palette/typo/media query dark/marque de recommandation tous présents) ; `publish.publier(html)` avec résolution de jeton forcée à `None` sur les deux voies retourne `False` sans lever, avertissement journalisé une seule fois

### Review Findings

> Revue de code du 2026-08-28 (skill `bmad-code-review`, 3 couches adversariales, sur
> Sonnet 5 — même modèle que l'implémentation, sur demande explicite d'Abdoulaye).
> Base de diff `7b840d1`. Les 3 couches ont convergé indépendamment sur les deux constats
> les plus sérieux (schéma d'URI non validé, `digest_vide` calculé sur la mauvaise donnée),
> chacun revérifié par TDD rouge→vert avant correctif.

**Correctifs appliqués (8) :**

- [x] [Review][Patch] `Item.url` (contenu de source externe non fiable) pouvait porter un schéma `javascript:`/`data:` — l'autoescaping Jinja2 neutralise les métacaractères mais jamais le schéma d'une URI ; un flux compromis aurait produit un lien cliquable exécutable malgré AC8, sans jamais toucher un métacaractère — constat convergent Acceptance Auditor + Blind Hunter. Corrigé par `render._url_surs()` (schéma http(s) exigé, insensible à la casse), exposée comme fonction globale Jinja et utilisée par le template à la place du test de vérité brut sur `entree.item.url` [src/veille/render.py, templates/digest.html.j2]
- [x] [Review][Patch] `digest_vide` était calculé sur `not entrees` (la liste d'entrée), pas sur le contenu réellement rendu — un registre absent de `CHAMPS_QUOTAS` (`repartir_par_quotas`, Story 1.5, conserve sans limite un registre qu'il ne connaît pas : donc bel et bien atteignable via une simple faute de frappe dans `sources.yaml`, pas seulement théorique) faisait disparaître l'entrée **sans** déclencher le message honnête d'AC9 — constat convergent des 3 couches. Corrigé : `digest_vide = not any(...)` sur les sections effectivement peuplées [src/veille/render.py]
- [x] [Review][Patch] Une entrée à registre inconnu disparaissait du rendu sans la moindre trace — désormais journalisée (`logger.warning`, guid + registre) avant d'être écartée, cohérent avec le réflexe déjà établi ailleurs dans le projet (jamais de perte silencieuse) [src/veille/render.py]
- [x] [Review][Patch] `pipeline.executer()` affirmait « ne lève jamais » en listant `collecter`/`enrichir`/`marquer_recommandation`/`publier` comme dégradant déjà proprement — mais omettait `rendre()`, qui n'a aucune garantie propre (un `templates/digest.html.j2` manquant ou corrompu lève `TemplateNotFound`) et rien ne l'isolait — constat convergent Blind Hunter + Edge Case Hunter. Corrigé par un filet de sécurité de dernier recours enveloppant l'intégralité du corps de la fonction [src/veille/pipeline.py]
- [x] [Review][Patch] `main()` calculait le succès/échec de la publication puis le jetait (seulement un `logger.warning`) — un futur planificateur de tâches (FR-11, Epic 3) n'aurait eu aucun moyen fiable de détecter une nuit en échec sans analyser les logs. Corrigé par un code de sortie (`sys.exit(0/1)`) [src/veille/pipeline.py]
- [x] [Review][Patch] `pipeline.executer()` rompait la convention de type hints du reste du projet (paramètres non annotés, contrairement à `collecter()`). Corrigé — sauf `llm_client`, délibérément non typé `anthropic.Anthropic | None` : l'importer romprait l'invariant AD-7 (un seul point d'import du SDK, vérifié par `grep`) pour une simple annotation [src/veille/pipeline.py]
- [x] [Review][Patch] `_sha_existant` traitait tout code HTTP non-200 (401 jeton invalide, 403 quota épuisé, 5xx) comme un « fichier absent » identique à un 404 — le PUT suivant aurait alors tenté une création sans `sha` sur un fichier existant, masquant la vraie panne derrière un rejet générique de l'API. Constat convergent des 3 couches. Corrigé : seul un 404 vaut « absent » ; tout autre code lève via `raise_for_status()`, isolé comme toute autre panne par `publier()` [src/veille/publish.py]
- [x] [Review][Patch] `.env.example` n'avait en réalité jamais été modifié malgré le plan de la story (« Structure de fichiers ») qui l'annonçait — corrigé, `GITHUB_TOKEN=` ajouté avec un commentaire expliquant le repli sur `gh auth token` [.env.example]

**Reporté (0) :** aucun.

**Rejeté comme bruit (5) :**

- « La publication pourrait masquer un run réellement en échec derrière un message « rien à signaler aujourd'hui » identique à celui d'une nuit calme » — explicitement hors périmètre de cette story (voir Dev Notes, « Bandeau d'échec nocturne ») : un bandeau distinctif suppose un état de run persistant qu'aucun composant ne fournit encore (`store.py`/SQLite, AD-5, toujours ⏳) ; reporté à l'Epic 3 comme déjà documenté.
- « `scoring.yaml` est relu deux fois par run » (une fois dans `collecter()`, une fois dans `pipeline.executer()` pour `marge_recommandation`) — lecture d'un petit fichier YAML, une fois par nuit : coût négligible. Le corriger exigerait d'exposer `Ponderations` comme un champ additif supplémentaire de `ResultatCollecte` pour un bénéfice marginal — non justifié maintenant.
- « Le jeton issu de `gh auth token` n'est ni restreint ni validé en portée avant un usage non surveillé » — compromis déjà assumé et documenté dans les Dev Notes de cette story (convenance immédiate ; un PAT `GITHUB_TOKEN` restreint reste disponible dès qu'Abdoulaye le souhaite).
- « L'API Contents de GitHub a un plafond de charge utile par fichier (~1 Mo), non anticipé » — prématuré à l'échelle réelle du projet (NFR1 : ≈8 accroches/jour, une page HTML minuscule), aucun AC ne l'exige.
- « Le `sha` peut changer entre le `GET` préalable et le `PUT` (écriture concurrente), sans logique de nouvelle tentative » — non atteignable aujourd'hui : système mono-opérateur, un seul run par nuit, aucun écrivain concurrent possible tant qu'aucun ordonnanceur (Epic 3) ne fait tourner le pipeline plusieurs fois en parallèle.

Suite complète revérifiée verte après application des correctifs : **299 tests** (291 avant revue).

## Dev Notes

### Prérequis de publication (hors code, ne bloque pas les Tasks 1-5)

Pour que Task 5 valide une publication **réelle**, un dépôt de sortie doit exister :

1. Créer un second dépôt GitHub, **public**, dédié uniquement à la page publiée (nom proposé : `agent-veille-tech-digest` — à ajuster librement, ne touche que la constante `PUBLISH_REPO` dans `publish.py`). Réalisable via `gh repo create <nom> --public`.
2. Activer GitHub Pages dessus (source : branche par défaut, racine). Réalisable via l'API (`gh api -X POST repos/{owner}/{repo}/pages -f "source[branch]=main" -f "source[path]=/"`).
3. `GITHUB_TOKEN` reste optionnel dans `.env` grâce au repli sur `gh auth token` (Task 3) — utile seulement si le run doit un jour se faire sans session `gh` authentifiée localement (ex. futur repli GitHub Actions, déjà noté « Deferred » dans `ARCHITECTURE-SPINE.md`). L'ajouter à `.env.example` (vide), comme `ANTHROPIC_API_KEY=`, pour documenter l'option — pas obligatoire pour que Task 5 réussisse.

**Créer un dépôt public est une action réelle, sortante, sous le compte d'Abdoulaye** — à confirmer explicitement avec lui avant de l'exécuter (`gh repo create`), même si le reste de l'implémentation (Tasks 1-4, tests) avance sans attendre cette confirmation, avec des clients simulés. Sans ce dépôt au moment de Task 5, traiter la validation réelle de bout en bout comme différée et le documenter ainsi (même limite déjà rencontrée avec `ANTHROPIC_API_KEY` en Story 1.6) — ne pas bloquer le reste de la story dessus.

### Pourquoi un second dépôt, public, dédié à la sortie (décidé avec Abdoulaye)

`Agent_Veille_Tech` est privé (contient le brief/PRD/stories — contexte professionnel personnel, réintégré au dépôt le 2026-08-28 précisément parce que le dépôt est privé). GitHub Pages sur un dépôt privé exige un plan payant (Pro/Team/Enterprise) ; sur un compte gratuit, Pages ne fonctionne que sur un dépôt public. Abdoulaye a choisi, entre plusieurs options présentées, de créer un **second dépôt public, dédié uniquement à la page publiée** — le code, les stories, le brief/PRD restent privés. Coût nul, ne force pas à rendre `Agent_Veille_Tech` public.

Ce choix n'est **pas une entorse à l'architecture** : le Structural Seed (`ARCHITECTURE-SPINE.md`) anticipait déjà explicitement cette variante — `site/ : sortie publiée (dépôt GitHub Pages) — peut être un sous-module ou un repo distinct` — et la ligne Stack le confirme : `Hébergement page + archive | GitHub Pages (dépôt public)`. Aucun amendement d'AD-8 n'est nécessaire.

### Pourquoi l'API Contents de GitHub, pas un clone local + `subprocess git`

Deux façons possibles d'écrire dans le dépôt de sortie : (a) cloner localement ce dépôt (répertoire fixe supposé), écrire le fichier, `git add/commit/push` via `subprocess` ; (b) appeler l'API REST Contents (`PUT /repos/{owner}/{repo}/contents/{path}`) avec le contenu encodé en base64, sans dépendance à un chemin local préexistant. Choix : **(b)**, pour deux raisons — testabilité (un client HTTP simulé, comme `enrich/llm.py` le fait déjà pour Claude ; un `subprocess` vers `git` serait bien plus difficile à isoler proprement dans un test) et absence de couplage à l'environnement de la machine (pas d'hypothèse sur un dossier voisin déjà cloné). `httpx` est déjà une dépendance du projet — aucune nouvelle dépendance réseau à ajouter.

L'API Contents exige le `sha` du fichier existant pour une *mise à jour* (sinon GitHub refuse, croyant à un conflit) ; un `GET` préalable le récupère. Une absence de fichier (premier run) doit être traitée comme une création, pas comme un échec.

### Piège Jinja2 : le nom de fichier `digest.html.j2` ne déclenche pas l'autoescaping par défaut

`jinja2.select_autoescape()` **sans argument** n'active l'échappement automatique que pour les noms de template se terminant par `.html`, `.htm`, `.xml` (et `.xhtml`) — déterminé par l'extension du **nom du fichier de template**. Le template s'appelant `digest.html.j2`, son extension au sens de `select_autoescape` est `.j2`, absent de la liste : **l'échappement serait silencieusement désactivé**, malgré le `.html` dans le nom. Conséquence concrète si ce piège n'est pas évité : un titre d'article contenant `<script>` (source externe non fiable — RSS/scraping, déjà la même préoccupation que le garde-fou anti-injection de `enrich/llm.py`, Story 1.6) serait injecté tel quel dans la page publiée. Deux corrections possibles, l'une des deux est requise :
- `Environment(..., autoescape=True)` — inconditionnel, le plus sûr ;
- `Environment(..., autoescape=select_autoescape(enabled_extensions=("html", "xml", "j2")))` — ajoute `.j2` à la liste reconnue.

Ne **jamais** s'appuyer sur le comportement par défaut de `select_autoescape()` avec ce nom de fichier. AC8 est vérifié par un test explicite qui injecte `<script>` dans un titre et vérifie l'échappement dans le HTML produit.

### Pourquoi `pipeline.py` n'éclate pas `collect.py`

`collecter()` orchestre déjà en interne collecte → seuil de signal → dédoublonnage → scoring → quotas (tension AD-1 assumée depuis la Story 1.4, 25 tests d'intégration reposent sur ce comportement exact). Cette story ne défait **pas** ce chaînage interne — `pipeline.py` appelle `collecter()` tel quel, puis enchaîne enrichissement, rendu, publication par-dessus. La tension AD-1 documentée (« pas d'orchestrateur dédié ») était surtout l'absence d'un point d'entrée unique couvrant tout le pipeline, pas nécessairement le fait que `collecter()` fasse plusieurs choses en interne — un éclatement complet toucherait beaucoup de code déjà testé et fonctionnel pour un gain non demandé par les AC de cette story. `pipeline.py` referme donc la partie de la tension qui a un AC réel (AC11) ; le chaînage interne de `collecter()` reste une simplification possible mais non requise, à ne pas faire ici (éviterait la sur-portée — même discipline que Story 1.7 sur `enrichir()`/`marquer_recommandation`).

### Pourquoi `resultats_repartis` est un champ additif sur `ResultatCollecte`, pas une signature changée

Même patron de décision qu'en Story 1.7 (fonction additive plutôt que signature changée) : ajouter un champ à une dataclass avec une valeur par défaut (`[]`) ne casse aucun appelant existant ni aucun des 25 tests de `test_collecte_integration.py`, qui comparent `ResultatCollecte` sur les champs qu'ils connaissent déjà. C'est la correction minimale qui ferme la dette « Score jeté » sans toucher au comportement de `collecter()`.

### Pourquoi `PUBLISH_REPO` est une constante en dur, pas une entrée de configuration

AD-3 (« Sources et Profil sont de la configuration ») lie explicitement FR-1/5/6 — pas la cible de publication. Précédent direct : `MODELE = "claude-haiku-4-5-20251001"` dans `enrich/llm.py` est déjà une constante en dur, pas un fichier de config, pour un paramètre tout aussi spécifique au déploiement d'Abdoulaye. Même traitement pour `PUBLISH_REPO` — un paramètre que seul Abdoulaye modifierait, et rarement. `GITHUB_TOKEN`, lui, est un secret : `.env`, jamais en dur, jamais versionné (AD-10) — même traitement que `ANTHROPIC_API_KEY`.

### Précédents à réutiliser, pas à réinventer

- **Ordre des registres** : `filter.CHAMPS_QUOTAS = ("apprendre", "ce_qui_bouge", "pour_le_metier")` est déjà l'ordre canonique utilisé pour les quotas — `render.py` le réutilise pour l'ordre d'affichage des sections, n'en redéfinit pas un second quelque part d'autre.
- **Isolation de panne réseau, dégradation, avertissement une fois par run** : `enrich/llm.py::_client()`/`generer_accroche()` (Story 1.6) sont le patron exact à reproduire dans `publish.py` — jeton nettoyé des espaces avant test de présence (`.strip()`, trouvé en revue Story 1.6), avertissement déduplicé, aucune exception qui remonte.
- **Repli sur le titre en cas d'échec d'accroche** (Story 1.6) : `enrichir()` n'est pas modifié par cette story, `pipeline.py` l'appelle tel quel.
- **`Entree.recommandee`** (Story 1.7) : au plus une entrée porte `True` par construction de `marquer_recommandation` — `render.py` n'a pas besoin de re-vérifier cet invariant, seulement de le refléter visuellement.

### Hors périmètre — ne pas anticiper

- **Archive Markdown datée** (`templates/digest.md.j2`, `site/archive/YYYY-MM-DD.md`) — Story 1.9, FR-10. `render.py` ne produit que le HTML de la page courante dans cette story.
- **Bandeau d'échec nocturne** (mentionné dans le texte de FR-9, mais absent des AC de la Story 1.8 dans `epics.md`) — suppose un état de run persistant (échec de la nuit précédente) que rien ne fournit encore : ni `store.py`/SQLite (AD-5, toujours ⏳), ni `pipeline.py` avant cette story. Reporté à l'Epic 3, quand l'exécution nocturne automatique (FR-11) et un état persistant existeront pour le nourrir.
- **Bascule manuelle de thème** (JS, préférence utilisateur mémorisée) — l'AC ne demande que la détection automatique `prefers-color-scheme` (UX-DR4) ; une bascule manuelle serait un ajout non demandé (UX-DR5, sobriété).
- **Éclater le chaînage interne de `collecter()`** — voir Dev Notes ci-dessus.
- **Ordonnancement nocturne automatique** (Planificateur Windows, FR-11) — Epic 3. `pipeline.py` expose un point d'entrée invocable manuellement, pas un déclencheur.

### Structure de fichiers

```text
config/
  (aucun changement)
.env.example                # MODIFIÉ — ajout de GITHUB_TOKEN= (optionnel, repli sur `gh auth token`)
src/veille/
  collect.py                 # MODIFIÉ — ResultatCollecte.resultats_repartis
  filter.py                  # MODIFIÉ — _CHAMPS_QUOTAS renommé CHAMPS_QUOTAS (public, réutilisé par render.py)
  render.py                  # NOUVEAU — rendu HTML (Jinja2)
  publish.py                 # NOUVEAU — publication via API Contents GitHub
  pipeline.py                # NOUVEAU — orchestrateur (AD-1)
templates/
  digest.html.j2              # NOUVEAU
pyproject.toml / uv.lock      # MODIFIÉS — dépendance jinja2
tests/
  test_collect.py             # MODIFIÉ — resultats_repartis
  test_render.py               # NOUVEAU
  test_publish.py              # NOUVEAU
  test_pipeline.py             # NOUVEAU
```

### Testing Standards

- `pytest`, via `uv run pytest`. **Aucun appel réseau ni subprocess réel** — client HTTP simulé pour `publish.py`, résolution de jeton simulée (pas d'appel réel à `gh`), client LLM simulé pour l'enrichissement (déjà établi Story 1.6) — tout tourne sans `GITHUB_TOKEN`, sans session `gh` authentifiée, ni `ANTHROPIC_API_KEY` configurés.
- **Audit par mutation en Task 5, configuration et template compris** — leçon des Stories 1.4/1.5/1.7, à ne pas répéter une quatrième fois par omission.
- Test d'échappement HTML explicite (AC8) — pas seulement une lecture visuelle, une assertion mécanique sur la sortie.

### Previous Story Intelligence (Story 1.7)

- `Entree` porte maintenant `item`, `accroche`, `recommandee` (frozen). `enrich/llm.py` expose `enrichir()`, `determiner_recommandation()`, `marquer_recommandation()` — aucun n'est encore appelé en dehors des tests ; cette story est la première à les enchaîner réellement.
- `marquer_recommandation(entrees, classement, ponderations)` attend un `classement` **filtré par quota** (`repartir_par_quotas()`), pas le classement brut de `classer()` — précisé en docstring lors de la revue de la Story 1.7 spécifiquement pour cette story. `resultats_repartis` (Task 1) est exactement ça.
- Aucune clé `ANTHROPIC_API_KEY` configurée à ce jour — sans conséquence pour le développement (client simulé), mais la validation réelle des accroches reste différée, comme documenté depuis la Story 1.6.
- Convention de commit établie (Stories 1.4-1.7) : un commit pour l'implémentation + revue de la story, un commit séparé pour la mise à jour de `docs/rapport-projet.md`, tous deux poussés vers `origin/main`.
- **Les dossiers `_bmad/`, `.claude/`, `_bmad-output/` sont maintenant suivis par git** (réintégrés le 2026-08-28, commit `7b840d1`) — inclure ce fichier de story dans les commits futurs (`git add -A` couvre tout), ne pas oublier comme la première fois.

### Git Intelligence Summary

Commits récents : Story 1.7 (implémentation + revue, un commit), rapport de projet (commit séparé), réintégration des dossiers BMad (commit séparé, hors cycle de story). Même convention à reproduire ici : un commit pour l'implémentation + revue de la Story 1.8, un commit séparé pour le rapport.

### Project Structure Notes

Aligné avec le Structural Seed de `ARCHITECTURE-SPINE.md` : `render.py`, `publish.py`, `pipeline.py` et `templates/digest.html.j2` sont exactement les chemins qu'il prévoit. Seul écart assumé et documenté : `site/` (sortie publiée) n'est **pas** un sous-dossier de ce dépôt comme le Structural Seed le montre en exemple — c'est un second dépôt distinct, variante que le même document anticipe explicitement (« peut être un sous-module ou un repo distinct »).

### References

- [Source: epics.md#Story-1.8] — story d'origine et critères d'acceptation
- [Source: epics.md#FR9] — page à URL stable ; [Source: epics.md#NFR4] — lisibilité mobile ; [Source: epics.md#NFR6] — qualité visuelle ; [Source: epics.md#UX-Design-Requirements] — UX-DR1 à UX-DR5
- [Source: ARCHITECTURE-SPINE.md#AD-1] — paradigme pipeline, orchestrateur dédié
- [Source: ARCHITECTURE-SPINE.md#AD-8] — publication par commit git vers GitHub Pages ; variante dépôt distinct explicitement anticipée (Structural Seed)
- [Source: ARCHITECTURE-SPINE.md#Structural-Seed] — chemins `render.py`, `publish.py`, `pipeline.py`, `templates/`, `site/`
- [Source: 1-4-scoring-par-profil.md] — origine de la dette « Score jeté par `collect.py` »
- [Source: 1-6-accroches-francaises.md] — patron `_client()`/isolation réseau à reproduire dans `publish.py` ; garde anti-injection dans un prompt, même préoccupation ici pour le HTML
- [Source: 1-7-recommandation-entree.md] — `marquer_recommandation` attend un classement filtré par quota ; `Entree.recommandee`
- [Source: deferred-work.md] — dette XSS (`contenu_brut` non échappé), `Score.motifs` jeté par `collect.py`, `pipeline.py` à créer, `models.py` ne valide pas la non-vacuité de `titre`/`url` (« à muscler quand la Story 1.8 rendra les champs vides visiblement cassés à l'écran »)
- Décision utilisateur du 2026-08-28 (cette session) : second dépôt GitHub public, dédié à la sortie — choisi parmi plusieurs options présentées après constat que GitHub Pages est indisponible sur un dépôt privé sans plan payant

## Dev Agent Record

### Agent Model Used

claude-sonnet-5 (Sonnet 5)

### Debug Log References

Un faux positif de mutation dû à un bytecode `__pycache__` non invalidé (voir Task 5, Completion Notes) — diagnostiqué et corrigé en vidant `__pycache__` entre chaque mutation, aucun impact sur le code livré.

### Completion Notes List

- **Prérequis de publication non exécuté cette session** : le second dépôt GitHub public (`petitlaye03/agent-veille-tech-digest`) n'a **pas** été créé — action réelle sous le compte d'Abdoulaye, à confirmer explicitement avant de l'exécuter (voir Dev Notes). Tasks 1-5 ont toutes avancé sans cette dépendance, avec des clients simulés, exactement comme prévu. `publish.publier()` est donc **validée par tests et par exécution réelle en dégradation** (sans jeton résolu → `False`, aucune exception), mais **pas encore contre l'API GitHub réelle** — même limite déjà rencontrée avec `ANTHROPIC_API_KEY` en Story 1.6, à lever dès que le dépôt de sortie existera.
- **Renommage `filter._CHAMPS_QUOTAS` → `filter.CHAMPS_QUOTAS`** (nom public) : ce nom devient un contrat inter-module réutilisé par `render.py` pour l'ordre d'affichage des sections — plus cohérent de l'exposer publiquement que d'importer un nom privé d'un autre module. Aucun autre appelant existant, renommage sans risque (vérifié par `grep` avant renommage).
- **Piège Jinja2 identifié et évité** : `select_autoescape()` sans argument ne reconnaît pas l'extension `.j2` du nom de template `digest.html.j2` — l'échappement aurait été silencieusement désactivé. Corrigé par `enabled_extensions=("html", "xml", "j2")` explicite. Vérifié par un test d'injection (`<script>`) et confirmé tuer un mutant qui désactive l'autoescaping.
- **`pipeline.executer()` accepte des chemins de configuration et des clients en paramètres** (au-delà du simple `executer()` esquissé dans la story) — nécessaire pour tester le chemin complet sans toucher au réseau ni au vrai `config/sources.yaml` : `collecter()` avec un `sources_path` par défaut à `None` résout sur le vrai socle de production si on ne le fournit pas explicitement, donc les tests de `pipeline.py` passent systématiquement un `sources_path` de test (patron déjà établi par `test_collect.py`/`test_collecte_integration.py`).
- **`scoring_path` résolu via `collect.DEFAULT_SCORING_PATH`** dans `pipeline.executer()` plutôt que via un défaut local, pour respecter la neutralisation `conftest.py` (qui patche `collect.DEFAULT_SCORING_PATH`, pas `filter.DEFAULT_SCORING_PATH`) et rester cohérent avec le chemin réellement utilisé par `collecter()` pour calculer le classement dont `marge_recommandation` doit dériver.
- **Tests de `pipeline.py` écrits après l'implémentation**, pas en rouge-vert strict (contrairement aux Tasks 1-3) — l'orchestrateur est une couche de câblage fine sur des fonctions déjà testées unitairement. Compensé par une vérification de mutation manuelle immédiate (retour forcé à `True` en ignorant l'échec de `publier()`) qui a bien fait échouer le test de dégradation attendu, confirmant que les tests exercent réellement le comportement et ne sont pas des tautologies.
- **Audit par mutation (Task 5)** : 5 mutants, tous tués — voir le détail dans la case à cocher de Task 5. Un faux positif intermédiaire (bytecode `__pycache__` stale après une restauration `cp` trop rapide, même seconde de mtime) a été diagnostiqué et n'affecte pas le résultat final ; chaque mutant a été revérifié isolément après vidage du cache.
- Suite complète après implémentation (avant revue) : **291 tests** (263 avant cette story : +3 Task 1, +11 Task 2, +11 Task 3, +3 Task 4). Après revue (8 correctifs, tests étendus) : **299 tests** — voir Review Findings.

### File List

**Code :**
- `src/veille/collect.py` — modifié : `ResultatCollecte.resultats_repartis`, docstring de `collecter()` mise à jour
- `src/veille/filter.py` — modifié : `_CHAMPS_QUOTAS` renommé `CHAMPS_QUOTAS` (public)
- `src/veille/render.py` — nouveau : `LIBELLES_REGISTRE`, `_url_surs`, `_environnement_jinja`, `rendre` (registre inconnu journalisé, `digest_vide` sur les sections réellement peuplées — revue)
- `src/veille/publish.py` — nouveau : `PUBLISH_REPO`, `_jeton_depuis_env`, `_jeton_depuis_gh_cli`, `_jeton`, `_client`, `_sha_existant` (404 distingué des autres erreurs — revue), `publier`, `_avertir_echec_publication`
- `src/veille/pipeline.py` — nouveau : `executer` (filet de sécurité, type hints — revue), `main` (code de sortie — revue)

**Templates :**
- `templates/digest.html.j2` — nouveau (mis à jour en revue : `url_surs()` remplace le test de vérité brut sur `entree.item.url`)

**Configuration :**
- `pyproject.toml` / `uv.lock` — modifiés : dépendance `jinja2` (3.1.6)
- `.env.example` — modifié en revue : ajout de `GITHUB_TOKEN=` (optionnel)

**Tests :**
- `tests/test_collect.py` — modifié : 3 tests `resultats_repartis` (10 tests au total désormais)
- `tests/test_render.py` — nouveau, étendu en revue : 17 tests (11 à l'implémentation + 6 en revue)
- `tests/test_publish.py` — nouveau, étendu en revue : 12 tests (11 à l'implémentation + 1 en revue)
- `tests/test_pipeline.py` — nouveau, étendu en revue : 4 tests (3 à l'implémentation + 1 en revue)

### Change Log

| Date | Modification |
|------|--------------|
| 2026-08-28 | Implémentation complète (Tasks 1-5) : `ResultatCollecte.resultats_repartis` (dette fermée), `render.py` + `templates/digest.html.j2` (rendu HTML, palette/typo/dark mode/mobile-first/échappement/marque de recommandation/repli titre-vide/pas-de-lien-si-url-vide), `publish.py` (publication via API Contents GitHub, résolution de jeton à deux niveaux), `pipeline.py` (orchestrateur AD-1). Audit par mutation à 5 mutants, tous tués. Exécution réelle en dégradation confirmée (sans clé Anthropic ni jeton GitHub). Prérequis de publication (dépôt de sortie, GitHub Pages) non exécuté — action réelle différée, confirmation explicite requise. 291 tests. Statut → review. |
| 2026-08-28 | Revue de code (Sonnet 5, 3 couches, même modèle que l'implémentation). 8 correctifs, 0 reporté, 5 rejetés : schéma d'URI non validé sur `Item.url` (constat convergent, corrigé par `_url_surs()`), `digest_vide` calculé sur la mauvaise donnée (constat convergent des 3 couches — un registre erroné dans `sources.yaml` blanchissait la page sans le message honnête d'AC9), registre inconnu désormais journalisé, filet de sécurité autour de `rendre()` dans l'orchestrateur, code de sortie de `main()`, type hints, `_sha_existant` distingue 404 des autres erreurs (constat convergent), `.env.example` réellement mis à jour. 299 tests. Statut → done. |
