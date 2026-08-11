from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from enrichment import ensure_replay_backfill_schema, ensure_replay_backfill_views


DEFAULT_REPLAY_DB = PROJECT_ROOT / "deliverables" / "replay_team_metrics_ewc2026_probe6.sqlite"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge replay-derived team metrics into the main compact SQLite database."
    )
    parser.add_argument("--target-db", required=True, help="Path to the main compact SQLite database.")
    parser.add_argument(
        "--replay-db",
        default=str(DEFAULT_REPLAY_DB),
        help="Path to the replay-only SQLite database with replay_team_metric_* tables.",
    )
    parser.add_argument("--source-name", default="source2_demo")
    return parser.parse_args()


def merge_replay_tables(target_db: Path, replay_db: Path, source_name: str) -> dict[str, object]:
    con = sqlite3.connect(str(target_db))
    try:
        ensure_replay_backfill_schema(con)
        con.execute("ATTACH DATABASE ? AS replay_src", (str(replay_db),))

        event_match_count = con.execute(
            """
            SELECT COUNT(DISTINCT match_id)
            FROM replay_src.replay_team_metric_events
            WHERE source_name = ?
            """,
            (source_name,),
        ).fetchone()[0]
        final_match_count = con.execute(
            """
            SELECT COUNT(DISTINCT match_id)
            FROM replay_src.replay_team_metric_final
            WHERE source_name = ?
            """,
            (source_name,),
        ).fetchone()[0]

        con.execute("DELETE FROM replay_team_metric_events WHERE source_name = ?", (source_name,))
        con.execute("DELETE FROM replay_team_metric_final WHERE source_name = ?", (source_name,))

        inserted_events = con.execute(
            """
            INSERT INTO replay_team_metric_events (
                source_name, match_id, tick, event_type, team_side, entity_handle,
                team_slot, stat_name, raw_value, imported_at_utc
            )
            SELECT
                source_name, match_id, tick, event_type, team_side, entity_handle,
                team_slot, stat_name, raw_value, imported_at_utc
            FROM replay_src.replay_team_metric_events
            WHERE source_name = ?
            """,
            (source_name,),
        ).rowcount
        inserted_final = con.execute(
            """
            INSERT INTO replay_team_metric_final (
                source_name, match_id, team_side, team_slot, stat_name,
                raw_value, last_tick, account_id, imported_at_utc
            )
            SELECT
                source_name, match_id, team_side, team_slot, stat_name,
                raw_value, last_tick, account_id, imported_at_utc
            FROM replay_src.replay_team_metric_final
            WHERE source_name = ?
            """,
            (source_name,),
        ).rowcount

        ensure_replay_backfill_views(con)

        final_summary = con.execute(
            """
            SELECT stat_name, COUNT(*) AS row_count,
                   SUM(CASE WHEN raw_value <> 0 THEN 1 ELSE 0 END) AS nonzero_rows,
                   MIN(raw_value) AS min_raw_value,
                   MAX(raw_value) AS max_raw_value
            FROM replay_team_metric_final
            WHERE source_name = ?
            GROUP BY stat_name
            ORDER BY stat_name
            """,
            (source_name,),
        ).fetchall()
        con.commit()
        con.execute("DETACH DATABASE replay_src")
        return {
            "target_db": str(target_db),
            "replay_db": str(replay_db),
            "source_name": source_name,
            "event_match_count": event_match_count,
            "final_match_count": final_match_count,
            "inserted_events": inserted_events,
            "inserted_final": inserted_final,
            "summary": [
                {
                    "stat_name": row[0],
                    "row_count": row[1],
                    "nonzero_rows": row[2],
                    "min_raw_value": row[3],
                    "max_raw_value": row[4],
                }
                for row in final_summary
            ],
        }
    finally:
        con.close()


def main() -> int:
    args = parse_args()
    result = merge_replay_tables(
        target_db=Path(args.target_db),
        replay_db=Path(args.replay_db),
        source_name=args.source_name,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
