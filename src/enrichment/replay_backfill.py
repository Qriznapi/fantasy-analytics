from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Any


def ensure_replay_backfill_schema(con: sqlite3.Connection) -> None:
    cur = con.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS replay_team_metric_events (
            source_name TEXT NOT NULL,
            match_id INTEGER NOT NULL,
            tick INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            team_side TEXT NOT NULL,
            entity_handle INTEGER NOT NULL,
            team_slot INTEGER NOT NULL,
            stat_name TEXT NOT NULL,
            raw_value REAL NOT NULL,
            imported_at_utc TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (source_name, match_id, tick, team_side, team_slot, stat_name)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS replay_team_metric_final (
            source_name TEXT NOT NULL,
            match_id INTEGER NOT NULL,
            team_side TEXT NOT NULL,
            team_slot INTEGER NOT NULL,
            stat_name TEXT NOT NULL,
            raw_value REAL NOT NULL,
            last_tick INTEGER NOT NULL,
            account_id INTEGER,
            imported_at_utc TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (source_name, match_id, team_side, team_slot, stat_name)
        )
        """
    )
    con.commit()


def ensure_replay_backfill_views(con: sqlite3.Connection) -> None:
    cur = con.cursor()
    for view_name in [
        "analytics_replay_team_metrics_long",
        "analytics_replay_team_metrics_wide",
        "analytics_replay_match_coverage",
        "analytics_replay_metric_summary",
    ]:
        cur.execute(f"DROP VIEW IF EXISTS {view_name}")

    cur.execute(
        """
        CREATE VIEW analytics_replay_team_metrics_long AS
        SELECT
            source_name,
            match_id,
            team_side,
            team_slot,
            stat_name,
            raw_value,
            last_tick,
            account_id,
            imported_at_utc
        FROM replay_team_metric_final
        """
    )
    cur.execute(
        """
        CREATE VIEW analytics_replay_team_metrics_wide AS
        SELECT
            source_name,
            match_id,
            team_side,
            team_slot,
            MAX(CASE WHEN stat_name = 'watchers_taken' THEN raw_value END) AS watchers_taken,
            MAX(CASE WHEN stat_name = 'lotuses_taken' THEN raw_value END) AS lotuses_taken,
            MAX(CASE WHEN stat_name = 'tormentor_kills' THEN raw_value END) AS tormentor_kills,
            MAX(CASE WHEN stat_name = 'acquired_madstone' THEN raw_value END) AS acquired_madstone,
            MAX(CASE WHEN stat_name = 'current_madstone' THEN raw_value END) AS current_madstone,
            MAX(last_tick) AS last_tick,
            MAX(imported_at_utc) AS imported_at_utc
        FROM replay_team_metric_final
        GROUP BY source_name, match_id, team_side, team_slot
        """
    )
    cur.execute(
        """
        CREATE VIEW analytics_replay_match_coverage AS
        SELECT
            source_name,
            match_id,
            COUNT(*) AS stat_rows,
            COUNT(DISTINCT team_side || ':' || team_slot) AS team_slot_rows,
            SUM(CASE WHEN raw_value <> 0 THEN 1 ELSE 0 END) AS nonzero_rows,
            MAX(last_tick) AS last_tick
        FROM replay_team_metric_final
        GROUP BY source_name, match_id
        """
    )
    cur.execute(
        """
        CREATE VIEW analytics_replay_metric_summary AS
        SELECT
            source_name,
            stat_name,
            COUNT(*) AS row_count,
            SUM(CASE WHEN raw_value <> 0 THEN 1 ELSE 0 END) AS nonzero_rows,
            MIN(raw_value) AS min_raw_value,
            MAX(raw_value) AS max_raw_value,
            COUNT(DISTINCT match_id) AS distinct_matches
        FROM replay_team_metric_final
        GROUP BY source_name, stat_name
        """
    )
    con.commit()


def _load_csv_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def import_replay_metric_csvs(
    con: sqlite3.Connection,
    *,
    events_csv_path: Path,
    final_long_csv_path: Path,
    source_name: str = "source2_demo",
    replace_match: bool = True,
) -> dict[str, int]:
    ensure_replay_backfill_schema(con)
    events_rows = _load_csv_rows(events_csv_path)
    final_rows = _load_csv_rows(final_long_csv_path)

    if replace_match:
        match_ids = sorted(
            {
                int(row["match_id"])
                for row in [*events_rows, *final_rows]
                if row.get("match_id")
            }
        )
        for match_id in match_ids:
            con.execute(
                "DELETE FROM replay_team_metric_events WHERE source_name = ? AND match_id = ?",
                (source_name, match_id),
            )
            con.execute(
                "DELETE FROM replay_team_metric_final WHERE source_name = ? AND match_id = ?",
                (source_name, match_id),
            )

    con.executemany(
        """
        INSERT OR REPLACE INTO replay_team_metric_events(
            source_name, match_id, tick, event_type, team_side, entity_handle, team_slot, stat_name, raw_value
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                source_name,
                int(row["match_id"]),
                int(row["tick"]),
                str(row["event_type"]),
                str(row["team_side"]),
                int(row["entity_handle"]),
                int(row["team_slot"]),
                str(row["metric_name"]),
                float(row["metric_value"]),
            )
            for row in events_rows
        ],
    )

    con.executemany(
        """
        INSERT OR REPLACE INTO replay_team_metric_final(
            source_name, match_id, team_side, team_slot, stat_name, raw_value, last_tick
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                source_name,
                int(row["match_id"]),
                str(row["team_side"]),
                int(row["team_slot"]),
                str(row["stat_name"]),
                float(row["raw_value"]),
                int(row["last_tick"]),
            )
            for row in final_rows
        ],
    )
    con.commit()
    ensure_replay_backfill_views(con)
    return {
        "events_rows": len(events_rows),
        "final_rows": len(final_rows),
    }


def summarize_replay_metric_import(con: sqlite3.Connection, *, source_name: str = "source2_demo") -> list[tuple[Any, ...]]:
    return con.execute(
        """
        SELECT
            stat_name,
            COUNT(*) AS row_count,
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
