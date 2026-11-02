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

out = pathlib.Path(os.environ.get("PULLED_IMAGE_DIR", "pulled_card_images"))
out.mkdir(parents=True, exist_ok=True)
client = CardSightAI()


def save_image(img, path_stem):
    """CardSight's docs don't spell out the image return type, so handle the common ones."""
    data = None
    if isinstance(img, (bytes, bytearray)):
        data = bytes(img)
    elif hasattr(img, "read"):
        data = img.read()
    elif hasattr(img, "content") and isinstance(img.content, (bytes, bytearray)):
        data = img.content
    else:
        url = getattr(img, "url", None) or getattr(img, "image_url", None)
        if isinstance(img, str) and img.startswith("http"):
            url = img
        if url:
            with urllib.request.urlopen(url) as r:
                data = r.read()
    if not data:
        raise ValueError(f"Unrecognized image response type: {type(img).__name__}")
    ext = ".png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ".webp" if data[8:12] == b"WEBP" else ".jpg"
    path = out / (path_stem + ext)
    path.write_bytes(data)
    return path.name


rows = []
for card_id, query in CARDS.items():
    try:
        res = client.catalog.search_catalog(q=query, take=5)
        results = list(getattr(res, "results", []) or [])
        cards_only = [r for r in results if str(getattr(r, "type_", "")).lower().endswith("card")]
        hits = cards_only or results
        if not hits:
            rows.append([card_id, query, "", "NO MATCH", ""])
            print(f"  no match   {card_id}")
            continue
        top = hits[0]
        uuid = getattr(top, "id", None)
        if not uuid:
            rows.append([card_id, query, getattr(top, "name", ""), "NO ID ON RESULT", ""])
            print(f"  no id      {card_id}")
            continue
        img = client.images.get_card_image(card_id=uuid)
        fname = save_image(img, card_id)
        rows.append([card_id, query, getattr(top, "name", ""), "OK", fname])
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
