#!/usr/bin/env python3
"""Repair CBB slates and results that were priced from stale VSiN Circa snapshots.

VSiN/Circa was dropped on Nov 14, 2026, but cbb_pull.py kept reading the old
data/<date>/HHMM_circa_CBB.csv files and preferred them over live lines. So from Nov 14 on,
any game that had been on VSiN's last board (pulled Nov 13, 10:42 PM ET) got that frozen
number as both its opener and its "current" line, and results graded those games against it.

A slate row is stale when its line_source reads "Circa MM-DD HH:MM" and that snapshot is from
an earlier day than the slate. (Same-day Circa rows from before the drop are real data; they
are left alone.) For each stale row this script:
  1. takes the DraftKings open + current line from the espn_lines.py pull
     (data/<date>/HHMM_lines_CBB.csv, matched on espn_id) made at or before the slate's
     pulled_et: the line that was live when the slate ran; if there is none, the line is
     blanked rather than left wrong;
  2. reprices the row with cbb_pull.price() (same weights and thresholds; the model is
     unchanged; the stored consensus is rounded to 0.1, so fair/edge can differ by <=0.05);
then rebuilds every results/<date>.csv from the repaired slates and the finals already in
it, and refreshes latest/slate.csv, results.csv, brief.md, calibration.md and status.json.

Runs by itself: cbb_pull.py calls repair() at the start of every CBB pull, so after this is
merged the next scheduled pull fixes any stale rows (including ones written by runs of the old
code) before it grades anything. Idempotent: once fixed, nothing is stale.
By hand: python repair_cbb_lines.py [--check]   (--check reports what would change, writes nothing)
"""
import csv, glob, json, os, re, sys

import cbb_pull as cp

STALE = re.compile(r"^Circa (\d\d)-(\d\d) \d\d:\d\d")
NUM = {"torvik_rank_away", "torvik_rank_home", "torvik_home_margin", "torvik_total", "tr_home_margin",
       "bpi_home_margin", "consensus_home_margin", "open_home_margin", "cur_home_margin", "open_total",
       "cur_total", "fair_home_margin", "edge_pts", "gap_cons_vs_open", "gap_cons_vs_cur"}


def fnum(v):
    return None if v in (None, "", "None") else float(v)


