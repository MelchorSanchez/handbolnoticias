import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from classifier import classify
from db import get_connection, init_db, insert_article, is_title_duplicate, article_exists
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

    render_all(conn)
    conn.close()
    logger.info("=== Pipeline completado ===")


if __name__ == "__main__":
    main()
