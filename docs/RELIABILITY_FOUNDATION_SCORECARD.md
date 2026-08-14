# Reliability Foundation Scorecard

This scorecard summarizes the new foundation-first reliability layer. It uses group-stage data as the training side and non-group-stage data as the playoff-style backtest surface.

## Segment Summary

| Entity type | Segment | Rows | Avg reliability | Avg expected | Avg band width | Confidence index |
|---|---|---:|---:|---:|---:|---:|
| player | core | 48 | 50.50 | 8962.02 | 3569.62 | 0.52 |
| player | mid | 24 | 50.50 | 10724.68 | 3758.83 | 0.52 |
| player | support | 48 | 50.50 | 6053.82 | 2454.38 | 0.52 |
| role_slot | core_pair | 24 | 50.50 | 8947.36 | 3318.68 | 0.52 |
| role_slot | mid_single | 24 | 50.50 | 10724.68 | 3758.83 | 0.52 |
| role_slot | support_pair | 24 | 50.50 | 6042.75 | 2219.35 | 0.52 |

## Backtest Summary

| Entity type | Segment | Rows backtested | MAE | Min actual | Max actual |
|---|---|---:|---:|---:|---:|
| player | core | 16 | 3327.15 | 8562.64 | 17611.95 |
| player | mid | 8 | 3694.03 | 9762.15 | 17571.65 |
| player | support | 16 | 2363.08 | 4928.05 | 11176.34 |
| role_slot | core_pair | 8 | 3036.38 | 8579.54 | 15623.01 |
| role_slot | mid_single | 8 | 3694.03 | 9762.15 | 17571.65 |
| role_slot | support_pair | 8 | 2098.50 | 5443.80 | 9527.28 |

## Top Players / core

| Player | Team | Reliability | Expected | Low | High | Confidence |
|---|---|---:|---:|---:|---:|---|
| SumaiL | Nigma Galaxy | 97.89 | 12090.81 | 10065.42 | 13825.19 | medium |
| Yuma | LGD Gaming | 95.79 | 11910.36 | 9584.62 | 13924.33 | high |
| Ghost | GamerLegion | 93.68 | 11216.68 | 8128.35 | 13631.97 | medium |
| Pure | 1w | 91.57 | 10931.38 | 8887.43 | 12629.12 | medium |
| Yatoro | Team Spirit | 89.47 | 10855.93 | 9286.29 | 12172.60 | medium |
| shiro | Vici Gaming | 87.36 | 10846.98 | 8484.92 | 12833.67 | medium |
| Wisper | LGD Gaming | 85.26 | 10385.48 | 8198.23 | 12277.98 | high |
| m1CKe | Team Liquid | 83.15 | 10355.04 | 7716.68 | 12563.39 | medium |

## Top Players / mid

| Player | Team | Reliability | Expected | Low | High | Confidence |
|---|---|---:|---:|---:|---:|---|
| lorenof | Nigma Galaxy | 100.00 | 13037.62 | 10947.87 | 14825.46 | medium |
| TaiLung | LGD Gaming | 91.39 | 12178.17 | 9856.11 | 14184.04 | high |
| Nisha | Team Liquid | 87.09 | 12048.95 | 9558.49 | 14133.71 | medium |
| NothingToSay | Xtreme Gaming | 82.78 | 11904.94 | 9381.36 | 13968.16 | medium |
| Malr1ne | Team Falcons | 78.48 | 11860.47 | 9153.79 | 13999.64 | medium |
| Xm | Vici Gaming | 69.87 | 11828.35 | 9722.86 | 13610.89 | medium |
| bzm | 1w | 65.57 | 11823.97 | 9405.27 | 13816.37 | medium |
| gpk~ | BoomBoys | 52.65 | 11090.60 | 9051.43 | 12787.17 | medium |

## Top Players / support

