"""Fetch podcast/YouTube RSS feeds and render the /podcasts/ page."""

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import httpx
from jinja2 import Environment, FileSystemLoader

SHOWS = [
    {
        "id": "handball-talks",
        "name": "Handball Talks",
        "channel_url": "https://www.youtube.com/@HandballTalks/videos",
        "rss": "https://www.youtube.com/feeds/videos.xml?channel_id=UCUQLLtFh1nIKmiLTDkifNcQ",
        "type": "youtube",
        "color": "red",
        "description": "Entrevistas y análisis en español",
        "title_filter": "handball talks #",
        "pinned_video_ids": ["S31v8wMrVd8", "7E_yI-2qmA8", "zg4pbjSrYY0", "DRPf0smcrWI", "2dIdroMb_Bk"],
    },
    {
        "id": "liftados",
        "name": "Liftados Balonmano",
        "channel_url": "https://www.youtube.com/@LiftadosBalonmano",
        "rss": "https://www.youtube.com/feeds/videos.xml?channel_id=UCKFW6Z0guZ-0xVp5nWk2cHA",
        "type": "youtube",
        "color": "orange",
        "description": "Contenido de balonmano en YouTube",
    },
    {
        "id": "jimvic",
        "name": "Jim & Vic Handball Show",
        "channel_url": "https://www.youtube.com/@jimvichandballshow",
        "rss": "https://www.youtube.com/feeds/videos.xml?channel_id=UCOXZAyqR-_KN1sH_Ni8KeAQ",
        "type": "youtube",
        "color": "blue",
        "description": "Análisis y debate sobre balonmano",
    },
    {
        "id": "de-rosca",
        "name": "De Rosca",
        "channel_url": "https://www.cope.es/podcasts/de-rosca",
        "rss": "https://www.cope.es/rss/podcasts/de-rosca.xml",
        "type": "podcast",
        "color": "purple",
        "description": "El podcast de balonmano de COPE",
    },
    {
        "id": "the-spin",
        "name": "The Spin",
        "channel_url": "https://www.youtube.com/playlist?list=PL6FkWVdzEY0XqKtEWFdl1eKBOk_73ynWT",
        "rss": "https://www.youtube.com/feeds/videos.xml?playlist_id=PL6FkWVdzEY0XqKtEWFdl1eKBOk_73ynWT",
        "type": "youtube",
        "color": "green",
        "description": "Análisis del balonmano internacional",
    },
]

_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "media": "http://search.yahoo.com/mrss/",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"}
TIMEOUT = 15


def _fetch_pinned_video(video_id):  # type: (str) -> dict
    """Fetch metadata for a pinned YouTube video via oEmbed."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        resp = httpx.get(
            f"https://www.youtube.com/oembed?url={url}&format=json",
            headers=HEADERS, timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        thumbnail = f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"
        return {"title": data.get("title", ""), "url": url,
                "published": datetime.now(timezone.utc),
                "thumbnail": thumbnail, "type": "video"}
    except Exception:
        return None


def _parse_date(raw: str) -> datetime:
    """Parse ISO 8601 or RFC 2822 date strings into a UTC-aware datetime."""
    if not raw:
        return datetime.now(timezone.utc)
    raw = raw.strip()
    # ISO 8601 (YouTube Atom)
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            return datetime.strptime(raw[:25], fmt[:len(raw[:25])])
        except ValueError:
            pass
    try:
        import email.utils
        ts = email.utils.parsedate_to_datetime(raw)
        return ts
    except Exception:
        return datetime.now(timezone.utc)


def _fetch_youtube(show):  # type: (dict) -> list
    resp = httpx.get(show["rss"], headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    title_filter = show.get("title_filter", "").lower()
    seen_links = set()
    episodes = []
    for entry in root.findall("atom:entry", _NS):
        title_el = entry.find("atom:title", _NS)
        link_el = entry.find("atom:link[@rel='alternate']", _NS)
        pub_el = entry.find("atom:published", _NS)
        thumb_el = entry.find(".//media:thumbnail", _NS)
        title = title_el.text if title_el is not None else ""
        link = link_el.attrib.get("href", "") if link_el is not None else ""
        if link in seen_links:
            continue
        if "/shorts/" in link:
            continue
        if title_filter and title_filter not in title.lower():
            continue
        seen_links.add(link)
        published = _parse_date(pub_el.text if pub_el is not None else "")
        thumbnail = thumb_el.attrib.get("url", "") if thumb_el is not None else ""
        if "ytimg.com/vi/" in thumbnail:
            vid_id = thumbnail.split("/vi/")[1].split("/")[0]
            thumbnail = f"https://i.ytimg.com/vi/{vid_id}/mqdefault.jpg"
        episodes.append({"title": title, "url": link, "published": published,
                         "thumbnail": thumbnail, "type": "video"})
        if len(episodes) >= 5:
            break
    # Fill remaining slots from pinned_video_ids if RSS didn't return enough
    pinned_ids = show.get("pinned_video_ids", [])
    if len(episodes) < 5 and pinned_ids:
        seen_video_ids = {ep["url"].split("v=")[-1].split("&")[0] for ep in episodes}
        for vid_id in pinned_ids:
            if vid_id in seen_video_ids:
                continue
            ep = _fetch_pinned_video(vid_id)
            if ep:
                episodes.append(ep)
                seen_video_ids.add(vid_id)
            if len(episodes) >= 5:
                break
    return episodes


def _fetch_podcast(show):  # type: (dict) -> list
    resp = httpx.get(show["rss"], headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    channel = root.find("channel")
    if channel is None:
        return []
    # Channel-level thumbnail fallback
    chan_img = ""
    img_el = channel.find("image/url")
    if img_el is not None:
        chan_img = img_el.text or ""
    episodes = []
    for item in channel.findall("item")[:5]:
        title_el = item.find("title")
        link_el = item.find("link")
        pub_el = item.find("pubDate")
        itunes_img = item.find("itunes:image", _NS)
        thumb = (itunes_img.attrib.get("href", "") if itunes_img is not None else "") or chan_img
        title = (title_el.text or "").strip() if title_el is not None else ""
        link = (link_el.text or "").strip() if link_el is not None else ""
        published = _parse_date(pub_el.text if pub_el is not None else "")
        episodes.append({"title": title, "url": link, "published": published,
                         "thumbnail": thumb, "type": "podcast"})
    return episodes


def fetch_shows():  # type: () -> list
    results = []
    for show in SHOWS:
        try:
            if show["type"] == "youtube":
                episodes = _fetch_youtube(show)
            else:
                episodes = _fetch_podcast(show)
            results.append({**show, "episodes": episodes})
        except Exception as exc:
            print(f"  Warning: could not fetch {show['name']}: {exc}")
            results.append({**show, "episodes": []})
    return results


def render_podcasts(shows):  # type: (list) -> None
    base = Path(__file__).parent.parent
    env = Environment(loader=FileSystemLoader(str(base / "templates")), autoescape=True)

    def fmt_date(dt: datetime) -> str:
        if not isinstance(dt, datetime):
            return ""
        return dt.strftime("%-d %b %Y")

    env.filters["fmtdate"] = fmt_date

    tmpl = env.get_template("podcasts.html")
    html = tmpl.render(shows=shows)
    out = base / "docs" / "podcasts" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"  Rendered {out}")


def main():
    print("Fetching podcast/video feeds...")
    shows = fetch_shows()
    render_podcasts(shows)
    print("Done.")


if __name__ == "__main__":
    main()
