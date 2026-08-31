"""Rendu HTML du digest (FR-9, Story 1.8).

Regroupe les `Entree` retenues par registre et produit la page publiée à
partir du template Jinja2 `templates/digest.html.j2`. Aucune logique de
scoring, de filtrage ni d'appel réseau ici — seulement de la mise en forme
sur des `Entree` déjà produites par `filter.py`/`enrich/llm.py`.
"""

import logging
import re
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from veille.filter import CHAMPS_QUOTAS
from veille.models import Entree

logger = logging.getLogger(__name__)

# Résolu depuis l'emplacement du module, pas depuis le répertoire courant —
# même raison que `config.chemin_config` : un run lancé par un planificateur
# de tâches (Epic 3) ne garantit aucun CWD particulier.
TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"

# Libellés d'affichage, dans l'ordre canonique déjà établi par les quotas
# (Story 1.5) — réutilisé tel quel, jamais un second ordre redéfini ailleurs.
LIBELLES_REGISTRE: dict[str, str] = {
    "apprendre": "Apprendre",
    "ce_qui_bouge": "Ce qui bouge",
    "pour_le_metier": "Pour le métier",
}

# Schémas d'URI qu'un lien publié peut légitimement porter — jamais
# `javascript:`/`data:`/autre schéma exécutable (trouvé en revue). Comparaison
# insensible à la casse : les navigateurs exécutent `JavaScript:...` aussi
# bien que `javascript:...`.
_SCHEMES_AUTORISES = ("http://", "https://")


def _url_surs(url: str) -> str | None:
    """Ne renvoie l'URL que si son schéma est http(s) et qu'elle ne porte
    aucun `<`/`>` littéral, sinon `None`.

    `Item.url` est du contenu de source externe non fiable (RSS/API/scraping,
    aucune source ne le valide) — l'autoescaping HTML de Jinja2 neutralise
    les métacaractères (`<`, `"`, ...) mais ne valide jamais le **schéma**
    d'une URI. Un flux compromis déclarant `<link>javascript:alert(1)</link>`
    produirait donc un lien cliquable exécutable malgré l'échappement actif,
    contournant entièrement AC8 sans jamais toucher un métacaractère.

    Le rejet de `<`/`>` (trouvé en revue de la Story 1.9) sert le template
    Markdown : `rendre_markdown()` enveloppe la destination entre `<...>`
    (syntaxe CommonMark qui tolère les parenthèses dans une URL) — une URL
    contenant elle-même un `<`/`>` littéral fermerait cette enveloppe
    prématurément, faisant fuiter le reste de l'URL comme texte du
    document. Sans conséquence pour le HTML (Jinja2 échappe déjà `<`/`>`
    dans un attribut), donc partagé sans risque entre les deux gabarits.

    Un schéma refusé, ou des chevrons littéraux, se traitent comme une URL
    vide (AC13) : pas de lien, texte seul.
    """
    if url and url.lower().startswith(_SCHEMES_AUTORISES) and "<" not in url and ">" not in url:
        return url
    return None


# Caractères qui portent une signification syntaxique en Markdown (CommonMark)
# **indépendamment de leur position** dans le texte — backtick, emphase,
# accolades/crochets/parenthèses (texte et destination de lien/image),
# point d'exclamation (image), barre (tableau GFM), tilde (barré), chevrons
# (balise HTML brute/autolien). Un titre de source externe qui en contient
# reformaterait involontairement l'archive (ex. `*Alerte*` deviendrait de
# l'italique, `<img ...>` une vraie balise HTML — trouvé en revue, `<`
# manquait initialement) sans cet échappement.
#
# `#`, `-`, `+`, `.` en sont volontairement **exclus** (trouvé en revue) :
# ils ne sont syntaxiquement significatifs qu'en tout début de ligne (titre,
# puce, liste numérotée) — jamais atteignable ici puisque le texte est
# toujours inséré au milieu d'une puce déjà ouverte, et que
# `_echapper_markdown` neutralise par ailleurs les sauts de ligne qui
# auraient pu les y replacer. Les échapper quand même casserait l'AC6
# (« cherchable par texte ») pour un cas aussi courant qu'un nom de modèle
# versionné (« GPT-5.2 ») ou une date.
_CARACTERES_MARKDOWN_SPECIAUX = re.compile(r"([\\`*_{}\[\]()!|~<>])")


def _echapper_markdown(texte: str) -> str:
    """Échappe les caractères spéciaux Markdown d'un texte de source externe
    (Story 1.9) — jamais implicite, contrairement à l'autoescaping HTML de
    Jinja2 qui ne s'applique pas ici (voir `_environnement_jinja_markdown`).

    Les sauts de ligne incorporés sont remplacés par un espace (trouvé en
    revue) : sans ça, un caractère normalement inerte en milieu de texte
    (`-`, `#`...) se retrouverait en tout début d'une nouvelle ligne, où il
    redevient syntaxiquement actif — et la structure de liste de l'archive
    (une entrée par puce) serait de toute façon rompue par une ligne
    orpheline hors de la puce.

    `None` ou vide → chaîne vide, ne lève jamais.
    """
    if not texte:
        return ""
    texte = texte.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    return _CARACTERES_MARKDOWN_SPECIAUX.sub(r"\\\1", texte)


