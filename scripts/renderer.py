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


def _rows_to_dicts(rows):
    return [dict(row) for row in rows]


def _get_section_articles(conn, section_slug):
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

    sections_data = {}
    for group in SECTIONS.values():
        for slug, label in group["subsections"].items():
            sections_data[slug] = {
                "label": label,
                "articles": _get_section_articles(conn, slug),
                "color": group["color"],
            }

    tmpl = env.get_template("index.html")
    html = tmpl.render(
        sections=SECTIONS,
        sections_data=sections_data,
        intl_sections=INTL_SECTIONS,
        updated_at=updated_at,
    )
    (OUTPUT_DIR / "index.html").write_text(html, encoding="utf-8")
    logger.info("Rendered index.html")

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
