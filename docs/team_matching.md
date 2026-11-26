# Team and matchup matching (CBB)

Added Nov 26 2026. Goal: 99%+ of source games matched to the right ESPN game, in the right orientation, with **zero** silent wrong matches.

## How it works

- **One key per team: the ESPN team id.** BPI and the ESPN scoreboard already use it.
- **`data/cbb/team_aliases.csv`** (2,622 rows) maps every spelling each source has used to that id, with the method and evidence. Sources covered: ESPN, DK splits, Odds API, TeamRankings and Torvik.
- **`data/cbb/team_crosswalk.csv`** is the same data with one row per Division I team (365 rows), for people to read.
- **`team_match.py`** does the matching:
  - `team_id(source, name)` looks the name up exactly in that source's aliases. There is no fuzzy step.
  - `match_game(...)` matches the **pair of team ids in either order** plus the start time: within 3 hours, or ±1 day for sources that only give a date. It returns `swapped` when the source lists the teams the other way round from ESPN's current order.
  - If only one team is known and it has exactly one game that day, the game is matched (`how="inferred"`) and the unknown name goes to `data/cbb/alias_review.csv`. Otherwise the game stays unmatched and is also logged. An unknown name is never guessed.
  - `check_opener(...)` checks the sign of ESPN's opening spread against the opening moneyline:
    - **fixed:** the moneyline names a clear favorite (8+ points of no-vig win probability over 50%) and the spread names the other team by 1.5 or more, so the sign is flipped.
    - **suspect:** the two disagree but the moneyline is near pick'em. The opener is not used for RLM, STEAM or FIRST-MOVE.
- **Wired into:**
  - `espn_lines.py`: writes team ids, `spread_open_raw` and `open_check`.
  - `dk_splits.py` (CBB): joins by team ids and swaps DK into ESPN's order. The week opener remembers which team was away when it was stored.
  - `cbb_pull.py`: checks the opener, swaps the splits when ESPN has flipped home/away since the splits pull, and joins the books by team ids.

## Stress test (held out: Nov 22–26, names learned only from games before Nov 22)

1,944 source games: 1,002 DK, 712 Odds API and 230 TeamRankings. 1,196 of them were at neutral sites.

| Approach | Correct | Wrong game | Unmatched |
|---|---|---|---|
| Current logic (names in away/home order + difflib) | 85.1% | 0% | 14.9% |
| + reversed-order key | 97.4% | 0% | 2.6% |
| Exact normalized names, either order | 84.2% | 0% | 15.8% |
| Fuzzy token-set, no time | 99.2% | 0.10% | 0.7% |
| Fuzzy token-sort + 90-min window | 97.9% | 0.10% | 2.0% |
| **Alias table + pair of ids in either order + time (`team_match`)** | **99.54%** | **0%** | 0.46% |

`team_match` on its own, starting with no aliases learned after Nov 21: 99.54% correct, 0 wrong, 9 unmatched. 85 games (4.4%) were inferred from one known team and sent to the review list.

Replaying today's 09:09 slate:
- **DK splits:** 21 of 21 joined (the old join got 18). Maryland/SDSU, St. John's/Louisville and Kansas State/Alabama were listed the other way round by DK.
- **Odds API:** 21 of 21 joined.
- **Openers fixed:**
  - Louisville/St. John's: SJU -4.5 → -2.5, which is now an RLM toward Louisville.
  - Alabama/Kansas State: Bama -12.5 → -14.5 (STEAM 2 instead of 27).
  - Baylor/Gonzaga: GONZ -4.5 → -3.5 (RLM toward Baylor instead of STEAM 8).

## What the stress test found

1. **ESPN flips home/away on the same event id between pulls** at neutral sites. It happened on 21 events within line pulls and 32 against the schedule cache, all neutral sites. Any "away @ home" key breaks, and the week opener changes sign.
2. **ESPN's opening spread can be in DraftKings' order while the moneyline follows ESPN's.** 22 strongly contradictory rows across 5 events this season: ALA/KSU, BAY/GONZ, LOU/SJU, ARST/LBSU and KENT/CLEV.
3. **Fuzzy matching is not safe on its own.** Token-set scoring rates "Arizona" vs "Northern Arizona" at 100 and put a Stanford game on Grand Canyon's. A school-prefix rule mapped Torvik's "Tennessee Martin", "Nebraska Omaha" and "Louisiana Monroe" to Tennessee, Nebraska and Louisiana. All six such Torvik names are now set by hand.
4. **Tricodes don't link sources.** ESPN's codes are stable: 449 teams, one code each, no clashes. But TeamRankings' page codes match ESPN's only 17% of the time, and TeamRankings sometimes prints full names there instead.

## Assumptions and limits

- **The test answers are this project's own pairing,** not an independent source. Each game was pinned by start time plus both team names. The 116 least obvious name pairs (e.g. Illinois Chicago → UIC) were checked by hand.
- **The "current logic" row is a copy** of the name-and-order join run against ESPN's latest order. The real pipeline ran against whatever order ESPN showed at each pull, so its true miss rate was probably higher.
- **Coverage:** DK names are known for 357 of 365 D1 teams and Odds API names for 347. The rest go through the inferred path and the review list until they show up.
- **The "suspect" opener rule is a judgment call.** It turns off opener-based flags on 61 near-pick'em rows this season instead of guessing the sign.
- **The aliases are CBB only.** NFL, CFB and NBA still use the old name join.

## Maintenance

- Check `data/cbb/alias_review.csv` weekly. Add confirmed names to `team_aliases.csv` with method `manual`.
- Run `python tests/test_team_match.py` (full replay; fails below 99% or on any wrong match) and `python tests/test_integration_today.py` (Nov 26 DK/ESPN replay).
