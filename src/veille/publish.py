"""Publication du digest (AD-8, FR-9).

Écrit/actualise `index.html` dans un **second dépôt GitHub, public, dédié
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

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Dépôt de sortie — constante en dur, même précédent que `MODELE` dans
# `enrich/llm.py` : AD-3 (configuration) lie explicitement FR-1/5/6, pas la
# cible de publication. Paramètre que seul Abdoulaye modifierait, et rarement.
PUBLISH_REPO = "petitlaye03/agent-veille-tech-digest"

CHEMIN_FICHIER = "index.html"
API_BASE = "https://api.github.com"

_env_charge = False
_avertissement_jeton_absent_emis = False
_avertissement_echec_publication_emis = False


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


def _sha_existant(client: httpx.Client) -> str | None:
    """Sha du fichier existant dans le dépôt de sortie, ou `None` si absent
    (première publication — traitée comme une création, pas un échec).

    Seul un **404** signifie « absent » — tout autre code d'erreur (401
    jeton invalide, 403 quota épuisé, 5xx) est une vraie panne, pas une
    absence de fichier (trouvé en revue) : les confondre laisserait le PUT
    suivant tenter une création sans `sha` sur un fichier qui existe peut-
    être réellement, masquant la cause exacte derrière un rejet générique
    de l'API. `raise_for_status()` la fait remonter à l'appelant
    (`publier`), qui l'isole comme toute autre panne.
    """
    reponse = client.get(f"/repos/{PUBLISH_REPO}/contents/{CHEMIN_FICHIER}")
    if reponse.status_code == 404:
        return None
    reponse.raise_for_status()
    return reponse.json().get("sha")


def publier(html: str, client: httpx.Client | None = None) -> bool:
    """Publie `html` comme `index.html` du dépôt de sortie (AC10).

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
        sha = _sha_existant(resolu)
        corps = {
            "message": "Mise à jour du digest",
            "content": base64.b64encode(html.encode("utf-8")).decode("ascii"),
        }
        if sha:
            corps["sha"] = sha

        reponse = resolu.put(f"/repos/{PUBLISH_REPO}/contents/{CHEMIN_FICHIER}", json=corps)
        reponse.raise_for_status()
        return True
    except httpx.HTTPError:
        _avertir_echec_publication()
        return False
    except Exception:  # noqa: BLE001 — isolation totale, même hors httpx.HTTPError
        _avertir_echec_publication()
        return False
    finally:
        if not fourni:
            resolu.close()


def _avertir_echec_publication() -> None:
    """Trace complète pour le premier échec du run, message court ensuite —
    même patron que `enrich/llm.py::_avertir_echec_api`."""
    global _avertissement_echec_publication_emis
    if not _avertissement_echec_publication_emis:
        logger.warning("Échec de la publication du digest.", exc_info=True)
        _avertissement_echec_publication_emis = True
    else:
        logger.warning("Échec de la publication du digest.")
