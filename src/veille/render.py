"""Rendu HTML du digest (FR-9, Story 1.8).

Regroupe les `Entree` retenues par registre et produit la page publiée à
partir du template Jinja2 `templates/digest.html.j2`. Aucune logique de
scoring, de filtrage ni d'appel réseau ici — seulement de la mise en forme
sur des `Entree` déjà produites par `filter.py`/`enrich/llm.py`.
"""

import html
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from veille.config import FORMAT_DEFAUT, SourceConfig
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

# Libellé et pictogramme de chaque format de contenu (audit du 2026-09-22).
# Un épisode de podcast de 50 minutes et une brève de 2 minutes étaient
# rendus à l'identique : sur une page dont toute la promesse est « 5 minutes
# le matin », l'engagement demandé est une information de premier plan.
#
# Pictogrammes en SVG inline plutôt qu'en emoji ou en police d'icônes :
# l'emoji dépend du jeu installé sur le téléphone (rendu coloré incohérent
# d'un appareil à l'autre), une police d'icônes demande une requête réseau
# que la page n'a aucune raison de payer. Le SVG hérite de `currentColor`,
# donc suit le thème clair/sombre sans réglage supplémentaire.
#
# Seuls les tracés figurent ici ; les attributs de trait sont portés par le
# gabarit. Les y mettre aussi aurait imposé un `|safe` sur une chaîne
# contenant des guillemets — l'autoescaping les aurait transformés en
# entités au milieu d'une balise ouvrante, produisant un SVG cassé.
FORMATS: dict[str, tuple[str, str]] = {
    "article": (
        "Article",
        '<path d="M4 5h11v14H4z"/><path d="M15 9h5v8a2 2 0 0 1-2 2h-3"/>'
        '<path d="M7 9h5M7 12h5M7 15h3"/>',
    ),
    "podcast": (
        "Podcast",
        '<rect x="9" y="3" width="6" height="11" rx="3"/>'
        '<path d="M5 11a7 7 0 0 0 14 0"/><path d="M12 18v3"/>',
    ),
    "papier": (
        "Papier",
        '<path d="M3 5h6a3 3 0 0 1 3 3v11a2 2 0 0 0-2-2H3z"/>'
        '<path d="M21 5h-6a3 3 0 0 0-3 3v11a2 2 0 0 1 2-2h7z"/>',
    ),
    "video": (
        "Vidéo",
        '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M10 9.5l5 2.5-5 2.5z"/>',
    ),
    "release": (
        "Release",
        '<path d="M3 12V5a2 2 0 0 1 2-2h7l9 9-9 9z"/><circle cx="7.5" cy="7.5" r="1.5"/>',
    ),
}

# Au-delà de ce nombre de jours, l'âge d'une entrée est signalé visuellement
# (audit du 2026-09-22). Volontairement plus large que l'horizon de
# `filter.HORIZON_FRAICHEUR_DEFAUT` : les sources à cadence lente déclarent
# légitimement un horizon plus long, et leur contenu n'a rien d'anormal —
# ce seuil ne marque que ce qui mérite d'être vu comme « pas de cette
# semaine » avant de cliquer.
SEUIL_AGE_SIGNALE = 21

_MOIS = (
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)
_JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")


def _date_lisible(valeur: datetime | date, avec_jour: bool = False) -> str:
    """Date en toutes lettres, en français, sans dépendance à la locale
    du système (audit du 2026-09-22).

    `strftime("%d %B %Y")` produirait « September » sur un runner GitHub
    Actions, dont la locale est C/POSIX : la page publiée serait en partie
    en anglais sans qu'aucun test local ne le montre, la machine de
    développement étant, elle, en français.
    """
    base = f"{valeur.day} {_MOIS[valeur.month - 1]} {valeur.year}"
    return f"{_JOURS[valeur.weekday()]} {base}" if avec_jour else base


