from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from enrichment.stat_source_map import STAT_POINT_FORMULAS  # noqa: E402
from project_db import canonical_db_path, resolve_db_path  # noqa: E402


DEFAULT_DB_PATH = canonical_db_path(PROJECT_ROOT)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a unified fantasy metric table that merges player-level and replay-derived sources."
    )
    parser.add_argument("--db-path", default="", help="Path to the compact SQLite database.")
    return parser.parse_args()


def _scaled_coefficients(connection: sqlite3.Connection) -> dict[str, float]:
    return {
        "watchers_taken": float(STAT_POINT_FORMULAS["watchers_taken"]),
        "lotus": float(STAT_POINT_FORMULAS["lotus"]),
        "tormentor_kills": float(STAT_POINT_FORMULAS["tormentor_kills"]),
    }


def ensure_schema(connection: sqlite3.Connection) -> None:
    cur = connection.cursor()
    cur.execute("DROP VIEW IF EXISTS analytics_fantasy_metric_unified_summary")
    cur.execute("DROP TABLE IF EXISTS fantasy_metric_unified")
    cur.execute(
        """
        CREATE TABLE fantasy_metric_unified (
            match_id INTEGER NOT NULL,
            team_name TEXT NOT NULL,
            side TEXT,
            account_id INTEGER,
            player_name TEXT,
            team_slot INTEGER,
            role_bucket TEXT,
            stat_name TEXT NOT NULL,
            raw_value REAL NOT NULL,
            base_points REAL NOT NULL,
            preferred_source TEXT NOT NULL,
            source_table TEXT NOT NULL,
            source_entity_level TEXT NOT NULL,
            resolution_status TEXT NOT NULL,
            coverage_status TEXT NOT NULL,
            note TEXT,
            created_at_utc TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX idx_fantasy_metric_unified_lookup
        ON fantasy_metric_unified(match_id, team_name, stat_name, source_entity_level, resolution_status)
        """
    )
    cur.execute(
        """
        CREATE VIEW analytics_fantasy_metric_unified_summary AS
        SELECT
            stat_name,
            source_entity_level,
            resolution_status,
            coverage_status,
            preferred_source,
            COUNT(*) AS rows_total,
            SUM(CASE WHEN raw_value <> 0 THEN 1 ELSE 0 END) AS nonzero_raw_rows,
            SUM(CASE WHEN base_points <> 0 THEN 1 ELSE 0 END) AS nonzero_point_rows,
            ROUND(AVG(raw_value), 4) AS avg_raw_value,
            ROUND(MAX(raw_value), 4) AS max_raw_value,
            ROUND(AVG(base_points), 4) AS avg_base_points,
            ROUND(MAX(base_points), 4) AS max_base_points
        FROM fantasy_metric_unified
        GROUP BY stat_name, source_entity_level, resolution_status, coverage_status, preferred_source
        ORDER BY stat_name, source_entity_level, resolution_status
        """
    )


