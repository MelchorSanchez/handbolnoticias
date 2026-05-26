# HandbolNoticias Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a static handball news aggregator hosted on GitHub Pages that fetches RSS feeds, scrapes websites, and accepts manual links, updating daily via GitHub Actions.

**Architecture:** A Python pipeline (`fetcher.py` → `translator.py` → `renderer.py`) runs daily via GitHub Actions, stores articles in SQLite, and generates static HTML files in `docs/` using Jinja2 templates served by GitHub Pages.

**Tech Stack:** Python 3.12, feedparser, httpx, BeautifulSoup4, langdetect, deep-translator, Jinja2, SQLite, Tailwind CSS (CDN), GitHub Actions, GitHub Pages.

---

## File Map

| File | Responsibility |
|------|---------------|
| `scripts/db.py` | SQLite init, insert, query helpers |
| `scripts/fetcher.py` | RSS fetch + HTML scraping + manual links |
| `scripts/translator.py` | Language detection + Spanish translation with DB cache |
| `scripts/renderer.py` | Jinja2 → static HTML in `docs/` |
| `scripts/run_all.py` | Pipeline orchestrator |
| `config/sources.yaml` | Source definitions (RSS/scrape) |
| `config/manual_links.yaml` | User-added manual news links |
| `templates/base.html` | Shared layout: navbar, footer, Tailwind CDN |
| `templates/index.html` | Homepage with latest 5 articles per section |
| `templates/section.html` | Full article list for a section (last 30 days) |
| `tests/test_db.py` | DB layer tests |
| `tests/test_fetcher.py` | Fetcher tests (mocked HTTP) |
| `tests/test_translator.py` | Translator tests (mocked translation API) |
| `tests/test_renderer.py` | Renderer tests (HTML output assertions) |
| `.github/workflows/update.yml` | Daily cron + manual trigger |
| `requirements.txt` | Runtime dependencies |
| `requirements-dev.txt` | Test dependencies |
| `docs/.nojekyll` | Disables Jekyll processing on GitHub Pages |

---

## Task 1: Project setup

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `.gitignore`
- Create: `docs/.nojekyll`
- Create: `data/` (directory only, gitignored except `.gitkeep`)
- Create: `config/manual_links.yaml`

- [ ] **Step 1: Initialize git repo and create directory structure**

```bash
cd /home/melchor/science/handbolnoticias
git init
mkdir -p scripts tests templates config data docs
touch data/.gitkeep
touch docs/.nojekyll
```

- [ ] **Step 2: Create `requirements.txt`**

```
feedparser==6.0.11
httpx==0.27.0
beautifulsoup4==4.12.3
lxml==5.2.2
langdetect==1.0.9
deep-translator==1.11.4
Jinja2==3.1.4
PyYAML==6.0.2
```

- [ ] **Step 3: Create `requirements-dev.txt`**

```
-r requirements.txt
pytest==8.2.0
pytest-mock==3.14.0
respx==0.21.1
```

- [ ] **Step 4: Create `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
.env
data/articles.db
data/errors.log
```

Note: `articles.db` is gitignored locally. GitHub Actions will commit it directly in CI.

- [ ] **Step 5: Create `config/manual_links.yaml`**

```yaml
# Añade aquí links manuales a noticias de interés.
# El script los procesará en la próxima ejecución.
manual_links: []

# Ejemplo:
# manual_links:
#   - url: https://ejemplo.com/noticia
#     title: "Título opcional (si no, se auto-extrae)"
#     section: spain/asobal
#     date: "2026-05-26"
```

- [ ] **Step 6: Install dependencies**

```bash
pip install -r requirements-dev.txt
```

- [ ] **Step 7: Commit**

```bash
git add .
git commit -m "chore: initial project structure"
```

---

## Task 2: Database layer

**Files:**
- Create: `scripts/db.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_db.py`:

```python
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


def sample_article(url="https://example.com/1", section="spain/asobal"):
    return {
        "id": article_id(url),
        "url": url,
        "title": "Título de prueba",
        "title_orig": "Título de prueba",
        "summary": "Resumen",
        "image_url": None,
        "source_name": "test.es",
        "section": section,
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/melchor/science/handbolnoticias
python -m pytest tests/test_db.py -v
```

Expected: `ModuleNotFoundError: No module named 'db'`

- [ ] **Step 3: Create `scripts/db.py`**

```python
import hashlib
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "articles.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS articles (
                id          TEXT PRIMARY KEY,
                url         TEXT UNIQUE NOT NULL,
                title       TEXT NOT NULL,
                title_orig  TEXT,
                summary     TEXT,
                image_url   TEXT,
                source_name TEXT,
                section     TEXT NOT NULL,
                published   TEXT,
                fetched_at  TEXT NOT NULL,
                is_manual   INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS translations (
                text_hash   TEXT PRIMARY KEY,
                original    TEXT NOT NULL,
                translated  TEXT NOT NULL,
                lang_from   TEXT
            );
        """)


def article_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def insert_article(conn: sqlite3.Connection, article: dict) -> bool:
    try:
        conn.execute("""
            INSERT INTO articles
                (id, url, title, title_orig, summary, image_url,
                 source_name, section, published, fetched_at, is_manual)
            VALUES
                (:id, :url, :title, :title_orig, :summary, :image_url,
                 :source_name, :section, :published, :fetched_at, :is_manual)
        """, article)
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def get_articles_by_section(conn: sqlite3.Connection, section: str, days: int = 30) -> list:
    return conn.execute("""
        SELECT * FROM articles
        WHERE section = ?
          AND (published > datetime('now', ? || ' days') OR published IS NULL)
        ORDER BY published DESC, fetched_at DESC
        LIMIT 100
    """, (section, f"-{days}")).fetchall()


def get_recent_by_section(conn: sqlite3.Connection, section: str, limit: int = 5) -> list:
    return conn.execute("""
        SELECT * FROM articles
        WHERE section = ?
        ORDER BY published DESC, fetched_at DESC
        LIMIT ?
    """, (section, limit)).fetchall()


def get_all_sections(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT DISTINCT section FROM articles").fetchall()
    return [row["section"] for row in rows]
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/test_db.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/db.py tests/test_db.py
git commit -m "feat: add SQLite database layer with insert and query helpers"
```

