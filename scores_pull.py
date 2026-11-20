#!/usr/bin/env python3
"""Final scores + closing lines for NFL, CFB and NBA, graded per game (no login, stdlib only).

Why: the cloud tasks can't read ESPN themselves (bash is blocked from site.api.espn.com and
WebFetch serves days-old cached copies), so the weekly scorecard couldn't reliably get finals.
This runs on GitHub's servers from the Pipeline loop and writes:

  data/results/<SPORT>/<YYYY-MM-DD>.csv   one row per game on that ET date (rewritten each run
                                          until every game is final): score, state, the
                                          pipeline's week open and close, ESPN's own DK
                                          open/close, margin, total, cover/over vs the close
  data/results/status.json                per sport: games, finals, games still missing a close

Close = the last pipeline lines pull (data/<date>/HHMM_lines_<SPORT>.csv) before kickoff;
ESPN's DK "close" is kept beside it as a cross-check. Open = the first pipeline pull within
WEEK_DAYS before kickoff (ESPN's NFL/CFB "open" is the schedule-release number, months old).
Spreads are from the AWAY team's side, like the lines files.

Usage: python3 scores_pull.py [days_back]    (default 3: yesterday-ish games get re-checked
                                              until ESPN marks them final)
"""
import csv, glob, json, os, sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from espn_lines import BASE, dig, get, num, parse_odds

ET = ZoneInfo("America/New_York")
NOW = datetime.now(ET)
LEAGUES = {
    "NFL": ("football/nfl", ""),
    "CFB": ("football/college-football", "&groups=80&limit=300"),
    "NBA": ("basketball/nba", ""),
}
WEEK_DAYS = {"NFL": 6, "CFB": 6, "NBA": 2}
FIELDS = ["espn_id", "date_et", "start_et", "away", "home", "away_abbr", "home_abbr", "state", "detail",
          "away_score", "home_score", "final", "open_spread", "open_total", "open_at",
          "close_spread", "close_total", "close_ml_away", "close_ml_home", "close_at",
          "espn_open_spread", "espn_close_spread", "espn_open_total", "espn_close_total",
          "home_margin", "total_points", "away_cover_close", "over_close", "updated_et"]


