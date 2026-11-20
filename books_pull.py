#!/usr/bin/env python3
"""Lines across books from The Odds API (free tier: 500 credits a month), plus book-lag flags.

ESPN gives us DraftKings only. This adds FanDuel and Novig (where Jeremy bets), Pinnacle (the
sharp reference; public-site odds, can lag a little), BetOnline and LowVig (early movers on sharp
action) and Kalshi. Runs on GitHub's servers from the Pipeline loop; needs the ODDS_API_KEY secret.

Cost: markets x regions, and with the `bookmakers` parameter every group of 10 books counts as one
region, so spreads + totals for these 7 books = 2 credits per sport per call (calls that return no
events are free). Schedule (loop_pull.py): 10:41 AM CBB, 3:29 PM and 7:44 PM NFL+CFB+CBB =
at most 14 credits a day, ~420 a month. A budget guard skips calls when credits run low.

Writes, per sport and pull:
  data/books/<date>/<HHMM>_books_<SPORT>.csv   one row per game x book: spread (away side) + price,
                                               total + prices, the book's last update
  data/books/latest/<SPORT>.csv                 one row per game: every book side by side, LAG flags
  data/books/latest/board_<SPORT>.md            the same as a table, lag games first
  data/books/status.json                        per sport ok/error, credits used/remaining
LAG (spreads): FanDuel or Novig offers a side 1+ point better than the sharp reference (Pinnacle,
else DraftKings) = the book hasn't caught up with the market. Totals: 1.5+.
Usage: python3 books_pull.py NFL CFB CBB
"""
import csv, json, os, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime
from statistics import median
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
NOW = datetime.now(ET)
API = "https://api.the-odds-api.com/v4/sports/{sport}/odds"
SPORT_KEYS = {"NFL": "americanfootball_nfl", "CFB": "americanfootball_ncaaf", "CBB": "basketball_ncaab"}
BOOKS = ["pinnacle", "draftkings", "fanduel", "novig", "betonlineag", "lowvig", "kalshi"]   # <= 10 = 1 region
SHORT = {"pinnacle": "PIN", "draftkings": "DK", "fanduel": "FD", "novig": "NOV", "betonlineag": "BOL",
         "lowvig": "LV", "kalshi": "KAL"}
BET_BOOKS = ["fanduel", "novig"]          # where Jeremy bets: these are checked for lag
LAG_SPREAD, LAG_TOTAL = 1.0, 1.5
MIN_CREDITS = {"floor": 8, "reserve": 40}  # below reserve only the 3:29 PM pull runs; below floor none
LONG = ["pulled_et", "event_id", "commence_et", "away", "home", "book", "last_update",
        "spread_away", "spread_away_price", "spread_home_price", "total", "over_price", "under_price"]
STATUS = "data/books/status.json"


