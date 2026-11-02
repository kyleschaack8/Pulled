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
import os
import pathlib
import sys
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
    for q in searches_for(card_id, query):
        res = client.catalog.search_catalog(q=q, take=10)
        results = list(getattr(res, "results", []) or [])
        cards_only = [r for r in results if str(getattr(r, "type_", "")).lower().endswith("card")]
        if cards_only:
            return cards_only[0], q
    return None, None


out = pathlib.Path(os.environ.get("PULLED_IMAGE_DIR", "pulled_card_images"))
out.mkdir(parents=True, exist_ok=True)
client = CardSightAI()


def describe_images_api():
    """Print what the SDK's image functions look like, for troubleshooting in the Actions log."""
    import inspect
    imgs = client.images
    print("CardSight image functions:")
    for n in dir(imgs):
        if n.startswith("_"):
            continue
        fn = getattr(imgs, n)
        if callable(fn):
            try:
                sig = str(inspect.signature(fn))
            except (TypeError, ValueError):
                sig = "(?)"
            print(f"  images.{n}{sig}")


def fetch_image(uuid):
    """Call the SDK's image function, trying the likely names and argument styles.
    Their docs say binary downloads may need a *_detailed variant, so try those first."""
    imgs = client.images
    names = [n for n in dir(imgs) if not n.startswith("_") and "image" in n.lower() and callable(getattr(imgs, n))]
    names.sort(key=lambda n: (0 if "detailed" in n else 1, n))
    last_err = None
    for n in names:
        fn = getattr(imgs, n)
        for call in (lambda f: f(id=uuid), lambda f: f(card_id=uuid), lambda f: f(uuid)):
            try:
                result = call(fn)
            except TypeError as e:
                last_err = e
                continue
            if result is not None:
                return result
    raise RuntimeError(f"No image function accepted the card id ({last_err})")


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


def save_image(img, path_stem):
    data = to_bytes(img)
    if not data:
        raise ValueError("Empty image")
    ext = ".png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ".webp" if data[8:12] == b"WEBP" else ".jpg"
    path = out / (path_stem + ext)
    path.write_bytes(data)
    return path.name


describe_images_api()

rows = []
for card_id, query in CARDS.items():
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
        img = fetch_image(uuid)
        fname = save_image(img, card_id)
        rows.append([card_id, used, getattr(top, "name", ""), "OK", fname])
        print(f"  saved      {card_id}  ->  {getattr(top, 'name', '')}")
    except Exception as e:  # keep going so one bad card doesn't stop the run
        rows.append([card_id, query, "", f"ERROR: {e}", ""])
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
            if k not in manifest and (out / v).exists():
                manifest[k] = v
    except ValueError:
        pass
(out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))

ok = sum(1 for r in rows if r[3] == "OK")
print(f"\nDone: {ok} of {len(CARDS)} images saved to {out.resolve()}")
print("Open matches.csv and check each match is the right set and parallel before using it.")
