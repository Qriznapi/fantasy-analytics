# Prediction Monte Carlo Scorecard

This scorecard summarizes the Monte Carlo layer built on top of the production prediction surface. It estimates ranking stability and upside probabilities by repeatedly sampling entity scores from the stored predictive surface plus uncertainty scale.

| Target | Split | Entity type | Segment | Entities | Avg p_top1 | Avg p_top3 | Avg sim std |
|---|---|---|---|---:|---:|---:|---:|
| player_map_score | group_to_playoff | player | core | 48 | 0.021 | 0.062 | 1996.00 |
| player_map_score | group_to_playoff | player | mid | 24 | 0.042 | 0.125 | 2002.96 |
| player_map_score | group_to_playoff | player | support | 48 | 0.021 | 0.062 | 1994.52 |
| player_map_score | temporal_60_40 | player | core | 48 | 0.021 | 0.062 | 2379.41 |
| player_map_score | temporal_60_40 | player | mid | 24 | 0.042 | 0.125 | 2385.71 |
| player_map_score | temporal_60_40 | player | support | 48 | 0.021 | 0.062 | 2385.38 |
| player_series_mean | group_to_playoff | player | core | 48 | 0.021 | 0.062 | 1542.86 |
| player_series_mean | group_to_playoff | player | mid | 24 | 0.042 | 0.125 | 1545.57 |
| player_series_mean | group_to_playoff | player | support | 48 | 0.021 | 0.062 | 1545.11 |
| player_series_mean | temporal_60_40 | player | core | 48 | 0.021 | 0.062 | 1464.64 |
| player_series_mean | temporal_60_40 | player | mid | 24 | 0.042 | 0.125 | 1464.96 |
| player_series_mean | temporal_60_40 | player | support | 48 | 0.021 | 0.062 | 1464.35 |
| player_series_top1 | group_to_playoff | player | core | 48 | 0.021 | 0.062 | 1953.38 |
| player_series_top1 | group_to_playoff | player | mid | 24 | 0.042 | 0.125 | 1947.92 |
| player_series_top1 | group_to_playoff | player | support | 48 | 0.021 | 0.062 | 1952.35 |
| player_series_top1 | temporal_60_40 | player | core | 48 | 0.021 | 0.062 | 250.22 |
| player_series_top1 | temporal_60_40 | player | mid | 24 | 0.042 | 0.125 | 249.44 |
| player_series_top1 | temporal_60_40 | player | support | 48 | 0.021 | 0.062 | 250.01 |
| role_slot_map_score | group_to_playoff | role_slot | core_pair | 24 | 0.042 | 0.125 | 1846.15 |
| role_slot_map_score | group_to_playoff | role_slot | mid_single | 24 | 0.042 | 0.125 | 1843.17 |
| role_slot_map_score | group_to_playoff | role_slot | support_pair | 24 | 0.042 | 0.125 | 1841.86 |
| role_slot_map_score | temporal_60_40 | role_slot | core_pair | 24 | 0.042 | 0.125 | 2342.12 |
| role_slot_map_score | temporal_60_40 | role_slot | mid_single | 24 | 0.042 | 0.125 | 2328.83 |
| role_slot_map_score | temporal_60_40 | role_slot | support_pair | 24 | 0.042 | 0.125 | 2332.51 |
| role_slot_series_mean | group_to_playoff | role_slot | core_pair | 24 | 0.042 | 0.125 | 1399.04 |
| role_slot_series_mean | group_to_playoff | role_slot | mid_single | 24 | 0.042 | 0.125 | 1407.32 |
| role_slot_series_mean | group_to_playoff | role_slot | support_pair | 24 | 0.042 | 0.125 | 1401.83 |
| role_slot_series_mean | temporal_60_40 | role_slot | core_pair | 24 | 0.042 | 0.125 | 1432.66 |
| role_slot_series_mean | temporal_60_40 | role_slot | mid_single | 24 | 0.042 | 0.125 | 1428.09 |
| role_slot_series_mean | temporal_60_40 | role_slot | support_pair | 24 | 0.042 | 0.125 | 1432.02 |
| role_slot_series_top1 | group_to_playoff | role_slot | core_pair | 24 | 0.042 | 0.125 | 1782.57 |
| role_slot_series_top1 | group_to_playoff | role_slot | mid_single | 24 | 0.042 | 0.125 | 1766.96 |
| role_slot_series_top1 | group_to_playoff | role_slot | support_pair | 24 | 0.042 | 0.125 | 1772.46 |
| role_slot_series_top1 | temporal_60_40 | role_slot | core_pair | 24 | 0.042 | 0.125 | 1724.92 |
| role_slot_series_top1 | temporal_60_40 | role_slot | mid_single | 24 | 0.042 | 0.125 | 1727.67 |
| role_slot_series_top1 | temporal_60_40 | role_slot | support_pair | 24 | 0.042 | 0.125 | 1726.92 |

