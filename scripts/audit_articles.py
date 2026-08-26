"""Detecta artículos sospechosos de estar mal clasificados o corruptos.

No modifica nada: solo imprime un listado para revisión manual.
Uso: python3 scripts/audit_articles.py
"""
import re
import sqlite3
from pathlib import Path

from renderer import SECTION_DESCRIPTIONS

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "articles.db"

VALID_SLUGS = set(SECTION_DESCRIPTIONS.keys())

GARBAGE_PATTERNS = [
    r"error 500",
    r"error 404",
    r"server error",
    r"that.?s an error",
    r"page not found",
    r"just a moment",
    r"enable javascript",
    r"access denied",
    r"forbidden",
    r"attention required",
    r"are you a robot",
    r"captcha",
]
GARBAGE_RE = re.compile("|".join(GARBAGE_PATTERNS), re.IGNORECASE)

MASC_SLUGS = {
    "spain/asobal", "spain/dhp", "spain/primera-nacional-masc",
    "spain/seleccion-masc", "spain/base-masc",
    "europe/champions", "europe/european-league", "europe/cup-men",
    "europe/euro-men", "ihf/world-men",
    "germany/bundesliga", "germany/bundesliga2",
    "france/starligue", "france/pro-d2",
}
FEM_SLUGS = {
    "spain/guerreras", "spain/dho-fem", "spain/dhp-fem",
    "spain/seleccion-fem", "spain/base-fem",
    "europe/champions-women", "europe/european-league-women", "europe/cup-women",
    "europe/euro-women", "ihf/world-women",
    "germany/bundesliga-fem", "germany/bundesliga2-fem",
    "france/d1f", "france/d2f",
}
MASC_WORDS = re.compile(r"\bmasculin[oa]s?\b|\bhombres\b|\bchicos\b", re.IGNORECASE)
FEM_WORDS = re.compile(r"\bfemenin[oa]s?\b|\bmujeres\b|\bchicas\b|\bguerreras\b|\bféminas\b", re.IGNORECASE)

def all_sections(row):
    section, extra = row
    out = [section] if section else []
    if extra:
        out += [s for s in extra.split("|") if s]
    return out


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT id, title, summary, section, extra_sections, source_name, url FROM articles")
    rows = cur.fetchall()

    invalid_slug, garbage, gender_mismatch = [], [], []

    for id_, title, summary, section, extra, source, url in rows:
        secs = all_sections((section, extra))

        bad_slugs = [s for s in secs if s not in VALID_SLUGS]
        if bad_slugs:
            invalid_slug.append((id_, title, bad_slugs, source, url))

        if (title and GARBAGE_RE.search(title)) or (summary and GARBAGE_RE.search(summary)):
            garbage.append((id_, title, source, url))
            continue  # no tiene sentido seguir evaluando un artículo corrupto

        has_masc = any(s in MASC_SLUGS for s in secs)
        has_fem = any(s in FEM_SLUGS for s in secs)
        if title:
            title_masc = bool(MASC_WORDS.search(title))
            title_fem = bool(FEM_WORDS.search(title))
            if has_masc and not has_fem and title_fem and not title_masc:
                gender_mismatch.append((id_, title, secs, source, url, "sección masc., texto fem."))
            elif has_fem and not has_masc and title_masc and not title_fem:
                gender_mismatch.append((id_, title, secs, source, url, "sección fem., texto masc."))

    def show(label, items, cols):
        print(f"\n=== {label} ({len(items)}) ===")
        for item in items:
            print(" | ".join(str(x) for x in item))

    show("Slugs de sección inválidos", invalid_slug, None)
    show("Título/contenido con patrón de error o bloqueo (posible scrape corrupto)", garbage, None)
    show("Posible desajuste de género entre sección y título (revisar)", gender_mismatch, None)

    print(f"\nTotal artículos analizados: {len(rows)}")


if __name__ == "__main__":
    main()
