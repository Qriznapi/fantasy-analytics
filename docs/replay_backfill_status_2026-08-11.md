# Replay backfill status

Date: `2026-08-11`

- Tournament matches in manifest: `157`
- Matches with replay URL: `157`
- Matches loaded into `replay_team_metric_final`: `157`
- Matches loaded into `replay_team_metric_events`: `157`

## Metric summary

| stat_name | row_count | nonzero_rows | min_raw_value | max_raw_value |
| --- | ---: | ---: | ---: | ---: |
| acquired_madstone | 1570 | 1570 | 6.0 | 16.0 |
| current_madstone | 1570 | 1019 | 0.0 | 15.0 |
| lotuses_taken | 1570 | 853 | 0.0 | 6.0 |
| tormentor_kills | 1570 | 0 | 0.0 | 0.0 |
| watchers_taken | 1570 | 954 | 0.0 | 9.0 |

## Where to look

- `replay_team_metric_events` - event-level replay counter updates.
- `replay_team_metric_final` - final values per `match_id + team_side + team_slot + stat_name`.
- `analytics_replay_team_metrics_long` - public long-format replay view.
- `analytics_replay_team_metrics_wide` - one row per team-slot with replay metrics as columns.
- `analytics_replay_match_coverage` - per-match replay coverage summary.
- `analytics_replay_metric_summary` - per-metric coverage summary.
