---
baseline_commit: ba805f6
---

# Story 1.9: Archiver chaque digest en Markdown

Status: done

## Story

As a Abdoulaye,
I want que chaque digest soit conservé dans une archive versionnée,
so that je peux retrouver un sujet lu plusieurs semaines auparavant.

## Acceptance Criteria

1. **[FR-10]** Étant donné une liste d'`Entree` et une date de génération, `render.rendre_markdown(entrees, date_generation)` produit une archive Markdown avec les mêmes trois sections, dans le même ordre, que la page HTML (Story 1.8) — réutilise le regroupement par registre déjà existant, n'en réimplémente pas un second qui pourrait diverger.
2. **[FR-10]** L'archive est publiée à un chemin **daté** dans le dépôt de sortie (`site/archive/YYYY-MM-DD.md`, Structural Seed) — `publish.publier_archive(markdown, date_digest, client=None)`.
3. **[AD-9]** Relancer le pipeline pour la même date **écrase** l'archive de cette date (upsert via le `sha` existant, même mécanisme que `publier()` pour la page) — jamais un second fichier pour un même jour.
4. **[Sûreté]** Le titre et l'accroche (contenu de source externe non fiable) sont échappés des caractères spéciaux Markdown avant insertion dans l'archive — sinon un titre contenant `*`, `[`, `` ` `` reformaterait involontairement l'archive, ou `[texte](url-malveillante)` créerait un lien arbitraire non prévu par la source.
5. **[Sûreté]** Un lien Markdown vers l'original enveloppe sa destination entre `<...>` (`[texte](<url>)`) — une URL contenant des parenthèses (fréquent, ex. liens Wikipédia) casserait sinon la syntaxe `(url)` du lien. Même garde-fou de schéma que la page HTML (`render._url_surs`, réutilisé, pas réinventé) : une URL de schéma refusé n'émet aucun lien.
6. **[FR-10]** L'archive reste « cherchable par texte sur l'ensemble de l'historique » par construction — fichiers Markdown en clair, un par jour, dans un dépôt versionné (grep/recherche GitHub natifs) : aucune infrastructure de recherche dédiée n'est nécessaire ni ajoutée par cette story.
7. **[AD-1]** `pipeline.executer()` publie désormais la page **et** l'archive du jour dans le même run — `rendre()`+`publier()` (Story 1.8, inchangés) et `rendre_markdown()`+`publier_archive()` (nouveaux), à partir du même horodatage de génération.
8. Un échec de publication de l'archive est distingué d'un échec de publication de la page dans les journaux (message différent) — sinon Abdoulaye ne saurait pas laquelle des deux a échoué une nuit donnée.

## Tasks / Subtasks

- [x] Task 1 : Rendu Markdown (AC: 1, 4, 5, 6)
  - [x] Extrait `_grouper_par_registre(entrees) -> tuple[list[tuple[str, str, list[Entree]]], bool]` de `rendre()` (`src/veille/render.py`) — refactor pur confirmé : les 17 tests existants de `test_render.py` sont restés verts sans modification avant d'ajouter la moindre nouvelle fonctionnalité
  - [x] `_echapper_markdown(texte: str) -> str` — échappe `` \`*_{}[]()#+-.!|>~ `` par backslash (CommonMark : tout backslash devant une ponctuation ASCII est rendu comme le caractère littéral). `None`/vide → chaîne vide
  - [x] `_environnement_jinja_markdown() -> Environment` — environnement séparé, `autoescape=False`, filtre `markdown_safe`, global `url_surs` réutilisé
  - [x] `templates/digest.md.j2` — sections, titre/accroche via `| markdown_safe`, lien `[texte](<{{ lien }}>)`, état vide honnête
  - [x] `rendre_markdown(entrees, date_generation) -> str`
  - [x] Tests (8) : 3 sections dans le bon ordre ; contenu présent ; échappement des caractères spéciaux (`*`, `[`) vérifié ; URL Wikipédia-style avec parenthèses → lien `(<url>)` valide ; schéma `javascript:` refusé → pas de lien ; registre inconnu journalisé ; liste vide → message honnête ; titre vide → repli sur l'accroche. Suite complète : 307 passed (299 avant cette story)

- [x] Task 2 : Publication de l'archive (AC: 2, 3, 8)
  - [x] `src/veille/publish.py` : `CHEMIN_FICHIER` renommé `CHEMIN_PAGE`
  - [x] `_sha_existant(client, chemin)` paramétrée par le chemin — comportement inchangé pour `publier` (lui passe toujours `CHEMIN_PAGE`)
  - [x] Extrait `_publier(chemin, contenu, client, quoi) -> bool` — cœur partagé ; `publier(html, client=None)` devient un appelant fin, signature et comportement observable inchangés (12 tests existants de `test_publish.py` restés verts sans modification avant l'ajout des nouveaux)
  - [x] `publier_archive(markdown, date_digest, client=None) -> bool` — `_publier(f"site/archive/{date_digest.isoformat()}.md", markdown, client, ...)`
  - [x] `_avertir_echec_publication(quoi)` — paramétrée (`"de la page"` / `"de l'archive du {date}"`)
  - [x] Tests (6) : création, mise à jour (sha transmis) au chemin daté correct, jeton absent, échec réseau, réponse en erreur (500), messages de log distincts page/archive. Suite complète : 313 passed (307 avant cette tâche)

- [x] Task 3 : Câblage dans l'orchestrateur (AC: 7)
  - [x] `src/veille/pipeline.py::executer()` : un seul horodatage (`maintenant`) réutilisé pour `rendre`, `rendre_markdown` et `publier_archive(..., maintenant.date(), ...)`
  - [x] Retour : `True` seulement si la page **et** l'archive sont publiées avec succès (`page_ok and archive_ok`) — les deux toujours tentées, même si l'une échoue
  - [x] Tests (2, dont un existant réécrit) : chemin complet — deux appels `PUT` (page + archive daté, chemins vérifiés par regex) ; échec de l'archive seule n'empêche pas la tentative de la page (et inversement), `reussite=False` reflète bien l'échec partiel. Effet de bord positif trouvé pendant l'écriture de ce test : la fausse réponse HTTP locale de `test_pipeline.py` ne levait jamais sur un code d'erreur (`raise_for_status` était un no-op) — corrigée pour refléter le vrai comportement de `httpx.Response`, ce qui rend aussi les tests existants de ce fichier plus fidèles. Suite complète : 314 passed (313 avant cette tâche)

- [x] Task 4 : Validation (AC: 1-8)
  - [x] Suite complète verte, **aucune régression** — 314 passed (299 avant la story ; +15 : 8 Task 1, 6 Task 2, 1 net Task 3 après réécriture d'un test existant)
  - [x] Aucun appel réseau/subprocess réel dans les tests de cette story
  - [x] Audit par mutation, template compris (4 mutants, tous tués) : (M1) échappement Markdown désactivé → test d'échappement en échec ; (M2) enveloppe `<...>` retirée du lien → test des parenthèses d'URL en échec ; (M3) `publier_archive` avec un chemin non daté → 2 tests en échec (chemin attendu absent) ; (M4) `rendre_markdown` réimplémente un regroupement divergent au lieu de réutiliser `_grouper_par_registre` → test du registre inconnu en échec (avertissement absent)
  - [x] Exécution réelle (sans clé API ni jeton GitHub résolu) : `rendre_markdown()` sur un lot d'`Entree` représentatif produit un Markdown plausible (310 caractères, sections + marque de recommandation présentes) ; `publish.publier_archive()` et `pipeline.executer()` (chemin complet, vraie collecte sur une source de test) dégradent tous deux proprement à `False` sans lever, jeton non résolu journalisé une fois

### Review Findings

> Revue de code du 2026-08-31 (skill `bmad-code-review`, 3 couches adversariales, sur
> Sonnet 5 — même modèle que l'implémentation, sur demande explicite d'Abdoulaye).
> Base de diff `ba805f6`. Les 3 couches ont convergé indépendamment sur le couple de
> constats le plus sérieux (échappement Markdown incomplet d'un côté, sur-échappement
> de l'autre — les deux dans `_echapper_markdown`), chacun revérifié par TDD rouge→vert
> et, pour deux correctifs de robustesse de l'orchestrateur, par mutation manuelle
> avant classement.

**Correctifs appliqués (9) :**

- [x] [Review][Patch] `_CARACTERES_MARKDOWN_SPECIAUX` omettait `<` — un titre de source externe contenant `<img src=x onerror=...>` restait une vraie balise HTML brute dans l'archive Markdown, contournant l'AC4 malgré l'échappement des autres caractères. Constat convergent (Acceptance Auditor + Edge Case Hunter). **Dans le même mouvement** : `#`, `-`, `+`, `.` retirés de l'ensemble échappé — ils ne sont syntaxiquement actifs qu'en tout début de ligne (jamais atteignable ici, texte toujours inséré au milieu d'une puce déjà ouverte), et les échapper quand même cassait l'AC6 (« cherchable par texte ») pour un cas aussi courant qu'un nom de modèle versionné (`GPT-5.2`) — second constat convergent (Acceptance Auditor + Blind Hunter), résolu par le même correctif que le premier [src/veille/render.py, `_CARACTERES_MARKDOWN_SPECIAUX`]
- [x] [Review][Patch] `_echapper_markdown` ne neutralisait pas les sauts de ligne incorporés — un titre/accroche multi-ligne aurait replacé un caractère normalement inerte en milieu de texte en tout début d'une nouvelle ligne, où il redevient actif (et aurait de toute façon rompu la structure de liste de l'archive). Nécessaire pour que le retrait de `-`/`.`/`+`/`#` du correctif précédent reste sûr. Constat convergent (Edge Case Hunter + Blind Hunter) [src/veille/render.py, `_echapper_markdown`]
- [x] [Review][Patch] `pipeline.executer()` affirmait que la page et l'archive sont « toujours tentées, même si l'une échoue » — vrai seulement pour un échec côté publication. Si `rendre_markdown()` levait *après* que `rendre()` a réussi, la page déjà produite avec succès était perdue faute d'avoir été publiée avant l'échec de l'archive. Corrigé en publiant la page immédiatement après son rendu, avant même de tenter le rendu de l'archive [src/veille/pipeline.py]
- [x] [Review][Patch] Le drapeau « trace complète au premier échec » de `publish.py` était un booléen unique partagé entre page et archive — si les deux échouaient dans le même run, seule la première des deux obtenait sa trace complète, l'autre n'ayant plus qu'un message sans contexte de diagnostic malgré un échec tout aussi nouveau. Corrigé par un ensemble de catégories (`"page"`/`"archive"`) plutôt qu'un booléen global [src/veille/publish.py, `_avertir_echec_publication`]
- [x] [Review][Patch] `_url_surs` ne rejetait pas une URL contenant un `<`/`>` littéral — l'enveloppe `<...>` du lien Markdown (ajoutée précisément pour tolérer les parenthèses) se fermerait prématurément sur un tel caractère, faisant fuiter le reste de l'URL comme texte du document. Sans conséquence pour le HTML (Jinja2 échappe déjà `<`/`>` dans un attribut), donc corrigé au niveau partagé sans risque pour `rendre()` [src/veille/render.py, `_url_surs`]
- [x] [Review][Patch] Le libellé de secours d'une section (`LIBELLES_REGISTRE.get(registre, registre)`) n'était pas passé par `markdown_safe` dans le template — actuellement inatteignable via l'API publique (les 3 valeurs de `CHAMPS_QUOTAS` ont toutes un libellé dans `LIBELLES_REGISTRE`), mais échappé par cohérence défensive sans coût, au cas où cette correspondance se désynchronise un jour [templates/digest.md.j2]
- [x] [Review][Patch] `test_executer_publie_la_page_et_l_archive_datee` vérifiait la présence des mêmes sous-chaînes dans les deux corps publiés sans jamais corréler quel contenu avait atterri à quel chemin — une régression qui inverserait les deux corps (Markdown publié comme page, HTML publié comme archive) serait passée inaperçue. Corrigé, et vérifié par une mutation manuelle qui inverse réellement les deux publications : le test durci l'attrape [tests/test_pipeline.py]
- [x] [Review][Patch] Couverture de `_url_surs` asymétrique entre `rendre()` (URL vide, `javascript:`, `data:`, casse) et `rendre_markdown()` (seulement `javascript:`) — deux tests ajoutés côté Markdown pour la parité [tests/test_render.py]
- [x] [Review][Patch] Aucun test n'exerçait `_echapper_markdown` sur un saut de ligne incorporé ou un backslash littéral, malgré son rôle central dans cette story — deux tests ajoutés [tests/test_render.py]

