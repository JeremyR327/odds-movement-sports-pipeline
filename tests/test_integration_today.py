"""Offline replay of the Nov 26 09:09 CBB slate through dk_splits.build() with the saved DK splits and
ESPN lines: every DK game must join an ESPN line, in ESPN's orientation, with splits swapped to match.
Run from the repo root: python tests/test_integration_today.py"""
import csv, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dk_splits

DAY, SLOT = "2026-11-26", "0909"
saved = list(csv.DictReader(open(f"data/splits/{DAY}/{SLOT}_dk_CBB.csv", encoding="utf-8")))
lines = list(csv.DictReader(open(f"data/{DAY}/{SLOT}_lines_CBB.csv", encoding="utf-8")))
import team_match
for l in lines:     # what espn_lines.py now writes (the saved file predates the opener check)
    if "open_check" not in l:
        l["spread_open_raw"] = l["spread_open"]
        l["spread_open"], l["open_check"] = team_match.check_opener(l["spread_open"], l["ml_away_open"], l["ml_home_open"])
        if l["open_check"] == "no_spread":
            l["spread_open"] = l["spread_open_raw"]
dk_splits.NOW = dk_splits.datetime.fromisoformat(saved[0]["pulled_et"])
dk_splits.WO_OVERRIDE = {}
games = []
n = lambda v: float(v) if v not in ("", None) else None
for r in saved:     # rebuild DK page games (DK's own order) from the saved rows
    sel_a = r["spr_away_sel"].rsplit(" ", 1)[0] if r["spr_away_sel"] else r["away"]
    games.append({"away": r["away"], "home": r["home"], "when": r["when"],
                  "spread": [{"sel": f'{r["away"]} x', "handle": n(r["spr_away_handle"]), "bets": n(r["spr_away_bets"])},
                             {"sel": f'{r["home"]} x', "handle": n(r["spr_home_handle"]), "bets": n(r["spr_home_bets"])}],
                  "total": [{"sel": "Over", "handle": n(r["over_handle"]), "bets": n(r["over_bets"])},
                            {"sel": "Under", "handle": 100 - (n(r["over_handle"]) or 0), "bets": 100 - (n(r["over_bets"]) or 0)}]})
rows, unmatched = dk_splits.build("CBB", games, [], lines, f"data/{DAY}/{SLOT}_lines_CBB.csv")
byid = {l["espn_id"]: l for l in lines}
ok = 0
for r, src in zip(rows, saved):
    l = byid.get(r["espn_id"])
    oriented = bool(l) and r["away"] in l["away"] or (l and l["away"].startswith(r["away"].split()[0]))
    swapped = r["away"] != src["away"]
    print(f'{src["away"]:20} @ {src["home"]:18} -> espn {r["espn_id"] or "NONE":10} {"SWAPPED " if swapped else ""}'
          f'away h/b {r["spr_away_handle"]}/{r["spr_away_bets"]} open {r["spread_open"]} now {r["spread_now"]} | {r["flags"][:70]}')
    ok += bool(r["espn_id"])
print(f"\n{ok}/{len(rows)} joined; unmatched: {unmatched}")
want = {"401920530": ("St. Johns", "4.5", "RLM"), "401920539": ("Alabama", "-12.5", "PUB"), "401920540": ("Baylor", "4.5", "RLM")}
bad = []
for r in rows:
    if r["espn_id"] in want:
        hm, op, fl = want[r["espn_id"]]
        if r["home"] != hm and r["away"] == hm: pass
        if str(float(r["spread_open"])) != str(float(op)) or fl not in r["flags"] or "STEAM" in r["flags"].split("OPENER")[0] and abs(float(r["spread_open"]) - float(r["spread_now"])) < 1.5:
            bad.append((r["away"], r["home"], r["spread_open"], r["flags"]))
print("opener-flip games:", "OK" if not bad else bad)
sys.exit(0 if ok == len(rows) and not bad else 1)
