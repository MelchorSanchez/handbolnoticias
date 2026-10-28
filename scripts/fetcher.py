import hashlib
import logging
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import feedparser
import httpx
import yaml
from bs4 import BeautifulSoup
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).parent.parent / "config"
DATA_DIR = Path(__file__).parent.parent / "data"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"}
TIMEOUT = 10.0

_CATALAN_MONTHS = {
    'gener': 1, 'febrer': 2, 'març': 3, 'abril': 4,
    'maig': 5, 'juny': 6, 'juliol': 7, 'agost': 8,
    'setembre': 9, 'octubre': 10, 'novembre': 11, 'desembre': 12,
}
_SPANISH_MONTHS = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
    'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
    'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12,
}
_ENGLISH_MONTHS = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
}
_ITALIAN_MONTHS = {
    'gennaio': 1, 'febbraio': 2, 'marzo': 3, 'aprile': 4,
    'maggio': 5, 'giugno': 6, 'luglio': 7, 'agosto': 8,
    'settembre': 9, 'ottobre': 10, 'novembre': 11, 'dicembre': 12,
}
_ALL_MONTHS = {**_CATALAN_MONTHS, **_SPANISH_MONTHS, **_ENGLISH_MONTHS, **_ITALIAN_MONTHS}


def _parse_date_text(text: str) -> str:
    """Parse human-readable date (Catalan/Spanish/Joomla) from scraped text, return ISO string."""
    clean = text.strip().lower()
    # ISO: 2025-12-30 or 2025-12-30T...
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', clean)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}T12:00:00+00:00"
    # D/M/YYYY or D/M/YYYY, H:MM:SS (Sport.es format)
    m = re.search(r'^(\d{1,2})/(\d{1,2})/(\d{4})', clean)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), 12, 0, 0, tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    # DD.MM.YYYY (e.g. "30.12.2025")
    m = re.search(r'(\d{1,2})\.(\d{1,2})\.(\d{4})', clean)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), 12, 0, 0, tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    # DD-MM-YYYY (e.g. "30-12-2025")
    m = re.search(r'(\d{1,2})-(\d{1,2})-(\d{4})', clean)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), 12, 0, 0, tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    # DD month YYYY (e.g. "30 desembre 2025" / "30 de diciembre de 2025")
    m = re.search(r'(\d{1,2})\s+(?:de\s+)?(\w+)\s+(?:de\s+)?(\d{4})', clean)
    if m:
        day, month_name, year = int(m.group(1)), m.group(2), int(m.group(3))
        month = _ALL_MONTHS.get(month_name)
        if month:
            try:
                return datetime(year, month, day, 12, 0, 0, tzinfo=timezone.utc).isoformat()
            except ValueError:
                pass
    # month DD, YYYY (Joomla: "desembre 30, 2025")
    m = re.search(r'(\w+)\s+(\d{1,2}),?\s+(\d{4})', clean)
    if m:
        month_name, day, year = m.group(1), int(m.group(2)), int(m.group(3))
        month = _ALL_MONTHS.get(month_name)
        if month:
            try:
                return datetime(year, month, day, 12, 0, 0, tzinfo=timezone.utc).isoformat()
            except ValueError:
                pass
    return _now()

def load_sources() -> list:
    with open(CONFIG_DIR / "sources.yaml") as f:
        return yaml.safe_load(f)["sources"]


def _article_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rss_date(entry) -> str:
    """Return ISO 8601 UTC date from a feedparser entry. Falls back to now."""
    parsed = getattr(entry, "published_parsed", None)
    if parsed:
        try:
            return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat()
        except (ValueError, TypeError):
            pass
    return _now()


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


def _clean_cdata(text: str) -> str:
    """Strip <![CDATA[...]]> wrappers that some feeds leave unprocessed."""
    return re.sub(r"<!\[CDATA\[(.*?)]]>", r"\1", text, flags=re.DOTALL).strip()


