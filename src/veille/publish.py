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
import subprocess
from datetime import date

import httpx
from dotenv import load_dotenv

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
    """
    reponse = client.get(f"/repos/{PUBLISH_REPO}/contents/{chemin}")
    if reponse.status_code == 404:
        return None
    reponse.raise_for_status()
    return reponse.json().get("sha")


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
        corps = {
            "message": f"Mise à jour {quoi}",
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
