"""État « déjà vu » persistant (AD-5, AD-11, Story 3.4).

Un fichier SQLite local (stdlib `sqlite3`, aucune nouvelle dépendance) est
la seule source de vérité pour savoir si un item a déjà été publié dans un
digest antérieur — exactement ce qu'AD-5 demande (« un fichier SQLite local
est la seule source de vérité pour... l'état d'une Source »).

**AD-11, contrainte de conception posée dès la Story 3.2** : un item n'est
marqué « vu » qu'**après** une publication réussie, jamais avant — pour
qu'un run qui échoue puisse retenter les mêmes items à la prochaine
reprise sans qu'aucun n'ait été perdu entre-temps. `marquer_vus()` n'est
donc appelée par `pipeline.executer()` qu'une fois `page_ok and archive_ok`
confirmés, jamais avant ni en cas d'échec partiel.

**Persistance à travers les runs GitHub Actions** (Story 3.1 a choisi un
runner éphémère, rien n'y survit d'un run à l'autre) : le fichier SQLite
est lui-même committé dans le **dépôt source** (`Agent_Veille_Tech`, privé
— pas le dépôt de sortie public, cet état est un détail d'implémentation
du pipeline, pas du contenu publié) via l'API Contents de GitHub, réutilisant
le même mécanisme d'upsert par `sha` que `publish.py`, mais avec son propre
jeton (`SOURCE_GITHUB_TOKEN` — le jeton ambiant du workflow, scopé au
dépôt courant, distinct de `DIGEST_PUBLISH_TOKEN` qui vise le dépôt de
sortie). Choix délibéré plutôt qu'un service de stockage dédié : le fichier
reste minuscule à cette échelle (identifiants d'articles, pas leur contenu),
et ce mécanisme est déjà construit, testé, et gratuit (NFR1).
"""

import base64
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from dotenv import load_dotenv

from veille.dedup import normaliser_url
from veille.models import Item

logger = logging.getLogger(__name__)

CHEMIN_LOCAL_DEFAUT = Path("data/deja-vu.sqlite3")

# Dépôt source (privé) — distinct de `publish.PUBLISH_REPO` (dépôt de
# sortie public) : cet état est un détail d'implémentation du pipeline,
# jamais publié.
#
# `CHEMIN_DISTANT` correspond au même motif `*.sqlite3` exclu par
# `.gitignore` (trouvé en revue) — sans contradiction : l'API Contents de
# GitHub écrit directement dans l'historique du dépôt sans jamais passer
# par une commande `git` locale, donc `.gitignore` (qui ne régit que le
# suivi local) ne s'applique tout simplement pas à cette écriture.
SOURCE_REPO = "petitlaye03/Agent_Veille_Tech"
CHEMIN_DISTANT = "data/deja-vu.sqlite3"
API_BASE = "https://api.github.com"

_env_charge = False
_avertissement_jeton_absent_emis = False


@dataclass(frozen=True)
class RapportDejaVu:
    """Ce que le filtrage « déjà vu » a écarté, par source — même patron
    que `filter.RapportFiltrageSignal` (Story 1.4)."""

    ecartes_par_source: dict[str, int] = field(default_factory=dict)

    @property
    def total_ecartes(self) -> int:
        return sum(self.ecartes_par_source.values())

    def resume(self) -> str:
        if not self.total_ecartes:
            return "Déjà vu : aucun item déjà publié une nuit précédente."
        ventilation = ", ".join(
            f"{source} (-{n})"
            for source, n in sorted(self.ecartes_par_source.items(), key=lambda x: (-x[1], x[0]))
        )
        return f"Déjà vu : {self.total_ecartes} item(s) déjà publié(s) une nuit précédente — {ventilation}"


