#!/usr/bin/env python3
"""Pull TeamRankings picks, power ratings, ATS/O-U trends and team stats.

Runs in GitHub Actions. Reads the TeamRankings login cookie from the
TEAMRANKINGS_COOKIE secret (needed for the current picks grid; ratings, trends
and stats are public). Writes timestamped CSVs under data/YYYY-MM-DD/:
  HHMM_tr_picks_<SPORT>.csv    game winner / ATS / total / ML value picks, stars, win %
  HHMM_tr_ratings_<SPORT>.csv  predictive power ratings
  HHMM_tr_ats_<SPORT>.csv      team ATS records (all games)
  HHMM_tr_ou_<SPORT>.csv       team over/under records (all games)
  HHMM_tr_stats_<SPORT>.csv    selected team stats, long format (one row per team per stat)
NFL, CFB and CBB also get (added Nov 19, 2026):
  HHMM_tr_splits_<SPORT>.csv   ATS records as home / away / favorite / underdog and O-U as home / away
                               (long format: split, market, team, record columns)
  HHMM_tr_ratings_more_<SPORT>.csv  home rating, away rating and strength of schedule (rating_kind column)
  HHMM_tr_proj_<SPORT>.csv     TeamRankings' final-score projection per game (projected score for each
                               team -> projected home margin and total; Vegas-implied score for comparison),
                               for every NFL game, CFB games with both teams TR top-50 and CBB games with
                               both teams TR top-100. Needs the subscriber cookie: logged out, the page
                               shows "Subscribe to view" and the row is marked locked.
and data/tr_status.json.

Exit codes: 0 = everything pulled; 1 = some pages failed (see tr_status.json);
2 = cookie set but TeamRankings shows the logged-out page -> refresh the secret.
"""
import csv, json, os, re, sys, time, urllib.error, urllib.request
from datetime import datetime
from html import unescape
from zoneinfo import ZoneInfo

BASE = "https://www.teamrankings.com"
# Per sport: picks-grid page, slug for ranking/stat pages, slug for trend pages.
SPORTS = {
    "NFL": ("nfl-betting-picks", "nfl", "nfl"),
    "CFB": ("college-football-betting-picks", "college-football", "ncf"),
    "NBA": ("nba-betting-picks", "nba", "nba"),
    "CBB": ("ncaa-basketball-betting-picks", "ncaa-basketball", "ncb"),
}
STATS = {
    "NFL": ["points-per-play", "opponent-points-per-play", "yards-per-play", "opponent-yards-per-play",
            "plays-per-game", "turnover-margin-per-game", "third-down-conversion-pct", "red-zone-scoring-pct"],
    "CFB": ["points-per-play", "opponent-points-per-play", "yards-per-play", "opponent-yards-per-play",
            "plays-per-game"],
    "NBA": ["possessions-per-game", "offensive-efficiency", "defensive-efficiency",
            "effective-field-goal-pct", "opponent-effective-field-goal-pct"],
    "CBB": ["possessions-per-game", "offensive-efficiency", "defensive-efficiency", "effective-field-goal-pct"],
}
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
NOW = datetime.now(ZoneInfo("America/New_York"))
OUTDIR = os.path.join("data", NOW.strftime("%Y-%m-%d"))
STAMP = NOW.strftime("%H%M")
PAUSE = 1.0  # seconds between requests
EXTRA_PAUSE = 2.5   # slower for the added pages (TeamRankings rate-limits bursts)
SPLITS = [("ats", "is_home"), ("ats", "is_away"), ("ats", "is_fav"), ("ats", "is_dog"), ("ou", "is_home"), ("ou", "is_away")]
MORE_RATINGS = [("home", "home-by-other"), ("away", "away-by-other"), ("sos", "schedule-strength-by-other")]
PROJ = {"NFL": (None, 16), "CFB": (50, 15), "CBB": (100, 20)}   # (both teams within TR rank, max games)


class RateLimited(Exception):
    pass


def get(url, cookie=None, pause=PAUSE):
    h = {"User-Agent": UA}
    if cookie:
        h["Cookie"] = cookie
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=40) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            raise RateLimited(f"HTTP {e.code}")
        raise
    time.sleep(pause)
    if re.search(r"rate.?limit|too many requests", body[:3000], flags=re.I):
        raise RateLimited("rate-limit page")
    return body


def text(frag):
    return unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", frag))).strip()


def logged_in(html):
    """Logged-out pages link to /login/ ("Log In") in the header; signed-in pages don't.
    (Checked Nov 12, 2026: with the cookie set, picks were current but the old
    'Log Out'/'My Account' test said logged out.)"""
    return not re.search(r'href="[^"]*teamrankings\.com/login/?"', html)


