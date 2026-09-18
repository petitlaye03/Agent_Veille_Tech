"""Publication du digest (AD-8, FR-9) et de son archive datée (FR-10).

Écrit/actualise `index.html` (page) et `site/archive/YYYY-MM-DD.md`
(archive, Story 1.9) dans un **second dépôt GitHub, public, dédié
uniquement à la sortie publiée** — `Agent_Veille_Tech` (le code, les
stories) reste privé. Décision actée avec Abdoulaye le 2026-08-28 : la
Structural Seed de l'architecture anticipait déjà cette variante (« `site/`
peut être un sous-module ou un repo distinct »).

Via l'API Contents de GitHub (`PUT /repos/{owner}/{repo}/contents/{path}`),
jamais un clone local ni un appel `subprocess` à `git` — testabilité (client
HTTP simulé, comme `enrich/llm.py` le fait déjà pour Claude) et absence de
couplage à un dossier voisin supposé déjà cloné.
"""

import base64
import logging
import os
import re
import subprocess
from datetime import date

import httpx
from dotenv import load_dotenv

from veille.render import (
    A_DECOUVRIR_DEBUT,
    A_DECOUVRIR_FIN,
    BANDEAU_ECHEC_DEBUT,
    BANDEAU_ECHEC_FIN,
    RECAPITULATIF_SANTE_DEBUT,
    RECAPITULATIF_SANTE_FIN,
    rendre_a_decouvrir,
    rendre_recapitulatif_sante,
)

logger = logging.getLogger(__name__)

# Dépôt de sortie — constante en dur, même précédent que `MODELE` dans
# `enrich/llm.py` : AD-3 (configuration) lie explicitement FR-1/5/6, pas la
# cible de publication. Paramètre que seul Abdoulaye modifierait, et rarement.
PUBLISH_REPO = "petitlaye03/agent-veille-tech-digest"

# Renommé depuis `CHEMIN_FICHIER` (Story 1.9) : il existe désormais un second
# chemin, celui de l'archive datée (voir `publier_archive`).
CHEMIN_PAGE = "index.html"
API_BASE = "https://api.github.com"

_env_charge = False
_avertissement_jeton_absent_emis = False
# Catégories (`"page"`, `"archive"`) ayant déjà reçu leur trace complète au
# premier échec — un `set`, pas un booléen unique, depuis la Story 1.9 (voir
# `_avertir_echec_publication`).
_categories_echec_avec_trace_emise: set[str] = set()


def _jeton_depuis_env() -> str | None:
    """Lit `GITHUB_TOKEN` dans `.env`. Nettoyé des espaces avant le test de
    présence — même piège de clé blanche trouvé en revue de la Story 1.6
    (`_client` de `enrich/llm.py`) : une variable d'environnement composée
    uniquement d'espaces passerait sinon le test `if not cle`."""
    global _env_charge
    if not _env_charge:
        load_dotenv()
        _env_charge = True
    cle = (os.environ.get("GITHUB_TOKEN") or "").strip()
    return cle or None


def _jeton_depuis_gh_cli() -> str | None:
    """Repli sur la session `gh` déjà authentifiée localement — évite
    d'imposer à Abdoulaye de créer un jeton dédié tout de suite. Ne lève
    jamais : `gh` absent, non authentifié, ou tout autre échec → `None`."""
    try:
        resultat = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if resultat.returncode != 0:
        return None
    jeton = resultat.stdout.strip()
    return jeton or None


def _jeton() -> str | None:
    """Résout un jeton d'accès GitHub — `GITHUB_TOKEN` (`.env`) en priorité,
    sinon `gh auth token`. Ne lève jamais ; `None` si aucune des deux voies
    n'aboutit."""
    return _jeton_depuis_env() or _jeton_depuis_gh_cli()


