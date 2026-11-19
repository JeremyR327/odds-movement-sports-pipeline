#!/usr/bin/env python3
"""DraftKings betting splits (DK Network, public) joined to the pipeline's DraftKings lines.

Why: the cloud scans read DK Network live, 10 games per page, so CFB coverage stopped at
~20 games. This pulls every page on GitHub, joins each game to its DraftKings open/now line
from espn_lines.py, computes Jeremy's rubric flags for EVERY game, and writes one short
brief the scans can read in a single fetch.

Writes (kept out of data/latest/, which publish_gist.py rewrites):
  data/splits/<date>/HHMM_dk_<SPORT>.csv      every game, every pull (the day's split path)
  data/splits/latest/brief_<SPORT>.md         one row per game, signal games first
  data/splits/latest/dk_<SPORT>.csv           newest pull
  data/splits/latest/status.json

Rubric (from the sharp-betting-scan skill): PUB = 65%+ of DK bets on one side;
SHARP = handle minus bets >= +15 on a side; RLM = the DK spread moved (open -> now) toward
the side with under 50% of bets; STEAM = 1.5+ spread move; KEY = crossed a key number.
Usage: python dk_splits.py [CFB NFL]   (default: CFB NFL)
"""
import csv, difflib, glob, html, json, os, re, sys, time, urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
NOW = datetime.now(ET)
URL = ("https://dknetwork.draftkings.com/draftkings-sportsbook-betting-splits/"
       "?tb_eg={eg}&tb_edate=n7days&tb_emt=0&tb_page={page}")
EG = {"CFB": 87637, "NFL": 88808, "CBB": 92483}   # CBB = DraftKings NCAAB event group (unverified: status shows 0 games if wrong)
KEYS = {"CFB": (3, 7, 14, 17), "NFL": (3, 7, 10), "CBB": ()}
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/130 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      "Accept-Language": "en-US,en;q=0.9", "Cache-Control": "no-cache", "Pragma": "no-cache"}
OUT = "data/splits"
# ESPN's DraftKings "open" for NFL/CFB is the number posted at schedule release (May for the NFL), so
# open -> now spans months of injuries and records, not this week's market. For these sports the
# opener is the FIRST pipeline pull that saw the game within this many days; ESPN's open is kept
# as spread_open_espn / total_open_espn. CBB openers are posted the day before and stay ESPN's.
WEEK_OPEN_DAYS = {"NFL": 6, "CFB": 6}


def get(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))


def page_text(raw):
    """HTML -> one line of plain text per block element (headings, rows, cells)."""
    raw = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<\s*(br|/p|/div|/li|/tr|/td|/th|/h\d|/span|/a)\b[^>]*>", "\n", raw)
    txt = html.unescape(re.sub(r"<[^>]+>", " ", raw)).replace("−", "-").replace(" ", " ")
    return "\n".join(l for l in (re.sub(r"[ \t]+", " ", x).strip() for x in txt.splitlines()) if l)


TITLE = re.compile(r"^(?P<away>[^@\n]{2,60}?) @ (?P<home>[^@\n]{2,60})$")
WHEN = re.compile(r"(?P<dow>Mon|Tue|Wed|Thu|Fri|Sat|Sun)\w* (?P<md>\d{1,2}/\d{1,2})\s*[·\-|]?\s*(?P<tm>\d{1,2}:\d{2} [AP]M)")
UPDATED = re.compile(r"Updated (\d{1,2}:\d{2} [AP]M)")
# one side row inside a market: name (+ line), odds, handle %, bets %
ROW = re.compile(r"(?P<sel>[A-Za-z&.'()][A-Za-z0-9&.'()+\- ]*?)\s+(?P<odds>[+-]\d{3,5}|EVEN)\s+(?P<h>\d{1,3})%\s+(?P<b>\d{1,3})%")


