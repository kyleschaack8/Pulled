"""
Pulled: build real card data from CardSight AI for every player in data/players.json.

For each player it finds their rookie-year cards, then saves:
  data/cards.json    card details (year, release, set, number, print run, rookie flag)
  data/prices.json   12 months of completed-sale prices and sales counts, raw and PSA 10
  images/cards/      one real card image per player (the top card)
  data/progress.json which players are done and how many API calls were used

It's resumable and budgeted: each run stops after MAX_CALLS API calls (default 200),
saves what it has, and the next run picks up where it left off.

Run on GitHub: Actions tab -> "Build card data" -> Run workflow.
Needs the CARDSIGHTAI_API_KEY repository secret.

Environment options:
  MAX_CALLS=200          API call budget for this run
  CARDS_PER_PLAYER=4     cards tracked per player
  MODE=build             build = add players not done yet; prices = refresh prices for all tracked cards
"""
import datetime as dt
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = os.environ.get("CARDSIGHTAI_BASE_URL", "https://api.cardsight.ai").rstrip("/")
KEY = os.environ.get("CARDSIGHTAI_API_KEY")
if not KEY:
    sys.exit("No API key found. Add the CARDSIGHTAI_API_KEY repository secret.")

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
IMAGES = ROOT / "images" / "cards"
IMAGES.mkdir(parents=True, exist_ok=True)

MAX_CALLS = int(os.environ.get("MAX_CALLS", "200"))
PER_PLAYER = int(os.environ.get("CARDS_PER_PLAYER", "4"))
MODE = os.environ.get("MODE", "build")

PRIORITY = ["prizm", "topps chrome", "bowman chrome", "optic", "topps update", "topps", "bowman",
            "select", "mosaic", "upper deck", "fleer", "score", "donruss", "contenders",
            "national treasures", "flawless", "goudey", "leaf", "spx", "finest"]


class RateLimited(Exception):
    pass


class OutOfBudget(Exception):
    pass


calls = {"n": 0}
_last = [0.0]