def pipeline_path(sport, espn_id, kick):
    """(open row, close row) from the pipeline's own pulls before kickoff."""
    first = last = None
    lo = kick - timedelta(days=WEEK_DAYS[sport] + 1)
    days = {(kick - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(WEEK_DAYS[sport] + 2)}
    for d in sorted(days):
        for p in sorted(glob.glob(f"data/{d}/[0-9][0-9][0-9][0-9]_lines_{sport}.csv")):
            with open(p, newline="") as f:
                for r in csv.DictReader(f):
                    if r.get("espn_id") != espn_id:
                        continue
                    try:
                        at = datetime.fromisoformat(r["pulled_et"])
                    except Exception:
                        continue
                    if not (lo <= at < kick) or r.get("spread_now") in (None, "") and r.get("total_now") in (None, ""):
                        continue
                    if first is None or at < first[0]:
                        first = (at, r)
                    if last is None or at > last[0]:
                        last = (at, r)
    return first, last


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def grade(sport, ev):
    comp = (ev.get("competitions") or [{}])[0]
    st = dig(comp, "status", "type") or {}
    teams = {c.get("homeAway"): c for c in comp.get("competitors", [])}
    if "home" not in teams or "away" not in teams:
        return None
    a, h = teams["away"], teams["home"]
    kick = datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(ET)
    final = bool(st.get("completed")) and st.get("state") == "post"
    asc, hsc = f(a.get("score")), f(h.get("score"))
    odds = next((x for x in comp.get("odds") or [] if "draft" in (dig(x, "provider", "name") or "").lower()),
                (comp.get("odds") or [{}])[0]) or {}
    eo = parse_odds(odds, dig(a, "team", "abbreviation") or "", dig(h, "team", "abbreviation") or "") if odds else {}
    op, cl = pipeline_path(sport, ev.get("id"), kick)
    row = {"espn_id": ev.get("id"), "date_et": kick.strftime("%Y-%m-%d"), "start_et": kick.strftime("%a %m-%d %I:%M %p"),
           "away": dig(a, "team", "displayName") or "", "home": dig(h, "team", "displayName") or "",
           "away_abbr": dig(a, "team", "abbreviation") or "", "home_abbr": dig(h, "team", "abbreviation") or "",
           "state": st.get("state", ""), "detail": st.get("shortDetail") or st.get("detail", ""),
           "away_score": "" if asc is None or st.get("state") == "pre" else int(asc),
           "home_score": "" if hsc is None or st.get("state") == "pre" else int(hsc),
           "final": int(final),
           "open_spread": op[1].get("spread_now", "") if op else "", "open_total": op[1].get("total_now", "") if op else "",
           "open_at": op[0].isoformat(timespec="minutes") if op else "",
           "close_spread": cl[1].get("spread_now", "") if cl else "", "close_total": cl[1].get("total_now", "") if cl else "",
           "close_ml_away": cl[1].get("ml_away_now", "") if cl else "", "close_ml_home": cl[1].get("ml_home_now", "") if cl else "",
           "close_at": cl[0].isoformat(timespec="minutes") if cl else "",
           "espn_open_spread": eo.get("spread_open", ""), "espn_close_spread": eo.get("spread_now", ""),
           "espn_open_total": eo.get("total_open", ""), "espn_close_total": eo.get("total_now", ""),
           "home_margin": "", "total_points": "", "away_cover_close": "", "over_close": "",
           "updated_et": NOW.isoformat(timespec="minutes")}
    if final and asc is not None and hsc is not None:
        row["home_margin"], row["total_points"] = int(hsc - asc), int(hsc + asc)
        # close: pipeline first, ESPN's DK close as the fallback
        cs = f(row["close_spread"]) if row["close_spread"] != "" else f(row["espn_close_spread"])
        ct = f(row["close_total"]) if row["close_total"] != "" else f(row["espn_close_total"])
        if cs is not None:      # away covers when away margin + away spread > 0
            v = (asc - hsc) + cs
            row["away_cover_close"] = "win" if v > 0 else "loss" if v < 0 else "push"
        if ct is not None:
            v = (asc + hsc) - ct
            row["over_close"] = "win" if v > 0 else "loss" if v < 0 else "push"
    return row


def pull(sport, days_back):
    path, extra = LEAGUES[sport]
    by_date = {}
    for i in range(days_back, -1, -1):
        day = NOW - timedelta(days=i)
        url = f"{BASE}{path}/scoreboard?dates={day:%Y%m%d}{extra}"
        for ev in get(url).get("events", []):
            r = grade(sport, ev)
            if r and r["date_et"] == f"{day:%Y-%m-%d}":      # ESPN's date is UTC-ish; keep ET date only
                by_date.setdefault(r["date_et"], {})[r["espn_id"]] = r
    out = {"games": 0, "final": 0, "no_close": 0, "files": []}
    for d, rows in sorted(by_date.items()):
        os.makedirs(f"data/results/{sport}", exist_ok=True)
        p = f"data/results/{sport}/{d}.csv"
        old = {}
        if os.path.exists(p):           # never overwrite a graded final with a worse read
            with open(p, newline="") as fh:
                old = {r["espn_id"]: r for r in csv.DictReader(fh)}
        for k, r in rows.items():
            if k in old and old[k].get("final") == "1" and r["final"] != 1:
                rows[k] = old[k]
        rows = {**{k: v for k, v in old.items() if k not in rows}, **rows}
        with open(p, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore"); w.writeheader()
            w.writerows(sorted(rows.values(), key=lambda r: (r["start_et"], r["away"])))
        out["files"].append(p)
        out["games"] += len(rows)
        out["final"] += sum(1 for r in rows.values() if str(r["final"]) == "1")
        out["no_close"] += sum(1 for r in rows.values() if str(r["final"]) == "1" and r["close_spread"] in ("", None))
    return out


def main():
    days_back = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    status = {"pulled_et": NOW.isoformat(timespec="minutes"), "source": "ESPN scoreboard + pipeline lines"}
    for sport in LEAGUES:
        try:
            s = pull(sport, days_back)
            status[sport] = (f"ok {s['games']} games, {s['final']} final, "
                             f"{s['no_close']} final without a pipeline close") if s["games"] else "ok 0 games"
        except Exception as e:
            status[sport] = f"error: {e}"[:200]
    os.makedirs("data/results", exist_ok=True)
    with open("data/results/status.json", "w") as fh:
        json.dump(status, fh, indent=2)
    print(json.dumps(status, indent=2))
    return 1 if all(str(status[s]).startswith("error") for s in LEAGUES) else 0


if __name__ == "__main__":
    sys.exit(main())