def parse_page(raw):
    """-> (games, updated). Each game: away, home, when, ml/spread/total sides with handle/bets."""
    text = page_text(raw)
    upd = UPDATED.search(text)
    lines = text.split("\n")
    starts = [i for i, l in enumerate(lines) if TITLE.match(l) and i + 1 < len(lines) and WHEN.search(" ".join(lines[i + 1:i + 3]))]
    games = []
    for n, i in enumerate(starts):
        block = " ".join(lines[i + 1:(starts[n + 1] if n + 1 < len(starts) else len(lines))])
        t, w = TITLE.match(lines[i]), WHEN.search(block)
        g = {"away": t["away"].strip(), "home": t["home"].strip(), "when": f'{w["dow"]} {w["md"]} {w["tm"]}'}
        # split the block on the market labels, in the page's order: Moneyline, Spread, Total
        parts = re.split(r"\b(Moneyline|Spread|Total)\b(?!\s*\d)", block)
        for k in range(1, len(parts) - 1, 2):
            mkt, body = parts[k].lower(), parts[k + 1]
            body = re.sub(r"\b(Selection|Odds|Handle|Bets|Advertisement)\b", " ", body)
            rows = [m.groupdict() for m in ROW.finditer(body)][:2]
            if len(rows) == 2 and mkt not in g:
                g[mkt] = [{"sel": r["sel"].strip(), "odds": r["odds"], "handle": int(r["h"]), "bets": int(r["b"])} for r in rows]
        if any(m in g for m in ("moneyline", "spread", "total")):
            games.append(g)
    return games, (upd.group(1) if upd else "")


def pull_splits(sport):
    games, seen, updated = [], set(), []
    for page in range(1, 16):
        gs, upd = parse_page(get(URL.format(eg=EG[sport], page=page) + f"&_={int(time.time())}"))
        new = [g for g in gs if (g["away"], g["home"], g["when"]) not in seen]
        if not new:
            break
        for g in new:
            seen.add((g["away"], g["home"], g["when"]))
        games += new; updated.append(upd)
        time.sleep(1)
    return games, updated


# ---------------------------------------------------------------- join to the DraftKings lines
def norm(s):
    s = (s or "").lower().replace("&", " and ").replace("state", "st").replace("saint", "st")
    return re.sub(r"[^a-z0-9 ]", "", s).strip()


def name_score(dk, espn):
    """DK uses school names ('Miami FL', 'Ohio State'); ESPN displayName adds the mascot."""
    d, e = norm(dk), norm(espn)
    if e.startswith(d):
        return 1.0
    dw, ew = d.split(), e.split()
    if len(dw) >= 2 and dw[-1] == ew[-1] and (dw[0][0] == ew[0][0] or len(dw[0]) <= 3):
        return 0.95                                                     # 'la chargers' ~ 'los angeles chargers'

    d2 = re.sub(r"\b(fl|oh|pa|ca|tx)\b", "", d).strip()                 # 'miami fl' -> 'miami'
    if d2 and e.startswith(d2 + " "):
        return 0.95
    return difflib.SequenceMatcher(None, d, " ".join(e.split()[:len(d.split()) + 1])).ratio()


def latest_lines(sport):
    paths = sorted(glob.glob(f"data/{NOW:%Y-%m-%d}/[0-9][0-9][0-9][0-9]_lines_{sport}.csv"))
    if not paths:
        paths = sorted(glob.glob(f"data/????-??-??/[0-9][0-9][0-9][0-9]_lines_{sport}.csv"))[-1:]
    return list(csv.DictReader(open(paths[-1], encoding="utf-8"))) if paths else [], (paths[-1] if paths else "")


