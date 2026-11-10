#!/usr/bin/env python3
"""CBB slate pull: model aggregate + Circa line movement.

Separate from the NBA/NFL/CFB ledger. Writes one CSV row per game on the slate
(bet or not) so model weights and thresholds can be fit later.

Sources (all public; the cloud environment must allow these domains):
  - Torvik team ratings CSV   barttorvik.com/<season>_team_results.csv
  - ESPN BPI team table        www.espn.com/mens-college-basketball/bpi   (optional)
  - Circa open/current lines   data.vsin.com/college-basketball/vegas-odds-linetracker/  (URL to verify)

Usage:  python3 cbb_pull.py --season 2027 --date 2026-11-07 --out slate_2026-11-07.csv
Exit codes: 0 ok, 2 a required source failed (the run must say so, never fill gaps).
"""
import argparse, csv, difflib, io, json, re, sys, urllib.request
from datetime import datetime, timezone

UA = {"User-Agent": "Mozilla/5.0 (cbb-ledger script)"}
HCA = 3.0                      # home-court points; refit later
W = {"torvik": 0.5, "bpi": 0.3, "internal": 0.2}   # starting weights (ledger: Model weights)
ALIASES = {}                   # vsin name -> torvik name; grows as mismatches appear


def get(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


# ---------- Torvik ----------
def torvik_ratings(season):
    """Return {team: {adjoe, adjde, adjt}} from Torvik's public team CSV."""
    text = get(f"https://barttorvik.com/{season}_team_results.csv")
    rows = list(csv.reader(io.StringIO(text)))
    head = [h.strip().lower() for h in rows[0]]
    if "team" not in head or "adjoe" not in head:
        raise RuntimeError("Torvik CSV header changed: " + ",".join(head[:8]))
    i_t, i_o, i_d, i_tp = head.index("team"), head.index("adjoe"), head.index("adjde"), head.index("adjt")
    out = {}
    for r in rows[1:]:
        try:
            out[r[i_t].strip()] = {"adjoe": float(r[i_o]), "adjde": float(r[i_d]), "adjt": float(r[i_tp])}
        except (ValueError, IndexError):
            continue
    if len(out) < 300:
        raise RuntimeError(f"Torvik CSV only parsed {len(out)} teams")
    return out


def torvik_predict(a, h, R, neutral=False):
    """KenPom-style: possessions from tempos, points from O vs D relative to D-I average."""
    avg_eff = sum(t["adjoe"] for t in R.values()) / len(R)
    avg_tmp = sum(t["adjt"] for t in R.values()) / len(R)
    poss = R[a]["adjt"] * R[h]["adjt"] / avg_tmp
    pa = R[a]["adjoe"] * R[h]["adjde"] / avg_eff * poss / 100
    ph = R[h]["adjoe"] * R[a]["adjde"] / avg_eff * poss / 100
    hca = 0 if neutral else HCA
    return {"home_margin": round(ph - pa + hca, 1), "total": round(pa + ph, 1)}


# ---------- ESPN BPI (optional) ----------
def bpi_ratings():
    """BPI = points above an average team per 70 possessions. Optional input."""
    html = get("https://www.espn.com/mens-college-basketball/bpi")
    names = re.findall(r'"displayName":"([^"]+)"', html)
    vals = re.findall(r'"bpi":\s*"?(-?\d+\.\d+)', html)
    if not names or len(names) != len(vals):
        raise RuntimeError("BPI page layout not parsed")
    return dict(zip(names, map(float, vals)))


# ---------- Circa via VSiN line tracker ----------
def circa_lines(url):
    """Parse OPEN row + away/home rows: Circa is the first book column."""
    html = get(url)
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S)
    cells = [[re.sub(r"<[^>]+>|\s+", " ", c).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, flags=re.S)] for r in rows]
    games = []
    for i, c in enumerate(cells):
        if c and "OPEN" in c[0] and i + 2 < len(cells):
            a, h = cells[i + 1], cells[i + 2]
            if "Verifying" in html[:500] or len(a) < 4:
                continue
            num = lambda s: (re.match(r"[+-]?\d+(\.\d+)?|PK", s or "") or [None])[0]
            games.append({
                "tip": (re.search(r"\d+:\d+ [AP]M", c[0]) or [""])[0],
                "away": a[0], "home": h[0],
                "open_away_spread": num(c[1]), "open_total": num(c[3]),
                "cur_away_spread": num(a[1]), "cur_total": num(a[3]),
            })
    if not games:
        raise RuntimeError("No Circa CBB games parsed (page blocked, empty, or layout changed)")
    return games


