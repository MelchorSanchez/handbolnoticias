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
