import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pytest
from db import init_db, get_connection, insert_article, article_id
from renderer import render_all


@pytest.fixture
def conn_with_data(tmp_path, monkeypatch):
    monkeypatch.setattr("db.DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr("renderer.OUTPUT_DIR", tmp_path / "docs")
    monkeypatch.setattr("renderer.TEMPLATES_DIR",
                        Path(__file__).parent.parent / "templates")
    init_db()
    conn = get_connection()
    conn.execute("""
        INSERT INTO articles (id, url, title, title_orig, summary, image_url,
            source_name, section, published, fetched_at, is_manual)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        article_id("https://example.com/test"),
        "https://example.com/test",
        "Noticia de prueba ASOBAL",
        "Noticia de prueba ASOBAL",
        "Resumen de la noticia",
        None,
        "test.es",
        "spain/asobal",
        "2026-05-26T10:00:00+00:00",
        "2026-05-26T12:00:00+00:00",
        0,
    ))
    conn.commit()
    return conn


def test_render_creates_index(conn_with_data, tmp_path):
    render_all(conn_with_data)
    index = tmp_path / "docs" / "index.html"
    assert index.exists()
    content = index.read_text()
    assert "HandbolNoticias" in content
    assert "Noticia de prueba ASOBAL" in content


def test_render_creates_section_page(conn_with_data, tmp_path):
    render_all(conn_with_data)
    section_page = tmp_path / "docs" / "spain" / "asobal" / "index.html"
    assert section_page.exists()
    content = section_page.read_text()
    assert "ASOBAL" in content
    assert "Noticia de prueba ASOBAL" in content


def test_render_creates_empty_section_page(conn_with_data, tmp_path):
    render_all(conn_with_data)
    section_page = tmp_path / "docs" / "germany" / "index.html"
    assert section_page.exists()