---

## Task 3: RSS Fetcher

**Files:**
- Create: `scripts/fetcher.py` (RSS section only)
- Create: `tests/test_fetcher.py` (RSS tests only)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_fetcher.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pytest
from unittest.mock import patch, MagicMock
from fetcher import fetch_rss, extract_image


RSS_SOURCE = {
    "name": "Test Feed",
    "section": "spain/asobal",
    "type": "rss",
    "url": "https://example.com/feed/",
    "max_items": 10,
}

MOCK_ENTRY = MagicMock()
MOCK_ENTRY.get.side_effect = lambda k, d="": {
    "link": "https://example.com/noticia-1",
    "title": "Gran partido de ASOBAL",
    "summary": "<p>Resumen de la noticia</p>",
    "published": "2026-05-26T10:00:00+00:00",
}.get(k, d)
MOCK_ENTRY.enclosures = []
MOCK_ENTRY.media_content = []


def test_fetch_rss_returns_articles():
    mock_feed = MagicMock()
    mock_feed.entries = [MOCK_ENTRY]
    with patch("fetcher.feedparser.parse", return_value=mock_feed):
        articles = fetch_rss(RSS_SOURCE)
    assert len(articles) == 1
    assert articles[0]["url"] == "https://example.com/noticia-1"
    assert articles[0]["title"] == "Gran partido de ASOBAL"
    assert articles[0]["section"] == "spain/asobal"
    assert articles[0]["source_name"] == "Test Feed"
    assert articles[0]["is_manual"] == 0


def test_fetch_rss_skips_entry_without_link():
    no_link = MagicMock()
    no_link.get.side_effect = lambda k, d="": {"link": "", "title": "X", "summary": "", "published": ""}.get(k, d)
    no_link.enclosures = []
    no_link.media_content = []
    mock_feed = MagicMock()
    mock_feed.entries = [no_link]
    with patch("fetcher.feedparser.parse", return_value=mock_feed):
        articles = fetch_rss(RSS_SOURCE)
    assert articles == []


def test_fetch_rss_returns_empty_on_error():
    with patch("fetcher.feedparser.parse", side_effect=Exception("Network error")):
        articles = fetch_rss(RSS_SOURCE)
    assert articles == []


def test_fetch_rss_respects_max_items():
    mock_feed = MagicMock()
    mock_feed.entries = [MOCK_ENTRY] * 20
    source = {**RSS_SOURCE, "max_items": 5}
    with patch("fetcher.feedparser.parse", return_value=mock_feed):
        articles = fetch_rss(source)
    assert len(articles) == 5


def test_extract_image_from_enclosure():
    entry = MagicMock()
    entry.enclosures = [{"type": "image/jpeg", "href": "https://example.com/img.jpg"}]
    assert extract_image(entry) == "https://example.com/img.jpg"


def test_extract_image_returns_none_when_absent():
    entry = MagicMock()
    entry.enclosures = []
    entry.media_content = []
    entry.summary = "<p>No image here</p>"
    assert extract_image(entry) is None
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_fetcher.py -v
```

Expected: `ModuleNotFoundError: No module named 'fetcher'`

- [ ] **Step 3: Create `scripts/fetcher.py` with RSS support**

```python
import hashlib
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

import feedparser
import httpx
import yaml
from bs4 import BeautifulSoup
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).parent.parent / "config"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; HandbolNoticias/1.0; +https://github.com/handbolnoticias)"}
TIMEOUT = 10.0


def load_sources() -> list:
    with open(CONFIG_DIR / "sources.yaml") as f:
        return yaml.safe_load(f)["sources"]


def _article_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def extract_image(entry) -> str | None:
    if hasattr(entry, "enclosures") and entry.enclosures:
        for enc in entry.enclosures:
            if enc.get("type", "").startswith("image"):
                return enc.get("href")
    if hasattr(entry, "media_content") and entry.media_content:
        return entry.media_content[0].get("url")
    summary = getattr(entry, "summary", "") or ""
    if summary:
        soup = BeautifulSoup(summary, "lxml")
        img = soup.find("img")
        if img and img.get("src"):
            return img["src"]
    return None


def fetch_rss(source: dict) -> list[dict]:
    try:
        feed = feedparser.parse(source["url"])
        articles = []
        for entry in feed.entries[: source.get("max_items", 50)]:
            url = entry.get("link", "")
            if not url:
                continue
            summary_html = entry.get("summary", "") or ""
            summary_text = BeautifulSoup(summary_html, "lxml").get_text()[:500]
            articles.append({
                "id": _article_id(url),
                "url": url,
                "title": entry.get("title", "").strip(),
                "title_orig": entry.get("title", "").strip(),
                "summary": summary_text,
                "image_url": extract_image(entry),
                "source_name": source["name"],
                "section": source["section"],
                "published": entry.get("published", _now()),
                "fetched_at": _now(),
                "is_manual": 0,
            })
        return articles
    except Exception as exc:
        logger.error("RSS error %s: %s", source["name"], exc)
        return []
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/test_fetcher.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/fetcher.py tests/test_fetcher.py
git commit -m "feat: add RSS fetcher with image extraction"
```

---

## Task 4: Web Scraper

**Files:**
- Modify: `scripts/fetcher.py` (add `fetch_scrape`, `fetch_all`)
- Modify: `tests/test_fetcher.py` (add scraping tests)

- [ ] **Step 1: Add failing scraping tests to `tests/test_fetcher.py`**

Append to `tests/test_fetcher.py`:

```python
import respx
import httpx as _httpx

