"""Chargement et analyse du profil de filtrage (AD-3, FR-5).

Le profil (`config/profil.md`) reste un document lisible par un humain,
co-écrit avec Abdoulaye ; ce module en extrait les mots-clés par catégorie.
Ne lève **jamais** : un profil absent ou illisible dégrade vers un profil
neutre plutôt que de faire perdre la nuit entière (leçon Story 1.3).
"""

import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from veille.config import chemin_config

logger = logging.getLogger(__name__)

DEFAULT_PROFIL_PATH = chemin_config("profil.md")

# Préfixe (normalisé : sans accent, en minuscule) du titre de section `## `
# -> catégorie de score qu'il alimente. Préfixe et non égalité stricte :
# Abdoulaye doit pouvoir reformuler la fin d'un titre sans casser le
# parseur (Dev Notes).
_CATEGORIES_PAR_PREFIXE = {
    "themes prioritaires": "prioritaire",
    "signal fort": "signal_fort",
    "domaines d'application": "domaine",
    "themes secondaires": "secondaire",
    "bruit": "bruit",
}

# Section connue mais qui ne porte pas de mots-clés (prose) : ignorée sans
# avertissement, à la différence d'un titre réellement inconnu.
_SECTIONS_IGNOREES = ("posture",)

# Commentaire italique entre parenthèses (« *(...)* ») : de la prose, jamais
# des mots-clés — retiré avant toute extraction. Non gourmand, sans quoi un
# aside contenant lui-même une parenthèse avalerait la suite de la ligne.
_ASIDE_ITALIQUE = re.compile(r"\*\(.*?\)\*")

# Puce de liste, sous toutes ses formes Markdown courantes. Le profil est
# édité à la main : rien ne garantit que la puce reste un tiret.
_PUCE = re.compile(r"^\s*(?:[-*+•]\s+|\d+[.)]\s+)")

# Commentaire HTML : de la documentation destinée au lecteur du fichier,
# jamais des mots-clés. Retiré du texte entier avant l'analyse, car un
# commentaire s'étend souvent sur plusieurs lignes.
_COMMENTAIRE_HTML = re.compile(r"<!--.*?-->", re.DOTALL)

# Tiret introduisant de la prose descriptive (« Finance — data/IA appliquée
# à la finance »). Cadratin et demi-cadratin acceptés indifféremment.
_TIRET_PROSE = re.compile(r"\s*[—–]\s+")

# Délimiteurs de mots-clés au sein d'une ligne. Les parenthèses en font
# partie : « inference (vLLM, Ollama) » énumère des exemples concrets, pas
# une note collée au mot qui précède.
_DELIMITEURS = re.compile(r"[,:()&/]")

# Ponctuation décorative en bordure de mot-clé. La retirer est indispensable :
# une frontière de mot (`\b`) ne peut jamais s'ancrer contre un caractère non
# alphanumérique, si bien qu'un mot-clé comme « Qwen… » ne matcherait même
# pas son propre texte littéral.
_PONCTUATION_BORDURE = "«»\"'`´“”‘’.…,;:!?*_-–—()[]{}"


@dataclass(frozen=True)
class Profil:
    """Mots-clés du profil, groupés par catégorie de score.

    Un profil neutre (toutes catégories vides) est une valeur valide : c'est
    ce que produit `charger_profil` en cas d'échec, plutôt qu'une exception.
    """

    prioritaire: tuple[str, ...] = ()
    signal_fort: tuple[str, ...] = ()
    domaine: tuple[str, ...] = ()
    secondaire: tuple[str, ...] = ()
    bruit: tuple[str, ...] = ()

    @property
    def est_vide(self) -> bool:
        return not (
            self.prioritaire
            or self.signal_fort
            or self.domaine
            or self.secondaire
            or self.bruit
        )


def charger_profil(chemin: str | Path = DEFAULT_PROFIL_PATH) -> Profil:
    """Lit et analyse `profil.md`.

    Un fichier absent ou illisible produit un profil neutre et un
    avertissement journalisé, jamais un plantage du run.
    """
    try:
        texte = Path(chemin).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        logger.warning(
            "Profil illisible (%s) — classement neutre pour cette nuit.", chemin
        )
        return Profil()

    return _analyser(texte)


