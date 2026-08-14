from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from math import ceil


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

import sqlite3

from project_db import resolve_db_path
from tournament_config import known_event_ids
from enrichment.opendota_backfill import (
    OPENDOTA_SUPPORTED_STATS,
    ensure_backfill_schema,
    fetch_many_opendota_matches,
    list_target_match_ids,
    refresh_stat_catalog_metadata,
)
from enrichment.stratz_backfill import STRATZ_SUPPORTED_STATS, run_stratz_preflight


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill missing fantasy stats from external sources.")
    parser.add_argument("--event-id", default="ewc2026", choices=known_event_ids())
    parser.add_argument("--db-path", default="")
    parser.add_argument("--match-limit", type=int, default=5)
    parser.add_argument("--match-ids", default="")
    parser.add_argument("--source", choices=["opendota", "stratz"], default="opendota")
    parser.add_argument("--write-raw", action="store_true")
    parser.add_argument("--write-stage", action="store_true")
    parser.add_argument("--sleep-sec", type=float, default=0.5)
    parser.add_argument("--timeout-sec", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--skip-existing-raw", action="store_true")
    parser.add_argument("--retry-errors-only", action="store_true")
    parser.add_argument("--schema-probe", action="store_true")
    parser.add_argument("--use-cached-raw", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db_path) if args.db_path else resolve_db_path(PROJECT_ROOT, event_id=args.event_id)
    con = sqlite3.connect(db_path)
    ensure_backfill_schema(con)
    refresh_stat_catalog_metadata(con)

    if args.retry_errors_only:
        match_ids = [
            int(row[0])
            for row in con.execute(
                """
                SELECT match_id
                FROM raw_match_source_status
                WHERE source_name = ?
                  AND status = 'error'
                ORDER BY match_id
                """,
                (args.source,),
            ).fetchall()
        ]
    elif args.match_ids.strip():
        match_ids = [int(part.strip()) for part in args.match_ids.split(",") if part.strip()]
    else:
        match_ids = list_target_match_ids(con, limit=args.match_limit)

    print("[config]")
    print(json.dumps(
        {
            "event_id": args.event_id,
            "db_path": str(db_path),
            "source": args.source,
            "match_ids": match_ids,
            "write_raw": args.write_raw,
            "write_stage": args.write_stage,
            "supported_stats": OPENDOTA_SUPPORTED_STATS if args.source == "opendota" else STRATZ_SUPPORTED_STATS,
        },
        ensure_ascii=False,
        indent=2,
    ))

    if args.source == "stratz":
        result = run_stratz_preflight(
            con,
            match_ids=match_ids,
            timeout_sec=args.timeout_sec,
            write_raw=args.write_raw,
            schema_probe=args.schema_probe,
        )
    else:
        all_batch_results = []
        total_batches = ceil(len(match_ids) / args.batch_size) if match_ids else 0
        coverage_summary = []
        for batch_index in range(total_batches):
            batch_match_ids = match_ids[batch_index * args.batch_size : (batch_index + 1) * args.batch_size]
            print(f"\n[batch {batch_index + 1}/{total_batches}] {batch_match_ids[0]}..{batch_match_ids[-1]} ({len(batch_match_ids)} matches)")
            batch_result = fetch_many_opendota_matches(
                con,
                match_ids=batch_match_ids,
                write_raw=args.write_raw,
                write_stage=args.write_stage,
                sleep_sec=args.sleep_sec,
                timeout_sec=args.timeout_sec,
                overwrite_stage=True,
                skip_existing_raw=args.skip_existing_raw,
                use_cached_raw=args.use_cached_raw,
            )
            all_batch_results.append(batch_result)
            coverage_summary = batch_result.get("coverage_summary", coverage_summary)

        result = {
            "processed_matches": sum(item["processed_matches"] for item in all_batch_results),
            "stage_rows_total": sum(item["stage_rows_total"] for item in all_batch_results),
            "fetch_errors": [error for item in all_batch_results for error in item["fetch_errors"]],
            "detected_fields": {
                stat_name: sorted(
                    {
                        field
                        for item in all_batch_results
                        for field in item["detected_fields"].get(stat_name, [])
                    }
                )
                for stat_name in OPENDOTA_SUPPORTED_STATS
            },
            "coverage_summary": coverage_summary,
            "batches": total_batches,
        }

    print("\n[result]")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    con.close()


if __name__ == "__main__":
    main()
