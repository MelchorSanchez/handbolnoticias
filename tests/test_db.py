import sys
import sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pytest
from db import init_db, insert_article, article_id, get_articles_by_section, get_recent_by_section


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr("db.DB_PATH", tmp_path / "test.db")
    init_db()
    from db import get_connection
    return get_connection()


def sample_article(url="https://example.com/1", section="spain/asobal", extra_sections=""):
    return {
        "id": article_id(url),
        "url": url,
        "title": "Título de prueba",
        "title_orig": "Título de prueba",
        "summary": "Resumen",
        "image_url": None,
        "source_name": "test.es",
        "section": section,
        "extra_sections": extra_sections,
        "published": "2026-05-26T10:00:00+00:00",
        "fetched_at": "2026-05-26T12:00:00+00:00",
        "is_manual": 0,
    }


def test_insert_article_returns_true_for_new(conn):
    assert insert_article(conn, sample_article()) is True


def test_insert_article_returns_false_for_duplicate(conn):
    insert_article(conn, sample_article())
    assert insert_article(conn, sample_article()) is False


def test_article_id_is_deterministic():
    assert article_id("https://example.com") == article_id("https://example.com")


def test_article_id_differs_for_different_urls():
    assert article_id("https://a.com") != article_id("https://b.com")


def test_get_articles_by_section_returns_inserted(conn):
    insert_article(conn, sample_article())
    rows = get_articles_by_section(conn, "spain/asobal")
    assert len(rows) == 1
    assert rows[0]["title"] == "Título de prueba"


def test_get_articles_by_section_filters_by_section(conn):
    insert_article(conn, sample_article(url="https://a.com", section="spain/asobal"))
    insert_article(conn, sample_article(url="https://b.com", section="germany"))
    rows = get_articles_by_section(conn, "spain/asobal")
    assert len(rows) == 1


def test_get_recent_by_section_returns_top_n(conn):
    for i in range(10):
        insert_article(conn, sample_article(url=f"https://example.com/{i}"))
    rows = get_recent_by_section(conn, "spain/asobal", limit=3)
    assert len(rows) == 3


def test_get_articles_by_extra_section(conn):
    insert_article(conn, sample_article(url="https://a.com", section="spain/guerreras",
                                        extra_sections="europe/other"))
    assert len(get_articles_by_section(conn, "europe/other")) == 1
    assert len(get_articles_by_section(conn, "spain/guerreras")) == 1
    assert len(get_articles_by_section(conn, "spain/asobal")) == 0
