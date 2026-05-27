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
            "spain/asobal":               "ASOBAL",
            "spain/dhp":                  "División Honor Plata",
            "spain/primera-nacional-masc": "Primera Nacional masc.",
            "spain/guerreras":            "Liga Guerreras Iberdrola",
            "spain/dho-fem":              "División Honor Oro fem.",
            "spain/dhp-fem":              "División Honor Plata fem.",
            "spain/seleccion-masc":       "Selección Masculina",
            "spain/seleccion-fem":        "Selección Femenina",
            "spain/base-masc":            "Base Masculino",
            "spain/base-fem":             "Base Femenino",
            "spain/catalonia":            "Cataluña",
            "spain/navarra":              "Navarra",
            "spain/euskadi":              "Euskadi",
        },
    },
    "europe": {
        "label": "Europa EHF",
        "color": "green",
        "subsections": {
            "europe/champions":           "Champions League Masc",
            "europe/champions-women":     "Champions League Fem",
            "europe/european-league":     "European League Masc",
            "europe/european-league-women": "European League Fem",
            "europe/cup-men":             "European Cup Masc",
            "europe/cup-women":           "European Cup Fem",
            "europe/euro-men":            "EHF EURO Masc",
            "europe/euro-women":          "EHF EURO Fem",
            "europe/other":               "Otras EHF",
        },
    },
    "ihf": {
        "label": "IHF",
        "color": "purple",
        "subsections": {
            "ihf/world-men":   "Mundial Masc",
            "ihf/world-women": "Mundial Fem",
        },
    },
    "germany": {
        "label": "Alemania",
        "color": "blue",
        "subsections": {
            "germany/bundesliga":  "Bundesliga",
            "germany/zweite-liga": "2. Bundesliga",
            "germany":             "General",
        },
    },
    "france": {
        "label": "Francia",
        "color": "blue",
        "subsections": {
            "france/starligue": "Starligue",
            "france/pro-d2":    "Pro D2",
            "france":           "General",
        },
    },
    "international": {
        "label": "Internacional",
        "color": "blue",
        "subsections": {
            "denmark":      "Dinamarca",
            "sweden":       "Suecia",
            "norway":       "Noruega",
            "portugal":     "Portugal",
            "austria":      "Austria",
            "switzerland":  "Suiza",
            "iceland":      "Islandia",
            "faroe-islands": "Islas Feroe",
            "hungary":        "Hungría",
            "poland":         "Polonia",
            "croatia":        "Croacia",
            "serbia":         "Serbia",
            "slovakia":       "Eslovaquia",
            "slovenia":       "Eslovenia",
            "romania":        "Rumania",
            "greece":         "Grecia",
            "italy":          "Italia",
            "north-macedonia": "Macedonia del Norte",
            "argentina":      "Argentina",
            "brazil":         "Brasil",
            "japan":          "Japón",
        },
    },
}

# Flat label lookup for all sections
SECTION_LABELS = {}
for _group in SECTIONS.values():
    for _slug, _label in _group["subsections"].items():
        SECTION_LABELS[_slug] = _label

# Structured Internacional dropdown (IHF + Alemania + Francia + rest)
INTL_MENU = [
    {"type": "header", "label": "IHF"},
    {"type": "link",   "slug": "ihf/world-men",   "label": "Mundial Masc"},
    {"type": "link",   "slug": "ihf/world-women",  "label": "Mundial Fem"},
    {"type": "separator"},
    {"type": "header", "label": "Alemania"},
    {"type": "link",   "slug": "germany/bundesliga",  "label": "Bundesliga"},
    {"type": "link",   "slug": "germany/zweite-liga", "label": "2. Bundesliga"},
    {"type": "link",   "slug": "germany",             "label": "General"},
    {"type": "separator"},
    {"type": "header", "label": "Francia"},
    {"type": "link",   "slug": "france/starligue", "label": "Starligue"},
    {"type": "link",   "slug": "france/pro-d2",    "label": "Pro D2"},
    {"type": "link",   "slug": "france",            "label": "General"},
    {"type": "separator"},
    {"type": "header", "label": "Otros países"},
] + [
    {"type": "link", "slug": slug, "label": label}
    for slug, label in SECTIONS["international"]["subsections"].items()
]


def _rows_to_dicts(rows):
    return [dict(row) for row in rows]


def _get_section_articles(conn, section_slug):
    rows = conn.execute("""
        SELECT * FROM articles
        WHERE (section = ?
               OR (extra_sections != '' AND ('|' || extra_sections || '|') LIKE ('%|' || ? || '|%')))
          AND (published > datetime('now', '-30 days') OR published IS NULL)
        ORDER BY COALESCE(published, fetched_at) DESC
        LIMIT 100
    """, (section_slug, section_slug)).fetchall()
    return _rows_to_dicts(rows)


def _get_all_recent_articles(conn):
    rows = conn.execute("""
        SELECT * FROM articles
        WHERE published > datetime('now', '-7 days') OR published IS NULL
        ORDER BY COALESCE(published, fetched_at) DESC
        LIMIT 200
    """).fetchall()
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

    all_articles = _get_all_recent_articles(conn)

    base_ctx = dict(
        sections=SECTIONS,
        intl_menu=INTL_MENU,
        section_labels=SECTION_LABELS,
        updated_at=updated_at,
    )

    tmpl = env.get_template("index.html")
    html = tmpl.render(**base_ctx, sections_data=sections_data)
    (OUTPUT_DIR / "index.html").write_text(html, encoding="utf-8")
    logger.info("Rendered index.html")

    all_tmpl = env.get_template("all_news.html")
    html = all_tmpl.render(**base_ctx, articles=all_articles)
    all_dir = OUTPUT_DIR / "all"
    all_dir.mkdir(parents=True, exist_ok=True)
    (all_dir / "index.html").write_text(html, encoding="utf-8")
    logger.info("Rendered all_news.html")

    section_tmpl = env.get_template("section.html")
    for slug, data in sections_data.items():
        section_dir = OUTPUT_DIR / slug
        section_dir.mkdir(parents=True, exist_ok=True)
        html = section_tmpl.render(
            **base_ctx,
            section_slug=slug,
            section_label=data["label"],
            articles=data["articles"],
        )
        (section_dir / "index.html").write_text(html, encoding="utf-8")
    logger.info("Rendered %d section pages", len(sections_data))
