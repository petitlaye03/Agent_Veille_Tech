from datetime import timezone
from pathlib import Path

import httpx
import pytest

from veille.config import SourceConfig
from veille.connectors.rss_connector import fetch

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _source_config(url: str) -> SourceConfig:
    return SourceConfig(
        id="test-source",
        type="rss",
        url=url,
        langue="fr",
        registre="apprendre",
    )


def test_fetch_produit_des_items_au_format_canonique():
    source_config = _source_config(str(FIXTURE_DIR / "sample_feed.xml"))

    items = fetch(source_config)

    assert len(items) == 2

    premier = items[0]
    assert premier.source_id == "test-source"
    assert premier.guid == "https://example.invalid/articles/premier"
    assert premier.titre == "Premier article de test"
    assert premier.date_publication.tzinfo == timezone.utc
    assert premier.date_publication.year == 2026
    assert premier.date_publication.month == 7
    assert premier.date_publication.day == 24
    assert premier.langue == "fr"
    assert premier.registre == "apprendre"
    assert premier.url == "https://example.invalid/articles/premier"
    assert "premier article" in premier.contenu_brut.lower()


def test_fetch_sur_flux_malforme_ne_leve_pas_et_retourne_liste_vide(tmp_path):
    flux_malforme = tmp_path / "malformed.xml"
    flux_malforme.write_text("ceci n'est pas du XML valide <<<", encoding="utf-8")

    items = fetch(_source_config(str(flux_malforme)))

    assert items == []


def test_fetch_utilise_un_hash_de_repli_si_aucune_url_stable(tmp_path):
    flux_sans_guid = tmp_path / "no_guid.xml"
    flux_sans_guid.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <title>Flux sans identifiants stables</title>
            <item>
              <title>Article sans lien ni guid</title>
              <pubDate>Fri, 24 Jul 2026 09:00:00 GMT</pubDate>
              <description>Un article sans URL stable.</description>
            </item>
          </channel>
        </rss>
        """,
        encoding="utf-8",
    )

    items = fetch(_source_config(str(flux_sans_guid)))

    assert len(items) == 1
    # 64 caractères hexadécimaux = empreinte SHA-256
    assert len(items[0].guid) == 64
    assert items[0].url == ""


def test_flux_imparfait_mais_exploitable_conserve_ses_entrees(tmp_path):
    """Une esperluette non échappée met bozo=1 alors que les entrées restent bonnes."""
    flux_imparfait = tmp_path / "imparfait.xml"
    flux_imparfait.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0"><channel><title>Flux imparfait</title>
        <item><title>Fish & Chips</title><link>https://example.invalid/a</link>
        <pubDate>Fri, 24 Jul 2026 10:00:00 GMT</pubDate>
        <description>Premier article.</description></item>
        <item><title>Deuxième</title><link>https://example.invalid/b</link>
        <pubDate>Fri, 24 Jul 2026 11:00:00 GMT</pubDate>
        <description>Deuxième article.</description></item>
        </channel></rss>
        """,
        encoding="utf-8",
    )

    items = fetch(_source_config(str(flux_imparfait)))

    assert len(items) == 2
    assert items[0].titre == "Fish & Chips"


def test_une_entree_cassee_ne_fait_pas_perdre_les_autres(tmp_path, monkeypatch):
    """L'isolation doit descendre au niveau de l'entrée, pas seulement de la source."""
    import veille.connectors.rss_connector as module

    original = module._to_item

    def _to_item_capricieux(entry, source_config):
        if entry.get("title") == "Premier article de test":
            raise ValueError("entrée corrompue simulée")
        return original(entry, source_config)

    monkeypatch.setattr(module, "_to_item", _to_item_capricieux)

    items = fetch(_source_config(str(FIXTURE_DIR / "sample_feed.xml")))

    assert len(items) == 1
    assert items[0].titre == "Deuxième article de test"


