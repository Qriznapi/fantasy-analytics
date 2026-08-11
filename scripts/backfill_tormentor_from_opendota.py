from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fantasy_profile_constructor import recalculate_profile_scores


STAT_NAME = "tormentor_kills"
OBJECTIVE_TYPE = "CHAT_MESSAGE_MINIBOSS_KILL"
EVENT_SOURCE_NAME = "opendota_objectives"
STAGE_SOURCE_NAME = "opendota"
BASE_POINTS_PER_TORMENTOR = 879.0
ROLE_SHARES = {
    1: 0.4,
    2: 0.2,
    3: 0.2,
    4: 0.1,
    5: 0.1,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill Tormentor kills from cached OpenDota objectives and distribute team kills by role shares."
    )
    parser.add_argument("--db-path", required=True, help="Target SQLite database to update.")
    parser.add_argument(
        "--payload-db-path",
        default="",
        help="Optional SQLite database containing raw_match_source_payloads. Defaults to --db-path.",
    )
    parser.add_argument(
        "--run-id",
        default="opendota_tormentor_role_share_v1_2026_08_11",
        help="Audit run identifier.",
    )
    return parser.parse_args()


def ensure_support_schema(connection: sqlite3.Connection) -> None:
    cur = connection.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS stg_player_match_enriched_stats (
            source_name TEXT NOT NULL,
            match_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            team_name TEXT NOT NULL,
            stat_name TEXT NOT NULL,
            raw_value REAL,
            source_field_name TEXT,
            extraction_method TEXT,
            coverage_note TEXT,
            created_at_utc TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (source_name, match_id, account_id, team_name, stat_name)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS fantasy_stat_backfill_audit (
            run_id TEXT NOT NULL,
            stat_name TEXT NOT NULL,
            source_name TEXT NOT NULL,
            rows_written INTEGER NOT NULL,
            nonzero_rows INTEGER NOT NULL,
            created_at_utc TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tormentor_objective_events (
            source_name TEXT NOT NULL,
            match_id INTEGER NOT NULL,
            objective_index INTEGER NOT NULL,
            objective_time_sec INTEGER,
            objective_type TEXT NOT NULL,
            objective_team_code INTEGER,
            team_side TEXT NOT NULL,
            team_name TEXT,
            shard_player_slot INTEGER,
            shard_account_id INTEGER,
            objective_payload_json TEXT NOT NULL,
            extracted_at_utc TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (source_name, match_id, objective_index)
        )
        """
    )
    connection.commit()


def recreate_views(connection: sqlite3.Connection) -> None:
    cur = connection.cursor()
    cur.execute("DROP VIEW IF EXISTS analytics_tormentor_objectives")
    cur.execute("DROP VIEW IF EXISTS analytics_tormentor_player_shares")
    cur.execute(
        """
        CREATE VIEW analytics_tormentor_objectives AS
        SELECT
            source_name,
            match_id,
            objective_index,
            objective_time_sec,
            objective_type,
            objective_team_code,
            team_side,
            team_name,
            shard_player_slot,
            shard_account_id,
            extracted_at_utc
        FROM tormentor_objective_events
        """
    )
    cur.execute(
        """
        CREATE VIEW analytics_tormentor_player_shares AS
        SELECT
            s.match_id,
            m.match_date,
            m.stage_name,
            m.stage_bucket,
            s.team_name,
            pir.official_name,
            pir.official_position,
            pir.role_group,
            s.account_id,
            s.raw_value AS tormentor_kills_share,
            ROUND(s.raw_value * 879.0, 2) AS tormentor_points_share,
            s.source_field_name,
            s.extraction_method,
            s.coverage_note
        FROM stg_player_match_enriched_stats s
        JOIN player_identity_registry pir
          ON pir.account_id = s.account_id
         AND pir.team_name = s.team_name
        JOIN matches m
          ON m.match_id = s.match_id
        WHERE s.source_name = 'opendota'
          AND s.stat_name = 'tormentor_kills'
        """
    )
    connection.commit()


def table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {
        str(row[1])
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


def _team_side_from_code(team_code: Any, player_slot: Any) -> str:
    if team_code == 2:
        return "radiant"
    if team_code == 3:
        return "dire"
    if isinstance(player_slot, int):
        return "radiant" if player_slot < 128 else "dire"
    return "unknown"


def load_tormentor_events(payload_connection: sqlite3.Connection) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    cur = payload_connection.cursor()
    for match_id, payload_json in cur.execute(
        """
        SELECT match_id, payload_json
        FROM raw_match_source_payloads
        WHERE source_name = 'opendota'
        ORDER BY match_id
        """
    ):
        payload = json.loads(payload_json)
        players_by_slot = {
            player.get("player_slot"): player
            for player in payload.get("players", [])
            if isinstance(player.get("player_slot"), int)
        }
        for objective_index, objective in enumerate(payload.get("objectives") or []):
            if objective.get("type") != OBJECTIVE_TYPE:
                continue
            player_slot = objective.get("player_slot")
            team_side = _team_side_from_code(objective.get("team"), player_slot)
            team_name = None
            if team_side == "radiant":
                team_name = payload.get("radiant_name")
            elif team_side == "dire":
                team_name = payload.get("dire_name")
            player_payload = players_by_slot.get(player_slot, {})
            events.append(
                {
                    "source_name": EVENT_SOURCE_NAME,
                    "match_id": int(match_id),
                    "objective_index": int(objective_index),
                    "objective_time_sec": int(objective.get("time")) if objective.get("time") is not None else None,
                    "objective_type": OBJECTIVE_TYPE,
                    "objective_team_code": int(objective.get("team")) if objective.get("team") is not None else None,
                    "team_side": team_side,
                    "team_name": team_name,
                    "shard_player_slot": int(player_slot) if isinstance(player_slot, int) else None,
                    "shard_account_id": player_payload.get("account_id"),
                    "objective_payload_json": json.dumps(objective, ensure_ascii=False, sort_keys=True),
                }
            )
    return events


def load_match_team_names(connection: sqlite3.Connection) -> dict[tuple[int, str], str]:
    mapping: dict[tuple[int, str], str] = {}
    for match_id, radiant_name, dire_name in connection.execute(
        "SELECT match_id, radiant_name, dire_name FROM matches ORDER BY match_id"
    ):
        mapping[(int(match_id), "radiant")] = (radiant_name or "").strip()
        mapping[(int(match_id), "dire")] = (dire_name or "").strip()
    return mapping


def load_player_rows(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    cur = connection.cursor()
    rows = []
    for match_id, team_name, account_id, official_position in cur.execute(
        """
        SELECT
            f.match_id,
            f.team_name,
            f.account_id,
            pir.official_position
        FROM player_game_fantasy_summary f
        JOIN player_identity_registry pir
          ON pir.account_id = f.account_id
         AND pir.team_name = f.team_name
        ORDER BY f.match_id, f.team_name, pir.official_position, f.account_id
        """
    ):
        rows.append(
            {
                "match_id": int(match_id),
                "team_name": str(team_name).strip(),
                "account_id": int(account_id),
                "official_position": int(official_position),
            }
        )
    return rows


def build_stage_rows(
    *,
    player_rows: list[dict[str, Any]],
    events: list[dict[str, Any]],
    match_team_names: dict[tuple[int, str], str],
) -> tuple[list[tuple[Any, ...]], Counter[str], list[str]]:
    share_by_player: defaultdict[tuple[int, int, str], float] = defaultdict(float)
    team_position_map: defaultdict[tuple[int, str], dict[int, int]] = defaultdict(dict)

    for row in player_rows:
        team_position_map[(row["match_id"], row["team_name"])][row["official_position"]] = row["account_id"]

    warnings: list[str] = []
    for event in events:
        match_id = event["match_id"]
        team_side = event["team_side"]
        team_name = match_team_names.get((match_id, team_side)) or (event["team_name"] or "").strip()
        if not team_name:
            warnings.append(f"match {match_id}: could not resolve team_name for side={team_side}")
            continue
        positions = team_position_map.get((match_id, team_name), {})
        missing_positions = [pos for pos in ROLE_SHARES if pos not in positions]
        if missing_positions:
            warnings.append(
                f"match {match_id} team {team_name}: missing positions {missing_positions} for tormentor share"
            )
            continue
        for position, share in ROLE_SHARES.items():
            account_id = positions[position]
            share_by_player[(match_id, account_id, team_name)] += share

    rows_written = []
    nonzero_counter: Counter[str] = Counter()
    for row in player_rows:
        key = (row["match_id"], row["account_id"], row["team_name"])
        raw_value = round(share_by_player.get(key, 0.0), 6)
        if raw_value > 0:
            nonzero_counter["nonzero_rows"] += 1
        rows_written.append(
            (
                STAGE_SOURCE_NAME,
                row["match_id"],
                row["account_id"],
                row["team_name"],
                STAT_NAME,
                raw_value,
                "objectives.CHAT_MESSAGE_MINIBOSS_KILL",
                "objective_team_role_share_v1",
                "approx_team_tormentor_share_by_roles_0.4_0.2_0.2_0.1_0.1",
            )
        )
    return rows_written, nonzero_counter, warnings


def apply_updates(
    connection: sqlite3.Connection,
    *,
    events: list[dict[str, Any]],
    stage_rows: list[tuple[Any, ...]],
    run_id: str,
) -> dict[str, Any]:
    cur = connection.cursor()
    ensure_support_schema(connection)

    cur.execute("DELETE FROM tormentor_objective_events WHERE source_name = ?", (EVENT_SOURCE_NAME,))
    cur.executemany(
        """
        INSERT OR REPLACE INTO tormentor_objective_events(
            source_name, match_id, objective_index, objective_time_sec, objective_type,
            objective_team_code, team_side, team_name, shard_player_slot, shard_account_id, objective_payload_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                event["source_name"],
                event["match_id"],
                event["objective_index"],
                event["objective_time_sec"],
                event["objective_type"],
                event["objective_team_code"],
                event["team_side"],
                event["team_name"],
                event["shard_player_slot"],
                event["shard_account_id"],
                event["objective_payload_json"],
            )
            for event in events
        ],
    )

    cur.execute(
        """
        DELETE FROM stg_player_match_enriched_stats
        WHERE source_name = ? AND stat_name = ?
        """,
        (STAGE_SOURCE_NAME, STAT_NAME),
    )
    cur.executemany(
        """
        INSERT OR REPLACE INTO stg_player_match_enriched_stats(
            source_name, match_id, account_id, team_name, stat_name, raw_value,
            source_field_name, extraction_method, coverage_note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        stage_rows,
    )

    cur.execute("DELETE FROM fantasy_player_map_stat_points WHERE stat_name = ?", (STAT_NAME,))
    cur.executemany(
        """
        INSERT OR REPLACE INTO fantasy_player_map_stat_points(
            match_id, account_id, team_name, stat_name, raw_value,
            base_points, base_points_column, source_table
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                match_id,
                account_id,
                team_name,
                STAT_NAME,
                raw_value,
                round(raw_value * BASE_POINTS_PER_TORMENTOR, 6),
                "tormentor_points",
                "stg_player_match_enriched_stats",
            )
            for _, match_id, account_id, team_name, _, raw_value, *_ in stage_rows
        ],
    )

    cur.execute("UPDATE player_game_fantasy_summary SET tormentor_kills = 0, tormentor_points = 0")
    cur.executemany(
        """
        UPDATE player_game_fantasy_summary
        SET tormentor_kills = ?, tormentor_points = ?
        WHERE match_id = ? AND account_id = ? AND team_name = ?
        """,
        [
            (
                raw_value,
                round(raw_value * BASE_POINTS_PER_TORMENTOR, 6),
                match_id,
                account_id,
                team_name,
            )
            for _, match_id, account_id, team_name, _, raw_value, *_ in stage_rows
        ],
    )

    catalog_columns = table_columns(connection, "fantasy_scoring_stat_catalog")
    if catalog_columns:
        assignments = []
        params: list[Any] = []
        optional_updates = {
            "preferred_source": "opendota",
            "fallback_source": "team_objective_role_share",
            "source_field_name": "objectives.CHAT_MESSAGE_MINIBOSS_KILL",
            "coverage_status": "filled_approximation",
        }
        for column_name, value in optional_updates.items():
            if column_name in catalog_columns:
                assignments.append(f"{column_name} = ?")
                params.append(value)
        if assignments:
            params.append(STAT_NAME)
            cur.execute(
                f"""
                UPDATE fantasy_scoring_stat_catalog
                SET {", ".join(assignments)}
                WHERE stat_name = ?
                """,
                params,
            )

    cur.execute("DELETE FROM fantasy_stat_backfill_audit WHERE run_id = ? AND stat_name = ?", (run_id, STAT_NAME))
    cur.execute(
        """
        INSERT INTO fantasy_stat_backfill_audit(run_id, stat_name, source_name, rows_written, nonzero_rows)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            run_id,
            STAT_NAME,
            STAGE_SOURCE_NAME,
            len(stage_rows),
            sum(1 for row in stage_rows if float(row[5]) > 0),
        ),
    )

    profile_ids = [
        row[0]
        for row in cur.execute(
            "SELECT profile_id FROM fantasy_scoring_profiles ORDER BY is_default DESC, profile_id"
        ).fetchall()
    ]
    for profile_id in profile_ids:
        recalculate_profile_scores(connection, profile_id)

    recreate_views(connection)
    connection.commit()

    total_share = round(sum(float(row[5]) for row in stage_rows), 6)
    total_points = round(total_share * BASE_POINTS_PER_TORMENTOR, 6)
    return {
        "events_written": len(events),
        "stage_rows_written": len(stage_rows),
        "nonzero_stage_rows": sum(1 for row in stage_rows if float(row[5]) > 0),
        "total_share_sum": total_share,
        "total_tormentor_base_points": total_points,
        "profiles_rebuilt": profile_ids,
    }


def main() -> None:
    args = parse_args()
    target_db_path = Path(args.db_path).resolve()
    payload_db_path = Path(args.payload_db_path).resolve() if args.payload_db_path else target_db_path

    target_connection = sqlite3.connect(target_db_path)
    payload_connection = sqlite3.connect(payload_db_path)
    try:
        ensure_support_schema(target_connection)
        events = load_tormentor_events(payload_connection)
        player_rows = load_player_rows(target_connection)
        match_team_names = load_match_team_names(target_connection)
        stage_rows, counters, warnings = build_stage_rows(
            player_rows=player_rows,
            events=events,
            match_team_names=match_team_names,
        )
        result = apply_updates(
            target_connection,
            events=events,
            stage_rows=stage_rows,
            run_id=args.run_id,
        )
    finally:
        payload_connection.close()
        target_connection.close()

    print(
        json.dumps(
            {
                "target_db_path": str(target_db_path),
                "payload_db_path": str(payload_db_path),
                "result": result,
                "warnings_count": len(warnings),
                "warnings_sample": warnings[:10],
                "nonzero_stage_rows": counters.get("nonzero_rows", 0),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
