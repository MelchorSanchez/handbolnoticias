import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import httpx
from bs4 import BeautifulSoup

from classifier import classify
from db import get_connection, init_db, insert_article, is_title_duplicate, article_exists
from fetcher import fetch_all, load_sources, _parse_date_text, _now, HEADERS, TIMEOUT
from renderer import render_all
from translator import translate_article
from podcasts import main as render_podcasts

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


_BLACKLIST_PATH = Path(__file__).resolve().parent.parent / "config" / "url_blacklist.txt"

# URL fragments that signal commercial/non-editorial content — filtered for ALL sources
_COMMERCIAL_URL_FRAGMENTS = (
    "/abono", "/abonos", "/abonnement", "/campagne-abonnement",
    "/billetterie", "/dauerkarte", "/fanshop", "/fan-shop",
    "/merchandise", "/tienda-oficial", "/shop/",
    "/sponsor", "/patrocin",
    "/ticketverkauf", "/einzelticket", "/tickets/", "/ticket-",
    "/entradas/", "/venta-entradas", "/compra-entradas",
    "/billetes/", "/taquilla",
    "/campus/", "/campus-balonmano", "/campus-handball",
    "/summer-camp", "/verano-handball",
)

# Title keywords that signal commercial/promotional content — filtered for CLUB sources only
_CLUB_COMMERCIAL_TITLE_KWS = (
    "abono", "abonado", "abonados", "hazte abonado", "renueva tu abono",
    "campaña de abonos", "campagne abonnement", "dauerkarte",
    "patrocinador", "patrocina ", "nuevo patrocinador", "acuerdo de patrocinio",
    "sponsor oficial", "esponsor", "naming rights",
    "abonnement", "abonnements",
    "venta de entradas", "compra tus entradas", "entradas ya disponibles",
    "ticketverkauf", "einzelticket", "tickets available", "buy tickets",
    "billetterie ouverte", "billetes disponibles",
    "campus de balonmano", "campus de handball", "campus de verano",
    "campus handball", "summer camp", "handball camp",
    "clinic de balonmano", "clínica de balonmano",
    "jornada de puertas abiertas", "puertas abiertas",
    "fiesta fin de temporada", "cena de gala", "gala de",
    "inscripcion al campus", "inscripción al campus",
)

# URL fragments that signal routine weekend result roundups — filtered for CLUB sources only
# Keep narrow: only clearly routine report patterns, NOT general youth/base content
_CLUB_BASE_URL_FRAGMENTS = (
    "/akademie-rueckblick", "/akademie-ruckblick",
    "/wochenrueckblick", "/wochenruckblick",
    "/nachwuchs-wochenende",
)

# Title keywords that signal routine weekend result roundups — filtered for CLUB sources only
_CLUB_BASE_TITLE_KWS = (
    "rueckblick zum wochenende", "rückblick zum wochenende",
    "nachwuchs-wochenende", "wochenendbericht nachwuchs",
)


def _should_skip_article(article: dict) -> bool:
    """Return True if the article should be dropped before inserting."""
    url = article.get("url", "").lower()
    title = (article.get("title_orig") or article.get("title") or "").lower()
    is_club = article.get("source_name", "").lower().endswith("-web")

    # Global: commercial URL patterns
    if any(frag in url for frag in _COMMERCIAL_URL_FRAGMENTS):
        return True

    # Club sources: commercial title keywords
    if is_club and any(kw in title for kw in _CLUB_COMMERCIAL_TITLE_KWS):
        return True

    # Club sources: base/youth routine report URL patterns
    if is_club and any(frag in url for frag in _CLUB_BASE_URL_FRAGMENTS):
        return True

    # Club sources: base/youth routine report title keywords
    if is_club and any(kw in title for kw in _CLUB_BASE_TITLE_KWS):
        return True

    return False


def _load_blacklist() -> set:
    if not _BLACKLIST_PATH.exists():
        return set()
    urls = set()
    for line in _BLACKLIST_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.add(line.rstrip("/"))
    return urls


_DETAIL_DATE_SELECTORS = [
    "time[datetime]",
    "meta[property='article:published_time']",
    "span.artdate",
    "span.span-date",
    ".itemDateCreated",
    ".entry-date",
    ".lte-post-date",
]

