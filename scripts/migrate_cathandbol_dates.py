"""
One-off: fix scraped articles whose published == fetched_at (date was not extracted).
Fetches each article page and reads the real publication date.
Covers: CatHandbol, BalonmanoInfo, MiBalonmano.
"""
import sys
import time
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
from db import get_connection
from fetcher import _parse_date_text

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; HandbolNoticias/1.0)"}
TIMEOUT = 10.0
SOURCES = ("CatHandbol", "BalonmanoInfo", "MiBalonmano")

DATE_SELECTORS = [
    "time[datetime]",
    "span.artdate",
    "span.span-date",   # MiBalonmano
    ".itemDateCreated",
    ".entry-date",
    "span.published",
]


def _scrape_date(url):
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        for sel in DATE_SELECTORS:
            el = soup.select_one(sel)
            if el:
                dt_attr = el.get("datetime", "").strip()
                text = dt_attr if dt_attr else el.get_text().strip()
                if text:
                    result = _parse_date_text(text)
                    # Only return if parse succeeded (not a fallback to now)
                    from datetime import datetime, timezone
                    now_date = datetime.now(timezone.utc).date().isoformat()
                    if result[:10] != now_date:
                        return result
    except Exception as e:
        print(f"  ERROR {url}: {e}")
    return None


def main():
    conn = get_connection()
    placeholders = ",".join("?" * len(SOURCES))
    rows = conn.execute(f"""
        SELECT id, url, published, fetched_at, source_name
        FROM articles
        WHERE source_name IN ({placeholders})
          AND substr(published, 1, 10) = substr(fetched_at, 1, 10)
        ORDER BY source_name, url
    """, SOURCES).fetchall()

    print(f"Found {len(rows)} articles with suspicious dates")
    fixed = 0
    for row in rows:
        real_date = _scrape_date(row["url"])
        if real_date:
            conn.execute(
                "UPDATE articles SET published = ? WHERE id = ?",
                (real_date, row["id"])
            )
            conn.commit()
            fixed += 1
            print(f"  FIXED [{row['source_name']}] {real_date[:10]} <- ...{row['url'][-55:]}")
        else:
            print(f"  SKIP  [{row['source_name']}] {row['url'][-55:]}")
        time.sleep(0.3)

    print(f"\nDone: {fixed}/{len(rows)} dates corrected.")
    conn.close()


if __name__ == "__main__":
    main()
