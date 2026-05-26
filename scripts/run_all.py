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
