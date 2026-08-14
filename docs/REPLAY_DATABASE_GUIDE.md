# Replay database guide

This guide describes the replay-derived layer used for `watchers_taken` and `lotus`.

There are two practical modes in the current project:

- historical EWC replay backfill, which is already fully merged into the compact database
- live TI replay preparation, where manifest export and parser wrappers are ready but public replay archive download is still the blocking step

## Relevant paths

- replay cache for TI: `data/cache_ti_2026/replays/`
- replay cache for EWC: event-specific local cache if you choose to rebuild replay parsing
- merged player-level results: `fantasy_player_map_stat_points`
- raw replay slot layer: `replay_team_metric_final`
- replay-to-player resolved layer: `replay_player_metric_resolved`

## Main replay scripts

- `scripts/export_replay_manifest_from_db.py`
- `scripts/download_replays_from_manifest.py`
- `scripts/download_replay_via_browser.py`
- `scripts/run_replay_team_metric_batch.py`
- `scripts/import_replay_team_metrics.py`
- `scripts/merge_replay_metrics_into_compact_db.py`
- `scripts/reconcile_replay_player_metrics.py`
- `scripts/backfill_replay_metrics_for_event.py`

## Recommended workflow

If replay archives already exist locally:

```bash
python scripts/backfill_replay_metrics_for_event.py --event-id ewc2026 --skip-download
python scripts/backfill_replay_metrics_for_event.py --event-id ti2026 --skip-download
```

If you want to export a replay manifest directly from the compact database:

```bash
python scripts/export_replay_manifest_from_db.py --event-id ti2026
```

If you later obtain `.dem.bz2` files manually, place them in the event cache and rerun the wrapper.

## Main replay objects

- `replay_team_metric_events` - event-level counter changes from replay parsing.
- `replay_team_metric_final` - final metric values by `match_id + team_side + team_slot + stat_name`.

## Public replay views

- `analytics_replay_team_metrics_long` - long-format replay metrics.
- `analytics_replay_team_metrics_wide` - one row per `match_id + team_side + team_slot`.
- `analytics_replay_match_coverage` - how many replay rows were loaded per match.
- `analytics_replay_metric_summary` - metric-level coverage summary.

## Useful SQL

### One match, all replay team-slot metrics

```sql
SELECT *
FROM analytics_replay_team_metrics_wide
WHERE match_id = 8904419709
ORDER BY team_side, team_slot;
```

### Coverage by metric

```sql
SELECT *
FROM analytics_replay_metric_summary
ORDER BY stat_name;
```

### Coverage by match

```sql
SELECT *
FROM analytics_replay_match_coverage
ORDER BY match_id;
```

## Current limitation on TI 2026

As of **August 14, 2026**:

- TI replay manifests can be exported successfully
- the current TI matches resolve to replay host `cluster=413`
- public `.dem.bz2` retrieval from that host is not reliable in this environment
- browser-assisted STRATZ probes can inspect some replay metadata, but they still do not yield a downloadable archive by themselves

So for TI:

- replay parsing code is ready
- replay import code is ready
- the blocking step is obtaining the actual replay archives