def _cles_identite(item: Item) -> list[str]:
    """Mêmes identités que `dedup._cles_identite` (URL normalisée, `guid`
    scopé par source) — **sans** le repli par position de `dedup.py`
    (non pertinent ici : la position d'un item dans le lot d'une nuit n'a
    aucun sens d'une nuit à l'autre). Un item sans URL ni `guid` exploitable
    n'est simplement jamais reconnaissable comme « déjà vu » — conservé par
    défaut, jamais écarté sur une identité qu'on ne peut pas vérifier (même
    principe que `filtrer_par_signal` : l'absence de donnée n'est pas une
    présomption de doublon).
    """
    cles = []
    url_normalisee = normaliser_url(item.url)
    if url_normalisee:
        cles.append(f"url:{url_normalisee}")
    if item.guid:
        cles.append(f"guid:{item.source_id}:{item.guid}")
    return cles


def ouvrir(chemin: str | Path | None = None) -> sqlite3.Connection:
    """Ouvre (et crée si nécessaire) le fichier SQLite local. Ne lève
    jamais au sens applicatif : un chemin invalide ou un fichier corrompu
    ferait légitimement lever `sqlite3` — l'appelant (`pipeline.py`) isole
    ça comme toute autre panne de la nuit, pas cette fonction elle-même
    (cohérent avec le reste du projet : les fonctions de bas niveau ne
    décident pas de la politique d'isolation de leur appelant)."""
    chemin = Path(chemin) if chemin is not None else CHEMIN_LOCAL_DEFAUT
    chemin.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(chemin))
    # Mode journal fixé explicitement (trouvé en revue) : `televerser_vers_
    # distant` lit le fichier via `read_bytes()` brut, pas via une requête
    # SQL — si SQLite écrivait en mode WAL (persistant dans l'en-tête du
    # fichier, pourrait être hérité d'une connexion externe), des lignes
    # commitées pourraient rester dans un fichier `-wal` compagnon jamais lu
    # ni téléversé : une perte silencieuse de marques « vu ». DELETE (le
    # mode par défaut de sqlite3, ici rendu explicite plutôt qu'implicite)
    # garantit que chaque commit atterrit dans le fichier principal.
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("CREATE TABLE IF NOT EXISTS deja_vu (cle TEXT PRIMARY KEY)")
    # Santé des sources (AD-5, FR-12/13, Story 4.1) : même fichier, même
    # fonction d'ouverture — AD-5 désigne explicitement ce fichier SQLite
    # comme la seule source de vérité pour « le déjà vu par source **et**
    # l'État d'une Source », pas deux fichiers séparés. `health.py` reste
    # seul responsable de la logique de transition d'état ; ce module reste
    # seul responsable du schéma (un seul propriétaire par table, même
    # principe que pour `deja_vu`).
    conn.execute(
        "CREATE TABLE IF NOT EXISTS sante_source ("
        "source_id TEXT PRIMARY KEY, "
        "dernier_item_vu TEXT, "
        "etat TEXT NOT NULL DEFAULT 'active'"
        ")"
    )
    # Migration additive (Story 4.2, FR-13) : un fichier déjà synchronisé
    # créé par une version antérieure du code n'a pas cette colonne —
    # `ALTER TABLE ... ADD COLUMN` l'ajoute sans perdre les lignes
    # existantes. Vérifié via `PRAGMA table_info` plutôt qu'un
    # `try/except` sur le message d'erreur (corrigé en revue — trouvé par
    # l'Edge Case Hunter) : un `try/except sqlite3.OperationalError` qui ne
    # distingue « colonne déjà là » d'une vraie panne (ex. verrou) que par
    # un texte d'erreur ferait exécuter `ALTER TABLE` à **chaque** appel
    # d'`ouvrir()`, pas seulement la première fois — et ferait planter le
    # chemin nocturne normal sur toute erreur au message différent. Ici,
    # l'instruction ne s'exécute qu'une fois, seulement si la colonne
    # manque réellement.
    colonnes_existantes = {ligne[1] for ligne in conn.execute("PRAGMA table_info(sante_source)").fetchall()}
    if "dates_suspectes" not in colonnes_existantes:
        conn.execute("ALTER TABLE sante_source ADD COLUMN dates_suspectes INTEGER NOT NULL DEFAULT 0")
    conn.commit()
    return conn


