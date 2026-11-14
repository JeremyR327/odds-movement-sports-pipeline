#!/usr/bin/env python3
"""Copy the latest pipeline data to a secret (unlisted) GitHub gist.

The nightly Claude analysis runs where it cannot read this private repo, so the
workflows call this after each pull. The gist holds:
  lines_status.json, tr_status.json      latest run status (ESPN lines / TeamRankings)
  lines_<SPORT>.csv                      ALL of today's DraftKings line pulls via ESPN (pulled_et = pull time)
  brief_<SPORT>.md                       one row per upcoming game: open -> first today -> now, move flags
  tr_<kind>_<SPORT>.csv                  newest TeamRankings file of each kind
  README.md                              update time and file list
Raw files: https://gist.githubusercontent.com/<owner>/<GIST_ID>/raw/<file>

`python publish_gist.py --write-dir data/latest` writes the same files into the
repo instead (fixed names, so they can be read from a public repo's raw URLs).

Needs env GIST_TOKEN (token with gist scope only) and GIST_ID. Exits 0 without
doing anything if either is missing, so the pull workflows never fail on it.
Anyone who has the gist URL can read it: keep GIST_ID out of public places.
"""
import glob, json, os, re, sys, urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

SPORTS = ["NFL", "CFB", "NBA", "CBB"]
VSIN_KINDS = ["splits_DK", "splits_CIRCA", "circa"]   # history only: VSiN was dropped Nov 14, 2026
LINE_KINDS = ["lines"]                                   # espn_lines.py: DraftKings open/now via ESPN
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
    for name in ("lines_status.json", "tr_status.json"):
        p = os.path.join("data", name)
        if os.path.exists(p):
            files[name] = open(p, encoding="utf-8").read()
    for sport in SPORTS:
        for kind in LINE_KINDS:
            paths = glob.glob(os.path.join(day, f"[0-9][0-9][0-9][0-9]_{kind}_{sport}.csv"))
            if paths:
                files[f"{kind}_{sport}.csv"] = combine(paths)
        for kind in TR_KINDS:
            # TeamRankings runs less often than VSiN, so take its newest file from any
            # day (folder name + HHMM sort in time order); otherwise the 12:00 AM-10:23 AM
            # window after the first VSiN pull of the day has no TR files at all.
            paths = sorted(glob.glob(os.path.join("data", "????-??-??", f"[0-9][0-9][0-9][0-9]_{kind}_{sport}.csv")))
            if paths:
                files[f"{kind}_{sport}.csv"] = open(paths[-1], encoding="utf-8").read()
    for sport in SPORTS:
        b = brief(files, sport)
        if b:
            files[f"brief_{sport}.md"] = b
    return {k: v for k, v in files.items() if v.strip()}


def _num(s):
    """First number in a cell ('+2.5 -110' -> 2.5, 'PK' -> 0.0, '' -> None)."""
    s = (s or "").strip()
    if s.upper().startswith("PK"):
        return 0.0
    m = re.match(r"[+-]?\d+(?:\.\d+)?", s.replace(",", ""))
    return float(m.group(0)) if m else None


def _rows(text):
    import csv, io
    return list(csv.DictReader(io.StringIO(text))) if text else []


KEYS = {"NFL": (3, 7, 10), "CFB": (3, 7, 14, 17)}
STEAM = {"NFL": 1.5, "CFB": 1.5, "NBA": 1.5, "CBB": 1.5}
TOTAL_MOVE = {"NFL": 1.5, "CFB": 2, "NBA": 2, "CBB": 2}


def _crossed(a, b, keys):
    """Key numbers strictly between |a| and |b| or landed on/off, e.g. -2.5 -> -3.5 crosses 3."""
    if a is None or b is None or a == b or (a > 0) != (b > 0) and a != 0 and b != 0:
        return []
    lo, hi = sorted((abs(a), abs(b)))
    return [k for k in keys if lo < k < hi or (k in (lo, hi) and lo != hi)]


