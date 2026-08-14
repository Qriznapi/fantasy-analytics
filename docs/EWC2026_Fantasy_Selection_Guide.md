# EWC 2026 Fantasy Selection Guide

Guide snapshot: compact database with EWC 2026 fantasy outputs plus the current qualified-team analytical layer. This guide is meant to be practical first: it explains how to choose stats, how to preserve flexibility, and how to convert the data into a usable banner decision.

## What this guide is for

Use this guide when you want to answer three questions:

1. Which stats are actually worth targeting on a banner.
2. Which teams or player combinations are good for those stats.
3. How to make a choice without locking yourself into only one rigid "best" option.

The guide is universal in the sense that it starts from `x1.0` stat value and role-level repeatability, so it stays useful even if your exact banner multipliers differ. A private worked example is included at the end for one concrete profile.

## How to use the guide

1. Start from `P75`, not from `Max`.
2. Use `Avg` as a sanity check, not as the main selection criterion.
3. Use `Trust` to downweight metrics that are correct enough to be useful but structurally less clean than standard OpenDota-derived stats.
4. Prefer stat bundles that naturally work together instead of fighting each other.
5. Only after choosing the stat family should you choose the exact team or player combination.

Short interpretation:

- `P75` = "good realistic upside"; usually the best single number for fantasy drafting.
- `Avg` = how much the stat gives on an ordinary map.
- `Max` = pure ceiling; useful, but too noisy if used alone.
- `Trust` = subjective data-confidence score from `1` to `10`.

## Core ideas behind good fantasy picks

### 1. Synergy matters more than isolated stat strength

The best banners usually combine stats that like the same game script:

- long, farm-heavy core games: `creep_score`, `gpm`, often `teamfight participation`
- active mid games: `runes_grabbed`, `teamfight participation`, then one of `creep_score`, `gpm`, `kills`
- utility support games: `teamfight participation` plus blue support stats such as `wards placed`, `smokes used`, `camps stacked`, `watchers taken`

Bad combinations are usually the ones where one stat wants a very different kind of game than the other two.

### 2. Ceiling matters, but not alone

Fantasy scoring eventually cares a lot about the best maps of the best series, so pure upside matters. But chasing only spikes is dangerous. That is why this guide prioritizes:

- first: `P75`
- second: stat synergy
- third: player / team fit
- fourth: ceiling checks via `Max`

### 3. Flexibility is better than a single hard recommendation

If several options sit in the same band, keep them alive as alternatives. In practice, a strong fantasy draft usually comes from a shortlist of:

- `3-5` stat bundles per role
- `4-8` role-slot combinations per role
- `2-3` final lineups depending on your risk appetite

## Role-by-role practical recommendations

## Core pair

### Best single stats to target

| Stat | Color | P75 x1 | Avg x1 | Max x1 | Trust | Practical meaning |
|---|---|---:|---:|---:|---:|---|
| creep score | Red | 1645.50 | 1404.40 | 2946.00 | 10 | Best pure core farming anchor; strong in long maps and stable enough to build around. |
| gpm | Red | 1495.00 | 1352.59 | 1792.00 | 10 | Strong second farm stat; combines naturally with creeps and good team performance. |
| teamfight participation | Green | 1464.15 | 1298.73 | 1866.55 | 10 | Best universal green core stat; upgrades both active and long-game core pairs. |
| deaths | Red | 1560.00 | 1241.92 | 1950.00 | 10 | Surprisingly strong, but context-heavy; better as a complementary stat than as the whole identity. |
| kills | Red | 909.50 | 712.45 | 2247.00 | 10 | Good ceiling stat; less repeatable than farm anchors but very usable when the pair is naturally high-kill. |
| camps stacked | Blue | 936.00 | 697.37 | 2340.00 | 9 | Niche but stronger than many expect; useful if your core pair naturally picks it up. |
| runes grabbed | Blue | 634.50 | 462.09 | 1339.50 | 9 | Not a primary core stat, but can be a useful third-stat differentiator. |

### Best core stat bundles

| Stat combination | P75 x1 | Avg x1 | Max x1 | When to use |
|---|---:|---:|---:|---|
| creep score + gpm + teamfight participation | 4579.83 | 4055.72 | 6219.74 | Default high-quality core bundle; best general starting point. |
| deaths + gpm + teamfight participation | 4427.90 | 3893.24 | 4987.30 | Good when you want less farm concentration and more broad map involvement. |
| creep score + deaths + teamfight participation | 4425.65 | 3945.05 | 5598.24 | Good hybrid bundle with stable floor and real upside. |
| creep score + kills + teamfight participation | 3990.28 | 3415.58 | 5564.55 | Better for explosive cores than for purely disciplined macro teams. |
| creep score + gpm + roshan kills | 3867.25 | 3296.58 | 6685.50 | Ceiling-chasing option; stronger if you deliberately want a higher-variance path. |