**Reporté (0) :** aucun.

**Rejeté comme bruit (4) :**

- « `rendre()` et `rendre_markdown()` journalisent chacun l'avertissement « registre inconnu » via leur propre appel à `_grouper_par_registre` — un run avec un registre mal configuré le journalise donc deux fois » — un correctif propre exigerait soit de changer la signature publique de `rendre()`/`rendre_markdown()` pour leur passer un regroupement déjà calculé (changement disproportionné pour un bruit de log), soit un drapeau persistant qui supprimerait à tort un avertissement réellement nouveau lors d'un run ultérieur non lié. Bruit de journalisation mineur, pas un défaut fonctionnel — non corrigé.
- « Le risque `.nojekyll`/Jekyll (signalé dans les Dev Notes de cette story) s'étend maintenant aussi aux fichiers d'archive » — déjà un prérequis d'infrastructure reconnu et suivi (pas du code) ; un `.nojekyll` désactive Jekyll pour tout le dépôt de sortie, couvrant déjà implicitement `index.html` et l'archive à la fois.
- « Pas de paramètre pour surcharger la date de l'archive sur `executer()` (rattrapage/rejeu futur) » — explicitement hors périmètre de cette story (« aucun rattrapage rétroactif »), déjà acté dans les Dev Notes.
- « Lignes vides un peu désordonnées dans le rendu de `digest.md.j2` » — cosmétique, sans effet sur le rendu Markdown, qualifié de « sans conséquence » par le relecteur lui-même ; aucun AC concerné.

