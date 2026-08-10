from __future__ import annotations

import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "ewc_2026_fantasy_compact.sqlite"


def main() -> None:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    print("[raw payload counts by source]")
    for row in cur.execute(
        """
        SELECT source_name, COUNT(*) AS payloads
        FROM raw_match_source_payloads
        GROUP BY source_name
        ORDER BY source_name
        """
    ).fetchall():
        print(row)

    print("\n[staging nonzero coverage by source/stat]")
    for row in cur.execute(
        """
        SELECT
            source_name,
            stat_name,
            COUNT(*) AS total_rows,
            SUM(CASE WHEN COALESCE(raw_value, 0) != 0 THEN 1 ELSE 0 END) AS nonzero_rows,
            ROUND(MAX(COALESCE(raw_value, 0)), 4) AS max_raw_value
        FROM stg_player_match_enriched_stats
        GROUP BY source_name, stat_name
        ORDER BY source_name, stat_name
        """
    ).fetchall():
        print(row)

    print("\n[final fantasy stat coverage for planned backfill stats]")
    for row in cur.execute(
        """
        SELECT
            stat_name,
            COUNT(*) AS total_rows,
            SUM(CASE WHEN COALESCE(raw_value, 0) != 0 THEN 1 ELSE 0 END) AS nonzero_raw_rows,
            SUM(CASE WHEN COALESCE(base_points, 0) != 0 THEN 1 ELSE 0 END) AS nonzero_point_rows,
            ROUND(MAX(COALESCE(raw_value, 0)), 4) AS max_raw_value,
            ROUND(MAX(COALESCE(base_points, 0)), 4) AS max_base_points
        FROM fantasy_player_map_stat_points
        WHERE stat_name IN (
            'first_blood', 'stuns', 'runes_grabbed', 'wards_placed',
            'smokes_used', 'camps_stacked', 'courier_kills', 'roshan_kills',
            'watchers_taken', 'lotus', 'tormentor_kills'
        )
        GROUP BY stat_name
        ORDER BY stat_name
        """
    ).fetchall():
        print(row)

    print("\n[coverage view with zero semantics]")
    for row in cur.execute(
        """
        SELECT
            stat_name,
            preferred_source,
            fallback_source,
            coverage_status,
            expected_rows,
            final_rows,
            has_stage_evidence,
            is_row_complete,
            zero_raw_rows,
            nonzero_raw_rows,
            field_present_rows,
            sparse_zero_rows,
            source_missing_rows,
            objective_derived_rows,
            clamped_rows,
            min_raw_value,
            max_raw_value
        FROM analytics_fantasy_backfill_coverage
        ORDER BY stat_name
        """
    ).fetchall():
        print(row)

    print("\n[sanity issues view]")
    sanity_rows = cur.execute(
        """
        SELECT stat_name, issue_type, issue_rows, sample_min_value, sample_max_value
        FROM analytics_fantasy_backfill_sanity
        ORDER BY stat_name, issue_type
        """
    ).fetchall()
    if sanity_rows:
        for row in sanity_rows:
            print(row)
    else:
        print("no sanity issues detected")

    print("\n[stat catalog source metadata]")
    for row in cur.execute(
        """
        SELECT stat_name, preferred_source, fallback_source, source_field_name, coverage_status
        FROM fantasy_scoring_stat_catalog
        WHERE stat_name IN (
            'first_blood', 'stuns', 'runes_grabbed', 'wards_placed',
            'smokes_used', 'camps_stacked', 'courier_kills', 'roshan_kills',
            'watchers_taken', 'lotus', 'tormentor_kills'
        )
        ORDER BY stat_name
        """
    ).fetchall():
        print(row)

    con.close()


if __name__ == "__main__":
    main()