def _passes_filter(source: dict, title: str, summary: str, url: str = "") -> bool:
    """Return False to skip articles that don't pass source-level filters."""
    min_len = source.get("min_title_length", 0)
    if min_len and len(title) < min_len:
        return False
    exclude_url = source.get("exclude_url_patterns", [])
    if exclude_url and any(p.lower() in url.lower() for p in exclude_url):
        return False
    include_url = source.get("include_url_patterns", [])
    if include_url and not any(p.lower() in url.lower() for p in include_url):
        return False
    # filter_title_only: only check the title, not the RSS description/summary.
    # Use for general-press sources whose RSS descriptions include boilerplate handball
    # mentions in sidebars/footers, which would otherwise pass non-handball articles.
    if source.get("filter_title_only"):
        text = title.lower()
    else:
        text = (title + " " + summary).lower()
    exclude = source.get("exclude_keywords", [])
    if exclude and any(kw.lower() in text for kw in exclude):
        return False
    keywords = source.get("filter_keywords", [])    # Level 1: sport terms, sufficient alone
    team_keywords = source.get("team_keywords", [])  # Level 2: only pass with a Level 1 match
    if not keywords and not team_keywords:
        return True
    has_sport = bool(keywords) and any(kw.lower() in text for kw in keywords)
    if has_sport:
        return True
    if not team_keywords:
        return False
    # team keywords only pass when also a sport term is found
    has_team = any(kw.lower() in text for kw in team_keywords)
    return has_sport and has_team


RSS_TIMEOUT = 30.0
_FEEDPARSER_HEADERS = {"User-Agent": feedparser.USER_AGENT}


def _download_feed(url: str) -> bytes:
    """Download a feed with a timeout: feedparser.parse(url) has none, and a feed
    server that accepted the connection but never answered hung the whole Action
    until its 70-minute limit (2026-10-28). The browser User-Agent gets past the
    WAF of several Prensa Ibérica / Vocento feeds that reject feedparser's, while
    a few sites (teamesbjerg.dk) only accept feedparser's, so fall back to it."""
    resp = httpx.get(url, headers=HEADERS, timeout=RSS_TIMEOUT, follow_redirects=True)
    if resp.is_error:
        resp = httpx.get(url, headers=_FEEDPARSER_HEADERS, timeout=RSS_TIMEOUT, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


def _fetch_rss(source: dict) -> tuple:
    feed = feedparser.parse(_download_feed(source["url"]))
    articles = []
    for entry in feed.entries[: source.get("max_items", 50)]:
        url = entry.get("link", "")
        if not url:
            continue
        summary_html = entry.get("summary", "") or ""
        summary_text = BeautifulSoup(summary_html, "lxml").get_text()[:500]
        title = _clean_cdata(entry.get("title", "").strip())
        if not _passes_filter(source, title, summary_text, url):
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
            "published": _rss_date(entry),
            "fetched_at": _now(),
            "is_manual": 0,
            "_raw_tags": raw_tags,
        })
    return len(feed.entries), articles


def _date_from_url(url: str):
    """Extract publication date embedded in news article URLs.
    Handles /YYYY/MM/DD/ (Marca, FNavarraBM) and /YYYYMMDD/ (MundoDeportivo) patterns.
    Returns ISO string or None."""
    # /2026/05/24/ style
    m = re.search(r'/(\d{4})/(\d{2})/(\d{2})/', url)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                            12, 0, 0, tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    # /20260524/ style (8-digit date block between slashes)
    m = re.search(r'/(\d{4})(\d{2})(\d{2})/', url)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                            12, 0, 0, tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    return None