def test_url_reseau_est_recuperee_avec_un_delai_d_attente_explicite(monkeypatch):
    """Story 2.2 (AC2) : une source http(s) doit passer par httpx, timeout
    explicite — pas par la récupération interne de feedparser, sans timeout."""
    import veille.connectors.rss_connector as module

    appels = []

    def _get_espion(url, timeout, follow_redirects, headers):
        appels.append({"url": url, "timeout": timeout, "headers": headers})
        return httpx.Response(
            200,
            content=(FIXTURE_DIR / "sample_feed.xml").read_bytes(),
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(module.httpx, "get", _get_espion)

    items = fetch(_source_config("https://exemple.invalid/flux.xml"))

    assert len(items) == 2
    assert len(appels) == 1
    assert appels[0]["url"] == "https://exemple.invalid/flux.xml"
    assert appels[0]["timeout"] == module.TIMEOUT_SECONDES
    assert "User-Agent" in appels[0]["headers"]


def test_schema_insensible_a_la_casse_est_traite_comme_reseau(monkeypatch):
    """Trouvé en revue (Story 2.2) : un schéma `HTTP://` ne doit pas retomber
    silencieusement sur la branche locale (`str.startswith` était sensible à
    la casse, contrairement à `urlparse(...).scheme`)."""
    import veille.connectors.rss_connector as module

    def _get_espion(url, timeout, follow_redirects, headers):
        return httpx.Response(
            200,
            content=(FIXTURE_DIR / "sample_feed.xml").read_bytes(),
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(module.httpx, "get", _get_espion)

    items = fetch(_source_config("HTTP://exemple.invalid/flux.xml"))

    assert len(items) == 2


def test_chemin_local_ne_passe_pas_par_httpx(monkeypatch):
    """Les tests (et tout chemin non http(s)) doivent rester inchangés :
    feedparser continue de lire directement le fichier local."""
    import veille.connectors.rss_connector as module

    def _get_qui_ne_devrait_jamais_etre_appele(*args, **kwargs):
        raise AssertionError("httpx.get ne doit pas être appelé pour un chemin local")

    monkeypatch.setattr(module.httpx, "get", _get_qui_ne_devrait_jamais_etre_appele)

    items = fetch(_source_config(str(FIXTURE_DIR / "sample_feed.xml")))

    assert len(items) == 2


def test_encodage_reste_correct_malgre_un_en_tete_content_type_menteur(monkeypatch):
    """Risque identifié en Dev Notes (Story 2.2) : passer par `httpx` puis
    `feedparser.parse(bytes)` perd l'indice d'encodage de l'en-tête HTTP
    `Content-Type`. Vérifié en conditions réelles contre `tldr-ai` (même
    désaccord : le serveur déclare us-ascii, le corps est en réalité de
    l'UTF-8) sans perte d'entrée — mais une vérification de comptage
    n'aurait pas détecté un mauvais décodage silencieux (accents corrompus)
    qui préserve le nombre d'entrées. Ce test verrouille le contenu décodé,
    pas seulement le compte."""
    import veille.connectors.rss_connector as module

    contenu_utf8 = (
        """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0"><channel><title>Flux</title>
        <item><title>Article accentué : été, forêt, garçon</title>
        <link>https://example.invalid/a</link>
        <pubDate>Fri, 24 Jul 2026 10:00:00 GMT</pubDate>
        <description>Contenu.</description></item>
        </channel></rss>
        """
    ).encode("utf-8")

    def _get_charset_menteur(url, timeout, follow_redirects, headers):
        # Le serveur déclare us-ascii dans l'en-tête HTTP alors que le corps
        # est en réalité de l'UTF-8 — même désaccord que `tldr-ai` en réel.
        return httpx.Response(
            200,
            content=contenu_utf8,
            headers={"Content-Type": "application/rss+xml; charset=us-ascii"},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(module.httpx, "get", _get_charset_menteur)

    items = fetch(_source_config("https://exemple.invalid/flux.xml"))

    assert len(items) == 1
    assert items[0].titre == "Article accentué : été, forêt, garçon"


def test_erreur_http_leve_pour_etre_capturee_par_l_isolation_de_panne(monkeypatch):
    """Story 2.2 (AC3) : une panne HTTP (403/429/500...) doit lever une vraie
    exception — pas être avalée par le mécanisme `bozo`, où elle serait
    indiscernable d'un flux simplement vide (MUETTE plutôt qu'ÉCHEC)."""
    import veille.connectors.rss_connector as module

    def _get_403(url, timeout, follow_redirects, headers):
        return httpx.Response(403, request=httpx.Request("GET", url))

    monkeypatch.setattr(module.httpx, "get", _get_403)

    with pytest.raises(httpx.HTTPStatusError):
        fetch(_source_config("https://exemple.invalid/flux.xml"))


def test_timeout_reseau_leve_pour_etre_capture_par_l_isolation_de_panne(monkeypatch):
    """Story 2.2 (AC2) : un dépassement de délai d'attente doit lever, pas
    bloquer indéfiniment le run (dette suivie depuis la Story 1.1)."""
    import veille.connectors.rss_connector as module

    def _get_timeout(url, timeout, follow_redirects, headers):
        raise httpx.TimeoutException("délai d'attente dépassé")

    monkeypatch.setattr(module.httpx, "get", _get_timeout)

    with pytest.raises(httpx.TimeoutException):
        fetch(_source_config("https://exemple.invalid/flux.xml"))


def test_contenu_brut_retombe_sur_content_quand_summary_absent(tmp_path):
    """Les flux Atom exposent souvent `content` plutôt que `summary`."""
    flux_atom = tmp_path / "atom.xml"
    flux_atom.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <title>Flux Atom</title>
          <entry>
            <title>Article Atom</title>
            <link href="https://example.invalid/atom-1"/>
            <id>tag:example.invalid,2026:atom-1</id>
            <published>2026-07-24T10:00:00Z</published>
            <content type="text">Le contenu vit dans content, pas dans summary.</content>
          </entry>
        </feed>
        """,
        encoding="utf-8",
    )

    items = fetch(_source_config(str(flux_atom)))

    assert len(items) == 1
    assert "contenu vit dans content" in items[0].contenu_brut