## Top Players / player_map_score / group_to_playoff

| Player | Team | Pos | Role | Score | p_top1 | p_top3 | p_top5 | Exp rank | Sim std |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|
| Yopaj | OG | 2 | mid | 14762.68 | 0.047 | 0.129 | 0.210 | 12.48 | 2019.98 |
| Mikoto | Aurora Gaming | 2 | mid | 14762.68 | 0.045 | 0.128 | 0.203 | 12.53 | 2005.83 |
| LarI | Team Spirit | 2 | mid | 14762.68 | 0.043 | 0.123 | 0.209 | 12.49 | 2002.20 |
| gpk~ | BoomBoys | 2 | mid | 14762.68 | 0.042 | 0.125 | 0.214 | 12.31 | 1991.45 |
| CHIRA_JUNIOR | Team Yandex | 2 | mid | 14762.68 | 0.042 | 0.132 | 0.206 | 12.48 | 2009.85 |
| lorenof | Nigma Galaxy | 2 | mid | 14762.68 | 0.042 | 0.125 | 0.208 | 12.58 | 2011.10 |
| Nisha | Team Liquid | 2 | mid | 14762.68 | 0.042 | 0.122 | 0.204 | 12.76 | 2040.37 |
| TaiLung | LGD Gaming | 2 | mid | 14762.68 | 0.041 | 0.128 | 0.205 | 12.51 | 1981.65 |
| RCY | GamerLegion | 2 | mid | 14762.68 | 0.040 | 0.123 | 0.215 | 12.40 | 1985.66 |
| bzm | 1w | 2 | mid | 14762.68 | 0.040 | 0.126 | 0.217 | 12.34 | 2015.83 |

## Top Players / player_map_score / temporal_60_40

| Player | Team | Pos | Role | Score | p_top1 | p_top3 | p_top5 | Exp rank | Sim std |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|
| RCY | GamerLegion | 2 | mid | 14106.18 | 0.052 | 0.142 | 0.229 | 12.01 | 2418.25 |
| Xm | Vici Gaming | 2 | mid | 14106.18 | 0.048 | 0.147 | 0.243 | 11.84 | 2407.53 |
| Mikoto | Aurora Gaming | 2 | mid | 14106.18 | 0.048 | 0.138 | 0.227 | 12.16 | 2413.07 |
| Satanic | PVISION | 1 | core | 14106.18 | 0.047 | 0.125 | 0.195 | 17.71 | 2377.42 |
| Pure | 1w | 1 | core | 14106.18 | 0.047 | 0.127 | 0.200 | 17.70 | 2416.07 |
| Yatoro | Team Spirit | 1 | core | 14106.18 | 0.047 | 0.124 | 0.201 | 17.57 | 2379.76 |
| NothingToSay | Xtreme Gaming | 2 | mid | 14106.18 | 0.046 | 0.134 | 0.222 | 12.19 | 2391.10 |
| Yopaj | OG | 2 | mid | 14106.18 | 0.046 | 0.130 | 0.216 | 12.36 | 2409.27 |
| Nisha | Team Liquid | 2 | mid | 14106.18 | 0.045 | 0.135 | 0.226 | 12.14 | 2374.88 |
| Ame | Xtreme Gaming | 1 | core | 14106.18 | 0.045 | 0.119 | 0.185 | 18.06 | 2424.24 |

## Top Players / player_series_mean / group_to_playoff