def _environnement_jinja() -> Environment:
    """Construit l'environnement Jinja2 — autoescaping **explicite**.

    Piège évité ici (trouvé lors de la création de cette story) :
    `select_autoescape()` sans argument ne reconnaît que les noms de
    template finissant par `.html`/`.htm`/`.xml`/`.xhtml`. Le template
    s'appelle `digest.html.j2` : son extension au sens de cette fonction est
    `.j2`, absente de la liste par défaut — l'échappement serait
    silencieusement désactivé malgré le `.html` dans le nom. `.j2` est donc
    ajouté explicitement à `enabled_extensions`, sans quoi tout contenu de
    source externe (`titre`, `contenu_brut` via `accroche`) serait injecté
    tel quel dans la page publiée (AC8).
    """
    environnement = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(enabled_extensions=("html", "xml", "j2")),
    )
    environnement.globals["url_surs"] = _url_surs
    return environnement


def _environnement_jinja_markdown() -> Environment:
    """Environnement Jinja2 **séparé** de `_environnement_jinja()`, dédié au
    template Markdown (Story 1.9).

    Piège évité ici : `_environnement_jinja()` active l'autoescaping HTML
    pour tout template dont le nom se termine par `.j2` (ajouté en Story
    1.8 précisément parce que `digest.html.j2` se termine par `.j2`, pas
    `.html`). Mais `digest.md.j2` se termine *aussi* par `.j2` — réutiliser
    le même environnement produirait des entités HTML (`&amp;`) erronées
    dans un fichier Markdown, l'échappement HTML et Markdown ne partageant
    presque aucune règle. L'échappement Markdown est donc appliqué
    **explicitement** via le filtre `markdown_safe`, jamais par autoescape.
    """
    environnement = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=False)
    environnement.filters["markdown_safe"] = _echapper_markdown
    environnement.globals["url_surs"] = _url_surs
    return environnement


def _grouper_par_registre(
    entrees: list[Entree],
) -> tuple[list[tuple[str, str, list[Entree]]], bool]:
    """Regroupe les `Entree` par registre, dans l'ordre canonique
    `filter.CHAMPS_QUOTAS`, et calcule `digest_vide`.

    Extrait de `rendre()` (Story 1.9) : `rendre()` (HTML) et
    `rendre_markdown()` (Markdown) doivent produire le **même**
    regroupement et le même garde-fou sur un registre inconnu — les
    dupliquer risquerait de les faire diverger silencieusement à la
    prochaine modification de l'un des deux.

    Un registre absent de `CHAMPS_QUOTAS` (typo dans `sources.yaml` :
    `repartir_par_quotas`, Story 1.5, conserve sans limite un registre
    qu'il ne connaît pas — donc bel et bien atteignable ici, trouvé en
    revue de la Story 1.8) est journalisé une fois plutôt que
    silencieusement perdu. `digest_vide` reflète les sections
    **réellement peuplées**, pas seulement la non-vacuité de `entrees` —
    sinon une entrée ainsi égarée ne serait affichée nulle part, ni dans
    une section, ni dans le message « rien à signaler ».
    """
    par_registre: dict[str, list[Entree]] = {registre: [] for registre in CHAMPS_QUOTAS}
    for entree in entrees:
        registre = entree.item.registre
        if registre not in par_registre:
            logger.warning(
                "Entrée '%s' avec un registre inconnu ('%s') — absente du "
                "rendu (aucune des %d sections publiées ne le reconnaît).",
                entree.item.guid,
                registre,
                len(CHAMPS_QUOTAS),
            )
        par_registre.setdefault(registre, []).append(entree)

    sections = [
        (registre, LIBELLES_REGISTRE.get(registre, registre), par_registre.get(registre, []))
        for registre in CHAMPS_QUOTAS
    ]
    digest_vide = not any(entrees_section for _, _, entrees_section in sections)
    return sections, digest_vide


def rendre(entrees: list[Entree], date_generation: datetime) -> str:
    """Rend la page HTML du digest.

    Regroupe par `entree.item.registre`, dans l'ordre canonique
    `filter.CHAMPS_QUOTAS` (AC1, voir `_grouper_par_registre`). Une liste
    vide produit un message honnête plutôt qu'une page cassée ou
    silencieusement vide (AC9). Un titre vide se replie sur l'accroche
    pour l'en-tête affiché ; une URL vide, ou dont le schéma n'est pas
    http(s) (`_url_surs`, trouvé en revue), n'émet aucun lien cliquable
    (AC13, `Entree`/`Item` ne garantissent pas la non-vacuité de ces
    champs — cf. `deferred-work.md`).
    """
    sections, digest_vide = _grouper_par_registre(entrees)

    environnement = _environnement_jinja()
    template = environnement.get_template("digest.html.j2")
    return template.render(
        sections=sections,
        date_generation=date_generation,
        digest_vide=digest_vide,
    )


def rendre_markdown(entrees: list[Entree], date_generation: datetime) -> str:
    """Rend l'archive Markdown datée du digest (FR-10, Story 1.9).

    Même regroupement par registre que `rendre()` (`_grouper_par_registre`,
    partagé — pas un second regroupement qui pourrait diverger). Le titre
    et l'accroche sont échappés pour Markdown (`markdown_safe`, pas pour
    HTML : ce n'est pas la même cible), et le lien vers l'original enveloppe
    sa destination entre `<...>` dans le template — une URL contenant des
    parenthèses (fréquent, ex. Wikipédia) casserait sinon `[texte](url)`.
    """
    sections, digest_vide = _grouper_par_registre(entrees)

    environnement = _environnement_jinja_markdown()
    template = environnement.get_template("digest.md.j2")
    return template.render(
        sections=sections,
        date_generation=date_generation,
        digest_vide=digest_vide,
    )
