#!/usr/bin/env python3
"""Copy the latest pipeline data to a secret (unlisted) GitHub gist.

The nightly Claude analysis runs where it cannot read this private repo, so the
workflows call this after each pull. The gist holds:
  status.json, tr_status.json            latest run status (VSiN / TeamRankings)
  splits_DK_<SPORT>.csv                  ALL of today's DK split pulls (pulled_et column = pull time)
  splits_CIRCA_<SPORT>.csv               ALL of today's Circa split pulls
  circa_<SPORT>.csv                      ALL of today's Circa line-tracker pulls (open + current)
  tr_<kind>_<SPORT>.csv                  newest TeamRankings file of each kind
  README.md                              update time and file list
Raw files: https://gist.githubusercontent.com/<owner>/<GIST_ID>/raw/<file>

Needs env GIST_TOKEN (token with gist scope only) and GIST_ID. Exits 0 without
doing anything if either is missing, so the pull workflows never fail on it.
Anyone who has the gist URL can read it: keep GIST_ID out of public places.
"""
import glob, json, os, re, sys, urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

SPORTS = ["NFL", "CFB", "NBA", "CBB"]
VSIN_KINDS = ["splits_DK", "splits_CIRCA", "circa"]
TR_KINDS = ["tr_picks", "tr_ratings", "tr_ats", "tr_ou", "tr_stats"]


def latest_day_dir():
    days = sorted(d for d in glob.glob("data/????-??-??") if os.path.isdir(d))
    return days[-1] if days else None


def combine(paths):
    """Concatenate the day's CSVs (oldest first) under one header. Only files with
    the newest file's columns are kept, so files written by an older parser version
    drop out; rows with the raw split-history entity are an old splits bug, so skip them."""
    files = [open(p, encoding="utf-8").read().splitlines() for p in sorted(paths)]
    files = [f for f in files if f]
    if not files:
        return ""
    header = files[-1][0]
    out = [header]
    for lines in files:
        if lines[0] == header:
            out.extend(l for l in lines[1:] if "&#8634;" not in l)
    return "\n".join(out) + "\n"


def build_files(day):
    files = {}
    for name in ("status.json", "tr_status.json"):
        p = os.path.join("data", name)
        if os.path.exists(p):
            files[name] = open(p, encoding="utf-8").read()
    for sport in SPORTS:
        for kind in VSIN_KINDS:
            paths = glob.glob(os.path.join(day, f"[0-9][0-9][0-9][0-9]_{kind}_{sport}.csv"))
            if paths:
                files[f"{kind}_{sport}.csv"] = combine(paths)
        for kind in TR_KINDS:
            paths = sorted(glob.glob(os.path.join(day, f"[0-9][0-9][0-9][0-9]_{kind}_{sport}.csv")))
            if paths:
                files[f"{kind}_{sport}.csv"] = open(paths[-1], encoding="utf-8").read()
    return {k: v for k, v in files.items() if v.strip()}


def main():
    token, gist_id = os.environ.get("GIST_TOKEN", "").strip(), os.environ.get("GIST_ID", "").strip()
    if not token or not gist_id:
        print("GIST_TOKEN or GIST_ID not set; skipping gist publish")
        return 0
    if not re.fullmatch(r"[0-9a-f]{20,40}", gist_id):
        print("GIST_ID does not look like a gist id; skipping")
        return 1
    day = latest_day_dir()
    if not day:
        print("no data folder yet; skipping")
        return 0
    files = build_files(day)
    now = datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="minutes")
    readme = [f"# Pipeline data (latest)", "", f"Updated {now} ET from `{day}`.", "",
              "VSiN files hold every pull of the day (see `pulled_et`); TeamRankings files are the newest pull.", ""]
    readme += [f"- `{k}` ({v.count(chr(10)) - 1} rows)" if k.endswith(".csv") else f"- `{k}`" for k, v in sorted(files.items())]
    files["README.md"] = "\n".join(readme) + "\n"
    body = json.dumps({"files": {k: {"content": v} for k, v in files.items()}}).encode()
    req = urllib.request.Request(f"https://api.github.com/gists/{gist_id}", data=body, method="PATCH", headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "odds-pipeline-gist"})
    with urllib.request.urlopen(req, timeout=60) as r:
        print(f"gist updated: HTTP {r.status}, {len(files)} files from {day}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