### Flexible core shortlist

These are not "pick only one"; they are the best practical pool to draft from.

| Type | Team | Players | Why they belong in the pool |
|---|---|---|---|
| Safe all-rounder | GamerLegion | Ghost, Fayde | Best current optimizer-style anchor for many aggressive and balanced paths. |
| Safe all-rounder | Xtreme Gaming | Ame, Xxs | Strong for farm-heavy bundles and very healthy `creep_score` profile. |
| Safe all-rounder | LGD Gaming | Yuma, Wisper | Good across farm and utility-adjacent core blue stats; versatile. |
| Ceiling-focused | Team Falcons | skiter, ATF | Very strong in aggressive slates and good `roshan kills` / high-impact scripts. |
| Ceiling-focused | Team Spirit | Yatoro, Collapse | Best when you want more kill-and-fight upside. |
| Balanced alternative | 1w | Pure, 33 | Strong across several red/blue directions and easy to keep as a flexible backup. |
| Profile-fit alternative | PVISION | Satanic, Noticed | Useful when your banner leans heavily into kills or high-activity scripts. |

## Mid

### Best single stats to target

| Stat | Color | P75 x1 | Avg x1 | Max x1 | Trust | Practical meaning |
|---|---|---:|---:|---:|---:|---|
| runes grabbed | Blue | 1833.00 | 1377.89 | 3384.00 | 9 | Best standalone mid stat in this pool; very strong identity stat. |
| teamfight participation | Green | 1699.20 | 1493.94 | 2124.00 | 10 | Best universal green mid stat and one of the cleanest anchors overall. |
| deaths | Red | 1560.00 | 1236.61 | 1950.00 | 10 | Very efficient on paper, but better as support to the main bundle than as the whole thesis. |
| creep score | Red | 1482.00 | 1256.66 | 4071.00 | 10 | Best red mid stat when you want farm-carrying mids. |
| gpm | Red | 1422.00 | 1274.07 | 2142.00 | 10 | Usually paired with runes and fight volume rather than used alone. |
| kills | Red | 1177.00 | 872.95 | 2568.00 | 10 | Good upgrade for high-tempo mids with finishing responsibility. |
| camps stacked | Blue | 702.00 | 443.67 | 2574.00 | 9 | Real upside, but more situational than the top three mid stats. |

### Best mid stat bundles

| Stat combination | P75 x1 | Avg x1 | Max x1 | When to use |
|---|---:|---:|---:|---|
| deaths + runes grabbed + teamfight participation | 4775.50 | 4108.44 | 6352.29 | Best broad mid bundle if you want consistent production. |
| creep score + runes grabbed + teamfight participation | 4758.07 | 4128.49 | 8098.15 | Best mixed farm-and-activity package; excellent universal choice. |
| gpm + runes grabbed + teamfight participation | 4691.20 | 4145.90 | 7024.15 | Strong if you like mids who scale while still controlling map tempo. |
| kills + runes grabbed + teamfight participation | 4421.89 | 3744.78 | 7323.15 | Better aggressive option. |
| gpm + runes grabbed + stuns | 3693.17 | 3078.91 | 5974.30 | Interesting alternative when teamfight share is a little weaker but spell impact is high. |

### Flexible mid shortlist

| Type | Team | Player | Why they belong in the pool |
|---|---|---|---|
| Universal top option | 1w | bzm | Best aggressive/balanced role-slot result in several decision layers. |
| Universal top option | Team Falcons | Malr1ne | Strongest pure single-player rescoring profile; excellent rune/fight fit. |
| Universal top option | Xtreme Gaming | NothingToSay | Very healthy mix of runes, teamfight, and clean repeatability. |
| Balanced alternative | Team Liquid | Nisha | Still one of the strongest profile-specific mids when banner weights fit him. |
| Balanced alternative | Nigma Galaxy | lorenof | Good if you want a middle ground between stable production and upside. |
| Niche alternative | GamerLegion | RCY | Useful when you specifically want `creep_score`-leaning mid value. |

## Support pair

### Best single stats to target

| Stat | Color | P75 x1 | Avg x1 | Max x1 | Trust | Practical meaning |
|---|---|---:|---:|---:|---:|---|
| teamfight participation | Green | 1517.14 | 1401.65 | 2124.00 | 10 | Best universal support anchor; safest green support choice. |
| wards placed | Blue | 1228.50 | 1074.43 | 2398.50 | 9 | One of the most useful blue support stats; very practical and interpretable. |
| smokes used | Blue | 1172.00 | 950.07 | 2197.50 | 9 | Strong macro support stat, especially for coordinated teams. |
| camps stacked | Blue | 1111.50 | 845.64 | 2340.00 | 9 | Excellent if the support pair genuinely contributes stack value. |
| deaths | Red | 1170.00 | 712.43 | 1950.00 | 10 | Valuable but context-sensitive; better as a side stat than main support identity. |
| watchers taken | Blue | 441.00 | 370.41 | 735.00 | 8 | Useful situational blue stat; trustworthy enough to use, but not the first anchor. |
| lotus | Blue | 264.00 | 180.36 | 528.00 | 8 | Works as a profile-specialized addition rather than a universal default. |