def week_open(sport):
    """espn_id -> {spread, total, at}: the first pipeline line pull that saw the game in the window."""
    days = WEEK_OPEN_DAYS.get(sport)
    if not days:
        return {}
    cutoff = (NOW - timedelta(days=days)).strftime("%Y-%m-%d")
    out = {}
    for p in sorted(glob.glob(f"data/????-??-??/[0-9][0-9][0-9][0-9]_lines_{sport}.csv")):
        day = os.path.basename(os.path.dirname(p))
        if day < cutoff:
            continue
        at = f"{day[5:]} {os.path.basename(p)[:4]}"
        with open(p, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                e = out.setdefault(r.get("espn_id", ""), {"spread": "", "total": "", "at": ""})
                if not e["spread"] and r.get("spread_now") not in (None, ""):
                    e["spread"], e["at"] = r["spread_now"], at
                if not e["total"] and r.get("total_now") not in (None, ""):
                    e["total"] = r["total_now"]
    out.pop("", None)
    return out


def tr_proj(sport):
    """Newest TeamRankings final-score projections (teamrankings_pull.py, daily ~3:29 PM) if from
    today or yesterday: [(away, home, proj_home_margin, proj_total)], plus the file's pull time."""
    paths = sorted(glob.glob(f"data/????-??-??/[0-9][0-9][0-9][0-9]_tr_proj_{sport}.csv"))
    if not paths:
        return [], ""
    day = os.path.basename(os.path.dirname(paths[-1]))
    if (NOW.date() - datetime.strptime(day, "%Y-%m-%d").date()).days > 1:
        return [], ""
    rows = [r for r in csv.DictReader(open(paths[-1], encoding="utf-8")) if r.get("status") == "ok"]
    return rows, f"{day[5:]} {os.path.basename(paths[-1])[:4]}"


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def thin(rows):
    """CBB/early-week samples: a 0% or 100% handle or bets cell means too few tickets to read."""
    return not rows or any(r["handle"] in (0, 100) or r["bets"] in (0, 100) for r in rows)


def orient(g):
    """DK Network lists the HOME side first. Put the away side first by matching names, so every
    away/home column (and RLM) is right whatever order the page uses; Over first for totals."""
    for mkt in ("moneyline", "spread"):
        rows = g.get(mkt)
        if rows and len(rows) == 2:
            sa = name_score(g["away"], rows[0]["sel"]) + name_score(g["home"], rows[1]["sel"])
            sb = name_score(g["away"], rows[1]["sel"]) + name_score(g["home"], rows[0]["sel"])
            if sb > sa:
                g[mkt] = [rows[1], rows[0]]
    tot = g.get("total")
    if tot and len(tot) == 2 and not tot[0]["sel"].lower().startswith("over"):
        g["total"] = [tot[1], tot[0]]
    return g


def flags(g, line, sport):
    """Rubric flags for one game. Spread numbers are the AWAY team's (line file convention)."""
    out, sides = [], {}
    sp = g.get("spread")
    if sp:
        sides["away"], sides["home"] = sp          # orient() put the away side first
    if sp and not thin(sp):
        pub = max(sp, key=lambda r: r["bets"])
        if pub["bets"] >= 65:
            out.append(f'PUB {pub["sel"]} {pub["bets"]}%')
        for r in sp:
            if r["handle"] - r["bets"] >= 15:
                out.append(f'SHARP {r["sel"]} +{r["handle"] - r["bets"]}')
    o, n = (f(line.get("spread_open")), f(line.get("spread_now"))) if line else (None, None)
    if o is not None and n is not None and n != o and sp:
        # Away spread +3 -> +5: away gets more points = market moved to HOME. -3 -> -5 = moved to AWAY.
        toward = "home" if n > o else "away"
        minority = None if thin(sp) else ("away" if sides["away"]["bets"] < 50 else ("home" if sides["home"]["bets"] < 50 else None))
        if minority and minority == toward:
            out.append(f'RLM {sides[toward]["sel"]} ({o:+g}→{n:+g})')
        if abs(n - o) >= 1.5:
            out.append(f'STEAM {toward} {abs(n - o):g}')
        lo, hi = sorted((abs(o), abs(n)))
        crossed = [k for k in KEYS[sport] if lo != hi and lo <= k <= hi and not (k == lo and o * n > 0 and lo == hi)]
        if crossed and (o * n >= 0):                  # same favorite: through or onto/off a key number
            out.append(f"KEY {','.join(map(str, crossed))}")
        elif o * n < 0:
            out.append("FLIP favorite")
    tot = g.get("total")
    if tot and not thin(tot):
        ov = next((r for r in tot if r["sel"].lower().startswith("over")), tot[0])
        if ov["bets"] >= 65 or ov["bets"] <= 35:
            out.append(f'PUB {"Over" if ov["bets"] >= 65 else "Under"} {max(ov["bets"], 100 - ov["bets"])}%')
        for r in tot:
            if r["handle"] - r["bets"] >= 15:
                out.append(f'SHARP {r["sel"].split()[0]} +{r["handle"] - r["bets"]}')
    to, tn = (f(line.get("total_open")), f(line.get("total_now"))) if line else (None, None)
    if to is not None and tn is not None and abs(tn - to) >= {"CFB": 2, "NFL": 1.5, "CBB": 3}.get(sport, 2):
        out.append(f"TOTAL {'up' if tn > to else 'down'} {abs(tn - to):g}")
    return out


def score(fl):
    """Sort key: sharp + RLM agreeing first, then any sharp/RLM, then public/steam only."""
    s = sum(3 for x in fl if x.startswith("RLM")) + sum(2 for x in fl if x.startswith("SHARP"))
    return s + sum(1 for x in fl if x.startswith(("STEAM", "KEY", "TOTAL", "PUB")))


def build(sport, games, updated, lines, lines_path):
    rows, used, unmatched = [], set(), []
    WO = week_open(sport)
    TP, _ = tr_proj(sport)
    for g in games:
        best, bs = None, 0.0
        for i, l in enumerate(lines):
            s = name_score(g["away"], l["away"]) + name_score(g["home"], l["home"])
            if s > bs:
                best, bs = i, s
        line = lines[best] if best is not None and bs >= 1.6 else None
        if line:
            used.add(best)
            line = dict(line, spread_open_espn=line.get("spread_open", ""), total_open_espn=line.get("total_open", ""), open_at="ESPN open")
            wo = WO.get(line.get("espn_id", ""))
            if wo:
                line.update(spread_open=wo["spread"] or line["spread_open"], total_open=wo["total"] or line["total_open"],
                            open_at=f"first pull {wo['at']}")
        else:
            unmatched.append(f'{g["away"]} @ {g["home"]}')
        orient(g)
        fl = flags(g, line, sport)
        tp, ts, flip = None, 0.0, False
        aw, hm = ((line or {}).get("away") or g["away"]), ((line or {}).get("home") or g["home"])
        for t in TP:
            # TR uses school/city names ("Indianapolis"); ESPN's full names ("Indianapolis Colts") match them best.
            # Neutral sites can list the teams the other way round: then the margin's sign flips.
            for rev in (False, True):
                ta, th = (t["home"], t["away"]) if rev else (t["away"], t["home"])
                sc = max(name_score(ta, aw) + name_score(th, hm), name_score(g["away"], ta) + name_score(g["home"], th))
                if sc > ts:
                    tp, ts, flip = t, sc, rev
        if tp and ts >= 1.4 and flip and tp.get("proj_home_margin") not in (None, ""):
            tp = dict(tp, proj_home_margin=-float(tp["proj_home_margin"]))
        tp = tp if ts >= 1.4 else None
        sp, tot, ml = g.get("spread") or [{}, {}], g.get("total") or [{}, {}], g.get("moneyline") or [{}, {}]
        rows.append({"pulled_et": NOW.isoformat(timespec="minutes"), "when": g["when"],
                     "away": g["away"], "home": g["home"], "espn_id": (line or {}).get("espn_id", ""),
                     "spread_open": (line or {}).get("spread_open", ""), "spread_now": (line or {}).get("spread_now", ""),
                     "total_open": (line or {}).get("total_open", ""), "total_now": (line or {}).get("total_now", ""),
                     "open_at": (line or {}).get("open_at", ""), "spread_open_espn": (line or {}).get("spread_open_espn", ""),
                     "total_open_espn": (line or {}).get("total_open_espn", ""),
                     "spr_away_sel": sp[0].get("sel", ""), "spr_away_handle": sp[0].get("handle", ""), "spr_away_bets": sp[0].get("bets", ""),
                     "spr_home_handle": sp[1].get("handle", ""), "spr_home_bets": sp[1].get("bets", ""),
                     "over_handle": tot[0].get("handle", ""), "over_bets": tot[0].get("bets", ""),
                     "ml_away_handle": ml[0].get("handle", ""), "ml_away_bets": ml[0].get("bets", ""),
                     "tr_proj_spread_away": (tp or {}).get("proj_home_margin", ""), "tr_proj_total": (tp or {}).get("proj_total", ""),
                     "flags": "; ".join(fl + (["THIN spread sample"] if g.get("spread") and thin(g["spread"]) else [])),
                     "signal": score(fl)})
    return rows, unmatched


def brief(sport, rows, updated, lines_path, unmatched):
    hdr = [f"# {sport} — DK splits + DraftKings lines, pulled {NOW:%Y-%m-%d %H:%M} ET",
           "",
           f"Splits: DK Network, {len(rows)} games (page 'Updated' times: {', '.join(sorted(set(u for u in updated if u))) or 'n/a'}). "
           f"Lines: {os.path.basename(lines_path) or 'none'} (DraftKings via ESPN; spread = AWAY team's number, open → now). "
           + (f"Open = the first pipeline pull that saw the game in the last {WEEK_OPEN_DAYS[sport]} days (ESPN's open is the schedule-release number), "
              "so movement is this week's market." if sport in WEEK_OPEN_DAYS else "Open = ESPN's DraftKings opener."),
           "Splits cells = handle% / bets% for the AWAY side (spread, ML) or the Over (total); home/Under = 100 minus.",
           "Flags: PUB 65%+ bets · SHARP handle−bets ≥ +15 · RLM line moved toward the side with <50% of bets · STEAM 1.5+ · KEY number crossed · TOTAL moved 2+ (CFB) / 1.5+ (NFL).",
           "Rows sorted by signal (RLM and SHARP first). Verify every flag against the numbers.",
           "TR proj = TeamRankings' final-score projection as the AWAY team's spread / total"
           + (f" (pulled {tr_proj(sport)[1]}); a model check only, never a signal." if tr_proj(sport)[1] else ": none pulled today or yesterday."),
           f"Unmatched to a DK line: {', '.join(unmatched) or 'none'}",
           "",
           "| Game | Start (ET) | Spread open→now | DK spr h/b | Total open→now | DK over h/b | DK ML h/b | TR proj | Flags |",
           "|---|---|---|---|---|---|---|---|---|"]
    body = []
    for r in sorted(rows, key=lambda r: (-r["signal"], r["when"])):
        so, sn = r["spread_open"], r["spread_now"]
        body.append(f'| {r["away"]} @ {r["home"]} | {r["when"]} | {so or "—"}→{sn or "—"} | {r["spr_away_handle"]}/{r["spr_away_bets"]} | '
                    f'{r["total_open"] or "—"}→{r["total_now"] or "—"} | {r["over_handle"]}/{r["over_bets"]} | '
                    f'{r["ml_away_handle"]}/{r["ml_away_bets"]} | '
                    + (f'{float(r["tr_proj_spread_away"]):+g} / {r["tr_proj_total"]}' if r.get("tr_proj_spread_away") not in (None, "") else "—")
                    + f' | {r["flags"] or "—"} |')
    return "\n".join(hdr + body) + "\n"


def write_csv(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        if rows:
            w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def main():
    sports = [s.upper() for s in sys.argv[1:]] or ["CFB", "NFL", "CBB"]
    status = {"pulled_et": NOW.isoformat(timespec="minutes"), "source": "DK Network splits + espn_lines.py"}
    os.makedirs(f"{OUT}/latest", exist_ok=True)
    for sport in sports:
        try:
            games, updated = pull_splits(sport)
            lines, lp = latest_lines(sport)
            rows, unmatched = build(sport, games, updated, lines, lp)
            write_csv(f"{OUT}/{NOW:%Y-%m-%d}/{NOW:%H%M}_dk_{sport}.csv", rows)
            write_csv(f"{OUT}/latest/dk_{sport}.csv", rows)
            with open(f"{OUT}/latest/brief_{sport}.md", "w", encoding="utf-8") as fh:
                fh.write(brief(sport, rows, updated, lp, unmatched))
            status[sport] = (f"ok {len(rows)} games, {sum(1 for r in rows if r['signal'])} with a flag, "
                             f"{len(unmatched)} without a DK line; page updated {', '.join(sorted(set(u for u in updated if u))) or 'n/a'}")
            if not rows:
                status[sport] = "0 games parsed (page empty, blocked, or layout changed)"
        except Exception as e:
            status[sport] = f"error: {e}"[:200]
    with open(f"{OUT}/latest/status.json", "w") as fh:
        json.dump(status, fh, indent=2)
    print(json.dumps(status, indent=2))
    return 1 if all(str(status.get(s, "")).startswith(("error", "0 games")) for s in sports) else 0


if __name__ == "__main__":
    sys.exit(main())