Suite complète revérifiée verte après application des correctifs : **323 tests** (314 avant revue).

## Dev Notes

### Pourquoi un environnement Jinja2 séparé pour le Markdown

`_environnement_jinja()` (Story 1.8) active l'autoescaping pour tout template dont l'extension **ou le nom complet** correspond à `("html", "xml", "j2")` — ajout nécessaire à l'époque parce que `digest.html.j2` se termine par `.j2`, pas `.html`. Mais `digest.md.j2` se termine *aussi* par `.j2` : réutiliser cet environnement tel quel activerait l'échappement **HTML** sur un template Markdown — un `&` deviendrait `&amp;` dans le fichier `.md` publié, ce qui est incorrect pour ce format de sortie (l'échappement HTML et l'échappement Markdown ne partagent presque aucune règle). D'où `_environnement_jinja_markdown()`, distinct, `autoescape=False`, avec un échappement Markdown appliqué **explicitement** via le filtre `markdown_safe` sur chaque champ de source externe (titre, accroche) — jamais implicitement.

### Pourquoi envelopper les liens Markdown entre `<...>`

`[texte](url)` est la syntaxe de lien la plus commune, mais elle interprète la première parenthèse fermante comme la fin de la destination — une URL Wikipédia typique (`https://fr.wikipedia.org/wiki/Exemple_(desambiguation)`) casserait le lien en un texte à moitié interprété. La syntaxe alternative `[texte](<destination>)` (CommonMark) n'a pas ce problème : entre `<` et `>`, les parenthèses ne sont pas spéciales. `render._url_surs()` (Story 1.8) reste le garde-fou de schéma, réutilisé tel quel — cette story ajoute seulement l'enveloppe `<...>` propre au Markdown, pas un second contrôle de schéma.