def _client() -> httpx.Client | None:
    """Construit le client HTTP GitHub, ou `None` si aucun jeton n'est
    résolu. Avertissement journalisé une seule fois par run (même patron que
    `enrich/llm.py::_client`)."""
    global _avertissement_jeton_absent_emis
    jeton = _jeton()
    if jeton is None:
        if not _avertissement_jeton_absent_emis:
            logger.warning(
                "Aucun jeton GitHub résolu (ni GITHUB_TOKEN, ni `gh auth "
                "token`) — la publication du digest sera ignorée cette nuit."
            )
            _avertissement_jeton_absent_emis = True
        return None
    return httpx.Client(
        base_url=API_BASE,
        headers={
            "Authorization": f"Bearer {jeton}",
            "Accept": "application/vnd.github+json",
        },
        timeout=15.0,
    )


def _sha_existant(client: httpx.Client, chemin: str) -> str | None:
    """Sha du fichier existant dans le dépôt de sortie, ou `None` si absent
    (première publication — traitée comme une création, pas un échec).

    Seul un **404** signifie « absent » — tout autre code d'erreur (401
    jeton invalide, 403 quota épuisé, 5xx) est une vraie panne, pas une
    absence de fichier (trouvé en revue) : les confondre laisserait le PUT
    suivant tenter une création sans `sha` sur un fichier qui existe peut-
    être réellement, masquant la cause exacte derrière un rejet générique
    de l'API. `raise_for_status()` la fait remonter à l'appelant
    (`_publier`), qui l'isole comme toute autre panne.

    `chemin` (Story 1.9) : cette fonction sert aussi bien la page
    (`CHEMIN_PAGE`) que l'archive datée (`site/archive/YYYY-MM-DD.md`) —
    même mécanisme d'upsert par `sha` pour les deux (AD-9).

    Délègue à `_charge_existante` (Story 3.2) — même requête `GET`/même
    distinction 404, réutilisée aussi par `publier_bandeau_echec`.
    """
    charge = _charge_existante(client, chemin)
    return charge.get("sha") if charge is not None else None


def _publier(chemin: str, contenu: str, client: httpx.Client | None, quoi: str, categorie: str) -> bool:
    """Cœur partagé : écrit/actualise un fichier via l'API Contents (Story 1.9).

    Extrait de l'ancien corps unique de `publier()` pour être réutilisé par
    `publier()` (page) et `publier_archive()` (archive datée) sans dupliquer
    la résolution/fermeture du client ni l'isolation de panne. `quoi`
    (« de la page », « de l'archive du ... ») distingue les deux dans les
    journaux (AC8, Story 1.9) ; `categorie` (`"page"`/`"archive"`, trouvé
    en revue) sert uniquement à dédupliquer la trace complète du premier
    échec par catégorie — voir `_avertir_echec_publication`.

    Isolation totale (réseau, 401, 404, timeout) : ne lève jamais, retourne
    `False` sur tout échec — y compris l'absence de jeton résolu. Un client
    fourni explicitement (tests) n'est jamais fermé par cette fonction ;
    celui construit ici l'est toujours, succès ou échec.
    """
    fourni = client is not None
    resolu = client if fourni else _client()
    if resolu is None:
        return False

    try:
        sha = _sha_existant(resolu, chemin)
        # Trouvé en revue (Story 3.3) : le message de commit disait « Mise à
        # jour » même pour une toute première création — trompeur dans
        # l'historique du dépôt de sortie, corrigé pour refléter les deux cas.
        corps = {
            "message": f"{'Mise à jour' if sha else 'Publication'} {quoi}",
            "content": base64.b64encode(contenu.encode("utf-8")).decode("ascii"),
        }
        if sha:
            corps["sha"] = sha

        reponse = resolu.put(f"/repos/{PUBLISH_REPO}/contents/{chemin}", json=corps)
        reponse.raise_for_status()
        return True
    except httpx.HTTPError:
        _avertir_echec_publication(quoi, categorie)
        return False
    except Exception:  # noqa: BLE001 — isolation totale, même hors httpx.HTTPError
        _avertir_echec_publication(quoi, categorie)
        return False
    finally:
        if not fourni:
            resolu.close()


