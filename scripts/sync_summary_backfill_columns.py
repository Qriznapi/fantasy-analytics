from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "ewc_2026_fantasy_compact.sqlite"

STAT_COLUMN_MAP = [
    ("wards_placed", "observer_wards_placed", "wards_points"),
    ("camps_stacked", "camps_stacked", "camps_stacked_points"),
    ("runes_grabbed", "runes_grabbed", "runes_grabbed_points"),
    ("roshan_kills", "roshan_kills", "roshan_points"),
    ("stuns", "stuns_sec", "stuns_points"),
    ("courier_kills", "courier_kills", "courier_points"),
    ("first_blood", "first_blood", "first_blood_points"),
    ("smokes_used", "smokes_used", "smokes_points"),
    ("tormentor_kills", "tormentor_kills", "tormentor_points"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync player_game_fantasy_summary raw/points columns from fantasy_player_map_stat_points."
    )
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    return parser.parse_args()


def sync_summary_columns(connection: sqlite3.Connection) -> dict[str, dict[str, int | float | None]]:
    cur = connection.cursor()
    results: dict[str, dict[str, int | float | None]] = {}

    for stat_name, raw_col, points_col in STAT_COLUMN_MAP:
        cur.execute(f"UPDATE player_game_fantasy_summary SET {raw_col} = 0, {points_col} = 0")
        cur.execute(
            f"""
            UPDATE player_game_fantasy_summary
            SET {raw_col} = (
                    SELECT COALESCE(sp.raw_value, 0)
                    FROM fantasy_player_map_stat_points sp
                    WHERE sp.match_id = player_game_fantasy_summary.match_id
                      AND sp.account_id = player_game_fantasy_summary.account_id
                      AND sp.team_name = player_game_fantasy_summary.team_name
                      AND sp.stat_name = ?
                ),
                {points_col} = (
                    SELECT COALESCE(sp.base_points, 0)
                    FROM fantasy_player_map_stat_points sp
                    WHERE sp.match_id = player_game_fantasy_summary.match_id
                      AND sp.account_id = player_game_fantasy_summary.account_id
                      AND sp.team_name = player_game_fantasy_summary.team_name
                      AND sp.stat_name = ?
                )
            WHERE EXISTS (
                SELECT 1
                FROM fantasy_player_map_stat_points sp
                WHERE sp.match_id = player_game_fantasy_summary.match_id
                  AND sp.account_id = player_game_fantasy_summary.account_id
                  AND sp.team_name = player_game_fantasy_summary.team_name
                  AND sp.stat_name = ?
            )
            """,
            (stat_name, stat_name, stat_name),
        )
        raw_nonzero, points_nonzero, max_raw, max_points = cur.execute(
            f"""
            SELECT
                SUM(CASE WHEN COALESCE({raw_col}, 0) <> 0 THEN 1 ELSE 0 END),
                SUM(CASE WHEN COALESCE({points_col}, 0) <> 0 THEN 1 ELSE 0 END),
                MAX({raw_col}),
                MAX({points_col})
            FROM player_game_fantasy_summary
            """
        ).fetchone()
        results[stat_name] = {
            "raw_nonzero_rows": int(raw_nonzero or 0),
            "points_nonzero_rows": int(points_nonzero or 0),
            "max_raw_value": max_raw,
            "max_points_value": max_points,
        }

    # Recompute legacy banner contribution columns that depend on synced backfill stats.
    cur.execute(
        """
        UPDATE player_game_fantasy_summary
        SET score_from_runes = ROUND(COALESCE(runes_grabbed_points, 0) * COALESCE(multiplier_runes_grabbed, 0), 6),
            score_from_watchers = ROUND(COALESCE(watchers_taken_points, 0) * COALESCE(multiplier_watchers_taken, 0), 6),
            score_from_lotuses = ROUND(COALESCE(lotus_points, 0) * COALESCE(multiplier_lotus, 0), 6)
        """
    )

    connection.commit()
    return results


def main() -> None:
    args = parse_args()
    db_path = Path(args.db_path).resolve()
    connection = sqlite3.connect(db_path)
    try:
        results = sync_summary_columns(connection)
    finally:
        connection.close()
    print(json.dumps({"db_path": str(db_path), "synced_stats": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
