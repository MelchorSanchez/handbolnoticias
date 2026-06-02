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
