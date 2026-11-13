#!/usr/bin/env python3
"""CBB model aggregate + line movement, run in GitHub Actions.

Separate from the NBA/NFL/CFB scans. Every game on the slate is logged (bet or
not) so model weights and bet thresholds can be fit later.

Sources
  - ESPN scoreboard API (schedule, tip, neutral site, ESPN's book line, finals)   required
  - Torvik team CSV  barttorvik.com/<season>_team_results.csv                     preferred
    (if Torvik is unreachable, e.g. it blocks GitHub's servers, the slate is built from
    TR + BPI: TR ranks set the tier and Torvik's totals/ranks are left blank)
  - TeamRankings predictive ratings (newest data/*/HHMM_tr_ratings_CBB.csv)        optional
  - ESPN BPI via the power-index API (skipped if its layout isn't recognized)     optional
  - Circa open/current: newest data/*/HHMM_circa_CBB.csv from vsin_pull.py        optional
    (no Circa -> ESPN's book line is used as the current line, labeled as such)

Outputs
  data/cbb/YYYY-MM-DD/HHMM_slate.csv      one row per game for this run
  data/cbb/results/YYYY-MM-DD.csv         yesterday's finals vs model, open and close
  data/cbb/latest/slate.csv, results.csv, brief.md, status.json   fixed URLs for the Claude tasks
  (kept out of data/latest/, which publish_gist.py rewrites on every VSiN run)

Usage: python cbb_pull.py [--date YYYY-MM-DD] [--season 2027] [--no-results]
Exit codes: 0 ok (source problems are listed in status.json), 2 no slate possible
(ESPN failed, or neither Torvik nor TR ratings are available).
"""
import argparse, csv, difflib, glob, io, json, os, re, sys, urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
NOW = datetime.now(ET)
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/130 Safari/537.36", "Accept": "*/*"}
HCA = 3.0                                          # home-court points (ledger: Model weights)
W = {"torvik": 0.5, "tr": 0.3, "bpi": 0.2}         # consensus weights; renormalized over models present
MARKET_W = {1: 0.7, 2: 0.5, 3: 0.4}                # weight on the Circa opener in the fair line
NOV_BUMP = 0.1                                     # extra market weight in November
THRESH = {1: 1.5, 2: 2.5, 3: 2.5}                  # |fair - current| needed to flag, points
OUT = "data/cbb"


# ---------------------------------------------------------------- helpers
def get(url, timeout=40):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def norm(name):
    """School-name key that lines up ESPN, Torvik, TeamRankings and VSiN spellings."""
    s = (name or "").lower().replace("&", " and ")
    s = re.sub(r"\(\d+\)", " ", s)
    s = re.sub(r"[.'’()]", "", s)
    s = re.sub(r"\bsaint\b", "st", s)
    s = re.sub(r"\bstate\b", "st", s)
    s = re.sub(r"\buniversity\b", "", s)
    s = s.replace("-", " ")
    return re.sub(r"\s+", " ", s).strip()


# TeamRankings abbreviates school names ("W Kentucky", "Loyola Chi", "SF Austin"). With
# expand=True the matcher also indexes each name with these spelled out, so ESPN's
# "Western Kentucky" / "Loyola Chicago" find it. (Torvik's full names made this
# unnecessary while Torvik was the primary pool.)
TR_ABBR = {
    "n": ["north", "northern"], "s": ["south", "southern"], "e": ["east", "eastern"],
    "w": ["west", "western"], "c": ["central"], "se": ["southeast", "southeastern"],
    "nc": ["north carolina"], "sc": ["south carolina"], "ut": ["texas", "tennessee"],
    "uc": ["california", "uc"], "cs": ["cal st", "csu"], "ul": ["louisiana"],
    "sf": ["stephen f"], "chi": ["chicago"], "mymt": ["marymount"], "md": ["maryland"],
    "intl": ["international"], "car": ["carolina"], "tenn": ["tennessee"], "miss": ["mississippi"],
    "g": ["george"], "fl": ["florida"], "so": ["southern"],
}
# Whole-name nicknames TR doesn't use (key: TR name, values: other spellings).
TR_EXTRA = {"Mississippi": ["Ole Miss"], "E Texas A&M": ["Texas A&M-Commerce", "East Texas A&M"],
            "Texas A&M-CC": ["Texas A&M-Corpus Christi"]}


def _expansions(key):
    """norm()ed name -> set of norm()ed spellings with TR abbreviations expanded (capped)."""
    out = [""]
    for tok in key.split():
        opts = [tok] + TR_ABBR.get(tok, [])
        out = [f"{o} {x}".strip() for o in out for x in opts][:64]
    return {norm(v) for v in out}


class Matcher:
    """Map a school name (or school + mascot) onto a pool of school names."""
    def __init__(self, pool, expand=False):
        self.by_key = {norm(p): p for p in pool}
        if expand:
            for p in pool:
                for k in _expansions(norm(p)) | {norm(x) for x in TR_EXTRA.get(p, [])}:
                    self.by_key.setdefault(k, p)
        self.keys = list(self.by_key)

    def __call__(self, *names):
        for name in names:
            k = norm(name)
            if not k:
                continue
            if k in self.by_key:
                return self.by_key[k]
            words = k.split()
            for n in range(len(words) - 1, 0, -1):          # drop mascot words from the right
                if " ".join(words[:n]) in self.by_key:
                    return self.by_key[" ".join(words[:n])]
        for name in names:
            hit = difflib.get_close_matches(norm(name), self.keys, n=1, cutoff=0.88)
            if hit:
                return self.by_key[hit[0]]
        return None


def first_num(s):
    """'+5 -110' -> 5.0, 'PK' -> 0.0, '224.5 o -110' -> 224.5."""
    s = (s or "").strip()
    if s.upper().startswith("PK"):
        return 0.0
    m = re.match(r"[+-]?\d+(\.\d+)?", s)
    return float(m.group(0)) if m else None


def rnd(x, n=1):
    return None if x is None else round(x, n)


# ---------------------------------------------------------------- sources
def espn_games(day):
    url = ("https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/"
           f"scoreboard?dates={day:%Y%m%d}&groups=50&limit=500")
    data = json.loads(get(url))
    if "events" not in data:
        raise RuntimeError("ESPN scoreboard returned no events key")
    games = []
    for ev in data["events"]:
        comp = (ev.get("competitions") or [{}])[0]
        teams = {c.get("homeAway"): c for c in comp.get("competitors", [])}
        if "home" not in teams or "away" not in teams:
            continue

        def info(c):
            t = c.get("team", {})
            return {"school": t.get("location") or t.get("shortDisplayName") or t.get("displayName", ""),
                    "full": t.get("displayName", ""), "short": t.get("shortDisplayName", ""),
                    "abbr": t.get("abbreviation", ""), "score": c.get("score")}
        a, h = info(teams["away"]), info(teams["home"])
        odds = (comp.get("odds") or [{}])[0]
        tip = datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(ET)
        stype = ((comp.get("status") or ev.get("status") or {}).get("type") or {})
        # ESPN 'details' reads like "DUKE -7.5"; convert to the home team's expected margin.
        line_home, det = None, (odds.get("details") or "").strip()
        m = re.match(r"(.+?)\s+([+-]?\d+(\.\d+)?)$", det)
        if m:
            fav, pts = m.group(1).strip().upper(), abs(float(m.group(2)))
            if fav in (h["abbr"].upper(), h["short"].upper(), h["full"].upper()):
                line_home = pts
            elif fav in (a["abbr"].upper(), a["short"].upper(), a["full"].upper()):
                line_home = -pts
        elif det.upper() in ("EVEN", "PK", "PICK"):
            line_home = 0.0
        games.append({
            "espn_id": str(ev.get("id")), "tip_dt": tip, "tip": tip.strftime("%I:%M %p").lstrip("0"),
            "away": a, "home": h, "neutral": bool(comp.get("neutralSite")),
            "espn_book": (odds.get("provider") or {}).get("name", ""),
            "espn_line_home": line_home, "espn_total": odds.get("overUnder"),
            "completed": bool(stype.get("completed")),
        })
    return games


def torvik_ratings(season):
    text = get(f"https://barttorvik.com/{season}_team_results.csv")
    rows = list(csv.reader(io.StringIO(text)))
    head = [h.strip().lower() for h in rows[0]] if rows else []
    if "team" not in head or "adjoe" not in head:
        raise RuntimeError("Torvik CSV header changed or page blocked: " + ",".join(head[:8]))
    i_t, i_o, i_d, i_tp = head.index("team"), head.index("adjoe"), head.index("adjde"), head.index("adjt")
    i_rk = head.index("rank") if "rank" in head else None
    out = {}
    for n, r in enumerate(rows[1:], 1):
        try:
            out[r[i_t].strip()] = {"adjoe": float(r[i_o]), "adjde": float(r[i_d]), "adjt": float(r[i_tp]),
                                   "rank": int(float(r[i_rk])) if i_rk is not None else n}
        except (ValueError, IndexError):
            continue
    if len(out) < 300:
        raise RuntimeError(f"Torvik CSV only parsed {len(out)} teams")
    return out


def torvik_predict(a, h, R, neutral):
    """KenPom-style: possessions from tempos, points from O vs D relative to D-I average."""
    avg_eff = sum(t["adjoe"] for t in R.values()) / len(R)
    avg_tmp = sum(t["adjt"] for t in R.values()) / len(R)
    poss = R[a]["adjt"] * R[h]["adjt"] / avg_tmp
    pa = R[a]["adjoe"] * R[h]["adjde"] / avg_eff * poss / 100
    ph = R[h]["adjoe"] * R[a]["adjde"] / avg_eff * poss / 100
    return ph - pa + (0 if neutral else HCA), pa + ph


def tr_ratings():
    """TeamRankings predictive rating (points vs an average team, neutral court)."""
    paths = sorted(glob.glob("data/????-??-??/[0-9][0-9][0-9][0-9]_tr_ratings_CBB.csv"))
    if not paths:
        raise RuntimeError("no tr_ratings_CBB.csv in the repo yet")
    out = {}
    with open(paths[-1], encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                out[r["team"].strip()] = float(r["rating"])
            except (KeyError, ValueError):
                continue
    if len(out) < 300:
        raise RuntimeError(f"TR ratings only {len(out)} teams")
    day = os.path.basename(os.path.dirname(paths[-1]))
    return out, f"{day} {os.path.basename(paths[-1])[:4]}"


def bpi_ratings():
    """ESPN BPI via the power-index API. Optional: any layout surprise -> skipped."""
    url = ("https://site.web.api.espn.com/apis/fitt/v3/sports/basketball/mens-college-basketball/"
           "powerindex?region=us&lang=en&limit=500")
    data = json.loads(get(url))
    cats = data.get("categories") or []
    names = [str(n).lower() for n in (cats[0].get("names") or [])] if cats else []
    out = {}
    if "bpi" in names:
        i = names.index("bpi")
        for t in data.get("teams", []):
            team = (t.get("team") or {}).get("location") or (t.get("team") or {}).get("displayName")
            vals = ((t.get("categories") or [{}])[0]).get("values") or []
            try:
                out[team] = float(vals[i])
            except (ValueError, IndexError, TypeError):
                pass
    if len(out) < 300:
        raise RuntimeError(f"BPI layout not recognized ({len(out)} teams)")
    return out


def circa_rows():
    """Recent pulls from the VSiN pipeline's Circa CBB files (oldest first)."""
    rows = []
    for p in sorted(glob.glob("data/????-??-??/[0-9][0-9][0-9][0-9]_circa_CBB.csv"))[-80:]:
        with open(p, encoding="utf-8") as f:
            rows += list(csv.DictReader(f))
    return rows


# ---------------------------------------------------------------- build
def tier_of(ra, rh):
    """Proxy until a conference/TV flag is added: both top-100 = T1, avg rank <= 200 = T2, else T3."""
    if max(ra, rh) <= 100:
        return 1
    if (ra + rh) / 2 <= 200:
        return 2
    return 3


def build_slate(day, games, R, TR, B, circa):
    mt = Matcher(R) if R else None
    mtr = Matcher(TR, expand=True) if TR else None
    # Without Torvik, tiers come from TR rank (1 = best rating).
    tr_rank = {t: i for i, t in enumerate(sorted(TR, key=TR.get, reverse=True), 1)} if TR else {}
    mb = Matcher(B) if B else None
    circ = {}
    for r in circa:
        circ.setdefault(norm(r.get("away")) + " @ " + norm(r.get("home")), []).append(r)
    ckeys = list(circ)
    used = set()

    def circa_for(g):
        # VSiN CBB names are usually the school only ("George Mason"), sometimes shortened ("UMKC").
        cands = lambda t: [norm(x) for x in (t["school"], t["short"], t["full"], t["abbr"]) if x]
        hits = None
        for ka in cands(g["away"]):
            for kh in cands(g["home"]):
                hits = hits or circ.get(ka + " @ " + kh)
        if not hits:
            best = difflib.get_close_matches(norm(g["away"]["school"]) + " @ " + norm(g["home"]["school"]),
                                             ckeys, n=1, cutoff=0.85)
            hits = circ.get(best[0]) if best else None
        if not hits:
            return None, None
        used.add(norm(hits[0].get("away")) + " @ " + norm(hits[0].get("home")))
        tip_iso = g["tip_dt"].isoformat(timespec="minutes")
        hits = [r for r in hits if r.get("pulled_et", "") >= (g["tip_dt"] - timedelta(days=2)).isoformat()] or hits
        pre = [r for r in hits if r.get("pulled_et", "") <= tip_iso] or hits
        return hits[0], pre[-1]

    out, unmatched = [], []
    nov = day.month == 11
    for g in games:
        if g["tip_dt"] <= NOW or g["completed"]:
            continue                      # already tipped: the last pre-tip snapshot is the close
        hca = 0 if g["neutral"] else HCA
        tv_m = tv_t = tv_ra = tv_rh = None
        parts, tr_m, bpi_m, ra, rh = [], None, None, None, None
        if mt:
            ta = mt(g["away"]["school"], g["away"]["full"])
            th = mt(g["home"]["school"], g["home"]["full"])
            if not ta or not th:
                unmatched.append(f'{g["away"]["full"]} @ {g["home"]["full"]}')
                continue
            tv_m, tv_t = torvik_predict(ta, th, R, g["neutral"])
            parts.append(("torvik", tv_m))
            tv_ra, tv_rh = ra, rh = R[ta]["rank"], R[th]["rank"]
        if mtr:
            a2, h2 = mtr(g["away"]["school"], g["away"]["full"]), mtr(g["home"]["school"], g["home"]["full"])
            if a2 and h2:
                tr_m = TR[h2] - TR[a2] + hca; parts.append(("tr", tr_m))
                if ra is None:
                    ra, rh = tr_rank[a2], tr_rank[h2]
        if mb:
            a3, h3 = mb(g["away"]["school"], g["away"]["full"]), mb(g["home"]["school"], g["home"]["full"])
            if a3 and h3:
                bpi_m = B[h3] - B[a3] + hca; parts.append(("bpi", bpi_m))
        if not parts or ra is None:       # no Torvik and no TR match: can't rate or tier this game
            unmatched.append(f'{g["away"]["full"]} @ {g["home"]["full"]}')
            continue
        cons = sum(W[k] * v for k, v in parts) / sum(W[k] for k, _ in parts)

        first, last = circa_for(g)
        src, open_h, cur_h, open_t, cur_t = "", None, None, None, None
        if last:
            o, c = first_num(first.get("circa_open_away_spread")), first_num(last.get("circa_away_spread"))
            # Away spread +26 = home favored by 26 = home margin +26.
            open_h, cur_h = o, c
            open_t, cur_t = first_num(first.get("circa_open_total")), first_num(last.get("circa_total"))
            src = "Circa " + last.get("pulled_et", "")[5:16].replace("T", " ")
        if cur_h is None and g["espn_line_home"] is not None:
            cur_h, cur_t = g["espn_line_home"], g["espn_total"]
            src = f'ESPN/{g["espn_book"] or "book"} (no Circa)'

        tier = tier_of(ra, rh)
        mw = min(0.9, MARKET_W[tier] + (NOV_BUMP if nov else 0))
        anchor = open_h if open_h is not None else cur_h
        fair = mw * anchor + (1 - mw) * cons if anchor is not None else None
        edge = fair - cur_h if fair is not None and cur_h is not None else None
        moved = None
        if open_h is not None and cur_h is not None and cur_h != open_h:
            moved = (cur_h - open_h) * (cons - open_h) > 0
        flag = ""
        if edge is not None and abs(edge) >= THRESH[tier]:
            side = g["home"]["school"] if edge > 0 else g["away"]["school"]
            flag = f"EDGE {side} {abs(edge):.1f}"
            flag += " · moved toward model" if moved is True else (" · line moved away" if moved is False else "")
        out.append({
            "date": day.isoformat(), "tip_et": g["tip"], "espn_id": g["espn_id"],
            "away": g["away"]["school"], "home": g["home"]["school"], "site": "N" if g["neutral"] else "H",
            "tier": tier, "torvik_rank_away": tv_ra, "torvik_rank_home": tv_rh,
            "torvik_home_margin": rnd(tv_m), "torvik_total": rnd(tv_t), "tr_home_margin": rnd(tr_m),
            "bpi_home_margin": rnd(bpi_m), "consensus_home_margin": rnd(cons),
            "line_source": src, "open_home_margin": open_h, "cur_home_margin": cur_h,
            "open_total": open_t, "cur_total": cur_t,
            "fair_home_margin": rnd(fair), "edge_pts": rnd(edge),
            "gap_cons_vs_open": rnd(cons - open_h) if open_h is not None else None,
            "gap_cons_vs_cur": rnd(cons - cur_h) if cur_h is not None else None,
            "moved_toward_model": moved, "flag": flag,
            "flag_side": ("home" if edge > 0 else "away") if flag else "",
            "pulled_et": NOW.isoformat(timespec="minutes"),
        })
    # Circa games for this date that matched no ESPN game: name mismatches to add to norm()/aliases.
    tag = day.strftime("%b %-d")
    orphans = sorted({k for k, rs in circ.items() if k not in used and any(tag in (r.get("date") or "") for r in rs)})
    return out, unmatched, orphans


def build_results(day, games, slate_rows):
    """Finals for `day` joined to the last slate row written for each game (oldest files first)."""
    last = {r["espn_id"]: r for r in slate_rows}
    out = []
    for g in games:
        r = last.get(g["espn_id"])
        if not g["completed"] or not r:
            continue
        try:
            hs, as_ = float(g["home"]["score"]), float(g["away"]["score"])
        except (TypeError, ValueError):
            continue
        num = lambda k: float(r[k]) if r.get(k) not in (None, "", "None") else None
        close, cons, opn = num("cur_home_margin"), num("consensus_home_margin"), num("open_home_margin")
        margin, total = hs - as_, hs + as_
        out.append({
            "date": day.isoformat(), "espn_id": g["espn_id"], "away": r["away"], "home": r["home"],
            "tier": r["tier"], "site": r["site"], "final_home_margin": margin, "final_total": total,
            "open_home_margin": opn, "close_home_margin": close, "close_source": r["line_source"],
            "close_total": r.get("cur_total"), "consensus_home_margin": cons,
            "torvik_home_margin": num("torvik_home_margin"), "tr_home_margin": num("tr_home_margin"),
            "bpi_home_margin": num("bpi_home_margin"), "fair_home_margin": num("fair_home_margin"),
            "torvik_total": num("torvik_total"), "flag_at_close": r["flag"], "flag_side": r.get("flag_side", ""),
            "model_err": rnd(margin - cons) if cons is not None else None,
            "close_err": rnd(margin - close) if close is not None else None,
            "home_covered": None if close is None or margin == close else margin > close,
        })
    return out


def calibration(res):
    """One summary row per slate for the ledger's Calibration log (games with open and close lines)."""
    gaps_o, gaps_c, moves, toward, n, flagged, flag_cov = [], [], [], 0, 0, 0, 0
    for r in res:
        o, c, k = r["open_home_margin"], r["close_home_margin"], r["consensus_home_margin"]
        if c is None or k is None:
            continue
        n += 1
        gaps_c.append(abs(k - c))
        if o is not None:
            gaps_o.append(abs(k - o)); moves.append(abs(c - o))
            if c != o and (c - o) * (k - o) > 0:
                toward += 1
        if r["flag_side"] and r["home_covered"] is not None:
            flagged += 1
            flag_cov += int((r["flag_side"] == "home") == r["home_covered"])
    avg = lambda xs: round(sum(xs) / len(xs), 2) if xs else None
    moved = [m for m in moves if m > 0]
    return {"games": n, "with_open": len(gaps_o), "avg_gap_cons_vs_open": avg(gaps_o),
            "avg_gap_cons_vs_close": avg(gaps_c), "avg_move_open_to_close": avg(moves),
            "pct_moved_toward_consensus": round(100 * toward / len(moved), 1) if moved else None,
            "flagged_games_graded": flagged, "flagged_covered": flag_cov}


def calibration_all():
    """Season-to-date accuracy over every results/*.csv: the file the weekly review reads."""
    rows = []
    for p in sorted(glob.glob(f"{OUT}/results/????-??-??.csv")):
        with open(p, encoding="utf-8") as fh:
            rows += list(csv.DictReader(fh))
    f = lambda r, k: float(r[k]) if r.get(k) not in (None, "", "None") else None
    def mae(k, target="final_home_margin", sub=None):
        e = [abs(f(r, k) - f(r, target)) for r in (sub if sub is not None else rows) if f(r, k) is not None and f(r, target) is not None]
        return f"{sum(e) / len(e):.2f} (n={len(e)})" if e else "—"
    tiers = {t: [r for r in rows if r.get("tier") == str(t)] for t in (1, 2, 3)}
    out = [f"# CBB calibration, season to date — {len(rows)} games graded (updated {NOW:%Y-%m-%d %H:%M} ET)", "",
           "Mean absolute error vs the final margin; lower is better. The closing line is the benchmark to beat.", "",
           "| Predictor | All | Tier 1 | Tier 2 | Tier 3 |", "|---|---|---|---|---|"]
    for k, label in (("close_home_margin", "Closing line"), ("open_home_margin", "Opener"), ("torvik_home_margin", "Torvik"),
                     ("tr_home_margin", "TeamRankings"), ("bpi_home_margin", "BPI"), ("consensus_home_margin", "Model consensus"),
                     ("fair_home_margin", "Fair line")):
        out.append(f"| {label} | {mae(k)} | " + " | ".join(mae(k, sub=tiers[t]) for t in (1, 2, 3)) + " |")
    flagged = [r for r in rows if r.get("flag_side") and r.get("home_covered") in ("True", "False")]
    won = sum((r["flag_side"] == "home") == (r["home_covered"] == "True") for r in flagged)
    out += ["", f"- Flagged sides vs the closing line: {won}-{len(flagged) - won}" +
            (f" ({100 * won / len(flagged):.1f}%; break-even at -110 is 52.4%)" if flagged else ""),
            f"- Totals MAE: Torvik {mae('torvik_total', 'final_total')} vs closing total {mae('close_total', 'final_total')}",
            "", "Change weights or thresholds only after ~300 graded games, and only where a gap holds in every tier."]
    os.makedirs(f"{OUT}/latest", exist_ok=True)
    with open(f"{OUT}/latest/calibration.md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    return len(rows)


def write_csv(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def brief(slate, status):
    def f(x):
        return "—" if x in (None, "") else (f"{x:+.1f}" if isinstance(x, float) else str(x))
    lines = [f"# CBB model brief — {status['date']} (pulled {status['pulled_et'][11:16]} ET)", "",
             "All numbers are the HOME team's margin (+ = home favored). Edge = fair minus current line; "
             f"EDGE flags meet the tier threshold (T1 {THRESH[1]}, T2-3 {THRESH[2]} pts). "
             "Fair = market weight x Circa opener + the rest x model consensus.",
             f"Sources: {status['sources']}", "",
             "| Game (ET) | Site | Tier | Line src | Open→now | Total open→now | Torvik | TR | BPI | Cons | Fair | Edge | To model | Flag |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    rows = [r for r in slate if r["cur_home_margin"] is not None]
    rows.sort(key=lambda r: (r["flag"] == "", -abs(r["edge_pts"] or 0)))
    for r in rows:
        moved = "—" if r["moved_toward_model"] is None else ("yes" if r["moved_toward_model"] else "no")
        lines.append(f"| {r['away']} @ {r['home']} {r['tip_et']} | {r['site']} | {r['tier']} | {r['line_source']} | "
                     f"{f(r['open_home_margin'])}→{f(r['cur_home_margin'])} | {r['open_total'] or '—'}→{r['cur_total'] or '—'} | "
                     f"{f(r['torvik_home_margin'])} | {f(r['tr_home_margin'])} | {f(r['bpi_home_margin'])} | "
                     f"{f(r['consensus_home_margin'])} | {f(r['fair_home_margin'])} | {f(r['edge_pts'])} | {moved} | {r['flag']} |")
    lines += ["", f"{len(slate) - len(rows)} games had no line yet; they are in slate.csv only."]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=NOW.date().isoformat())
    ap.add_argument("--season", default="2027")
    ap.add_argument("--no-results", action="store_true")
    args = ap.parse_args()
    day = datetime.strptime(args.date, "%Y-%m-%d").date()
    status = {"date": day.isoformat(), "pulled_et": NOW.isoformat(timespec="minutes")}
    soft_fail = False

    try:
        games = espn_games(day); status["espn"] = f"ok {len(games)} games"
    except Exception as e:
        games = None; status["espn"] = f"error: {e}"
    try:
        R = torvik_ratings(args.season); status["torvik"] = f"ok {len(R)} teams"
    except Exception as e:
        R = None; status["torvik"] = f"error: {e}"
    try:
        TR, when = tr_ratings(); status["tr"] = f"ok {len(TR)} teams ({when})"
    except Exception as e:
        TR = {}; status["tr"] = f"skipped: {e}"; soft_fail = True
    try:
        B = bpi_ratings(); status["bpi"] = f"ok {len(B)} teams"
    except Exception as e:
        B = {}; status["bpi"] = f"skipped: {e}"
    circa = circa_rows()
    today = [r for r in circa if r.get("pulled_et", "").startswith(day.isoformat())]
    status["circa"] = (f"ok {len(today)} CBB rows pulled today" if today else
                       "none today (VSiN pull failing or board not up): ESPN book line used where posted")

    os.makedirs(f"{OUT}/latest", exist_ok=True)
    if R is None and TR:
        status["alert"] = ("Torvik unavailable: slate built from TR + BPI only "
                           "(tiers from TR rank; no Torvik totals)")
    if games is None or (R is None and not TR):
        status["alert"] = "no slate written: ESPN failed, or neither Torvik nor TR ratings are available"
        json.dump(status, open(f"{OUT}/latest/status.json", "w"), indent=2)
        print(json.dumps(status, indent=2)); sys.exit(2)

    slate, unmatched, orphans = build_slate(day, games, R, TR, B, circa)
    status.update({"circa_unmatched": orphans[:40], "games_written": len(slate),
                   "with_line": sum(1 for r in slate if r["cur_home_margin"] is not None),
                   "with_circa": sum(1 for r in slate if r["line_source"].startswith("Circa")),
                   "flags": sum(1 for r in slate if r["flag"]), "unmatched": unmatched[:40]})
    status["sources"] = " · ".join(f"{k} {status[k]}" for k in ("espn", "torvik", "tr", "bpi", "circa"))
    write_csv(f"{OUT}/{day.isoformat()}/{NOW:%H%M}_slate.csv", slate)
    write_csv(f"{OUT}/latest/slate.csv", slate)
    with open(f"{OUT}/latest/brief.md", "w", encoding="utf-8") as fh:
        fh.write(brief(slate, status))

    if not args.no_results:
        graded = []
        for back in (3, 2, 1):
            yday = day - timedelta(days=back)
            if os.path.exists(f"{OUT}/results/{yday.isoformat()}.csv") and back > 1:
                continue
            prior = []
            for p in sorted(glob.glob(f"{OUT}/{yday.isoformat()}/[0-9][0-9][0-9][0-9]_slate.csv")):
                with open(p, encoding="utf-8") as fh:
                    prior += list(csv.DictReader(fh))
            if not prior:
                continue
            try:
                res = build_results(yday, espn_games(yday), prior)
                write_csv(f"{OUT}/results/{yday.isoformat()}.csv", res)
                if back == 1:
                    write_csv(f"{OUT}/latest/results.csv", res)
                    status["calibration"] = calibration(res)
                graded.append(f"{yday.isoformat()}: {len(res)} finals")
            except Exception as e:
                graded.append(f"{yday.isoformat()}: error {e}"); soft_fail = True
        status["results"] = "; ".join(graded) or "no earlier slate files yet"
        status["season_graded"] = calibration_all()

    with open(f"{OUT}/latest/status.json", "w") as fh:
        json.dump(status, fh, indent=2)
    print(json.dumps(status, indent=2))
    if soft_fail:
        print("note: an optional source was skipped; see status.json")


if __name__ == "__main__":
    main()
