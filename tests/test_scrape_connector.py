from datetime import timezone
from pathlib import Path

from veille.config import SourceConfig
from veille.connectors.scrape_connector import fetch

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _anthropic_source() -> SourceConfig:
    return SourceConfig(
        id="anthropic-news",
        type="scrape",
        url=(FIXTURE_DIR / "anthropic_news.html").as_uri(),
        langue="en",
        registre="ce_qui_bouge",
        selecteur="/news/",
        base_url="https://www.anthropic.com",
    )


def test_fetch_produit_des_items_canoniques_depuis_une_page_html():
    items = fetch(_anthropic_source())

    # 4 articles exploitables ; les liens hors périmètre et l'entrée dégradée sont écartés
    assert len(items) == 4

    premier = items[0]
    assert premier.source_id == "anthropic-news"
    assert premier.titre == "Introducing Claude Opus 5"
    assert premier.url == "https://www.anthropic.com/news/claude-opus-5"
    assert premier.guid == "https://www.anthropic.com/news/claude-opus-5"
    assert premier.date_publication.tzinfo == timezone.utc
    assert premier.date_publication.year == 2026
    assert premier.date_publication.month == 7
    assert premier.date_publication.day == 24
    assert "step change improvement" in premier.contenu_brut


def test_le_titre_est_trouve_quel_que_soit_son_niveau_de_titrage():
    """La page mélange h2 (article en vedette) et h3 (articles courants)."""
    items = fetch(_anthropic_source())
    titres = [i.titre for i in items]

    assert "Introducing Claude Opus 5" in titres  # h2
    assert "Inviting hard questions" in titres  # h3


def test_le_titre_est_trouve_meme_sans_balise_de_titre_semantique():
    """La majorité des articles placent leur titre dans un span, pas dans un h2/h3."""
    items = fetch(_anthropic_source())
    par_url = {i.url: i for i in items}

    article = par_url["https://www.anthropic.com/news/position-open-weights-models"]

    # Le titre doit être le vrai titre, pas la catégorie ni la date du bloc méta
    assert article.titre == "Our position on open-weights models"
    assert article.date_publication.day == 27


def test_les_liens_hors_perimetre_sont_ecartes():
    items = fetch(_anthropic_source())

    assert all("/news/" in item.url for item in items)
    assert not any("pricing" in item.url or "twitter" in item.url for item in items)


def test_une_entree_sans_titre_exploitable_est_ignoree():
    items = fetch(_anthropic_source())

    assert not any("entree-degradee" in item.url for item in items)


def test_page_sans_lien_correspondant_retourne_liste_vide(tmp_path):
    page = tmp_path / "vide.html"
    page.write_text("<html><body><p>Rien à collecter ici.</p></body></html>", encoding="utf-8")

    source = SourceConfig(
        id="page-vide",
        type="scrape",
        url=page.as_uri(),
        langue="fr",
        registre="apprendre",
        selecteur="/news/",
        base_url="https://exemple.invalid",
    )

    assert fetch(source) == []
