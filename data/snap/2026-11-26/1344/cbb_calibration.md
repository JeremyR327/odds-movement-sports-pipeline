# CBB calibration, season to date — 646 games graded (updated 2026-11-26 13:44 ET)

Mean absolute error vs the final margin; lower is better. The closing line is the benchmark to beat.

| Predictor | All | Tier 1 | Tier 2 | Tier 3 |
|---|---|---|---|---|
| Closing line | 9.97 (n=618) | 10.11 (n=72) | 10.22 (n=293) | 9.65 (n=253) |
| Opener | 10.17 (n=594) | 10.37 (n=71) | 10.45 (n=283) | 9.78 (n=240) |
| Torvik | 13.29 (n=643) | 12.69 (n=73) | 14.34 (n=309) | 12.21 (n=261) |
| TeamRankings | 11.83 (n=610) | 11.30 (n=73) | 12.49 (n=294) | 11.20 (n=243) |
| BPI | 10.35 (n=619) | 10.70 (n=72) | 10.70 (n=294) | 9.85 (n=253) |
| Model consensus | 12.09 (n=646) | 11.59 (n=73) | 12.96 (n=311) | 11.20 (n=262) |
| Fair line | 10.05 (n=618) | 10.45 (n=72) | 10.36 (n=293) | 9.58 (n=253) |

Records vs the closing line (break-even at -110 is 52.4%):
- All model flags (any tier, as logged): 63-52 (54.8%)
- EDGE flags (Tier 2-3, edge 3-5 pts; from Nov 16): 57-48 (54.3%)
- CHECK flags (edge 5+, usually data problems): 6-4 (60.0%)
- MKT flags, Tier 1 (RLM, or sharp money + steam): 14-4 (77.8%)
- MKT flags, all tiers: 84-57 (59.6%)
- FADE (away side vs a home favorite of 7+): 73-66 (52.5%)
- TOTAL-MKT flags (total RLM, or sharp money + same-way move; from Nov 18): 34-47 (42.0%)
- Baseline, every game's Under vs the closing total: 304-313 (49.3%) (a TOTAL family must beat this)
- Pace FAST games, Under vs the closing total: 30-38
- Pace SLOW games, Under vs the closing total: 26-37
- Pace CLASH games, Under vs the closing total: 8-10
- TOTAL-MKT agreeing with pace (Under + SLOW, Over + FAST): 9-16
- Retired model-total rule (stand-in total 4+ off the close, not de-biased): 194-174
- Totals MAE: Torvik 14.80 (n=643) · TR projection 11.55 (n=25) vs closing total 13.13 (n=617)
- TR projected margin MAE (Tier 1-type games only): 9.58 (n=25) vs closing line 9.34 (n=25)
- TR projected total 4+ off the close (side vs the closing total): 0-0

## Closing-line value by family (the real test at this volume)

CLV = points the close moved toward the flagged side after the FIRST snapshot the family fired (no hindsight). Open CLV = the same side as if bet at the DraftKings opener (the bet-timing test). Record = that first-flag side vs the closing number. A family that wins but has negative CLV is luck or a fading market bias, not an edge. MKT and TOTAL-MKT flags are defined by the line already moving their way, so their open CLV is positive by construction: judge them on CLV after the flag.

| Family | n | Avg CLV (pts) | % CLV > 0 | Avg open CLV | % open CLV > 0 | Record vs close |
|---|---|---|---|---|---|---|
| EDGE (Tier 2-3) | 142 | +0.54 | 35% | -0.15 | 35% | 75-66 (53.2%) |
| MKT (all tiers) | 175 | -0.01 | 14% | +1.73 | 95% | 101-74 (57.7%) |
| MKT Tier 1 | 23 | -0.13 | 9% | +1.57 | 91% | 18-5 (78.3%) |
| TOTAL-MKT | 140 | +0.07 | 14% | +1.99 | 84% | 65-75 (46.4%) |
| FADE home fav 7+ | 143 | +0.63 | 52% | +0.71 | 55% | 74-69 (51.7%) |
| ROT (opponent of a team missing a core player) | 93 | +0.20 | 33% | +0.30 | 34% | 43-50 (46.2%) |
| FAT (opponent of the tired team) | 39 | -0.08 | 26% | -0.26 | 33% | 25-14 (64.1%) |
| ALT (home team at altitude) | 4 | +1.00 | 50% | +0.75 | 75% | 2-2 (50.0%) |
| FIRST-MOVE (1.5+ off the opener before 10 AM) | 31 | +0.19 | 26% | +2.26 | 84% | 18-13 (58.1%) |
| LAG (FanDuel/Novig 1+ off the market, at that book) | 77 | +2.34 | 65% | -0.44 | 29% | 44-33 (57.1%) |

Flag families overlap (a game can be EDGE, FADE and TOTAL at once); judge each on its own record.
Change weights or thresholds only after ~300 graded games, and only where a gap holds in every tier.
