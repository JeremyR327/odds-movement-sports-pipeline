# CBB calibration, season to date — 667 games graded (updated 2026-11-27 22:41 ET)

Mean absolute error vs the final margin; lower is better. The closing line is the benchmark to beat.

| Predictor | All | Tier 1 | Tier 2 | Tier 3 |
|---|---|---|---|---|
| Closing line | 9.88 (n=639) | 9.45 (n=85) | 10.20 (n=298) | 9.66 (n=256) |
| Opener | 10.07 (n=615) | 9.62 (n=84) | 10.42 (n=288) | 9.81 (n=243) |
| Torvik | 13.12 (n=664) | 11.73 (n=86) | 14.27 (n=314) | 12.20 (n=264) |
| TeamRankings | 11.68 (n=631) | 10.42 (n=86) | 12.43 (n=299) | 11.21 (n=246) |
| BPI | 10.23 (n=640) | 9.88 (n=85) | 10.66 (n=299) | 9.85 (n=256) |
| Model consensus | 11.93 (n=667) | 10.68 (n=86) | 12.89 (n=316) | 11.19 (n=265) |
| Fair line | 9.95 (n=639) | 9.68 (n=85) | 10.33 (n=298) | 9.60 (n=256) |

Records vs the closing line (break-even at -110 is 52.4%):
- All model flags (any tier, as logged): 63-52 (54.8%)
- EDGE flags (Tier 2-3, edge 3-5 pts; from Nov 16): 57-48 (54.3%)
- CHECK flags (edge 5+, usually data problems): 6-4 (60.0%)
- MKT flags, Tier 1 (RLM, or sharp money + steam): 16-7 (69.6%)
- MKT flags, all tiers: 88-62 (58.7%)
- FADE (away side vs a home favorite of 7+): 74-66 (52.9%)
- TOTAL-MKT flags (total RLM, or sharp money + same-way move; from Nov 18): 35-48 (42.2%)
- Baseline, every game's Under vs the closing total: 315-323 (49.4%) (a TOTAL family must beat this)
- Pace FAST games, Under vs the closing total: 31-43
- Pace SLOW games, Under vs the closing total: 28-38
- Pace CLASH games, Under vs the closing total: 9-10
- TOTAL-MKT agreeing with pace (Under + SLOW, Over + FAST): 10-16
- Retired model-total rule (stand-in total 4+ off the close, not de-biased): 200-176
- Totals MAE: Torvik 14.72 (n=664) · TR projection 12.71 (n=34) vs closing total 13.11 (n=638)
- TR projected margin MAE (Tier 1-type games only): 8.72 (n=34) vs closing line 8.59 (n=34)
- TR projected total 4+ off the close (side vs the closing total): 0-0

## Closing-line value by family (the real test at this volume)

CLV = points the close moved toward the flagged side after the FIRST snapshot the family fired (no hindsight). Open CLV = the same side as if bet at the DraftKings opener (the bet-timing test). Record = that first-flag side vs the closing number. A family that wins but has negative CLV is luck or a fading market bias, not an edge. MKT and TOTAL-MKT flags are defined by the line already moving their way, so their open CLV is positive by construction: judge them on CLV after the flag.

| Family | n | Avg CLV (pts) | % CLV > 0 | Avg open CLV | % open CLV > 0 | Record vs close |
|---|---|---|---|---|---|---|
| EDGE (Tier 2-3) | 142 | +0.54 | 35% | -0.15 | 35% | 75-66 (53.2%) |
| MKT (all tiers) | 189 | -0.04 | 13% | +1.70 | 93% | 109-80 (57.7%) |
| MKT Tier 1 | 32 | -0.25 | 9% | +1.50 | 78% | 23-9 (71.9%) |
| TOTAL-MKT | 149 | +0.09 | 15% | +2.11 | 84% | 70-79 (47.0%) |
| FADE home fav 7+ | 144 | +0.64 | 53% | +0.73 | 56% | 75-69 (52.1%) |
| ROT (opponent of a team missing a core player) | 102 | +0.23 | 34% | +0.33 | 35% | 45-57 (44.1%) |
| FAT (opponent of the tired team) | 41 | -0.15 | 24% | -0.34 | 32% | 26-15 (63.4%) |
| ALT (home team at altitude) | 4 | +1.00 | 50% | +0.75 | 75% | 2-2 (50.0%) |
| FIRST-MOVE (1.5+ off the opener before 10 AM) | 39 | +0.05 | 26% | +2.08 | 79% | 22-17 (56.4%) |
| LAG (FanDuel/Novig 1+ off the market, at that book) | 81 | +2.25 | 63% | -0.47 | 28% | 45-36 (55.6%) |

Flag families overlap (a game can be EDGE, FADE and TOTAL at once); judge each on its own record.
Change weights or thresholds only after ~300 graded games, and only where a gap holds in every tier.