def publier(html: str, client: httpx.Client | None = None) -> bool:
    """Publie `html` comme `index.html` du dépôt de sortie (AC10, Story 1.8)."""
    return _publier(CHEMIN_PAGE, html, client, "de la page", categorie="page")


def publier_archive(markdown: str, date_digest: date, client: httpx.Client | None = None) -> bool:
    """Publie l'archive Markdown datée du digest (FR-10, Story 1.9).

    Chemin `site/archive/YYYY-MM-DD.md` (Structural Seed) — relancer le
    pipeline pour la même date écrase l'archive existante au lieu d'en
    créer une seconde (AC3, AD-9) : même mécanisme d'upsert par `sha` que
    `publier()`, hérité de `_publier()` sans code supplémentaire.
    """
    chemin = f"site/archive/{date_digest.isoformat()}.md"
    return _publier(
        chemin, markdown, client, f"de l'archive du {date_digest.isoformat()}", categorie="archive"
    )


def _charge_existante(client: httpx.Client, chemin: str) -> dict | None:
    """`GET` bas niveau partagé par `_sha_existant` et `publier_bandeau_echec`
    (correctif de revue — la version initiale de `publier_bandeau_echec`
    dupliquait cette requête au lieu de la réutiliser, contrairement à ce
    que sa docstring affirmait). `None` si le fichier n'existe pas encore
    (404, pas une panne) ; toute autre erreur HTTP lève, isolée par l'appelant.
    """
    reponse = client.get(f"/repos/{PUBLISH_REPO}/contents/{chemin}")
    if reponse.status_code == 404:
        return None
    reponse.raise_for_status()
    return reponse.json()


def publier_bandeau_echec(bandeau: str, client: httpx.Client | None = None) -> bool | None:
    """Insère (ou remplace, AC4) `bandeau` dans la page déjà publiée, sans
    perdre son contenu (Story 3.2, AC3).

    Contrairement à `publier()`, ne régénère pas la page depuis zéro : lit
    le HTML déjà publié, y patche le fragment `render.rendre_bandeau_echec`
    entre les marqueurs stables, republie via le même mécanisme d'upsert
    par `sha` que le reste de ce module. Isolation totale : ne lève jamais.

    Valeur de retour à trois états (corrigé en revue — un simple `bool`
    confondait deux situations distinctes) :
    - `None` — aucune page déjà publiée à annoter (première nuit jamais
      publiée avec succès) : pas une panne, rien à patcher, `main_bandeau_echec`
      ne doit pas en faire un code de sortie non nul ;
    - `False` — panne réelle (réseau, HTTP, contenu illisible) ;
    - `True` — bandeau publié avec succès.
    """
    fourni = client is not None
    resolu = client if fourni else _client()
    if resolu is None:
        return False

    try:
        charge = _charge_existante(resolu, CHEMIN_PAGE)
        if charge is None:
            logger.info(
                "Aucune page déjà publiée à annoter d'un bandeau d'échec — "
                "rien à faire (probablement la toute première nuit)."
            )
            return None
        if not charge.get("content"):
            # Contenu absent/vidé par l'API (ex. fichier trop volumineux
            # pour être inclus en ligne, trouvé en revue) : une vraie panne,
            # pas une absence de page — distincte du cas 404 ci-dessus.
            raise ValueError("réponse GET sans champ 'content' exploitable")
        html_existant = base64.b64decode(charge["content"]).decode("utf-8")

        corps = {
            "message": "Bandeau d'échec nocturne",
            "content": base64.b64encode(
                _inserer_fragment(html_existant, _MOTIF_BANDEAU_ECHEC, bandeau).encode("utf-8")
            ).decode("ascii"),
        }
        if charge.get("sha"):  # même garde que `_publier` — jamais `"sha": null`
            corps["sha"] = charge["sha"]

        reponse_put = resolu.put(f"/repos/{PUBLISH_REPO}/contents/{CHEMIN_PAGE}", json=corps)
        reponse_put.raise_for_status()
        return True
    except httpx.HTTPError:
        _avertir_echec_publication("du bandeau d'échec", categorie="bandeau")
        return False
    except Exception:  # noqa: BLE001 — isolation totale, même hors httpx.HTTPError
        _avertir_echec_publication("du bandeau d'échec", categorie="bandeau")
        return False
    finally:
        if not fourni:
            resolu.close()


