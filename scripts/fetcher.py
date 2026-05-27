import hashlib
import itertools
import logging
import os
import re
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
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; HandbolNoticias/1.0; +https://github.com/handbolnoticias)"}
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
_ALL_MONTHS = {**_CATALAN_MONTHS, **_SPANISH_MONTHS}


def _parse_date_text(text: str) -> str:
    """Parse human-readable date (Catalan/Spanish) from scraped text, return ISO string."""
    clean = text.strip().lower()
    m = re.search(r'(\d{1,2})\s+(?:de\s+)?(\w+)\s+(?:de\s+)?(\d{4})', clean)
    if m:
        day, month_name, year = int(m.group(1)), m.group(2), int(m.group(3))
        month = _ALL_MONTHS.get(month_name)
        if month:
            try:
                return datetime(year, month, day, 12, 0, 0, tzinfo=timezone.utc).isoformat()
            except ValueError:
                pass
    m2 = re.search(r'(\d{4})-(\d{2})-(\d{2})', clean)
    if m2:
        return f"{m2.group(1)}-{m2.group(2)}-{m2.group(3)}T12:00:00+00:00"
    return _now()

# Instagram: reject pure countdown/promo posts, keep results/news/transfers
_IG_REJECT = re.compile(
    r'\b(mañana\s+(partido|jugamos|nos\s+vemos)|este\s+(sábado|domingo|lunes|martes'
    r'|miércoles|jueves|viernes|finde)|partido\s+(el|este)\s+(sábado|domingo|lunes'
    r'|martes|miércoles|jueves|viernes|próximo|de\s+mañana)|os\s+esperamos\s+el'
    r'|nos\s+vemos\s+el|entradas\s+a\s+la\s+venta|compra\s+tu\s+entrada'
    r'|horario\s+de\s+(la\s+)?jornada|próxima\s+jornada|jornada\s+\d+\s+de\s+la\s+temporada)\b',
    re.IGNORECASE,
)
_IG_ACCEPT = re.compile(
    r'(\b\d{1,2}[-–]\d{1,2}\b'  # score like 29-27
    r'|\bfich[oaóa]?\b|\bfirm[oaóa]?\b|\brenuev[oa]\b|\bcontrato\b'
    r'|\bvictoria\b|\bderrota\b|\bempate\b|\bcampe[oó]n\b|\bcampeonas?\b'
    r'|\bascenso\b|\bdescenso\b|\bpromoci[oó]n\b|\bfinal\s+four\b'
    r'|\bnuevo\s+(jugador|entrenador|técnico)\b|\bnueva\s+(jugadora|entrenadora)\b'
    r'|\bsuma\s+\d+\s+puntos\b|\bclasificaci[oó]n\b)',
    re.IGNORECASE,
)

_IG_NOT_INITIALIZED = object()
_ig_loader = _IG_NOT_INITIALIZED  # sentinel: one login attempt per pipeline run


def _instagram_is_news(caption: str) -> bool:
    """Return True if an Instagram caption looks like real news vs. a promo/countdown post."""
    if not caption or len(caption.strip()) < 30:
        return False
    if _IG_ACCEPT.search(caption):
        return True
    if _IG_REJECT.search(caption):
        return False
    return True


def _get_instagram_loader():
    """
    Return an authenticated instaloader instance, or None if credentials absent.
    Sessions are cached in data/instagram_sessions/ to avoid re-login each run.
    Set INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD env vars (or GitHub Secrets).
    """
    try:
        import instaloader
        username = os.environ.get("INSTAGRAM_USERNAME", "").strip()
        password = os.environ.get("INSTAGRAM_PASSWORD", "").strip()
        if not username or not password:
            logger.info("Instagram: INSTAGRAM_USERNAME/PASSWORD not set, skipping Instagram sources")
            return None

        session_dir = DATA_DIR / "instagram_sessions"
        session_dir.mkdir(parents=True, exist_ok=True)
        session_file = session_dir / f"session-{username}"

        L = instaloader.Instaloader(
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            quiet=True,
        )

        if session_file.exists():
            try:
                L.load_session_from_file(username, str(session_file))
                logger.info("Instagram: loaded cached session for @%s", username)
                return L
            except Exception as e:
                logger.warning("Instagram: cached session invalid (%s), re-logging in", e)

        L.login(username, password)
        L.save_session_to_file(str(session_file))
        logger.info("Instagram: logged in as @%s, session saved", username)
        return L
    except Exception as exc:
        logger.error("Instagram login failed: %s", exc)
        return None


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
            title = _clean_cdata(entry.get("title", "").strip())
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
                "published": _rss_date(entry),
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
            title_text = _clean_cdata(title_el.get_text().strip())
            if not _passes_filter(source, title_text, ""):
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
                published = _now()
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
        return articles
    except Exception as exc:
        logger.error("Scrape error %s: %s", source["name"], exc)
        return []


def fetch_instagram(source: dict) -> list:
    """Fetch recent posts from a public Instagram account using instaloader."""
    global _ig_loader
    if _ig_loader is _IG_NOT_INITIALIZED:
        _ig_loader = _get_instagram_loader()
    if _ig_loader is None:
        return []

    account = source["account"]
    try:
        import instaloader
        profile = instaloader.Profile.from_username(_ig_loader.context, account)
        articles = []
        for post in itertools.islice(profile.get_posts(), source.get("max_items", 5)):
            caption = post.caption or ""
            if not _instagram_is_news(caption):
                logger.debug("Instagram skip (promo) @%s: %s", account, caption[:60])
                continue
            url = f"https://www.instagram.com/p/{post.shortcode}/"
            first_line = caption.split("\n")[0].strip()[:200]
            articles.append({
                "id": _article_id(url),
                "url": url,
                "title": first_line or url,
                "title_orig": first_line or url,
                "summary": caption[:500],
                "image_url": post.url,
                "source_name": f"@{account}",
                "section": source["section"],
                "published": post.date_utc.isoformat(),
                "fetched_at": _now(),
                "is_manual": 0,
            })
        return articles
    except Exception as exc:
        logger.error("Instagram error @%s: %s", account, exc)
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
        elif source["type"] == "instagram":
            articles.extend(fetch_instagram(source))
    articles.extend(fetch_manual_links())
    return articles
