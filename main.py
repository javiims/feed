"""
AMC Channels -> RSS (Series de Animación / Anime)

Queries the Parse (Back4App) backend used by amcchannels.es and builds
amc_animacion.xml. Run `python main.py --inspect` to print the genre/subgenre
values currently in the database (useful if AMC changes its data model again).
"""
import datetime
import json
import os
import re
import sys
import unicodedata

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from feedgen.feed import FeedGenerator

API_URL = "https://tuamc.b4a.app/classes/Content"
HEADERS = {
    "X-Parse-Application-Id": os.getenv("AMC_APP_ID", "EqXj3CWkTa9Ens1sPrzQkKMbBdnc6bYbHKR2qvRE"),
    "X-Parse-JavaScript-Key": os.getenv("AMC_JS_KEY", "Cd3j7SWbPhXJahCRK3D47bcYFNnHWFjBfiDnXSjX"),
}

OUTPUT_FILE = "amc_animacion.xml"
SITE = "https://amcchannels.es"
EPISODE_PATH = "/programa/"          # new site structure (was /series/)
SERIES_PATH = "/serie/"
PAGE_SIZE = 1000                     # Parse page size
MAX_PAGES = 50                       # safety stop
MAX_ITEMS = int(os.getenv("MAX_ITEMS", "500"))  # items kept in the feed

# Fields that may hold the genre classification (string or array of strings)
GENRE_FIELDS = ("genre", "genres")
SUBGENRE_FIELDS = ("subgenre", "subgenres", "subGenre", "category", "categories", "tags")
ANIME_RE = re.compile(r"anim", re.I)  # matches Animación / Animacion / Anime / Animation
SERIES_RE = re.compile(r"^serie", re.I)

# Server-side filter: broad regex instead of the old exact match
SERVER_WHERE = {
    "$and": [
        {"genre": {"$regex": "^[Ss]erie"}},
        {"$or": [
            {"subgenre": {"$regex": "[Aa]nim"}},
            {"genre": {"$regex": "[Aa]nim"}},
        ]},
    ]
}


def session():
    s = requests.Session()
    retry = Retry(total=4, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update(HEADERS)
    return s


def fetch_all(s, where=None, order="-createdAt"):
    """Fetch every matching row, paginating with skip (old code stopped at 1000)."""
    results = []
    for page in range(MAX_PAGES):
        params = {"order": order, "limit": PAGE_SIZE, "skip": page * PAGE_SIZE}
        if where:
            params["where"] = json.dumps(where)
        r = s.get(API_URL, params=params, timeout=60)
        r.raise_for_status()
        batch = r.json().get("results", [])
        results.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
    return results


def _strings(value):
    """Flatten str / list / Parse objects into plain strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        out = []
        for v in value:
            out.extend(_strings(v))
        return out
    if isinstance(value, dict):
        return [str(v) for k, v in value.items() if k in ("name", "title", "value") and v]
    return [str(value)]


def is_anime_series(item):
    genres = [g for f in GENRE_FIELDS for g in _strings(item.get(f))]
    subs = [g for f in SUBGENRE_FIELDS for g in _strings(item.get(f))]
    is_series = any(SERIES_RE.search(g) for g in genres) or not genres
    is_anime = any(ANIME_RE.search(g) for g in genres + subs)
    return is_series and is_anime


def parse_date(value):
    if isinstance(value, dict):          # Parse Date: {"__type": "Date", "iso": "..."}
        value = value.get("iso")
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def build_link(item):
    url = item.get("url") or ""
    if str(url).startswith("http"):
        return url
    slug = str(item.get("slug") or url or "").strip("/")
    if not slug:
        slug = slugify(item.get("metaTitle") or item.get("title") or "")
    # Old slugs may still carry a legacy prefix
    slug = re.sub(r"^(series|serie|programa)/", "", slug)
    is_series_page = str(item.get("type", "")).lower() in ("serie", "series", "show")
    return SITE + (SERIES_PATH if is_series_page else EPISODE_PATH) + slug


def get_items(s):
    try:
        items = fetch_all(s, where=SERVER_WHERE)
        print(f"Server-side filter returned {len(items)} items.")
    except requests.HTTPError as e:
        print(f"Server-side filter failed ({e}); falling back to client-side filter.")
        items = []
    # Double-check / fallback: scan recent content and filter locally.
    if not items:
        everything = fetch_all(s)
        print(f"Scanned {len(everything)} content rows.")
        items = everything
    items = [i for i in items if is_anime_series(i)]
    # Deduplicate by objectId
    unique = {i.get("objectId") or build_link(i): i for i in items}
    return list(unique.values())


def build_anime_rss():
    s = session()
    print("Fetching data from AMC API...")
    try:
        anime_list = get_items(s)
    except requests.RequestException as e:
        print(f"❌ Error fetching data: {e}")
        sys.exit(1)

    if not anime_list:
        print("⚠️ 0 items matched. Feed NOT overwritten. Run `python main.py --inspect`.")
        return

    def added_on(item):
        return (parse_date(item.get("publishDate")) or parse_date(item.get("createdAt"))
                or parse_date(item.get("updatedAt"))
                or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc))

    anime_list.sort(key=added_on, reverse=True)
    anime_list = anime_list[:MAX_ITEMS]

    fg = FeedGenerator()
    fg.title("AMC Channels - Series de Animación")
    fg.link(href=f"{SITE}/buscar/categoria/Series?sub=Animacion", rel="alternate")
    fg.description("Últimas series de animación publicadas en AMC Channels.")
    fg.language("es")

    for item in anime_list:
        title = item.get("metaTitle") or item.get("title") or "Sin título"
        link = build_link(item)
        description = item.get("description") or item.get("metaDescription") or "Sin descripción"
        fe = fg.add_entry(order="append")   # keep newest first
        fe.title(str(title))
        fe.link(href=link)
        fe.guid(str(item.get("objectId") or link), permalink=False)
        fe.description(str(description))
        fe.pubDate(added_on(item) if added_on(item).year > 1
                   else datetime.datetime.now(datetime.timezone.utc))

    fg.rss_file(OUTPUT_FILE, pretty=True)
    print(f"✅ RSS feed generated with {len(anime_list)} items: {OUTPUT_FILE}")


def inspect():
    """Print the classification values present in the DB, to adapt filters quickly."""
    s = session()
    rows = fetch_all(s)
    print(f"{len(rows)} rows. Fields seen: {sorted({k for r in rows for k in r})}\n")
    for field in GENRE_FIELDS + SUBGENRE_FIELDS + ("type",):
        counts = {}
        for r in rows:
            for v in _strings(r.get(field)):
                counts[v] = counts.get(v, 0) + 1
        if counts:
            print(f"[{field}]", dict(sorted(counts.items(), key=lambda x: -x[1])))


if __name__ == "__main__":
    inspect() if "--inspect" in sys.argv else build_anime_rss()