| Player | Team | Reliability | Expected | Low | High | Confidence |
|---|---|---:|---:|---:|---:|---|
| Thiolicor | LGD Gaming | 100.00 | 7301.76 | 5833.91 | 8646.24 | high |
| XinQ | Vici Gaming | 97.89 | 7249.88 | 5281.20 | 8925.86 | medium |
| OmaR | Nigma Galaxy | 95.79 | 7182.96 | 6088.15 | 8195.19 | medium |
| KJ | LGD Gaming | 93.68 | 7170.43 | 5766.00 | 8463.51 | high |
| tOfu | Team Liquid | 91.57 | 7027.80 | 4900.42 | 8831.11 | medium |
| Ari | 1w | 87.36 | 6867.46 | 5320.07 | 8175.04 | medium |
| GH | Nigma Galaxy | 83.15 | 6777.64 | 5120.13 | 8191.71 | medium |
| Whitemon | 1w | 81.04 | 6658.27 | 5256.51 | 7851.47 | medium |

## Top Role Slots / core_pair

| Players | Team | Reliability | Expected | Low | High | Confidence |
|---|---|---:|---:|---:|---:|---|
| Yuma, Wisper | LGD Gaming | 100.00 | 11149.97 | 9102.30 | 12952.37 | high |
| SumaiL, Davai | Nigma Galaxy | 91.39 | 10694.38 | 9090.21 | 12103.75 | medium |
| Yatoro, Collapse | Team Spirit | 82.78 | 9920.75 | 8677.30 | 10995.81 | medium |
| shiro, Bach | Vici Gaming | 78.48 | 9907.08 | 7956.01 | 11582.54 | medium |
| skiter, ATF | Team Falcons | 74.17 | 9831.10 | 7967.42 | 11333.52 | medium |
| m1CKe, Ace | Team Liquid | 69.87 | 9823.71 | 7712.77 | 11622.37 | medium |
| Pure, 33 | 1w | 65.57 | 9801.02 | 8215.43 | 11138.88 | medium |
| Ghost, Fayde | GamerLegion | 61.26 | 9643.85 | 7174.09 | 11592.27 | medium |

## Top Role Slots / mid_single

| Players | Team | Reliability | Expected | Low | High | Confidence |
|---|---|---:|---:|---:|---:|---|
| lorenof | Nigma Galaxy | 100.00 | 13037.62 | 10947.87 | 14825.46 | medium |
| TaiLung | LGD Gaming | 91.39 | 12178.17 | 9856.11 | 14184.04 | high |
| Nisha | Team Liquid | 87.09 | 12048.95 | 9558.49 | 14133.71 | medium |
| NothingToSay | Xtreme Gaming | 82.78 | 11904.94 | 9381.36 | 13968.16 | medium |
| Malr1ne | Team Falcons | 78.48 | 11860.47 | 9153.79 | 13999.64 | medium |
| Xm | Vici Gaming | 69.87 | 11828.35 | 9722.86 | 13610.89 | medium |
| bzm | 1w | 65.57 | 11823.97 | 9405.27 | 13816.37 | medium |
| gpk~ | BoomBoys | 52.65 | 11090.60 | 9051.43 | 12787.17 | medium |

## Top Role Slots / support_pair

| Players | Team | Reliability | Expected | Low | High | Confidence |
|---|---|---:|---:|---:|---:|---|
| Thiolicor, KJ | LGD Gaming | 100.00 | 7197.73 | 5850.98 | 8449.67 | high |
| OmaR, GH | Nigma Galaxy | 95.70 | 7001.55 | 5820.50 | 8085.56 | medium |
| XinQ, y` | Vici Gaming | 82.78 | 6719.51 | 5356.39 | 7923.55 | medium |
| Ari, Whitemon | 1w | 78.48 | 6699.57 | 5430.32 | 7801.71 | medium |
| Boxi, tOfu | Team Liquid | 74.17 | 6631.79 | 5076.57 | 7995.32 | medium |
| Cr1t-, Sneyking | Team Falcons | 69.87 | 6473.70 | 5277.91 | 7448.33 | medium |
| fy, xNova | Xtreme Gaming | 65.57 | 6448.25 | 4951.78 | 7716.66 | medium |
| not me, rue | Team Spirit | 61.26 | 6270.20 | 5266.60 | 7156.36 | medium |