_DETAIL_DATE_SOURCES = {"BalonmanoInfo", "MiBalonmano", "CatHandbol", "Porrino-web", "PallamanoItalia", "HCEivissa-web"}


def _fix_detail_dates(conn):
    """For newly inserted articles without real dates, fetch the detail page."""
    rows = conn.execute("""
        SELECT id, url, source_name FROM articles
        WHERE source_name IN ('BalonmanoInfo','MiBalonmano','CatHandbol','MundoDeportivo-Balonmano','HCEivissa-web','CeskaTelevize-Hazena','PlzenskyDenik-Hazena','MBL-Handbolti','NTVSpor-Hentbol','AjansSpor-Hentbol')
          AND substr(published, 1, 10) = substr(fetched_at, 1, 10)
          AND fetched_at > datetime('now', '-48 hours')
    """).fetchall()
    if not rows:
        return
    logger.info("Fixing dates for %d recently inserted articles via detail pages", len(rows))
    now_date = _now()[:10]
    fixed = 0
    for row in rows:
        try:
            resp = httpx.get(row["url"], headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            for sel in _DETAIL_DATE_SELECTORS:
                el = soup.select_one(sel)
                if el:
                    dt_attr = (el.get("datetime") or el.get("content") or "").strip()
                    text = dt_attr if dt_attr else el.get_text().strip()
                    if text:
                        real_date = _parse_date_text(text)
                        if real_date[:10] != now_date:
                            conn.execute("UPDATE articles SET published=? WHERE id=?",
                                         (real_date, row["id"]))
                            conn.commit()
                            fixed += 1
                            break
        except Exception as exc:
            logger.debug("Detail date fetch failed %s: %s", row["url"], exc)
        time.sleep(0.2)
    logger.info("Detail date fix: corrected %d/%d articles", fixed, len(rows))


def main():
    logger.info("=== HandbolNoticias pipeline iniciado ===")
    init_db()
    conn = get_connection()

    sources = load_sources()
    logger.info("Fuentes cargadas: %d", len(sources))

    articles = fetch_all(sources)
    logger.info("Artículos obtenidos: %d", len(articles))

    # Territorial sections are always kept as extra even when article is reclassified
    _TERRITORIAL = {"spain/catalonia", "spain/navarra", "spain/euskadi"}
    # IHF source defaults are preserved as extra when classifier finds a more specific section
    _IHF_PRESERVE = {"ihf/other", "ihf/world-men", "ihf/world-women"}

    blacklist = _load_blacklist()

    new_count = 0
    classified_count = 0
    dup_count = 0
    skipped_commercial = 0
    for article in articles:
        if article.get("url", "").rstrip("/") in blacklist:
            continue
        if _should_skip_article(article):
            skipped_commercial += 1
            continue
        original_section = article["section"]
        sections = classify(article)
        if sections:
            if original_section not in sections and original_section in _TERRITORIAL:
                sections.append(original_section)
            if original_section not in sections and original_section in _IHF_PRESERVE:
                sections.append(original_section)
            primary = sections[0]
            extras = "|".join(sections[1:])
            if primary != original_section:
                classified_count += 1
            article["section"] = primary
            article["extra_sections"] = extras
        else:
            article["extra_sections"] = ""

        article.pop("_raw_tags", None)

        # Skip title-dup check for already-known articles (let the UPDATE run normally)
        if not article_exists(conn, article["id"]):
            orig_title = article.get("title_orig") or article.get("title", "")
            if is_title_duplicate(conn, orig_title):
                dup_count += 1
                continue

        article = translate_article(conn, article)
        if insert_article(conn, article):
            new_count += 1

    logger.info("Artículos comerciales/base omitidos: %d", skipped_commercial)
    logger.info("Artículos reclasificados: %d", classified_count)
    logger.info("Artículos duplicados omitidos: %d", dup_count)
    logger.info("Artículos nuevos insertados: %d", new_count)

    _fix_detail_dates(conn)
    render_all(conn)
    conn.close()
    render_podcasts()
    logger.info("=== Pipeline completado ===")


if __name__ == "__main__":
    main()
