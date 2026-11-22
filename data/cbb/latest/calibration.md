# CBB calibration, season to date — 376 games graded (updated 2026-11-21 22:41 ET)

Mean absolute error vs the final margin; lower is better. The closing line is the benchmark to beat.

| Predictor | All | Tier 1 | Tier 2 | Tier 3 |
|---|---|---|---|---|
| Closing line | 10.08 (n=361) | 10.43 (n=41) | 10.48 (n=172) | 9.52 (n=148) |
| Opener | 10.25 (n=337) | 10.43 (n=40) | 10.64 (n=162) | 9.72 (n=135) |
| Torvik | 13.64 (n=373) | 13.86 (n=42) | 14.51 (n=179) | 12.56 (n=152) |
| TeamRankings | 11.97 (n=358) | 11.93 (n=42) | 12.39 (n=172) | 11.48 (n=144) |
| BPI | 10.55 (n=362) | 11.04 (n=41) | 10.88 (n=173) | 10.02 (n=148) |
| Model consensus | 12.07 (n=376) | 12.44 (n=42) | 12.80 (n=181) | 11.11 (n=153) |
| Fair line | 10.17 (n=361) | 10.61 (n=41) | 10.52 (n=172) | 9.63 (n=148) |

Records vs the closing line (break-even at -110 is 52.4%):
- All model flags (any tier, as logged): 55-42 (56.7%)
- EDGE flags (Tier 2-3, edge 3-5 pts; from Nov 16): 53-41 (56.4%)
- CHECK flags (edge 5+, usually data problems): 2-1 (66.7%)
- MKT flags, Tier 1 (RLM, or sharp money + steam): 5-0 (100.0%)
- MKT flags, all tiers: 35-23 (60.3%)
- FADE (away side vs a home favorite of 7+): 33-31 (51.6%)
- TOTAL-MKT flags (total RLM, or sharp money + same-way move; from Nov 18): 5-12 (29.4%)
- Baseline, every game's Under vs the closing total: 181-180 (50.1%) (a TOTAL family must beat this)
- Pace FAST games, Under vs the closing total: 5-8
- Pace SLOW games, Under vs the closing total: 5-8
- Pace CLASH games, Under vs the closing total: 1-5
- TOTAL-MKT agreeing with pace (Under + SLOW, Over + FAST): 2-5
- Retired model-total rule (stand-in total 4+ off the close, not de-biased): 135-113
- Totals MAE: Torvik 15.15 (n=373) · TR projection 10.10 (n=5) vs closing total 13.13 (n=361)
- TR projected margin MAE (Tier 1-type games only): 10.02 (n=5) vs closing line 9.30 (n=5)
- TR projected total 4+ off the close (side vs the closing total): 0-0

## Closing-line value by family (the real test at this volume)

CLV = points the close moved toward the flagged side after the FIRST snapshot the family fired (no hindsight). Open CLV = the same side as if bet at the DraftKings opener (the bet-timing test). Record = that first-flag side vs the closing number. A family that wins but has negative CLV is luck or a fading market bias, not an edge. MKT and TOTAL-MKT flags are defined by the line already moving their way, so their open CLV is positive by construction: judge them on CLV after the flag.

| Family | n | Avg CLV (pts) | % CLV > 0 | Avg open CLV | % open CLV > 0 | Record vs close |
|---|---|---|---|---|---|---|
| EDGE (Tier 2-3) | 114 | +0.39 | 31% | -0.04 | 35% | 59-54 (52.2%) |
| MKT (all tiers) | 74 | +0.14 | 18% | +1.89 | 95% | 39-35 (52.7%) |
| MKT Tier 1 | 6 | -0.50 | 0% | +0.83 | 83% | 5-1 (83.3%) |
| TOTAL-MKT | 63 | +0.13 | 24% | +1.16 | 67% | 29-34 (46.0%) |
| FADE home fav 7+ | 65 | +0.55 | 46% | +0.97 | 57% | 33-32 (50.8%) |
| ROT (opponent of a team missing a core player) | 8 | +0.25 | 12% | +0.00 | 38% | 4-4 (50.0%) |
| FAT (opponent of the tired team) | 17 | +0.06 | 29% | -0.47 | 29% | 12-5 (70.6%) |
| ALT (home team at altitude) | 1 | +0.00 | 0% | +1.00 | 100% | 1-0 (100.0%) |
| FIRST-MOVE (1.5+ off the opener before 10 AM) | 0 | — | — | — | — | 0-0 |
| LAG (FanDuel/Novig 1+ off the market, at that book) | 19 | +7.37 | 95% | -0.58 | 32% | 8-11 (42.1%) |

Flag families overlap (a game can be EDGE, FADE and TOTAL at once); judge each on its own record.
Change weights or thresholds only after ~300 graded games, and only where a gap holds in every tier.