_MOTIF_BANDEAU_ECHEC = re.compile(
    re.escape(BANDEAU_ECHEC_DEBUT) + r".*?" + re.escape(BANDEAU_ECHEC_FIN), re.DOTALL
)
_MOTIF_RECAPITULATIF_SANTE = re.compile(
    re.escape(RECAPITULATIF_SANTE_DEBUT) + r".*?" + re.escape(RECAPITULATIF_SANTE_FIN), re.DOTALL
)
_MOTIF_A_DECOUVRIR = re.compile(
    re.escape(A_DECOUVRIR_DEBUT) + r".*?" + re.escape(A_DECOUVRIR_FIN), re.DOTALL
)
_MOTIF_BALISE_BODY = re.compile(r"<body[^>]*>", re.IGNORECASE)


def _inserer_fragment(html: str, motif: re.Pattern, fragment: str) -> str:
    """Remplace le contenu déjà présent entre les marqueurs stables
    correspondant à `motif` s'il y en a un (idempotence — un fragment ne
    doit jamais s'empiler d'un run au suivant), sinon l'insère juste après
    la balise `<body>` (avec ou sans attributs — `<body>`/`<body
    class="...">`, correctif de revue de la Story 3.2 : un
    `str.replace("<body>", ...)` littéral aurait raté toute balise portant
    un attribut). Si `<body...>` lui-même est introuvable (page corrompue
    de façon inattendue), l'ajoute en tête plutôt que de ne rien faire
    silencieusement.

    Généralisée depuis `_inserer_bandeau` (Story 3.2) à l'occasion de la
    Story 4.3, qui en introduit un second usage (récapitulatif des sources
    à surveiller) — factoriser à la deuxième occurrence d'un motif non
    trivial plutôt que de le dupliquer une seconde fois à l'identique.

    `fragment` est passé à `re.sub` via une fonction de remplacement
    plutôt qu'une chaîne brute (correctif de revue de la Story 3.2) : une
    chaîne de remplacement littérale ferait interpréter par `re` un
    `\\1`/`\\g<0>` qu'elle contiendrait, une source d'erreur ou de
    corruption silencieuse sans rapport avec le contenu réel du fragment.
    """
    if motif.search(html):
        # Pas de `count=1` : si plusieurs paires de marqueurs existaient
        # (ne devrait jamais arriver par ce code, mais auto-cicatrisant si
        # une corruption externe en laissait plusieurs), toutes convergent
        # vers le même contenu plutôt que d'en laisser une orpheline.
        return motif.sub(lambda _m: fragment, html)
    if _MOTIF_BALISE_BODY.search(html):
        return _MOTIF_BALISE_BODY.sub(lambda m: f"{m.group(0)}\n{fragment}", html, count=1)
    return f"{fragment}\n{html}"


