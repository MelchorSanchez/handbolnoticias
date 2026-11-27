import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from classifier import _sections_from_teams, _contains_as_word_start


def test_team_name_inside_a_longer_word_does_not_match():
    # "Gradec" (Slovenj Gradec) caía dentro de "agradeció" y mandaba a Eslovenia
    # un artículo sobre los árbitros paraguayos.
    texto = ("rolando ferres dejó de ser el jefe de árbitros: el comité "
             "ejecutivo agradeció su profesionalismo")
    assert "slovenia" not in _sections_from_teams(texto)


def test_german_name_still_matches_as_prefix():
    # El match sigue abierto por la derecha: los compuestos alemanes añaden
    # sufijos al nombre de la ciudad.
    assert _contains_as_word_start("die flensburger handewitt", "flensburg")


def test_club_initials_in_a_social_handle_still_match():
    # "@bmguadalajara" es una mención buena aunque el nombre no empiece palabra.
    assert _contains_as_word_start("triangular con @bmguadalajara", "guadalajara")


def test_spanish_spelling_of_porto_matches():
    assert "portugal" in _sections_from_teams(
        "el barça venció al oporto en la supercopa ibérica")


def test_retrospective_signing_is_not_a_transfer():
    # "el porqué de su fichaje" habla del rendimiento, no de un traspaso.
    from classifier import resolve_sections
    primary, extra = resolve_sections({
        "url": "https://www.sport.es/es/videos/barca/balonmano/20261126/"
               "seif-elderaa-mostrando-fichaje-ultimos/136870428.shtml",
        "title_orig": "Seif Elderaa está mostrando por fin el porqué de su "
                      "fichaje en los últimos partidos en el Barça",
        "summary": "", "source_name": "Sport-balonmano", "section": "spain"})
    assert "fichajes" not in [primary] + extra
    # Un fichaje de verdad sigue entrando.
    primary, extra = resolve_sections({
        "url": "https://example.com/a", "title_orig": "El Barça ficha a Dika Mem",
        "summary": "", "source_name": "Sport-balonmano", "section": "spain"})
    assert "fichajes" in [primary] + extra