def main_table(html, cls="datatable"):
    """(headers, rows) of the first <table> whose class contains `cls`; rows keep empty cells."""
    m = re.search(r'<table[^>]*class="[^"]*' + cls + r'[^"]*"[^>]*>(.*?)</table>', html, flags=re.S)
    if not m:
        return [], []
    t = m.group(1)
    head = re.search(r"<thead[^>]*>(.*?)</thead>", t, flags=re.S)
    headers = [text(c) for c in re.findall(r"<th[^>]*>(.*?)</th>", head.group(1), flags=re.S)] if head else []
    body = re.search(r"<tbody[^>]*>(.*?)</tbody>", t, flags=re.S)
    rows = [[text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)]
            for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body.group(1) if body else t, flags=re.S)]
    return headers, [r for r in rows if r]


def parse_picks(html):
    """Picks grid: one row per game; each pick cell carries stars + model probability
    in data-sort="<stars>-<prob%>" (e.g. "3-78.80")."""
    m = re.search(r'<table[^>]*picks-grid-table[^>]*>(.*?)</table>', html, flags=re.S)
    if not m:
        return []
    body = re.search(r"<tbody[^>]*>(.*?)</tbody>", m.group(1), flags=re.S)
    games = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body.group(1) if body else m.group(1), flags=re.S):
        tds = re.findall(r"<td([^>]*)>(.*?)</td>", tr, flags=re.S)
        if len(tds) < 6:
            continue
        rot = re.findall(r"\d+", text(tds[0][1]))
        teams = [text(x) for x in re.split(r"<br\s*/?>", tds[1][1]) if text(x)]
        if len(teams) < 2:
            continue
        link = re.search(r'href="([^"]*/matchup/[^"]*)"', tr)
        row = {"rot_away": rot[0] if rot else "", "rot_home": rot[1] if len(rot) > 1 else "",
               "away": teams[0], "home": teams[1]}
        for key, (attrs, cell) in zip(("winner", "ats", "total", "ml_value"), tds[2:6]):
            ds = re.search(r'data-sort="(\d+)-([\d.]+)"', attrs)
            row[f"{key}_pick"] = text(cell)
            row[f"{key}_stars"] = int(ds.group(1)) if ds else ""
            # Win/cover probability % for winner/ATS/total; for ML value the number is
            # TeamRankings' value score (e.g. 1.98 on ATL +153), not a probability.
            num = f"{key}_score" if key == "ml_value" else f"{key}_prob"
            row[num] = float(ds.group(2)) if ds and float(ds.group(2)) else ""
        row["matchup_url"] = link.group(1) if link else ""
        games.append(row)
    return games


def parse_ratings(html):
    headers, rows = main_table(html)
    out = []
    for r in rows:
        if len(r) < 3:
            continue
        m = re.match(r"(.*?)\s*\((\d+-\d+(?:-\d+)?)\)$", r[1])
        d = {"rank": r[0], "team": m.group(1) if m else r[1], "record": m.group(2) if m else ""}
        for h, v in zip(headers[2:], r[2:]):
            d[re.sub(r"\W+", "_", h.lower()).strip("_")] = v
        out.append(d)
    return out


def parse_trend(html):
    headers, rows = main_table(html)
    keys = [re.sub(r"\W+", "_", h.lower().replace("%", "pct").replace("+/-", "plus_minus")).strip("_")
            for h in headers]
    return [dict(zip(keys, r)) for r in rows if len(r) == len(keys)]


def parse_stat(html, stat):
    """Columns: Rank, Team, <this season>, Last 3, Last 1, Home, Away, <last season>."""
    headers, rows = main_table(html)
    names = ["rank", "team", "season", "last3", "last1", "home", "away", "prev_season"]
    if len(headers) != len(names):
        raise ValueError(f"{stat}: unexpected columns {headers}")
    return [{"stat": stat, "season_label": headers[2], **dict(zip(names, r))} for r in rows if len(r) == len(names)]


def parse_proj(html):
    """'Final Score Projection' table on a matchup page: rows (team, projection, Vegas implied[, actual]).
    Returns [] if the section is missing; projection None where the page says 'Subscribe to view'."""
    i = html.find("Final Score Projection")
    if i < 0:
        return []
    start, end = html.rfind("<table", 0, i), html.find("</table>", i)
    if start < 0 or end < 0:
        return []
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html[start:end], flags=re.S):
        cells = [text(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S)]
        if not cells or "Final Score Projection" in cells[0] or not cells[0]:
            continue
        locked = any("subscribe" in c.lower() for c in cells[1:])
        nums = [float(x) for c in cells[1:] for x in re.findall(r"^\s*(-?\d+(?:\.\d+)?)\s*$", c)]
        if locked:
            out.append({"team": cells[0], "proj": None, "vegas": nums[0] if nums else None, "locked": True})
        elif nums:
            out.append({"team": cells[0], "proj": nums[0], "vegas": nums[1] if len(nums) > 1 else None, "locked": False})
    return out[:2]


