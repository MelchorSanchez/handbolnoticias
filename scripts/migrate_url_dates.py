"""One-off: fix Marca, MundoDeportivo, and FNavarraBM articles whose stored published date
is later than the real date extracted from the article URL."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from db import get_connection, init_db
from fetcher import _date_from_url

def main():
    init_db()
    conn = get_connection()

    rows = conn.execute("""
        SELECT id, url, published, fetched_at FROM articles
        WHERE source_name IN ('Marca-Balonmano', 'MundoDeportivo-Balonmano', 'FNavarraBM')
    """).fetchall()

    print(f"Found {len(rows)} articles to check")
    fixed = 0
    for row in rows:
        date = _date_from_url(row["url"])
        if date and date < row["published"]:
            conn.execute("UPDATE articles SET published=? WHERE id=?", (date, row["id"]))
            fixed += 1
            print(f"  Fixed: {row['url'][:80]}")
            print(f"         {row['published'][:10]} → {date[:10]}")

    conn.commit()
    conn.close()
    print(f"Fixed {fixed}/{len(rows)} articles")

if __name__ == "__main__":
    main()