| Player | Team | Pos | Role | Score | p_top1 | p_top3 | p_top5 | Exp rank | Sim std |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|
| No[o]ne- | PVISION | 2 | mid | 14822.34 | 0.047 | 0.129 | 0.217 | 12.44 | 1562.70 |
| Malr1ne | Team Falcons | 2 | mid | 14822.34 | 0.046 | 0.128 | 0.208 | 12.44 | 1562.86 |
| Mikoto | Aurora Gaming | 2 | mid | 14822.34 | 0.045 | 0.124 | 0.207 | 12.49 | 1557.66 |
| CHIRA_JUNIOR | Team Yandex | 2 | mid | 14822.34 | 0.044 | 0.130 | 0.218 | 12.41 | 1560.64 |
| LarI | Team Spirit | 2 | mid | 14822.34 | 0.044 | 0.123 | 0.209 | 12.46 | 1559.50 |
| Nisha | Team Liquid | 2 | mid | 14822.34 | 0.043 | 0.123 | 0.204 | 12.42 | 1514.91 |
| Yopaj | OG | 2 | mid | 14822.34 | 0.042 | 0.128 | 0.212 | 12.57 | 1545.10 |
| bzm | 1w | 2 | mid | 14822.34 | 0.041 | 0.128 | 0.210 | 12.43 | 1536.88 |
| lorenof | Nigma Galaxy | 2 | mid | 14822.34 | 0.041 | 0.117 | 0.203 | 12.60 | 1520.21 |
| NothingToSay | Xtreme Gaming | 2 | mid | 14822.34 | 0.041 | 0.122 | 0.202 | 12.69 | 1550.25 |

## Top Players / player_series_mean / temporal_60_40

| Player | Team | Pos | Role | Score | p_top1 | p_top3 | p_top5 | Exp rank | Sim std |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|
| Ghost | GamerLegion | 1 | core | 16612.93 | 0.313 | 0.636 | 0.788 | 3.73 | 1443.83 |
| Malr1ne | Team Falcons | 2 | mid | 16814.39 | 0.192 | 0.447 | 0.619 | 5.34 | 1456.88 |
| bzm | 1w | 2 | mid | 16441.41 | 0.136 | 0.358 | 0.523 | 6.46 | 1479.88 |
| NothingToSay | Xtreme Gaming | 2 | mid | 16352.16 | 0.119 | 0.329 | 0.505 | 6.65 | 1454.06 |
| lorenof | Nigma Galaxy | 2 | mid | 16293.14 | 0.107 | 0.314 | 0.476 | 6.84 | 1445.97 |
| Bignum | GamerLegion | 4 | support | 9733.36 | 0.100 | 0.236 | 0.351 | 12.14 | 1480.18 |
| SumaiL | Nigma Galaxy | 1 | core | 15386.63 | 0.086 | 0.304 | 0.470 | 7.43 | 1484.64 |
| Pure | 1w | 1 | core | 15312.24 | 0.085 | 0.290 | 0.466 | 7.42 | 1456.46 |
| OmaR | Nigma Galaxy | 4 | support | 9491.91 | 0.081 | 0.199 | 0.296 | 13.69 | 1478.57 |
| Yuma | LGD Gaming | 1 | core | 15217.37 | 0.079 | 0.259 | 0.436 | 7.79 | 1473.27 |

## Top Players / player_series_top1 / group_to_playoff

| Player | Team | Pos | Role | Score | p_top1 | p_top3 | p_top5 | Exp rank | Sim std |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|
| RCY | GamerLegion | 2 | mid | 16752.53 | 0.046 | 0.130 | 0.215 | 12.39 | 1983.84 |
| CHIRA_JUNIOR | Team Yandex | 2 | mid | 16752.53 | 0.045 | 0.125 | 0.217 | 12.40 | 1934.60 |
| Xm | Vici Gaming | 2 | mid | 16752.53 | 0.045 | 0.122 | 0.215 | 12.30 | 1950.75 |
| Yopaj | OG | 2 | mid | 16752.53 | 0.044 | 0.129 | 0.209 | 12.57 | 1982.18 |
| bzm | 1w | 2 | mid | 16752.53 | 0.044 | 0.136 | 0.215 | 12.49 | 1963.17 |
| gpk~ | BoomBoys | 2 | mid | 16752.53 | 0.043 | 0.126 | 0.212 | 12.46 | 1968.01 |
| LarI | Team Spirit | 2 | mid | 16752.53 | 0.043 | 0.125 | 0.216 | 12.47 | 1955.06 |
| NothingToSay | Xtreme Gaming | 2 | mid | 16752.53 | 0.043 | 0.124 | 0.203 | 12.50 | 1964.85 |
| TaiLung | LGD Gaming | 2 | mid | 16752.53 | 0.043 | 0.126 | 0.207 | 12.49 | 1964.69 |
| lorenof | Nigma Galaxy | 2 | mid | 16752.53 | 0.042 | 0.125 | 0.215 | 12.46 | 1957.74 |