def projections(sport, picks, ratings, cookie):
    """One matchup page per selected game (picks grid order = away, home)."""
    top, cap = PROJ[sport]
    rank = {r["team"]: int(r["rank"]) for r in ratings if str(r.get("rank", "")).isdigit()}
    pick = [g for g in picks if g.get("matchup_url") and
            (top is None or (rank.get(g["away"], 999) <= top and rank.get(g["home"], 999) <= top))][:cap]
    rows, locked = [], 0
    for g in pick:
        url = g["matchup_url"] if g["matchup_url"].startswith("http") else BASE + g["matchup_url"]
        p = parse_proj(get(url, cookie, EXTRA_PAUSE))
        if len(p) != 2:
            rows.append({"away": g["away"], "home": g["home"], "matchup_url": url, "status": "no projection table"})
            continue
        a, h = p
        r = {"away": g["away"], "home": g["home"], "matchup_url": url, "page_teams": f"{a['team']} / {h['team']}",
             "away_proj": a["proj"], "home_proj": h["proj"], "vegas_away": a["vegas"], "vegas_home": h["vegas"]}
        if a["locked"] or h["locked"] or a["proj"] is None or h["proj"] is None:
            locked += 1
            r["status"] = "locked (Subscribe to view)"
        else:
            r.update(proj_home_margin=round(h["proj"] - a["proj"], 1), proj_total=round(h["proj"] + a["proj"], 1), status="ok")
        if a["vegas"] is not None and h["vegas"] is not None:
            r.update(vegas_home_margin=round(h["vegas"] - a["vegas"], 1), vegas_total=round(h["vegas"] + a["vegas"], 1))
        rows.append(r)
    return rows, locked


def write(name, rows):
    if not rows:
        return
    os.makedirs(OUTDIR, exist_ok=True)
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with open(os.path.join(OUTDIR, f"{STAMP}_{name}.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)


def main():
    cookie = os.environ.get("TEAMRANKINGS_COOKIE", "").strip()
    pulled = NOW.isoformat(timespec="minutes")
    status, logged_out = {"pulled_et": pulled, "cookie_set": bool(cookie)}, False
    limited = False
    for sport, (picks_page, slug, trend_slug) in SPORTS.items():
        got = {}
        jobs = [("picks", f"{BASE}/{picks_page}/", parse_picks),
                ("ratings", f"{BASE}/{slug}/ranking/predictive-by-other", parse_ratings),
                ("ats", f"{BASE}/{trend_slug}/trends/ats_trends/", parse_trend),
                ("ou", f"{BASE}/{trend_slug}/trends/ou_trends/", parse_trend)]
        for kind, url, parse in jobs:
            key = f"tr_{kind}_{sport}"
            try:
                html = get(url, cookie or None)
                rows = parse(html)
                got[kind] = rows
                write(key, [{"pulled_et": pulled, **r} for r in rows])
                status[key] = f"ok {len(rows)} rows" if rows else "0 rows"
                if kind == "picks":
                    status[f"{key}_logged_in"] = logged_in(html)
                    if cookie and not logged_in(html):
                        logged_out = True
            except Exception as e:
                status[key] = f"error: {e}"
        stats, errs = [], []
        for stat in STATS[sport]:
            try:
                stats += parse_stat(get(f"{BASE}/{slug}/stat/{stat}"), stat)
            except Exception as e:
                errs.append(f"{stat}: {e}")
        write(f"tr_stats_{sport}", [{"pulled_et": pulled, **r} for r in stats])
        status[f"tr_stats_{sport}"] = f"ok {len(stats)} rows" + (f"; errors: {'; '.join(errs)}" if errs else "")
        if sport not in PROJ:
            continue
        # Added pages: slower, and the whole extra block stops for the day on a rate limit.
        for name, fn in (("splits", lambda: [dict(split=sc[3:], market=mk, **r) for mk, sc in SPLITS
                                             for r in parse_trend(get(f"{BASE}/{trend_slug}/trends/{mk}_trends/?sc={sc}", None, EXTRA_PAUSE))]),
                         ("ratings_more", lambda: [dict(rating_kind=k, **r) for k, page in MORE_RATINGS
                                                   for r in parse_ratings(get(f"{BASE}/{slug}/ranking/{page}", None, EXTRA_PAUSE))]),
                         ("proj", None)):
            key = f"tr_{name}_{sport}"
            if limited:
                status[key] = "skipped (TeamRankings rate limit earlier in this run)"
                continue
            try:
                if name == "proj":
                    rows, nlock = projections(sport, got.get("picks", []), got.get("ratings", []), cookie or None)
                    status[key] = f"ok {len(rows)} games" + (f", {nlock} locked (cookie not a subscriber or expired)" if nlock else "")
                else:
                    rows = fn()
                    status[key] = f"ok {len(rows)} rows"
                write(key, [{"pulled_et": pulled, **r} for r in rows])
            except RateLimited as e:
                limited = True
                status[key] = f"rate limited ({e}); extra TeamRankings pages skipped for the rest of this run"
            except Exception as e:
                status[key] = f"error: {e}"[:200]
    if logged_out:
        status["alert"] = "TeamRankings cookie set but pages show logged out: refresh the TEAMRANKINGS_COOKIE secret"
    os.makedirs("data", exist_ok=True)
    with open(os.path.join("data", "tr_status.json"), "w") as f:
        json.dump(status, f, indent=2)
    print(json.dumps(status, indent=2))
    sys.exit(2 if logged_out else (1 if any("error" in str(v) for v in status.values()) else 0))


if __name__ == "__main__":
    main()