def _fetch_scrape(source: dict) -> tuple:
    resp = httpx.get(source["url"], headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    sel = source["selectors"]
    base = urlparse(source["url"])
    articles = []
    items = soup.select(sel["articles"])
    for item in items[: source.get("max_items", 30)]:
        title_el = item.select_one(sel["title"])
        link_el = item.select_one(sel["link"])
        if not title_el or not link_el:
            continue
        href = link_el.get("href", "")
        if href.startswith("/"):
            href = f"{base.scheme}://{base.netloc}{href}"
        if not href:
            continue
        title_text = _clean_cdata(title_el.get_text().strip())
        if not _passes_filter(source, title_text, "", href):
            continue
        img_el = item.select_one(sel.get("image", "img"))
        image_url = img_el.get("src") if img_el else None
        if image_url and image_url.startswith("/"):
            image_url = f"{base.scheme}://{base.netloc}{image_url}"
        date_sel = sel.get("date", "")
        date_el = item.select_one(date_sel) if date_sel else None
        if date_el:
            dt_attr = date_el.get("datetime", "").strip()
            published = _parse_date_text(dt_attr) if dt_attr else _parse_date_text(date_el.get_text())
        else:
            published = _date_from_url(href) or _now()
        articles.append({
            "id": _article_id(href),
            "url": href,
            "title": title_text,
            "title_orig": title_text,
            "summary": "",
            "image_url": image_url,
            "source_name": source["name"],
            "section": source["section"],
            "published": published,
            "fetched_at": _now(),
            "is_manual": 0,
        })
    return len(items), articles


def _find_nextjs_articles(obj, results=None):
    """Recursively find all Article_Out objects in __NEXT_DATA__ JSON."""
    if results is None:
        results = []
    if isinstance(obj, dict):
        if obj.get("__typename") == "Article_Out" and "slug" in obj and "title" in obj:
            results.append(obj)
        else:
            for v in obj.values():
                _find_nextjs_articles(v, results)
    elif isinstance(obj, list):
        for item in obj:
            _find_nextjs_articles(item, results)
    return results


def _fetch_nextjs(source: dict) -> tuple:
    """Fetch articles from a Next.js page by extracting __NEXT_DATA__ JSON."""
    resp = httpx.get(source["url"], headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script:
        logger.warning("No __NEXT_DATA__ found for %s", source["name"])
        return 0, []
    import json as _json
    data = _json.loads(script.string)
    raw_articles = _find_nextjs_articles(data)
    seen_ids = set()
    articles = []
    base = urlparse(source["url"])
    base_url = f"{base.scheme}://{base.netloc}"
    for item in raw_articles:
        art_id = item.get("id")
        slug = item.get("slug", "")
        if not art_id or not slug or art_id in seen_ids:
            continue
        seen_ids.add(art_id)
        section_path = (item.get("mainSection") or {}).get("path", "")
        url = f"{base_url}/clanek/{section_path}/{slug}-{art_id}" if section_path else f"{base_url}/clanek/{slug}-{art_id}"
        title_obj = item.get("title", {})
        title_text = (title_obj.get("main") if isinstance(title_obj, dict) else title_obj) or ""
        if not _passes_filter(source, title_text, "", url):
            continue
        pub = item.get("publication") or {}
        ts = pub.get("firstPublished") or pub.get("datePublished") or item.get("dateUpdated")
        if ts:
            published = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        else:
            published = _now()
        preview_image = item.get("previewImage") or {}
        image_url = preview_image.get("src") if isinstance(preview_image, dict) else None
        perex_raw = item.get("perex") or ""
        perex = perex_raw.get("text", "") if isinstance(perex_raw, dict) else (perex_raw or "")
        articles.append({
            "id": _article_id(url),
            "url": url,
            "title": title_text,
            "title_orig": title_text,
            "summary": perex[:500],
            "image_url": image_url,
            "source_name": source["name"],
            "section": source["section"],
            "published": published,
            "fetched_at": _now(),
            "is_manual": 0,
        })
        if len(articles) >= source.get("max_items", 15):
            break
    return len(raw_articles), articles


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


_FETCHERS = {"rss": (_fetch_rss, "RSS"), "scrape": (_fetch_scrape, "Scrape"),
             "nextjs": (_fetch_nextjs, "Next.js scrape")}


def fetch_source(source: dict, kind: str = None) -> tuple:
    """Fetch one source. Returns (articles, stats); never raises. stats records
    how many entries the feed/page had (`raw`), how many passed the source filter
    (`passed`), the error if any and the time taken, for the source health report."""
    fetch, label = _FETCHERS[kind or source["type"]]
    start = time.monotonic()
    raw, articles, error = 0, [], ""
    try:
        raw, articles = fetch(source)
    except Exception as exc:
        logger.error("%s error %s: %s", label, source["name"], exc)
        error = f"{type(exc).__name__}: {exc}"[:300]
    stats = {"name": source["name"], "raw": raw, "passed": len(articles),
             "error": error, "seconds": round(time.monotonic() - start, 1)}
    return articles, stats


def fetch_rss(source: dict) -> list:
    return fetch_source(source, "rss")[0]


def fetch_scrape(source: dict) -> list:
    return fetch_source(source, "scrape")[0]


def fetch_nextjs(source: dict) -> list:
    return fetch_source(source, "nextjs")[0]


def fetch_all(sources: list, health: list = None) -> list:
    """Fetch every source. If `health` is given, one stats dict per source is
    appended to it (see fetch_source)."""
    articles = []
    for source in sources:
        if source["type"] not in _FETCHERS:
            continue
        found, stats = fetch_source(source)
        articles.extend(found)
        if health is not None:
            health.append(stats)
    articles.extend(fetch_manual_links())
    return articles
