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


def _by_game(rows):
    """{(away, home): row} for the newest pull, and the same for the first pull of the day."""
    if not rows:
        return {}, {}
    pulls = sorted({r["pulled_et"] for r in rows})
    first = {(r["away"], r["home"]): r for r in rows if r["pulled_et"] == pulls[0]}
    last = {(r["away"], r["home"]): r for r in rows if r["pulled_et"] == pulls[-1]}
    return last, first


def _pct(r, side, kind):
    """'bets/handle' for one side, e.g. '23/12'."""
    if not r:
        return "-"
    b, h = _num(r.get(f"{side}_{kind}_bets")), _num(r.get(f"{side}_{kind}_handle"))
    return "-" if b is None or h is None else f"{b:.0f}/{h:.0f}"


def brief(files, sport):
    """One markdown line per game: Circa open->now, DK/Circa splits (away side, bets/handle %),
    DK first pull of the day, and rubric flags. Small enough to read reliably by WebFetch."""
    dk, dk_first = _by_game(_rows(files.get(f"splits_DK_{sport}.csv")))
    ci, _ = _by_game(_rows(files.get(f"splits_CIRCA_{sport}.csv")))
    ln, _ = _by_game(_rows(files.get(f"circa_{sport}.csv")))
    if not dk and not ln:
        return ""
    stamp = next(iter(dk.values()))["pulled_et"][11:16] if dk else "?"
    first_stamp = next(iter(dk_first.values()))["pulled_et"][11:16] if dk_first else "?"
    out = [f"# {sport} brief — DK/Circa pull {stamp} ET (DK first pull {first_stamp} ET)", "",
           "Splits are AWAY side as bets%/handle% (home = 100 minus). Spreads are the away team's. "
           "Flags: PUB = 65%+ of DK bets on one side; SHARP DK = handle minus bets >= +15, SHARP CI = >= +10 (Circa); "
           "RLM = Circa spread moved toward the side with under 50% of DK bets. 0/0 and 100/100 cells and thin Circa samples (0/50/100) are not flagged.", "",
           "| Game | Tip | Circa spread open→now | Circa total open→now | DK spr | DK spr first | Circa spr | DK over | Circa over | DK ML | Flags |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    order = list(ln) + [k for k in dk if k not in ln]  # line-tracker order is the page's date/tip order
    for key in order:
        d, f, c, l = dk.get(key), dk_first.get(key), ci.get(key), ln.get(key)
        o_sp, n_sp = (_num(l.get("circa_open_away_spread")), _num(l.get("circa_away_spread"))) if l else (None, None)
        o_to, n_to = (_num(l.get("circa_open_total")), _num(l.get("circa_total"))) if l else (None, None)
        flags = []
        if d:
            ab, ah = _num(d.get("away_sp_bets")), _num(d.get("away_sp_handle"))
            if ab is not None and ah is not None and not (ab in (0, 100) and ah in (0, 100)):  # 0/0, 100/100 = feed artifacts
                if ab >= 65 or ab <= 35:
                    flags.append(f"PUB {'away' if ab >= 65 else 'home'} {max(ab, 100 - ab):.0f}%")
                if ah - ab >= 15 or ab - ah >= 15:
                    flags.append(f"SHARP DK {'away' if ah > ab else 'home'} +{abs(ah - ab):.0f}")
                if o_sp is not None and n_sp is not None and o_sp != n_sp:
                    toward_away = n_sp < o_sp  # away spread got smaller = market moved toward away
                    if (toward_away and ab < 50) or (not toward_away and ab > 50):
                        flags.append(f"RLM {'away' if toward_away else 'home'}")
            tb, th = _num(d.get("away_ov_bets")), _num(d.get("away_ov_handle"))
            if tb is not None and th is not None and not (tb in (0, 100) and th in (0, 100)) and abs(th - tb) >= 15:
                flags.append(f"SHARP DK {'over' if th > tb else 'under'} +{abs(th - tb):.0f}")
        if c:
            cb, chh = _num(c.get("away_sp_bets")), _num(c.get("away_sp_handle"))
            if cb is not None and chh is not None and cb not in (0, 50, 100) and abs(chh - cb) >= 10:
                flags.append(f"SHARP CI {'away' if chh > cb else 'home'} +{abs(chh - cb):.0f}")
        fmt = lambda a, b: "-" if a is None and b is None else f"{'' if a is None else f'{a:+g}'}→{'' if b is None else f'{b:+g}'}"
        fmt_t = lambda a, b: "-" if a is None and b is None else f"{'' if a is None else f'{a:g}'}→{'' if b is None else f'{b:g}'}"
        when = f"{l.get('date', '')} {l.get('tip', '')}".strip() if l else (d.get("day", "") if d else "")
        out.append(f"| {key[0]} @ {key[1]} | {when} | {fmt(o_sp, n_sp)} | {fmt_t(o_to, n_to)} | "
                   f"{_pct(d, 'away', 'sp')} | {_pct(f, 'away', 'sp')} | {_pct(c, 'away', 'sp')} | "
                   f"{_pct(d, 'away', 'ov')} | {_pct(c, 'away', 'ov')} | {_pct(d, 'away', 'ml')} | {'; '.join(flags) or '-'} |")
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
