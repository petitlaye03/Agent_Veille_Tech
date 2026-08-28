from datetime import datetime, timedelta, timezone

import pytest

from veille.models import Entree, Item


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


def test_signal_est_absent_par_defaut():
    """Amendement AD-4 (2026-08-27) : signal est un champ optionnel, neutre
    par défaut — une source qui n'en fournit pas ne doit rien remarquer."""
    item = _make_item()

    assert item.signal is None


def test_signal_peut_etre_declare():
    item = _make_item(signal=18.0)

    assert item.signal == 18.0


# --- Story 1.6 : le type Entrée ------------------------------------------


def test_entree_expose_l_item_et_son_accroche():
    item = _make_item()

    entree = Entree(item=item, accroche="Une accroche en français.")

    assert entree.item is item
    assert entree.accroche == "Une accroche en français."


def test_entree_est_immuable():
    entree = Entree(item=_make_item(), accroche="Accroche.")

    with pytest.raises(AttributeError):
        entree.accroche = "Autre chose"


# --- Story 1.7 : Entree.recommandee --------------------------------------


def test_entree_n_est_pas_recommandee_par_defaut():
    """Une recommandation ne doit jamais être implicite (AC2, AC3)."""
    entree = Entree(item=_make_item(), accroche="Accroche.")

    assert entree.recommandee is False


def test_entree_peut_etre_declaree_recommandee():
    entree = Entree(item=_make_item(), accroche="Accroche.", recommandee=True)

    assert entree.recommandee is True
