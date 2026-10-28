"""Informe de salud por fuente al final de cada ejecución del pipeline.

Guarda en la tabla source_health el resultado de la última descarga de cada fuente
y cuántas ejecuciones seguidas lleva fallando (error o feed vacío). Avisa de:
  - fuentes que dan error,
  - fuentes que responden pero sin ninguna entrada (selectores rotos, WAF que
    devuelve HTML en vez del feed...): fallan en silencio, sin error,
  - fuentes que llevan STALE_DAYS días sin aportar ningún artículo nuevo.

El informe va al log y, en GitHub Actions, también al resumen de la ejecución
($GITHUB_STEP_SUMMARY).

Uso suelto (estado guardado, sin descargar nada): python3 scripts/source_health.py
"""
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

logger = logging.getLogger(__name__)

STALE_DAYS = 30
SLOW_SECONDS = 20


def _now():
    return datetime.now(timezone.utc)


def _runs(n):
    return "1 ejecución" if n == 1 else f"{n} ejecuciones seguidas"


def _last_new_by_source(conn):
    rows = conn.execute(
        "SELECT source_name, MAX(fetched_at) FROM articles GROUP BY source_name"
    ).fetchall()
    out = {}
    for name, ts in rows:
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            continue
        out[name] = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return out


def record_run(conn, health, new_by_source):
    """Guarda en source_health el resultado de esta ejecución."""
    now = _now().isoformat()
    for st in health:
        bad = bool(st["error"]) or st["raw"] == 0
        prev = conn.execute(
            "SELECT bad_runs, last_good_at FROM source_health WHERE source_name = ?",
            (st["name"],),
        ).fetchone()
        prev_bad, prev_good = (prev[0], prev[1]) if prev else (0, None)
        conn.execute(
            """INSERT OR REPLACE INTO source_health
               (source_name, last_run_at, raw, passed, new, error, seconds, bad_runs, last_good_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (st["name"], now, st["raw"], st["passed"], new_by_source.get(st["name"], 0),
             st["error"], st["seconds"], prev_bad + 1 if bad else 0,
             prev_good if bad else now),
        )
    conn.commit()


def build_report(conn, source_names):
    """Devuelve el informe en Markdown a partir del estado guardado."""
    rows = {
        r[0]: r for r in conn.execute(
            "SELECT source_name, last_run_at, raw, passed, new, error, seconds, bad_runs, last_good_at "
            "FROM source_health"
        ).fetchall()
    }
    last_new = _last_new_by_source(conn)
    stale_limit = _now() - timedelta(days=STALE_DAYS)

    errors, empty, stale, slow = [], [], [], []
    for name in source_names:
        r = rows.get(name)
        if r is None:
            continue
        _, _, raw, _, _, error, seconds, bad_runs, last_good = r
        since = f"última vez bien el {last_good[:10]}" if last_good else "sin ninguna descarga buena registrada"
        if error:
            errors.append(f"- **{name}**: {error} ({_runs(bad_runs)}, {since})")
        elif raw == 0:
            empty.append(f"- **{name}**: 0 entradas ({_runs(bad_runs)}, {since})")
        if seconds >= SLOW_SECONDS:
            slow.append(f"- **{name}**: {seconds:.0f} s")
        ln = last_new.get(name)
        if ln is None:
            stale.append((datetime.min.replace(tzinfo=timezone.utc), f"- **{name}**: ningún artículo nunca"))
        elif ln < stale_limit:
            stale.append((ln, f"- **{name}**: último artículo nuevo el {ln.date()} "
                              f"({(_now() - ln).days} días)"))
    stale.sort()

    measured = [rows[n] for n in source_names if n in rows]
    total_raw = sum(r[2] for r in measured)
    total_passed = sum(r[3] for r in measured)
    total_new = sum(r[4] for r in measured)
    total_secs = sum(r[6] for r in measured)

    lines = [
        "## Salud de las fuentes",
        "",
        f"{len(measured)} fuentes · {total_raw} entradas · {total_passed} pasan el filtro · "
        f"{total_new} artículos nuevos · {total_secs / 60:.1f} min descargando",
        "",
    ]
    for title, items in (
        ("Con error", errors),
        ("Responden pero sin entradas", empty),
        (f"Sin artículos nuevos en {STALE_DAYS} días", [s for _, s in stale]),
        (f"Lentas (≥ {SLOW_SECONDS} s)", slow),
    ):
        if items:
            lines += [f"### {title} ({len(items)})", "", *items, ""]
    if not measured:
        lines.append("Aún no hay datos: se guardan en cada ejecución del pipeline.")
    elif not (errors or empty or stale or slow):
        lines.append("Todas las fuentes funcionan.")
    return "\n".join(lines)


def report(conn, health, new_by_source):
    """Guarda esta ejecución y publica el informe en el log y en GitHub Actions."""
    record_run(conn, health, new_by_source)
    text = build_report(conn, [st["name"] for st in health])
    for line in text.splitlines():
        if line:
            logger.info(line)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(text + "\n")
    return text


if __name__ == "__main__":
    from db import get_connection, init_db
    from fetcher import load_sources

    init_db()
    conn = get_connection()
    print(build_report(conn, [s["name"] for s in load_sources()]))