def publier_recapitulatif_sante(
    sources: list, client: httpx.Client | None = None
) -> bool | None:
    """Insère, remplace ou retire le panneau des sources à surveiller sur
    la page déjà publiée (Story 4.3, AC1/AC3/AC4).

    `sources` : `list[health.SourceASurveiller]` — non typé explicitement
    ici pour la même raison que `render.rendre_recapitulatif_sante` (dont
    la signature reprend le même choix) : ne pas faire dépendre `publish.py`
    de `health.py`, aucun import inter-module de ce sens ailleurs dans le
    projet.

    Même patron que `publier_bandeau_echec` (Story 3.2) : lit le HTML déjà
    publié, patche entre marqueurs stables (`_inserer_fragment`), republie
    via le même mécanisme d'upsert par `sha`. Isolation totale : ne lève
    jamais.

    `sources` (`list[health.SourceASurveiller]`) **vide** signifie : plus
    aucune source à surveiller cette semaine — le panneau existant, s'il y
    en a un, est **retiré** (AC4 : un panneau périmé listant des problèmes
    déjà résolus serait trompeur) ; s'il n'y en avait pas déjà un, rien à
    faire (dégrade en `None`, pas un `True` qui prétendrait avoir changé
    quelque chose).

    Retour à trois états (même discipline que `publier_bandeau_echec`,
    décision #46 du journal) :
    - `None` — rien à changer (aucune page déjà publiée à patcher, ou
      `sources` vide et aucun panneau existant à retirer) ;
    - `False` — panne réelle (réseau, HTTP, contenu illisible) ;
    - `True` — panneau publié, remplacé, ou retiré avec succès.
    """
    fourni = client is not None
    resolu = client if fourni else _client()
    if resolu is None:
        return False

    try:
        charge = _charge_existante(resolu, CHEMIN_PAGE)
        if charge is None:
            logger.info(
                "Aucune page déjà publiée à annoter d'un récapitulatif de "
                "santé — rien à faire (probablement la toute première nuit)."
            )
            return None
        if not charge.get("content"):
            raise ValueError("réponse GET sans champ 'content' exploitable")
        html_existant = base64.b64decode(charge["content"]).decode("utf-8")

        if sources:
            fragment = rendre_recapitulatif_sante(sources)
            html_nouveau = _inserer_fragment(html_existant, _MOTIF_RECAPITULATIF_SANTE, fragment)
            message = "Mise à jour du récapitulatif des sources à surveiller"
        else:
            if not _MOTIF_RECAPITULATIF_SANTE.search(html_existant):
                logger.info(
                    "Aucune source à surveiller et aucun récapitulatif déjà "
                    "publié — rien à faire."
                )
                return None
            # Retrait pur et simple (AC4) : les marqueurs et tout leur
            # contenu disparaissent, pas de fragment vide laissé en place.
            html_nouveau = _MOTIF_RECAPITULATIF_SANTE.sub("", html_existant)
            message = "Retrait du récapitulatif des sources à surveiller (tout est rétabli)"

        corps = {
            "message": message,
            "content": base64.b64encode(html_nouveau.encode("utf-8")).decode("ascii"),
        }
        if charge.get("sha"):  # même garde que `_publier` — jamais `"sha": null`
            corps["sha"] = charge["sha"]

        reponse_put = resolu.put(f"/repos/{PUBLISH_REPO}/contents/{CHEMIN_PAGE}", json=corps)
        reponse_put.raise_for_status()
        return True
    except httpx.HTTPError:
        _avertir_echec_publication("du récapitulatif de santé", categorie="recapitulatif")
        return False
    except Exception:  # noqa: BLE001 — isolation totale, même hors httpx.HTTPError
        _avertir_echec_publication("du récapitulatif de santé", categorie="recapitulatif")
        return False
    finally:
        if not fourni:
            resolu.close()