def _analyser(texte: str) -> Profil:
    mots_cles: dict[str, list[str]] = {c: [] for c in set(_CATEGORIES_PAR_PREFIXE.values())}
    categorie_courante: str | None = None

    texte = _COMMENTAIRE_HTML.sub("", texte)

    for ligne in texte.splitlines():
        depouillee = ligne.lstrip()
        if depouillee.startswith("#"):
            # Tout titre ferme la section courante — sans quoi les lignes
            # suivant un `# ` resteraient rattachées à la catégorie
            # précédente, et un mot-clé prioritaire atterrirait dans le bruit.
            niveau = len(depouillee) - len(depouillee.lstrip("#"))
            titre = depouillee.lstrip("#").strip()
            categorie_courante = _categorie(titre) if niveau in (2, 3) else None
            continue
        if categorie_courante is None:
            continue

        connus = {m.lower() for m in mots_cles[categorie_courante]}
        for mot in _extraire_mots_cles(ligne):
            if mot.lower() not in connus:
                mots_cles[categorie_courante].append(mot)
                connus.add(mot.lower())

    profil = Profil(
        prioritaire=tuple(mots_cles["prioritaire"]),
        signal_fort=tuple(mots_cles["signal_fort"]),
        domaine=tuple(mots_cles["domaine"]),
        secondaire=tuple(mots_cles["secondaire"]),
        bruit=tuple(mots_cles["bruit"]),
    )

    if profil.est_vide:
        # Un profil vide désactive le classement en entier. Sans ce signal,
        # le récapitulatif d'une nuit non filtrée est indiscernable de celui
        # d'une nuit saine.
        logger.warning(
            "Profil analysé sans aucun mot-clé — le classement par "
            "pertinence est neutralisé pour cette exécution."
        )

    return profil


def _categorie(titre: str) -> str | None:
    """Résout un titre de section `## ...` vers sa catégorie, par préfixe.

    Une section connue mais sans mots-clés (Posture), ou un titre non
    reconnu, renvoient `None` : les lignes qui suivent sont alors ignorées
    plutôt que rattachées à la mauvaise catégorie.
    """
    # L'apostrophe typographique est ce que produisent la plupart des
    # éditeurs : sans cette normalisation, « Domaines d'application » ne
    # correspondrait à aucun préfixe et la section entière serait perdue.
    normalise = sans_accents(titre).lower().replace("’", "'").replace("‘", "'")

    for prefixe, categorie in _CATEGORIES_PAR_PREFIXE.items():
        if normalise.startswith(prefixe):
            return categorie

    if not normalise.startswith(_SECTIONS_IGNOREES):
        logger.warning("Section de profil inconnue, ignorée : %r", titre)
    return None


def sans_accents(texte: str) -> str:
    """Normalise les accents. Partagé avec `filter.py` (même règle de
    correspondance pour l'analyse du profil et pour le scoring)."""
    decompose = unicodedata.normalize("NFD", texte)
    return "".join(c for c in decompose if unicodedata.category(c) != "Mn")


def _extraire_mots_cles(ligne: str) -> list[str]:
    """Extrait les mots-clés d'une ligne (élément de liste ou terme en gras).

    Dans l'ordre : retirer les asides italiques entre parenthèses (prose),
    tronquer après un tiret cadratin (prose descriptive introduite par
    « — »), retirer la puce et les marques de gras, puis découper sur les
    délimiteurs. Les mots-clés multi-mots (« hybrid search ») restent
    intacts : seuls les délimiteurs explicites séparent, jamais l'espace.
    """
    ligne = _ASIDE_ITALIQUE.sub("", ligne)
    ligne = _TIRET_PROSE.split(ligne, maxsplit=1)[0]
    ligne = _PUCE.sub("", ligne, count=1)
    ligne = ligne.replace("**", "").strip()

    mots_cles = []
    for segment in _DELIMITEURS.split(ligne):
        mot = segment.strip().strip(_PONCTUATION_BORDURE).strip()
        # Un « mot-clé » sans le moindre caractère alphanumérique (un tiret
        # isolé, par exemple) matcherait un peu partout : l'écarter.
        if mot and any(c.isalnum() for c in mot):
            mots_cles.append(mot)

    return mots_cles