### Pourquoi `_grouper_par_registre` est extrait de `rendre()`

`rendre()` (HTML) et `rendre_markdown()` (Markdown) doivent produire le **même** regroupement par registre — même ordre, même garde-fou sur un registre inconnu (journalisé une fois, Story 1.8). Dupliquer cette logique dans les deux fonctions risquerait de les faire diverger silencieusement à la prochaine modification de l'une des deux (un correctif appliqué à l'une, oublié dans l'autre). Extraction en fonction partagée : refactor pur, sans changement de comportement observable pour `rendre()` — les 17 tests existants n'ont pas besoin d'être modifiés, seulement revérifiés verts.

### Pourquoi `.nojekyll` (prérequis à ajouter, pas du code)

Trouvé pendant la conception de cette story, concerne **aussi** l'`index.html` déjà publié en Story 1.8 : GitHub Pages traite par défaut le contenu d'un dépôt avec **Jekyll**, qui applique son propre moteur de templates (Liquid, `{{ }}`/`{% %}`) à `.html` et `.md` — un titre de source externe contenant littéralement `{{ 7*7 }}` pourrait être évalué par Jekyll au moment de la construction de la page, indépendamment de tout ce que `render.py`/Jinja2 font correctement de leur côté (Jekyll intervient *après*, sur le fichier déjà produit). La protection standard est un fichier `.nojekyll` vide à la racine du dépôt de sortie, qui désactive ce traitement. **Ce n'est pas du code** — un fichier à créer une fois dans le dépôt de sortie (`gh api`/manuellement), à ajouter à la liste des prérequis de publication de la Story 1.8 (dépôt + Pages) au moment où ce dépôt sera effectivement créé. Aucune tâche de cette story ne dépend de ce prérequis pour être développée/testée (mêmes raisons que Story 1.8 : clients simulés).

