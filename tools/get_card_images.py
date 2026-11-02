"""
Pulled: download CardSight AI images for the cards in the test site.

Setup (one time):
  1. Get a free API key at cardsight.ai (no credit card needed).
  2. Install the SDK:            pip install cardsightai
  3. Save your key as an environment variable (keep it private, don't share it):
       Mac/Linux:  export CARDSIGHTAI_API_KEY="your_key_here"
       Windows:    setx CARDSIGHTAI_API_KEY "your_key_here"   (then open a new terminal)

Run:
  python tools/get_card_images.py

Output (folder set by PULLED_IMAGE_DIR, default pulled_card_images/):
  <card id>.jpg/.png/.webp   one image per card, named by the test site's card id
  matches.csv                what CardSight matched each card to, so you can check
                             it picked the right set and parallel
  manifest.json              card id -> image file, read by the website

Run automatically on GitHub: Actions tab -> "Fetch card images" -> Run workflow.

Uses about 2 API calls per card (32 total), well inside the free tier.
"""
import csv
import json
import time
import os
import pathlib
import sys
import urllib.error
import urllib.request

try:
    from cardsightai import CardSightAI
except ImportError:
    sys.exit("The CardSight SDK isn't installed. Run:  pip install cardsightai")

if not os.environ.get("CARDSIGHTAI_API_KEY"):
    sys.exit("No API key found. Set CARDSIGHTAI_API_KEY first (see the top of this file).")

# Test site card id -> search text for CardSight
CARDS = {
    "curry-chrome-ref":  "2009 Topps Chrome Stephen Curry 101 Refractor",
    "curry-contenders":  "2009 Playoff Contenders Stephen Curry Rookie Ticket Auto",
    "curry-chrome-base": "2009 Topps Chrome Stephen Curry 101",
    "curry-prizm":       "2012 Panini Prizm Stephen Curry 1 Silver",
    "wemby-silver":      "2023 Panini Prizm Victor Wembanyama 136 Silver",
    "wemby-base":        "2023 Panini Prizm Victor Wembanyama 136",
    "wemby-nt":          "2023 National Treasures Victor Wembanyama Rookie Patch Auto",
    "mahomes-silver":    "2017 Panini Prizm Patrick Mahomes 269 Silver",
    "mahomes-nt":        "2017 National Treasures Patrick Mahomes Rookie Patch Auto",
    "mahomes-optic":     "2017 Donruss Optic Patrick Mahomes Rated Rookie 177",
    "ohtani-update":     "2018 Topps Update Shohei Ohtani US1",
    "ohtani-orange":     "2018 Bowman Chrome Shohei Ohtani Prospect Auto Orange",
    "ohtani-chrome":     "2018 Topps Chrome Update Shohei Ohtani",
    "griffey-ud":        "1989 Upper Deck Ken Griffey Jr 1",
    "griffey-bowman":    "1989 Bowman Tiffany Ken Griffey Jr 220",
    "griffey-ud-raw":    "1989 Upper Deck Ken Griffey Jr 1",
}

# The card number on the real card, used to pick the right match among search results
NUMBERS = {
    "curry-chrome-ref": "101", "curry-contenders": "106", "curry-chrome-base": "101", "curry-prizm": "72",
    "wemby-silver": "136", "wemby-base": "136", "mahomes-silver": "269", "mahomes-nt": "161",
    "mahomes-optic": "177", "ohtani-update": "US1", "ohtani-chrome": "HMT1",
    "griffey-ud": "1", "griffey-bowman": "220", "griffey-ud-raw": "1",
}


class RateLimited(Exception):
    pass


_last_call = [0.0]


