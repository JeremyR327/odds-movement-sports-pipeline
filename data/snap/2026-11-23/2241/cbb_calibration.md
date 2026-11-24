# CBB calibration, season to date — 467 games graded (updated 2026-11-23 22:41 ET)

Mean absolute error vs the final margin; lower is better. The closing line is the benchmark to beat.

| Predictor | All | Tier 1 | Tier 2 | Tier 3 |
|---|---|---|---|---|
| Closing line | 10.23 (n=450) | 10.97 (n=47) | 10.61 (n=208) | 9.64 (n=195) |
| Opener | 10.40 (n=426) | 11.00 (n=46) | 10.80 (n=198) | 9.82 (n=182) |
| Torvik | 13.38 (n=464) | 13.70 (n=48) | 14.55 (n=217) | 12.01 (n=199) |
| TeamRankings | 11.74 (n=442) | 12.33 (n=48) | 12.35 (n=208) | 10.91 (n=186) |
| BPI | 10.53 (n=451) | 11.29 (n=47) | 10.98 (n=209) | 9.87 (n=195) |
| Model consensus | 12.03 (n=467) | 12.58 (n=48) | 13.08 (n=219) | 10.76 (n=200) |
| Fair line | 10.27 (n=450) | 11.11 (n=47) | 10.64 (n=208) | 9.68 (n=195) |

Records vs the closing line (break-even at -110 is 52.4%):
- All model flags (any tier, as logged): 56-44 (56.0%)
- EDGE flags (Tier 2-3, edge 3-5 pts; from Nov 16): 54-43 (55.7%)
- CHECK flags (edge 5+, usually data problems): 2-1 (66.7%)
- MKT flags, Tier 1 (RLM, or sharp money + steam): 7-1 (87.5%)
- MKT flags, all tiers: 53-35 (60.2%)
- FADE (away side vs a home favorite of 7+): 47-39 (54.7%)
- TOTAL-MKT flags (total RLM, or sharp money + same-way move; from Nov 18): 16-27 (37.2%)
- Baseline, every game's Under vs the closing total: 217-233 (48.2%) (a TOTAL family must beat this)
- Pace FAST games, Under vs the closing total: 12-18
- Pace SLOW games, Under vs the closing total: 12-24
- Pace CLASH games, Under vs the closing total: 3-7
- TOTAL-MKT agreeing with pace (Under + SLOW, Over + FAST): 5-12
- Retired model-total rule (stand-in total 4+ off the close, not de-biased): 151-127
- Totals MAE: Torvik 14.78 (n=464) · TR projection 9.72 (n=6) vs closing total 12.96 (n=450)
- TR projected margin MAE (Tier 1-type games only): 9.98 (n=6) vs closing line 9.33 (n=6)
- TR projected total 4+ off the close (side vs the closing total): 0-0

## Closing-line value by family (the real test at this volume)

CLV = points the close moved toward the flagged side after the FIRST snapshot the family fired (no hindsight). Open CLV = the same side as if bet at the DraftKings opener (the bet-timing test). Record = that first-flag side vs the closing number. A family that wins but has negative CLV is luck or a fading market bias, not an edge. MKT and TOTAL-MKT flags are defined by the line already moving their way, so their open CLV is positive by construction: judge them on CLV after the flag.

| Family | n | Avg CLV (pts) | % CLV > 0 | Avg open CLV | % open CLV > 0 | Record vs close |
|---|---|---|---|---|---|---|
| EDGE (Tier 2-3) | 122 | +0.42 | 33% | -0.09 | 35% | 63-58 (52.1%) |
| MKT (all tiers) | 105 | +0.11 | 15% | +1.89 | 96% | 57-48 (54.3%) |
| MKT Tier 1 | 9 | -0.33 | 0% | +1.11 | 89% | 7-2 (77.8%) |
| TOTAL-MKT | 91 | +0.09 | 16% | +1.64 | 77% | 41-50 (45.1%) |
| FADE home fav 7+ | 88 | +0.62 | 52% | +0.90 | 60% | 47-41 (53.4%) |
| ROT (opponent of a team missing a core player) | 35 | +0.31 | 31% | +0.20 | 37% | 20-15 (57.1%) |
| FAT (opponent of the tired team) | 19 | -0.11 | 26% | -0.58 | 26% | 13-6 (68.4%) |
| ALT (home team at altitude) | 1 | +0.00 | 0% | +1.00 | 100% | 1-0 (100.0%) |
| FIRST-MOVE (1.5+ off the opener before 10 AM) | 8 | -0.38 | 0% | +3.12 | 88% | 4-4 (50.0%) |
| LAG (FanDuel/Novig 1+ off the market, at that book) | 44 | +3.52 | 70% | -0.32 | 34% | 24-20 (54.5%) |

Flag families overlap (a game can be EDGE, FADE and TOTAL at once); judge each on its own record.
Change weights or thresholds only after ~300 graded games, and only where a gap holds in every tier.
