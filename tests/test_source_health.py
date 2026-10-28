import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from db import init_db, insert_article, article_id
from fetcher import fetch_all
import source_health


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr("db.DB_PATH", tmp_path / "test.db")
    init_db()
    from db import get_connection
    return get_connection()


def _stats(name, raw=10, passed=5, error="", seconds=1.0):
    return {"name": name, "raw": raw, "passed": passed, "error": error, "seconds": seconds}


def _article(source, days_ago):
    url = f"https://example.com/{source}/{days_ago}"
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return {"id": article_id(url), "url": url, "title": "t", "title_orig": "t", "summary": "",
            "image_url": None, "source_name": source, "section": "spain", "extra_sections": "",
            "published": ts, "fetched_at": ts, "is_manual": 0}


def test_bad_runs_count_up_and_reset(conn):
    for _ in range(3):
        source_health.record_run(conn, [_stats("A", error="ConnectError: x")], {})
    assert conn.execute("SELECT bad_runs FROM source_health").fetchone()[0] == 3
    source_health.record_run(conn, [_stats("A")], {})
    bad_runs, last_good = conn.execute("SELECT bad_runs, last_good_at FROM source_health").fetchone()
    assert bad_runs == 0 and last_good


def test_empty_feed_counts_as_bad_but_keeps_last_good(conn):
    source_health.record_run(conn, [_stats("A")], {})
    good = conn.execute("SELECT last_good_at FROM source_health").fetchone()[0]
    source_health.record_run(conn, [_stats("A", raw=0, passed=0)], {})
    assert tuple(conn.execute("SELECT bad_runs, last_good_at FROM source_health").fetchone()) == (1, good)


def test_report_lists_errors_empty_and_stale(conn):
    insert_article(conn, _article("Fresh", 2))
    insert_article(conn, _article("Old", 60))
    health = [_stats("Fresh"), _stats("Old"), _stats("Broken", raw=0, passed=0, error="ReadTimeout: t"),
              _stats("Empty", raw=0, passed=0)]
    text = source_health.report(conn, health, {"Fresh": 1})
    errors = text.split("### Con error")[1].split("###")[0]
    empty = text.split("### Responden pero sin entradas")[1].split("###")[0]
    stale = text.split("### Sin artículos nuevos")[1].split("###")[0]
    assert "Broken" in errors and "ReadTimeout" in errors
    assert "Empty" in empty and "Broken" not in empty
    assert "Old" in stale and "Fresh" not in stale
    assert "1 artículos nuevos" in text


def test_report_writes_github_step_summary(conn, tmp_path, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    source_health.report(conn, [_stats("A")], {})
    assert "Salud de las fuentes" in summary.read_text()


def test_fetch_all_collects_health_including_errors():
    sources = [{"name": "Bad", "type": "rss", "url": "https://bad.example/feed", "section": "spain"}]
    with patch("fetcher._download_feed", side_effect=TimeoutError("boom")):
        health = []
        fetch_all(sources, health)
    assert health[0]["name"] == "Bad"
    assert health[0]["raw"] == 0 and "boom" in health[0]["error"]
