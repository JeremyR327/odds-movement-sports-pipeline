#!/usr/bin/env python3
"""Run the pulls on a clock inside one long GitHub Actions job.

GitHub's own cron schedule never fired for this repo, so .github/workflows/loop.yml
runs this script for ~5.5 hours and then starts the next loop run itself.

  VSiN pull (vsin_pull.py):           :09 and :39 past each hour, 9 AM to midnight ET
  TeamRankings pull (teamrankings_pull.py): 10:23 AM, 3:23 PM and 6:23 PM ET

After each pull it refreshes data/latest/ (publish_gist.py --write-dir), commits
and pushes. A failed pull or push is logged and the loop carries on.
Set LOOP_MINUTES to change how long one run lasts (default 330).
"""
import os, subprocess, sys, time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
VSIN_MINUTES = (9, 39)
VSIN_HOURS = set(range(9, 24)) | {0}          # 9 AM through the 12:xx AM pulls
TR_TIMES = {(10, 23), (15, 23), (18, 23)}
RUN_FOR = timedelta(minutes=int(os.environ.get("LOOP_MINUTES", "330")))


def slots_after(now):
    """Next scheduled (time, kind) after `now`, scanning minute by minute (cheap: <= 1 day)."""
    t = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(24 * 60 + 1):
        kinds = []
        if t.minute in VSIN_MINUTES and t.hour in VSIN_HOURS:
            kinds.append("vsin")
        if (t.hour, t.minute) in TR_TIMES:
            kinds.append("tr")
        if kinds:
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
        save("Pipeline pull" if len(kinds) > 1 else ("VSiN pull" if kinds == ["vsin"] else "TeamRankings pull"))


if __name__ == "__main__":
    sys.exit(main())
