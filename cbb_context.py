#!/usr/bin/env python3
"""Small-conference context for cbb_pull.py: rotation (DNP) and fatigue/travel/altitude flags,
from ESPN's free feeds. Imported by cbb_pull.py; can also run alone to warm the caches.

Why: books price 360+ teams with little attention; small-school absences rarely make the news,
and schedule spots (back-to-backs at holiday events, long road trips, altitude) are mechanical.
Each flag is TRACKED on closing-line value (did the line move our way after the flag?) before
anyone bets it.

Caches (so each ESPN page is read once):
  data/cbb/sched/<date>.json   every D-I game that day: ids, teams, home/away, neutral, final
  data/cbb/box/<date>.json     espn_id -> team_id -> [{id, name, min, starter, dnp}] for finals
ROT  = a core player (avg 24+ min over 3+ prior games) played < 50% of his average, or was
       listed DNP / missing, in his team's most recent game. Side = the opponent.
FAT  = played yesterday (B2B), or 2+ games in the prior 3 days (3-in-4), or today is a 3rd+
       straight road/neutral game. Side = the opponent of the tired team (none if both are).
ALT  = home team plays at altitude (4,500 ft+) and the visitor doesn't. Side = home.
"""
import json, os, sys, time, urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/"
OUT = "data/cbb"
CORE_MIN, CORE_GAMES, ROT_DROP = 24.0, 3, 0.5
HISTORY_DAYS = 21          # box scores kept in view for minutes averages
MAX_BOX_PER_RUN = 220      # summary pages fetched per run (backfill catches up over a few runs)
SEASON_START = date(2026, 11, 2)
# Home courts at ~4,500 ft or higher (ESPN location names).
ALTITUDE = {"Air Force", "Colorado", "Colorado State", "Wyoming", "Utah State", "Denver", "Northern Colorado",
            "New Mexico", "Northern Arizona", "BYU", "Utah", "Utah Valley", "Idaho State", "Montana State",
            "Nevada", "Weber State", "Southern Utah"}


def get(url, timeout=30):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 odds-pipeline"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception:
            if attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))


def _load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, separators=(",", ":"))


def schedule(day, today):
    """All D-I games on `day` (cached once the day is over)."""
    path = f"{OUT}/sched/{day.isoformat()}.json"
    if day < today:
        c = _load(path)
        if c is not None:
            return c
    data = get(f"{BASE}scoreboard?dates={day:%Y%m%d}&groups=50&limit=500")
    games = []
    for ev in data.get("events", []):
        comp = (ev.get("competitions") or [{}])[0]
        t = {c.get("homeAway"): c for c in comp.get("competitors", [])}
        if "home" not in t or "away" not in t:
            continue
        st = ((comp.get("status") or {}).get("type") or {})
        games.append({"espn_id": str(ev.get("id")), "date": day.isoformat(), "tip": ev.get("date"),
                      "away_id": str(t["away"].get("team", {}).get("id")), "home_id": str(t["home"].get("team", {}).get("id")),
                      "away": t["away"].get("team", {}).get("location", ""), "home": t["home"].get("team", {}).get("location", ""),
                      "neutral": bool(comp.get("neutralSite")), "final": bool(st.get("completed"))})
    if day < today and all(g["final"] for g in games):
        _save(path, games)
    return games


def box(espn_id):
    """team_id -> [{id, name, min, starter, dnp}] from ESPN's game summary."""
    data = get(f"{BASE}summary?event={espn_id}")
    out = {}
    for tp in (data.get("boxscore") or {}).get("players", []) or []:
        tid = str((tp.get("team") or {}).get("id"))
        players = []
        for st in tp.get("statistics", []) or []:
            keys = [k.lower() for k in (st.get("keys") or st.get("names") or st.get("labels") or [])]
            mi = next((i for i, k in enumerate(keys) if k in ("minutes", "min")), None)
            for a in st.get("athletes", []) or []:
                ath = a.get("athlete") or {}
                stats = a.get("stats") or []
                mins = None
                if mi is not None and mi < len(stats):
                    try:
                        mins = float(str(stats[mi]).split(":")[0])
                    except ValueError:
                        mins = None
                players.append({"id": str(ath.get("id")), "name": ath.get("displayName") or ath.get("shortName", ""),
                                "min": mins, "starter": bool(a.get("starter")),
                                "dnp": bool(a.get("didNotPlay")) or (mins is not None and mins == 0)})
        if players:
            out[tid] = players
    return out


