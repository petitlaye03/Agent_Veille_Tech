"""Rendu HTML du digest (FR-9, Story 1.8).

Regroupe les `Entree` retenues par registre et produit la page publiée à
partir du template Jinja2 `templates/digest.html.j2`. Aucune logique de
scoring, de filtrage ni d'appel réseau ici — seulement de la mise en forme
sur des `Entree` déjà produites par `filter.py`/`enrich/llm.py`.
"""

import logging
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
    """Ne renvoie l'URL que si son schéma est http(s), sinon `None`.

    `Item.url` est du contenu de source externe non fiable (RSS/API/scraping,
    aucune source ne le valide) — l'autoescaping HTML de Jinja2 neutralise
    les métacaractères (`<`, `"`, ...) mais ne valide jamais le **schéma**
    d'une URI. Un flux compromis déclarant `<link>javascript:alert(1)</link>`
    produirait donc un lien cliquable exécutable malgré l'échappement actif,
    contournant entièrement AC8 sans jamais toucher un métacaractère. Un
    schéma refusé se traite comme une URL vide (AC13) : pas de lien, texte
    seul.
    """
    if url and url.lower().startswith(_SCHEMES_AUTORISES):
        return url
    return None


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


def rendre(entrees: list[Entree], date_generation: datetime) -> str:
    """Rend la page HTML du digest.

    Regroupe par `entree.item.registre`, dans l'ordre canonique
    `filter.CHAMPS_QUOTAS` (AC1). Une liste vide produit un message honnête
    plutôt qu'une page cassée ou silencieusement vide (AC9). Un titre vide
    se replie sur l'accroche pour l'en-tête affiché ; une URL vide, ou dont
    le schéma n'est pas http(s) (`_url_surs`, trouvé en revue), n'émet
    aucun lien cliquable (AC13, `Entree`/`Item` ne garantissent pas la
    non-vacuité de ces champs — cf. `deferred-work.md`).

    Ne lève jamais si `entrees` est vide. Un registre absent de
    `CHAMPS_QUOTAS` (typo dans `sources.yaml` : `repartir_par_quotas`,
    Story 1.5, conserve sans limite un registre qu'il ne connaît pas — donc
    bel et bien atteignable ici, trouvé en revue) est journalisé une fois
    plutôt que silencieusement perdu ; `digest_vide` reflète les sections
    **réellement peuplées**, pas seulement la non-vacuité de `entrees` —
    sinon une entrée ainsi égarée ne serait affichée nulle part, ni dans une
    section, ni dans le message « rien à signaler », ce que l'AC9 interdit.
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

    environnement = _environnement_jinja()
    template = environnement.get_template("digest.html.j2")
    return template.render(
        sections=sections,
        date_generation=date_generation,
        digest_vide=not any(entrees_section for _, _, entrees_section in sections),
    )
