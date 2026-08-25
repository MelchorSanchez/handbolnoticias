"""Scrapea resultados/calendario y clasificaciones de ligas españolas desde
resultadosbalonmano.isquad.es (sistema oficial de la RFEBM) y renderiza las
páginas /resultados/ y /clasificaciones/.

El scraping solo se ejecuta viernes, sábado y domingo (cuando hay partidos).
El renderizado se ejecuta siempre, con lo último que haya en la BD.
"""

import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader

import db

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"}
TIMEOUT = 20

BASE = Path(__file__).parent.parent
COMPETITIONS_PATH = BASE / "config" / "competitions.yaml"
MATCH_URL = (
    "https://resultadosbalonmano.isquad.es/competicion.php"
    "?seleccion=0&id={id}&id_ambito=1&id_territorial=9999&id_superficie=1"
    "&iframe=0&id_categoria={id_categoria}&id_competicion={id_competicion}&jornada={jornada}"
)
STANDINGS_URL = (
    "https://resultadosbalonmano.isquad.es/clasificacion.php"
    "?seleccion=0&id={id}&id_ambito=1&id_territorial=9999&id_superficie=1"
    "&iframe=0&id_categoria={id_categoria}&id_competicion={id_competicion}"
)

_INT_RE = re.compile(r"-?\d+")


def load_competitions() -> list:
    data = yaml.safe_load(COMPETITIONS_PATH.read_text(encoding="utf-8"))
    return data["competitions"]


def _first_int(text: str, default=None):
    m = _INT_RE.search(text or "")
    return int(m.group()) if m else default