SCRAPE_SOURCE = {
    "name": "Test Scraper",
    "section": "spain/catalonia",
    "type": "scrape",
    "url": "https://example-scrape.com/noticias",
    "max_items": 10,
    "selectors": {
        "articles": "article.news",
        "title": "h2",
        "link": "a",
        "image": "img",
    },
}

SAMPLE_HTML = """
<html><body>
  <article class="news">
    <h2><a href="/noticia-1">Cataluña gana el campeonato</a></h2>
    <a href="/noticia-1">Leer más</a>
    <img src="/img/noticia.jpg">
  </article>
</body></html>
"""


@respx.mock
def test_fetch_scrape_returns_articles():
    respx.get("https://example-scrape.com/noticias").mock(
        return_value=_httpx.Response(200, text=SAMPLE_HTML)
    )
    from fetcher import fetch_scrape
    articles = fetch_scrape(SCRAPE_SOURCE)
    assert len(articles) == 1
    assert articles[0]["title"] == "Cataluña gana el campeonato"
    assert articles[0]["url"] == "https://example-scrape.com/noticia-1"
    assert articles[0]["section"] == "spain/catalonia"


@respx.mock
def test_fetch_scrape_returns_empty_on_http_error():
    respx.get("https://example-scrape.com/noticias").mock(
        return_value=_httpx.Response(403)
    )
    from fetcher import fetch_scrape
    articles = fetch_scrape(SCRAPE_SOURCE)
    assert articles == []


def test_fetch_all_combines_rss_and_scrape():
    sources = [
        {**RSS_SOURCE, "url": "https://rss.example.com/feed/"},
        {**SCRAPE_SOURCE, "url": "https://scrape.example.com/news"},
    ]
    mock_feed = MagicMock()
    mock_feed.entries = [MOCK_ENTRY]

    with patch("fetcher.feedparser.parse", return_value=mock_feed), \
         respx.mock:
        respx.get("https://scrape.example.com/news").mock(
            return_value=_httpx.Response(200, text=SAMPLE_HTML)
        )
        from fetcher import fetch_all
        articles = fetch_all(sources)

    assert any(a["section"] == "spain/asobal" for a in articles)
    assert any(a["section"] == "spain/catalonia" for a in articles)
