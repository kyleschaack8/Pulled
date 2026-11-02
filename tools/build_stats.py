"""
Pulled: player team, stats and injury status for every player in data/players.json.

Source for now: ESPN's public (unofficial) data feeds. Free and no key, but not licensed
for a commercial product, so switch to a licensed provider (e.g. balldontlie) before launch.
Only this file needs to change for that switch: the site reads data/stats.json.

Modes (MODE env):
  discover   save sample responses for a few players to debug/espn/ (for development)
  build      write data/stats.json for all players (run nightly)
"""
import json
import os
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
MODE = os.environ.get("MODE", "build")
LEAGUE = {"NBA": ("basketball", "nba"), "MLB": ("baseball", "mlb"), "NFL": ("football", "nfl")}
UA = {"User-Agent": "Mozilla/5.0 (Pulled test site; stats refresh)", "Accept": "application/json"}

_last = [0.0]


def get(url):
    wait = 0.6 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.time()
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"    HTTP {e.code} {url}")
        return None
    except Exception as e:  # noqa: BLE001
        print(f"    failed {url}: {e}")
        return None


def search(name, sport):
    q = urllib.parse.quote(name)
    sp, lg = LEAGUE[sport]
    return get(f"https://site.web.api.espn.com/apis/common/v3/search?query={q}&limit=5&type=player&sport={sp}&league={lg}")


def endpoints(sport, aid):
    sp, lg = LEAGUE[sport]
    base = f"https://site.web.api.espn.com/apis/common/v3/sports/{sp}/{lg}/athletes/{aid}"
    return {"athlete": base, "overview": base + "/overview", "stats": base + "/stats"}


def find_id(res):
    """Pull the first athlete id out of a search response, whatever its exact shape."""
    def walk(o):
        if isinstance(o, dict):
            if o.get("type") in ("player", "athlete") and o.get("id"):
                return str(o["id"])
            for k in ("items", "results", "contents", "data"):
                if k in o:
                    r = walk(o[k])
                    if r:
                        return r
            for v in o.values():
                r = walk(v)
                if r:
                    return r
        elif isinstance(o, list):
            for v in o:
                r = walk(v)
                if r:
                    return r
        return None
    return walk(res)


def discover():
    out = ROOT / "debug" / "espn"
    out.mkdir(parents=True, exist_ok=True)
    for name, sport in [("Stephen Curry", "NBA"), ("Aaron Judge", "MLB"), ("Patrick Mahomes", "NFL"), ("Ken Griffey Jr.", "MLB")]:
        slug = name.lower().replace(" ", "-").replace(".", "")
        res = search(name, sport)
        (out / f"{slug}-search.json").write_text(json.dumps(res, indent=1)[:200000])
        aid = find_id(res)
        print(f"{name}: id={aid}")
        if not aid:
            continue
        for label, url in endpoints(sport, aid).items():
            data = get(url)
            (out / f"{slug}-{label}.json").write_text(json.dumps(data, indent=1)[:400000])
            print(f"  {label}: {'ok' if data else 'none'} keys={list(data.keys())[:15] if isinstance(data, dict) else type(data).__name__}")


def load(name, default):
    try:
        return json.loads((DATA / name).read_text())
    except (OSError, ValueError):
        return default


def simple(s):
    return "".join(ch for ch in (s or "").lower() if ch.isalpha())


def lookup_id(player, cache):
    if player["id"] in cache:
        return cache[player["id"]]
    sp, lg = LEAGUE[player["sport"]]
    names = [player["name"]] + list(player.get("aka", []))
    names += [player["name"].replace(" Jr.", "").replace(",", "")]
    want = simple(player["name"].replace(" Jr.", ""))
    for name in dict.fromkeys(names):
        q = urllib.parse.quote(name)
        for url in (f"https://site.web.api.espn.com/apis/common/v3/search?query={q}&limit=5&type=player&sport={sp}&league={lg}",
                    f"https://site.web.api.espn.com/apis/common/v3/search?query={q}&limit=10&type=player"):
            res = get(url) or {}
            for it in res.get("items", []) or []:
                if it.get("type") == "player" and it.get("league") in (lg, None) and (it.get("sport") in (sp, None)):
                    if want[:6] in simple(it.get("displayName", "")):
                        cache[player["id"]] = str(it["id"])
                        return cache[player["id"]]
    return None  # not cached, so it's retried next run


