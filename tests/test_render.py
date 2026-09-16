"""Tests du rendu HTML (FR-9, Story 1.8) — aucun appel réseau, tout est local."""

import re
from datetime import datetime, timezone

from veille.models import Entree, Item
from veille.render import BANDEAU_ECHEC_DEBUT, BANDEAU_ECHEC_FIN, rendre, rendre_bandeau_echec, rendre_markdown

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


# --- Story 1.9 : rendre_markdown -------------------------------------


def test_rendre_markdown_produit_les_trois_sections_dans_l_ordre():
    entrees = [
        _entree(guid="c", registre="pour_le_metier", titre="C"),
        _entree(guid="a", registre="apprendre", titre="A"),
        _entree(guid="b", registre="ce_qui_bouge", titre="B"),
    ]

    md = rendre_markdown(entrees, DATE_GEN)

    assert md.index("Apprendre") < md.index("Ce qui bouge") < md.index("Pour le métier")
    assert "A" in md and "B" in md and "C" in md


def test_rendre_markdown_affiche_titre_accroche_et_lien():
    """Le point final est volontairement absent de l'assertion : l'échappement
    Markdown (CommonMark autorise l'échappement de toute ponctuation ASCII,
    rendu ensuite comme le caractère littéral) le fait ressortir `\\.`, ce qui
    est correct et sans effet visuel une fois rendu — ce n'est pas ce que ce
    test vérifie."""
    entrees = [_entree(titre="Un article", url="https://example.invalid/x", accroche="Explication utile")]

    md = rendre_markdown(entrees, DATE_GEN)

    assert "Un article" in md
    assert "Explication utile" in md
    assert "https://example.invalid/x" in md


def test_rendre_markdown_echappe_les_caracteres_speciaux_du_titre():
    """AC4 : sans échappement, `*Alerte*` deviendrait de l'italique, pas
    du texte littéral."""
    entrees = [_entree(titre="*Alerte* [important]", accroche="ok")]

    md = rendre_markdown(entrees, DATE_GEN)

    assert "*Alerte*" not in md
    assert "\\*Alerte\\*" in md or "\\[important\\]" in md


def test_rendre_markdown_url_avec_parentheses_reste_un_lien_valide():
    """AC5 : une URL de type Wikipédia, avec parenthèses, casserait la
    syntaxe `[texte](url)` sans l'enveloppe `<...>`."""
    url = "https://fr.wikipedia.org/wiki/Exemple_(desambiguation)"
    entrees = [_entree(titre="Article", url=url)]

    md = rendre_markdown(entrees, DATE_GEN)

    assert f"(<{url}>)" in md


def test_rendre_markdown_url_a_schema_javascript_n_emet_aucun_lien():
    entrees = [_entree(titre="Payload", url="javascript:alert(1)")]

    md = rendre_markdown(entrees, DATE_GEN)

    assert "javascript:" not in md
    assert "](<" not in md


def test_rendre_markdown_registre_inconnu_est_journalise(caplog):
    entrees = [_entree(titre="Egaré", registre="aprendre")]

    with caplog.at_level("WARNING"):
        rendre_markdown(entrees, DATE_GEN)

    assert "aprendre" in caplog.text or "registre" in caplog.text.lower()


def test_rendre_markdown_liste_vide_affiche_un_message_honnete():
    md = rendre_markdown([], DATE_GEN)

    assert "rien à signaler" in md.lower()


def test_rendre_markdown_titre_vide_se_replie_sur_l_accroche():
    entrees = [_entree(titre="", accroche="Accroche de repli utile")]

    md = rendre_markdown(entrees, DATE_GEN)

    assert "Accroche de repli utile" in md


def test_rendre_markdown_echappe_les_balises_html_brutes():
    """Trouvé en revue (constat convergent, 2 couches) : `<` était absent de
    l'ensemble échappé — un `<img src=x onerror=...>` de source externe
    resterait une vraie balise HTML brute dans l'archive, malgré
    l'échappement des autres caractères."""
    entrees = [_entree(titre="<img src=x onerror=alert(1)>", accroche="ok")]

    md = rendre_markdown(entrees, DATE_GEN)

    # Aucun `<`/`>` non précédé d'un backslash ne doit subsister pour ce
    # titre (l'enveloppe `<...>` du lien vers l'original est un `<`/`>`
    # légitime et distinct, non concerné par cette assertion).
    assert not re.search(r"(?<!\\)<img", md)
    assert not re.search(r"alert\\\(1\\\)(?<!\\)>", md)
    assert "\\<img" in md


