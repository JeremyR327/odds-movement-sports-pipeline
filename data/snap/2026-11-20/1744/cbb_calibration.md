# CBB calibration, season to date — 325 games graded (updated 2026-11-20 17:44 ET)

Mean absolute error vs the final margin; lower is better. The closing line is the benchmark to beat.

| Predictor | All | Tier 1 | Tier 2 | Tier 3 |
|---|---|---|---|---|
| Closing line | 9.99 (n=310) | 9.85 (n=37) | 10.54 (n=143) | 9.42 (n=130) |
| Opener | 10.19 (n=286) | 9.75 (n=36) | 10.70 (n=133) | 9.73 (n=117) |
| Torvik | 13.65 (n=322) | 13.57 (n=38) | 14.78 (n=150) | 12.41 (n=134) |
| TeamRankings | 12.10 (n=307) | 11.39 (n=38) | 12.69 (n=143) | 11.63 (n=126) |
| BPI | 10.44 (n=311) | 10.48 (n=37) | 10.88 (n=144) | 9.95 (n=130) |
| Model consensus | 12.16 (n=325) | 12.00 (n=38) | 13.12 (n=152) | 11.11 (n=135) |
| Fair line | 10.05 (n=310) | 9.97 (n=37) | 10.53 (n=143) | 9.54 (n=130) |

Records vs the closing line (break-even at -110 is 52.4%):
- All model flags (any tier, as logged): 54-40 (57.4%)
- EDGE flags (Tier 2-3, edge 3-5 pts; from Nov 16): 52-39 (57.1%)
- CHECK flags (edge 5+, usually data problems): 2-1 (66.7%)
- MKT flags, Tier 1 (RLM, or sharp money + steam): 5-0 (100.0%)
- MKT flags, all tiers: 24-15 (61.5%)
- FADE (away side vs a home favorite of 7+): 25-20 (55.6%)
- TOTAL-MKT flags (total RLM, or sharp money + same-way move; from Nov 18): 3-5 (37.5%)
- Baseline, every game's Under vs the closing total: 161-149 (51.9%) (a TOTAL family must beat this)
- Pace FAST games, Under vs the closing total: 3-2
- Pace SLOW games, Under vs the closing total: 0-3
- Pace CLASH games, Under vs the closing total: 1-0
- TOTAL-MKT agreeing with pace (Under + SLOW, Over + FAST): 2-3
- Retired model-total rule (stand-in total 4+ off the close, not de-biased): 123-93
- Totals MAE: Torvik 14.99 (n=322) · TR projection 10.10 (n=5) vs closing total 13.11 (n=310)
- TR projected margin MAE (Tier 1-type games only): 10.02 (n=5) vs closing line 9.30 (n=5)
- TR projected total 4+ off the close (side vs the closing total): 0-0

## Closing-line value by family (the real test at this volume)

CLV = points the close moved toward the flagged side after the FIRST snapshot the family fired (no hindsight). Open CLV = the same side as if bet at the DraftKings opener (the bet-timing test). Record = that first-flag side vs the closing number. A family that wins but has negative CLV is luck or a fading market bias, not an edge. MKT and TOTAL-MKT flags are defined by the line already moving their way, so their open CLV is positive by construction: judge them on CLV after the flag.

| Family | n | Avg CLV (pts) | % CLV > 0 | Avg open CLV | % open CLV > 0 | Record vs close |
|---|---|---|---|---|---|---|
| EDGE (Tier 2-3) | 107 | +0.33 | 29% | -0.18 | 34% | 57-49 (53.8%) |
| MKT (all tiers) | 52 | +0.10 | 17% | +1.90 | 94% | 28-24 (53.8%) |
| MKT Tier 1 | 6 | -0.50 | 0% | +0.83 | 83% | 5-1 (83.3%) |
| TOTAL-MKT | 52 | +0.17 | 27% | +0.90 | 60% | 25-27 (48.1%) |
| FADE home fav 7+ | 46 | +0.39 | 43% | +0.70 | 54% | 25-21 (54.3%) |
| ROT (opponent of a team missing a core player) | 0 | — | — | — | — | 0-0 |
| FAT (opponent of the tired team) | 0 | — | — | — | — | 0-0 |
| ALT (home team at altitude) | 0 | — | — | — | — | 0-0 |
| FIRST-MOVE (1.5+ off the opener before 10 AM) | 0 | — | — | — | — | 0-0 |
| LAG (FanDuel/Novig 1+ off the market, at that book) | 0 | — | — | — | — | 0-0 |

Flag families overlap (a game can be EDGE, FADE and TOTAL at once); judge each on its own record.
Change weights or thresholds only after ~300 graded games, and only where a gap holds in every tier.
