import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pytest
from unittest.mock import patch
from db import init_db, get_connection
from translator import translate_text, translate_article, retranslate_pending


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr("db.DB_PATH", tmp_path / "test.db")
    init_db()
    return get_connection()


def test_spanish_text_is_not_translated(conn):
    with patch("translator.detect", return_value="es"):
        result, lang = translate_text(conn, "Balonmano español es genial")
    assert result == "Balonmano español es genial"
    assert lang == "es"


def test_english_text_is_translated(conn):
    with patch("translator.detect", return_value="en"), \
         patch("translator._deepl_translate", return_value=("El balonmano es genial", "en")):
        result, lang = translate_text(conn, "Handball is great")
    assert result == "El balonmano es genial"
    assert lang == "en"


def test_source_hint_skips_langdetect(conn):
    # langdetect reads this short Polish headline as English
    with patch("translator.detect") as mock_detect, \
         patch("translator._deepl_translate", return_value=("El jueves arranca la Champions", "pl")):
        result, lang = translate_text(conn, "W czwartek startuje EHF Champions Cup", "pl")
    assert result == "El jueves arranca la Champions"
    assert lang == "pl"
    mock_detect.assert_not_called()


def test_spanish_detected_by_deepl_is_kept_and_cached(conn):
    with patch("translator.detect", return_value="pt"), \
         patch("translator._deepl_translate", return_value=("Ortega, sin confianzas", "es")) as mock_gt:
        assert translate_text(conn, "Ortega, sin confianzas")[0] == "Ortega, sin confianzas"
        assert translate_text(conn, "Ortega, sin confianzas")[0] == "Ortega, sin confianzas"
    assert mock_gt.call_count == 1


def test_source_lang_hint_from_sources_yaml():
    from translator import _lang_hint
    assert _lang_hint("Handnews-fr", "europe/champions") == "fr"
    assert _lang_hint("ZPRP-Poland", "europe/other") == "pl"
    assert _lang_hint("MiBalonmano", "europe/champions") is None
    assert _lang_hint("Desconocida", "germany/bundesliga") == "de"


def test_french_text_is_translated(conn):
    with patch("translator.detect", return_value="fr"), \
         patch("translator._deepl_translate") as mock_gt:
        mock_gt.return_value = ("El balonmano es genial", "fr")
        result, lang = translate_text(conn, "Le handball c'est super")
    assert result == "El balonmano es genial"
    assert lang == "fr"


def test_translation_is_cached(conn):
    with patch("translator.detect", return_value="de"), \
         patch("translator._deepl_translate") as mock_gt:
        mock_gt.return_value = ("Balonmano alemán", "de")
        translate_text(conn, "Handball Deutschland")
        translate_text(conn, "Handball Deutschland")
        assert mock_gt.call_count == 1


def test_empty_text_returns_as_is(conn):
    result, lang = translate_text(conn, "")
    assert result == ""
    assert lang is None


def test_translate_article_updates_title(conn):
    article = {
        "title": "Handball ist toll",
        "title_orig": "Handball ist toll",
        "summary": "Zusammenfassung",
    }
    with patch("translator.detect", return_value="de"), \
         patch("translator._deepl_translate") as mock_gt:
        mock_gt.side_effect = [("El balonmano es genial", "de"), ("Resumen", "de")]
        result = translate_article(conn, article)
    assert result["title"] == "El balonmano es genial"
    assert result["title_orig"] == "Handball ist toll"


def test_retranslate_pending_updates_untranslated_titles(conn):
    rows = [
        ("a1", "Handball ist toll", "germany/bundesliga"),
        ("a2", "Balonmano en Granollers", "spain/asobal"),
    ]
    for id_, title, section in rows:
        conn.execute(
            "INSERT INTO articles (id, url, title, title_orig, section, fetched_at, is_manual) "
            "VALUES (?, ?, ?, ?, ?, '2026-10-01T00:00:00+00:00', 0)",
            (id_, f"https://example.com/{id_}", title, title, section),
        )
    with patch("translator.detect", return_value="de"), \
         patch("translator._deepl_translate", return_value=("El balonmano es genial", "de")) as mock_gt:
        assert retranslate_pending(conn) == 1
    assert mock_gt.call_count == 1
    titles = dict(conn.execute("SELECT id, title FROM articles").fetchall())
    assert titles == {"a1": "El balonmano es genial", "a2": "Balonmano en Granollers"}