def pick(labels, values, wanted):
    """Values for the wanted labels (first occurrence), keeping order."""
    out = []
    for w in wanted:
        if w in labels:
            out.append([w, values[labels.index(w)]])
    return out


KEY = {
    "NBA": ["PTS", "REB", "AST", "FG%", "3P%", "STL", "BLK", "GP"],
    "MLB": ["HR", "RBI", "H", "R", "AB", "BB", "SO", "GP", "W", "L", "ERA", "K", "IP", "WHIP", "SV"],
    "NFL": ["YDS", "TD", "INT", "CMP%", "RTG", "REC", "CAR", "TOT", "SACK", "GP"],
}


def build():
    players = load("players.json", {}).get("players", [])
    cache = load("espn_ids.json", {})
    out = {"source": "ESPN public data feeds (unofficial; replace with a licensed provider before launch)",
           "updated": time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()), "players": {}}
    for p in players:
        aid = lookup_id(p, cache)
        if not aid:
            print(f"- {p['name']}: not found")
            continue
        urls = endpoints(p["sport"], aid)
        ath = (get(urls["athlete"]) or {}).get("athlete") or {}
        ov = get(urls["overview"]) or {}
        rec = {"espnId": aid}
        team = ath.get("team") or {}
        rec["team"] = team.get("displayName") or ""
        rec["teamAbbr"] = team.get("abbreviation") or ""
        rec["teamColor"] = ("#" + team["color"]) if team.get("color") else ""
        rec["teamAlt"] = ("#" + team["alternateColor"]) if team.get("alternateColor") else ""
        rec["jersey"] = ath.get("jersey") or ""
        rec["position"] = (ath.get("position") or {}).get("abbreviation") or ""
        rec["active"] = bool(ath.get("active"))
        rec["experience"] = ath.get("displayExperience") or ""
        rec["draft"] = ath.get("displayDraft") or ""
        inj = (ath.get("injuries") or [None])[0]
        if inj:
            det = inj.get("details") or {}
            rec["injury"] = {"status": inj.get("status") or "", "comment": inj.get("shortComment") or "",
                             "date": (inj.get("date") or "")[:10], "type": det.get("type") or "",
                             "returnDate": (det.get("returnDate") or "")[:10]}
        summ = ath.get("statsSummary") or {}
        if summ.get("statistics"):
            rec["summary"] = {"label": summ.get("displayName") or "This season",
                              "stats": [[s.get("abbreviation"), s.get("displayValue"), s.get("rankDisplayValue") or ""]
                                        for s in summ["statistics"]][:4]}
        st = ov.get("statistics") or {}
        labels = st.get("labels") or []
        splits = {s.get("displayName"): s.get("stats") or [] for s in st.get("splits") or []}
        want = KEY.get(p["sport"], [])
        rec["statsLabel"] = st.get("displayName") or ""
        for key, name in (("season", "Regular Season"), ("career", "Career"), ("projected", "Projected"), ("last5", "Last 5 Games")):
            if splits.get(name):
                rec[key] = pick(labels, splits[name], want)[:6]
        rec["awards"] = [[a.get("name"), a.get("displayCount") or ""] for a in (ov.get("awards") or [])][:6]
        out["players"][p["id"]] = rec
        print(f"- {p['name']}: {rec['team'] or 'no team'} {rec['jersey']} season={bool(rec.get('season'))} career={bool(rec.get('career'))} injury={rec.get('injury', {}).get('status', '-')}")
    (DATA / "stats.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, sort_keys=True))
    (DATA / "espn_ids.json").write_text(json.dumps(cache, indent=1, sort_keys=True))
    found = len(out["players"])
    print(f"\nStats saved for {found} of {len(players)} players.")


if __name__ == "__main__":
    if MODE == "discover":
        discover()
    else:
        build()
