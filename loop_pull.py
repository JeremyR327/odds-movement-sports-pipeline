#!/usr/bin/env python3
"""Run the pulls on a clock inside one long GitHub Actions job.

GitHub's own cron schedule never fired for this repo, so .github/workflows/loop.yml
runs this script for ~5.5 hours and then starts the next loop run itself.

Pulls are timed to feed the scheduled Claude tasks (all ET). VSiN was dropped on Nov 14, 2026
(it doesn't allow scripted access); lines now come from ESPN's public scoreboard feed
(DraftKings open + current, espn_lines.py), which runs here on GitHub's servers. Every lines
pull is followed by dk_splits.py (DK Network handle/bets for every NFL and CFB game, joined to
those lines, with the rubric flags; written to data/splits/latest/).
  9:09 AM daily          lines: morning baseline for the day's line path
  9:59 AM Sat/Sun        lines: for the 10:13 AM weekend final check
  12:39 PM daily         lines: midday point on the path
  3:29 PM daily          lines + TeamRankings: for the 3:45 PM NFL & CFB scan
  5:39 PM daily          lines: for the 5:52 PM evening analysis
  7:44 PM daily          lines + CBB: last read before the 9 PM tips
  10:41 AM, 1:44 PM, 3:29 PM, 5:44 PM, 7:44 PM, 10:41 PM  CBB model slate (cbb_pull.py). The extra
                         afternoon/evening snapshots give every tip window a pre-tip line + splits read
                         (the last snapshot before tip is the close used for grading).
Edit SLOTS below to change them.

After each pull it refreshes data/latest/ (publish_gist.py --write-dir), commits
and pushes. A failed pull or push is logged and the loop carries on.
Set LOOP_MINUTES to change how long one run lasts (default 330).
"""
import glob, os, shutil, subprocess, sys, time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
# (hour, minute, weekdays or None for every day, kinds); weekday 5 = Sat, 6 = Sun
SLOTS = [
    (9, 9, None, ["lines"]),
    (9, 59, {5, 6}, ["lines"]),
    (12, 39, None, ["lines"]),
    (13, 44, None, ["cbb"]),        # CBB snapshot before the early-afternoon tips (weekend noon-3 PM games)
    (15, 29, None, ["lines", "tr", "cbb"]),   # + CBB snapshot before 4-6 PM tips
    (17, 39, None, ["lines"]),
    (10, 41, None, ["cbb"]),
    (17, 44, None, ["cbb"]),        # after the 5:39 lines pull; read by the 5:57 PM CBB pre-tip task
    (19, 44, None, ["lines", "cbb"]),  # last read before the 9 PM tips (lines + DK splits + CBB)
    (22, 41, None, ["lines", "cbb"]),  # late games and closing lines for the next morning's grading
]
RUN_FOR = timedelta(minutes=int(os.environ.get("LOOP_MINUTES", "330")))


def slots_after(now):
    """Next scheduled (time, kinds) after `now`, scanning minute by minute (cheap: <= 2 days)."""
    t = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(2 * 24 * 60 + 1):
        for hour, minute, days, kinds in SLOTS:
            if (t.hour, t.minute) == (hour, minute) and (days is None or t.weekday() in days):
                return t, kinds
        t += timedelta(minutes=1)
    raise RuntimeError("no slot found")


def sh(*cmd):
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd).returncode


# WebFetch (the cloud tasks' reader) caches a fixed URL for days and ignores ?t=, so a task asking
# for data/splits/latest/status.json can get last week's copy. Each slot also writes the small
# status/brief files to a path that is new every pull: data/snap/<date>/<HHMM of the slot>/.
SNAP = {"data/splits/latest/status.json": "splits_status.json", "data/cbb/latest/status.json": "cbb_status.json",
        "data/cbb/latest/brief.md": "cbb_brief.md", "data/cbb/latest/calibration.md": "cbb_calibration.md",
        "data/lines_status.json": "lines_status.json", "data/tr_status.json": "tr_status.json"}


def snapshot(when, kinds):
    out = os.path.join("data", "snap", when.strftime("%Y-%m-%d"), when.strftime("%H%M"))
    os.makedirs(out, exist_ok=True)
    srcs = dict(SNAP)
    for p in glob.glob("data/splits/latest/brief_*.md"):
        srcs[p] = "splits_" + os.path.basename(p)
    n = 0
    for src, name in srcs.items():
        fresh = os.path.exists(src) and os.path.getmtime(src) >= when.timestamp() - 60
        if fresh:                      # only files this slot actually rewrote
            shutil.copyfile(src, os.path.join(out, name)); n += 1
    with open(os.path.join(out, "README.md"), "w") as f:
        f.write(f"Snapshot of slot {when:%Y-%m-%d %H:%M} ET ({'+'.join(kinds)}): {n} files.\n")


def save(label):
    """Commit + push via save_pull.py: own files first, then rebuild data/latest/ on top of
    the newest main, so overlapping jobs can't conflict (see save_pull.py)."""
    sh(sys.executable, "save_pull.py", label)


def main():
    deadline = datetime.now(ET) + RUN_FOR
    print(f"loop until {deadline:%H:%M} ET", flush=True)
    while True:
        when, kinds = slots_after(datetime.now(ET))
        if when > deadline:
            # Sleep out the rest of this run before handing off, so overnight gaps
            # don't turn into a burst of back-to-back short runs.
            rest = (deadline - datetime.now(ET)).total_seconds()
            print(f"next slot {when:%H:%M} ET is after this run ends; sleeping {max(rest, 0) / 60:.0f} min, then handing off", flush=True)
            time.sleep(max(0, rest))
            return 0
        wait = (when - datetime.now(ET)).total_seconds()
        print(f"sleeping {wait / 60:.0f} min until {when:%H:%M} ET for {'+'.join(kinds)}", flush=True)
        time.sleep(max(0, wait))
        if "lines" in kinds:
            sh(sys.executable, "espn_lines.py")
            sh(sys.executable, "dk_splits.py")       # DK Network splits for every NFL/CFB game, joined to these lines
        if "tr" in kinds:
            sh(sys.executable, "teamrankings_pull.py")
        if "cbb" in kinds:
            sh(sys.executable, "cbb_pull.py")        # exit 2 = no slate possible; logged, loop continues
        try:
            snapshot(when, kinds)
        except Exception as e:
            print(f"snapshot failed: {e}", flush=True)
        names = {"lines": "Lines pull", "tr": "TeamRankings pull", "cbb": "CBB pull"}
        save("Pipeline pull" if len(kinds) > 1 else names[kinds[0]])


if __name__ == "__main__":
    sys.exit(main())
