#!/usr/bin/env python3
"""Commit a pull's data and push it without merge conflicts.

Several jobs push to main (the Pipeline loop, the VSiN pull on the Mac, the CBB pull), and
each one used to rewrite data/latest/ before pushing. When two overlapped, `git pull --rebase`
hit conflicts in data/latest/ and the second job's data was never pushed (Nov 13: the 3:29 PM
TeamRankings pull was lost that way).

Now:
  1. commit only the job's own files (everything in data/ except data/latest/; those are
     timestamped per pull, so they don't collide);
  2. pull --rebase (on a conflict in a shared status file, this job's newer copy wins);
  3. rebuild data/latest/ from the merged tree, commit it and push;
  4. if the push is rejected (someone pushed in between), drop the rebuilt commit, pull again,
     rebuild again and retry.

Usage: python3 save_pull.py "<commit label>"     (needs git user.name/email set; Python 3.9+)
"""
import subprocess, sys, time
from datetime import datetime
from zoneinfo import ZoneInfo


def git(*args, check=False):
    print("+ git " + " ".join(args), flush=True)
    r = subprocess.run(("git",) + args)
    if check and r.returncode:
        raise SystemExit(f"git {' '.join(args)} failed")
    return r.returncode


def staged():
    return subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode != 0


def pull():
    if git("pull", "-q", "--rebase", "-X", "theirs", "origin", "main") == 0:
        return True
    git("rebase", "--abort")
    return False


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "Pipeline pull"
    stamp = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M ET")
    git("add", "-A", "data", ":(exclude)data/latest")
    if staged():
        git("commit", "-q", "-m", f"{label} {stamp}", check=True)
    # data/latest/ is rebuilt below from the merged tree, so drop any local edits to it now:
    # unstaged changes there would make `git pull --rebase` refuse to run.
    git("checkout", "-q", "--", "data/latest")
    git("clean", "-fdq", "--", "data/latest")
    for attempt in range(1, 6):
        if not pull():
            time.sleep(5 * attempt)
            continue
        subprocess.run([sys.executable, "publish_gist.py", "--write-dir", "data/latest"])
        git("add", "-A", "data/latest")
        rebuilt = staged()
        if rebuilt:
            git("commit", "-q", "-m", f"Refresh data/latest ({label} {stamp})", check=True)
        if git("push", "-q", "origin", "HEAD:main") == 0:
            print(f"pushed on attempt {attempt}", flush=True)
            return 0
        if rebuilt:
            git("reset", "-q", "--hard", "HEAD~1")    # drop the rebuilt data/latest; rebuild after the next pull
        time.sleep(5 * attempt)
    print("push failed after 5 attempts; the data stays committed locally in this job only", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
