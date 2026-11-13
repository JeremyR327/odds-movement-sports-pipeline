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
and data/tr_status.json.

Exit codes: 0 = everything pulled; 1 = some pages failed (see tr_status.json);
2 = cookie set but TeamRankings shows the logged-out page -> refresh the secret.
"""
import csv, json, os, re, sys, time, urllib.request
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


def get(url, cookie=None):
    h = {"User-Agent": UA}
    if cookie:
        h["Cookie"] = cookie
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=40) as r:
        body = r.read().decode("utf-8", "replace")
    time.sleep(PAUSE)
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
    for sport, (picks_page, slug, trend_slug) in SPORTS.items():
        jobs = [("picks", f"{BASE}/{picks_page}/", parse_picks),
                ("ratings", f"{BASE}/{slug}/ranking/predictive-by-other", parse_ratings),
                ("ats", f"{BASE}/{trend_slug}/trends/ats_trends/", parse_trend),
                ("ou", f"{BASE}/{trend_slug}/trends/ou_trends/", parse_trend)]
        for kind, url, parse in jobs:
            key = f"tr_{kind}_{sport}"
            try:
                html = get(url, cookie or None)
                rows = parse(html)
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
    if logged_out:
        status["alert"] = "TeamRankings cookie set but pages show logged out: refresh the TEAMRANKINGS_COOKIE secret"
    os.makedirs("data", exist_ok=True)
    with open(os.path.join("data", "tr_status.json"), "w") as f:
        json.dump(status, f, indent=2)
    print(json.dumps(status, indent=2))
    sys.exit(2 if logged_out else (1 if any("error" in str(v) for v in status.values()) else 0))


if __name__ == "__main__":
    main()
