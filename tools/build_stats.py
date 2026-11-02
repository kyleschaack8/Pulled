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


if __name__ == "__main__":
    if MODE == "discover":
        discover()
    else:
        raise SystemExit("build mode is added after discovery")
