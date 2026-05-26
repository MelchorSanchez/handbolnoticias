import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pytest
from unittest.mock import patch
from db import init_db, get_connection
from translator import translate_text, translate_article


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


def test_english_text_is_not_translated(conn):
    with patch("translator.detect", return_value="en"):
        result, lang = translate_text(conn, "Handball is great")
    assert result == "Handball is great"
    assert lang == "en"


def test_french_text_is_translated(conn):
    with patch("translator.detect", return_value="fr"), \
         patch("translator.GoogleTranslator") as mock_gt:
        mock_gt.return_value.translate.return_value = "El balonmano es genial"
        result, lang = translate_text(conn, "Le handball c'est super")
    assert result == "El balonmano es genial"
    assert lang == "fr"


def test_translation_is_cached(conn):
    with patch("translator.detect", return_value="de"), \
         patch("translator.GoogleTranslator") as mock_gt:
        mock_gt.return_value.translate.return_value = "Balonmano alemán"
        translate_text(conn, "Handball Deutschland")
        translate_text(conn, "Handball Deutschland")
        assert mock_gt.return_value.translate.call_count == 1


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
         patch("translator.GoogleTranslator") as mock_gt:
        mock_gt.return_value.translate.side_effect = ["El balonmano es genial", "Resumen"]
        result = translate_article(conn, article)
    assert result["title"] == "El balonmano es genial"
    assert result["title_orig"] == "Handball ist toll"