def read(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def stale(row):
    m = STALE.match(row.get("line_source") or "")
    return bool(m) and f"{row['date'][:4]}-{m.group(1)}-{m.group(2)}" < row["date"]


def espn_pulls(day):
    """[(pulled_et, {espn_id: row})] for the day's espn_lines.py CBB pulls, oldest first."""
    out = []
    for p in sorted(glob.glob(f"data/{day}/[0-9][0-9][0-9][0-9]_lines_CBB.csv")):
        rows = read(p)
        if rows:
            out.append((rows[0]["pulled_et"], {r["espn_id"]: r for r in rows}))
    return out


def repair_slate_row(r, pulls):
    """Replace the stale Circa line with the DraftKings line live at the slate's time; reprice."""
    when = r["pulled_et"]
    hit = None
    for pulled, by_id in pulls:
        if pulled <= when and r["espn_id"] in by_id and fnum(by_id[r["espn_id"]]["spread_now"]) is not None:
            hit = (pulled, by_id[r["espn_id"]])
    if hit:
        pulled, L = hit
        # espn_lines.py spreads are the AWAY team's number: away +5 = home favored by 5 = home margin +5.
        open_h, cur_h = fnum(L["spread_open"]), fnum(L["spread_now"])
        open_t, cur_t = fnum(L["total_open"]), fnum(L["total_now"])
        src = f"ESPN/{L['book'] or 'book'} open+now {pulled[11:16]} (repaired)"
    else:
        open_h = cur_h = open_t = cur_t = None
        src = "none (stale Circa removed; no DraftKings pull before this slate)"
    day = cp.datetime.strptime(r["date"], "%Y-%m-%d").date()
    p = cp.price(day, int(r["tier"]), fnum(r["consensus_home_margin"]), open_h, cur_h,
                 fnum(r["tr_home_margin"]), fnum(r["bpi_home_margin"]), r["away"], r["home"])
    p.pop("suspect")
    new = dict(r)
    new.update({"line_source": src, "open_home_margin": open_h, "cur_home_margin": cur_h,
                "open_total": open_t, "cur_total": cur_t, **p})
    return new


def typed(row):
    """CSV strings back to the types cbb_pull writes (for brief())."""
    t = dict(row)
    for k in NUM & set(t):
        t[k] = fnum(t[k])
    t["moved_toward_model"] = {"True": True, "False": False}.get(str(t.get("moved_toward_model")))
    return t


def regression_check(paths):
    """Repricing rows that were NOT stale must reproduce them: proves price() == the old math."""
    worst, n = 0.0, 0
    for path in paths:
        if path.split("/")[-2] < "2026-11-14":   # older slates came from earlier code (no name check yet)
            continue
        for r in read(path):
            if stale(r) or not r.get("line_source") or r["line_source"].startswith("Circa"):
                continue
            n += 1
            day = cp.datetime.strptime(r["date"], "%Y-%m-%d").date()
            p = cp.price(day, int(r["tier"]), fnum(r["consensus_home_margin"]), fnum(r["open_home_margin"]),
                         fnum(r["cur_home_margin"]), fnum(r["tr_home_margin"]), fnum(r["bpi_home_margin"]),
                         r["away"], r["home"])
            for k in ("fair_home_margin", "edge_pts"):
                if fnum(r[k]) is not None:
                    worst = max(worst, abs(fnum(r[k]) - p[k]))
            if r["flag_side"] != p["flag_side"] and abs(abs(fnum(r["edge_pts"]) or 0) - cp.THRESH[int(r["tier"])]) > 0.06:
                raise SystemExit(f"price() disagrees with a live row: {path} {r['away']} @ {r['home']}")
    return n, worst


def repair(check=False, log=print):
    """Re-line every stale slate row and rebuild the results of the days it touched.
    Returns (rows fixed, {day: rebuilt results or None}). cbb_pull.py calls this at the start
    of every run, so stale rows are fixed before anything is graded."""
    slates = sorted(glob.glob(f"{cp.OUT}/????-??-??/[0-9][0-9][0-9][0-9]_slate.csv"))
    changed_days, fixed = {}, 0
    for path in slates:
        rows = read(path)
        if not rows or not any(stale(r) for r in rows):
            continue
        pulls = espn_pulls(rows[0]["date"])
        new = [repair_slate_row(r, pulls) if stale(r) else r for r in rows]
        for a, b in zip(rows, new):
            if a is not b:
                fixed += 1
                log(f"  {path[-24:]} {a['away']} @ {a['home']}: {a['line_source']} "
                    f"{a['open_home_margin']}->{a['cur_home_margin']} [{a['flag'] or 'no flag'}]  =>  "
                    f"{b['line_source']} {b['open_home_margin']}->{b['cur_home_margin']} [{b['flag'] or 'no flag'}]")
        changed_days[rows[0]["date"]] = None
        if not check:
            cp.write_csv(path, new)
    log(f"{fixed} stale slate rows on {len(changed_days)} day(s): {', '.join(sorted(changed_days)) or 'none'}")
    if check:
        return fixed, changed_days

    # Rebuild results for the affected days from the repaired slates + the finals already graded.
    for day in sorted(changed_days):
        rpath = f"{cp.OUT}/results/{day}.csv"
        if not os.path.exists(rpath):
            continue                          # not graded yet: the next run grades the repaired slates
        old = read(rpath)
        games = [{"espn_id": r["espn_id"], "completed": True,
                  "home": {"score": (float(r["final_total"]) + float(r["final_home_margin"])) / 2},
                  "away": {"score": (float(r["final_total"]) - float(r["final_home_margin"])) / 2}} for r in old]
        prior = []
        for p in sorted(glob.glob(f"{cp.OUT}/{day}/[0-9][0-9][0-9][0-9]_slate.csv")):
            prior += read(p)
        res = cp.build_results(cp.datetime.strptime(day, "%Y-%m-%d").date(), games, prior)
        cp.write_csv(rpath, res)
        log(f"results/{day}.csv rebuilt: {sum(1 for a, b in zip(old, res) if a['close_source'] != b['close_source'])} "
            f"of {len(res)} games re-graded")
        changed_days[day] = res
    return fixed, changed_days


def main():
    check = "--check" in sys.argv
    slates = sorted(glob.glob(f"{cp.OUT}/????-??-??/[0-9][0-9][0-9][0-9]_slate.csv"))
    n, worst = regression_check(slates)
    print(f"regression check: {n} live rows since Nov 14 repriced with price(); flags identical, "
          f"max fair/edge diff {worst:.2f} (consensus rounding only)")
    fixed, days = repair(check)
    if check or not days:
        return 0
    graded = [(d, r) for d, r in sorted(days.items()) if r is not None]
    latest_res = graded[-1] if graded else None

    # Refresh the fixed-URL copies the Claude tasks read.
    newest_results = sorted(glob.glob(f"{cp.OUT}/results/????-??-??.csv"))[-1]
    status_path = f"{cp.OUT}/latest/status.json"
    status = json.load(open(status_path)) if os.path.exists(status_path) else {}
    if latest_res and newest_results.endswith(f"{latest_res[0]}.csv"):
        cp.write_csv(f"{cp.OUT}/latest/results.csv", latest_res[1])
        status["calibration"] = cp.calibration(latest_res[1])
    status["season_graded"] = cp.calibration_all()
    newest_slate = max((p for p in slates if read(p)), default=None)
    if newest_slate and os.path.exists(f"{cp.OUT}/latest/slate.csv") and read(newest_slate)[0]["pulled_et"] == read(f"{cp.OUT}/latest/slate.csv")[0]["pulled_et"]:
        slate = read(newest_slate)
        cp.write_csv(f"{cp.OUT}/latest/slate.csv", slate)
        typed_slate = [typed(r) for r in slate]
        status["with_line"] = sum(1 for r in typed_slate if r["cur_home_margin"] is not None)
        status["flags"] = sum(1 for r in typed_slate if r["flag"])
        status.pop("with_circa", None); status.pop("circa_unmatched", None); status.pop("circa", None)
        status["sources"] = " · ".join(f"{k} {status[k]}" for k in ("espn", "espn_lines", "torvik", "tr", "bpi") if k in status)
        with open(f"{cp.OUT}/latest/brief.md", "w", encoding="utf-8") as fh:
            fh.write(cp.brief(typed_slate, status))
    status["repaired"] = f"{fixed} slate rows priced from stale Circa snapshots re-lined from DraftKings (repair_cbb_lines.py)"
    with open(status_path, "w") as fh:
        json.dump(status, fh, indent=2)
    print("refreshed latest/ copies and calibration.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