_TAILLE_LOT_REQUETE = 500
# SQLite plafonne le nombre de paramètres liés par requête
# (`SQLITE_MAX_VARIABLE_NUMBER`, historiquement 999 sur nombre de
# distributions) — avec le socle de sources déjà étendu (Story 2.1, 17
# sources) et jusqu'à 2 clés d'identité par item, une seule requête
# `IN (...)` sur tout le lot d'une nuit peut dépasser ce plafond et lever
# `sqlite3.OperationalError` (trouvé en revue). Découpage en lots plutôt
# qu'une requête unique, pour que le filtrage reste correct à l'échelle au
# lieu de simplement échouer proprement.


def filtrer_deja_vus(items: list[Item], conn: sqlite3.Connection) -> tuple[list[Item], RapportDejaVu]:
    """Écarte les items dont au moins une identité est déjà connue —
    appelée **avant** tout filtrage (seuil de signal, dédoublonnage,
    scoring, quotas), conformément à l'AC de la Story 3.4.

    Ne lève jamais (trouvé en revue) : une panne ici (fichier corrompu,
    disque plein en cours de lecture…) dégrade en absence de filtrage
    « déjà vu » pour ce run plutôt que de faire échouer toute la nuit —
    même discipline que `synchroniser_depuis_distant`/`televerser_vers_
    distant`, qui l'annonçaient déjà pour elles-mêmes sans que ce soit
    encore vrai ici avant ce correctif.
    """
    if not items:
        return [], RapportDejaVu()

    toutes_les_cles = list({cle for item in items for cle in _cles_identite(item)})
    if not toutes_les_cles:
        return list(items), RapportDejaVu()

    try:
        cles_connues: set[str] = set()
        for debut in range(0, len(toutes_les_cles), _TAILLE_LOT_REQUETE):
            lot = toutes_les_cles[debut : debut + _TAILLE_LOT_REQUETE]
            placeholders = ",".join("?" * len(lot))
            lignes = conn.execute(
                f"SELECT cle FROM deja_vu WHERE cle IN ({placeholders})", tuple(lot)
            ).fetchall()
            cles_connues.update(ligne[0] for ligne in lignes)
    except Exception:  # noqa: BLE001 — isolation totale (trouvé en revue)
        logger.exception(
            "Échec du filtrage « déjà vu » — collecte sans ce filtrage pour cette nuit."
        )
        return list(items), RapportDejaVu()

    retenus: list[Item] = []
    ecartes_par_source: dict[str, int] = {}
    for item in items:
        if cles_connues.intersection(_cles_identite(item)):
            ecartes_par_source[item.source_id] = ecartes_par_source.get(item.source_id, 0) + 1
        else:
            retenus.append(item)

    return retenus, RapportDejaVu(ecartes_par_source=ecartes_par_source)


def marquer_vus(items: list[Item], conn: sqlite3.Connection) -> None:
    """Marque `items` comme vus.

    **À n'appeler qu'après une publication réussie** (AD-11) — jamais dans
    le chemin de collecte/filtrage lui-même, pour qu'un run qui échoue
    avant de publier puisse retenter les mêmes items à la prochaine
    reprise sans qu'aucun n'ait déjà été marqué.
    """
    for item in items:
        for cle in _cles_identite(item):
            conn.execute("INSERT OR IGNORE INTO deja_vu (cle) VALUES (?)", (cle,))
    conn.commit()


# --- Persistance à travers les runs GitHub Actions -------------------------


def _jeton() -> str | None:
    """`SOURCE_GITHUB_TOKEN` (`.env`, ou le jeton ambiant du workflow en
    CI) — **distinct** de `GITHUB_TOKEN`/`publish.py` (qui vise le dépôt de
    sortie via `DIGEST_PUBLISH_TOKEN`) : cette fonction écrit sur le dépôt
    **source**, pas le dépôt de sortie. En local, repli sur `gh auth token`
    (même patron que `publish._jeton_depuis_gh_cli`, dupliqué ici plutôt
    que réutilisé — module volontairement indépendant de `publish.py`,
    même esprit que les connecteurs qui ne partagent pas leur configuration
    réseau, AD-2)."""
    global _env_charge
    if not _env_charge:
        load_dotenv()
        _env_charge = True
    cle = (os.environ.get("SOURCE_GITHUB_TOKEN") or "").strip()
    if cle:
        return cle
    return _jeton_depuis_gh_cli()