### Pourquoi la date de l'archive vient de `datetime.now(timezone.utc)`, pas d'un paramètre séparé

Un seul relevé d'horloge par run (`maintenant`, déjà utilisé par `rendre()` depuis la Story 1.8) sert à la fois d'horodatage affiché sur la page **et** de date de fichier pour l'archive (`maintenant.date()`) — cohérent avec la convention d'architecture (dates ISO 8601, UTC en interne, Dakar = UTC+0 donc identique) et évite deux sources de vérité temporelle dans le même run.

### Précédents à réutiliser, pas à réinventer

- **`render._url_surs`** (Story 1.8) — garde-fou de schéma, identique pour le lien HTML et le lien Markdown.
- **`filter.CHAMPS_QUOTAS`/`render.LIBELLES_REGISTRE`** (Stories 1.5/1.8) — ordre et libellés des sections, communs aux deux sorties via `_grouper_par_registre`.
- **`publish._client()`/isolation réseau** (Story 1.8) — `_publier()` (nouveau, Task 2) en hérite directement ; `publier`/`publier_archive` n'ont qu'à fournir le chemin et le contenu.
- **Résolution de jeton à deux niveaux** (`GITHUB_TOKEN` puis `gh auth token`, Story 1.8) — inchangée, partagée par les deux publications.

### Hors périmètre — ne pas anticiper

- **Aucune infrastructure de recherche dédiée** (index, moteur de recherche plein texte) — AC6 est satisfait par la nature même de fichiers Markdown en clair dans un dépôt versionné ; en ajouter une serait une généralité spéculative non demandée.
- **Aucun rattrapage rétroactif** des digests déjà publiés avant cette story (il n'y en a pas eu de réel, `pipeline.py` n'a jamais tourné en production) — cette story ne fait qu'archiver à partir de maintenant.
- **`.nojekyll`, création du second dépôt, activation de GitHub Pages** — toujours des prérequis d'infrastructure non exécutés (Story 1.8), pas du code de cette story.
- **Bandeau d'échec nocturne** — toujours Epic 3 (état de run persistant requis, `store.py`/SQLite pas construit).
- **Modifier `AD-11`/l'état « déjà vu »** — Epic 3, SQLite non construit ; cette story ne touche à aucun état persistant.

### Structure de fichiers

