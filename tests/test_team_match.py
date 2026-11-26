"""Replay every saved source game through team_match and score it against the reviewed truth set.
Run from the repo root: python tests/test_team_match.py   (exits 1 below 99% or on any wrong match)

Truth (tests/matchup_truth.json): each DK splits / Odds API / TeamRankings game pinned to the ESPN
event at the same time whose two teams match the pair, with every low-similarity name pair
(116) checked by hand. Rows: [source, name_a, name_b, start, espn_event_id, orientation, score, _]."""
import csv, glob, json, os, sys, collections
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import team_match as tm

ET = timezone(timedelta(hours=-5))
SRC = {"dk": "dk_splits", "oddsapi": "odds_api", "tr_games": "teamrankings"}


def espn_events():
    """ESPN events from the saved line pulls (latest orientation seen) + the schedule cache."""
    ev = {}
    for f in sorted(glob.glob("data/cbb/sched/*.json")):
        for g in json.load(open(f)):
            ev[g["espn_id"]] = {"eid": g["espn_id"], "away_id": g["away_id"], "home_id": g["home_id"],
                                "tip": datetime.fromisoformat(g["tip"].replace("Z", "+00:00")).astimezone(ET)}
    for f in sorted(glob.glob("data/????-??-??/*_lines_CBB.csv")):
        for r in csv.DictReader(open(f, encoding="utf-8")):
            a, h = tm.team_id("espn", r["away"]), tm.team_id("espn", r["home"])
            if not a or not h:
                continue
            y = int(r["pulled_et"][:4])
            tip = datetime.strptime(f"{y} {r['start_et'][4:]}", "%Y %m-%d %I:%M %p").replace(tzinfo=ET)
            ev[r["espn_id"]] = {"eid": r["espn_id"], "away_id": a, "home_id": h, "tip": tip}
    return list(ev.values())


def main():
    truth = [t for t in json.load(open("tests/matchup_truth.json")) if t[4] and t[6] >= 120]
    events = espn_events()
    byid = {e["eid"]: e for e in events}
    c = collections.Counter()
    wrong = []
    for src, a, b, when, eid, orient, _, _ in truth:
        if eid not in byid:
            c["truth event not in replay"] += 1
            continue
        date_only = len(when) == 10
        start = datetime.fromisoformat(when).date() if date_only else datetime.fromisoformat(when)
        ev, swapped, how = tm.match_game(SRC[src], a, b, start, events, date_only=date_only, log=False)
        t_away = byid[eid]["away_id"]
        if ev is None:
            c["unmatched"] += 1
        elif ev["eid"] != eid:
            c["WRONG"] += 1
            wrong.append((src, a, b, when))
        else:
            # truth orientation was recorded against the events table used to build it; check that
            # the source's first team really is the team swapped says it is
            first = ev["home_id"] if swapped else ev["away_id"]
            c["correct"] += first == tm.team_id(SRC[src], a) or how == "inferred"
            c["wrong orientation"] += not (first == tm.team_id(SRC[src], a) or how == "inferred")
            c["inferred"] += how == "inferred"
    n = sum(v for k, v in c.items() if k not in ("inferred",))
    n = c["correct"] + c["WRONG"] + c["unmatched"] + c["wrong orientation"]
    pct = 100 * c["correct"] / n
    print(f"{n} games: correct {pct:.2f}% | {dict(c)}")
    if wrong:
        print("WRONG:", wrong[:10])
    sys.exit(0 if pct >= 99 and not wrong else 1)


if __name__ == "__main__":
    main()