def _jeton_depuis_gh_cli() -> str | None:
    import subprocess

    try:
        resultat = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if resultat.returncode != 0:
        return None
    jeton = resultat.stdout.strip()
    return jeton or None


def _client() -> httpx.Client | None:
    global _avertissement_jeton_absent_emis
    jeton = _jeton()
    if jeton is None:
        if not _avertissement_jeton_absent_emis:
            logger.warning(
                "Aucun jeton résolu pour le dépôt source (ni SOURCE_GITHUB_TOKEN, "
                "ni `gh auth token`) — l'état « déjà vu » restera local à ce run, "
                "non synchronisé."
            )
            _avertissement_jeton_absent_emis = True
        return None
    return httpx.Client(
        base_url=API_BASE,
        headers={"Authorization": f"Bearer {jeton}", "Accept": "application/vnd.github+json"},
        timeout=15.0,
    )


def synchroniser_depuis_distant(chemin_local: str | Path | None = None, client: httpx.Client | None = None) -> None:
    """Télécharge le fichier SQLite depuis le dépôt source vers `chemin_local`
    avant de l'ouvrir, s'il existe déjà à distance. Ne lève jamais : sans
    jeton résolu ou sur toute panne réseau, dégrade en laissant le fichier
    local tel quel (vide si c'est la toute première fois) — mieux vaut un
    run qui ne se souvient de rien qu'un run qui plante."""
    chemin_local = Path(chemin_local) if chemin_local is not None else CHEMIN_LOCAL_DEFAUT
    fourni = client is not None
    resolu = client if fourni else _client()
    if resolu is None:
        return

    try:
        reponse = resolu.get(f"/repos/{SOURCE_REPO}/contents/{CHEMIN_DISTANT}")
        if reponse.status_code == 404:
            logger.info("Aucun état « déjà vu » distant pour l'instant — première synchronisation.")
            return
        reponse.raise_for_status()
        contenu = base64.b64decode(reponse.json()["content"])
        chemin_local.parent.mkdir(parents=True, exist_ok=True)
        chemin_local.write_bytes(contenu)
    except Exception:  # noqa: BLE001 — isolation totale, jamais bloquer un run pour cet état
        logger.exception("Échec de la synchronisation de l'état « déjà vu » depuis le dépôt source.")
    finally:
        if not fourni:
            resolu.close()


def televerser_vers_distant(chemin_local: str | Path | None = None, client: httpx.Client | None = None) -> bool:
    """Publie le fichier SQLite local vers le dépôt source (upsert par
    `sha`, même mécanisme que `publish.py`). Ne lève jamais ; `False` sur
    tout échec — y compris l'absence de jeton résolu."""
    chemin_local = Path(chemin_local) if chemin_local is not None else CHEMIN_LOCAL_DEFAUT
    fourni = client is not None
    resolu = client if fourni else _client()
    if resolu is None:
        return False

    try:
        sha = None
        reponse_get = resolu.get(f"/repos/{SOURCE_REPO}/contents/{CHEMIN_DISTANT}")
        if reponse_get.status_code != 404:
            reponse_get.raise_for_status()
            sha = reponse_get.json().get("sha")

        contenu = chemin_local.read_bytes()
        corps = {
            "message": f"{'Mise à jour' if sha else 'Publication'} de l'état déjà-vu",
            "content": base64.b64encode(contenu).decode("ascii"),
        }
        if sha:
            corps["sha"] = sha

        reponse_put = resolu.put(f"/repos/{SOURCE_REPO}/contents/{CHEMIN_DISTANT}", json=corps)
        reponse_put.raise_for_status()
        return True
    except Exception:  # noqa: BLE001 — isolation totale
        logger.exception("Échec de la publication de l'état « déjà vu » vers le dépôt source.")
        return False
    finally:
        if not fourni:
            resolu.close()
