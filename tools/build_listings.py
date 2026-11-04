"""
Pulled: live eBay listings for every tracked card (data/listings.json).

Uses the eBay Browse API (free developer account). For each tracked card it searches the
Sports Trading Card Singles category, keeps listings whose titles match the card, and splits
them into raw and PSA 10. Saves the count, lowest and typical asking price, and a few of the
cheapest listings with links. One search per card per run (well under eBay's daily limit).

Secrets (GitHub -> Settings -> Secrets and variables -> Actions):
  EBAY_CLIENT_ID      your Production App ID (Client ID)
  EBAY_CLIENT_SECRET  your Production Cert ID (Client Secret)
Optional:
  EBAY_CAMPAIGN_ID    eBay Partner Network campaign id, to earn commission on clicks
"""
import base64
import json
import os
import pathlib
import re
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CID = os.environ.get("EBAY_CLIENT_ID", "").strip()
SECRET = os.environ.get("EBAY_CLIENT_SECRET", "").strip()
CAMPAIGN = os.environ.get("EBAY_CAMPAIGN_ID", "").strip()
CATEGORY = "261328"  # Sports Trading Card Singles (eBay US)
GRADED = re.compile(r"\b(PSA|BGS|SGC|CGC|BECKETT|GRADED|HGA|CSG|ARENA|TAG|ISA|KSA|GMA|MNT)\b", re.I)
OTHER_GRADER = re.compile(r"\b(BGS|SGC|CGC|BECKETT|HGA|CSG|ARENA|TAG|ISA|KSA|GMA|MNT)\b", re.I)
PSA10 = re.compile(r"\bPSA\s*-?\s*10\b|\bPSA\s*GEM\s*(MT|MINT)\s*10\b", re.I)
PARALLEL = re.compile(r"\b(silver|gold|red|blue|green|orange|purple|pink|black|white|bronze|holo|refractor|xfractor|mojo|shimmer|wave|cracked ice|hyper|disco|camo|tie[- ]dye|neon|auto|autograph|autographed|signed|patch|relic|jersey|sp|ssp|variation|image variation|parallel|chrome|rainbow|foil|lazer|laser|tri[- ]?colou?r|velocity|scope|fast break|choice|sapphire|atomic|prizm)\b|/\s?\d{1,4}\b", re.I)
JUNK = re.compile(r"\b(LOT|LOTS|REPRINT|RP|CUSTOM|DIGITAL|PICK|CHOOSE|YOU PICK|COMPLETE SET|TEAM SET|SLAB PACK|MYSTERY|REPACK|PROJECT 2020|PROJECT 70|BEN BALLER|ART CARD|PROXY|FACSIMILE)\b", re.I)


def token():
    auth = base64.b64encode(f"{CID}:{SECRET}".encode()).decode()
    body = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}).encode()
    req = urllib.request.Request("https://api.ebay.com/identity/v1/oauth2/token", data=body, method="POST",
                                 headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["access_token"]


def search(tok, q):
    params = {"q": q, "category_ids": CATEGORY, "limit": "100", "filter": "buyingOptions:{FIXED_PRICE|AUCTION},priceCurrency:USD"}
    url = "https://api.ebay.com/buy/browse/v1/item_summary/search?" + urllib.parse.urlencode(params)
    headers = {"Authorization": f"Bearer {tok}", "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"}
    if CAMPAIGN:
        headers["X-EBAY-C-ENDUSERCTX"] = f"affiliateCampaignId={CAMPAIGN}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"    HTTP {e.code}: {e.read()[:200]!r}")
        return {}


def simple(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def matches(title, card, last):
    t = title.lower()
    if JUNK.search(title) or last not in simple(title):
        return False
    num = str(card.get("number") or "").lower().lstrip("#")
    if num and not re.search(r"(#|no\.?\s?|\s)" + re.escape(num) + r"\b", t):
        return False
    base = (card.get("title", "") + " " + card.get("release", "") + " " + card.get("set", "")).lower()
    # every special-version word in the title must also be in the card's own name (so a Chrome card can say Chrome)
    for m in PARALLEL.finditer(title):
        w = m.group(0).lower()
        if re.sub(r"[\s-]", "", w) not in re.sub(r"[\s-]", "", base):
            return False
    yr = str(card.get("year") or "")[:4]
    if yr and yr not in t and (yr[2:] + "-") not in t:
        return False
    return True


def summarize(items):
    prices = sorted(i["price"] for i in items)
    cheap = sorted(items, key=lambda i: i["price"])[:3]
    return {"count": len(items), "low": prices[0] if prices else None,
            "typical": round(statistics.median(prices), 2) if prices else None,
            "auctions": sum(1 for i in items if i["auction"]), "cheapest": cheap}


def build():
    if not (CID and SECRET):
        raise SystemExit("Add EBAY_CLIENT_ID and EBAY_CLIENT_SECRET as GitHub secrets first.")
    players = {p["id"]: p for p in json.loads((DATA / "players.json").read_text())["players"]}
    cards = json.loads((DATA / "cards.json").read_text())["cards"]
    tok = token()
    out = {"source": "eBay Browse API (active listings, eBay US)", "updated": time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()), "cards": {}}
    for c in cards:
        p = players.get(c["playerId"])
        if not p:
            continue
        name = p["name"].replace(" Jr.", "")
        last = simple(name.split()[-1])
        q = f'{name} {c.get("year", "")[:4]} {c.get("release", "")} {c.get("number", "")}'.strip()
        res = search(tok, q)
        raw, psa = [], []
        for it in res.get("itemSummaries") or []:
            title = it.get("title") or ""
            if not matches(title, c, last):
                continue
            try:
                price = float((it.get("price") or {}).get("value"))
            except (TypeError, ValueError):
                continue
            rec = {"title": title[:120], "price": price, "url": it.get("itemAffiliateWebUrl") or it.get("itemWebUrl") or "",
                   "auction": "AUCTION" in (it.get("buyingOptions") or []), "ends": (it.get("itemEndDate") or "")[:16]}
            if PSA10.search(title) and not OTHER_GRADER.search(title):
                psa.append(rec)
            elif not GRADED.search(title):
                raw.append(rec)
        out["cards"][c["id"]] = {"raw": summarize(raw), "psa10": summarize(psa), "query": q}
        print(f"- {c['title']} ({p['name']}): raw {len(raw)}, PSA 10 {len(psa)}")
        time.sleep(0.3)
    (DATA / "listings.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, sort_keys=True))
    print(f"\nListings saved for {len(out['cards'])} cards.")


if __name__ == "__main__":
    build()