def brief(files, sport):
    """One markdown line per upcoming game: DraftKings spread / total / moneyline as
    open -> first pull today -> now (via ESPN), plus line-move flags. Splits are not in the
    pipeline (VSiN was dropped); the scheduled tasks read free DK splits themselves."""
    rows = _rows(files.get(f"lines_{sport}.csv"))
    if not rows:
        return ""
    pulls = sorted({r["pulled_et"] for r in rows})
    first = {r["espn_id"]: r for r in rows if r["pulled_et"] == pulls[0]}
    seen = {}
    for r in rows:                        # newest row per game (games drop out once they start)
        seen[r["espn_id"]] = r
    last_pull = pulls[-1]
    games = [r for r in seen.values() if r["pulled_et"] == last_pull]
    out = [f"# {sport} lines — DraftKings via ESPN, pull {last_pull[11:16]} ET (first pull today {pulls[0][11:16]} ET)", "",
           "Spread = AWAY team's number. Each cell is open → first pull today → now (DraftKings open is its opener for the game). "
           f"Flags: STEAM = spread moved {STEAM[sport]:g}+ since open (direction = side the market moved toward); "
           f"TOTAL = total moved {TOTAL_MOVE[sport]:g}+; KEY = crossed a key number"
           + (f" ({'/'.join(map(str, KEYS[sport]))})" if sport in KEYS else "") +
           "; FLIP = favorite changed; TODAY = moved 1+ since the first pull today. No splits here: read DK splits from DK Network.", "",
           "| Game | Start (ET) | Spread open→today→now | Total open→today→now | ML away open→now | ML home open→now | Flags |",
           "|---|---|---|---|---|---|---|"]
    f3 = lambda a, b, c, sign: " → ".join("-" if v is None else (f"{v:+g}" if sign else f"{v:g}") for v in (a, b, c))
    ml = lambda a, b: f"{'-' if a is None else f'{a:+g}'} → {'-' if b is None else f'{b:+g}'}"
    for r in games:
        f = first.get(r["espn_id"], r)
        so, sf, sn = _num(r["spread_open"]), _num(f["spread_now"]), _num(r["spread_now"])
        to, tf, tn = _num(r["total_open"]), _num(f["total_now"]), _num(r["total_now"])
        flags = []
        if so is not None and sn is not None:
            mv = sn - so
            if abs(mv) >= STEAM[sport]:
                flags.append(f"STEAM {'away' if mv < 0 else 'home'} {abs(mv):g}")
            if so != 0 and sn != 0 and (so > 0) != (sn > 0):
                flags.append("FLIP")
            ks = _crossed(so, sn, KEYS.get(sport, ()))
            if ks:
                flags.append("KEY " + "/".join(map(str, ks)))
        if to is not None and tn is not None and abs(tn - to) >= TOTAL_MOVE[sport]:
            flags.append(f"TOTAL {'up' if tn > to else 'down'} {abs(tn - to):g}")
        if sf is not None and sn is not None and abs(sn - sf) >= 1:
            flags.append(f"TODAY spr {sn - sf:+g}")
        if tf is not None and tn is not None and abs(tn - tf) >= 1:
            flags.append(f"TODAY tot {tn - tf:+g}")
        game = f"{r['away']} @ {r['home']}" + (" (neutral)" if r.get("status") == "neutral" else "")
        out.append(f"| {game} | {r['start_et']} | {f3(so, sf, sn, True)} | {f3(to, tf, tn, False)} | "
                   f"{ml(_num(r['ml_away_open']), _num(r['ml_away_now']))} | {ml(_num(r['ml_home_open']), _num(r['ml_home_now']))} | "
                   f"{'; '.join(flags) or '-'} |")
    return "\n".join(out) + "\n"


def write_dir(out):
    """Write the same files to a folder (e.g. data/latest) so they can be read at
    fixed URLs from the repo itself, without the gist."""
    day = latest_day_dir()
    if not day:
        print("no data folder yet; skipping")
        return 0
    files = build_files(day)
    os.makedirs(out, exist_ok=True)
    for old in glob.glob(os.path.join(out, "*")):
        if os.path.basename(old) not in files and os.path.isfile(old):
            os.remove(old)
    now = datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="minutes")
    files["README.md"] = f"Latest pipeline data, written {now} ET from `{day}`. Same layout as the gist; see publish_gist.py.\n"
    for name, content in files.items():
        with open(os.path.join(out, name), "w", encoding="utf-8") as f:
            f.write(content)
    print(f"wrote {len(files)} files to {out} from {day}")
    return 0


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--write-dir":
        return write_dir(sys.argv[2])
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
              "Line files hold every pull of the day (see `pulled_et`); TeamRankings files are the newest pull.", ""]
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