### Best support stat bundles

| Stat combination | P75 x1 | Avg x1 | Max x1 | When to use |
|---|---:|---:|---:|---|
| camps stacked + teamfight participation + wards placed | 3777.29 | 3321.73 | 6242.32 | Best broad support package if you want repeatability. |
| smokes used + teamfight participation + wards placed | 3744.31 | 3426.16 | 6333.82 | Best utility-heavy package for disciplined macro teams. |
| camps stacked + smokes used + teamfight participation | 3629.07 | 3197.37 | 6041.32 | Good high-utility alternative. |
| runes grabbed + teamfight participation + wards placed | 3180.32 | 2917.93 | 5405.32 | Good if your pair naturally contests map resources. |
| teamfight participation + wards placed + watchers taken | 3097.69 | 2846.50 | 4577.32 | Best watcher-oriented line. |
| camps stacked + teamfight participation + watchers taken | 3022.50 | 2617.71 | 4284.82 | More niche, but still valid for a specialized blue/green support profile. |

### Flexible support shortlist

| Type | Team | Players | Why they belong in the pool |
|---|---|---|---|
| Universal top option | 1w | Ari, Whitemon | Best current support-pair rescoring result and useful on several blue setups. |
| Universal top option | Team Yandex | Saksa, Malady | Very strong practical option with stable utility profile. |
| Universal top option | Xtreme Gaming | fy, xNova | Best support pair for classic utility blue stat bundles. |
| Balanced alternative | GamerLegion | Bignum, Speeed | Good teamfight plus ward/smoke profile. |
| Balanced alternative | Team Liquid | Boxi, tOfu | Useful if you want stronger ceiling while accepting some variance. |
| Specialized alternative | LGD Gaming | Thiolicor, KJ | Good for watcher/rune-oriented blue support ideas. |
| Specialized alternative | Team Falcons | Cr1t-, Sneyking | More profile-dependent, but still very viable when the banner likes their stat mix. |

## Practical decision framework

If you do not want to overthink every number, use this three-track approach.

### Conservative path

Choose teams that keep showing up in the stable decision layer, even if their raw ceiling is not the absolute highest.

- Core candidates: `Virtus.pro`, `MOUZ`, `GamerLegion`, `Rune Eaters`
- Mid candidates: `MOUZ`, `Virtus.pro`, `1w`
- Support candidates: `Virtus.pro`, `Rune Eaters`, `MOUZ`, `1w`

Use this path when you care more about avoiding a weak result than about hitting the single highest ceiling.

### Balanced path

Use teams that stay high both in practical role-slot decisions and in broader rescoring tables.

- Core candidates: `GamerLegion`, `Team Falcons`, `1w`, `LGD Gaming`
- Mid candidates: `1w`, `Team Falcons`, `Xtreme Gaming`, `Team Liquid`
- Support candidates: `1w`, `Team Yandex`, `Xtreme Gaming`, `Virtus.pro`

This is the default recommendation path for most users.

### Aggressive path

Lean into stronger upside and higher-volatility stat bundles.

- Core candidates: `GamerLegion`, `Team Falcons`, `LGD Gaming`, `PVISION`
- Mid candidates: `1w`, `Team Falcons`, `Xtreme Gaming`, `Nigma Galaxy`
- Support candidates: `1w`, `Team Yandex`, `Xtreme Gaming`, `GamerLegion`, `Team Liquid`

Use this path when you want to maximize tournament-winning upside rather than median safety.

## Suggested shortlists instead of one fixed answer

If you want a compact but flexible pool, this is a good working shortlist.

### Core pool

- `Ghost, Fayde` [GamerLegion]
- `skiter, ATF` [Team Falcons]
- `Ame, Xxs` [Xtreme Gaming]
- `Yuma, Wisper` [LGD Gaming]
- `Pure, 33` [1w]

### Mid pool

- `bzm` [1w]
- `Malr1ne` [Team Falcons]
- `NothingToSay` [Xtreme Gaming]
- `Nisha` [Team Liquid]
- `lorenof` [Nigma Galaxy]

### Support pool

- `Ari, Whitemon` [1w]
- `Saksa, Malady` [Team Yandex]
- `fy, xNova` [Xtreme Gaming]
- `Bignum, Speeed` [GamerLegion]
- `Boxi, tOfu` [Team Liquid]

