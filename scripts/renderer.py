import logging
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
OUTPUT_DIR = Path(__file__).parent.parent / "docs"
BASE_URL = "https://handbolnoticias.pages.dev"

SECTION_DESCRIPTIONS = {
    "spain/asobal":               "Noticias de la Liga ASOBAL de balonmano masculino: resultados, clasificación, fichajes y todo sobre la máxima competición española.",
    "spain/dhp":                  "Noticias de la División de Honor Plata masculina de balonmano en España: resultados, ascensos y equipos.",
    "spain/primera-nacional-masc":"Noticias de la Primera Nacional masculina de balonmano: equipos, resultados y clasificación.",
    "spain/guerreras":            "Noticias de la Liga Guerreras Iberdrola de balonmano femenino: resultados, clasificación, fichajes y más.",
    "spain/dho-fem":              "Noticias de la División de Honor Oro femenina de balonmano en España: resultados y equipos.",
    "spain/dhp-fem":              "Noticias de la División de Honor Plata femenina de balonmano en España: resultados y equipos.",
    "spain/seleccion-masc":       "Noticias de la Selección Española Masculina de balonmano: convocatorias, partidos y torneos internacionales.",
    "spain/seleccion-fem":        "Noticias de la Selección Española Femenina de balonmano: convocatorias, partidos y torneos internacionales.",
    "spain/base-masc":            "Noticias del balonmano base masculino en España: selecciones juveniles, categorías inferiores y formación.",
    "spain/base-fem":             "Noticias del balonmano base femenino en España: selecciones juveniles, categorías inferiores y formación.",
    "spain/catalonia":            "Noticias de balonmano en Cataluña: handbol català, competicions autonòmiques i clubs.",
    "spain/navarra":              "Noticias de balonmano en Navarra: clubs, competiciones y jugadores navarros.",
    "spain/euskadi":              "Noticias de balonmano en Euskadi: clubs vascos, competiciones y jugadores.",
    "europe/champions":           "Noticias de la EHF Champions League masculina: resultados, grupos, Final4 y los mejores clubs europeos de balonmano.",
    "europe/champions-women":     "Noticias de la EHF Champions League femenina: resultados, grupos, Final4 y los mejores clubs europeos de balonmano.",
    "europe/european-league":     "Noticias de la EHF European League masculina de balonmano: resultados y equipos.",
    "europe/european-league-women":"Noticias de la EHF European League femenina de balonmano: resultados y equipos.",
    "europe/cup-men":             "Noticias de la EHF European Cup masculina de balonmano.",
    "europe/cup-women":           "Noticias de la EHF European Cup femenina de balonmano.",
    "europe/euro-men":            "Noticias del EHF EURO masculino de balonmano: selecciones, resultados y clasificación.",
    "europe/euro-women":          "Noticias del EHF EURO femenino de balonmano: selecciones, resultados y clasificación.",
    "europe/other":               "Otras noticias y competiciones EHF de balonmano europeo.",
    "ihf/world-men":              "Noticias del Campeonato del Mundo masculino de balonmano IHF: selecciones, resultados y clasificación.",
    "ihf/world-women":            "Noticias del Campeonato del Mundo femenino de balonmano IHF: selecciones, resultados y clasificación.",
    "germany/bundesliga":         "Noticias de la Daikin HBL (Handball-Bundesliga) masculina: resultados, fichajes y todos los clubs alemanes.",
    "germany/bundesliga2":        "Noticias de la 2. Bundesliga masculina de balonmano alemán: resultados y clasificación.",
    "germany/bundesliga-fem":     "Noticias de la Alsco HBF (Handball-Bundesliga Frauen): resultados, fichajes y clubs del balonmano femenino alemán.",
    "germany/bundesliga2-fem":    "Noticias de la 2. Bundesliga femenina de balonmano alemán: resultados y clasificación.",
    "germany":                    "Noticias generales de balonmano en Alemania: DHB, selección y handball alemán.",
    "france/starligue":           "Noticias de la Liqui Moly Starligue masculina de balonmano francés: resultados y equipos.",
    "france/pro-d2":              "Noticias de la ProLigue masculina de balonmano francés: resultados y clasificación.",
    "france/d1f":                 "Noticias de la Ligue Butagaz Énergie (D1F) femenina de balonmano francés: resultados y equipos.",
    "france/d2f":                 "Noticias de la D2F femenina de balonmano francés.",
    "france":                     "Noticias generales de balonmano en Francia: selección y handball francés.",
    "denmark":                    "Noticias de balonmano en Dinamarca: Håndboldligaen, selección danesa y clubs.",
    "sweden":                     "Noticias de balonmano en Suecia: Handbollsligan, selección sueca y clubs.",
    "norway":                     "Noticias de balonmano en Noruega: Eliteserien, selección noruega y clubs.",
    "portugal":                   "Noticias de balonmano en Portugal: Andebol 1, selección portuguesa y clubs.",
    "austria":                    "Noticias de balonmano en Austria: HLA, selección y handball austriaco.",
    "switzerland":                "Noticias de balonmano en Suiza: NLA, selección y handball suizo.",
    "iceland":                    "Noticias de balonmano en Islandia: selección y clubs islandeses.",
    "faroe-islands":              "Noticias de balonmano en las Islas Feroe.",
    "hungary":                    "Noticias de balonmano en Hungría: Nemzeti Bajnokság y selección húngara.",
    "poland":                     "Noticias de balonmano en Polonia: PGNiG Superliga y selección polaca.",
    "croatia":                    "Noticias de balonmano en Croacia: HRK y selección croata.",
    "serbia":                     "Noticias de balonmano en Serbia: SuperLiga y selección serbia.",
    "slovakia":                   "Noticias de balonmano en Eslovaquia.",
    "slovenia":                   "Noticias de balonmano en Eslovenia: Liga NLB y selección eslovena.",
    "romania":                    "Noticias de balonmano en Rumanía: Liga Națională y selección rumana.",
    "greece":                     "Noticias de balonmano en Grecia.",
    "italy":                      "Noticias de balonmano en Italia: Serie A y selección italiana.",
    "north-macedonia":            "Noticias de balonmano en Macedonia del Norte.",
    "argentina":                  "Noticias de balonmano en Argentina: selección y clubs argentinos.",
    "brazil":                     "Noticias de balonmano en Brasil: selección y clubs brasileños.",
    "japan":                      "Noticias de balonmano en Japón: selección y clubs japoneses.",
    "turkey":                     "Noticias de balonmano en Turquía: selección y handball turco.",
    "czech-republic":             "Noticias de balonmano en República Checa: selección y clubs checos.",
}

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
            "germany/bundesliga":     "Daikin HBL (Masc)",
            "germany/bundesliga2":    "2. Bundesliga (Masc)",
            "germany/bundesliga-fem": "Alsco HBF (Fem)",
            "germany/bundesliga2-fem":"2. Bundesliga (Fem)",
            "germany":                "General",
        },
    },
    "france": {
        "label": "Francia",
        "color": "blue",
        "subsections": {
            "france/starligue": "Liqui Moly Starligue (Masc)",
            "france/pro-d2":    "ProLigue (Masc)",
            "france/d1f":       "Ligue Butagaz Énergie (Fem)",
            "france/d2f":       "D2F (Fem)",
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
            "turkey":         "Turquía",
            "czech-republic": "República Checa",
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
    {"type": "header", "label": "Alemania Masc"},
    {"type": "link",   "slug": "germany/bundesliga",  "label": "Daikin HBL"},
    {"type": "link",   "slug": "germany/bundesliga2", "label": "2. Bundesliga"},
    {"type": "header", "label": "Alemania Fem"},
    {"type": "link",   "slug": "germany/bundesliga-fem", "label": "Alsco HBF"},
    {"type": "link",   "slug": "germany/bundesliga2-fem","label": "2. Bundesliga Fem"},
    {"type": "link",   "slug": "germany",             "label": "General"},
    {"type": "separator"},
    {"type": "header", "label": "Francia Masc"},
    {"type": "link",   "slug": "france/starligue", "label": "Liqui Moly Starligue"},
    {"type": "link",   "slug": "france/pro-d2",    "label": "ProLigue"},
    {"type": "header", "label": "Francia Fem"},
    {"type": "link",   "slug": "france/d1f",        "label": "Ligue Butagaz Énergie"},
    {"type": "link",   "slug": "france/d2f",         "label": "D2F"},
    {"type": "link",   "slug": "france",             "label": "General"},
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


def _render_sitemap(slugs):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls = [
        f'  <url><loc>{BASE_URL}/</loc><changefreq>hourly</changefreq><priority>1.0</priority><lastmod>{today}</lastmod></url>',
        f'  <url><loc>{BASE_URL}/all/</loc><changefreq>hourly</changefreq><priority>0.8</priority><lastmod>{today}</lastmod></url>',
    ]
    for slug in slugs:
        urls.append(
            f'  <url><loc>{BASE_URL}/{slug}/</loc><changefreq>daily</changefreq><priority>0.7</priority><lastmod>{today}</lastmod></url>'
        )
    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + '\n'.join(urls) + '\n</urlset>\n'


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
        description = SECTION_DESCRIPTIONS.get(
            slug,
            f"Últimas noticias de {data['label']} — balonmano, handball, resultados y fichajes.",
        )
        html = section_tmpl.render(
            **base_ctx,
            section_slug=slug,
            section_label=data["label"],
            section_description=description,
            articles=data["articles"],
        )
        (section_dir / "index.html").write_text(html, encoding="utf-8")
    logger.info("Rendered %d section pages", len(sections_data))

    sitemap = _render_sitemap(list(sections_data.keys()))
    (OUTPUT_DIR / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    ROOT_DIR = OUTPUT_DIR.parent
    (ROOT_DIR / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    logger.info("Rendered sitemap.xml (%d URLs)", 2 + len(sections_data))

    robots = f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n"
    (OUTPUT_DIR / "robots.txt").write_text(robots, encoding="utf-8")
    (ROOT_DIR / "robots.txt").write_text(robots, encoding="utf-8")
    logger.info("Rendered robots.txt")
