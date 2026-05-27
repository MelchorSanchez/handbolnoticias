"""One-off migration: convert RFC 2822 published dates to ISO 8601 in the DB."""
import sys
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from db import get_connection

conn = get_connection()
rows = conn.execute("SELECT id, published FROM articles WHERE published IS NOT NULL").fetchall()

fixed = 0
for row in rows:
    pub = row["published"]
    # RFC 2822 strings start with a weekday abbreviation (Mon/Tue/.../Sun)
    if pub and pub[:3] in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"):
        try:
            dt = parsedate_to_datetime(pub)
            iso = dt.astimezone(__import__("datetime").timezone.utc).isoformat()
            conn.execute("UPDATE articles SET published = ? WHERE id = ?", (iso, row["id"]))
            fixed += 1
        except Exception as e:
            print(f"  SKIP {row['id']}: {pub!r} → {e}")

conn.commit()
conn.close()
print(f"Migration complete: {fixed} dates converted out of {len(rows)} articles.")
