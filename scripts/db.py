import hashlib
import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "articles.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        # Migrate: rebuild standings if it still has the old position-based
        # primary key (broke when several teams share position 0 pre-season).
        cols = [row[1] for row in conn.execute("PRAGMA table_info(standings)").fetchall()]
        if cols and "sort_order" not in cols:
            conn.execute("DROP TABLE standings")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS articles (
                id              TEXT PRIMARY KEY,
                url             TEXT UNIQUE NOT NULL,
                title           TEXT NOT NULL,
                title_orig      TEXT,
                summary         TEXT,
                image_url       TEXT,
                source_name     TEXT,
                section         TEXT NOT NULL,
                extra_sections  TEXT NOT NULL DEFAULT '',
                published       TEXT,
                fetched_at      TEXT NOT NULL,
                is_manual       INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS translations (
                text_hash   TEXT PRIMARY KEY,
                original    TEXT NOT NULL,
                translated  TEXT NOT NULL,
                lang_from   TEXT
            );
            CREATE TABLE IF NOT EXISTS blocked_articles (
                url TEXT PRIMARY KEY
            );
            CREATE TABLE IF NOT EXISTS matches (
                match_id    TEXT PRIMARY KEY,
                competition TEXT NOT NULL,
                jornada     INTEGER NOT NULL,
                home_team   TEXT NOT NULL,
                away_team   TEXT NOT NULL,
                home_crest  TEXT,
                away_crest  TEXT,
                home_score  INTEGER,
                away_score  INTEGER,
                status      TEXT NOT NULL,
                match_date  TEXT,
                venue       TEXT,
                fetched_at  TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS standings (
                competition TEXT NOT NULL,
                position    INTEGER NOT NULL,
                sort_order  INTEGER NOT NULL,
                team        TEXT NOT NULL,
                crest       TEXT,
                points      INTEGER,
                played      INTEGER,
                won         INTEGER,
                drawn       INTEGER,
                lost        INTEGER,
                gf          INTEGER,
                gc          INTEGER,
                diff        INTEGER,
                fetched_at  TEXT NOT NULL,
                PRIMARY KEY (competition, team)
            );
        """)
        # Migrate: add extra_sections if upgrading from old schema
        try:
            conn.execute("ALTER TABLE articles ADD COLUMN extra_sections TEXT NOT NULL DEFAULT ''")
        except Exception:
            pass


def article_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def block_article(conn: sqlite3.Connection, url: str):
    """Permanently block a URL from being inserted again."""
    conn.execute("INSERT OR IGNORE INTO blocked_articles (url) VALUES (?)", (url,))
    conn.execute("DELETE FROM articles WHERE url = ?", (url,))
    conn.commit()


def is_blocked(conn: sqlite3.Connection, url: str) -> bool:
    return conn.execute("SELECT 1 FROM blocked_articles WHERE url = ?", (url,)).fetchone() is not None


def insert_article(conn: sqlite3.Connection, article: dict) -> bool:
    """Insert article; if it exists, update section/extra_sections if classifier changed them.
    Returns True if new."""
    if is_blocked(conn, article["url"]):
        return False
    try:
        conn.execute("""
            INSERT INTO articles
                (id, url, title, title_orig, summary, image_url,
                 source_name, section, extra_sections, published, fetched_at, is_manual)
            VALUES
                (:id, :url, :title, :title_orig, :summary, :image_url,
                 :source_name, :section, :extra_sections, :published, :fetched_at, :is_manual)
        """, article)
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        conn.execute("""
            UPDATE articles
            SET section        = :section,
                extra_sections = :extra_sections,
                published      = CASE
                    WHEN :published IS NOT NULL AND (published IS NULL OR :published < published)
                    THEN :published
                    ELSE published
                END
            WHERE id = :id AND is_manual = 0
        """, {"id": article["id"], "section": article["section"],
               "extra_sections": article["extra_sections"],
               "published": article.get("published"),
               "fetched_at": article.get("fetched_at")})
        conn.commit()
        return False


def _section_filter(section: str) -> tuple:
    """SQL fragment + params to match articles belonging to a section (primary or extra)."""
    sql = """(section = ?
              OR (extra_sections != '' AND ('|' || extra_sections || '|') LIKE ('%|' || ? || '|%')))"""
    return sql, (section, section)


def get_articles_by_section(conn: sqlite3.Connection, section: str, days: int = 30) -> list:
    filt, params = _section_filter(section)
    return conn.execute(f"""
        SELECT * FROM articles
        WHERE {filt}
          AND (published > datetime('now', ? || ' days') OR published IS NULL)
        ORDER BY published DESC, fetched_at DESC
        LIMIT 100
    """, (*params, f"-{days}")).fetchall()


def get_recent_by_section(conn: sqlite3.Connection, section: str, limit: int = 5) -> list:
    filt, params = _section_filter(section)
    return conn.execute(f"""
        SELECT * FROM articles
        WHERE {filt}
        ORDER BY published DESC, fetched_at DESC
        LIMIT ?
    """, (*params, limit)).fetchall()


def get_all_sections(conn: sqlite3.Connection) -> list:
    rows = conn.execute("SELECT DISTINCT section FROM articles").fetchall()
    return [row["section"] for row in rows]


def article_exists(conn: sqlite3.Connection, article_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM articles WHERE id = ?", (article_id,)).fetchone()
    return row is not None


def _title_words(title: str) -> frozenset:
    words = re.sub(r'[^\w\s]', ' ', title.lower()).split()
    return frozenset(w for w in words if len(w) > 3)


def jornadas_a_refrescar(conn: sqlite3.Connection, competition: str, max_jornada: int) -> list:
    """Jornadas 1..max_jornada sin partidos guardados, o con algún partido no 'Jugado'."""
    rows = conn.execute(
        "SELECT jornada, status FROM matches WHERE competition = ?", (competition,)
    ).fetchall()
    by_jornada = {}
    for row in rows:
        by_jornada.setdefault(row["jornada"], []).append(row["status"])
    pendientes = []
    for jornada in range(1, max_jornada + 1):
        statuses = by_jornada.get(jornada)
        if not statuses or any(s != "Jugado" for s in statuses):
            pendientes.append(jornada)
    return pendientes


def upsert_match(conn: sqlite3.Connection, match: dict):
    conn.execute("""
        INSERT INTO matches
            (match_id, competition, jornada, home_team, away_team,
             home_crest, away_crest, home_score, away_score, status,
             match_date, venue, fetched_at)
        VALUES
            (:match_id, :competition, :jornada, :home_team, :away_team,
             :home_crest, :away_crest, :home_score, :away_score, :status,
             :match_date, :venue, :fetched_at)
        ON CONFLICT(match_id) DO UPDATE SET
            home_team=excluded.home_team, away_team=excluded.away_team,
            home_crest=excluded.home_crest, away_crest=excluded.away_crest,
            home_score=excluded.home_score, away_score=excluded.away_score,
            status=excluded.status, match_date=excluded.match_date,
            venue=excluded.venue, fetched_at=excluded.fetched_at
    """, match)


def replace_standings(conn: sqlite3.Connection, competition: str, rows: list):
    conn.execute("DELETE FROM standings WHERE competition = ?", (competition,))
    for row in rows:
        conn.execute("""
            INSERT INTO standings
                (competition, position, sort_order, team, crest, points, played, won, drawn, lost, gf, gc, diff, fetched_at)
            VALUES
                (:competition, :position, :sort_order, :team, :crest, :points, :played, :won, :drawn, :lost, :gf, :gc, :diff, :fetched_at)
        """, row)


def get_matches_by_jornada(conn: sqlite3.Connection, competition: str) -> dict:
    rows = conn.execute("""
        SELECT * FROM matches WHERE competition = ?
        ORDER BY jornada, match_date IS NULL, match_date
    """, (competition,)).fetchall()
    out = {}
    for row in rows:
        out.setdefault(row["jornada"], []).append(row)
    return out


def get_standings(conn: sqlite3.Connection, competition: str) -> list:
    return conn.execute("""
        SELECT * FROM standings WHERE competition = ? ORDER BY position, sort_order
    """, (competition,)).fetchall()


def is_title_duplicate(conn: sqlite3.Connection, title: str) -> bool:
    """Return True if an existing article (last 48 h) has ≥80% title word overlap."""
    new_words = _title_words(title)
    if len(new_words) < 4:
        return False
    rows = conn.execute("""
        SELECT title_orig FROM articles
        WHERE fetched_at > datetime('now', '-48 hours')
    """).fetchall()
    for row in rows:
        existing = _title_words(row["title_orig"] or "")
        if not existing:
            continue
        union = len(new_words | existing)
        if union and len(new_words & existing) / union >= 0.8:
            return True
    return False
