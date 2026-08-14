from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from tournament_config import resolve_event_db_path  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare imported official TI 2026 fantasy snapshots against local SQLite outputs.")
    parser.add_argument("--db-path", default="")
    parser.add_argument("--snapshot-label", default="")
    return parser.parse_args()


def ensure_table_exists(con: sqlite3.Connection) -> None:
    exists = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ti2026_official_fantasy_snapshots'"
    ).fetchone()
    if not exists:
        raise RuntimeError("Table ti2026_official_fantasy_snapshots does not exist yet. Import a snapshot first.")


def main() -> None:
    args = parse_args()
    db_path = Path(args.db_path) if args.db_path else resolve_event_db_path("ti2026")
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        ensure_table_exists(con)
        if args.snapshot_label:
            snapshot_label = args.snapshot_label
        else:
            row = con.execute(
                "SELECT snapshot_label FROM ti2026_official_fantasy_snapshots ORDER BY imported_at_utc DESC LIMIT 1"
            ).fetchone()
            if not row:
                raise RuntimeError("No official TI 2026 fantasy snapshots found.")
            snapshot_label = str(row["snapshot_label"])

        rows = [dict(row) for row in con.execute(
            """
            WITH official AS (
                SELECT snapshot_label, role_slot, official_name, team_name, official_position, official_score
                FROM ti2026_official_fantasy_snapshots
                WHERE snapshot_label = ?
            ),
            local_player AS (
                SELECT
                    official_name,
                    team_name,
                    official_position,
                    best_score AS local_best_map_score,
                    avg_score AS local_avg_map_score
                FROM fantasy_pick_value
                WHERE profile_id = 'example_constructor_same_as_current'
            )
            SELECT
                o.snapshot_label,
                o.role_slot,
                o.official_name,
                o.team_name,
                o.official_position,
                o.official_score,
                lp.local_best_map_score,
                lp.local_avg_map_score,
                ROUND(lp.local_best_map_score - o.official_score, 2) AS delta_best_minus_official,
                ROUND(lp.local_avg_map_score - o.official_score, 2) AS delta_avg_minus_official
            FROM official o
            LEFT JOIN local_player lp
              ON lp.official_name = o.official_name
             AND lp.team_name = o.team_name
            ORDER BY o.role_slot, o.official_score DESC, o.team_name, o.official_name
            """,
            [snapshot_label],
        ).fetchall()]
    finally:
        con.close()
    print(json.dumps({"db_path": str(db_path), "snapshot_label": snapshot_label, "rows": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