def publier_a_decouvrir(candidat, client: httpx.Client | None = None) -> bool | None:
    """Insère, remplace ou retire le panneau « À découvrir » sur la page
    déjà publiée (Story 4.4, AC1/AC3/AC4).

    `candidat` : `discover.CandidatSource | None` — non typé explicitement
    ici pour la même raison que `render.rendre_a_decouvrir` (dont la
    signature reprend le même choix) : ne pas faire dépendre `publish.py`
    de `discover.py`, aucun import inter-module de ce sens ailleurs dans
    le projet.

    Même patron à trois états que `publier_recapitulatif_sante` (Story
    4.3) : lit le HTML déjà publié, patche entre marqueurs stables
    (`_inserer_fragment`), republie via le même mécanisme d'upsert par
    `sha`. Isolation totale : ne lève jamais.

    `candidat=None` signifie : aucun candidat vivant cette semaine (pool
    entièrement mort, ou aucun candidat non déjà adopté — voir
    `discover.proposer_source`) — le panneau existant, s'il y en a un, est
    **retiré** (AC4 : un panneau périmé proposant une source déjà morte
    serait trompeur) ; s'il n'y en avait pas déjà un, rien à faire
    (dégrade en `None`, pas un `True` qui prétendrait avoir changé
    quelque chose).

    Retour à trois états (même discipline que `publier_recapitulatif_sante`) :
    - `None` — rien à changer (aucune page déjà publiée à patcher, ou
      `candidat=None` et aucun panneau existant à retirer) ;
    - `False` — panne réelle (réseau, HTTP, contenu illisible) ;
    - `True` — panneau publié, remplacé, ou retiré avec succès.
    """
    fourni = client is not None
    resolu = client if fourni else _client()
    if resolu is None:
        return False

    try:
        charge = _charge_existante(resolu, CHEMIN_PAGE)
        if charge is None:
            logger.info(
                "Aucune page déjà publiée à annoter d'un panneau « À "
                "découvrir » — rien à faire (probablement la toute "
                "première nuit)."
            )
            return None
        if not charge.get("content"):
            raise ValueError("réponse GET sans champ 'content' exploitable")
        html_existant = base64.b64decode(charge["content"]).decode("utf-8")

        if candidat is not None:
            fragment = rendre_a_decouvrir(candidat)
            html_nouveau = _inserer_fragment(html_existant, _MOTIF_A_DECOUVRIR, fragment)
            message = "Mise à jour du panneau « À découvrir »"
        else:
            if not _MOTIF_A_DECOUVRIR.search(html_existant):
                logger.info(
                    "Aucun candidat vivant cette semaine et aucun panneau "
                    "« À découvrir » déjà publié — rien à faire."
                )
                return None
            # Retrait pur et simple (AC4) : les marqueurs et tout leur
            # contenu disparaissent, pas de fragment vide laissé en place.
            html_nouveau = _MOTIF_A_DECOUVRIR.sub("", html_existant)
            message = "Retrait du panneau « À découvrir » (aucun candidat vivant)"

        corps = {
            "message": message,
            "content": base64.b64encode(html_nouveau.encode("utf-8")).decode("ascii"),
        }
        if charge.get("sha"):  # même garde que `_publier` — jamais `"sha": null`
            corps["sha"] = charge["sha"]

        reponse_put = resolu.put(f"/repos/{PUBLISH_REPO}/contents/{CHEMIN_PAGE}", json=corps)
        reponse_put.raise_for_status()
        return True
    except httpx.HTTPError:
        _avertir_echec_publication("du panneau « À découvrir »", categorie="a_decouvrir")
        return False
    except Exception:  # noqa: BLE001 — isolation totale, même hors httpx.HTTPError
        _avertir_echec_publication("du panneau « À découvrir »", categorie="a_decouvrir")
        return False
    finally:
        if not fourni:
            resolu.close()


def _avertir_echec_publication(quoi: str, categorie: str) -> None:
    """Trace complète pour le premier échec du run **par catégorie**, message
    court ensuite — même patron que `enrich/llm.py::_avertir_echec_api`.

    `categorie` (`"page"`/`"archive"`, trouvé en revue) : le drapeau
    « trace complète au premier échec » était auparavant un booléen unique
    partagé entre la page et l'archive — si les deux échouaient dans le
    même run, seule la première des deux obtenait sa trace complète,
    l'autre n'ayant plus qu'un message sans contexte de diagnostic malgré
    un échec tout aussi nouveau. Une catégorie par type de publication
    corrige ça sans réintroduire le risque écarté en Story 1.8 (un
    horodatage dans la clé de dédoublonnage empêcherait toute
    déduplication réelle, l'archive changeant de nom chaque jour)."""
    global _categories_echec_avec_trace_emise
    message = f"Échec de la publication {quoi}."
    if categorie not in _categories_echec_avec_trace_emise:
        logger.warning(message, exc_info=True)
        _categories_echec_avec_trace_emise.add(categorie)
    else:
        logger.warning(message)
