"""Team and matchup matching across sources, keyed on ESPN team ids.

Why this exists (stress test, Nov 26 2026, 1,944 held-out source games):
  * ESPN flips home/away on the SAME event id between pulls at neutral sites (21 events this
    season), so any join that keys on "away @ home" breaks and openers change sign.
  * ESPN's opening spread can sit in DraftKings' orientation while its moneyline follows ESPN's
    (Alabama -700 ML at the open, spread stored as Alabama +12.5).
  * Fuzzy name matching is not safe on its own: token-set scoring rates "Arizona" vs "Northern
    Arizona" at 100, and prefix rules turn "Tennessee Martin" into Tennessee.
So: names resolve to ESPN team ids through a reviewed alias table (data/cbb/team_aliases.csv),
games match on the UNORDERED pair of ids plus the start time, orientation is computed per source,
and an unknown name never gets a fuzzy guess: it is inferred from a known opponent at the same
time (logged for review) or left unmatched (logged for review).

Usage:
    import team_match as tm
    tid = tm.team_id("odds_api", "Kansas St Wildcats")            # -> "2306"
    ev, swapped, how = tm.match_game("dk_splits", "Kansas State", "Alabama", start_dt, espn_events)
    open_away, note = tm.check_opener(spread_open_away, ml_away_open, ml_home_open)
"""
import csv, os, re, unicodedata
from datetime import timedelta

ALIASES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cbb", "team_aliases.csv")
REVIEW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cbb", "alias_review.csv")
SOURCES = ("espn", "dk_splits", "odds_api", "teamrankings", "torvik")


def key(name):
    """Spelling-insensitive key. Deliberately simple: the alias table carries the real knowledge."""
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[.'’()]", "", s).replace("-", " ")
    s = re.sub(r"\bsaint\b", "st", s)
    s = re.sub(r"\bstate\b", "st", s)
    return re.sub(r"\s+", " ", s).strip()


_ALIAS = None


def _load():
    global _ALIAS
    if _ALIAS is None:
        _ALIAS = {s: {} for s in SOURCES}
        _ALIAS["espn_abbr"] = {}
        with open(ALIASES, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["method"] == "espn_abbr":
                    _ALIAS["espn_abbr"][r["name"].upper()] = r["espn_id"]
                else:
                    _ALIAS.setdefault(r["source"], {})[r["name_key"]] = r["espn_id"]
    return _ALIAS


def team_id(source, name):
    """ESPN team id for a source's spelling, or None. Source-scoped exact lookup first, then ESPN's
    own spellings (location / display name). No fuzzy step, on purpose."""
    A = _load()
    k = key(name)
    if not k:
        return None
    return A.get(source, {}).get(k) or A["espn"].get(k) or (A["espn_abbr"].get(name.strip().upper())
                                                             if source in ("espn", "espn_abbr") else None)


def _log_review(source, name, espn_id, why, when):
    new = not os.path.exists(REVIEW)
    with open(REVIEW, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["source", "name", "suggested_espn_id", "why", "seen_for_game_at"])
        w.writerow([source, name, espn_id or "", why, when])


def match_game(source, name_a, name_b, start, events, window_h=3.0, date_only=False, log=True):
    """Find the ESPN event for a source game.

    events: iterable of dicts with "eid", "tip" (aware datetime), "away_id", "home_id".
    start:  aware datetime (or a date when date_only=True).
    Returns (event, swapped, how): swapped=True when the source lists the teams in the opposite
    order to ESPN's CURRENT orientation; how in {"pair", "inferred", None}. 'inferred' rows were
    matched through one known team and are logged to alias_review.csv for a human to confirm.
    """
    ta, tb = team_id(source, name_a), team_id(source, name_b)

    def near(ev):
        if date_only:
            return abs((ev["tip"].date() - start).days) <= 1
        return abs((ev["tip"] - start).total_seconds()) <= window_h * 3600

    def dist(ev):
        return abs((ev["tip"].date() - start).days) if date_only else abs((ev["tip"] - start).total_seconds())

    pool = sorted((e for e in events if near(e)), key=dist)
    if ta and tb:
        for ev in pool:
            if {ev["away_id"], ev["home_id"]} == {ta, tb}:
                return ev, ev["away_id"] != ta, "pair"
    known, unknown_name = (ta, name_b) if ta and not tb else ((tb, name_a) if tb and not ta else (None, None))
    if known:
        same_day = [e for e in pool if known in (e["away_id"], e["home_id"])
                    and (e["tip"].date() == (start if date_only else start.date()))]
        if len(same_day) == 1:
            ev = same_day[0]
            opp = ev["home_id"] if ev["away_id"] == known else ev["away_id"]
            if log:
                _log_review(source, unknown_name, opp, "opponent inferred from a known team at the same time",
                            str(start))
            swapped = (ev["home_id"] == ta) if ta else (ev["away_id"] == tb)
            return ev, swapped, "inferred"
    if log:
        for nm, t in ((name_a, ta), (name_b, tb)):
            if not t:
                _log_review(source, nm, "", "unknown name, no game anchor", str(start))
    return None, False, None


def _prob(ml):
    ml = float(ml)
    return -ml / (-ml + 100) if ml < 0 else 100 / (ml + 100)


def check_opener(spread_open_away, ml_away_open, ml_home_open):
    """ESPN's opening spread (AWAY team's number) vs ESPN's opening moneyline.
    Returns (spread_open_away, note): note "ok", "fixed" (sign flipped: the moneyline names a clear
    favorite, 8+ pts of no-vig win probability over 50%, and the spread names the other team by
    1.5+), "suspect" (they disagree but the moneyline is near pick'em: don't build RLM/STEAM/
    FIRST-MOVE on this opener) or "no_ml". Season check: 22 strong contradictions across 5 events
    (all neutral or known flips: ALA/KSU, BAY/GONZ, LOU/SJU, ARST/LBSU, KENT/CLEV)."""
    try:
        so = float(spread_open_away)
    except (TypeError, ValueError):
        return spread_open_away, "no_spread"
    try:
        pa, ph = _prob(ml_away_open), _prob(ml_home_open)
    except (TypeError, ValueError):
        return so, "no_ml"
    pa = pa / (pa + ph)
    ml_fav = "away" if pa > 0.5 else ("home" if pa < 0.5 else None)
    sp_fav = "away" if so < 0 else ("home" if so > 0 else None)
    if not ml_fav or not sp_fav or ml_fav == sp_fav:
        return so, "ok"
    if abs(pa - 0.5) >= 0.08 and abs(so) >= 1.5:
        return -so, "fixed"
    return so, "suspect"


def orient_to_espn(away_val, home_val, swapped):
    """Put a source's (away, home) pair of values into ESPN's current orientation."""
    return (home_val, away_val) if swapped else (away_val, home_val)