def _libelle_age(publication: datetime, maintenant: datetime) -> tuple[str, int]:
    """Âge lisible (« hier », « il y a 3 semaines ») et âge en jours.

    Une date postérieure à `maintenant` (horloge de source en avance, fuseau
    mal déclaré — cas déjà connu de `health.py`, Story 4.2) est présentée
    comme « aujourd'hui » plutôt que par un nombre de jours négatif : le
    lecteur n'a rien à faire de l'anomalie, et `filtrer_par_fraicheur` a déjà
    décidé de conserver l'item.
    """
    jours = (maintenant - publication).days
    if jours <= 0:
        return "aujourd'hui", max(jours, 0)
    if jours == 1:
        return "hier", 1
    if jours <= 7:
        return f"il y a {jours} jours", jours
    if jours <= 30:
        semaines = jours // 7
        return f"il y a {semaines} semaine{'s' if semaines > 1 else ''}", jours
    mois = max(jours // 30, 1)
    return f"il y a {mois} mois", jours


@dataclass(frozen=True)
class EntreeRendue:
    """Une `Entree` accompagnée de tout ce que la page doit en montrer.

    Introduit par l'audit du 2026-09-22 : la page n'affichait que le titre,
    l'accroche et le lien — ni la source (pourtant exigée par FR-7 et
    UX-DR2, perdue dans la réécriture de l'AC1 de la Story 1.8), ni la date
    (si bien qu'un article vieux de sept mois avait exactement la même tête
    qu'une annonce du jour), ni le format.

    Calculé dans ce module plutôt que dans le gabarit : un gabarit Jinja2
    n'est pas testable unitairement, alors que ces règles (repli du nom sur
    l'`id`, format inconnu, date dans le futur) en méritent chacune un.
    """

    entree: Entree
    titre: str
    url: str | None
    nom_source: str
    format: str
    libelle_format: str
    pictogramme: str
    age: str
    age_jours: int
    date_iso: str
    date_lisible: str

    @property
    def recommandee(self) -> bool:
        return self.entree.recommandee

    @property
    def accroche(self) -> str:
        return self.entree.accroche

    @property
    def est_ancienne(self) -> bool:
        return self.age_jours > SEUIL_AGE_SIGNALE


def _preparer_entree(
    entree: Entree, sources: dict[str, SourceConfig], maintenant: datetime
) -> EntreeRendue:
    """Assemble la vue d'une entrée. Ne lève jamais : chaque champ
    facultatif a un repli explicite (nom → `source_id`, format inconnu →
    `FORMAT_DEFAUT`, titre vide → accroche, URL non http(s) → pas de lien)."""
    source = sources.get(entree.item.source_id)
    # `.strip()` ici en plus de `config._normaliser` (trouvé en écrivant
    # les tests de l'audit) : un `nom` composé d'espaces est *truthy*, et
    # un `SourceConfig` construit à la main ne passe pas par la
    # normalisation du chargeur — la page affichait alors un blanc à la
    # place de la source. Même piège de « clé blanche » que
    # `publish._jeton_depuis_env` (trouvé en revue de la Story 1.6).
    nom = (source.nom.strip() if source and source.nom else "") or entree.item.source_id

    format_declare = (source.format if source else FORMAT_DEFAUT) or FORMAT_DEFAUT
    if format_declare not in FORMATS:
        # Atteignable hors `load_sources` (qui normalise déjà) : un appelant
        # construisant un `SourceConfig` à la main n'a pas ce garde-fou.
        format_declare = FORMAT_DEFAUT
    libelle_format, pictogramme = FORMATS[format_declare]

    age, age_jours = _libelle_age(entree.item.date_publication, maintenant)

    return EntreeRendue(
        entree=entree,
        titre=entree.item.titre or entree.accroche,
        url=_url_surs(entree.item.url),
        nom_source=nom,
        format=format_declare,
        libelle_format=libelle_format,
        pictogramme=pictogramme,
        age=age,
        age_jours=age_jours,
        date_iso=entree.item.date_publication.date().isoformat(),
        date_lisible=_date_lisible(entree.item.date_publication),
    )


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
    sources: dict[str, SourceConfig] | None = None,
    maintenant: datetime | None = None,
) -> tuple[list[tuple[str, str, list[EntreeRendue]]], bool]:
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
    sources = sources or {}
    if maintenant is None:
        maintenant = datetime.now(timezone.utc)

    par_registre: dict[str, list[EntreeRendue]] = {registre: [] for registre in CHAMPS_QUOTAS}
    for entree_brute in entrees:
        entree = _preparer_entree(entree_brute, sources, maintenant)
        registre = entree.entree.item.registre
        if registre not in par_registre:
            logger.warning(
                "Entrée '%s' avec un registre inconnu ('%s') — absente du "
                "rendu (aucune des %d sections publiées ne le reconnaît).",
                entree.entree.item.guid,
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


def rendre(
    entrees: list[Entree],
    date_generation: datetime,
    sources: dict[str, SourceConfig] | None = None,
) -> str:
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
    sections, digest_vide = _grouper_par_registre(entrees, sources, date_generation)

    # L'entrée recommandée est sortie de sa section pour tenir la « une »
    # (audit du 2026-09-22) : elle portait jusqu'ici un simple badge, noyée
    # au milieu des autres, alors que FR-8 en fait le seul repère hiérarchique
    # de la page. Retirée de sa section plutôt que dupliquée — la voir deux
    # fois donnerait l'impression d'un doublon, pas d'une mise en avant.
    une = next(
        (e for _, _, entrees_section in sections for e in entrees_section if e.recommandee),
        None,
    )
    if une is not None:
        sections = [
            (registre, libelle, [e for e in entrees_section if e is not une])
            for registre, libelle, entrees_section in sections
        ]

    total = sum(len(entrees_section) for _, _, entrees_section in sections) + (
        1 if une is not None else 0
    )

    environnement = _environnement_jinja()
    template = environnement.get_template("digest.html.j2")
    return template.render(
        sections=sections,
        une=une,
        total=total,
        date_generation=date_generation,
        date_lisible=_date_lisible(date_generation, avec_jour=True),
        digest_vide=digest_vide,
    )


def rendre_markdown(
    entrees: list[Entree],
    date_generation: datetime,
    sources: dict[str, SourceConfig] | None = None,
) -> str:
    """Rend l'archive Markdown datée du digest (FR-10, Story 1.9).

    Même regroupement par registre que `rendre()` (`_grouper_par_registre`,
    partagé — pas un second regroupement qui pourrait diverger). Le titre
    et l'accroche sont échappés pour Markdown (`markdown_safe`, pas pour
    HTML : ce n'est pas la même cible), et le lien vers l'original enveloppe
    sa destination entre `<...>` dans le template — une URL contenant des
    parenthèses (fréquent, ex. Wikipédia) casserait sinon `[texte](url)`.
    """
    sections, digest_vide = _grouper_par_registre(entrees, sources, date_generation)

    environnement = _environnement_jinja_markdown()
    template = environnement.get_template("digest.md.j2")
    return template.render(
        sections=sections,
        date_generation=date_generation,
        date_lisible=_date_lisible(date_generation),
        digest_vide=digest_vide,
    )


# Habillage commun aux trois panneaux injectés après coup (bandeau d'échec,
# récapitulatif de santé, « À découvrir »). Aligné sur le langage visuel du
# gabarit lors de la refonte du 2026-09-22 — rayon de 3 px, filet d'accent à
# gauche, mention en petites capitales — mais écrit en styles **en ligne**,
# jamais en classes : ces fragments sont insérés dans des pages déjà
# publiées, dont la feuille de style est figée au moment où elles ont été
# rendues. Une classe ajoutée ici n'existerait pas dans ces pages-là.
def _cadre_panneau(fond: str, texte: str) -> str:
    return (
        f"background:var({fond});color:var({texte});"
        f"border-left:3px solid currentColor;border-radius:3px;"
        "padding:14px 16px;margin:20px 0 0;font-size:0.9rem;line-height:1.55;"
    )


_MENTION_PANNEAU = (
    "display:block;margin:0 0 6px;font-size:0.68rem;font-weight:700;"
    "letter-spacing:0.14em;text-transform:uppercase;opacity:0.85;"
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
        f'<div style="{_cadre_panneau("--bandeau-echec-bg", "--bandeau-echec-fg")}">\n'
        f'<strong style="{_MENTION_PANNEAU}">Pas de mise à jour cette nuit</strong>\n'
        f"La génération du {date_echec.strftime('%d/%m/%Y')} a échoué pour un "
        "problème technique. Le digest ci-dessous reste le plus récent "
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
        f'<div style="{_cadre_panneau("--recapitulatif-bg", "--recapitulatif-fg")}">\n'
        f'<strong style="{_MENTION_PANNEAU}">'
        f"{len(sources)} source(s) à surveiller</strong>\n"
        f'<ul style="margin:0;padding-left:1.15rem;">\n{lignes_html}\n</ul>\n'
        "</div>\n"
        f"{RECAPITULATIF_SANTE_FIN}"
    )


# Marqueurs stables délimitant le panneau « À découvrir » dans le HTML publié
# (Story 4.4, FR-14) — même principe que le bandeau d'échec et le
# récapitulatif de santé : `publish.publier_a_decouvrir` les utilise pour
# remplacer le panneau plutôt que de l'empiler d'une semaine à l'autre, ou
# pour le retirer si aucun candidat n'est vivant cette semaine-là.
A_DECOUVRIR_DEBUT = "<!-- A-DECOUVRIR:DEBUT -->"
A_DECOUVRIR_FIN = "<!-- A-DECOUVRIR:FIN -->"


def rendre_a_decouvrir(candidat) -> str:
    """Fragment HTML proposant une source candidate vérifiée active cette
    semaine (Story 4.4, FR-14) — destiné à être inséré/remplacé après coup
    dans le HTML déjà publié par `publish.publier_a_decouvrir`, jamais
    rendu ni publié seul (même patron que `rendre_bandeau_echec`/
    `rendre_recapitulatif_sante`).

    `candidat` : `discover.CandidatSource` — non typé explicitement ici
    pour ne pas faire dépendre `render.py` de `discover.py` (même raison
    que `rendre_recapitulatif_sante` vis-à-vis de `health.py`) ; seuls
    `candidat.justification`, `candidat.source.id` et `candidat.source.url`
    sont utilisés.

    N'est **jamais** appelée avec `candidat=None` (décision de l'appelant,
    `publish.publier_a_decouvrir` : `None` signifie retirer le panneau
    existant, pas publier un panneau vide) — **imposé** ici, pas seulement
    documenté (même discipline que `rendre_recapitulatif_sante`, trouvée en
    revue de la Story 4.3).

    `justification`/`source.id` échappés via `html.escape` (source de
    configuration, `config/candidats.yaml`, pas une source externe — mais
    coût nul à échapper systématiquement, même choix que pour
    `rendre_recapitulatif_sante`). `source.url` passe par `_url_surs` (même
    garde-fou que le reste de ce module, schéma http(s) uniquement, mêmes
    précautions AC8/AC13 que pour les entrées du digest) : une URL
    invalide dégrade en texte seul, jamais de lien cliquable.
    """
    if candidat is None:
        raise ValueError(
            "rendre_a_decouvrir() ne doit jamais être appelée avec un "
            "candidat manquant — l'appelant doit retirer le panneau "
            "existant plutôt que d'en publier un vide (voir "
            "publish.publier_a_decouvrir)."
        )
    url_source = candidat.source.url or ""
    url_sure = _url_surs(url_source)
    lien_html = (
        f'<a href="{html.escape(url_sure)}">{html.escape(url_source)}</a>'
        if url_sure
        else html.escape(url_source)
    )
    return (
        f"{A_DECOUVRIR_DEBUT}\n"
        f'<div style="{_cadre_panneau("--a-decouvrir-bg", "--a-decouvrir-fg")}">\n'
        f'<strong style="{_MENTION_PANNEAU}">À découvrir cette semaine</strong>\n'
        f'<span style="font-weight:700;">{html.escape(candidat.source.id)}</span> — '
        f"{html.escape(candidat.justification)}\n"
        f'<p style="margin:6px 0 0;font-size:0.82rem;opacity:0.85;">{lien_html}</p>\n'
        "</div>\n"
        f"{A_DECOUVRIR_FIN}"
    )
