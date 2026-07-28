from datetime import timezone
from pathlib import Path

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
