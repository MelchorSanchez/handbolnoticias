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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


_DETAIL_DATE_SELECTORS = [
    "time[datetime]",
    "span.artdate",
    "span.span-date",
    ".itemDateCreated",
    ".entry-date",
]

_DETAIL_DATE_SOURCES = {"BalonmanoInfo", "MiBalonmano", "CatHandbol"}


def _fix_detail_dates(conn):
    """For newly inserted articles without real dates, fetch the detail page."""
    rows = conn.execute("""
        SELECT id, url, source_name FROM articles
        WHERE source_name IN ('BalonmanoInfo','MiBalonmano','CatHandbol','MundoDeportivo-Balonmano')
          AND substr(published, 1, 10) = substr(fetched_at, 1, 10)
          AND fetched_at > datetime('now', '-2 hours')
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
                    dt_attr = el.get("datetime", "").strip()
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

    new_count = 0
    classified_count = 0
    dup_count = 0
    for article in articles:
        original_section = article["section"]
        sections = classify(article)
        if sections:
            if original_section not in sections and original_section in _TERRITORIAL:
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

    logger.info("Artículos reclasificados: %d", classified_count)
    logger.info("Artículos duplicados omitidos: %d", dup_count)
    logger.info("Artículos nuevos insertados: %d", new_count)

    _fix_detail_dates(conn)
    render_all(conn)
    conn.close()
    logger.info("=== Pipeline completado ===")


if __name__ == "__main__":
    main()