def _get(url: str) -> str:
    resp = httpx.get(url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
    resp.raise_for_status()
    return resp.text


def _max_jornada(html: str) -> int:
    jornadas = [int(n) for n in re.findall(r"jornada=(\d+)", html)]
    return max(jornadas) if jornadas else 1


def _parse_jornada(html: str, competition: str, jornada: int) -> list:
    soup = BeautifulSoup(html, "lxml")
    fetched_at = datetime.now(timezone.utc).isoformat()
    matches = []
    for tr in soup.select("tr.partido"):
        match_id = tr.get("data-id")
        status = tr.get("data-estado", "").strip()
        if not match_id:
            continue

        names = tr.select(".nombres-equipos a")
        home_team = names[0].get_text(strip=True) if len(names) > 0 else ""
        away_team = names[1].get_text(strip=True) if len(names) > 1 else ""

        home_crest_el = tr.select_one(".escudo-local-wrap img")
        away_crest_el = tr.select_one(".escudo-visitante-wrap img")
        home_crest = home_crest_el.get("src") if home_crest_el else None
        away_crest = away_crest_el.get("src") if away_crest_el else None

        local_el = tr.select_one(".col-marcador .local")
        visitante_el = tr.select_one(".col-marcador .visitante")
        home_score = _first_int(local_el.get_text() if local_el else "")
        away_score = _first_int(visitante_el.get_text() if visitante_el else "")

        date_el = tr.select_one(".negrita")
        date_text = date_el.get_text(strip=True) if date_el else ""
        match_date = None
        if date_text:
            time_text = ""
            time_el = date_el.find_next_sibling("div")
            if time_el:
                time_text = time_el.get_text(strip=True)
            try:
                if time_text and re.match(r"^\d{1,2}:\d{2}$", time_text):
                    dt = datetime.strptime(f"{date_text} {time_text}", "%d/%m/%Y %H:%M")
                else:
                    dt = datetime.strptime(date_text, "%d/%m/%Y")
                match_date = dt.isoformat()
            except ValueError:
                match_date = None

        venue_el = tr.select_one(".col-lugar span")
        venue = venue_el.get_text(strip=True) if venue_el else ""

        matches.append({
            "match_id": match_id,
            "competition": competition,
            "jornada": jornada,
            "home_team": home_team,
            "away_team": away_team,
            "home_crest": home_crest,
            "away_crest": away_crest,
            "home_score": home_score,
            "away_score": away_score,
            "status": status,
            "match_date": match_date,
            "venue": venue,
            "fetched_at": fetched_at,
        })
    return matches


def _parse_standings(html: str, competition: str) -> list:
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table.clasificacion")
    if not table:
        return []
    fetched_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for sort_order, tr in enumerate(table.select("tbody tr")):
        tds = tr.find_all("td")
        if len(tds) < 11:
            continue
        team_link = tds[1].select_one("a")
        team = team_link.get_text(strip=True) if team_link else tds[1].get_text(strip=True)
        crest_el = tds[1].select_one("img.escudo_tabla_clasificacion")
        rows.append({
            "competition": competition,
            "position": _first_int(tds[0].get_text(), 0),
            "sort_order": sort_order,
            "team": team,
            "crest": crest_el.get("src") if crest_el else None,
            "points": _first_int(tds[3].get_text(), 0),
            "played": _first_int(tds[4].get_text(), 0),
            "won": _first_int(tds[5].get_text(), 0),
            "drawn": _first_int(tds[6].get_text(), 0),
            "lost": _first_int(tds[7].get_text(), 0),
            "gf": _first_int(tds[8].get_text(), 0),
            "gc": _first_int(tds[9].get_text(), 0),
            "diff": _first_int(tds[10].get_text(), 0),
            "fetched_at": fetched_at,
        })
    return rows


def _es_fin_de_semana() -> bool:
    return datetime.now(timezone.utc).weekday() in (4, 5, 6)


def fetch_results(conn):
    if not _es_fin_de_semana():
        print("  No es viernes/sábado/domingo: no se piden resultados nuevos.")
        return

    competitions = load_competitions()
    for comp in competitions:
        slug = comp["slug"]
        try:
            first_page = _get(MATCH_URL.format(
                id=comp["id"], id_categoria=comp["id_categoria"],
                id_competicion=comp["id_competicion"], jornada=1,
            ))
        except Exception as exc:
            print(f"  Aviso: no se pudo obtener {slug} jornada 1: {exc}")
            continue

        max_jornada = _max_jornada(first_page)
        pendientes = db.jornadas_a_refrescar(conn, slug, max_jornada)
        if not pendientes:
            print(f"  {slug}: sin jornadas pendientes de actualizar.")
        for jornada in pendientes:
            try:
                if jornada == 1:
                    html = first_page
                else:
                    html = _get(MATCH_URL.format(
                        id=comp["id"], id_categoria=comp["id_categoria"],
                        id_competicion=comp["id_competicion"], jornada=jornada,
                    ))
                for match in _parse_jornada(html, slug, jornada):
                    db.upsert_match(conn, match)
                conn.commit()
                print(f"  {slug}: jornada {jornada} actualizada.")
            except Exception as exc:
                print(f"  Aviso: fallo en {slug} jornada {jornada}: {exc}")
            time.sleep(0.5)

        try:
            standings_html = _get(STANDINGS_URL.format(
                id=comp["id"], id_categoria=comp["id_categoria"],
                id_competicion=comp["id_competicion"],
            ))
            rows = _parse_standings(standings_html, slug)
            db.replace_standings(conn, slug, rows)
            conn.commit()
            print(f"  {slug}: clasificación actualizada ({len(rows)} equipos).")
        except Exception as exc:
            print(f"  Aviso: fallo en clasificación de {slug}: {exc}")
        time.sleep(0.5)


def _ultima_jornada_disputada(matches_by_jornada: dict) -> int:
    """Última jornada con todos los partidos ya 'Jugado'; si ninguna, la primera."""
    if not matches_by_jornada:
        return 1
    for jornada in sorted(matches_by_jornada.keys(), reverse=True):
        if all(m["status"] == "Jugado" for m in matches_by_jornada[jornada]):
            return jornada
    return min(matches_by_jornada.keys())


def render_results(conn):
    env = Environment(loader=FileSystemLoader(str(BASE / "templates")), autoescape=True)

    def fmt_match_date(iso: str) -> str:
        if not iso:
            return ""
        try:
            dt = datetime.fromisoformat(iso)
        except ValueError:
            return ""
        if dt.hour or dt.minute:
            return dt.strftime("%d/%m/%Y %H:%M")
        return dt.strftime("%d/%m/%Y")

    env.filters["matchdate"] = fmt_match_date

    competitions = load_competitions()
    grouped = {"fem": [], "masc": []}
    for comp in competitions:
        grouped[comp["gender"]].append(comp)

    index_tmpl = env.get_template("resultados_index.html")
    for mode in ("resultados", "clasificaciones"):
        html = index_tmpl.render(mode=mode, grouped=grouped)
        out = BASE / "docs" / mode / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        print(f"  Rendered {out}")

    comp_tmpl = env.get_template("resultados_competicion.html")
    for comp in competitions:
        slug = comp["slug"]
        matches_by_jornada = db.get_matches_by_jornada(conn, slug)
        standings = db.get_standings(conn, slug)
        default_jornada = _ultima_jornada_disputada(matches_by_jornada)
        for mode in ("resultados", "clasificaciones"):
            html = comp_tmpl.render(
                mode=mode,
                competition=comp,
                matches_by_jornada=matches_by_jornada,
                standings=standings,
                default_jornada=default_jornada,
            )
            out = BASE / "docs" / mode / slug / "index.html"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(html, encoding="utf-8")
        print(f"  Rendered {slug} (resultados + clasificaciones)")


def main():
    print("Actualizando resultados y clasificaciones...")
    conn = db.get_connection()
    fetch_results(conn)
    render_results(conn)
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