## Top Players / player_series_top1 / temporal_60_40

| Player | Team | Pos | Role | Score | p_top1 | p_top3 | p_top5 | Exp rank | Sim std |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|
| No[o]ne- | PVISION | 2 | mid | 11897.39 | 0.048 | 0.133 | 0.214 | 12.41 | 248.71 |
| CHIRA_JUNIOR | Team Yandex | 2 | mid | 11895.15 | 0.048 | 0.137 | 0.223 | 12.40 | 253.22 |
| RCY | GamerLegion | 2 | mid | 11894.14 | 0.046 | 0.120 | 0.202 | 12.51 | 249.32 |
| TaiLung | LGD Gaming | 2 | mid | 11896.30 | 0.045 | 0.135 | 0.215 | 12.36 | 250.90 |
| Mikoto | Aurora Gaming | 2 | mid | 11893.64 | 0.045 | 0.127 | 0.209 | 12.57 | 257.67 |
| bzm | 1w | 2 | mid | 11898.48 | 0.044 | 0.130 | 0.219 | 12.38 | 251.75 |
| Xm | Vici Gaming | 2 | mid | 11895.05 | 0.044 | 0.127 | 0.210 | 12.33 | 247.14 |
| LarI | Team Spirit | 2 | mid | 11895.34 | 0.044 | 0.122 | 0.209 | 12.48 | 246.92 |
| Yopaj | OG | 2 | mid | 11894.10 | 0.043 | 0.130 | 0.212 | 12.48 | 252.53 |
| Nisha | Team Liquid | 2 | mid | 11899.26 | 0.043 | 0.133 | 0.220 | 12.36 | 253.72 |

## Top Role Slots / role_slot_map_score / group_to_playoff

