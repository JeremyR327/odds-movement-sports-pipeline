#!/usr/bin/env python3
"""Pull VSiN Pro DK + Circa betting splits and the public Circa line tracker.

Runs in GitHub Actions. Reads the VSiN login cookie from the VSIN_COOKIE secret.
Writes timestamped CSVs under data/YYYY-MM-DD/ so repeated runs show line and
split movement (and which book moved first).

Exit codes: 0 = everything pulled; 1 = some sources failed (see status.json);
2 = VSiN cookie missing/expired (paywall) -> refresh the secret.
"""
import csv, json, os, re, sys, urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

SPORTS = ["NFL", "CFB", "NBA", "CBB"]          # VSiN sport codes (CBB to verify on first run)
SPLITS = "https://data.vsin.com/betting-splits/?source={src}&sport={sport}"
TRACKER = {                                     # public pages; NFL confirmed, others to verify
    "NFL": "https://data.vsin.com/nfl/vegas-odds-linetracker/",
    "CFB": "https://data.vsin.com/college-football/vegas-odds-linetracker/",
    "NBA": "https://data.vsin.com/nba/vegas-odds-linetracker/",
    "CBB": "https://data.vsin.com/college-basketball/vegas-odds-linetracker/",
}
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
NOW = datetime.now(ZoneInfo("America/New_York"))
OUTDIR = os.path.join("data", NOW.strftime("%Y-%m-%d"))
STAMP = NOW.strftime("%H%M")


def get(url, cookie=None):
    h = {"User-Agent": UA}
    if cookie:
        h["Cookie"] = cookie
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def table_rows(html):
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S):
        cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip()
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S)]
        cells = [c for c in cells if c != ""]
        if cells:
            out.append(cells)
    return out


def pct(s):
    m = re.search(r"-?\d+(\.\d+)?", s or "")
    return float(m.group(0)) if m else None


def parse_splits(html):
    """Pairs of team rows: team, spread, handle%, bets%, total, handle%, bets%, ML, handle%, bets%."""
    games, day, pend = [], "", None
    for c in table_rows(html):
        if re.match(r"^(CFB|NFL|NBA|CBB|NCAAB|CBK) - ", c[0]):
            day, pend = c[0], None
            continue
        q = c[1:] if (c[0] == "↺" or re.fullmatch(r"\d+", c[0])) else c
        if len(q) < 10:
            continue
        t = {"team": re.sub(r"^\(\d+\)\s*", "", q[0]), "spread": q[1], "sp_handle": pct(q[2]), "sp_bets": pct(q[3]),
             "total": q[4], "ov_handle": pct(q[5]), "ov_bets": pct(q[6]),
             "ml": q[7], "ml_handle": pct(q[8]), "ml_bets": pct(q[9])}
        if pend is None:
            pend = t
        else:
            games.append((day, pend, t)); pend = None
    return games


def parse_tracker(html):
    """OPEN row (Circa open) + away/home rows (Circa current is the first book column)."""
    rows, games, seen, in_second = table_rows(html), [], set(), False
    for i, c in enumerate(rows):
        # Each date block lists Circa's group of books first, then a second header
        # (Westgate | Stations | South Point | Wynn) that repeats the same games.
        if any(x.lower().startswith("westgate") for x in c[:3]):
            in_second = True
            continue
        if any(x.upper() == "CIRCA" for x in c[:3]):
            in_second = False
            continue
        if in_second:
            continue
        if "OPEN" in c[0] and i + 2 < len(rows):
            a, h = rows[i + 1], rows[i + 2]
            if len(c) < 4 or len(a) < 4:
                continue
            if (a[0], h[0]) in seen:
                continue
            seen.add((a[0], h[0]))
            tip = re.search(r"\d+:\d+ [AP]M", c[0])
            games.append({"tip": tip.group(0) if tip else "", "away": a[0], "home": h[0],
                          "circa_open_away_spread": c[1], "circa_open_away_ml": c[2], "circa_open_total": c[3],
                          "circa_away_spread": a[1], "circa_away_ml": a[2], "circa_total": a[3],
                          "circa_home_spread": h[1], "circa_home_ml": h[2]})
    return games


def write(name, rows):
    if not rows:
        return
    os.makedirs(OUTDIR, exist_ok=True)
    path = os.path.join(OUTDIR, f"{STAMP}_{name}.csv")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def main():
    cookie = os.environ.get("VSIN_COOKIE", "").strip()
    status, paywalled = {"pulled_et": NOW.isoformat(timespec="minutes")}, False
    for sport in SPORTS:
        for src in ("DK", "CIRCA"):
            key = f"splits_{src}_{sport}"
            try:
                g = parse_splits(get(SPLITS.format(src=src, sport=sport), cookie or None))
                rows = [{"pulled_et": status["pulled_et"], "day": d, "away": a["team"], "home": h["team"],
                         **{f"away_{k}": v for k, v in a.items() if k != "team"},
                         **{f"home_{k}": v for k, v in h.items() if k != "team"}} for d, a, h in g]
                write(key, rows)
                status[key] = f"ok {len(rows)} games" if rows else "0 games (paywall or empty)"
            except Exception as e:
                status[key] = f"error: {e}"
        try:
            t = parse_tracker(get(TRACKER[sport]))
            write(f"circa_{sport}", [{"pulled_et": status["pulled_et"], **r} for r in t])
            status[f"circa_{sport}"] = f"ok {len(t)} games"
        except Exception as e:
            status[f"circa_{sport}"] = f"error: {e}"
    # Paywall check: if no sport returned DK splits, the cookie is missing or expired.
    if not any(v.startswith("ok") for k, v in status.items() if k.startswith("splits_DK")):
        paywalled = True
        status["alert"] = "VSiN cookie missing or expired: refresh the VSIN_COOKIE secret"
    os.makedirs("data", exist_ok=True)
    with open(os.path.join("data", "status.json"), "w") as f:
        json.dump(status, f, indent=2)
    print(json.dumps(status, indent=2))
    sys.exit(2 if paywalled else (1 if any("error" in str(v) for v in status.values()) else 0))


if __name__ == "__main__":
    main()
