# CBB calibration, season to date — 586 games graded (updated 2026-11-25 15:33 ET)

Mean absolute error vs the final margin; lower is better. The closing line is the benchmark to beat.

| Predictor | All | Tier 1 | Tier 2 | Tier 3 |
|---|---|---|---|---|
| Closing line | 10.13 (n=561) | 10.03 (n=64) | 10.64 (n=262) | 9.60 (n=235) |
| Opener | 10.31 (n=537) | 10.29 (n=63) | 10.82 (n=252) | 9.73 (n=222) |
| Torvik | 13.43 (n=583) | 12.55 (n=65) | 14.75 (n=276) | 12.14 (n=242) |
| TeamRankings | 12.09 (n=553) | 11.25 (n=65) | 12.91 (n=262) | 11.38 (n=226) |
| BPI | 10.53 (n=562) | 10.50 (n=64) | 11.13 (n=263) | 9.86 (n=235) |
| Model consensus | 12.25 (n=586) | 11.49 (n=65) | 13.47 (n=278) | 11.06 (n=243) |
| Fair line | 10.20 (n=561) | 10.34 (n=64) | 10.73 (n=262) | 9.57 (n=235) |

Records vs the closing line (break-even at -110 is 52.4%):
- All model flags (any tier, as logged): 60-50 (54.5%)
- EDGE flags (Tier 2-3, edge 3-5 pts; from Nov 16): 55-46 (54.5%)
- CHECK flags (edge 5+, usually data problems): 5-4 (55.6%)
- MKT flags, Tier 1 (RLM, or sharp money + steam): 13-2 (86.7%)
- MKT flags, all tiers: 72-49 (59.5%)
- FADE (away side vs a home favorite of 7+): 61-60 (50.4%)
- TOTAL-MKT flags (total RLM, or sharp money + same-way move; from Nov 18): 30-43 (41.1%)
- Baseline, every game's Under vs the closing total: 277-284 (49.4%) (a TOTAL family must beat this)
- Pace FAST games, Under vs the closing total: 23-31
- Pace SLOW games, Under vs the closing total: 22-31
- Pace CLASH games, Under vs the closing total: 6-9
- TOTAL-MKT agreeing with pace (Under + SLOW, Over + FAST): 8-15
- Retired model-total rule (stand-in total 4+ off the close, not de-biased): 179-152
- Totals MAE: Torvik 14.63 (n=583) · TR projection 13.68 (n=17) vs closing total 13.05 (n=561)
- TR projected margin MAE (Tier 1-type games only): 9.70 (n=17) vs closing line 9.21 (n=17)
- TR projected total 4+ off the close (side vs the closing total): 0-0

## Closing-line value by family (the real test at this volume)

CLV = points the close moved toward the flagged side after the FIRST snapshot the family fired (no hindsight). Open CLV = the same side as if bet at the DraftKings opener (the bet-timing test). Record = that first-flag side vs the closing number. A family that wins but has negative CLV is luck or a fading market bias, not an edge. MKT and TOTAL-MKT flags are defined by the line already moving their way, so their open CLV is positive by construction: judge them on CLV after the flag.

| Family | n | Avg CLV (pts) | % CLV > 0 | Avg open CLV | % open CLV > 0 | Record vs close |
|---|---|---|---|---|---|---|
| EDGE (Tier 2-3) | 135 | +0.56 | 36% | -0.06 | 36% | 70-64 (52.2%) |
| MKT (all tiers) | 149 | +0.01 | 16% | +1.77 | 95% | 83-66 (55.7%) |
| MKT Tier 1 | 18 | -0.11 | 11% | +1.72 | 94% | 15-3 (83.3%) |
| TOTAL-MKT | 132 | +0.08 | 14% | +1.93 | 83% | 61-71 (46.2%) |
| FADE home fav 7+ | 124 | +0.67 | 54% | +0.77 | 57% | 61-63 (49.2%) |
| ROT (opponent of a team missing a core player) | 70 | +0.19 | 33% | +0.33 | 33% | 31-39 (44.3%) |
| FAT (opponent of the tired team) | 30 | -0.07 | 23% | -0.27 | 33% | 19-11 (63.3%) |
| ALT (home team at altitude) | 2 | +1.50 | 50% | +0.50 | 50% | 2-0 (100.0%) |
| FIRST-MOVE (1.5+ off the opener before 10 AM) | 27 | +0.19 | 26% | +2.22 | 81% | 16-11 (59.3%) |
| LAG (FanDuel/Novig 1+ off the market, at that book) | 68 | +2.57 | 65% | -0.47 | 29% | 39-29 (57.4%) |

Flag families overlap (a game can be EDGE, FADE and TOTAL at once); judge each on its own record.
Change weights or thresholds only after ~300 graded games, and only where a gap holds in every tier.
