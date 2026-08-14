# Data sources and provenance

This file describes the **roles**, **coverage**, and **caveats** of the external sources used by the project. It summarizes the source strategy already reflected in the SQLite database; it is not a fresh independent verification of every source page.

## Main sources

| Source | Role in the project | Current practical status |
|---|---|---|
| Liquipedia - Esports World Cup 2026 | Tournament format, stages, participants, roster context | Used as metadata / roster source |
| Liquipedia - The International 2026 | TI 2026 participant context and qualification cross-check | Stored as TI qualification context |
| Dotabuff EWC 2026 pages | Match list, match pages, player nick / position evidence per map | Main tournament/match discovery context |
| OpenDota heroes API | Hero ID to hero-name mapping | Fully usable |
| OpenDota match API | Player-map stat backfills for missing fantasy categories | Fully usable for current 9 covered backfill stats |
| STRATZ GraphQL API | Cross-check, schema probe, and replay-metadata exploration source | Partially usable; helpful for probing, but not yet a complete final-stat source |
| BattlePass Fantasy guide | Source of fantasy scoring coefficients and metric definitions | Used as rules reference |
| Dot Esports TI 2026 article | Secondary participant cross-check | Supporting provenance only |

## Source registry in the database

The public view `analytics_sources` exposes the stored source registry:

- source key
- source name
- URL
- snapshot/fetch time
- content type / content status
- hashes where available
- project notes

This registry supports source-first behavior in the query layer.

## How fantasy-stat coverage is split by source

### OpenDota-backed and currently covered

As of **August 14, 2026**, the following fantasy stats are backfilled from OpenDota and rebuilt into final fantasy point tables:

- `first_blood`
- `stuns`
- `runes_grabbed`
- `wards_placed`
- `smokes_used`
- `camps_stacked`
- `courier_kills`
- `roshan_kills`
- `tormentor_kills`

Notes:

- `tormentor_kills` is derived from OpenDota `objectives` entries with `CHAT_MESSAGE_MINIBOSS_KILL`.
- `smokes_used` can come from either `item_uses.smoke_of_deceit` or `item_usage.smoke_of_deceit`.
- One anomalous negative `stuns` value from source payloads is clamped to zero and surfaced through the sanity view.

### Replay-resolved and currently covered

- `watchers_taken`
- `lotus`

These are resolved from replay-derived team-slot counters and then matched to players through OpenDota `player_slot`:

- raw replay layer: `replay_team_metric_final`
- resolved player layer: `replay_player_metric_resolved`
- canonical final player stat layer: `fantasy_player_map_stat_points`

This means:

- the main compact database now contains player-level `watchers_taken` and `lotus`
- raw replay provenance remains queryable separately
- the remaining STRATZ connector is no longer required for these two metrics

### STRATZ availability in the current environment

The STRATZ path should be treated as optional and environment-dependent.

What is true in the current project state:

- the codebase supports schema probes and browser-assisted GraphQL checks
- a bearer token is still required for live STRATZ queries
- replay-related metadata such as `clusterId`, `didRequestDownload`, and `retryMatchDownload(...)` can be explored
- this still does **not** guarantee downloadable replay archives or final player-level `watchers_taken` / `lotus` rows for TI

The project supports reading these variables from a local repository `.env` file, so a typical setup is:

```text
STRATZ_API_TOKEN=your_token_here
```

## Real zeros vs unsupported zeros

This distinction matters.

### Real observed zero

A player had the stat tracked by the source, and the value is truly zero.

Examples:

- `first_blood = 0`
- `courier_kills = 0`
- `roshan_kills = 0`

### Sparse-key zero

The source often omits a nested key when the value is zero, but that omission is still interpreted as a reliable zero for that metric.

Current example:

- `smokes_used`

In the staging layer this appears as `coverage_note = 'field_absent_zero_assumed'`.

### Unsupported / unsourced metric

The database may still contain historical zero rows, but there is **no stage evidence** from the currently supported source pipeline.

These should be interpreted via `analytics_fantasy_backfill_coverage`, not by reading raw zero counts alone.

## Recommended source-trust order

For questions about already-modeled tournament stats:

1. Public `analytics_*` views
2. Underlying core SQLite tables
3. Source registry / cached provenance
4. External live source only if the fact is absent from the database

For missing fantasy categories:

1. `analytics_fantasy_backfill_coverage`
2. `analytics_fantasy_backfill_sanity`
3. `stg_player_match_enriched_stats`
4. `raw_match_source_payloads`
5. Live source fetch only if needed

## Important caveats

- External pages can change after a snapshot.
- The project currently stores **157** maps while the original expected Dotabuff total is **159**.
- Support-oriented fantasy metrics remain much weaker than core and mid interpretation.
- `watchers_taken` and `lotus` are supported in the main compact database once replay files are successfully processed, but their raw provenance still comes from replay counters rather than the regular OpenDota per-player stat payload.
- for TI 2026 specifically, the replay-parsing code path is ready but public replay downloads are currently the limiting factor.