That pool keeps meaningful freedom of choice without becoming so wide that the guide stops being actionable.

## Current banner profile example

This section is intentionally specific. It shows how the general rules above turn into a real recommendation for one stored banner.

### Stored profile formula

| Role | Slot | Stat | Multiplier | Notes |
|---|---:|---|---:|---|
| core | 1 | kills | 2.50 | Core banner: kills 250% |
| core | 2 | creep_score | 2.50 | Core banner: creep score 250% |
| core | 3 | teamfight_participation | 1.80 | Core banner: teamfight 180% |
| mid | 1 | creep_score | 2.70 | Mid banner: creep score 270% |
| mid | 2 | runes_grabbed | 1.80 | Mid banner: runes grabbed 180% |
| mid | 3 | teamfight_participation | 2.70 | Mid banner: teamfight 270% |
| support | 1 | lotus | 3.20 | Support banner: lotuses gained 320% |
| support | 2 | watchers_taken | 2.10 | Support banner: watchers taken 210% |
| support | 3 | teamfight_participation | 1.50 | Support banner: teamfight 150% |

### What this profile wants

- Core wants exactly what the general core section likes most: `creep_score` plus `teamfight`, with `kills` as the explosive third component.
- Mid strongly prefers the classic `creep_score + runes_grabbed + teamfight participation` package.
- Support is unusual: it is not a generic utility banner, because `lotus` and `watchers_taken` are weighted very aggressively. That means general support rankings matter, but profile-specific support rankings matter more than usual.

### Practical recommendations for this profile

#### Core

| Team | Players | Why they fit |
|---|---|---|
| GamerLegion | Ghost, Fayde | Best overall fit for the current profile; combines farm and active conversion well. |
| Team Falcons | skiter, ATF | Best aggressive alternative; slightly more volatile, still elite. |
| Xtreme Gaming | Ame, Xxs | Excellent if you want strong farm identity with real ceiling. |
| Team Spirit | Yatoro, Collapse | Better if you want more kill pressure and spike potential. |
| LGD Gaming | Yuma, Wisper | Good broader all-round option with less "all-in" feel. |

#### Mid

| Team | Player | Why they fit |
|---|---|---|
| Team Falcons | Malr1ne | Best direct optimizer result for this exact profile. |
| Xtreme Gaming | NothingToSay | Very clean profile fit; strong all-around alternative. |
| Team Liquid | Nisha | Still excellent for this banner because of the exact weighted stat mix. |
| 1w | bzm | Slightly lower on this exact profile than in the universal rankings, but still elite. |
| Aurora Gaming | Mikoto | Useful deeper alternative if you want to widen the pool. |

#### Support

| Team | Players | Why they fit |
|---|---|---|
| Team Falcons | Cr1t-, Sneyking | Best exact-profile result because the banner overweights `lotus` and `watchers_taken`. |
| Xtreme Gaming | fy, xNova | Best broad utility alternative and still close on this profile. |
| 1w | Ari, Whitemon | Strong universal pair that remains good even on this more specialized banner. |
| Team Liquid | Boxi, tOfu | Higher-variance support alternative with real spike upside. |
| Team Yandex | Saksa, Malady | Safe practical fallback if you want less dependence on the rarer blue metrics. |

### Recommended final builds for this profile

#### Safe-leaning

- Core: `Ghost, Fayde` [GamerLegion]
- Mid: `NothingToSay` [Xtreme Gaming]
- Support: `fy, xNova` [Xtreme Gaming]

#### Balanced

- Core: `Ghost, Fayde` [GamerLegion]
- Mid: `Malr1ne` [Team Falcons]
- Support: `Cr1t-, Sneyking` [Team Falcons]

#### Aggressive

- Core: `skiter, ATF` [Team Falcons]
- Mid: `Malr1ne` [Team Falcons]
- Support: `Cr1t-, Sneyking` [Team Falcons]

## Final takeaway

If you want one simple universal rule, use this:

- core: start from `creep_score + gpm + teamfight`, then branch into kills or deaths if your banner pushes you there
- mid: start from `runes_grabbed + teamfight`, then add `creep_score` or `gpm`
- support: start from `teamfight + wards/smokes/camps`, then only force `lotus` or `watchers` when your banner explicitly rewards them

If you want one practical drafting rule, use this:

- do not lock yourself into one "perfect" option
- keep a shortlist of `3-5` viable choices per role
- pick the final lineup according to whether you want a conservative, balanced, or aggressive build

For raw supporting tables and notebook outputs, use:

- [BANNER_RESCORING_SCORECARD.md](BANNER_RESCORING_SCORECARD.md)
- [BANNER_DECISION_SCORECARD.md](BANNER_DECISION_SCORECARD.md)
- [database_guide.md](database_guide.md)