| Players | Team | Role slot | Score | p_top1 | p_top3 | p_top5 | Exp rank | Sim std |
|---|---|---|---:|---:|---:|---:|---:|---:|
| Save-, Kataomi` | BoomBoys | support_pair | 8192.86 | 0.049 | 0.131 | 0.223 | 12.37 | 1843.22 |
| Nisha | Team Liquid | mid_single | 14762.68 | 0.048 | 0.134 | 0.215 | 12.32 | 1841.39 |
| Mira, kaori | Aurora Gaming | support_pair | 8192.86 | 0.048 | 0.131 | 0.218 | 12.29 | 1847.66 |
| SumaiL, Davai | Nigma Galaxy | core_pair | 12336.69 | 0.046 | 0.127 | 0.206 | 12.57 | 1874.27 |
| lorenof | Nigma Galaxy | mid_single | 14762.68 | 0.045 | 0.127 | 0.208 | 12.35 | 1843.15 |
| No[o]ne- | PVISION | mid_single | 14762.68 | 0.045 | 0.129 | 0.208 | 12.47 | 1839.04 |
| TIMS, skem | OG | support_pair | 8192.86 | 0.045 | 0.121 | 0.207 | 12.58 | 1868.63 |
| NothingToSay | Xtreme Gaming | mid_single | 14762.68 | 0.044 | 0.131 | 0.224 | 12.46 | 1845.38 |
| Kiritych~, MieRo | BoomBoys | core_pair | 12336.69 | 0.044 | 0.125 | 0.206 | 12.43 | 1869.58 |
| RCY | GamerLegion | mid_single | 14762.68 | 0.044 | 0.120 | 0.205 | 12.57 | 1847.58 |

## Top Role Slots / role_slot_map_score / temporal_60_40

| Players | Team | Role slot | Score | p_top1 | p_top3 | p_top5 | Exp rank | Sim std |
|---|---|---|---:|---:|---:|---:|---:|---:|
| Yuma, Wisper | LGD Gaming | core_pair | 14290.72 | 0.081 | 0.208 | 0.327 | 9.59 | 2336.72 |
| skiter, ATF | Team Falcons | core_pair | 14290.72 | 0.081 | 0.220 | 0.339 | 9.57 | 2375.85 |
| Ghost, Fayde | GamerLegion | core_pair | 14290.72 | 0.077 | 0.205 | 0.321 | 9.77 | 2347.86 |
| SumaiL, Davai | Nigma Galaxy | core_pair | 14130.05 | 0.069 | 0.198 | 0.312 | 10.08 | 2396.18 |
| Ame, Xxs | Xtreme Gaming | core_pair | 13957.31 | 0.060 | 0.172 | 0.281 | 10.46 | 2324.33 |
| Satanic, Noticed | PVISION | core_pair | 13957.31 | 0.059 | 0.164 | 0.276 | 10.55 | 2321.49 |
| m1CKe, Ace | Team Liquid | core_pair | 13957.31 | 0.056 | 0.175 | 0.284 | 10.58 | 2359.50 |
| Pure, 33 | 1w | core_pair | 13957.31 | 0.055 | 0.165 | 0.280 | 10.49 | 2295.32 |
| Kiritych~, MieRo | BoomBoys | core_pair | 13774.20 | 0.049 | 0.152 | 0.253 | 11.03 | 2338.07 |
| Mikoto | Aurora Gaming | mid_single | 14290.72 | 0.049 | 0.137 | 0.223 | 12.16 | 2348.59 |

## Top Role Slots / role_slot_series_mean / group_to_playoff

| Players | Team | Role slot | Score | p_top1 | p_top3 | p_top5 | Exp rank | Sim std |
|---|---|---|---:|---:|---:|---:|---:|---:|
| Malr1ne | Team Falcons | mid_single | 14822.34 | 0.051 | 0.137 | 0.217 | 12.32 | 1426.48 |
| fy, xNova | Xtreme Gaming | support_pair | 8200.03 | 0.047 | 0.128 | 0.203 | 12.50 | 1415.18 |
| Yopaj | OG | mid_single | 14822.34 | 0.046 | 0.132 | 0.208 | 12.51 | 1430.51 |
| CHIRA_JUNIOR | Team Yandex | mid_single | 14822.34 | 0.046 | 0.136 | 0.218 | 12.31 | 1401.28 |
| bzm | 1w | mid_single | 14822.34 | 0.046 | 0.122 | 0.210 | 12.44 | 1424.88 |
| 9Class, Dukalis | PVISION | support_pair | 8200.03 | 0.045 | 0.136 | 0.215 | 12.39 | 1412.74 |
| m1CKe, Ace | Team Liquid | core_pair | 12313.06 | 0.045 | 0.133 | 0.209 | 12.52 | 1433.26 |
| Kiritych~, MieRo | BoomBoys | core_pair | 12313.06 | 0.045 | 0.133 | 0.224 | 12.48 | 1438.66 |
| gpk~ | BoomBoys | mid_single | 14822.34 | 0.045 | 0.131 | 0.212 | 12.26 | 1398.70 |
| SumaiL, Davai | Nigma Galaxy | core_pair | 12313.06 | 0.045 | 0.127 | 0.201 | 12.68 | 1402.29 |

## Top Role Slots / role_slot_series_mean / temporal_60_40

| Players | Team | Role slot | Score | p_top1 | p_top3 | p_top5 | Exp rank | Sim std |
|---|---|---|---:|---:|---:|---:|---:|---:|
| Malr1ne | Team Falcons | mid_single | 16452.20 | 0.162 | 0.404 | 0.576 | 5.92 | 1402.23 |
| bzm | 1w | mid_single | 16147.03 | 0.125 | 0.317 | 0.473 | 7.11 | 1415.88 |
| Ghost, Fayde | GamerLegion | core_pair | 13781.78 | 0.122 | 0.323 | 0.478 | 6.88 | 1424.31 |
| Yuma, Wisper | LGD Gaming | core_pair | 13686.36 | 0.119 | 0.307 | 0.469 | 7.17 | 1441.69 |
| NothingToSay | Xtreme Gaming | mid_single | 16074.01 | 0.118 | 0.312 | 0.461 | 7.32 | 1429.29 |
| lorenof | Nigma Galaxy | mid_single | 16066.87 | 0.114 | 0.300 | 0.442 | 7.48 | 1455.78 |
| skiter, ATF | Team Falcons | core_pair | 13524.02 | 0.097 | 0.288 | 0.437 | 7.55 | 1428.06 |
| Thiolicor, KJ | LGD Gaming | support_pair | 8938.69 | 0.090 | 0.241 | 0.353 | 9.14 | 1410.25 |
| Pure, 33 | 1w | core_pair | 13420.60 | 0.086 | 0.249 | 0.397 | 7.93 | 1437.50 |
| Satanic, Noticed | PVISION | core_pair | 13248.72 | 0.078 | 0.223 | 0.365 | 8.51 | 1437.46 |

## Top Role Slots / role_slot_series_top1 / group_to_playoff

| Players | Team | Role slot | Score | p_top1 | p_top3 | p_top5 | Exp rank | Sim std |
|---|---|---|---:|---:|---:|---:|---:|---:|
| Pure, 33 | 1w | core_pair | 13936.23 | 0.048 | 0.129 | 0.207 | 12.69 | 1829.59 |
| m1CKe, Ace | Team Liquid | core_pair | 13936.23 | 0.047 | 0.130 | 0.211 | 12.50 | 1793.44 |
| 9Class, Dukalis | PVISION | support_pair | 9018.43 | 0.046 | 0.124 | 0.207 | 12.51 | 1760.49 |
| Yuma, Wisper | LGD Gaming | core_pair | 13936.23 | 0.046 | 0.138 | 0.223 | 12.45 | 1823.72 |
| gpk~ | BoomBoys | mid_single | 16752.53 | 0.045 | 0.131 | 0.214 | 12.41 | 1807.47 |
| LarI | Team Spirit | mid_single | 16752.53 | 0.044 | 0.128 | 0.206 | 12.53 | 1749.66 |
| watson, DM | Team Yandex | core_pair | 13936.23 | 0.044 | 0.126 | 0.208 | 12.41 | 1783.25 |
| NothingToSay | Xtreme Gaming | mid_single | 16752.53 | 0.044 | 0.128 | 0.206 | 12.60 | 1770.23 |
| No[o]ne- | PVISION | mid_single | 16752.53 | 0.044 | 0.121 | 0.207 | 12.55 | 1784.80 |
| Save-, Kataomi` | BoomBoys | support_pair | 9018.43 | 0.044 | 0.118 | 0.209 | 12.56 | 1775.94 |