def match(name, pool):
    if name in ALIASES:
        return ALIASES[name]
    base = re.sub(r"\(\d+\)", "", name).strip()
    words = base.split()
    pset = set(pool)
    # VSiN appends mascots ("Duke Blue Devils"); Torvik uses school only ("Duke", "Michigan St.")
    for k in range(len(words), 0, -1):
        for cand in (" ".join(words[:k]), " ".join(words[:k]).replace("State", "St.")):
            if cand in pset:
                return cand
    hit = difflib.get_close_matches(base.replace("State", "St."), pool, n=1, cutoff=0.8)
    return hit[0] if hit else None


def spread_num(s):
    if s in (None, ""): return None
    return 0.0 if s == "PK" else float(s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default="2027")
    ap.add_argument("--date", required=True)
    ap.add_argument("--lines-url", default="https://data.vsin.com/college-basketball/vegas-odds-linetracker/")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    status, ts = {}, datetime.now(timezone.utc).isoformat(timespec="minutes")

    try:
        R = torvik_ratings(args.season); status["torvik"] = f"ok {len(R)} teams"
    except Exception as e:
        print(json.dumps({"fatal": f"Torvik failed: {e}"})); sys.exit(2)
    try:
        B = bpi_ratings(); status["bpi"] = f"ok {len(B)} teams"
    except Exception as e:
        B = {}; status["bpi"] = f"skipped: {e}"
    try:
        G = circa_lines(args.lines_url); status["circa"] = f"ok {len(G)} games"
    except Exception as e:
        print(json.dumps({"fatal": f"Circa lines failed: {e}", **status})); sys.exit(2)

    out, unmatched = [], []
    for g in G:
        ta, th = match(g["away"], list(R)), match(g["home"], list(R))
        if not ta or not th:
            unmatched.append(f'{g["away"]}@{g["home"]}'); continue
        tv = torvik_predict(ta, th, R)
        ba, bh = match(g["away"], list(B)) if B else None, match(g["home"], list(B)) if B else None
        bpi_m = round(B[bh] - B[ba] + HCA, 1) if ba and bh else None
        internal_m = tv["home_margin"]   # placeholder until injury/minutes + matchup layer is built
        parts = [(W["torvik"], tv["home_margin"]), (W["internal"], internal_m)] + ([(W["bpi"], bpi_m)] if bpi_m is not None else [])
        cons = round(sum(w * m for w, m in parts) / sum(w for w, _ in parts), 1)
        open_home = -spread_num(g["open_away_spread"]) if g["open_away_spread"] else None   # home margin implied by line
        cur_home = -spread_num(g["cur_away_spread"]) if g["cur_away_spread"] else None
        out.append({
            "pulled_utc": ts, "date": args.date, "tip": g["tip"], "away": g["away"], "home": g["home"],
            "torvik_home_margin": tv["home_margin"], "torvik_total": tv["total"], "bpi_home_margin": bpi_m,
            "consensus_home_margin": cons,
            "circa_open_home_margin": open_home, "circa_cur_home_margin": cur_home,
            "circa_open_total": g["open_total"], "circa_cur_total": g["cur_total"],
            "gap_vs_open": round(cons - open_home, 1) if open_home is not None else None,
            "gap_vs_current": round(cons - cur_home, 1) if cur_home is not None else None,
            "moved_toward_model": (None if open_home is None or cur_home is None or cur_home == open_home
                                   else (cur_home - open_home) * (cons - open_home) > 0),
        })

    with open(args.out, "w", newline="") as f:
        if out:
            w = csv.DictWriter(f, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
    print(json.dumps({"status": status, "games_written": len(out), "unmatched": unmatched[:40]}))


if __name__ == "__main__":
    main()
