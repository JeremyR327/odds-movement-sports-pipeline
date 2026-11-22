# CBB calibration, season to date — 429 games graded (updated 2026-11-22 07:04 ET)

Mean absolute error vs the final margin; lower is better. The closing line is the benchmark to beat.

| Predictor | All | Tier 1 | Tier 2 | Tier 3 |
|---|---|---|---|---|
| Closing line | 10.21 (n=412) | 10.73 (n=44) | 10.67 (n=187) | 9.61 (n=181) |
| Opener | 10.38 (n=388) | 10.73 (n=43) | 10.84 (n=177) | 9.82 (n=168) |
| Torvik | 13.64 (n=426) | 13.74 (n=45) | 15.05 (n=196) | 12.12 (n=185) |
| TeamRankings | 11.91 (n=407) | 12.16 (n=45) | 12.61 (n=188) | 11.10 (n=174) |
| BPI | 10.58 (n=413) | 11.20 (n=44) | 11.10 (n=188) | 9.89 (n=181) |
| Model consensus | 12.20 (n=429) | 12.53 (n=45) | 13.42 (n=198) | 10.83 (n=186) |
| Fair line | 10.28 (n=412) | 10.88 (n=44) | 10.72 (n=187) | 9.67 (n=181) |

Records vs the closing line (break-even at -110 is 52.4%):
- All model flags (any tier, as logged): 56-44 (56.0%)
- EDGE flags (Tier 2-3, edge 3-5 pts; from Nov 16): 54-43 (55.7%)
- CHECK flags (edge 5+, usually data problems): 2-1 (66.7%)
- MKT flags, Tier 1 (RLM, or sharp money + steam): 5-1 (83.3%)
- MKT flags, all tiers: 45-28 (61.6%)
- FADE (away side vs a home favorite of 7+): 42-36 (53.8%)
- TOTAL-MKT flags (total RLM, or sharp money + same-way move; from Nov 18): 12-21 (36.4%)
- Baseline, every game's Under vs the closing total: 202-210 (49.0%) (a TOTAL family must beat this)
- Pace FAST games, Under vs the closing total: 10-14
- Pace SLOW games, Under vs the closing total: 9-16
- Pace CLASH games, Under vs the closing total: 2-7
- TOTAL-MKT agreeing with pace (Under + SLOW, Over + FAST): 5-10
- Retired model-total rule (stand-in total 4+ off the close, not de-biased): 140-118
- Totals MAE: Torvik 14.85 (n=426) · TR projection 9.72 (n=6) vs closing total 12.98 (n=412)
- TR projected margin MAE (Tier 1-type games only): 9.98 (n=6) vs closing line 9.33 (n=6)
- TR projected total 4+ off the close (side vs the closing total): 0-0

## Closing-line value by family (the real test at this volume)

CLV = points the close moved toward the flagged side after the FIRST snapshot the family fired (no hindsight). Open CLV = the same side as if bet at the DraftKings opener (the bet-timing test). Record = that first-flag side vs the closing number. A family that wins but has negative CLV is luck or a fading market bias, not an edge. MKT and TOTAL-MKT flags are defined by the line already moving their way, so their open CLV is positive by construction: judge them on CLV after the flag.

| Family | n | Avg CLV (pts) | % CLV > 0 | Avg open CLV | % open CLV > 0 | Record vs close |
|---|---|---|---|---|---|---|
| EDGE (Tier 2-3) | 118 | +0.39 | 31% | -0.13 | 35% | 61-56 (52.1%) |
| MKT (all tiers) | 90 | +0.13 | 17% | +1.91 | 96% | 49-41 (54.4%) |
| MKT Tier 1 | 7 | -0.43 | 0% | +0.86 | 86% | 5-2 (71.4%) |
| TOTAL-MKT | 80 | +0.10 | 19% | +1.60 | 74% | 36-44 (45.0%) |
| FADE home fav 7+ | 80 | +0.57 | 49% | +0.88 | 59% | 42-38 (52.5%) |
| ROT (opponent of a team missing a core player) | 19 | +0.21 | 21% | +0.05 | 37% | 10-9 (52.6%) |
| FAT (opponent of the tired team) | 18 | +0.00 | 28% | -0.50 | 28% | 13-5 (72.2%) |
| ALT (home team at altitude) | 1 | +0.00 | 0% | +1.00 | 100% | 1-0 (100.0%) |
| FIRST-MOVE (1.5+ off the opener before 10 AM) | 5 | +0.00 | 0% | +3.80 | 100% | 3-2 (60.0%) |
| LAG (FanDuel/Novig 1+ off the market, at that book) | 32 | +4.56 | 81% | -0.28 | 38% | 17-15 (53.1%) |

Flag families overlap (a game can be EDGE, FADE and TOTAL at once); judge each on its own record.
Change weights or thresholds only after ~300 graded games, and only where a gap holds in every tier.
