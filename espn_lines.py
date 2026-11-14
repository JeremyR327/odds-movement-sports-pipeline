#!/usr/bin/env python3
"""DraftKings open and current lines from ESPN's public scoreboard feed (no login).

Replaces the VSiN line tracker (VSiN does not allow scripted access). Runs on GitHub's
servers from the Pipeline loop. Each pull writes, per sport:
  data/<date>/HHMM_lines_<SPORT>.csv   one row per upcoming game: kick time, DK spread
                                       (away team's number), total and moneylines, open and now
  data/lines_status.json               "ok n games" / "error: ..." per sport
The day's pulls together give each game's path (publish_gist.py builds brief_<SPORT>.md).

ESPN's odds object (provider = DraftKings) carries pointSpread / total / moneyline with
"open" and "close" (close = current until kickoff). Older payloads only have "details"
("BUF -3.5") and "overUnder"; those fill the current line when the newer fields are missing.
Stdlib only.
"""
import csv, json, os, re, sys, time, urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
NOW = datetime.now(ET)
BASE = "https://site.api.espn.com/apis/site/v2/sports/"
# (path, extra query). NFL/CFB default to the current week; NBA/CBB are fetched for today
# and tomorrow ({d}; ESPN rejects a date range for the NBA).
LEAGUES = {
    "NFL": ("football/nfl", ""),
    "CFB": ("football/college-football", "&groups=80&limit=300"),   # FBS
    "NBA": ("basketball/nba", "&dates={d}"),
    "CBB": ("basketball/mens-college-basketball", "&groups=50&limit=500&dates={d}"),
}
FIELDS = ["pulled_et", "espn_id", "start_et", "away", "home", "away_abbr", "home_abbr", "book",
          "spread_open", "spread_now", "spread_odds_now", "total_open", "total_now",
          "ml_away_open", "ml_away_now", "ml_home_open", "ml_home_now", "status"]


def get(url):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 odds-pipeline", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception:
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))


def num(v):
    """'+3.5' / 'o47.5' / '-110' / 'EVEN' / 3.5 -> float (None if absent)."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().lower()
    if s in ("even", "ev"):          # moneyline even money
        return 100.0
    if s in ("pk", "pick"):          # pick'em spread
        return 0.0
    m = re.search(r"[+-]?\d+(?:\.\d+)?", s.replace(",", ""))
    return float(m.group(0)) if m else None


def dig(d, *keys):
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def parse_odds(odds, away_abbr, home_abbr):
    """-> dict of open/now numbers, spreads from the AWAY team's side."""
    o = {"book": dig(odds, "provider", "name") or ""}
    o["spread_open"] = num(dig(odds, "pointSpread", "away", "open", "line"))
    o["spread_now"] = num(dig(odds, "pointSpread", "away", "close", "line"))
    o["spread_odds_now"] = num(dig(odds, "pointSpread", "away", "close", "odds"))
    o["total_open"] = num(dig(odds, "total", "over", "open", "line"))
    o["total_now"] = num(dig(odds, "total", "over", "close", "line"))
    o["ml_away_open"] = num(dig(odds, "moneyline", "away", "open", "odds"))
    o["ml_away_now"] = num(dig(odds, "moneyline", "away", "close", "odds"))
    o["ml_home_open"] = num(dig(odds, "moneyline", "home", "open", "odds"))
    o["ml_home_now"] = num(dig(odds, "moneyline", "home", "close", "odds"))
    # Fallbacks from the older flat fields.
    if o["spread_now"] is None:
        det = (odds.get("details") or "").strip()
        m = re.match(r"(.+?)\s+([+-]?\d+(?:\.\d+)?)$", det)
        if m:
            fav, pts = m.group(1).strip().upper(), abs(float(m.group(2)))
            if fav == home_abbr.upper():
                o["spread_now"] = pts
            elif fav == away_abbr.upper():
                o["spread_now"] = -pts
        elif det.upper() in ("EVEN", "PK", "PICK"):
            o["spread_now"] = 0.0
    if o["total_now"] is None:
        o["total_now"] = num(odds.get("overUnder"))
    if o["ml_away_now"] is None:
        o["ml_away_now"] = num(dig(odds, "awayTeamOdds", "moneyLine"))
    if o["ml_home_now"] is None:
        o["ml_home_now"] = num(dig(odds, "homeTeamOdds", "moneyLine"))
    return o


def events(sport):
    path, extra = LEAGUES[sport]
    days = [NOW, NOW + timedelta(days=1)] if "{d}" in extra else [None]
    seen, out = set(), []
    for day in days:
        q = extra.format(d=day.strftime("%Y%m%d")) if day else extra
        for ev in get(BASE + path + "/scoreboard?" + q.lstrip("&")).get("events", []):
            if ev.get("id") not in seen:
                seen.add(ev.get("id")); out.append(ev)
    return out


def pull(sport):
    rows = []
    for ev in events(sport):
        comp = (ev.get("competitions") or [{}])[0]
        state = dig(comp, "status", "type", "state") or dig(ev, "status", "type", "state") or ""
        if state != "pre":           # started or final: no longer a betting line
            continue
        teams = {c.get("homeAway"): c.get("team", {}) for c in comp.get("competitors", [])}
        if "home" not in teams or "away" not in teams:
            continue
        a, h = teams["away"], teams["home"]
        odds = next((x for x in comp.get("odds") or [] if "draft" in (dig(x, "provider", "name") or "").lower()),
                    (comp.get("odds") or [{}])[0])
        start = datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(ET)
        rows.append({"pulled_et": NOW.isoformat(timespec="minutes"), "espn_id": ev.get("id"),
                     "start_et": start.strftime("%a %m-%d %I:%M %p"),
                     "away": a.get("displayName", ""), "home": h.get("displayName", ""),
                     "away_abbr": a.get("abbreviation", ""), "home_abbr": h.get("abbreviation", ""),
                     **parse_odds(odds or {}, a.get("abbreviation", ""), h.get("abbreviation", "")),
                     "status": "neutral" if comp.get("neutralSite") else ""})
    return rows


def main():
    status = {"pulled_et": NOW.isoformat(timespec="minutes"), "source": "ESPN scoreboard (DraftKings lines)"}
    outdir = os.path.join("data", NOW.strftime("%Y-%m-%d"))
    os.makedirs(outdir, exist_ok=True)
    for sport in LEAGUES:
        try:
            rows = pull(sport)
            with_line = sum(1 for r in rows if r["spread_now"] is not None or r["total_now"] is not None)
            with_open = sum(1 for r in rows if r["spread_open"] is not None)
            if rows:
                with open(os.path.join(outdir, f"{NOW:%H%M}_lines_{sport}.csv"), "w", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
            status[sport] = f"ok {len(rows)} games ({with_line} with a line, {with_open} with the opener)"
        except Exception as e:
            status[sport] = f"error: {e}"[:200]
    with open(os.path.join("data", "lines_status.json"), "w") as f:
        json.dump(status, f, indent=2)
    print(json.dumps(status, indent=2))
    return 1 if all(str(v).startswith("error") for k, v in status.items() if k in LEAGUES) else 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--dump":     # debug: one raw odds object per league
        for sp in LEAGUES:
            evs = events(sp)
            odds = next((e["competitions"][0].get("odds") for e in evs if e["competitions"][0].get("odds")), None)
            print(sp, len(evs), "events;", json.dumps(odds[0] if odds else None)[:600])
        sys.exit(0)
    sys.exit(main())