```text
src/veille/
  render.py                  # MODIFIÉ — _grouper_par_registre (extrait), _echapper_markdown, _environnement_jinja_markdown, rendre_markdown
  publish.py                  # MODIFIÉ — CHEMIN_PAGE (renommé), _sha_existant(client, chemin), _publier (extrait), publier_archive, _avertir_echec_publication(quoi)
  pipeline.py                 # MODIFIÉ — rendre_markdown + publier_archive câblés, un seul horodatage
templates/
  digest.md.j2                # NOUVEAU
tests/
  test_render.py              # MODIFIÉ — tests de rendre_markdown
  test_publish.py             # MODIFIÉ — tests de publier_archive
  test_pipeline.py            # MODIFIÉ — vérifie les deux PUT (page + archive)
```

### Testing Standards

- `pytest`, via `uv run pytest`. Aucun appel réseau ni subprocess réel — mêmes conventions établies en Story 1.8 (clients simulés, résolution de jeton monkeypatchée).
- **Audit par mutation en Task 4, template compris** — leçon des Stories 1.4/1.5/1.7/1.8, à ne pas répéter une cinquième fois par omission.
- Refactors de Task 1/2 (`_grouper_par_registre`, `_publier`) : re-exécuter la suite **existante** de `test_render.py`/`test_publish.py` sans la modifier, pour confirmer qu'aucun comportement observable n'a changé, avant d'ajouter les nouveaux tests.

### Previous Story Intelligence (Story 1.8)

- `render.py` existe : `LIBELLES_REGISTRE`, `_url_surs`, `_environnement_jinja`, `rendre`. Le piège `.j2`/autoescape déjà documenté et corrigé — cette story introduit un second piège du même ordre (autoescape HTML appliqué à tort à un template non-HTML), à ne pas répéter.
- `publish.py` existe : `PUBLISH_REPO`, `_jeton_depuis_env`/`_jeton_depuis_gh_cli`/`_jeton`, `_client`, `_sha_existant`, `publier`, `_avertir_echec_publication`. Le second dépôt de sortie n'est toujours pas créé — sans conséquence pour le développement (clients simulés), seule la validation réelle de bout en bout reste différée, comme pour `ANTHROPIC_API_KEY` en Story 1.6.
- `pipeline.py` existe : `executer()` enveloppe déjà tout son corps d'un filet de sécurité (trouvé en revue de la Story 1.8) — les nouveaux appels (`rendre_markdown`, `publier_archive`) en bénéficient automatiquement, aucun filet supplémentaire à ajouter.
- Convention de commit établie (Stories 1.4-1.8) : un commit pour l'implémentation + revue de la story, un commit séparé pour la mise à jour de `docs/rapport-projet.md`, tous deux poussés vers `origin/main`.
- Les dossiers `_bmad/`, `.claude/`, `_bmad-output/` sont suivis par git depuis la réintégration du 2026-08-28 — `git add -A` couvre tout, ne pas oublier ce fichier de story dans le commit d'implémentation.

### Git Intelligence Summary

Commits récents : Story 1.8 (implémentation + revue, un commit), rapport de projet (commit séparé), avant cela la réintégration des dossiers BMad (commit isolé, hors cycle de story). Même convention à reproduire ici : un commit pour l'implémentation + revue de la Story 1.9, un commit séparé pour le rapport.

### Project Structure Notes

Aligné avec le Structural Seed de `ARCHITECTURE-SPINE.md` : `templates/digest.md.j2` et `site/archive/YYYY-MM-DD.md` sont exactement les chemins qu'il prévoit. Aucun écart à documenter.

### References

