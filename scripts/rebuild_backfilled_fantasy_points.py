from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
DB_PATH = PROJECT_ROOT / "data" / "ewc_2026_fantasy_compact.sqlite"
sys.path.insert(0, str(SRC_DIR))

from enrichment.opendota_backfill import OPENDOTA_SUPPORTED_STATS, upsert_stat_points_from_staging
from enrichment.stratz_backfill import STRATZ_SUPPORTED_STATS
from fantasy_profile_constructor import recalculate_profile_scores


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply staged fantasy stat backfills and rebuild profile scores.")
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--source", choices=["opendota", "stratz"], default="opendota")
    parser.add_argument("--profile-id", action="append", default=[])
    parser.add_argument("--run-id", default="manual_backfill_run")
    parser.add_argument(
        "--full-stat-refresh",
        action="store_true",
        help="Replace all rows for the targeted stat_names. Default behavior only rewrites staged matches.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    con = sqlite3.connect(args.db_path)
    stat_names = OPENDOTA_SUPPORTED_STATS if args.source == "opendota" else STRATZ_SUPPORTED_STATS
    summary = upsert_stat_points_from_staging(
        con,
        source_name=args.source,
        stat_names=stat_names,
        run_id=args.run_id,
        restrict_to_staged_matches=not args.full_stat_refresh,
    )
    print("[stat_point_rows_written]", summary)

    if args.profile_id:
        profile_ids = args.profile_id
    else:
        profile_ids = [
            row[0]
            for row in con.execute("SELECT profile_id FROM fantasy_scoring_profiles ORDER BY is_default DESC, profile_id")
        ]

    print("[rebuilding_profiles]", profile_ids)
    for profile_id in profile_ids:
        recalculate_profile_scores(con, profile_id)
    con.commit()
    con.close()
    print("rebuild complete")


if __name__ == "__main__":
    main()
