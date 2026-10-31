"""
AMC Channels -> RSS (anime)

Detects anime straight from the Parse (Back4App) database behind amcchannels.es,
so it also finds items that the website no longer shows.

How detection works:
  1. Download ALL rows of `Content` (paginated) without filtering on genre or on
     visibility/publication flags, so hidden items are included.
  2. An item counts as anime if ANY of these is true:
       a) its genre/subgenre/tags contain "anim" (Animación, Anime...)
       b) it points (Parse Pointer) to a parent object that is anime
       c) it belongs to a series already known to be anime (matched by
          series title "Serie: Episodio X" or by slug prefix)
  3. `seen_ids.json` stores every objectId already published plus the date it
     was first detected. Anything not in that file is treated as NEW, whatever its
     createdAt/updatedAt says.

Commands:
  python main.py              -> build the feed
  python main.py --inspect    -> list fields, genre values and pointer fields
  python main.py --latest 50  -> show the 50 most recently created rows (any genre)
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

BASE_URL = "https://tuamc.b4a.app/classes/"
CONTENT_CLASS = "Content"
HEADERS = {
    "X-Parse-Application-Id": os.getenv("AMC_APP_ID", "EqXj3CWkTa9Ens1sPrzQkKMbBdnc6bYbHKR2qvRE"),
    "X-Parse-JavaScript-Key": os.getenv("AMC_JS_KEY", "Cd3j7SWbPhXJahCRK3D47bcYFNnHWFjBfiDnXSjX"),
}

OUTPUT_FILE = "amc_animacion.xml"
STATE_FILE = "seen_ids.json"
SITE = "https://amcchannels.es"
EPISODE_PATH = "/programa/"
SERIES_PATH = "/serie/"
PAGE_SIZE = 1000
MAX_PAGES = 100
MAX_ITEMS = int(os.getenv("MAX_ITEMS", "500"))

CLASS_FIELDS = ("genre", "genres", "subgenre", "subgenres", "subGenre",
                "category", "categories", "tags", "channel", "channels")
ANIME_RE = re.compile(r"anim", re.I)
EXCLUDE_RE = re.compile(r"^(cine|pel[ií]cula|movie)", re.I)  # ignore animated films
UTC = datetime.timezone.utc


# ----------------------------------------------------------------- API helpers
def session():
    s = requests.Session()
    retry = Retry(total=4, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update(HEADERS)
    return s


def fetch_all(s, class_name=CONTENT_CLASS, where=None, order="-createdAt"):
    """Fetch every row of a class. No visibility filter => hidden rows included."""
    rows = []
    for page in range(MAX_PAGES):
        params = {"order": order, "limit": PAGE_SIZE, "skip": page * PAGE_SIZE}
        if where:
            params["where"] = json.dumps(where)
        r = s.get(BASE_URL + class_name, params=params, timeout=60)
        r.raise_for_status()
        batch = r.json().get("results", [])
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
    return rows


# --------------------------------------------------------------- data helpers
def strings(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [x for v in value for x in strings(v)]
    if isinstance(value, dict):
        if value.get("__type") == "Pointer":
            return []
        return [str(v) for k, v in value.items() if k in ("name", "title", "value") and v]
    return [str(value)]


def pointers(item):
    """Yield (className, objectId) for every Pointer field (single or array)."""
    for v in item.values():
        for p in (v if isinstance(v, list) else [v]):
            if isinstance(p, dict) and p.get("__type") == "Pointer":
                yield p.get("className"), p.get("objectId")


def parse_date(value):
    if isinstance(value, dict):
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


def title_of(item):
    return item.get("metaTitle") or item.get("title") or item.get("name") or ""


def series_key(item):
    """'Yaiba: Samurai Legend: Episodio 3' -> 'yaiba-samurai-legend'."""
    t = title_of(item)
    if ":" in t:
        return slugify(t.rsplit(":", 1)[0])
    slug = str(item.get("slug") or "")
    m = re.match(r"(.+?)-(episodio|capitulo|temporada|t\d+)", slug)
    return m.group(1) if m else (slugify(t) or None)


def direct_anime(item):
    labels = [x for f in CLASS_FIELDS for x in strings(item.get(f))]
    if any(EXCLUDE_RE.search(x) for x in strings(item.get("genre"))):
        return False
    return any(ANIME_RE.search(x) for x in labels)


def build_link(item):
    url = str(item.get("url") or "")
    if url.startswith("http"):
        return url
    slug = str(item.get("slug") or url).strip("/") or slugify(title_of(item))
    slug = re.sub(r"^(series|serie|programa)/", "", slug)
    return SITE + EPISODE_PATH + slug


# ---------------------------------------------------------------- detection
def detect_anime(s):
    content = fetch_all(s)
    print(f"Downloaded {len(content)} rows from {CONTENT_CLASS}.")
    by_id = {(CONTENT_CLASS, r["objectId"]): r for r in content if r.get("objectId")}

    # Load parent classes referenced by pointers (e.g. Serie, Season) so their
    # genre can be inherited by episodes that don't carry one themselves.
    for cls in {c for r in content for c, _ in pointers(r)} - {CONTENT_CLASS, None}:
        try:
            for r in fetch_all(s, cls):
                by_id[(cls, r["objectId"])] = r
            print(f"Loaded pointer class '{cls}'.")
        except requests.HTTPError as e:
            print(f"Could not read class '{cls}' ({e.response.status_code}); skipped.")

    anime_ids = {k for k, r in by_id.items() if direct_anime(r)}

    # Propagate through pointers (episode -> season -> series) until stable.
    changed = True
    while changed:
        changed = False
        for k, r in by_id.items():
            if k not in anime_ids and any(p in anime_ids for p in pointers(r)):
                anime_ids.add(k)
                changed = True

    # Match by series name/slug against already-known anime series.
    anime_series = {series_key(by_id[k]) for k in anime_ids} - {None, ""}
    for k, r in by_id.items():
        if k[0] == CONTENT_CLASS and k not in anime_ids and series_key(r) in anime_series \
                and not EXCLUDE_RE.search(" ".join(strings(r.get("genre")))):
            anime_ids.add(k)

    return [by_id[k] for k in anime_ids if k[0] == CONTENT_CLASS]


# -------------------------------------------------------------------- state
def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1, sort_keys=True)


# ---------------------------------------------------------------------- feed
def build_anime_rss():
    s = session()
    try:
        anime = detect_anime(s)
    except requests.RequestException as e:
        print(f"❌ API error: {e}")
        sys.exit(1)
    if not anime:
        print("⚠️ 0 anime items detected. Feed NOT overwritten. Run with --inspect.")
        return

    state = load_state()
    first_run = not state
    now = datetime.datetime.now(UTC)
    new_items = []
    for item in anime:
        oid = item["objectId"]
        if oid not in state:
            created = parse_date(item.get("createdAt")) or now
            # First run: use the DB date. Later: use detection time so RSS
            # readers see it as new even if createdAt is old or was backdated.
            state[oid] = (created if first_run else now).isoformat()
            if not first_run:
                new_items.append(item)
    save_state(state)

    for item in new_items:
        print(f"🆕 NEW: {title_of(item)}  | genre={item.get('genre')} "
              f"subgenre={item.get('subgenre')} | {build_link(item)}")
    print(f"{len(new_items)} new item(s) since last run.")

    anime.sort(key=lambda i: parse_date(state[i["objectId"]]), reverse=True)
    anime = anime[:MAX_ITEMS]

    fg = FeedGenerator()
    fg.title("AMC Channels - Series de Animación")
    fg.link(href=f"{SITE}/buscar/categoria/Series?sub=Animacion", rel="alternate")
    fg.description("Últimas series de animación añadidas a AMC Channels "
                   "(incluye las que no aparecen en la web).")
    fg.language("es")
    for item in anime:
        fe = fg.add_entry(order="append")
        fe.title(str(title_of(item) or "Sin título"))
        fe.link(href=build_link(item))
        fe.guid(item["objectId"], permalink=False)
        fe.description(str(item.get("description") or item.get("metaDescription")
                           or "Sin descripción"))
        fe.pubDate(parse_date(state[item["objectId"]]))
    fg.rss_file(OUTPUT_FILE, pretty=True)
    print(f"✅ RSS feed generated with {len(anime)} items: {OUTPUT_FILE}")


# ------------------------------------------------------------------ debugging
def inspect():
    rows = fetch_all(session())
    print(f"{len(rows)} rows. Fields: {sorted({k for r in rows for k in r})}\n")
    print("Pointer fields:", sorted({f"{k}->{v.get('className')}" for r in rows
          for k, v in r.items() if isinstance(v, dict) and v.get("__type") == "Pointer"}))
    for field in CLASS_FIELDS + ("type", "published", "visible", "active", "status"):
        counts = {}
        for r in rows:
            for v in strings(r.get(field)) if field in CLASS_FIELDS else [str(r.get(field))]:
                counts[v] = counts.get(v, 0) + 1
        if any(k != "None" for k in counts):
            print(f"[{field}]", dict(sorted(counts.items(), key=lambda x: -x[1])))


def latest(n):
    params = {"order": "-createdAt", "limit": n}
    r = session().get(BASE_URL + CONTENT_CLASS, params=params, timeout=60)
    r.raise_for_status()
    for i in r.json().get("results", []):
        print(f"{i.get('createdAt')} | {title_of(i)} | genre={i.get('genre')} | "
              f"subgenre={i.get('subgenre')} | anime={direct_anime(i)}")


if __name__ == "__main__":
    if "--inspect" in sys.argv:
        inspect()
    elif "--latest" in sys.argv:
        idx = sys.argv.index("--latest")
        latest(int(sys.argv[idx + 1]) if len(sys.argv) > idx + 1 else 50)
    else:
        build_anime_rss()
