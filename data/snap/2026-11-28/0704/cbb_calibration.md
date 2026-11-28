# CBB calibration, season to date — 719 games graded (updated 2026-11-28 07:04 ET)

Mean absolute error vs the final margin; lower is better. The closing line is the benchmark to beat.

| Predictor | All | Tier 1 | Tier 2 | Tier 3 |
|---|---|---|---|---|
| Closing line | 9.95 (n=687) | 9.38 (n=101) | 10.26 (n=319) | 9.79 (n=267) |
| Opener | 10.14 (n=662) | 9.53 (n=99) | 10.49 (n=309) | 9.94 (n=254) |
| Torvik | 13.11 (n=716) | 11.35 (n=102) | 14.39 (n=337) | 12.19 (n=277) |
| TeamRankings | 11.77 (n=681) | 10.22 (n=102) | 12.61 (n=320) | 11.35 (n=259) |
| BPI | 10.29 (n=688) | 9.73 (n=101) | 10.73 (n=320) | 9.98 (n=267) |
| Model consensus | 12.01 (n=719) | 10.40 (n=102) | 13.07 (n=339) | 11.30 (n=278) |
| Fair line | 10.02 (n=687) | 9.56 (n=101) | 10.42 (n=319) | 9.73 (n=267) |

Records vs the closing line (break-even at -110 is 52.4%):
- All model flags (any tier, as logged): 63-53 (54.3%)
- EDGE flags (Tier 2-3, edge 3-5 pts; from Nov 16): 57-49 (53.8%)
- CHECK flags (edge 5+, usually data problems): 6-4 (60.0%)
- MKT flags, Tier 1 (RLM, or sharp money + steam): 20-10 (66.7%)
- MKT flags, all tiers: 101-71 (58.7%)
- FADE (away side vs a home favorite of 7+): 81-72 (52.9%)
- TOTAL-MKT flags (total RLM, or sharp money + same-way move; from Nov 18): 43-53 (44.8%)
- Baseline, every game's Under vs the closing total: 343-343 (50.0%) (a TOTAL family must beat this)
- Pace FAST games, Under vs the closing total: 34-50
- Pace SLOW games, Under vs the closing total: 34-40
- Pace CLASH games, Under vs the closing total: 11-12
- TOTAL-MKT agreeing with pace (Under + SLOW, Over + FAST): 11-18
- Retired model-total rule (stand-in total 4+ off the close, not de-biased): 218-187
- Totals MAE: Torvik 14.53 (n=716) · TR projection 12.71 (n=34) vs closing total 12.99 (n=686)
- TR projected margin MAE (Tier 1-type games only): 8.72 (n=34) vs closing line 8.59 (n=34)
- TR projected total 4+ off the close (side vs the closing total): 0-0

## Closing-line value by family (the real test at this volume)

CLV = points the close moved toward the flagged side after the FIRST snapshot the family fired (no hindsight). Open CLV = the same side as if bet at the DraftKings opener (the bet-timing test). Record = that first-flag side vs the closing number. A family that wins but has negative CLV is luck or a fading market bias, not an edge. MKT and TOTAL-MKT flags are defined by the line already moving their way, so their open CLV is positive by construction: judge them on CLV after the flag.

| Family | n | Avg CLV (pts) | % CLV > 0 | Avg open CLV | % open CLV > 0 | Record vs close |
|---|---|---|---|---|---|---|
| EDGE (Tier 2-3) | 145 | +0.54 | 36% | -0.16 | 35% | 76-68 (52.8%) |
| MKT (all tiers) | 214 | -0.05 | 12% | +1.71 | 93% | 122-92 (57.0%) |
| MKT Tier 1 | 41 | -0.20 | 10% | +1.63 | 80% | 27-14 (65.9%) |
| TOTAL-MKT | 164 | +0.09 | 15% | +2.13 | 85% | 80-84 (48.8%) |
| FADE home fav 7+ | 158 | +0.65 | 54% | +0.75 | 58% | 83-75 (52.5%) |
| ROT (opponent of a team missing a core player) | 115 | +0.18 | 34% | +0.29 | 35% | 52-63 (45.2%) |
| FAT (opponent of the tired team) | 44 | -0.20 | 23% | -0.39 | 30% | 27-17 (61.4%) |
| ALT (home team at altitude) | 4 | +1.00 | 50% | +0.75 | 75% | 2-2 (50.0%) |
| FIRST-MOVE (1.5+ off the opener before 10 AM) | 45 | +0.07 | 24% | +2.11 | 82% | 25-20 (55.6%) |
| LAG (FanDuel/Novig 1+ off the market, at that book) | 96 | +2.07 | 64% | -0.33 | 32% | 53-43 (55.2%) |

Flag families overlap (a game can be EDGE, FADE and TOTAL at once); judge each on its own record.
Change weights or thresholds only after ~300 graded games, and only where a gap holds in every tier.
