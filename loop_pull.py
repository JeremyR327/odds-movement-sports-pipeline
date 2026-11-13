#!/usr/bin/env python3
"""Run the pulls on a clock inside one long GitHub Actions job.

GitHub's own cron schedule never fired for this repo, so .github/workflows/loop.yml
runs this script for ~5.5 hours and then starts the next loop run itself.

Pulls are timed to feed the scheduled Claude tasks (all ET):
  9:09 AM daily          VSiN: morning baseline for the day's split/line path
  9:59 AM Sat/Sun        VSiN: for the 10:13 AM weekend final check
  3:29 PM daily          VSiN + TeamRankings: for the 3:45 PM NFL & CFB scan
  5:39 PM daily          VSiN: for the 5:52 PM evening analysis
  10:41 AM, 5:44 PM, 10:41 PM  CBB model slate (cbb_pull.py) for the CBB morning scan (10:57 AM)
                         and pre-tip (5:57 PM) tasks; the late run logs closing lines
Edit SLOTS below to change them.

After each pull it refreshes data/latest/ (publish_gist.py --write-dir), commits
and pushes. A failed pull or push is logged and the loop carries on.
Set LOOP_MINUTES to change how long one run lasts (default 330).
"""
import os, subprocess, sys, time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
# (hour, minute, weekdays or None for every day, kinds); weekday 5 = Sat, 6 = Sun
SLOTS = [
    (9, 9, None, ["vsin"]),
    (9, 59, {5, 6}, ["vsin"]),
    (15, 29, None, ["vsin", "tr"]),
    (17, 39, None, ["vsin"]),
    (10, 41, None, ["cbb"]),
    (17, 44, None, ["cbb"]),        # after the 5:39 VSiN pull; read by the 5:57 PM CBB pre-tip task
    (22, 41, None, ["cbb"]),        # late games and closing lines for the next morning's grading
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


def save(label):
    sh(sys.executable, "publish_gist.py", "--write-dir", "data/latest")
    sh("git", "add", "data")
    if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode == 0:
        print("nothing to commit", flush=True)
        return
    sh("git", "commit", "-q", "-m", f"{label} {datetime.now(ET):%Y-%m-%d %H:%M} ET")
    for attempt in range(3):
        if sh("git", "pull", "-q", "--rebase", "origin", "main") == 0 and sh("git", "push", "-q") == 0:
            return
        time.sleep(10 * (attempt + 1))
    print("push failed 3 times; will retry with the next pull", flush=True)


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
        if "vsin" in kinds:
            sh(sys.executable, "vsin_pull.py")       # exit 1/2 = some sources failed / cookie expired; keep going
        if "tr" in kinds:
            sh(sys.executable, "teamrankings_pull.py")
        if "cbb" in kinds:
            sh(sys.executable, "cbb_pull.py")        # exit 2 = no slate possible; logged, loop continues
        names = {"vsin": "VSiN pull", "tr": "TeamRankings pull", "cbb": "CBB pull"}
        save("Pipeline pull" if len(kinds) > 1 else names[kinds[0]])


if __name__ == "__main__":
    sys.exit(main())