def history(today):
    """(games by team, boxes by espn_id) for the last HISTORY_DAYS days, fetching missing boxes."""
    by_team, boxes, fetched, todo = {}, {}, 0, []
    start = max(SEASON_START, today - timedelta(days=HISTORY_DAYS))
    d = start
    while d < today:
        try:
            games = schedule(d, today)
        except Exception:
            games = []
        cache_path = f"{OUT}/box/{d.isoformat()}.json"
        cache = _load(cache_path) or {}
        for g in games:
            for side in ("away_id", "home_id"):
                by_team.setdefault(g[side], []).append(g)
            if g["final"] and g["espn_id"] in cache:
                boxes[g["espn_id"]] = cache[g["espn_id"]]
            elif g["final"]:
                todo.append((d, g["espn_id"]))
        d += timedelta(days=1)
    # newest days first, so today's flags are right even while older days backfill
    todo.sort(key=lambda x: x[0], reverse=True)
    dirty = {}
    for d, eid in todo[:MAX_BOX_PER_RUN]:
        try:
            b = box(eid)
        except Exception:
            continue
        fetched += 1
        if b:
            boxes[eid] = b
            dirty.setdefault(d, {})[eid] = b
        time.sleep(0.15)
    for d, add in dirty.items():
        p = f"{OUT}/box/{d.isoformat()}.json"
        cache = _load(p) or {}
        cache.update(add)
        _save(p, cache)
    for v in by_team.values():
        v.sort(key=lambda g: g["tip"] or g["date"])
    return by_team, boxes, {"box_fetched": fetched, "box_missing": max(0, len(todo) - MAX_BOX_PER_RUN)}


def rotation(team_id, by_team, boxes):
    """'ROT' notes for a team: core players who sat or barely played in the most recent game."""
    games = [g for g in by_team.get(team_id, []) if g["final"] and g["espn_id"] in boxes
             and team_id in boxes[g["espn_id"]]]
    if len(games) < CORE_GAMES + 1:
        return []
    last, prior = games[-1], games[:-1]
    mins = {}
    for g in prior:
        for p in boxes[g["espn_id"]][team_id]:
            if p["min"] is not None:
                mins.setdefault(p["id"], {"name": p["name"], "m": []})["m"].append(p["min"])
    lastp = {p["id"]: p for p in boxes[last["espn_id"]][team_id]}
    notes = []
    for pid, v in mins.items():
        if len(v["m"]) < CORE_GAMES:
            continue
        avg = sum(v["m"]) / len(v["m"])
        if avg < CORE_MIN:
            continue
        lp = lastp.get(pid)
        m = None if lp is None or lp["dnp"] else lp["min"]
        if m is None or m < ROT_DROP * avg:
            notes.append(f"{v['name']} {'DNP' if m is None else f'{m:.0f} min'} (avg {avg:.0f}) {last['date'][5:]}")
    return notes


def fatigue(team_id, by_team, today, home_today, neutral_today):
    prior = [g for g in by_team.get(team_id, []) if g["date"] < today.isoformat()]
    tags = []
    recent = [g for g in prior if (today - date.fromisoformat(g["date"])).days <= 3]
    if any((today - date.fromisoformat(g["date"])).days == 1 for g in prior):
        tags.append("B2B")
    if len(recent) >= 2:
        tags.append("3in4")
    away_today = neutral_today or not home_today
    if away_today:
        streak = 0
        for g in reversed(prior):
            if g["neutral"] or g["away_id"] == team_id:
                streak += 1
            else:
                break
        if streak >= 2:
            tags.append(f"ROAD{streak + 1}")
    return tags


def for_games(today, games, log=print):
    """espn_id -> {rot_flag, rot_side, fat_flag, fat_side, alt_flag} for today's games (cbb_pull's
    espn_games() rows with away/home 'id'). Never raises: returns ({}, status) on failure."""
    try:
        by_team, boxes, st = history(today)
    except Exception as e:
        return {}, f"error: {e}"[:160]
    out = {}
    for g in games:
        a, h = g["away"], g["home"]
        ra, rh = rotation(a.get("id", ""), by_team, boxes), rotation(h.get("id", ""), by_team, boxes)
        rot_flag = "; ".join(f"ROT {t['school']}: " + ", ".join(n) for t, n in ((a, ra), (h, rh)) if n)
        rot_side = "home" if ra and not rh else "away" if rh and not ra else ""
        fa = fatigue(a.get("id", ""), by_team, today, False, g["neutral"])
        fh = fatigue(h.get("id", ""), by_team, today, True, g["neutral"])
        fat_flag = "; ".join(x for x in (f"FAT {a['school']} {' '.join(fa)}" if fa else "",
                                         f"FAT {h['school']} {' '.join(fh)}" if fh else "") if x)
        fat_side = "home" if fa and not fh else "away" if fh and not fa else ""
        alt = (not g["neutral"]) and h["school"] in ALTITUDE and a["school"] not in ALTITUDE
        out[g["espn_id"]] = {"rot_flag": rot_flag, "rot_side": rot_side, "fat_flag": fat_flag,
                             "fat_side": fat_side, "alt_flag": f"ALT {h['school']}" if alt else ""}
    return out, (f"ok {len(boxes)} box scores in view ({st['box_fetched']} fetched this run, "
                 f"{st['box_missing']} still to backfill), {len(by_team)} teams")


if __name__ == "__main__":
    t = datetime.now(ET).date()
    _, s = for_games(t, [])
    print(s)
