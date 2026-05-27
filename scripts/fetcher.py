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


def extract_image(entry) -> str:
    if hasattr(entry, "enclosures") and entry.enclosures:
        for enc in entry.enclosures:
            if enc.get("type", "").startswith("image"):
                return enc.get("href")
    if hasattr(entry, "media_content") and entry.media_content:
        return entry.media_content[0].get("url")
    summary = getattr(entry, "summary", "") or ""
    if summary and isinstance(summary, str):
        soup = BeautifulSoup(summary, "lxml")
        img = soup.find("img")
        if img and img.get("src"):
            return img["src"]
    return None


def _passes_filter(source: dict, title: str, summary: str) -> bool:
    """If source defines filter_keywords, skip articles that don't mention any of them."""
    keywords = source.get("filter_keywords", [])
    if not keywords:
        return True
    text = (title + " " + summary).lower()
    return any(kw.lower() in text for kw in keywords)


def fetch_rss(source: dict) -> list:
    try:
        feed = feedparser.parse(source["url"])
        articles = []
        for entry in feed.entries[: source.get("max_items", 50)]:
            url = entry.get("link", "")
            if not url:
                continue
            summary_html = entry.get("summary", "") or ""
            summary_text = BeautifulSoup(summary_html, "lxml").get_text()[:500]
            title = entry.get("title", "").strip()
            if not _passes_filter(source, title, summary_text):
                continue
            raw_tags = [t.get("term", "") for t in getattr(entry, "tags", []) if t.get("term")]
            articles.append({
                "id": _article_id(url),
                "url": url,
                "title": title,
                "title_orig": title,
                "summary": summary_text,
                "image_url": extract_image(entry),
                "source_name": source["name"],
                "section": source["section"],
                "published": entry.get("published", _now()),
                "fetched_at": _now(),
                "is_manual": 0,
                "_raw_tags": raw_tags,
            })
        return articles
    except Exception as exc:
        logger.error("RSS error %s: %s", source["name"], exc)
        return []


def fetch_scrape(source: dict) -> list:
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
            title_text = title_el.get_text().strip()
            if not _passes_filter(source, title_text, ""):
                continue
            img_el = item.select_one(sel.get("image", "img"))
            image_url = img_el.get("src") if img_el else None
            if image_url and image_url.startswith("/"):
                image_url = f"{base.scheme}://{base.netloc}{image_url}"
            articles.append({
                "id": _article_id(href),
                "url": href,
                "title": title_text,
                "title_orig": title_text,
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


def fetch_manual_links() -> list:
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


def fetch_all(sources: list) -> list:
    articles = []
    for source in sources:
        if source["type"] == "rss":
            articles.extend(fetch_rss(source))
        elif source["type"] == "scrape":
            articles.extend(fetch_scrape(source))
    articles.extend(fetch_manual_links())
    return articles