- [Source: epics.md#Story-1.9] — story d'origine et critères d'acceptation
- [Source: epics.md#FR10] — archive Markdown versionnée, cherchable par texte
- [Source: ARCHITECTURE-SPINE.md#AD-8] — page et archive partagent le même dépôt
- [Source: ARCHITECTURE-SPINE.md#AD-9] — idempotence du job nocturne, upsert par date
- [Source: ARCHITECTURE-SPINE.md#Structural-Seed] — chemins `templates/digest.md.j2`, `site/archive/YYYY-MM-DD.md`
- [Source: 1-8-publication-page.md] — `render.py`/`publish.py`/`pipeline.py` existants, piège `.j2`/autoescape, garde-fou de schéma d'URI, décision du second dépôt de sortie
- [Source: deferred-work.md] — dépôt de sortie et GitHub Pages toujours non créés (prérequis d'infrastructure)

## Dev Agent Record

### Agent Model Used

claude-sonnet-5 (Sonnet 5)

### Debug Log References

Aucun blocage. Deux corrections d'assertions de test trouvées et corrigées en cours de route (pas des bugs d'implémentation) : l'échappement Markdown du point final (`.`) fait apparemment échouer des assertions qui vérifiaient une sous-chaîne non échappée — corrigé en retirant la ponctuation finale des chaînes de test concernées (comportement d'échappement lui-même correct, CommonMark rend `\.` comme un `.` littéral). Et la fausse réponse HTTP locale de `test_pipeline.py` ne levait jamais sur un code d'erreur (`raise_for_status` était un no-op) — corrigée pour refléter le vrai comportement de `httpx.Response`, trouvé en écrivant le test de dégradation partielle de la Task 3.

### Completion Notes List

- **Deux refactors purs vérifiés avant tout ajout de fonctionnalité** : `_grouper_par_registre` (extrait de `render.rendre()`) et `_publier`/`_sha_existant(chemin)` (extraits de `publish.publier()`) — dans les deux cas, la suite de tests existante a été rejouée verte sans la moindre modification avant d'écrire le code neuf, pour confirmer qu'aucun comportement observable n'avait changé.
- **Piège Jinja2 anticipé dès la conception de la story, confirmé à l'implémentation** : réutiliser `_environnement_jinja()` (autoescape HTML, Story 1.8) pour le template `digest.md.j2` aurait produit des entités HTML erronées dans l'archive Markdown, `digest.md.j2` se terminant lui aussi par `.j2`. Environnement Jinja2 séparé (`_environnement_jinja_markdown`), autoescape désactivé, échappement Markdown explicite via le filtre `markdown_safe`.
- **Enveloppe `<...>` des liens Markdown** : une URL contenant des parenthèses (ex. `https://fr.wikipedia.org/wiki/Exemple_(test)`, cas réel testé) casserait `[texte](url)` sans elle — vérifié par test dédié et par un mutant qui la retire (tué).
- **`pipeline.executer()` publie désormais la page et l'archive à partir du même relevé d'horloge** (`maintenant`), toutes deux tentées indépendamment même si l'une échoue (`page_ok and archive_ok`) — vérifié par un test où l'archive échoue seule (500) et où les deux `PUT` sont malgré tout constatés.
- **Audit par mutation (Task 4)** : 4 mutants, tous tués du premier coup après correction des deux artefacts de test mentionnés ci-dessus (Debug Log). Aucun faux positif de type `__pycache__` cette fois — cache vidé systématiquement entre chaque mutation, leçon retenue de la Story 1.8.
- **Exécution réelle sans clé API ni jeton GitHub** : `rendre_markdown()` (lot construit à la main) et `pipeline.executer()` (chemin complet, vraie collecte RSS sur une fixture de test, aucune clé/jeton résolu) dégradent tous deux proprement — `False`, aucune exception, avertissements journalisés une seule fois chacun.
- Suite complète après implémentation (avant revue) : **314 tests** (299 avant cette story : +8 Task 1, +6 Task 2, +1 net Task 3).
- **Revue (Sonnet 5)** : ensemble de caractères Markdown échappés corrigé dans les deux sens à la fois — `<` manquant (constat convergent Acceptance Auditor + Edge Case Hunter, un `<img ...>` de source externe restait une vraie balise HTML brute) et `#`/`-`/`+`/`.` en trop (constat convergent Acceptance Auditor + Blind Hunter, cassaient l'AC6 « cherchable par texte » pour un cas aussi courant qu'un nom de modèle versionné). Un test écrit pendant la revue (`test_rendre_markdown_libelle_de_section_echappe`) s'est révélé tester un chemin en réalité **inatteignable** via l'API publique — `LIBELLES_REGISTRE.get(registre, registre)` n'est jamais appelé avec un registre hors de `CHAMPS_QUOTAS`, puisque `sections` n'itère que sur ces 3 valeurs déjà toutes présentes dans `LIBELLES_REGISTRE` ; le correctif défensif (`markdown_safe` sur `libelle`) a été conservé (coût nul), le test supprimé plutôt que laissé à donner une fausse impression de couverture. Correctif de robustesse le plus significatif : `pipeline.executer()` publie désormais la page **avant** de même tenter de rendre l'archive — sans cet ordre, un `rendre_markdown()` qui lève après un `rendre()` réussi aurait fait perdre une page déjà prête, contredisant la propre docstring de la fonction. Vérifié par mutation manuelle (contenus HTML/Markdown inversés entre les deux publications) que le test durci de corrélation contenu↔chemin l'attrape bien.
- Suite complète finale après revue : **323 tests** (314 avant revue).

### File List

**Code :**
- `src/veille/render.py` — modifié : `_grouper_par_registre` (extrait, refactor pur), `_echapper_markdown` (revue : `<` ajouté, `#`/`-`/`+`/`.` retirés, sauts de ligne neutralisés), `_url_surs` (revue : rejette aussi `<`/`>` littéraux), `_environnement_jinja_markdown`, `rendre_markdown`
- `src/veille/publish.py` — modifié : `CHEMIN_FICHIER` renommé `CHEMIN_PAGE`, `_sha_existant(client, chemin)` paramétrée, `_publier` (extrait, refactor), `publier_archive`, `_avertir_echec_publication(quoi, categorie)` (revue : trace complète par catégorie, pas un booléen global)
- `src/veille/pipeline.py` — modifié : `executer()` publie la page et l'archive à partir d'un même horodatage, retour `page_ok and archive_ok` ; revue : page publiée avant le rendu de l'archive (un échec de `rendre_markdown()` ne fait plus perdre une page déjà réussie)

**Templates :**
- `templates/digest.md.j2` — nouveau ; revue : libellé de section passé par `markdown_safe`

**Tests :**
- `tests/test_render.py` — étendu : 32 tests (17 existants + 8 Task 1 + 7 net en revue : 8 ajoutés, 1 supprimé — testait un chemin en réalité inatteignable via l'API publique, voir Completion Notes)
- `tests/test_publish.py` — étendu : 19 tests (12 existants + 6 Task 2 + 1 en revue, trace complète par catégorie)
- `tests/test_pipeline.py` — étendu : 6 tests (5 après la Task 3 + 1 en revue : la page survit à un échec de rendu de l'archive) ; un test existant durci pour corréler contenu et chemin de publication ; `_FakeResponse.raise_for_status` corrigée pour lever réellement sur erreur

### Change Log

| Date | Modification |
|------|--------------|
| 2026-08-31 | Implémentation complète (Tasks 1-4) : `rendre_markdown`/`templates/digest.md.j2` (archive Markdown, échappement dédié, liens `<...>`), `publier_archive` (chemin daté `site/archive/YYYY-MM-DD.md`, upsert AD-9), `pipeline.py` câblé (page + archive, un seul horodatage, les deux tentées indépendamment). Deux refactors purs (`_grouper_par_registre`, `_publier`) vérifiés sans régression avant tout ajout. Audit par mutation à 4 mutants, tous tués. Exécution réelle en dégradation confirmée (sans clé Anthropic ni jeton GitHub). 314 tests. Statut → review. |
| 2026-08-31 | Revue de code (Sonnet 5, 3 couches, même modèle que l'implémentation). 9 correctifs, 0 reporté, 4 rejetés : ensemble de caractères Markdown échappés corrigé dans les deux sens (`<` ajouté — balise HTML brute non neutralisée ; `#`/`-`/`+`/`.` retirés — cassaient l'AC6 « cherchable par texte », constats convergents des 3 couches) ; sauts de ligne neutralisés ; page publiée avant le rendu de l'archive (ne plus perdre une page réussie si l'archive lève) ; trace complète par catégorie (page/archive) plutôt qu'un booléen global ; `_url_surs` rejette aussi les chevrons littéraux ; libellé de section échappé par cohérence ; test de publication durci pour corréler contenu et chemin (vérifié par mutation) ; couverture de test étendue pour la parité HTML/Markdown. 323 tests. Statut → done. |