def fetch(sport, key):
    q = urllib.parse.urlencode({"apiKey": key, "markets": "spreads,totals", "oddsFormat": "american",
                                "bookmakers": ",".join(BOOKS), "dateFormat": "iso"})
    req = urllib.request.Request(API.format(sport=SPORT_KEYS[sport]) + "?" + q,
                                 headers={"User-Agent": "odds-pipeline", "Accept": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                h = {k.lower(): v for k, v in r.headers.items()}
                return json.loads(r.read().decode()), h
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:200]
            if e.code in (401, 422, 429) or attempt == 2:      # bad key / bad params / out of credits: don't retry
                raise RuntimeError(f"HTTP {e.code}: {body}")
        except Exception:
            if attempt == 2:
                raise
        time.sleep(4 * (attempt + 1))


def rows_for(events):
    out = []
    for ev in events:
        away, home = ev.get("away_team", ""), ev.get("home_team", "")
        start = datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00")).astimezone(ET)
        for b in ev.get("bookmakers", []):
            r = {"pulled_et": NOW.isoformat(timespec="minutes"), "event_id": ev.get("id"),
                 "commence_et": start.isoformat(timespec="minutes"), "away": away, "home": home,
                 "book": b.get("key"), "last_update": b.get("last_update", "")}
            for m in b.get("markets", []):
                oc = {o.get("name"): o for o in m.get("outcomes", [])}
                if m.get("key") == "spreads" and away in oc and home in oc:
                    r.update(spread_away=oc[away].get("point"), spread_away_price=oc[away].get("price"),
                             spread_home_price=oc[home].get("price"))
                elif m.get("key") == "totals" and "Over" in oc and "Under" in oc:
                    r.update(total=oc["Over"].get("point"), over_price=oc["Over"].get("price"),
                             under_price=oc["Under"].get("price"))
            out.append(r)
    return out


def lag_flags(by_book):
    """by_book: book -> row. Spreads from the away side: a bigger away number is better for the away bettor."""
    ref_book = next((b for b in ("pinnacle", "draftkings") if by_book.get(b, {}).get("spread_away") is not None), None)
    flags, side, line, book_used = [], "", None, ""
    if ref_book:
        ref = float(by_book[ref_book]["spread_away"])
        for b in BET_BOOKS:
            v = by_book.get(b, {}).get("spread_away")
            if v is None:
                continue
            v = float(v)
            if v - ref >= LAG_SPREAD and (line is None or v - ref > abs(line - ref)):
                side, line, book_used = "away", v, b
            elif ref - v >= LAG_SPREAD and (line is None or ref - v > abs(line - ref)):
                side, line, book_used = "home", v, b
        if side:
            k = 1 if side == "away" else -1          # show each side's own number (home -2 vs -3.5)
            flags.append(f"LAG {SHORT[book_used]} {side} {k * line:+g} vs {SHORT[ref_book]} {k * ref:+g}")
    tref = next((b for b in ("pinnacle", "draftkings") if by_book.get(b, {}).get("total") is not None), None)
    if tref:
        t = float(by_book[tref]["total"])
        for b in BET_BOOKS:
            v = by_book.get(b, {}).get("total")
            if v is not None and abs(float(v) - t) >= LAG_TOTAL:
                flags.append(f"LAG-TOT {SHORT[b]} {'under' if float(v) > t else 'over'} {float(v):g} vs {SHORT[tref]} {t:g}")
    # side/line are the bet: away spread number at the lagging book (away-side convention)
    return flags, side, line, (SHORT[book_used] if book_used else ""), (SHORT[ref_book] if ref_book else "")


def wide(rows):
    games = {}
    for r in rows:
        games.setdefault(r["event_id"], {"event_id": r["event_id"], "commence_et": r["commence_et"],
                                         "away": r["away"], "home": r["home"], "_b": {}})["_b"][r["book"]] = r
    out = []
    for g in games.values():
        bb = g.pop("_b")
        for b in BOOKS:
            s = bb.get(b, {})
            g[f"{SHORT[b]}_spread_away"] = s.get("spread_away", "")
            g[f"{SHORT[b]}_spread_price"] = s.get("spread_away_price", "")
            g[f"{SHORT[b]}_total"] = s.get("total", "")
        sp = [float(bb[b]["spread_away"]) for b in bb if bb[b].get("spread_away") is not None]
        g["spread_range"] = round(max(sp) - min(sp), 1) if len(sp) > 1 else ""
        g["spread_median"] = median(sp) if sp else ""
        flags, side, line, book, ref = lag_flags(bb)
        g.update(lag_flag="; ".join(flags), lag_side=side, lag_spread_away=line if line is not None else "",
                 lag_book=book, lag_ref=ref, pulled_et=NOW.isoformat(timespec="minutes"))
        out.append(g)
    out.sort(key=lambda g: (not g["lag_flag"], g["commence_et"]))
    return out


def board(sport, games, note):
    cols = [SHORT[b] for b in BOOKS]
    lines = [f"# Lines across books — {sport} (pulled {NOW:%Y-%m-%d %H:%M} ET, The Odds API)", "",
             "Spread = AWAY team's number. PIN = Pinnacle (public-site odds, can lag a little), NOV = Novig, "
             "KAL = Kalshi. LAG = FanDuel or Novig 1+ pt better than Pinnacle (else DK) on a side "
             "(totals 1.5+): the bettable number hasn't caught up. Tracked on CLV, not a bet by itself.", "",
             f"{note}", "",
             "| Game (ET) | " + " | ".join(cols) + " | Range | Totals (PIN/DK/FD/NOV) | LAG |",
             "|---|" + "---|" * len(cols) + "---|---|---|"]
    for g in games:
        t = datetime.fromisoformat(g["commence_et"])
        cell = lambda c: (f"{float(g[c + '_spread_away']):+g}" if g[c + "_spread_away"] != "" else "—")
        tots = "/".join(str(g[f"{c}_total"]) if g[f"{c}_total"] != "" else "—" for c in ("PIN", "DK", "FD", "NOV"))
        lines.append(f"| {g['away']} @ {g['home']} {t:%a %I:%M %p} | " + " | ".join(cell(c) for c in cols) +
                     f" | {g['spread_range']} | {tots} | {g['lag_flag'] or '—'} |")
    return "\n".join(lines) + "\n"


def write(path, rows, fields=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields or (list(rows[0]) if rows else ["empty"]), extrasaction="ignore")
        w.writeheader(); w.writerows(rows)


def main():
    sports = [s.upper() for s in sys.argv[1:]] or ["NFL", "CFB", "CBB"]
    key = os.environ.get("ODDS_API_KEY", "").strip()
    prev = {}
    if os.path.exists(STATUS):
        try:
            prev = json.load(open(STATUS))
        except Exception:
            pass
    status = {"pulled_et": NOW.isoformat(timespec="minutes"), "source": "The Odds API",
              "books": ",".join(BOOKS), "credits_remaining": prev.get("credits_remaining")}
    if not key:
        status["alert"] = "no ODDS_API_KEY secret in this job's environment"
        sports = []
    remaining = status["credits_remaining"]
    main_slot = NOW.hour == 15                       # 3:29 PM pull = the one that feeds the 3:45 scan
    for sport in sports:
        if remaining is not None and (remaining < MIN_CREDITS["floor"] or
                                      (remaining < MIN_CREDITS["reserve"] and not main_slot)):
            status[sport] = f"skipped: {remaining} credits left (budget guard)"
            continue
        try:
            events, h = fetch(sport, key)
            remaining = int(float(h.get("x-requests-remaining", remaining or 0)))
            status["credits_remaining"], status["credits_used"] = remaining, h.get("x-requests-used")
            status[f"{sport}_cost"] = h.get("x-requests-last")
            rows = rows_for(events)
            write(f"data/books/{NOW:%Y-%m-%d}/{NOW:%H%M}_books_{sport}.csv", rows, LONG)
            g = wide(rows)
            write(f"data/books/latest/{sport}.csv", g)
            have = {b: sum(1 for r in rows if r["book"] == b) for b in BOOKS}
            note = "Books with lines: " + ", ".join(f"{SHORT[b]} {n}" for b, n in have.items())
            with open(f"data/books/latest/board_{sport}.md", "w", encoding="utf-8") as fh:
                fh.write(board(sport, g, note))
            status[sport] = (f"ok {len(g)} games; lag flags {sum(1 for x in g if x['lag_flag'])}; " + note.lower())
        except Exception as e:
            status[sport] = f"error: {e}".replace(key, "***")[:240]
    os.makedirs("data/books", exist_ok=True)
    with open(STATUS, "w") as fh:
        json.dump(status, fh, indent=2)
    print(json.dumps(status, indent=2))
    return 1 if sports and all(str(status.get(s, "")).startswith("error") for s in sports) else 0


if __name__ == "__main__":
    sys.exit(main())