## Top Role Slots / role_slot_series_top1 / temporal_60_40

| Players | Team | Role slot | Score | p_top1 | p_top3 | p_top5 | Exp rank | Sim std |
|---|---|---|---:|---:|---:|---:|---:|---:|
| Ghost, Fayde | GamerLegion | core_pair | 16985.76 | 0.342 | 0.620 | 0.762 | 3.85 | 1734.73 |
| bzm | 1w | mid_single | 19591.88 | 0.299 | 0.581 | 0.729 | 4.28 | 1748.55 |
| NothingToSay | Xtreme Gaming | mid_single | 18740.52 | 0.140 | 0.381 | 0.554 | 6.23 | 1708.25 |
| Malr1ne | Team Falcons | mid_single | 18638.85 | 0.131 | 0.348 | 0.520 | 6.58 | 1737.21 |
| Ari, Whitemon | 1w | support_pair | 9894.03 | 0.096 | 0.234 | 0.360 | 9.24 | 1781.63 |
| Saksa, Malady | Team Yandex | support_pair | 9933.73 | 0.092 | 0.251 | 0.377 | 8.97 | 1707.51 |
| skiter, ATF | Team Falcons | core_pair | 15451.99 | 0.085 | 0.276 | 0.428 | 7.66 | 1750.93 |
| fy, xNova | Xtreme Gaming | support_pair | 9849.07 | 0.083 | 0.236 | 0.360 | 9.22 | 1721.50 |
| Boxi, tOfu | Team Liquid | support_pair | 9722.39 | 0.080 | 0.210 | 0.323 | 9.74 | 1709.70 |
| Pure, 33 | 1w | core_pair | 15290.91 | 0.076 | 0.237 | 0.392 | 8.12 | 1718.93 |