def test_rendre_markdown_ne_sur_echappe_pas_les_tirets_et_points():
    """Trouvé en revue (constat convergent, 2 couches) : échapper `-`/`.`
    partout, alors qu'ils ne sont syntaxiquement significatifs qu'en tout
    début de ligne (puce, liste numérotée), cassait l'AC6 (« cherchable
    par texte ») pour un cas aussi courant qu'un nom de modèle versionné.
    Les parenthèses, elles, restent échappées (dangereuses en milieu de
    texte aussi — voir le test des liens Wikipédia) : volontairement
    absentes de cette assertion."""
    entrees = [_entree(titre="GPT-5.2 : le futur de l'IA générative")]

    md = rendre_markdown(entrees, DATE_GEN)

    assert "GPT-5.2 : le futur de l'IA générative" in md


def test_rendre_markdown_neutralise_les_sauts_de_ligne_du_titre():
    """Trouvé en revue : un saut de ligne incorporé replacerait un caractère
    normalement inerte en milieu de texte (`-`, `#`) en tout début de
    ligne, où il redevient syntaxiquement actif — d'où la neutralisation
    des sauts de ligne plutôt que le seul échappement caractère par
    caractère."""
    entrees = [_entree(titre="Première ligne\n# Titre injecté\n- faux point")]

    md = rendre_markdown(entrees, DATE_GEN)

    assert "\n# Titre injecté" not in md
    assert "\n- faux point" not in md


def test_rendre_markdown_echappe_un_backslash_litteral():
    entrees = [_entree(titre=r"Chemin C:\Users\test")]

    md = rendre_markdown(entrees, DATE_GEN)

    assert r"C:\\Users\\test" in md


def test_rendre_markdown_url_vide_n_emet_aucun_lien():
    """Parité avec `rendre()` (HTML) — même garde-fou, mêmes cas testés."""
    entrees = [_entree(titre="Sans lien", url="")]

    md = rendre_markdown(entrees, DATE_GEN)

    assert "](<" not in md


def test_rendre_markdown_url_a_schema_data_n_emet_aucun_lien():
    """Parité avec `rendre()` (HTML) — même garde-fou, mêmes cas testés."""
    entrees = [_entree(titre="Payload", url="data:text/html,<script>alert(1)</script>")]

    md = rendre_markdown(entrees, DATE_GEN)

    assert "](<" not in md


def test_rendre_markdown_url_avec_chevrons_bruts_n_emet_aucun_lien():
    """Trouvé en revue : une URL contenant un `<`/`>` littéral fermerait
    prématurément l'enveloppe `<...>` du lien, faisant fuiter le reste de
    l'URL comme texte du document."""
    entrees = [_entree(titre="Article", url="https://example.invalid/x>malicious")]

    md = rendre_markdown(entrees, DATE_GEN)

    assert "](<" not in md


def test_rendre_bandeau_echec_contient_la_date_et_les_marqueurs():
    from datetime import date

    fragment = rendre_bandeau_echec(date(2026, 9, 15))

    assert fragment.startswith(BANDEAU_ECHEC_DEBUT)
    assert fragment.endswith(BANDEAU_ECHEC_FIN)
    assert "15/09/2026" in fragment  # %d/%m/%Y, cohérent avec le reste du site


def test_rendre_bandeau_echec_n_est_pas_un_document_complet():
    from datetime import date

    fragment = rendre_bandeau_echec(date(2026, 9, 15))

    assert "<!doctype html>" not in fragment.lower()
    assert "<body" not in fragment


def test_rendre_recapitulatif_sante_contient_les_marqueurs_et_chaque_source():
    from veille.render import RECAPITULATIF_SANTE_DEBUT, RECAPITULATIF_SANTE_FIN, rendre_recapitulatif_sante
    from veille.health import SourceASurveiller

    sources = [
        SourceASurveiller(source_id="src-1", etat="suspecte", raison="45 jour(s) sans nouvel item"),
        SourceASurveiller(source_id="src-2", etat="en_sommeil", raison="120 jour(s) sans nouvel item"),
    ]

    fragment = rendre_recapitulatif_sante(sources)

    assert fragment.startswith(RECAPITULATIF_SANTE_DEBUT)
    assert fragment.endswith(RECAPITULATIF_SANTE_FIN)
    assert "src-1" in fragment
    assert "suspecte" in fragment
    assert "45 jour" in fragment
    assert "src-2" in fragment
    assert "en_sommeil" in fragment
    assert "2 source" in fragment


def test_rendre_recapitulatif_sante_echappe_le_contenu():
    from veille.render import rendre_recapitulatif_sante
    from veille.health import SourceASurveiller

    sources = [SourceASurveiller(source_id="<script>alert(1)</script>", etat="suspecte", raison="x")]

    fragment = rendre_recapitulatif_sante(sources)

    assert "<script>" not in fragment
    assert "&lt;script&gt;" in fragment


def test_rendre_recapitulatif_sante_n_est_pas_un_document_complet():
    from veille.render import rendre_recapitulatif_sante
    from veille.health import SourceASurveiller

    fragment = rendre_recapitulatif_sante(
        [SourceASurveiller(source_id="src", etat="suspecte", raison="x")]
    )

    assert "<!doctype html>" not in fragment.lower()
    assert "<body" not in fragment