def pace():
    """Space out API calls so the free plan's per-minute limit isn't hit."""
    wait = 1.5 - (time.time() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.time()


def check_limit(obj):
    s = str(obj).lower()
    if "429" in s or "rate limit" in s or "too many requests" in s or "quota" in s:
        raise RateLimited(s[:200])


_card_cache = {}


def get_card(uuid):
    if uuid not in _card_cache:
        pace()
        card = client.catalog.get_card(id=uuid)
        check_limit(type(card).__name__ + " " + str(getattr(card, "message", "")) + " " + str(getattr(card, "code", "")))
        _card_cache[uuid] = card
    return _card_cache[uuid]


def _card_number(uuid):
    try:
        card = get_card(uuid)
        d = card.to_dict() if hasattr(card, "to_dict") else vars(card)
        return str(d.get("number", "")).strip().upper()
    except Exception:  # noqa: BLE001
        return ""


# Broader searches to try when the exact one finds nothing
FALLBACK = {
    "curry": "Stephen Curry", "wemby": "Victor Wembanyama", "mahomes": "Patrick Mahomes",
    "ohtani": "Shohei Ohtani", "griffey": "Ken Griffey Jr",
}


def searches_for(card_id, query):
    year = query.split()[0]
    player = FALLBACK.get(card_id.split("-")[0], "")
    words = query.split()
    set_words = [w for w in words[1:4] if not any(ch.isdigit() for ch in w)]
    tries = [query]
    if player:
        tries.append(f"{year} {' '.join(set_words[:2])} {player}".strip())
        tries.append(f"{year} {player}")
    seen = []
    return [q for q in tries if not (q in seen or seen.append(q))]


def find_card(card_id, query):
    """Search, then prefer the result whose card number matches the real card."""
    want = NUMBERS.get(card_id, "").upper()
    first = None
    for q in searches_for(card_id, query):
        pace()
        res = client.catalog.search_catalog(q=q, take=10)
        check_limit(type(res).__name__ + " " + str(getattr(res, "message", "")) + " " + str(getattr(res, "code", "")))
        results = list(getattr(res, "results", []) or [])
        cards_only = [r for r in results if str(getattr(r, "type_", "")).lower().endswith("card")]
        if not cards_only:
            continue
        if first is None:
            first = (cards_only[0], q)
        if not want:
            return cards_only[0], q
        for r in cards_only[:4]:
            if _card_number(getattr(r, "id", "")) == want:
                return r, q
    return first if first else (None, None)


out = pathlib.Path(os.environ.get("PULLED_IMAGE_DIR", "pulled_card_images"))
out.mkdir(parents=True, exist_ok=True)
client = CardSightAI()


API_BASE = os.environ.get("CARDSIGHTAI_BASE_URL", "https://api.cardsight.ai").rstrip("/")


def describe_images_api():
    import cardsightai
    print(f"cardsightai version: {getattr(cardsightai, '__version__', 'unknown')}")


def fetch_image(uuid):
    """Download the raw JPEG straight from CardSight's REST API.
    (The SDK's get_card_image asks for raw bytes but then parses them as JSON, which fails.)"""
    pace()
    req = urllib.request.Request(
        f"{API_BASE}/v1/images/cards/{uuid}?format=raw&default=false",
        headers={"X-API-Key": os.environ["CARDSIGHTAI_API_KEY"], "Accept": "image/*"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise RateLimited("HTTP 429") from None
        raise RuntimeError(f"CardSight returned HTTP {e.code} for this card's image") from None
    if not data or data[:1] in (b"{", b"["):
        raise RuntimeError("CardSight returned no image for this card")
    return data


def card_details(uuid):
    """Year / set / number / parallel for the matched card, so matches can be checked."""
    try:
        card = get_card(uuid)
        d = card.to_dict() if hasattr(card, "to_dict") else vars(card)
    except RateLimited:
        raise
    except Exception as e:  # noqa: BLE001
        return f"(details unavailable: {e})"
    keep = []
    for k, v in d.items():
        kl = k.lower()
        if any(w in kl for w in ("year", "set", "release", "number", "parallel", "variation", "name", "manufacturer")):
            if isinstance(v, (str, int, float)) and str(v).strip():
                keep.append(f"{k}={v}")
            elif isinstance(v, dict):
                n = v.get("name") or v.get("title")
                if n:
                    keep.append(f"{k}={n}")
    return "; ".join(keep[:8])


def to_bytes(img):
    """Turn whatever the SDK returned into raw image bytes."""
    if isinstance(img, (bytes, bytearray)):
        return bytes(img)
    for attr in ("content", "payload", "data", "body"):
        v = getattr(img, attr, None)
        if isinstance(v, (bytes, bytearray)) and v:
            return bytes(v)
        if v is not None and hasattr(v, "read"):
            return v.read()
    if hasattr(img, "read"):
        return img.read()
    parsed = getattr(img, "parsed", None)
    if parsed is not None and parsed is not img:
        return to_bytes(parsed)
    url = None
    if isinstance(img, str) and img.startswith("http"):
        url = img
    else:
        for attr in ("url", "image_url", "imageUrl", "signed_url"):
            v = getattr(img, attr, None)
            if isinstance(v, str) and v.startswith("http"):
                url = v
                break
    if url:
        with urllib.request.urlopen(url) as r:
            return r.read()
    raise ValueError(f"Unrecognized image response: {type(img).__name__} with fields {[a for a in dir(img) if not a.startswith('_')][:12]}")


def is_image(data):
    return data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n" or data[8:12] == b"WEBP"


def save_image(img, path_stem):
    data = to_bytes(img)
    if not data or not is_image(data):
        raise ValueError("CardSight did not return an image file")
    ext = ".png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ".webp" if data[8:12] == b"WEBP" else ".jpg"
    path = out / (path_stem + ext)
    path.write_bytes(data)
    return path.name


describe_images_api()

existing = {}
try:
    existing = json.loads((out / "manifest.json").read_text())
except (OSError, ValueError):
    pass
REFRESH = os.environ.get("PULLED_REFRESH") == "1"

rows = []
stopped = False
for card_id, query in CARDS.items():
    if stopped:
        rows.append([card_id, query, "", "SKIPPED (rate limit)", existing.get(card_id, "")])
        continue
    have = existing.get(card_id)
    if have and not REFRESH and (out / have).exists() and is_image((out / have).read_bytes()[:12]):
        rows.append([card_id, query, "kept existing image", "OK", have])
        print(f"  kept       {card_id}")
        continue
    top = None
    details = ""
    try:
        top, used = find_card(card_id, query)
        if top is None:
            rows.append([card_id, query, "", "NO MATCH", ""])
            print(f"  no match   {card_id}")
            continue
        uuid = getattr(top, "id", None)
        if not uuid:
            rows.append([card_id, query, getattr(top, "name", ""), "NO ID ON RESULT", ""])
            print(f"  no id      {card_id}")
            continue
        details = card_details(uuid)
        img = fetch_image(uuid)
        fname = save_image(img, card_id)
        rows.append([card_id, used, details or getattr(top, "name", ""), "OK", fname])
        print(f"  saved      {card_id}  ->  {getattr(top, 'name', '')}")
    except RateLimited as e:
        stopped = True
        rows.append([card_id, query, "", "STOPPED: CardSight rate limit", ""])
        print(f"  RATE LIMIT hit at {card_id}; stopping to save your free calls. Run again later. ({e})")
    except Exception as e:  # keep going so one bad card doesn't stop the run
        matched = details or ((getattr(top, "name", "") or "") if top is not None else "")
        rows.append([card_id, query, matched, f"ERROR: {e}", ""])
        print(f"  error      {card_id}: {e}")

with open(out / "matches.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["test_site_card_id", "searched_for", "cardsight_matched", "status", "image_file"])
    w.writerows(rows)

manifest = {r[0]: r[4] for r in rows if r[3] == "OK"}
old = out / "manifest.json"
if old.exists():  # keep images from earlier runs for cards that failed this time
    try:
        prev = json.loads(old.read_text())
        for k, v in prev.items():
            f = out / v
            if k not in manifest and f.exists() and is_image(f.read_bytes()[:12]):
                manifest[k] = v
    except ValueError:
        pass
(out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))

ok = sum(1 for r in rows if r[3] == "OK")
print(f"\nDone: {ok} of {len(CARDS)} images saved to {out.resolve()}")
print("Open matches.csv and check each match is the right set and parallel before using it.")