def api(path, params=None, raw=False):
    if calls["n"] >= MAX_CALLS:
        raise OutOfBudget()
    wait = 1.5 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.time()
    calls["n"] += 1
    q = ("?" + urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})) if params else ""
    req = urllib.request.Request(API + path + q, headers={"X-API-Key": KEY, "Accept": "image/*" if raw else "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise RateLimited(f"HTTP 429 on {path}") from None
        if e.code == 404:
            return None
        detail = e.read()[:200].decode("utf-8", "replace")
        if "limit" in detail.lower() or "quota" in detail.lower():
            raise RateLimited(detail) from None
        print(f"    HTTP {e.code} on {path}: {detail}")
        return None
    return body if raw else json.loads(body)


def g(d, *keys, default=None):
    """Read the first present key (handles camelCase or snake_case)."""
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] is not None:
            return d[k]
    return default


def load(name, default):
    try:
        return json.loads((DATA / name).read_text())
    except (OSError, ValueError):
        return default


def save(name, obj):
    (DATA / name).write_text(json.dumps(obj, indent=1, ensure_ascii=False, sort_keys=True))


def norm(s):
    return re.sub(r"[^a-z ]", "", (s or "").lower().replace(".", "").replace(",", ""))


def months_axis():
    today = dt.date.today().replace(day=1)
    out = []
    y, m = today.year, today.month
    for _ in range(12):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


MONTHS = months_axis()


def series(candles):
    """Monthly candles -> 12 medians (None when no sales) and 12 counts, on the shared month axis."""
    by = {}
    for c in candles or []:
        start = str(g(c, "periodStart", "period_start", default=""))[:7]
        types = g(c, "types", default={}) or {}
        a = g(types, "auction", default=None)
        if a and start:
            by[start] = (g(a, "median"), int(g(a, "count", default=0) or 0))
    med = [round(by[m][0], 2) if m in by and by[m][0] is not None else None for m in MONTHS]
    cnt = [by[m][1] if m in by else 0 for m in MONTHS]
    return {"median": med, "count": cnt}


def price_history(card_id):
    ts = api(f"/v1/pricing/{card_id}/timeseries", {"interval": "monthly", "periods": 12, "listing_type": "auction"})
    if not ts:
        return None
    out = {"raw": series(g(g(ts, "raw", default={}), "candles", default=[]))}
    for comp in g(ts, "graded", default=[]) or []:
        if str(g(comp, "companyName", "company_name", default="")).upper() == "PSA":
            for gr in g(comp, "grades", default=[]) or []:
                if str(g(gr, "gradeValue", "grade_value", default="")) == "10":
                    out["psa10"] = series(g(gr, "candles", default=[]))
    return out


def has_sales(ph):
    return ph and any(v for k in ("raw", "psa10") if k in ph for v in ph[k]["count"])


def api_post(path, body):
    if calls["n"] >= MAX_CALLS:
        raise OutOfBudget()
    wait = 1.5 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.time()
    calls["n"] += 1
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"X-API-Key": KEY, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise RateLimited(f"HTTP 429 on {path}") from None
        print(f"    HTTP {e.code} on {path}: {e.read()[:200].decode('utf-8', 'replace')}")
        return None


def sales_counts(card_ids):
    """One bulk call: how many completed sales each candidate had in the last year (raw + graded, capped at 25 each)."""
    res = api_post("/v1/pricing/", {"card_ids": card_ids[:100], "period": "1y", "listing_type": "auction"})
    out = {}
    for item in g(res, "results", default=[]) or []:
        data = g(item, "data", default={}) or {}
        n = int(g(g(data, "raw", default={}), "count", default=0) or 0)
        for comp in g(data, "graded", default=[]) or []:
            for gr in g(comp, "grades", default=[]) or []:
                n += int(g(gr, "count", default=0) or 0)
            n += int(g(comp, "count", default=0) or 0) if not g(comp, "grades") else 0
        out[str(g(item, "card_id", "cardId"))] = n
    return out


def pick_cards(player):
    """Find the player's rookie-year cards, then keep the most-traded ones (one per release)."""
    name, year = player["name"], str(player["rookieYear"])
    last = norm(name.replace(" Jr.", "").replace(" Jr", "")).split()[-1]
    res = api("/v1/catalog/cards", {"name": name, "year": year, "take": 100})
    cards = g(res, "cards", default=[]) or []
    total = int(g(res, "totalCount", "total_count", default=0) or 0)
    if cards and total > 100:
        more = api("/v1/catalog/cards", {"name": name, "year": year, "take": 100, "skip": 100})
        cards += g(more, "cards", default=[]) or []
    if not cards:
        res = api("/v1/catalog/cards", {"name": name, "take": 100, "sort": "year", "order": "asc"})
        cards = g(res, "cards", default=[]) or []
        rookie = [c for c in cards if str(g(c, "releaseYear", "release_year", default="")).startswith(year)]
        cards = rookie or cards[:40]
    cands, seen = [], set()
    for c in cards:
        if last not in norm(g(c, "name", default="")):
            continue
        if g(c, "isParallelOnly", "is_parallel_only", default=False) or g(c, "variationOf", "variation_of"):
            continue
        k = (g(c, "releaseName", "release_name"), g(c, "setName", "set_name"), g(c, "number"))
        if k in seen or not g(c, "id"):
            continue
        seen.add(k)
        cands.append(c)
    if not cands:
        return []
    counts = sales_counts([str(g(c, "id")) for c in cands])

    def rank(c):
        rel = norm(g(c, "releaseName", "release_name", default=""))
        pri = next((i for i, p in enumerate(PRIORITY) if p in rel), len(PRIORITY))
        return (-counts.get(str(g(c, "id")), 0), pri)

    picked, releases = [], set()
    for c in sorted(cands, key=rank):
        if counts.get(str(g(c, "id")), 0) == 0:
            break
        rel = norm(g(c, "releaseName", "release_name", default=""))
        if rel in releases:
            continue
        releases.add(rel)
        picked.append(c)
        if len(picked) >= PER_PLAYER + 2:
            break
    return picked


def card_record(c, player):
    year = str(g(c, "releaseYear", "release_year", default=""))
    rel = g(c, "releaseName", "release_name", default="")
    st = g(c, "setName", "set_name", default="")
    num = g(c, "number", default="")
    attrs = g(c, "attributes", default=[]) or []
    title = f"{year[:4]} {rel}".strip()
    if st and norm(st) not in ("base set", "base", norm(rel)):
        title += f" {st}"
    if num:
        title += f" #{num}"
    return {"id": g(c, "id"), "playerId": player["id"], "title": title, "year": year, "release": rel, "set": st,
            "number": num, "numberedTo": g(c, "numberedTo", "numbered_to"), "attributes": attrs,
            "rookie": "RC" in [a.upper() for a in attrs] or str(player["rookieYear"]) == year[:4]}


def fetch_image(card_id):
    data = api(f"/v1/images/cards/{card_id}", {"format": "raw", "default": "false"}, raw=True)
    if data and (data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n"):
        ext = ".png" if data[:4] == b"\x89PNG" else ".jpg"
        (IMAGES / f"{card_id}{ext}").write_bytes(data)
        return f"images/cards/{card_id}{ext}"
    return None


def main():
    players = load("players.json", {}).get("players", [])
    cards = load("cards.json", {"cards": []})
    prices = load("prices.json", {"cards": {}})
    progress = load("progress.json", {"done": [], "calls": []})
    by_id = {c["id"]: c for c in cards["cards"]}
    status = "complete"
    try:
        if MODE == "prices":
            for cid in list(by_id):
                ph = price_history(cid)
                if ph:
                    prices["cards"][cid] = ph
            print(f"Refreshed prices for {len(by_id)} cards")
        else:
            todo = [p for p in players if p["id"] not in progress["done"]]
            print(f"{len(todo)} players to add, budget {MAX_CALLS} calls")
            for p in todo:
                print(f"- {p['name']} ({p['sport']}, {p['rookieYear']})")
                kept = 0
                for c in pick_cards(p):
                    if kept >= PER_PLAYER:
                        break
                    rec = card_record(c, p)
                    ph = price_history(rec["id"])
                    if not has_sales(ph):
                        continue
                    if kept == 0 and not rec.get("image"):
                        rec["image"] = fetch_image(rec["id"])
                    by_id[rec["id"]] = rec
                    prices["cards"][rec["id"]] = ph
                    kept += 1
                    print(f"    + {rec['title']}")
                if kept == 0:
                    print("    (no cards with recent sales found)")
                progress["done"].append(p["id"])
                cards["cards"] = list(by_id.values())
                save("cards.json", cards)
                save("prices.json", {**prices, "months": MONTHS})
                save("progress.json", progress)
    except OutOfBudget:
        status = f"stopped: used this run's budget of {MAX_CALLS} calls"
    except RateLimited as e:
        status = f"stopped: CardSight rate limit ({e})"
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    cards["cards"] = list(by_id.values())
    cards["updated"] = now
    prices["months"] = MONTHS
    prices["updated"] = now
    progress["calls"] = (progress.get("calls", []) + [{"at": now, "used": calls["n"], "mode": MODE}])[-50:]
    save("cards.json", cards)
    save("prices.json", prices)
    save("progress.json", progress)
    done = len(progress["done"])
    print(f"\n{status}. {calls['n']} API calls used. Players done: {done} of {len(players)}. Cards tracked: {len(by_id)}.")


if __name__ == "__main__":
    main()
