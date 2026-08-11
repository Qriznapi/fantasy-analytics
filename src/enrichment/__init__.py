"""Enrichment helpers for backfilling fantasy stat coverage."""

from .opendota_backfill import (
    OPENDOTA_SUPPORTED_STATS,
    ensure_backfill_schema,
    extract_opendota_stat_rows,
    fetch_many_opendota_matches,
    fetch_opendota_match_payload,
    list_target_match_ids,
    refresh_stat_catalog_metadata,
    summarize_nonzero_coverage,
    upsert_raw_payload,
    upsert_stage_rows,
    upsert_stat_points_from_staging,
)
from .replay_backfill import (
    ensure_replay_backfill_schema,
    ensure_replay_backfill_views,
    import_replay_metric_csvs,
    summarize_replay_metric_import,
)
from .stratz_backfill import STRATZ_SUPPORTED_STATS, run_stratz_preflight
