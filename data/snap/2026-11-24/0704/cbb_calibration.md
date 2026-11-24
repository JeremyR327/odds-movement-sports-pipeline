# CBB calibration, season to date — 504 games graded (updated 2026-11-24 07:04 ET)

Mean absolute error vs the final margin; lower is better. The closing line is the benchmark to beat.

| Predictor | All | Tier 1 | Tier 2 | Tier 3 |
|---|---|---|---|---|
| Closing line | 10.12 (n=483) | 10.38 (n=51) | 10.59 (n=228) | 9.53 (n=204) |
| Opener | 10.28 (n=459) | 10.44 (n=50) | 10.77 (n=218) | 9.69 (n=191) |
| Torvik | 13.42 (n=501) | 13.22 (n=52) | 14.84 (n=241) | 11.83 (n=208) |
| TeamRankings | 11.91 (n=476) | 11.65 (n=52) | 12.87 (n=231) | 10.84 (n=193) |
| BPI | 10.44 (n=484) | 10.76 (n=51) | 10.98 (n=229) | 9.75 (n=204) |
| Model consensus | 12.13 (n=504) | 11.96 (n=52) | 13.50 (n=243) | 10.57 (n=209) |
| Fair line | 10.16 (n=483) | 10.51 (n=51) | 10.64 (n=228) | 9.54 (n=204) |

Records vs the closing line (break-even at -110 is 52.4%):
- All model flags (any tier, as logged): 57-45 (55.9%)
- EDGE flags (Tier 2-3, edge 3-5 pts; from Nov 16): 55-44 (55.6%)
- CHECK flags (edge 5+, usually data problems): 2-1 (66.7%)
- MKT flags, Tier 1 (RLM, or sharp money + steam): 9-1 (90.0%)
- MKT flags, all tiers: 59-42 (58.4%)
- FADE (away side vs a home favorite of 7+): 52-44 (54.2%)
- TOTAL-MKT flags (total RLM, or sharp money + same-way move; from Nov 18): 19-35 (35.2%)
- Baseline, every game's Under vs the closing total: 236-247 (48.9%) (a TOTAL family must beat this)
- Pace FAST games, Under vs the closing total: 16-22
- Pace SLOW games, Under vs the closing total: 14-25
- Pace CLASH games, Under vs the closing total: 3-8
- TOTAL-MKT agreeing with pace (Under + SLOW, Over + FAST): 7-13
- Retired model-total rule (stand-in total 4+ off the close, not de-biased): 159-130
- Totals MAE: Torvik 14.80 (n=501) · TR projection 9.72 (n=6) vs closing total 13.08 (n=483)
- TR projected margin MAE (Tier 1-type games only): 9.98 (n=6) vs closing line 9.33 (n=6)
- TR projected total 4+ off the close (side vs the closing total): 0-0

## Closing-line value by family (the real test at this volume)

CLV = points the close moved toward the flagged side after the FIRST snapshot the family fired (no hindsight). Open CLV = the same side as if bet at the DraftKings opener (the bet-timing test). Record = that first-flag side vs the closing number. A family that wins but has negative CLV is luck or a fading market bias, not an edge. MKT and TOTAL-MKT flags are defined by the line already moving their way, so their open CLV is positive by construction: judge them on CLV after the flag.

| Family | n | Avg CLV (pts) | % CLV > 0 | Avg open CLV | % open CLV > 0 | Record vs close |
|---|---|---|---|---|---|---|
| EDGE (Tier 2-3) | 127 | +0.50 | 35% | -0.01 | 37% | 67-59 (53.2%) |
| MKT (all tiers) | 119 | +0.13 | 16% | +1.88 | 96% | 64-55 (53.8%) |
| MKT Tier 1 | 11 | -0.36 | 0% | +1.18 | 91% | 9-2 (81.8%) |
| TOTAL-MKT | 106 | +0.08 | 16% | +1.76 | 78% | 45-61 (42.5%) |
| FADE home fav 7+ | 98 | +0.74 | 55% | +0.98 | 62% | 52-46 (53.1%) |
| ROT (opponent of a team missing a core player) | 47 | +0.28 | 34% | +0.17 | 34% | 25-22 (53.2%) |
| FAT (opponent of the tired team) | 22 | -0.32 | 23% | -0.73 | 23% | 15-7 (68.2%) |
| ALT (home team at altitude) | 1 | +0.00 | 0% | +1.00 | 100% | 1-0 (100.0%) |
| FIRST-MOVE (1.5+ off the opener before 10 AM) | 11 | +0.18 | 18% | +3.27 | 91% | 5-6 (45.5%) |
| LAG (FanDuel/Novig 1+ off the market, at that book) | 51 | +3.08 | 67% | -0.55 | 29% | 28-23 (54.9%) |

Flag families overlap (a game can be EDGE, FADE and TOTAL at once); judge each on its own record.
Change weights or thresholds only after ~300 graded games, and only where a gap holds in every tier.