def populate_unified_table(connection: sqlite3.Connection) -> dict[str, int]:
    coeffs = _scaled_coefficients(connection)
    cur = connection.cursor()

    inserted_player = cur.execute(
        """
        INSERT INTO fantasy_metric_unified (
            match_id, team_name, side, account_id, player_name, team_slot, role_bucket,
            stat_name, raw_value, base_points, preferred_source, source_table,
            source_entity_level, resolution_status, coverage_status, note
        )
        SELECT
            sp.match_id,
            sp.team_name,
            pg.side,
            sp.account_id,
            pg.player_name,
            NULL AS team_slot,
            pg.role_bucket,
            sp.stat_name,
            COALESCE(sp.raw_value, 0) AS raw_value,
            COALESCE(sp.base_points, 0) AS base_points,
            COALESCE(cov.preferred_source, cat.preferred_source, 'existing') AS preferred_source,
            'fantasy_player_map_stat_points' AS source_table,
            'player' AS source_entity_level,
            CASE
                WHEN sp.stat_name = 'tormentor_kills' THEN 'player_approximated'
                ELSE 'player_resolved'
            END AS resolution_status,
            COALESCE(cov.coverage_status, cat.coverage_status, 'filled_existing') AS coverage_status,
            CASE
                WHEN sp.stat_name = 'tormentor_kills' THEN 'Player-level approximation from OpenDota objective-share pipeline.'
                ELSE 'Player-level stat points row.'
            END AS note
        FROM fantasy_player_map_stat_points sp
        LEFT JOIN player_game_fantasy_summary pg
          ON pg.match_id = sp.match_id
         AND pg.account_id = sp.account_id
         AND pg.team_name = sp.team_name
        LEFT JOIN fantasy_scoring_stat_catalog cat
          ON cat.stat_name = sp.stat_name
        LEFT JOIN analytics_fantasy_backfill_coverage cov
          ON cov.stat_name = sp.stat_name
        """
    ).rowcount

    inserted_replay = cur.execute(
        """
        INSERT INTO fantasy_metric_unified (
            match_id, team_name, side, account_id, player_name, team_slot, role_bucket,
            stat_name, raw_value, base_points, preferred_source, source_table,
            source_entity_level, resolution_status, coverage_status, note
        )
        SELECT
            rf.match_id,
            CASE
                WHEN rf.team_side = 'radiant' THEN m.radiant_name
                WHEN rf.team_side = 'dire' THEN m.dire_name
                ELSE NULL
            END AS team_name,
            rf.team_side AS side,
            rf.account_id,
            pg.player_name,
            rf.team_slot,
            pg.role_bucket,
            CASE
                WHEN rf.stat_name = 'lotuses_taken' THEN 'lotus'
                ELSE rf.stat_name
            END AS stat_name,
            rf.raw_value,
            ROUND(
                rf.raw_value *
                CASE
                    WHEN rf.stat_name = 'watchers_taken' THEN ?
                    WHEN rf.stat_name = 'lotuses_taken' THEN ?
                    WHEN rf.stat_name = 'tormentor_kills' THEN ?
                    ELSE 0
                END,
                6
            ) AS base_points,
            'source2_demo' AS preferred_source,
            'replay_team_metric_final' AS source_table,
            'replay_slot' AS source_entity_level,
            CASE
                WHEN rf.account_id IS NOT NULL THEN 'team_slot_resolved'
                ELSE 'team_slot_unresolved'
            END AS resolution_status,
            CASE
                WHEN rf.stat_name = 'tormentor_kills' THEN 'filled_approximation'
                ELSE 'source2_replay_available'
            END AS coverage_status,
            CASE
                WHEN rf.account_id IS NOT NULL THEN 'Replay-derived slot metric resolved to account_id via OpenDota player_slot match.'
                ELSE 'Replay-derived slot metric; available in game counters but not yet resolved to account_id.'
            END AS note
        FROM replay_team_metric_final rf
        JOIN matches m
          ON m.match_id = rf.match_id
        LEFT JOIN player_game_fantasy_summary pg
          ON pg.match_id = rf.match_id
         AND pg.account_id = rf.account_id
         AND pg.team_name = CASE
                WHEN rf.team_side = 'radiant' THEN m.radiant_name
                WHEN rf.team_side = 'dire' THEN m.dire_name
                ELSE NULL
            END
        WHERE rf.source_name = 'source2_demo'
          AND rf.stat_name IN ('watchers_taken', 'lotuses_taken', 'tormentor_kills')
          AND COALESCE(rf.raw_value, 0) <> 0
        """,
        (coeffs["watchers_taken"], coeffs["lotus"], coeffs["tormentor_kills"]),
    ).rowcount

    connection.commit()
    return {
        "inserted_player_rows": int(inserted_player or 0),
        "inserted_replay_rows": int(inserted_replay or 0),
    }


def summarize(connection: sqlite3.Connection) -> dict[str, object]:
    cur = connection.cursor()
    rows = cur.execute(
        """
        SELECT
            stat_name,
            source_entity_level,
            resolution_status,
            nonzero_raw_rows,
            max_raw_value
        FROM analytics_fantasy_metric_unified_summary
        WHERE stat_name IN ('watchers_taken', 'lotus', 'tormentor_kills', 'creep_score', 'gpm')
        ORDER BY stat_name, source_entity_level, resolution_status
        """
    ).fetchall()
    return {
        "summary_rows": [
            {
                "stat_name": row[0],
                "source_entity_level": row[1],
                "resolution_status": row[2],
                "nonzero_raw_rows": row[3],
                "max_raw_value": row[4],
            }
            for row in rows
        ]
    }


def main() -> None:
    args = parse_args()
    db_path = resolve_db_path(PROJECT_ROOT, args.db_path or None).resolve()
    connection = sqlite3.connect(str(db_path))
    try:
        ensure_schema(connection)
        insert_counts = populate_unified_table(connection)
        summary = summarize(connection)
    finally:
        connection.close()

    print(
        json.dumps(
            {
                "db_path": str(db_path),
                **insert_counts,
                **summary,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
