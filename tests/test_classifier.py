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
