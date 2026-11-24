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
from bs4 import BeautifulSoup, NavigableString
from jinja2 import Environment, FileSystemLoader

import db

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"}
TIMEOUT = 20

BASE = Path(__file__).parent.parent
COMPETITIONS_PATH = BASE / "config" / "competitions.yaml"
# embed=1 es imprescindible desde noviembre de 2026: isquad estrenó una web
# nueva (una SPA en /maqueta/ que pide los datos por POST a json/beta.php) y las
# páginas clásicas responden 302 hacia ella. Con embed=1 siguen devolviendo el
# HTML de siempre, que es lo que parsea este script; la propia SPA las usa así
# para las secciones que aún no ha migrado.
MATCH_URL = (
    "https://resultadosbalonmano.isquad.es/competicion.php"
    "?seleccion=0&id={id}&id_ambito={id_ambito}&id_territorial={id_territorial}&id_superficie=1"
    "&iframe=0&id_categoria={id_categoria}&id_competicion={id_competicion}&jornada={jornada}"
    "&embed=1"
)
STANDINGS_URL = (
    "https://resultadosbalonmano.isquad.es/clasificacion.php"
    "?seleccion=0&id={id}&id_ambito={id_ambito}&id_territorial={id_territorial}&id_superficie=1"
    "&iframe=0&id_categoria={id_categoria}&id_competicion={id_competicion}"
    "&embed=1"
)

_INT_RE = re.compile(r"-?\d+")
_DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")


def _cell_int(td, default=0):
    """Número de una celda de la clasificación.

    Las celdas llevan ahora un segundo valor dentro de un <div> (el porcentaje
    de partidos ganados, los goles por partido), así que el texto plano sale
    pegado: "276" + "30.67 gol/part." = "27630.67", y la base guardaba 27630
    goles a favor. El atributo data-export trae el valor limpio.
    """
    if td is None:
        return default
    exported = td.get("data-export")
    if exported is not None:
        return _first_int(exported, default)
    return _first_int(td.get_text(), default)


def load_competitions() -> list:
    data = yaml.safe_load(COMPETITIONS_PATH.read_text(encoding="utf-8"))
    return data["competitions"]


def _first_int(text: str, default=None):
    m = _INT_RE.search(text or "")
    return int(m.group()) if m else default


def _get(url: str) -> str:
    """Descarga una página clásica de isquad, reintentando si nos frena.

    isquad limita las peticiones seguidas: pedimos una página por jornada y por
    competición (bastantes cientos en una pasada), y a partir de cierto punto
    responde 429. Como las ligas catalanas van al final de competitions.yaml,
    eran justo las que se quedaban sin actualizar. Con una espera creciente la
    petición entra al segundo o tercer intento.
    """
    for intento, espera in enumerate((30, 60, 120)):
        resp = httpx.get(url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
        if resp.status_code != 429:
            resp.raise_for_status()
            return resp.text
        print(f"  isquad nos frena (429), espero {espera} s y reintento...")
        time.sleep(espera)
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

        # El primer .negrita de la fila ya no es la fecha: el nombre del equipo
        # local también lleva esa clase, y con ".negrita" a secas la fecha salía
        # como "HANDBOL GAVÀ (A)" y se perdía (716 de 5310 partidos con fecha).
        # Se busca el div cuyo texto sea una fecha dd/mm/aaaa.
        date_el = next(
            (d for d in tr.select("div.negrita") if _DATE_RE.match(d.get_text(strip=True))),
            None,
        )
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
        if team_link:
            # El <a> incluye un <span> con el indicador de subida/bajada de puesto
            # (p.ej. "1" si sube una posición) antes del nombre del equipo; solo el
            # nombre real llega como texto suelto (NavigableString) directamente
            # dentro del <a>, así que se ignora cualquier texto anidado en hijos.
            team = "".join(
                c for c in team_link.contents if isinstance(c, NavigableString)
            ).strip()
        else:
            team = tds[1].get_text(strip=True)
        crest_el = tds[1].select_one("img.escudo_tabla_clasificacion")
        rows.append({
            "competition": competition,
            "position": _first_int(tds[0].get_text(), 0),
            "sort_order": sort_order,
            "team": team,
            "crest": crest_el.get("src") if crest_el else None,
            "points": _cell_int(tds[3]),
            "played": _cell_int(tds[4]),
            "won": _cell_int(tds[5]),
            "drawn": _cell_int(tds[6]),
            "lost": _cell_int(tds[7]),
            "gf": _cell_int(tds[8]),
            "gc": _cell_int(tds[9]),
            "diff": _cell_int(tds[10]),
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
        id_ambito = comp.get("id_ambito", 1)
        id_territorial = comp.get("id_territorial", 9999)
        try:
            first_page = _get(MATCH_URL.format(
                id=comp["id"], id_categoria=comp["id_categoria"],
                id_competicion=comp["id_competicion"], jornada=1,
                id_ambito=id_ambito, id_territorial=id_territorial,
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
                        id_ambito=id_ambito, id_territorial=id_territorial,
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
                id_ambito=id_ambito, id_territorial=id_territorial,
            ))
            rows = _parse_standings(standings_html, slug)
            db.replace_standings(conn, slug, rows)
            conn.commit()
            print(f"  {slug}: clasificación actualizada ({len(rows)} equipos).")
        except Exception as exc:
            print(f"  Aviso: fallo en clasificación de {slug}: {exc}")
        time.sleep(0.5)


def _jornada_actual(matches_by_jornada: dict) -> int:
    """Primera jornada con algún partido aún sin jugar; si todas lo están, la última."""
    if not matches_by_jornada:
        return 1
    for jornada in sorted(matches_by_jornada.keys()):
        if any(m["home_score"] is None or m["away_score"] is None for m in matches_by_jornada[jornada]):
            return jornada
    return max(matches_by_jornada.keys())


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
        jornada_actual = _jornada_actual(matches_by_jornada)
        for mode in ("resultados", "clasificaciones"):
            html = comp_tmpl.render(
                mode=mode,
                competition=comp,
                matches_by_jornada=matches_by_jornada,
                standings=standings,
                jornada_actual=jornada_actual,
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
