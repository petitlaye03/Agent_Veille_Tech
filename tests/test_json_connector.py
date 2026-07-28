from datetime import timezone
from pathlib import Path

from veille.config import SourceConfig
from veille.connectors.json_connector import fetch

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _hf_source(url: str) -> SourceConfig:
    """Source HF Daily Papers telle qu'elle sera déclarée dans sources.yaml."""
    return SourceConfig(
        id="hf-daily-papers",
        type="json",
        url=url,
        langue="en",
        registre="apprendre",
        mapping={
            "guid": "paper.id",
            "titre": "title",
            "date_publication": "publishedAt",
            "contenu_brut": "paper.summary",
        },
        url_modele="https://huggingface.co/papers/{guid}",
    )


def test_fetch_produit_des_items_canoniques_depuis_une_api_json():
    source = _hf_source((FIXTURE_DIR / "hf_daily_papers.json").as_uri())

    items = fetch(source)

    assert len(items) == 2

    premier = items[0]
    assert premier.source_id == "hf-daily-papers"
    assert premier.guid == "2607.22682"
    assert premier.titre == "A Vocabulary for Multi-Agent Automated Research Systems"
    assert premier.url == "https://huggingface.co/papers/2607.22682"
    assert premier.date_publication.tzinfo == timezone.utc
    assert premier.date_publication.year == 2026
    assert "vocabulary for automated research" in premier.contenu_brut
    assert premier.langue == "en"
    assert premier.registre == "apprendre"


def test_le_mapping_vient_de_la_configuration_pas_du_code(tmp_path):
    """Une API de forme différente doit se brancher sans toucher au connecteur."""
    payload = tmp_path / "autre_api.json"
    payload.write_text(
        """
        {"resultats": [
          {"ref": "abc-1", "intitule": "Titre A", "date": "2026-07-01T08:00:00Z",
           "corps": {"texte": "Contenu A"}},
          {"ref": "abc-2", "intitule": "Titre B", "date": "2026-07-02T08:00:00Z",
           "corps": {"texte": "Contenu B"}}
        ]}
        """,
        encoding="utf-8",
    )

    source = SourceConfig(
        id="autre-api",
        type="json",
        url=payload.as_uri(),
        langue="fr",
        registre="pour_le_metier",
        racine="resultats",
        mapping={
            "guid": "ref",
            "titre": "intitule",
            "date_publication": "date",
            "contenu_brut": "corps.texte",
        },
        url_modele="https://exemple.invalid/{guid}",
    )

    items = fetch(source)

    assert [i.titre for i in items] == ["Titre A", "Titre B"]
    assert items[0].guid == "abc-1"
    assert items[0].url == "https://exemple.invalid/abc-1"
    assert items[0].contenu_brut == "Contenu A"


def test_un_champ_absent_du_mapping_ne_produit_pas_l_entree_entiere(tmp_path):
    """Un mapping incomplet doit laisser le champ vide, pas y coller tout le JSON."""
    payload = tmp_path / "sans_titre.json"
    payload.write_text(
        '[{"id": "abc-1", "title": "Un titre", "date": "2026-07-01T08:00:00Z"}]',
        encoding="utf-8",
    )

    source = SourceConfig(
        id="mapping-partiel",
        type="json",
        url=payload.as_uri(),
        langue="fr",
        registre="apprendre",
        # 'titre' et 'contenu_brut' volontairement absents du mapping
        mapping={"guid": "id", "date_publication": "date"},
    )

    items = fetch(source)

    assert len(items) == 1
    assert items[0].titre == ""
    assert items[0].contenu_brut == ""


def test_un_identifiant_numerique_zero_reste_valide(tmp_path):
    """0 est un identifiant légitime : il ne doit pas être confondu avec l'absence."""
    payload = tmp_path / "id_zero.json"
    payload.write_text(
        '[{"id": 0, "titre": "Premier"}, {"id": 1, "titre": "Second"}]',
        encoding="utf-8",
    )

    source = SourceConfig(
        id="api-zero",
        type="json",
        url=payload.as_uri(),
        langue="fr",
        registre="apprendre",
        mapping={"guid": "id", "titre": "titre"},
    )

    items = fetch(source)

    assert [i.guid for i in items] == ["0", "1"]


def test_une_entree_incomplete_est_ignoree_sans_perdre_les_autres(tmp_path):
    payload = tmp_path / "partiel.json"
    payload.write_text(
        """
        [
          {"id": "ok-1", "titre": "Bon", "date": "2026-07-01T08:00:00Z"},
          {"titre": "Sans identifiant ni date"},
          {"id": "ok-2", "titre": "Bon aussi", "date": "2026-07-02T08:00:00Z"}
        ]
        """,
        encoding="utf-8",
    )

    source = SourceConfig(
        id="api-partielle",
        type="json",
        url=payload.as_uri(),
        langue="fr",
        registre="apprendre",
        mapping={"guid": "id", "titre": "titre", "date_publication": "date"},
    )

    items = fetch(source)

    assert [i.guid for i in items] == ["ok-1", "ok-2"]
