import hashlib
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
        """)
        # Migrate: add extra_sections if upgrading from old schema
        try:
            conn.execute("ALTER TABLE articles ADD COLUMN extra_sections TEXT NOT NULL DEFAULT ''")
        except Exception:
            pass


def article_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def insert_article(conn: sqlite3.Connection, article: dict) -> bool:
    """Insert article; if it exists, update section/extra_sections if classifier changed them.
    Returns True if new."""
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
            SET section = :section, extra_sections = :extra_sections
            WHERE id = :id
              AND (section != :section OR extra_sections != :extra_sections)
        """, {"id": article["id"], "section": article["section"],
               "extra_sections": article["extra_sections"]})
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
