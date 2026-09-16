"""Rendu HTML du digest (FR-9, Story 1.8).

Regroupe les `Entree` retenues par registre et produit la page publiée à
partir du template Jinja2 `templates/digest.html.j2`. Aucune logique de
scoring, de filtrage ni d'appel réseau ici — seulement de la mise en forme
sur des `Entree` déjà produites par `filter.py`/`enrich/llm.py`.
"""

import html
import logging
import re
from datetime import date, datetime
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


# Marqueurs stables délimitant le bandeau d'échec dans le HTML publié
# (Story 3.2) — permettent à `publish.publier_bandeau_echec` de le
# remplacer plutôt que de l'empiler sur plusieurs nuits d'échec
# consécutives (AC4), sans dépendre d'un état persistant : le HTML publié
# porte lui-même l'information de présence du bandeau.
BANDEAU_ECHEC_DEBUT = "<!-- BANDEAU-ECHEC:DEBUT -->"
BANDEAU_ECHEC_FIN = "<!-- BANDEAU-ECHEC:FIN -->"


def rendre_bandeau_echec(date_echec: date) -> str:
    """Fragment HTML signalant qu'aucune mise à jour n'a réussi cette
    nuit-là (Story 3.2, AC3).

    Ce n'est **pas** un document complet ni une page rendue par le chemin
    normal (`rendre()`) : un run qui échoue avant `rendre()` n'a par
    définition aucune `Entree` à lui donner. Ce fragment est destiné à être
    inséré après coup dans le HTML déjà publié par
    `publish.publier_bandeau_echec` — jamais rendu ni publié seul, donc pas
    de passage par Jinja2/l'autoescape habituel de ce fichier. Sans risque
    ici : `date_echec.strftime(...)` (déterministe) est la seule donnée
    insérée, jamais de contenu de source externe.

    Format de date (`%d/%m/%Y`, corrigé en revue) cohérent avec le reste du
    site (`digest.html.j2` : « Généré le JJ/MM/AAAA à HH:MM ») — l'ISO 8601
    initial (`AAAA-MM-JJ`) aurait juré visuellement avec le reste de la page.
    Couleurs via `var(--bandeau-echec-bg)`/`var(--bandeau-echec-fg)`
    (corrigé en revue) plutôt qu'en dur : ces variables sont déjà définies
    dans le `<style>` de `digest.html.j2` (clair/sombre via
    `prefers-color-scheme`, même système que `--recommandee-bg`) — le
    fragment s'insère dans une page qui les a déjà en portée, pas de raison
    de sortir de ce système de thème pour ce seul élément.
    """
    return (
        f"{BANDEAU_ECHEC_DEBUT}\n"
        '<div style="background:var(--bandeau-echec-bg);'
        "color:var(--bandeau-echec-fg);padding:0.75rem 1rem;"
        'border-radius:8px;margin:0 0 1rem;font-size:0.95rem;">\n'
        f"⚠️ Pas de nouveau digest dans la nuit du {date_echec.strftime('%d/%m/%Y')} "
        "— problème technique. Le digest ci-dessous reste le plus récent "
        "disponible.\n"
        "</div>\n"
        f"{BANDEAU_ECHEC_FIN}"
    )


# Marqueurs stables délimitant le récapitulatif des sources à surveiller
# dans le HTML publié (Story 4.3) — même principe que le bandeau d'échec :
# `publish.publier_recapitulatif_sante` les utilise pour remplacer le
# panneau plutôt que de l'empiler, ou pour le retirer une fois qu'il n'y a
# plus rien à signaler (AC4).
RECAPITULATIF_SANTE_DEBUT = "<!-- RECAPITULATIF-SANTE:DEBUT -->"
RECAPITULATIF_SANTE_FIN = "<!-- RECAPITULATIF-SANTE:FIN -->"


def rendre_recapitulatif_sante(sources: list) -> str:
    """Fragment HTML listant les sources actuellement `suspecte`/`en_sommeil`
    (Story 4.3, AC1) — destiné à être inséré/remplacé après coup dans le
    HTML déjà publié par `publish.publier_recapitulatif_sante`, jamais
    rendu ni publié seul (même patron que `rendre_bandeau_echec`).

    `sources` : `list[health.SourceASurveiller]` — non typé explicitement
    ici pour ne pas faire dépendre `render.py` de `health.py` (aucun autre
    import inter-module de ce sens dans le projet ; les deux attributs
    utilisés, `source_id`/`etat`/`raison`, sont de simples chaînes).

    N'est **jamais** appelée avec une liste vide (décision de l'appelant,
    `publish.publier_recapitulatif_sante` : une liste vide signifie
    retirer le panneau existant, pas publier un panneau vide) — **imposé**
    ici, pas seulement documenté (trouvé en revue, convergence blind+edge :
    le contrat n'était vérifié que par la discipline du seul appelant
    existant, un futur appel direct avec une liste vide aurait rendu un
    panneau « 0 source(s) à surveiller » silencieusement absurde plutôt
    que d'échouer bruyamment).

    `source_id`/`raison`/`etat` échappés via `html.escape` (défensif :
    `source_id` vient de `sources.yaml`, de la configuration plutôt que
    d'une source externe, mais rien ne garantit qu'il ne contient jamais
    de caractère spécial HTML — coût nul, jamais de raison de ne pas
    échapper une chaîne insérée telle quelle dans un document HTML).
    """
    if not sources:
        raise ValueError(
            "rendre_recapitulatif_sante() ne doit jamais être appelée avec une "
            "liste vide — l'appelant doit retirer le panneau existant plutôt "
            "que d'en publier un vide (voir publish.publier_recapitulatif_sante)."
        )
    lignes_html = "\n".join(
        "<li><strong>{id}</strong> — {etat} : {raison}</li>".format(
            id=html.escape(s.source_id),
            etat=html.escape(s.etat),
            raison=html.escape(s.raison),
        )
        for s in sources
    )
    return (
        f"{RECAPITULATIF_SANTE_DEBUT}\n"
        '<div style="background:var(--recapitulatif-bg);'
        "color:var(--recapitulatif-fg);padding:0.75rem 1rem;"
        'border-radius:8px;margin:0 0 1rem;font-size:0.95rem;">\n'
        f"🔎 {len(sources)} source(s) à surveiller :\n"
        f"<ul style=\"margin:0.5rem 0 0;padding-left:1.25rem;\">\n{lignes_html}\n</ul>\n"
        "</div>\n"
        f"{RECAPITULATIF_SANTE_FIN}"
    )
