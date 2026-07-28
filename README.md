# Agent de veille tech

Un agent qui produit chaque nuit une page de veille — IA, data, informatique — prête à consulter au réveil sur mobile.

La page n'est pas un flux brut : c'est une couche d'**aiguillage** qui trie des centaines de sources jusqu'à huit items par jour, répartis en trois registres — apprendre, suivre l'actualité, rester employable — et pointe vers l'original pour qui veut approfondir.

## Pourquoi

Suivre l'IA en 2026 relève de l'impossible : il se publie chaque jour plus que ce qu'on peut lire en un mois. Les digests existants échouent souvent pour une raison précise — ils exigent de créer un nouveau moment dans la journée, et un moment qu'il faut créer finit toujours par ne pas l'être.

Ce projet part de là : la page doit coûter le moins d'effort possible à consulter, et **zéro effort à produire**. Elle est générée la veille au soir, disponible au réveil, à une URL fixe qu'on met en favori une fois pour toutes.

## Architecture

Pipeline en six étapes isolées (*pipes and filters*) :

```
collecte → dédoublonnage → filtrage/scoring → accroches FR → rendu → publication
```

Quelques décisions structurantes :

| Décision | Raison |
|---|---|
| Connecteurs derrière une interface uniforme | Ajouter une source RSS, API ou scrapée ne modifie jamais le pipeline |
| Sources et profil en **configuration**, pas en code | Re-régler le filtrage ne demande aucune modification de code |
| Isolation de panne par source *et* par entrée | Une source morte ou une entrée corrompue ne fait jamais perdre le reste |
| Frontière LLM unique | Un seul module appelle l'API — coût maîtrisé, modèle interchangeable |
| Filtrage agressif par conception | Mieux vaut une page maigre qu'une page bruyante |

## État d'avancement

- [x] **Story 1.1** — collecte d'une première source RSS, modèle d'item canonique, isolation de panne
- [x] **Story 1.2** — connecteurs API JSON et scraping derrière la même interface
- [ ] Story 1.3 — dédoublonnage inter-sources
- [ ] Stories 1.4-1.6 — filtrage, scoring par profil, quotas par section
- [ ] Stories 1.7-1.9 — accroches en français, publication, archive
- [ ] Epic 2 — socle élargi et robustesse aux pannes
- [ ] Epic 3 — génération nocturne automatique
- [ ] Epic 4 — santé des sources et découverte

## Stack

Python 3.11 · uv · feedparser · httpx · Jinja2 · SQLite · API Claude (Haiku)

## Démarrage

```bash
uv sync                          # installe les dépendances
uv run pytest                    # lance la suite de tests
uv run python -m veille.collect  # collecte les sources de config/sources.yaml
```

## Configuration

Les sources vivent dans `config/sources.yaml` — aucune modification de code n'est nécessaire pour en ajouter ou en retirer. Trois types sont disponibles :

```yaml
sources:
  # Flux RSS/Atom
  - id: openai-news
    type: rss
    url: https://openai.com/news/rss.xml
    langue: en
    registre: ce_qui_bouge

  # API JSON — la forme de l'API est décrite en configuration,
  # pas codée en dur : brancher une autre API n'exige aucun code.
  - id: hf-daily-papers
    type: json
    url: https://huggingface.co/api/daily_papers?limit=50
    langue: en
    registre: apprendre
    mapping:
      guid: paper.id
      titre: title
      date_publication: publishedAt
      contenu_brut: paper.summary
    url_modele: https://huggingface.co/papers/{guid}

  # Scraping — réservé aux sources sans flux ni API,
  # et uniquement lorsque le robots.txt l'autorise.
  - id: anthropic-news
    type: scrape
    url: https://www.anthropic.com/news
    langue: en
    registre: ce_qui_bouge
    selecteur: /news/
    base_url: https://www.anthropic.com
```

## Tests

```bash
uv run pytest -v
```

Les tests n'effectuent **aucun appel réseau** : ils s'appuient sur des fixtures locales, y compris pour les cas de flux malformés.
