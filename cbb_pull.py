#!/usr/bin/env python3
"""CBB model aggregate + line movement, run in GitHub Actions.

Separate from the NBA/NFL/CFB scans. Every game on the slate is logged (bet or
not) so model weights and bet thresholds can be fit later.

Sources
  - ESPN scoreboard API (schedule, tip, neutral site, ESPN's book line, finals)   required
  - Efficiency ratings: today's saved copy, else barttorvik.com/<season>_team_results.csv,
    else CollegeBasketballData /ratings/adjusted (CBBD_API_KEY or CBD_API_KEY, 1 request/day) preferred
    (if Torvik is unreachable, e.g. it blocks GitHub's servers, the slate is built from
    TR + BPI: TR ranks set the tier and Torvik's totals/ranks are left blank)
  - TeamRankings predictive ratings (newest data/*/HHMM_tr_ratings_CBB.csv)        optional
  - ESPN BPI via the power-index API (skipped if its layout isn't recognized)     optional
  - Lines: DraftKings open + current from ESPN's scoreboard; if ESPN has no opener for most
    games, CollegeBasketballData /lines open + current by book (one request per run); else
    ESPN's current line only. The source is labeled in line_source. (VSiN/Circa was dropped
    on Nov 14, 2026; repair_cbb_lines.py fixed the slates and results it left stale.)

Outputs
  data/cbb/YYYY-MM-DD/HHMM_slate.csv      one row per game for this run
  data/cbb/results/YYYY-MM-DD.csv         yesterday's finals vs model, open and close
  data/cbb/latest/slate.csv, results.csv, brief.md, status.json   fixed URLs for the Claude tasks
  (kept out of data/latest/, which publish_gist.py rewrites on every pull)

Usage: python cbb_pull.py [--date YYYY-MM-DD] [--season 2027] [--no-results]
Exit codes: 0 ok (source problems are listed in status.json), 2 no slate possible
(ESPN failed, or neither Torvik nor TR ratings are available).
"""
import argparse, csv, difflib, glob, io, json, os, re, sys, urllib.error, urllib.parse, urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
NOW = datetime.now(ET)
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/130 Safari/537.36", "Accept": "*/*"}
HCA = 3.0                                          # home-court points (ledger: Model weights)
# Nov 16 review (150 games): BPI MAE 10.00 (~ the opener), TR 10.92, Torvik stand-in 12.57 with a +4
# home bias, so BPI leads. Renormalized over the models present.
W = {"torvik": 0.2, "tr": 0.35, "bpi": 0.45}
MARKET_W = {1: 0.7, 2: 0.5, 3: 0.4}                # weight on the opener in the fair line
NOV_BUMP = 0.1                                     # extra market weight in November
# |fair - current| needed for a MODEL flag. Tier 1 (both top-100) gets no model flags: model edges went
# 1-6 there; Tier 1 is read through the market instead (MKT flags: line path + DK splits).
THRESH = {1: None, 2: 3.0, 3: 3.0}
CHECK_EDGE = 5.0          # model edges this big are usually data problems: flag as CHECK, track apart
TOTAL_GAP = 4.0           # retired as a flag Nov 18: de-biased, the stand-in total went 54-52 (no edge); the
                          # 70-38 "unders" record was early-season closing totals running high, not the model
TOTAL_MOVE = 1.0          # TOTAL (market) flag: total moved this far, toward the side with <50% of DK bets (RLM),
TOTAL_STEAM = 3.0         # or sharp money (handle - bets >= 15) on a side with a same-way move; 3+ = steam
FADE_FAV = 7.0            # home favorites of 7+ (home dog = FADE flag, tracked apart from the models)
SPLITS_MAX_AGE_H = 3.0    # DK splits (data/splits/latest/dk_CBB.csv) older than this are ignored
OUT = "data/cbb"


# ---------------------------------------------------------------- helpers
def get(url, timeout=40):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def norm(name):
    """School-name key that lines up ESPN, Torvik, TeamRankings and CBBD spellings."""
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
            "Texas A&M-CC": ["Texas A&M-Corpus Christi"], "FGCU": ["Florida Gulf Coast"],
            "Cal Baptist": ["California Baptist"], "AR-Pine Bluff": ["Arkansas-Pine Bluff", "Arkansas Pine Bluff"],
            "Prairie View": ["Prairie View A&M"], "UMKC": ["Kansas City"], "SIUE": ["SIU Edwardsville"],
            "UTSA": ["UT San Antonio"], "LIU": ["Long Island University", "Long Island"]}
NAME_CHECK_PTS = 12.0   # TR vs BPI home margins this far apart almost always means a name mismatch


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
        """names = (school, full name with mascot, ...). Exact matches first; trailing words are
        dropped only from the later (full) names, never from the school name, which otherwise
        turned "Florida Gulf Coast" into Florida and "California Baptist" into California."""
        for i, name in enumerate(names):
            k = norm(name)
            if not k:
                continue
            if k in self.by_key:
                return self.by_key[k]
            if i == 0 and len(names) > 1:
                continue
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
        # Newer payloads: DraftKings open and current ("close" until tip) per side.
        # Home spread "-7.5" = home favored by 7.5 = home margin +7.5.
        def side(market, who, when, field):
            v = (((odds.get(market) or {}).get(who) or {}).get(when) or {}).get(field)
            return first_num(str(v).lstrip("ouOU")) if v is not None else None   # totals read "o155.5"
        sp_open, sp_now = side("pointSpread", "home", "open", "line"), side("pointSpread", "home", "close", "line")
        to_open, to_now = side("total", "over", "open", "line"), side("total", "over", "close", "line")
        games.append({
            "espn_id": str(ev.get("id")), "tip_dt": tip, "tip": tip.strftime("%I:%M %p").lstrip("0"),
            "away": a, "home": h, "neutral": bool(comp.get("neutralSite")),
            "espn_book": (odds.get("provider") or {}).get("name", ""),
            "espn_line_home": -sp_now if sp_now is not None else line_home,
            "espn_total": to_now if to_now is not None else odds.get("overUnder"),
            "espn_open_home": -sp_open if sp_open is not None else None, "espn_open_total": to_open,
            "completed": bool(stype.get("completed")),
        })
    return games


def _parse_torvik_csv(text):
    """Torvik-style CSV (team, adjoe, adjde, adjt[, rank]) -> {team: ratings}."""
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


CBD = "https://www.cbbdata.com/api"
# cbbdata column names vary by version; first match wins.
CBD_COLS = {"team": ["team"], "adjoe": ["adj_o", "adjoe", "adj_oe"], "adjde": ["adj_d", "adjde", "adj_de"],
            "adjt": ["adj_t", "adjt", "adj_tempo", "tempo"], "rank": ["barthag_rank", "rank", "trank"]}


def _post_json(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={**UA, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def cbbdata_key(user, pw, email=""):
    """Log in to cbbdata (www.cbbdata.com, Torvik data) and return an API key, the way the R
    package's cbd_login() does. If the login fails and an email is given, register the account
    once (cbd_create_account()) and log in again."""
    def login():
        code, text = _post_json(f"{CBD}/auth/login", {"username": user, "password": pw})
        if code == 200:
            data = json.loads(text)
            key = next(iter(data.values())) if isinstance(data, dict) else (data[0] if isinstance(data, list) else data)
            if isinstance(key, str) and key:
                return key, ""
        return None, f"login HTTP {code}: {text[:150]}"
    key, err = login()
    if key or not email:
        return key, err
    code, text = _post_json(f"{CBD}/auth/register", {"username": user, "email": email,
                                                    "password": pw, "confirm_password": pw})
    if code not in (200, 201):
        return None, f"{err}; register HTTP {code}: {text[:150]}"
    key, err2 = login()
    return key, err2 and f"registered, but {err2}"


def cbbdata_ratings(season, key):
    """Torvik T-Rank ratings from cbbdata: one GET /api/torvik/ratings?year=<season>&key=<key>,
    returning a Parquet file (read with pyarrow, installed by the workflow)."""
    import pyarrow.parquet as pq
    try:
        with urllib.request.urlopen(urllib.request.Request(
                f"{CBD}/torvik/ratings?year={season}&key={key}", headers=UA), timeout=60) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:150]}")
    if not data.startswith(b"PAR1"):
        raise RuntimeError("did not return Parquet: " + data[:200].decode("utf-8", "replace"))
    rows = pq.read_table(io.BytesIO(data)).to_pylist()
    cols = list(rows[0]) if rows else []
    pick = {k: next((c for c in names if c in cols), None) for k, names in CBD_COLS.items()}
    if not all(pick[k] for k in ("team", "adjoe", "adjde", "adjt")):
        raise RuntimeError(f"columns not recognized: {cols}")
    if "year" in cols:
        rows = [r for r in rows if str(r["year"]) == str(season)] or rows
    out = {}
    for n, r in enumerate(sorted(rows, key=lambda r: -(r.get("barthag") or 0)), 1):
        try:
            out[str(r[pick["team"]]).strip()] = {
                "adjoe": float(r[pick["adjoe"]]), "adjde": float(r[pick["adjde"]]), "adjt": float(r[pick["adjt"]]),
                "rank": int(float(r[pick["rank"]])) if pick["rank"] and r[pick["rank"]] is not None else n}
        except (TypeError, ValueError):
            continue
    if len(out) < 300:
        raise RuntimeError(f"only {len(out)} teams for {season} (columns: {cols})")
    return out


PACE_PRIOR_GP = 8          # games of this season before it counts as much as last season's pace
PACE_TAG = 3.0             # projected possessions this far above/below average = FAST / SLOW
PACE_CLASH = 6.0           # teams' paces this far apart = CLASH (who controls tempo?)
CBBD_POSS = 68.0   # CBBD's adjusted ratings have no tempo: assume a typical D-I pace for every team


def cbbd_ratings(season, key):
    """Adjusted efficiency from CollegeBasketballData (api.collegebasketballdata.com; key shared
    with CollegeFootballData, ~1,000 requests/month across both). Exactly one request:
    GET /ratings/adjusted?season=<season>, Bearer auth. No tempo, so adjt = CBBD_POSS for all."""
    req = urllib.request.Request(f"https://api.collegebasketballdata.com/ratings/adjusted?season={season}",
                                 headers={**UA, "Accept": "application/json", "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        rows = json.loads(r.read().decode("utf-8", "replace"))
    g = lambda d, *ks: next((d[k] for k in ks if isinstance(d, dict) and d.get(k) is not None), None)
    out = {}
    for r in rows if isinstance(rows, list) else []:
        team, o, d = g(r, "team"), g(r, "offensiveRating", "offensive_rating"), g(r, "defensiveRating", "defensive_rating")
        if team is None or o is None or d is None:
            continue
        rank = g(g(r, "rankings") or {}, "net")
        out[str(team).strip()] = {"adjoe": float(o), "adjde": float(d), "adjt": CBBD_POSS,
                                  "rank": int(rank) if rank is not None else None}
    if len(out) < 300:
        keys = list(rows[0]) if isinstance(rows, list) and rows and isinstance(rows[0], dict) else str(rows)[:200]
        raise RuntimeError(f"CBBD returned {len(out)} usable teams for season {season} (fields: {keys})")
    missing = [t for t, v in out.items() if v["rank"] is None]
    if missing:                                    # rank by net rating if CBBD left any blank
        for n, t in enumerate(sorted(out, key=lambda t: out[t]["adjde"] - out[t]["adjoe"]), 1):
            out[t]["rank"] = n
    return out


def torvik_ratings(season):
    """Efficiency ratings, cheapest source first: today's saved copy (no request) ->
    barttorvik.com CSV (blocks GitHub's servers since Nov 2026) -> cbbdata Torvik ratings
    (login with CBD_USERNAME/CBD_PASSWORD, registering once if CBD_EMAIL is set; 1 data request)
    -> CollegeBasketballData adjusted efficiency (one request; CBBD_API_KEY or CBD_API_KEY; no tempo).
    A fresh pull is saved to data/cbb/torvik/YYYY-MM-DD.csv so later runs that day reuse it.
    Returns (ratings, source label)."""
    cache = f"{OUT}/torvik/{NOW:%Y-%m-%d}.csv"
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            return _parse_torvik_csv(f.read()), "saved copy from today"
    errors, R, src = [], None, ""
    try:                                           # free, no quota: try it first in case it unblocks
        R, src = _parse_torvik_csv(get(f"https://barttorvik.com/{season}_team_results.csv")), "barttorvik"
    except Exception as e:
        errors.append(f"barttorvik: {e}")
    user, pw = os.environ.get("CBD_USERNAME", "").strip(), os.environ.get("CBD_PASSWORD", "")
    secrets = [x for x in (pw, os.environ.get("CBD_EMAIL", "").strip()) if x]
    if R is None and user and pw:                  # cbbdata = Torvik's own numbers (with tempo)
        try:
            ckey, err = cbbdata_key(user, pw, os.environ.get("CBD_EMAIL", "").strip())
            if not ckey:
                raise RuntimeError(err)
            secrets.append(ckey)
            R, src = cbbdata_ratings(season, ckey), "cbbdata (Torvik)"
        except Exception as e:
            msg = f"cbbdata: {e}"
            for x in secrets:
                msg = msg.replace(x, "***")
            errors.append(msg)
    key = (os.environ.get("CBBD_API_KEY") or os.environ.get("CBD_API_KEY") or "").strip()
    if R is None and key:
        try:
            R, src = cbbd_ratings(season, key), f"CollegeBasketballData adjusted efficiency, {CBBD_POSS:g} poss"
        except Exception as e:
            errors.append(f"CBBD: {e}".replace(key, "***"))
    elif R is None:
        errors.append("CBBD: no CBBD_API_KEY/CBD_API_KEY secret")
    if R is None:
        raise RuntimeError("; ".join(errors))
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    with open(cache, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["team", "adjoe", "adjde", "adjt", "rank"])
        for t, v in sorted(R.items(), key=lambda kv: kv[1]["rank"]):
            w.writerow([t, v["adjoe"], v["adjde"], v["adjt"], v["rank"]])
    return R, src


def add_pace(R):
    """CBBD's adjusted ratings have no tempo (every team got 68 possessions, which squeezed its margins:
    finals ran ~1.2x its predictions). Fill adjt from TeamRankings' possessions-per-game where a team
    matches; leave 68 otherwise. Returns how many teams got a real pace."""
    paths = sorted(glob.glob("data/????-??-??/[0-9][0-9][0-9][0-9]_tr_stats_CBB.csv"))
    if not paths:
        return 0
    # Early season a team's few games (often buy games) say little about its pace, so blend this
    # season with last season, weighting this season by games played: w = gp / (gp + PACE_PRIOR_GP).
    start = date(NOW.year if NOW.month >= 8 else NOW.year - 1, 11, 1)
    gp = max(0.0, (NOW.date() - start).days / 3.5)            # ~1 game every 3.5 days
    w = gp / (gp + PACE_PRIOR_GP)
    pace = {}
    with open(paths[-1], encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("stat") == "possessions-per-game":
                def g(k):
                    try:
                        return float(r[k])
                    except (KeyError, TypeError, ValueError):
                        return None
                cur, prev = g("season"), g("prev_season")
                v = (w * cur + (1 - w) * prev) if cur is not None and prev is not None else (cur if cur is not None else prev)
                if v is not None:
                    pace[r["team"].strip()] = v
    if len(pace) < 300:
        return 0
    # TR's raw possessions run several above an adjusted tempo (early-season buy games, OT), which
    # pushed every projected total up ~9 points. Keep each team's pace RELATIVE to the field and
    # rescale so the D-I average stays at CBBD_POSS.
    good = [v for v in pace.values() if 55 <= v <= 85]
    scale = CBBD_POSS / (sum(good) / len(good)) if good else 1.0
    m, n = Matcher(pace, expand=True), 0
    for t, v in R.items():
        hit = m(t)
        if hit and 55 <= pace[hit] <= 85 and v.get("adjt") == CBBD_POSS:
            v["adjt"] = round(pace[hit] * scale, 2); n += 1
    return n


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


# Book preference when CBBD lists several (first present wins); otherwise the first listed.
CBBD_BOOKS = ["consensus", "draftkings", "espn bet", "fanduel", "bovada", "betmgm", "caesars"]


def cbbd_lines(day, key):
    """Opening + current lines by sportsbook from CollegeBasketballData, one request per run:
    GET /lines?startDateRange=<day 6 AM ET>&endDateRange=<next day 6 AM ET> (Bearer key).
    The raw response is saved to data/cbb/lines/YYYY-MM-DD/HHMM.json so movement can be traced.
    Returns {"away @ home" (norm()ed): {"provider", "spread", "spread_open", "total", "total_open",
    "home_ml", "away_ml"}} using one book per game (CBBD_BOOKS order). CFBD-style spreads are
    the home team's (-5.5 = home favored by 5.5)."""
    start = datetime(day.year, day.month, day.day, 6, tzinfo=ET)
    end = start + timedelta(days=1)
    q = urllib.parse.urlencode({"startDateRange": start.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                "endDateRange": end.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")})
    req = urllib.request.Request(f"https://api.collegebasketballdata.com/lines?{q}",
                                 headers={**UA, "Accept": "application/json", "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:150]}")
    games = json.loads(raw)
    os.makedirs(f"{OUT}/lines/{day.isoformat()}", exist_ok=True)
    with open(f"{OUT}/lines/{day.isoformat()}/{NOW:%H%M}.json", "w", encoding="utf-8") as f:
        f.write(raw)
    out = {}
    for g in games if isinstance(games, list) else []:
        books = [b for b in (g.get("lines") or []) if b.get("spread") is not None or b.get("overUnder") is not None]
        if not books:
            continue
        rank = lambda b: next((i for i, n in enumerate(CBBD_BOOKS) if n in str(b.get("provider", "")).lower()),
                              len(CBBD_BOOKS))
        b = min(books, key=rank)
        out[norm(g.get("awayTeam")) + " @ " + norm(g.get("homeTeam"))] = {
            "provider": b.get("provider"), "spread": b.get("spread"), "spread_open": b.get("spreadOpen"),
            "total": b.get("overUnder"), "total_open": b.get("overUnderOpen"),
            "home_ml": b.get("homeMoneyline"), "away_ml": b.get("awayMoneyline"),
            "books": sorted({str(x.get("provider")) for x in books})}
    return out


# ---------------------------------------------------------------- build
def tier_of(ra, rh):
    """Proxy until a conference/TV flag is added: both top-100 = T1, avg rank <= 200 = T2, else T3."""
    if max(ra, rh) <= 100:
        return 1
    if (ra + rh) / 2 <= 200:
        return 2
    return 3


def price(day, tier, cons, open_h, cur_h, tr_m, bpi_m, away, home):
    """Fair line, edge and flag for one game (home-margin convention). Shared by build_slate and
    repair_cbb_lines.py so a repaired row is priced exactly like a live one."""
    mw = min(0.9, MARKET_W[tier] + (NOV_BUMP if day.month == 11 else 0))
    anchor = open_h if open_h is not None else cur_h
    fair = mw * anchor + (1 - mw) * cons if anchor is not None else None
    edge = fair - cur_h if fair is not None and cur_h is not None else None
    moved = None
    if open_h is not None and cur_h is not None and cur_h != open_h:
        moved = (cur_h - open_h) * (cons - open_h) > 0
    flag = ""
    suspect = tr_m is not None and bpi_m is not None and abs(tr_m - bpi_m) > NAME_CHECK_PTS
    th = THRESH.get(tier)
    if edge is not None and th is not None and abs(edge) >= th and not suspect:
        side = home if edge > 0 else away
        flag = f"{'CHECK' if abs(edge) >= CHECK_EDGE else 'EDGE'} {side} {abs(edge):.1f}"
        flag += " · moved toward model" if moved is True else (" · line moved away" if moved is False else "")
    return {"fair_home_margin": rnd(fair), "edge_pts": rnd(edge),
            "gap_cons_vs_open": rnd(cons - open_h) if open_h is not None else None,
            "gap_cons_vs_cur": rnd(cons - cur_h) if cur_h is not None else None,
            "moved_toward_model": moved, "flag": flag,
            "flag_side": ("home" if edge > 0 else "away") if flag else "", "suspect": suspect}


def dk_splits_cbb():
    """espn_id -> DK Network spread/total handle and bets (dk_splits.py output), if fresh."""
    p = "data/splits/latest/dk_CBB.csv"
    if not os.path.exists(p):
        return {}, "no dk_CBB.csv"
    with open(p, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("espn_id")]
    if not rows:
        return {}, "dk_CBB.csv has no games joined to ESPN"
    age = (NOW - datetime.fromisoformat(rows[0]["pulled_et"])).total_seconds() / 3600
    if age > SPLITS_MAX_AGE_H:
        return {}, f"stale ({age:.1f} h old)"
    return {r["espn_id"]: r for r in rows}, f"ok {len(rows)} games, pulled {rows[0]['pulled_et'][11:16]}"


def market_read(sp, open_h, cur_h, away, home):
    """MKT flags from the DraftKings line path (home margin) and DK splits (away side handle/bets).
    RLM = line moved toward the side with under 50% of bets; SHARP = handle minus bets >= 15;
    STEAM = 1.5+ move. Thin samples (any 0% or 100% cell) are not read."""
    out = []
    num = lambda k: float(sp[k]) if sp and sp.get(k) not in (None, "", "None") else None
    ah, ab = num("spr_away_handle"), num("spr_away_bets")
    thin = ah is None or ab is None or ah in (0, 100) or ab in (0, 100)
    moved = None if open_h is None or cur_h is None or cur_h == open_h else cur_h - open_h
    toward = None if moved is None else (home if moved > 0 else away)    # home margin up = market to home
    if not thin:
        if ah - ab >= 15:
            out.append(f"SHARP {away} +{ah - ab:.0f}")
        elif ab - ah >= 15:
            out.append(f"SHARP {home} +{ab - ah:.0f}")
        minority = away if ab < 50 else (home if ab > 50 else None)
        if toward and minority == toward:
            out.append(f"RLM {toward} ({open_h:+.1f}→{cur_h:+.1f})")
        if max(ab, 100 - ab) >= 65:
            out.append(f"PUB {away if ab >= 65 else home} {max(ab, 100 - ab):.0f}%")
    if moved is not None and abs(moved) >= 1.5:
        out.append(f"STEAM {toward} {abs(moved):.1f}")
    return out, ("thin" if thin and sp else ("n/a" if not sp else f"{ah:.0f}/{ab:.0f}"))


def tr_projections():
    """(away, home) TR names -> TeamRankings final-score projection row (teamrankings_pull.py, daily
    ~3:29 PM, Tier 1-type games only), if the newest file is from today or yesterday."""
    paths = sorted(glob.glob("data/????-??-??/[0-9][0-9][0-9][0-9]_tr_proj_CBB.csv"))
    if not paths:
        return {}
    day = datetime.strptime(os.path.basename(os.path.dirname(paths[-1])), "%Y-%m-%d").date()
    if (NOW.date() - day).days > 1:
        return {}
    with open(paths[-1], encoding="utf-8") as fh:
        return {(r["away"].strip(), r["home"].strip()): r for r in csv.DictReader(fh) if r.get("status") == "ok"}


def total_read(sp, open_t, cur_t):
    """TOTAL (market) flag from the DraftKings total path + DK splits (Over handle/bets), the same rule
    as MKT for sides: RLM (total moved toward the side with <50% of bets), or SHARP money with a
    same-way move. Returns (flag, side, note)."""
    num = lambda k: float(sp[k]) if sp and sp.get(k) not in (None, "", "None") else None
    oh, ob = num("over_handle"), num("over_bets")
    try:
        mv = None if open_t in (None, "") or cur_t in (None, "") else float(cur_t) - float(open_t)
    except ValueError:
        mv = None
    thin = oh is None or ob is None or not (2 < oh < 98) or not (2 < ob < 98)
    if thin or not mv or abs(mv) < TOTAL_MOVE:
        return "", "", ("thin" if sp and thin else "")
    side = "over" if mv > 0 else "under"
    side_bets = ob if side == "over" else 100 - ob
    side_edge = (oh - ob) if side == "over" else (ob - oh)        # handle minus bets on the side it moved to
    tags = []
    if side_edge < 0:            # the money is on the other side: not a market read (Jeremy's rubric)
        return "", "", ""
    if side_bets < 50:
        tags.append(f"RLM {side.title()} ({float(open_t):g}→{float(cur_t):g}, {side_bets:.0f}% of bets)")
    if side_edge >= 15:
        tags.append(f"SHARP {side.title()} +{side_edge:.0f}")
    if not tags:
        return "", "", ""
    if abs(mv) >= TOTAL_STEAM:
        tags.append(f"STEAM {abs(mv):g}")
    return "TOTAL-MKT " + " + ".join(tags), side, ""


def build_slate(day, games, R, TR, B, lines=None):
    SPL, _ = dk_splits_cbb()
    mt = Matcher(R) if R else None
    mtr = Matcher(TR, expand=True) if TR else None
    # Without Torvik, tiers come from TR rank (1 = best rating).
    tr_rank = {t: i for i, t in enumerate(sorted(TR, key=TR.get, reverse=True), 1)} if TR else {}
    mb = Matcher(B) if B else None
    lines = lines or {}
    lkeys = list(lines)

    def lines_for(g):
        cands = lambda t: [norm(x) for x in (t["school"], t["short"], t["full"], t["abbr"]) if x]
        for ka in cands(g["away"]):
            for kh in cands(g["home"]):
                if ka + " @ " + kh in lines:
                    return lines[ka + " @ " + kh]
        best = difflib.get_close_matches(norm(g["away"]["school"]) + " @ " + norm(g["home"]["school"]),
                                         lkeys, n=1, cutoff=0.85)
        return lines[best[0]] if best else None

    out, unmatched, name_checks = [], [], []
    # Picks-grid names can differ from ratings names ("N Carolina"), so key projections by the ratings name.
    TRP = {(mtr(a, a), mtr(h, h)): r for (a, h), r in tr_projections().items()} if mtr else {}
    tempos = [v["adjt"] for v in R.values()] if R else []
    avg_t = sum(tempos) / len(tempos) if tempos else None
    has_pace = bool(tempos) and max(tempos) - min(tempos) > 1      # all 68s = CBBD without TR pace
    for g in games:
        if g["tip_dt"] <= NOW or g["completed"]:
            continue                      # already tipped: the last pre-tip snapshot is the close
        hca = 0 if g["neutral"] else HCA
        tv_m = tv_t = tv_ra = tv_rh = None
        proj_poss, pace_tag = None, ""
        trp_m = trp_t = None
        parts, tr_m, bpi_m, ra, rh = [], None, None, None, None
        if mt:
            ta = mt(g["away"]["school"], g["away"]["full"])
            th = mt(g["home"]["school"], g["home"]["full"])
            if not ta or not th:
                unmatched.append(f'{g["away"]["full"]} @ {g["home"]["full"]}')
                continue
            tv_m, tv_t = torvik_predict(ta, th, R, g["neutral"])
            parts.append(("torvik", tv_m))
            if has_pace:
                pa_t, ph_t = R[ta]["adjt"], R[th]["adjt"]
                proj_poss = pa_t * ph_t / avg_t
                tags = (["FAST"] if proj_poss - avg_t >= PACE_TAG else ["SLOW"] if avg_t - proj_poss >= PACE_TAG else [])
                if abs(pa_t - ph_t) >= PACE_CLASH:
                    tags.append("CLASH")
                pace_tag = " ".join(tags)
            tv_ra, tv_rh = ra, rh = R[ta]["rank"], R[th]["rank"]
        if mtr:
            a2, h2 = mtr(g["away"]["school"], g["away"]["full"]), mtr(g["home"]["school"], g["home"]["full"])
            if a2 and h2:
                tr_m = TR[h2] - TR[a2] + hca; parts.append(("tr", tr_m))
                pj = TRP.get((a2, h2))
                if pj and pj.get("proj_home_margin") not in (None, ""):
                    trp_m, trp_t = float(pj["proj_home_margin"]), float(pj["proj_total"])
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

        src, open_h, cur_h, open_t, cur_t = "", None, None, None, None
        if g.get("espn_open_home") is not None and g["espn_line_home"] is not None:
            # ESPN's DraftKings opener + current: the main line source.
            open_h, cur_h = g["espn_open_home"], g["espn_line_home"]
            open_t, cur_t = g.get("espn_open_total"), g["espn_total"]
            src = f'ESPN/{g["espn_book"] or "book"} open+now'
        cb = lines_for(g) if cur_h is None else None
        if cb and cb["spread"] is not None:
            # CBBD spread is the home team's: -5.5 = home favored by 5.5 = home margin +5.5.
            cur_h = -float(cb["spread"])
            open_h = -float(cb["spread_open"]) if cb["spread_open"] is not None else None
            cur_t = cb["total"]
            open_t = cb["total_open"]
            src = f'CBBD/{cb["provider"]}'
        if cur_h is None and g["espn_line_home"] is not None:
            cur_h, cur_t = g["espn_line_home"], g["espn_total"]
            src = f'ESPN/{g["espn_book"] or "book"} (current only)'

        tier = tier_of(ra, rh)
        p = price(day, tier, cons, open_h, cur_h, tr_m, bpi_m, g["away"]["school"], g["home"]["school"])
        if p.pop("suspect"):
            name_checks.append(f'{g["away"]["school"]} @ {g["home"]["school"]}: TR {tr_m:+.1f} vs BPI {bpi_m:+.1f}')
        away_s, home_s = g["away"]["school"], g["home"]["school"]
        mkt, spl = market_read(SPL.get(g["espn_id"]), open_h, cur_h, away_s, home_s)
        # Tier 1 is read through the market: a MKT flag needs RLM, or SHARP money with a move the same way.
        mkt_flag = ""
        rlm = next((x for x in mkt if x.startswith("RLM")), None)
        sharp = next((x for x in mkt if x.startswith("SHARP")), None)
        steam = next((x for x in mkt if x.startswith("STEAM")), None)
        if rlm:
            mkt_flag = rlm
        elif sharp and steam and sharp.split()[1] == steam.split()[1]:
            mkt_flag = f"{sharp} + {steam}"
        # Both MKT kinds back the side the line moved toward (home margin up = toward home).
        mkt_side = ("home" if cur_h > open_h else "away") if mkt_flag else ""
        tot_flag, tot_side, _ = total_read(SPL.get(g["espn_id"]), open_t, cur_t)
        # The stand-in model total is logged (torvik_total, total_model_gap) for calibration only.
        tot_gap = rnd(tv_t - float(cur_t)) if tv_t is not None and cur_t not in (None, "") else None
        fade = "FADE home fav" if (not g["neutral"] and cur_h is not None and cur_h >= FADE_FAV) else ""
        out.append({
            "date": day.isoformat(), "tip_et": g["tip"], "espn_id": g["espn_id"],
            "away": g["away"]["school"], "home": g["home"]["school"], "site": "N" if g["neutral"] else "H",
            "tier": tier, "torvik_rank_away": tv_ra, "torvik_rank_home": tv_rh,
            "torvik_home_margin": rnd(tv_m), "torvik_total": rnd(tv_t), "tr_home_margin": rnd(tr_m),
            "bpi_home_margin": rnd(bpi_m), "consensus_home_margin": rnd(cons),
            "line_source": src, "open_home_margin": open_h, "cur_home_margin": cur_h,
            "open_total": open_t, "cur_total": cur_t, **p,
            "dk_spr_away_h_b": spl, "market": "; ".join(mkt), "mkt_flag": mkt_flag, "mkt_side": mkt_side,
            "total_flag": tot_flag, "total_side": tot_side, "total_model_gap": tot_gap,
            "proj_poss": rnd(proj_poss), "pace_tag": pace_tag,
            "tr_proj_home_margin": rnd(trp_m), "tr_proj_total": rnd(trp_t),
            "tr_total_gap": rnd(trp_t - float(cur_t)) if trp_t is not None and cur_t not in (None, "") else None,
            "fade_flag": fade,
            "pulled_et": NOW.isoformat(timespec="minutes"),
        })
    return out, unmatched, name_checks


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
            "mkt_flag": r.get("mkt_flag", ""), "mkt_side": r.get("mkt_side", ""),
            "total_flag": r.get("total_flag", ""), "total_side": r.get("total_side", ""),
            "proj_poss": num("proj_poss"), "pace_tag": r.get("pace_tag", ""),
            "tr_proj_home_margin": num("tr_proj_home_margin"), "tr_proj_total": num("tr_proj_total"),
            "fade_flag": r.get("fade_flag", ""),
            "total_result": (None if num("cur_total") is None or total == num("cur_total")
                             else ("over" if total > num("cur_total") else "under")),
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
    def rec(sub, side_key):
        g = [r for r in sub if r.get(side_key) and r.get("home_covered") in ("True", "False")]
        w = sum((r[side_key] == "home") == (r["home_covered"] == "True") for r in g)
        return f"{w}-{len(g) - w}" + (f" ({100 * w / len(g):.1f}%)" if g else "")
    edge = [r for r in rows if r.get("flag_at_close", "").startswith("EDGE")]
    check = [r for r in rows if r.get("flag_at_close", "").startswith("CHECK")]
    t1m = [r for r in rows if r.get("tier") == "1" and r.get("mkt_flag")]
    mk = [r for r in rows if r.get("mkt_flag")]
    fade = [dict(r, fade_side="away") for r in rows if r.get("fade_flag")]
    for r in rows:                     # results files before Nov 17 carry no total_result column
        if r.get("total_result") not in ("over", "under") and f(r, "final_total") is not None and f(r, "close_total") is not None:
            ft, ct = f(r, "final_total"), f(r, "close_total")
            r["total_result"] = "over" if ft > ct else ("under" if ft < ct else "push")
    graded_t = [r for r in rows if r.get("total_result") in ("over", "under")]
    tots = [r for r in graded_t if r.get("total_side") and r.get("total_flag", "").startswith("TOTAL-MKT")]
    tw = sum(r["total_side"] == r["total_result"] for r in tots)
    # Retired model-total rule, re-derived from the logged numbers (stand-in total 4+ off the close).
    old = [dict(r, total_side="over" if f(r, "torvik_total") > f(r, "close_total") else "under") for r in graded_t
           if f(r, "torvik_total") is not None and abs(f(r, "torvik_total") - f(r, "close_total")) >= TOTAL_GAP]
    ow = sum(r["total_side"] == r["total_result"] for r in old)
    uw = sum(r["total_result"] == "under" for r in graded_t)
    out += ["", "Records vs the closing line (break-even at -110 is 52.4%):",
            f"- All model flags (any tier, as logged): {rec(rows, 'flag_side')}",
            f"- EDGE flags (Tier 2-3, edge 3-5 pts; from Nov 16): {rec(edge, 'flag_side')}",
            f"- CHECK flags (edge 5+, usually data problems): {rec(check, 'flag_side')}",
            f"- MKT flags, Tier 1 (RLM, or sharp money + steam): {rec(t1m, 'mkt_side')}",
            f"- MKT flags, all tiers: {rec(mk, 'mkt_side')}",
            f"- FADE (away side vs a home favorite of {FADE_FAV:g}+): {rec(fade, 'fade_side')}",
            f"- TOTAL-MKT flags (total RLM, or sharp money + same-way move; from Nov 18): {tw}-{len(tots) - tw}" +
            (f" ({100 * tw / len(tots):.1f}%)" if tots else ""),
            f"- Baseline, every game's Under vs the closing total: {uw}-{len(graded_t) - uw}" +
            (f" ({100 * uw / len(graded_t):.1f}%)" if graded_t else "") + " (a TOTAL family must beat this)",
            *[f"- Pace {t} games, Under vs the closing total: " +
              (lambda g: f"{sum(r['total_result'] == 'under' for r in g)}-{sum(r['total_result'] == 'over' for r in g)}")(
                  [r for r in graded_t if t in r.get("pace_tag", "").split()]) for t in ("FAST", "SLOW", "CLASH")],
            "- TOTAL-MKT agreeing with pace (Under + SLOW, Over + FAST): " +
            (lambda g: f"{sum(r['total_side'] == r['total_result'] for r in g)}-{sum(r['total_side'] != r['total_result'] for r in g)}")(
                [r for r in tots if (r["total_side"] == "under" and "SLOW" in r.get("pace_tag", "")) or
                 (r["total_side"] == "over" and "FAST" in r.get("pace_tag", ""))]),
            f"- Retired model-total rule (stand-in total {TOTAL_GAP:g}+ off the close, not de-biased): {ow}-{len(old) - ow}",
            f"- Totals MAE: Torvik {mae('torvik_total', 'final_total')} · TR projection {mae('tr_proj_total', 'final_total')} vs closing total {mae('close_total', 'final_total')}",
            f"- TR projected margin MAE (Tier 1-type games only): {mae('tr_proj_home_margin')} vs closing line {mae('close_home_margin', sub=[r for r in rows if f(r, 'tr_proj_home_margin') is not None])}",
            "- TR projected total 4+ off the close (side vs the closing total): " +
            (lambda g: f"{sum((f(r, 'tr_proj_total') > f(r, 'close_total')) == (r['total_result'] == 'over') for r in g)}-"
                       f"{sum((f(r, 'tr_proj_total') > f(r, 'close_total')) != (r['total_result'] == 'over') for r in g)}")(
                [r for r in graded_t if f(r, "tr_proj_total") is not None and abs(f(r, "tr_proj_total") - f(r, "close_total")) >= 4]),
            "", "Flag families overlap (a game can be EDGE, FADE and TOTAL at once); judge each on its own record.",
            "Change weights or thresholds only after ~300 graded games, and only where a gap holds in every tier."]
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
             f"Model flags (Tier 2-3 only): EDGE = edge {THRESH[2]}-{CHECK_EDGE:g} pts, CHECK = {CHECK_EDGE:g}+ (verify names/rosters first). "
             "Fair = market weight x opener + the rest x model consensus. "
             f"MKT = market read from the DraftKings line path + DK splits (RLM, or sharp money with a same-way move); "
             f"TOTAL = market read on the total (RLM, or sharp money with a same-way move of {TOTAL_MOVE:g}+); FADE = home favorite of {FADE_FAV:g}+ (tracked, not a model call).",
             f"Sources: {status['sources']} · DK splits {status.get('dk_splits', 'n/a')}", ""]
    rows = [r for r in slate if r["cur_home_margin"] is not None]
    t1 = sorted([r for r in rows if r["tier"] == 1], key=lambda r: (r["mkt_flag"] == "", r["tip_et"]))
    lines += ["## Tier 1 market board (both teams top-100: read the market, not the models)", "",
              "| Game (ET) | Site | Open→now | Total open→now | DK spr h/b (away) | Market | MKT flag | Cons / Fair · TR proj (info) |",
              "|---|---|---|---|---|---|---|---|"]
    for r in t1:
        lines.append(f"| {r['away']} @ {r['home']} {r['tip_et']} | {r['site']} | {f(r['open_home_margin'])}→{f(r['cur_home_margin'])} | "
                     f"{r['open_total'] or '—'}→{r['cur_total'] or '—'} | {r['dk_spr_away_h_b']} | {r['market'] or '—'} | "
                     f"{r['mkt_flag'] or '—'} | {f(r['consensus_home_margin'])} / {f(r['fair_home_margin'])}"
                     + (f" · TR proj {f(r['tr_proj_home_margin'])}, total {r['tr_proj_total']:g}" if r.get("tr_proj_total") is not None else "")
                     + " |")
    if not t1:
        lines.append("| no Tier 1 games with a line | | | | | | | |")
    lines += ["", "## All games (flags first)", "",
              "| Game (ET) | Site | Tier | Line src | Open→now | Total open→now | Torvik | TR | BPI | Cons | Fair | Edge | To model | DK h/b | Flag | MKT | TOTAL | FADE |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    anyflag = lambda r: bool(r["flag"] or r["mkt_flag"] or r["total_flag"])
    rows.sort(key=lambda r: (not anyflag(r), -abs(r["edge_pts"] or 0)))
    for r in rows:
        moved = "—" if r["moved_toward_model"] is None else ("yes" if r["moved_toward_model"] else "no")
        lines.append(f"| {r['away']} @ {r['home']} {r['tip_et']} | {r['site']} | {r['tier']} | {r['line_source']} | "
                     f"{f(r['open_home_margin'])}→{f(r['cur_home_margin'])} | {r['open_total'] or '—'}→{r['cur_total'] or '—'} | "
                     f"{f(r['torvik_home_margin'])} | {f(r['tr_home_margin'])} | {f(r['bpi_home_margin'])} | "
                     f"{f(r['consensus_home_margin'])} | {f(r['fair_home_margin'])} | {f(r['edge_pts'])} | {moved} | "
                     f"{r['dk_spr_away_h_b']} | {r['flag'] or '—'} | {r['mkt_flag'] or '—'} | {(r['total_flag'] + (' · ' if r['total_flag'] and r.get('pace_tag') else '') + (r.get('pace_tag') or '')) or '—'} | {r['fade_flag'] or '—'} |")
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

    # Fix slate rows priced from stale VSiN Circa snapshots (Nov 14-15, 2026, and any run of the
    # old code) before anything below grades them. Does nothing once everything is fixed.
    try:
        sys.modules.setdefault("cbb_pull", sys.modules[__name__])   # share this module, not a 2nd copy
        import repair_cbb_lines
        fixed, days = repair_cbb_lines.repair(log=lambda *a: None)
        if fixed:
            status["repaired"] = f"{fixed} stale Circa slate rows re-lined from DraftKings ({', '.join(sorted(days))})"
    except Exception as e:
        status["repaired"] = f"error: {e}"; soft_fail = True

    try:
        games = espn_games(day); status["espn"] = f"ok {len(games)} games"
    except Exception as e:
        games = None; status["espn"] = f"error: {e}"
    try:
        R, tsrc = torvik_ratings(args.season); status["torvik"] = f"ok {len(R)} teams ({tsrc})"
        if "CollegeBasketballData" in tsrc or "saved copy" in tsrc:
            npace = add_pace(R)
            if npace:
                status["torvik"] += f"; pace from TeamRankings for {npace} teams"
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

    os.makedirs(f"{OUT}/latest", exist_ok=True)
    if R is None and TR:
        status["alert"] = ("Torvik unavailable: slate built from TR + BPI only "
                           "(tiers from TR rank; no Torvik totals)")
    if games is None or (R is None and not TR):
        status["alert"] = "no slate written: ESPN failed, or neither Torvik nor TR ratings are available"
        json.dump(status, open(f"{OUT}/latest/status.json", "w"), indent=2)
        print(json.dumps(status, indent=2)); sys.exit(2)

    lines = {}
    lkey = (os.environ.get("CBBD_API_KEY") or os.environ.get("CBD_API_KEY") or "").strip()
    upcoming = [g for g in games if g["tip_dt"] > NOW and not g["completed"]]
    priced = [g for g in upcoming if g["espn_line_home"] is not None]
    espn_open = sum(1 for g in priced if g.get("espn_open_home") is not None)
    status["espn_lines"] = f"{espn_open}/{len(priced)} priced games have ESPN's DraftKings opener"
    if not upcoming:
        status["cbbd_lines"] = "skipped: every game today has tipped (nothing to price)"
    elif priced and espn_open >= 0.8 * len(priced):
        status["cbbd_lines"] = "skipped: ESPN has DraftKings open + current (saves the CBBD monthly quota)"
    elif not lkey:
        status["cbbd_lines"] = "skipped: no CBBD_API_KEY/CBD_API_KEY secret"
    else:
        try:
            lines = cbbd_lines(day, lkey)
            books = sorted({b for v in lines.values() for b in v["books"]})
            status["cbbd_lines"] = f"ok {len(lines)} games; books: {', '.join(books) or 'none'}"
            # Sign check vs ESPN's line (same home-margin convention): should mostly agree.
            pairs = []
            for g in games:
                k = norm(g["away"]["school"]) + " @ " + norm(g["home"]["school"])
                if k in lines and lines[k]["spread"] is not None and g["espn_line_home"] not in (None, 0):
                    pairs.append((-float(lines[k]["spread"]) > 0) == (g["espn_line_home"] > 0))
            status["cbbd_sign_check"] = f"{sum(pairs)}/{len(pairs)} games agree with ESPN on the favorite"
        except Exception as e:
            status["cbbd_lines"] = f"error: {e}".replace(lkey, "***")

    status["dk_splits"] = dk_splits_cbb()[1]
    slate, unmatched, name_checks = build_slate(day, games, R, TR, B, lines)
    if name_checks:
        status["check_names"] = name_checks[:40]   # flags suppressed on these games
    status.update({"games_written": len(slate),
                   "with_line": sum(1 for r in slate if r["cur_home_margin"] is not None),
                   "with_espn_open": sum(1 for r in slate if r["line_source"].endswith("open+now")),
                   "flags": sum(1 for r in slate if r["flag"]),
                   "mkt_flags": sum(1 for r in slate if r["mkt_flag"]),
                   "tier1_mkt_flags": sum(1 for r in slate if r["mkt_flag"] and r["tier"] == 1),
                   "total_flags": sum(1 for r in slate if r["total_flag"]),
                   "fade_flags": sum(1 for r in slate if r["fade_flag"]), "unmatched": unmatched[:40]})
    status["sources"] = " · ".join(f"{k} {status[k]}" for k in ("espn", "espn_lines", "torvik", "tr", "bpi"))
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