```

- [ ] **Step 2: Run new tests to confirm they fail**

```bash
python -m pytest tests/test_fetcher.py::test_fetch_scrape_returns_articles -v
```

Expected: `ImportError: cannot import name 'fetch_scrape'`

- [ ] **Step 3: Add `fetch_scrape` and `fetch_all` to `scripts/fetcher.py`**

Append to `scripts/fetcher.py`:

```python
def fetch_scrape(source: dict) -> list[dict]:
    try:
        resp = httpx.get(source["url"], headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        sel = source["selectors"]
        base = urlparse(source["url"])
        articles = []
        for item in soup.select(sel["articles"])[: source.get("max_items", 30)]:
            title_el = item.select_one(sel["title"])
            link_el = item.select_one(sel["link"])
            if not title_el or not link_el:
                continue
            href = link_el.get("href", "")
            if href.startswith("/"):
                href = f"{base.scheme}://{base.netloc}{href}"
            if not href:
                continue
            img_el = item.select_one(sel.get("image", "img"))
            image_url = img_el.get("src") if img_el else None
            if image_url and image_url.startswith("/"):
                image_url = f"{base.scheme}://{base.netloc}{image_url}"
            articles.append({
                "id": _article_id(href),
                "url": href,
                "title": title_el.get_text().strip(),
                "title_orig": title_el.get_text().strip(),
                "summary": "",
                "image_url": image_url,
                "source_name": source["name"],
                "section": source["section"],
                "published": _now(),
                "fetched_at": _now(),
                "is_manual": 0,
            })
        return articles
    except Exception as exc:
        logger.error("Scrape error %s: %s", source["name"], exc)
        return []


def fetch_manual_links() -> list[dict]:
    path = CONFIG_DIR / "manual_links.yaml"
    if not path.exists():
        return []
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    articles = []
    for link in data.get("manual_links", []):
        url = link["url"]
        articles.append({
            "id": _article_id(url),
            "url": url,
            "title": link.get("title", url),
            "title_orig": link.get("title", url),
            "summary": "",
            "image_url": None,
            "source_name": "Manual",
            "section": link["section"],
            "published": link.get("date", _now()),
            "fetched_at": _now(),
            "is_manual": 1,
        })
    return articles


def fetch_all(sources: list) -> list[dict]:
    articles = []
    for source in sources:
        if source["type"] == "rss":
            articles.extend(fetch_rss(source))
        elif source["type"] == "scrape":
            articles.extend(fetch_scrape(source))
    articles.extend(fetch_manual_links())
    return articles
```

- [ ] **Step 4: Run all fetcher tests**

```bash
python -m pytest tests/test_fetcher.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/fetcher.py tests/test_fetcher.py
git commit -m "feat: add web scraper and manual links support to fetcher"
```

---

## Task 5: Translator

**Files:**
- Create: `scripts/translator.py`
- Create: `tests/test_translator.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_translator.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pytest
from unittest.mock import patch, MagicMock
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_translator.py -v
```

Expected: `ModuleNotFoundError: No module named 'translator'`

- [ ] **Step 3: Create `scripts/translator.py`**

```python
import hashlib
import logging

from deep_translator import GoogleTranslator
from langdetect import LangDetectException, detect

logger = logging.getLogger(__name__)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _get_cached(conn, text: str) -> str | None:
    row = conn.execute(
        "SELECT translated FROM translations WHERE text_hash = ?",
        (_hash(text),),
    ).fetchone()
    return row["translated"] if row else None


def _cache(conn, original: str, translated: str, lang_from: str):
    conn.execute(
        "INSERT OR IGNORE INTO translations (text_hash, original, translated, lang_from) VALUES (?, ?, ?, ?)",
        (_hash(original), original, translated, lang_from),
    )
    conn.commit()


def translate_text(conn, text: str) -> tuple[str, str | None]:
    if not text or not text.strip():
        return text, None
    try:
        lang = detect(text)
    except LangDetectException:
        return text, None
    if lang in ("es", "en"):
        return text, lang
    cached = _get_cached(conn, text)
    if cached:
        return cached, lang
    try:
        translated = GoogleTranslator(source="auto", target="es").translate(text)
        _cache(conn, text, translated, lang)
        return translated, lang
    except Exception as exc:
        logger.error("Translation error: %s", exc)
        return text, lang


def translate_article(conn, article: dict) -> dict:
    translated_title, _ = translate_text(conn, article["title_orig"])
    article["title"] = translated_title
    if article.get("summary"):
        translated_summary, _ = translate_text(conn, article["summary"][:300])
        article["summary"] = translated_summary
    return article
```

- [ ] **Step 4: Run all translator tests**

```bash
python -m pytest tests/test_translator.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/translator.py tests/test_translator.py
git commit -m "feat: add translator with DB-cached translations"
```

---

## Task 6: Sources configuration

**Files:**
- Create: `config/sources.yaml`

- [ ] **Step 1: Create `config/sources.yaml` with all known sources**

```yaml
sources:
  # ── España — ASOBAL ──────────────────────────────────────────────────────
  - name: RFEBM
    section: spain/asobal
    type: rss
    url: https://www.rfebm.com/feed/
    max_items: 50

  - name: LigaAsobal
    section: spain/asobal
    type: rss
    url: https://www.ligaasobal.es/feed/      # verificar URL real
    max_items: 50

  - name: MiBalonmano
    section: spain/asobal
    type: rss
    url: https://www.mibalonmano.es/feed/
    max_items: 50

  - name: BalonmanoCentral
    section: spain/asobal
    type: rss
    url: https://www.balonmanocentral.com/feed/
    max_items: 50

  - name: Balonmano100x100
    section: spain/asobal
    type: rss
    url: https://www.balonmano100x100.es/feed/
    max_items: 30

  - name: Balonmano.info
    section: spain/asobal
    type: rss
    url: https://www.balonmano.info/feed/
    max_items: 30

  # ── España — División Honor Plata ─────────────────────────────────────────
  - name: MiBalonmano-DHP
    section: spain/dhp
    type: rss
    url: https://www.mibalonmano.es/category/division-honor-plata/feed/
    max_items: 30

  # ── España — Femenino ─────────────────────────────────────────────────────
  - name: RFEBM-Femenino
    section: spain/guerreras
    type: rss
    url: https://www.rfebm.com/category/femenino/feed/  # verificar
    max_items: 30

  # ── España — Cataluña ─────────────────────────────────────────────────────
  - name: CatHandbol
    section: spain/catalonia
    type: rss
    url: https://www.cathandbol.cat/feed/
    max_items: 30

  # ── España — Prensa deportiva nacional ────────────────────────────────────
  - name: Marca-Balonmano
    section: spain/asobal
    type: scrape
    url: https://www.marca.com/balonmano.html
    max_items: 20
    selectors:
      articles: "article"
      title: "h2, h3"
      link: "a[href]"
      image: "img"

  - name: AS-Balonmano
    section: spain/asobal
    type: scrape
    url: https://as.com/balonmano/
    max_items: 20
    selectors:
      articles: "article"
      title: "h2, h3"
      link: "a[href]"
      image: "img"

  - name: MundoDeportivo-Balonmano
    section: spain/asobal
    type: scrape
    url: https://www.mundodeportivo.com/balonmano
    max_items: 20
    selectors:
      articles: "article"
      title: "h2, h3"
      link: "a[href]"
      image: "img"

  # ── Europa ────────────────────────────────────────────────────────────────
  - name: EHF Champions League
    section: europe/champions
    type: rss
    url: https://www.ehf-euro.com/feed/          # verificar
    max_items: 30

  - name: EHF
    section: europe/champions
    type: scrape
    url: https://www.eurohandball.com/en/news/
    max_items: 30
    selectors:
      articles: "article, .news-item"
      title: "h2, h3, .title"
      link: "a[href]"
      image: "img"

  # ── Internacional — Francia ───────────────────────────────────────────────
  - name: LNH-Starligue
    section: france
    type: scrape
    url: https://www.lnh.fr/fr/actualites
    max_items: 20
    selectors:
      articles: "article, .news-card"
      title: "h2, h3"
      link: "a[href]"
      image: "img"

  # ── Internacional — Alemania ──────────────────────────────────────────────
  - name: HBL-Bundesliga
    section: germany
    type: scrape
    url: https://www.liquimoly-hbl.de/news/
    max_items: 20
    selectors:
      articles: "article, .news-item"
      title: "h2, h3"
      link: "a[href]"
      image: "img"

  # ── Internacional — Dinamarca ─────────────────────────────────────────────
  - name: Handball-Dinamarca
    section: denmark
    type: scrape
    url: https://www.dhf.dk/nyheder/
    max_items: 20
    selectors:
      articles: "article, .news"
      title: "h2, h3"
      link: "a[href]"
      image: "img"

  # ── Internacional — Noruega ───────────────────────────────────────────────
  - name: NHF-Noruega
    section: norway
    type: scrape
    url: https://www.handball.no/nyheter/
    max_items: 20
    selectors:
      articles: "article"
      title: "h2, h3"
      link: "a[href]"
      image: "img"

  # ── Internacional — Portugal ──────────────────────────────────────────────
  - name: FPA-Portugal
    section: portugal
    type: scrape
    url: https://www.fpa.pt/noticias
    max_items: 20
    selectors:
      articles: "article, .noticia"
      title: "h2, h3"
      link: "a[href]"
      image: "img"

  # ── Nota: añadir más fuentes para Suecia, Austria, Suiza, Islandia,
  #         Islas Feroe, Hungría, Polonia, Croacia, Serbia, Eslovaquia,
  #         Rumania, Argentina, Brasil y Japón siguiendo el mismo patrón.
  #         Los selectores CSS necesitan verificación visitando cada sitio.
```

- [ ] **Step 2: Verify at least 3 RSS feeds parse correctly**

```bash
cd /home/melchor/science/handbolnoticias
python -c "
import sys; sys.path.insert(0, 'scripts')
import feedparser
feeds = [
    'https://www.rfebm.com/feed/',
    'https://www.mibalonmano.es/feed/',
    'https://www.cathandbol.cat/feed/',
]
for url in feeds:
    f = feedparser.parse(url)
    print(f'{url}: {len(f.entries)} entries')
"
```

Expected: each URL prints a number > 0. If a feed returns 0 entries, update its URL in `sources.yaml` to the correct path.

- [ ] **Step 3: Commit**

```bash
git add config/sources.yaml
git commit -m "feat: add sources configuration with all known handball news sites"
```

---

## Task 7: HTML Templates

**Files:**
- Create: `templates/base.html`
- Create: `templates/index.html`
- Create: `templates/section.html`

- [ ] **Step 1: Create `templates/base.html`**

```html
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}HandbolNoticias{% endblock %}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .bg-hb-blue  { background-color: #003DA5; }
        .text-hb-blue { color: #003DA5; }
        .text-hb-orange { color: #FF6B00; }
        .border-hb-orange { border-color: #FF6B00; }
        .text-spain-red { color: #CC0000; }
        .border-spain-red { border-color: #CC0000; }
        .text-europe-green { color: #2E7D32; }
        .border-europe-green { border-color: #2E7D32; }
        .group:hover .group-hover\:block { display: block; }
    </style>
</head>
<body class="bg-gray-50 text-gray-900 min-h-screen flex flex-col">

<nav class="bg-hb-blue text-white shadow-lg sticky top-0 z-40">
    <div class="max-w-7xl mx-auto px-4 flex items-center justify-between h-14">
        <a href="/" class="font-bold text-xl tracking-tight flex items-center gap-2">
            🤾 <span>HandbolNoticias</span>
        </a>
        <div class="flex gap-6 text-sm font-medium">
            <!-- España -->
            <div class="relative group">
                <button class="hover:text-orange-300 py-4">España ▾</button>
                <div class="hidden group-hover:block absolute top-full left-0 bg-white text-gray-800 shadow-xl rounded-lg min-w-52 z-50 py-1">
                    <div class="px-3 py-1 text-xs font-bold text-gray-400 uppercase tracking-wider">Masculino</div>
                    <a href="/spain/asobal/" class="block px-4 py-2 hover:bg-red-50 hover:text-red-700 text-sm">ASOBAL</a>
                    <a href="/spain/dhp/" class="block px-4 py-2 hover:bg-red-50 hover:text-red-700 text-sm">División Honor Plata</a>
                    <a href="/spain/primera-nacional-masc/" class="block px-4 py-2 hover:bg-red-50 hover:text-red-700 text-sm">Primera Nacional</a>
                    <div class="border-t mx-3 my-1"></div>
                    <div class="px-3 py-1 text-xs font-bold text-gray-400 uppercase tracking-wider">Femenino</div>
                    <a href="/spain/guerreras/" class="block px-4 py-2 hover:bg-red-50 hover:text-red-700 text-sm">Liga Guerreras Iberdrola</a>
                    <a href="/spain/dho-fem/" class="block px-4 py-2 hover:bg-red-50 hover:text-red-700 text-sm">División Honor Oro</a>
                    <a href="/spain/dhp-fem/" class="block px-4 py-2 hover:bg-red-50 hover:text-red-700 text-sm">División Honor Plata</a>
                    <div class="border-t mx-3 my-1"></div>
                    <div class="px-3 py-1 text-xs font-bold text-gray-400 uppercase tracking-wider">Territorial</div>
                    <a href="/spain/catalonia/" class="block px-4 py-2 hover:bg-red-50 hover:text-red-700 text-sm">Cataluña</a>
                    <a href="/spain/navarra/" class="block px-4 py-2 hover:bg-red-50 hover:text-red-700 text-sm">Navarra</a>
                    <a href="/spain/euskadi/" class="block px-4 py-2 hover:bg-red-50 hover:text-red-700 text-sm">País Vasco</a>
                </div>
            </div>
            <!-- Europa -->
            <div class="relative group">
                <button class="hover:text-orange-300 py-4">Europa ▾</button>
                <div class="hidden group-hover:block absolute top-full left-0 bg-white text-gray-800 shadow-xl rounded-lg min-w-52 z-50 py-1">
                    <a href="/europe/champions/" class="block px-4 py-2 hover:bg-green-50 hover:text-green-700 text-sm">Champions League EHF</a>
                    <a href="/europe/european-league/" class="block px-4 py-2 hover:bg-green-50 hover:text-green-700 text-sm">EHF European League</a>
                    <a href="/europe/other/" class="block px-4 py-2 hover:bg-green-50 hover:text-green-700 text-sm">Otras EHF</a>
                </div>
            </div>
            <!-- Internacional -->
            <div class="relative group">
                <button class="hover:text-orange-300 py-4">Internacional ▾</button>
                <div class="hidden group-hover:block absolute top-full left-0 bg-white text-gray-800 shadow-xl rounded-lg min-w-52 z-50 py-1 max-h-96 overflow-y-auto">
                    {% for slug, label in intl_sections.items() %}
                    <a href="/{{ slug }}/" class="block px-4 py-2 hover:bg-blue-50 hover:text-blue-700 text-sm">{{ label }}</a>
                    {% endfor %}
                </div>
            </div>
        </div>
    </div>
</nav>

<main class="max-w-7xl mx-auto px-4 py-8 flex-grow">
    {% block content %}{% endblock %}
</main>

<footer class="bg-gray-800 text-gray-400 text-sm text-center py-6 mt-8">
    <p>Actualizado: {{ updated_at }} ·
       <a href="https://github.com/melchor/handbolnoticias" class="underline hover:text-white">GitHub</a>
    </p>
    <p class="mt-1 text-gray-500">HandbolNoticias — Agregador de noticias de balonmano</p>
</footer>

</body>
</html>
```

- [ ] **Step 2: Create `templates/index.html`**

```html
{% extends "base.html" %}
{% block title %}HandbolNoticias — Balonmano en todo el mundo{% endblock %}
{% block content %}

{% for group_key, group in sections.items() %}
{% set group_articles = [] %}
{% for slug in group.subsections.keys() %}
  {% if slug in sections_data and sections_data[slug].articles %}
    {# collect up to 2 articles per subsection for the homepage block #}
    {% for a in sections_data[slug].articles[:2] %}
      {% set _ = group_articles.append((slug, sections_data[slug].label, a)) %}
    {% endfor %}
  {% endif %}
{% endfor %}

{% if group_articles %}
<section class="mb-10">
    <div class="flex items-center justify-between mb-4 border-b-2 border-{{ group.color }}-600 pb-2">
        <h2 class="text-xl font-bold text-{{ group.color }}-700">{{ group.label }}</h2>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {% for slug, label, article in group_articles[:6] %}
        <a href="{{ article.url }}" target="_blank" rel="noopener"
           class="flex gap-3 bg-white rounded-lg shadow-sm hover:shadow-md transition p-3 border border-gray-100">
            {% if article.image_url %}
            <img src="{{ article.image_url }}" alt=""
                 class="w-24 h-16 object-cover rounded flex-shrink-0 bg-gray-100"
                 onerror="this.style.display='none'">
            {% else %}
            <div class="w-24 h-16 flex-shrink-0 bg-gray-100 rounded flex items-center justify-center text-2xl">🤾</div>
            {% endif %}
            <div class="flex-1 min-w-0">
                <span class="text-xs font-semibold text-{{ group.color }}-600 uppercase tracking-wide">{{ label }}</span>
                <p class="font-medium text-sm leading-snug line-clamp-2 mt-0.5">{{ article.title }}</p>
                <p class="text-xs text-gray-400 mt-1">{{ article.source_name }} · {{ article.published[:10] if article.published else "" }}</p>
            </div>
        </a>
        {% endfor %}
    </div>
    <div class="mt-3 flex flex-wrap gap-2">
        {% for slug, label in group.subsections.items() %}
        <a href="/{{ slug }}/" class="text-xs text-{{ group.color }}-600 hover:underline">{{ label }} →</a>
        {% endfor %}
    </div>
</section>
{% endif %}
{% endfor %}

{% endblock %}
```

- [ ] **Step 3: Create `templates/section.html`**

```html
{% extends "base.html" %}
{% block title %}{{ section_label }} — HandbolNoticias{% endblock %}
{% block content %}

<nav class="text-sm text-gray-500 mb-6">
    <a href="/" class="hover:text-hb-blue">Inicio</a>
    <span class="mx-2">›</span>
    <span class="text-gray-800 font-medium">{{ section_label }}</span>
</nav>

<h1 class="text-2xl font-bold mb-6 text-gray-900">{{ section_label }}</h1>

{% if articles %}
<div class="space-y-3">
    {% for article in articles %}
    <a href="{{ article.url }}" target="_blank" rel="noopener"
       class="flex gap-4 bg-white rounded-lg shadow-sm hover:shadow-md transition p-4 border border-gray-100">
        {% if article.image_url %}
        <img src="{{ article.image_url }}" alt=""
             class="w-32 h-20 object-cover rounded flex-shrink-0 bg-gray-100"
             onerror="this.style.display='none'">
        {% else %}
        <div class="w-32 h-20 flex-shrink-0 bg-gray-100 rounded flex items-center justify-center text-3xl">🤾</div>
        {% endif %}
        <div class="flex-1 min-w-0">
            <p class="font-semibold leading-snug line-clamp-2">{{ article.title }}</p>
            {% if article.summary %}
            <p class="text-sm text-gray-500 mt-1 line-clamp-2">{{ article.summary }}</p>
            {% endif %}
            <div class="flex items-center gap-2 mt-2">
                <span class="text-xs font-medium text-gray-600">{{ article.source_name }}</span>
                <span class="text-gray-300">·</span>
                <span class="text-xs text-gray-400">{{ article.published[:10] if article.published else "" }}</span>
                {% if article.is_manual %}
                <span class="text-xs bg-orange-100 text-orange-700 px-1.5 py-0.5 rounded">Manual</span>
                {% endif %}
            </div>
        </div>
    </a>
    {% endfor %}
</div>
{% else %}
<div class="text-center py-16 text-gray-400">
    <div class="text-5xl mb-4">🤾</div>
    <p>No hay noticias recientes en esta sección.</p>
    <p class="text-sm mt-2">Se actualizan diariamente.</p>
</div>
{% endif %}

{% endblock %}
```

- [ ] **Step 4: Commit**

```bash
git add templates/
git commit -m "feat: add Jinja2 HTML templates with Tailwind CSS"
```

---

## Task 8: Renderer

**Files:**
- Create: `scripts/renderer.py`
- Create: `tests/test_renderer.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_renderer.py`:

```python
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_renderer.py -v
```

Expected: `ModuleNotFoundError: No module named 'renderer'`

- [ ] **Step 3: Create `scripts/renderer.py`**

```python
import logging
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
OUTPUT_DIR = Path(__file__).parent.parent / "docs"

SECTIONS = {
    "spain": {
        "label": "España",
        "color": "red",
        "subsections": {
            "spain/asobal": "ASOBAL",
            "spain/dhp": "División Honor Plata",
            "spain/primera-nacional-masc": "Primera Nacional masc.",
            "spain/guerreras": "Liga Guerreras Iberdrola",
            "spain/dho-fem": "División Honor Oro fem.",
            "spain/dhp-fem": "División Honor Plata fem.",
            "spain/catalonia": "Cataluña",
            "spain/navarra": "Navarra",
            "spain/euskadi": "País Vasco",
        },
    },
    "europe": {
        "label": "Europa",
        "color": "green",
        "subsections": {
            "europe/champions": "Champions League EHF",
            "europe/european-league": "EHF European League",
            "europe/other": "Otras EHF",
        },
    },
    "international": {
        "label": "Internacional",
        "color": "blue",
        "subsections": {
            "france": "Francia",
            "germany": "Alemania",
            "denmark": "Dinamarca",
            "sweden": "Suecia",
            "norway": "Noruega",
            "portugal": "Portugal",
            "austria": "Austria",
            "switzerland": "Suiza",
            "iceland": "Islandia",
            "faroe-islands": "Islas Feroe",
            "hungary": "Hungría",
            "poland": "Polonia",
            "croatia": "Croacia",
            "serbia": "Serbia",
            "slovakia": "Eslovaquia",
            "romania": "Rumania",
            "argentina": "Argentina",
            "brazil": "Brasil",
            "japan": "Japón",
        },
    },
}

INTL_SECTIONS = SECTIONS["international"]["subsections"]


def _rows_to_dicts(rows) -> list[dict]:
    return [dict(row) for row in rows]


def _get_section_articles(conn, section_slug: str) -> list[dict]:
    rows = conn.execute("""
        SELECT * FROM articles
        WHERE section = ?
          AND (published > datetime('now', '-30 days') OR published IS NULL)
        ORDER BY published DESC, fetched_at DESC
        LIMIT 100
    """, (section_slug,)).fetchall()
    return _rows_to_dicts(rows)


def render_all(conn):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    updated_at = datetime.now(timezone.utc).strftime("%d/%m/%Y a las %H:%M UTC")

    # Build sections_data for all slugs
    sections_data = {}
    for group in SECTIONS.values():
        for slug, label in group["subsections"].items():
            sections_data[slug] = {
                "label": label,
                "articles": _get_section_articles(conn, slug),
                "color": group["color"],
            }

    # Render homepage
    tmpl = env.get_template("index.html")
    html = tmpl.render(
        sections=SECTIONS,
        sections_data=sections_data,
        intl_sections=INTL_SECTIONS,
        updated_at=updated_at,
    )
    (OUTPUT_DIR / "index.html").write_text(html, encoding="utf-8")
    logger.info("Rendered index.html")

    # Render one page per section slug
    section_tmpl = env.get_template("section.html")
    for slug, data in sections_data.items():
        section_dir = OUTPUT_DIR / slug
        section_dir.mkdir(parents=True, exist_ok=True)
        html = section_tmpl.render(
            section_slug=slug,
            section_label=data["label"],
            articles=data["articles"],
            sections=SECTIONS,
            intl_sections=INTL_SECTIONS,
            updated_at=updated_at,
        )
        (section_dir / "index.html").write_text(html, encoding="utf-8")
    logger.info("Rendered %d section pages", len(sections_data))
```

- [ ] **Step 4: Run all renderer tests**

```bash
python -m pytest tests/test_renderer.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Run the full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/renderer.py tests/test_renderer.py
git commit -m "feat: add HTML renderer generating static pages from SQLite data"
```

---

## Task 9: Pipeline orchestrator

**Files:**
- Create: `scripts/run_all.py`

- [ ] **Step 1: Create `scripts/run_all.py`**

```python
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from db import get_connection, init_db, insert_article
from fetcher import fetch_all, load_sources
from renderer import render_all
from translator import translate_article

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    logger.info("=== HandbolNoticias pipeline iniciado ===")
    init_db()
    conn = get_connection()

    sources = load_sources()
    logger.info("Fuentes cargadas: %d", len(sources))

    articles = fetch_all(sources)
    logger.info("Artículos obtenidos: %d", len(articles))

    new_count = 0
    for article in articles:
        article = translate_article(conn, article)
        if insert_article(conn, article):
            new_count += 1

    logger.info("Artículos nuevos insertados: %d", new_count)

    render_all(conn)
    conn.close()
    logger.info("=== Pipeline completado ===")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the pipeline locally to verify end-to-end**

```bash
cd /home/melchor/science/handbolnoticias
python scripts/run_all.py
```

Expected output (example):
```
2026-05-26 12:00:00 INFO === HandbolNoticias pipeline iniciado ===
2026-05-26 12:00:00 INFO Fuentes cargadas: 14
2026-05-26 12:00:02 INFO Artículos obtenidos: 87
2026-05-26 12:00:05 INFO Artículos nuevos insertados: 87
2026-05-26 12:00:06 INFO Rendered index.html
2026-05-26 12:00:06 INFO Rendered 31 section pages
2026-05-26 12:00:06 INFO === Pipeline completado ===
```

- [ ] **Step 3: Verify the generated site opens correctly**

```bash
python -m http.server 8080 --directory docs/
```

Open `http://localhost:8080` in a browser. Verify:
- Navbar shows España / Europa / Internacional dropdowns
- Homepage shows news blocks by section
- At least one section page (`http://localhost:8080/spain/asobal/`) shows articles
- Footer shows today's date

Stop the server with `Ctrl+C`.

- [ ] **Step 4: Commit**

```bash
git add scripts/run_all.py
git commit -m "feat: add pipeline orchestrator run_all.py"
```

---

## Task 10: GitHub Actions workflow

**Files:**
- Create: `.github/workflows/update.yml`

- [ ] **Step 1: Create `.github/workflows/update.yml`**

```yaml
name: Actualizar noticias

on:
  schedule:
    - cron: '0 1 * * *'   # 01:00 UTC = 02:00–03:00 hora España
  workflow_dispatch:        # permite ejecución manual desde GitHub Actions UI

permissions:
  contents: write

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Configurar Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'

      - name: Instalar dependencias
        run: pip install -r requirements.txt

      - name: Ejecutar pipeline
        run: python scripts/run_all.py

      - name: Commit y push si hay cambios
        run: |
          git config user.name "HandbolNoticias Bot"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add docs/ data/articles.db
          if git diff --staged --quiet; then
            echo "No hay cambios nuevos"
          else
            git commit -m "Actualización diaria $(date -u +%Y-%m-%d)"
            git push
          fi
```

- [ ] **Step 2: Update `.gitignore` to NOT ignore `articles.db` in CI context**

The `.gitignore` ignores `data/articles.db` locally. In GitHub Actions the DB starts fresh each run. This is intentional: the bot commits the updated DB. No change needed — the `git add data/articles.db` in the workflow overrides `.gitignore`.

- [ ] **Step 3: Commit**

```bash
git add .github/
git commit -m "ci: add GitHub Actions workflow for daily news update"
```

---

## Task 11: GitHub Pages setup

**Files:**
- Verify: `docs/.nojekyll` (created in Task 1)

- [ ] **Step 1: Create the GitHub repository**

Go to `https://github.com/new` and create a new public repository named `handbolnoticias`.

- [ ] **Step 2: Push the project**

```bash
git remote add origin https://github.com/melchor/handbolnoticias.git
git branch -M main
git push -u origin main
```

- [ ] **Step 3: Enable GitHub Pages**

1. Go to the repository on GitHub
2. Settings → Pages
3. Source: **Deploy from a branch**
4. Branch: `main`, folder: `/docs`
5. Click Save

- [ ] **Step 4: Trigger a manual workflow run**

1. Go to Actions tab on GitHub
2. Click "Actualizar noticias"
3. Click "Run workflow"
4. Wait for it to complete (~2-3 minutes)

- [ ] **Step 5: Verify the live site**

Open `https://melchor.github.io/handbolnoticias/` in a browser.
Verify the homepage loads with news articles and navigation works.

- [ ] **Step 6: Final commit with any fixes**

```bash
git add .
git status
# only commit if there are actual changes
git commit -m "fix: post-deploy adjustments" || echo "Nothing to commit"
git push
```

---

## Self-Review Notes

**Spec coverage:**
- ✅ GitHub Pages static site
- ✅ RSS + scraping + manual links
- ✅ Daily updates via GitHub Actions
- ✅ SQLite for articles + translation cache
- ✅ España (masc/fem/territorial), Europa (EHF), Internacional (19 países)
- ✅ Translation to Spanish via deep-translator
- ✅ Google News/Feedly style with Tailwind CSS
- ✅ Blue/orange/red/green color scheme
- ✅ Instagram marked as Phase 2 (not in this plan)
- ✅ All known sources in sources.yaml

**Known limitation:** CSS selectors in `sources.yaml` for scraping sources use generic patterns (`article`, `h2`, etc.) that will likely need manual adjustment after visiting each site. Task 6 Step 2 covers verification of RSS feeds; scraping selectors are best tuned iteratively by running the pipeline and checking which sources return 0 articles.
