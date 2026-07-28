from datetime import datetime, timedelta, timezone

import pytest

from veille.models import Item


def _make_item(**overrides):
    defaults = dict(
        source_id="openai-news",
        guid="https://openai.com/news/example",
        titre="Un titre d'exemple",
        date_publication=datetime(2026, 7, 24, 10, 0, tzinfo=timezone.utc),
        langue="en",
        registre="ce_qui_bouge",
        url="https://openai.com/news/example",
        contenu_brut="Un extrait de contenu.",
    )
    defaults.update(overrides)
    return Item(**defaults)


def test_item_expose_tous_les_champs_invariants():
    item = _make_item()

    assert item.source_id == "openai-news"
    assert item.guid == "https://openai.com/news/example"
    assert item.titre == "Un titre d'exemple"
    assert item.date_publication == datetime(2026, 7, 24, 10, 0, tzinfo=timezone.utc)
    assert item.langue == "en"
    assert item.registre == "ce_qui_bouge"
    assert item.url == "https://openai.com/news/example"
    assert item.contenu_brut == "Un extrait de contenu."


def test_date_publication_doit_etre_timezone_aware():
    naive_datetime = datetime(2026, 7, 24, 10, 0)  # pas de tzinfo

    with pytest.raises(ValueError):
        _make_item(date_publication=naive_datetime)


def test_date_publication_doit_etre_en_utc():
    non_utc = datetime(2026, 7, 24, 10, 0, tzinfo=timezone.utc).astimezone(
        timezone(offset=timedelta(hours=1))
    )

    with pytest.raises(ValueError):
        _make_item(date_publication=non_utc)
