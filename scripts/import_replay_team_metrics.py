from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from enrichment.replay_backfill import import_replay_metric_csvs, summarize_replay_metric_import


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import replay-derived team metric CSVs into SQLite staging tables.")
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--events-csv", required=True)
    parser.add_argument("--final-long-csv", required=True)
    parser.add_argument("--source-name", default="source2_demo")
    parser.add_argument("--append", action="store_true", help="Do not delete existing rows for the same match.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    con = sqlite3.connect(args.db_path)
    result = import_replay_metric_csvs(
        con,
        events_csv_path=Path(args.events_csv),
        final_long_csv_path=Path(args.final_long_csv),
        source_name=args.source_name,
        replace_match=not args.append,
    )
    summary = summarize_replay_metric_import(con, source_name=args.source_name)
    con.close()
    print(
        json.dumps(
            {
                "import_result": result,
                "summary": [
                    {
                        "stat_name": row[0],
                        "row_count": row[1],
                        "nonzero_rows": row[2],
                        "min_raw_value": row[3],
                        "max_raw_value": row[4],
                    }
                    for row in summary
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
