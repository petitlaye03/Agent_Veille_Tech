"""Tests du rendu HTML (FR-9, Story 1.8) — aucun appel réseau, tout est local."""

from datetime import datetime, timezone

from veille.models import Entree, Item
from veille.render import rendre

DATE_GEN = datetime(2026, 8, 28, 22, 14, tzinfo=timezone.utc)


def _item(
    guid="a",
    titre="Titre",
    registre="apprendre",
    url="https://example.invalid/a",
    contenu_brut="",
):
    return Item(
        source_id="s",
        guid=guid,
        titre=titre,
        date_publication=datetime(2026, 8, 28, 21, 0, tzinfo=timezone.utc),
        langue="fr",
        registre=registre,
        url=url,
        contenu_brut=contenu_brut,
    )


def _entree(recommandee=False, accroche="Une accroche.", **kwargs):
    return Entree(item=_item(**kwargs), accroche=accroche, recommandee=recommandee)


def test_rendre_produit_les_trois_sections_dans_l_ordre():
    entrees = [
        _entree(guid="c", registre="pour_le_metier", titre="C"),
        _entree(guid="a", registre="apprendre", titre="A"),
        _entree(guid="b", registre="ce_qui_bouge", titre="B"),
    ]

    html = rendre(entrees, DATE_GEN)

    assert html.index("Apprendre") < html.index("Ce qui bouge") < html.index("Pour le métier")
    assert "A" in html and "B" in html and "C" in html


def test_rendre_affiche_titre_accroche_et_lien():
    entrees = [_entree(titre="Un article", url="https://example.invalid/x", accroche="Explication.")]

    html = rendre(entrees, DATE_GEN)

    assert "Un article" in html
    assert "Explication." in html
    assert 'href="https://example.invalid/x"' in html


def test_rendre_embarque_une_palette_et_une_typo_explicites():
    """Un <style> vide ou trivial ne serait pas une vraie palette (UX-DR1, NFR6)."""
    html = rendre([], DATE_GEN)

    assert "<style>" in html
    assert len(html.split("<style>")[1].split("</style>")[0].strip()) > 100


def test_rendre_a_un_viewport_mobile_first():
    html = rendre([], DATE_GEN)

    assert 'name="viewport"' in html
    assert "width=device-width" in html


def test_rendre_a_une_media_query_theme_sombre():
    html = rendre([], DATE_GEN)

    assert "prefers-color-scheme: dark" in html


def test_rendre_affiche_la_date_de_generation():
    html = rendre([], DATE_GEN)

    assert "28/08/2026" in html
    assert "22:14" in html


def test_rendre_marque_l_entree_recommandee():
    recommandee = _entree(guid="r", titre="Recommandée", recommandee=True)
    normale = _entree(guid="n", titre="Normale", recommandee=False)

    html = rendre([recommandee, normale], DATE_GEN)

    # Exactement une marque distincte, pour l'entrée recommandée seulement.
    # Recherche l'usage de la classe dans un attribut `class=`, pas la
    # simple sous-chaîne (qui matcherait aussi la règle CSS du <style>).
    assert html.count('class="entree entree--recommandee"') == 1


def test_rendre_echappe_le_contenu_malveillant():
    """AC8 : contenu de source externe non fiable, jamais rendu tel quel."""
    entrees = [_entree(titre="<script>alert(1)</script>", accroche="ok")]

    html = rendre(entrees, DATE_GEN)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_rendre_liste_vide_affiche_un_message_honnete():
    html = rendre([], DATE_GEN)

    assert "rien à signaler" in html.lower()


def test_rendre_titre_vide_se_replie_sur_l_accroche():
    """AC13 : un titre vide ne doit jamais apparaître comme un en-tête blanc."""
    entrees = [_entree(titre="", accroche="Accroche de repli.")]

    html = rendre(entrees, DATE_GEN)

    assert "Accroche de repli." in html


def test_rendre_url_vide_n_emet_aucun_lien():
    """AC13 : jamais une ancre vers nulle part ni un self-link."""
    entrees = [_entree(titre="Sans lien", url="")]

    html = rendre(entrees, DATE_GEN)

    assert "<a href=" not in html


def test_rendre_url_a_schema_javascript_n_emet_aucun_lien():
    """AC8 (trouvé en revue) : l'autoescaping HTML neutralise les
    métacaractères, jamais le schéma d'une URI — un flux compromis
    déclarant `<link>javascript:...</link>` produirait sinon un lien
    cliquable exécutable malgré l'échappement actif."""
    entrees = [_entree(titre="Payload", url="javascript:alert(1)")]

    html = rendre(entrees, DATE_GEN)

    assert "<a href=" not in html
    assert "javascript:" not in html


def test_rendre_url_a_schema_data_n_emet_aucun_lien():
    entrees = [_entree(titre="Payload", url="data:text/html,<script>alert(1)</script>")]

    html = rendre(entrees, DATE_GEN)

    assert "<a href=" not in html


def test_rendre_url_a_schema_javascript_en_majuscules_n_emet_aucun_lien():
    """Les navigateurs sont insensibles à la casse du schéma d'une URI —
    un contrôle sensible à la casse laisserait passer `JavaScript:...`."""
    entrees = [_entree(titre="Payload", url="JavaScript:alert(1)")]

    html = rendre(entrees, DATE_GEN)

    assert "<a href=" not in html


def test_rendre_url_https_reste_cliquable():
    """Non-régression : le garde-fou de schéma ne doit pas casser le cas normal."""
    entrees = [_entree(titre="Article normal", url="https://example.invalid/x")]

    html = rendre(entrees, DATE_GEN)

    assert 'href="https://example.invalid/x"' in html


def test_rendre_registre_inconnu_ne_fait_pas_disparaitre_l_entree_sans_trace(caplog):
    """Trouvé en revue : `repartir_par_quotas` conserve sans limite un
    registre absent de `Quotas` (Story 1.5) — un registre mal orthographié
    dans `sources.yaml` peut donc atteindre `rendre()`. Une entrée ainsi
    écartée du rendu doit au moins être journalisée, jamais silencieuse."""
    entrees = [_entree(titre="Egaré", registre="aprendre")]  # faute de frappe

    with caplog.at_level("WARNING"):
        html = rendre(entrees, DATE_GEN)

    assert "aprendre" in caplog.text or "registre" in caplog.text.lower()


def test_rendre_digest_vide_si_seules_des_entrees_a_registre_inconnu(caplog):
    """Le message honnête (AC9) doit se déclencher même quand `entrees`
    n'est pas vide mais qu'aucune section reconnue n'a de contenu — sinon
    la page ne montre ni les entrées (invisibles) ni le message, ce qui
    ressemble à une page cassée."""
    entrees = [_entree(titre="Egaré", registre="aprendre")]

    html = rendre(entrees, DATE_GEN)

    assert "rien à signaler" in html.lower()
