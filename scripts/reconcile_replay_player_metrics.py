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


SUPPORTED_REPLAY_STATS = {
    "watchers_taken": {
        "normalized_stat_name": "watchers_taken",
        "points_column": "watchers_taken_points",
        "point_factor": float(STAT_POINT_FORMULAS["watchers_taken"]),
    },
    "lotuses_taken": {
        "normalized_stat_name": "lotus",
        "points_column": "lotus_points",
        "point_factor": float(STAT_POINT_FORMULAS["lotus"]),
    },
    "tormentor_kills": {
        "normalized_stat_name": "tormentor_kills",
        "points_column": "tormentor_points",
        "point_factor": float(STAT_POINT_FORMULAS["tormentor_kills"]),
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve replay-derived team-slot metrics to player account_ids via "
            "OpenDota player_slot, persist a canonical replay_player_metric_resolved layer, "
            "and sync watchers/lotus into the final fantasy stat tables."
        )
    )
    parser.add_argument("--db-path", default="", help="Path to the compact SQLite database.")
    return parser.parse_args()


def ensure_schema(connection: sqlite3.Connection) -> None:
    cur = connection.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS replay_player_metric_resolved (
            source_name TEXT NOT NULL,
            match_id INTEGER NOT NULL,
            team_side TEXT NOT NULL,
            team_name TEXT NOT NULL,
            team_slot INTEGER NOT NULL,
            player_slot INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            db_player_name TEXT,
            official_name TEXT,
            official_position INTEGER,
            role_group TEXT,
            source_stat_name TEXT NOT NULL,
            normalized_stat_name TEXT NOT NULL,
            raw_value REAL NOT NULL,
            base_points REAL NOT NULL,
            scoring_points_column TEXT NOT NULL,
            resolution_method TEXT NOT NULL,
            confidence_label TEXT NOT NULL,
            imported_at_utc TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (source_name, match_id, team_side, team_slot, normalized_stat_name)
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_replay_player_metric_resolved_lookup
        ON replay_player_metric_resolved(match_id, account_id, normalized_stat_name)
        """
    )
    for view_name in [
        "analytics_replay_player_metrics_long",
        "analytics_replay_player_metrics_wide",
        "analytics_replay_player_metric_summary",
    ]:
        cur.execute(f"DROP VIEW IF EXISTS {view_name}")
    cur.execute(
        """
        CREATE VIEW analytics_replay_player_metrics_long AS
        SELECT
            source_name,
            match_id,
            team_side,
            team_name,
            team_slot,
            player_slot,
            account_id,
            db_player_name,
            official_name,
            official_position,
            role_group,
            source_stat_name,
            normalized_stat_name AS stat_name,
            raw_value,
            base_points,
            scoring_points_column,
            resolution_method,
            confidence_label,
            imported_at_utc
        FROM replay_player_metric_resolved
        """
    )
    cur.execute(
        """
        CREATE VIEW analytics_replay_player_metrics_wide AS
        SELECT
            source_name,
            match_id,
            team_side,
            team_name,
            team_slot,
            player_slot,
            account_id,
            db_player_name,
            official_name,
            official_position,
            role_group,
            MAX(CASE WHEN normalized_stat_name = 'watchers_taken' THEN raw_value END) AS watchers_taken,
            MAX(CASE WHEN normalized_stat_name = 'lotus' THEN raw_value END) AS lotus,
            MAX(CASE WHEN normalized_stat_name = 'tormentor_kills' THEN raw_value END) AS tormentor_kills,
            MAX(CASE WHEN normalized_stat_name = 'watchers_taken' THEN base_points END) AS watchers_taken_points,
            MAX(CASE WHEN normalized_stat_name = 'lotus' THEN base_points END) AS lotus_points,
            MAX(CASE WHEN normalized_stat_name = 'tormentor_kills' THEN base_points END) AS tormentor_points,
            MAX(imported_at_utc) AS imported_at_utc
        FROM replay_player_metric_resolved
        GROUP BY
            source_name, match_id, team_side, team_name, team_slot, player_slot,
            account_id, db_player_name, official_name, official_position, role_group
        """
    )
    cur.execute(
        """
        CREATE VIEW analytics_replay_player_metric_summary AS
        SELECT
            stat_name,
            COUNT(*) AS rows_total,
            SUM(CASE WHEN raw_value <> 0 THEN 1 ELSE 0 END) AS nonzero_rows,
            ROUND(AVG(raw_value), 4) AS avg_raw_value,
            ROUND(MAX(raw_value), 4) AS max_raw_value,
            ROUND(AVG(base_points), 4) AS avg_base_points,
            ROUND(MAX(base_points), 4) AS max_base_points
        FROM analytics_replay_player_metrics_long
        GROUP BY stat_name
        ORDER BY stat_name
        """
    )
    connection.commit()


def _load_summary_lookup(connection: sqlite3.Connection) -> dict[tuple[int, int, str], dict[str, object]]:
    connection.row_factory = sqlite3.Row
    cur = connection.cursor()
    lookup: dict[tuple[int, int, str], dict[str, object]] = {}
    for row in cur.execute(
        """
        SELECT DISTINCT
            match_id,
            account_id,
            team_name,
            side,
            player_name,
            role_bucket
        FROM player_game_fantasy_summary
        """
    ):
        lookup[(int(row["match_id"]), int(row["account_id"]), str(row["team_name"]))] = {
            "side": row["side"],
            "player_name": row["player_name"],
            "role_bucket": row["role_bucket"],
        }
    return lookup


def _load_registry_lookup(connection: sqlite3.Connection) -> dict[tuple[int, str], dict[str, object]]:
    connection.row_factory = sqlite3.Row
    cur = connection.cursor()
    lookup: dict[tuple[int, str], dict[str, object]] = {}
    for row in cur.execute(
        """
        SELECT
            account_id,
            team_name,
            official_name,
            official_position,
            role_group
        FROM player_identity_registry
        """
    ):
        lookup[(int(row["account_id"]), str(row["team_name"]))] = {
            "official_name": row["official_name"],
            "official_position": row["official_position"],
            "role_group": row["role_group"],
        }
    return lookup


def build_slot_lookup(connection: sqlite3.Connection) -> dict[tuple[int, str, int], dict[str, object]]:
    connection.row_factory = sqlite3.Row
    cur = connection.cursor()
    match_names = {
        int(row["match_id"]): {
            "radiant": row["radiant_name"],
            "dire": row["dire_name"],
        }
        for row in cur.execute("SELECT match_id, radiant_name, dire_name FROM matches")
    }
    summary_lookup = _load_summary_lookup(connection)
    registry_lookup = _load_registry_lookup(connection)

    slot_lookup: dict[tuple[int, str, int], dict[str, object]] = {}
    for row in cur.execute(
        """
        SELECT match_id, payload_json
        FROM raw_match_source_payloads
        WHERE source_name = 'opendota'
        """
    ):
        match_id = int(row["match_id"])
        payload = json.loads(row["payload_json"])
        players = payload.get("players", [])
        names = match_names.get(match_id, {})
        for player in players:
            account_id = player.get("account_id")
            player_slot = player.get("player_slot")
            if account_id is None or not isinstance(player_slot, int):
                continue
            side = "radiant" if player_slot < 128 else "dire"
            team_slot = int(player_slot % 128)
            team_name = str(names.get(side) or "")
            summary_meta = summary_lookup.get((match_id, int(account_id), team_name), {})
            registry_meta = registry_lookup.get((int(account_id), team_name), {})
            slot_lookup[(match_id, side, team_slot)] = {
                "account_id": int(account_id),
                "player_slot": int(player_slot),
                "team_name": team_name,
                "db_player_name": summary_meta.get("player_name"),
                "official_name": registry_meta.get("official_name"),
                "official_position": registry_meta.get("official_position"),
                "role_group": registry_meta.get("role_group"),
            }
    return slot_lookup


def resolve_replay_account_ids(
    connection: sqlite3.Connection,
    slot_lookup: dict[tuple[int, str, int], dict[str, object]],
) -> dict[str, int]:
    connection.row_factory = sqlite3.Row
    cur = connection.cursor()
    rows = cur.execute(
        """
        SELECT rowid, match_id, team_side, team_slot
        FROM replay_team_metric_final
        WHERE source_name = 'source2_demo'
          AND stat_name IN ('watchers_taken', 'lotuses_taken', 'tormentor_kills')
        """
    ).fetchall()
    updates: list[tuple[int | None, int]] = []
    unresolved = 0
    for row in rows:
        meta = slot_lookup.get((int(row["match_id"]), str(row["team_side"]), int(row["team_slot"])))
        if meta is None:
            unresolved += 1
            updates.append((None, int(row["rowid"])))
            continue
        updates.append((int(meta["account_id"]), int(row["rowid"])))
    cur.executemany("UPDATE replay_team_metric_final SET account_id = ? WHERE rowid = ?", updates)
    connection.commit()
    return {
        "replay_rows_examined": len(rows),
        "replay_rows_resolved": len(rows) - unresolved,
        "replay_rows_unresolved": unresolved,
    }


def rebuild_resolved_table(
    connection: sqlite3.Connection,
    slot_lookup: dict[tuple[int, str, int], dict[str, object]],
) -> dict[str, int]:
    connection.row_factory = sqlite3.Row
    cur = connection.cursor()
    cur.execute("DELETE FROM replay_player_metric_resolved WHERE source_name = 'source2_demo'")

    rows = cur.execute(
        """
        SELECT source_name, match_id, team_side, team_slot, stat_name, raw_value, account_id
        FROM replay_team_metric_final
        WHERE source_name = 'source2_demo'
          AND stat_name IN ('watchers_taken', 'lotuses_taken', 'tormentor_kills')
        ORDER BY match_id, team_side, team_slot, stat_name
        """
    ).fetchall()

    inserts: list[tuple[object, ...]] = []
    unresolved = 0
    for row in rows:
        stat_meta = SUPPORTED_REPLAY_STATS.get(str(row["stat_name"]))
        if stat_meta is None:
            continue
        match_id = int(row["match_id"])
        team_side = str(row["team_side"])
        team_slot = int(row["team_slot"])
        slot_meta = slot_lookup.get((match_id, team_side, team_slot))
        if slot_meta is None:
            unresolved += 1
            continue
        raw_value = float(row["raw_value"] or 0.0)
        point_factor = float(stat_meta["point_factor"])
        inserts.append(
            (
                str(row["source_name"]),
                match_id,
                team_side,
                str(slot_meta["team_name"]),
                team_slot,
                int(slot_meta["player_slot"]),
                int(slot_meta["account_id"]),
                slot_meta.get("db_player_name"),
                slot_meta.get("official_name"),
                slot_meta.get("official_position"),
                slot_meta.get("role_group"),
                str(row["stat_name"]),
                str(stat_meta["normalized_stat_name"]),
                raw_value,
                round(raw_value * point_factor, 6),
                str(stat_meta["points_column"]),
                "opendota_player_slot_to_replay_team_slot_exact_match",
                "high",
            )
        )

    cur.executemany(
        """
        INSERT OR REPLACE INTO replay_player_metric_resolved (
            source_name, match_id, team_side, team_name, team_slot, player_slot,
            account_id, db_player_name, official_name, official_position, role_group,
            source_stat_name, normalized_stat_name, raw_value, base_points,
            scoring_points_column, resolution_method, confidence_label
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        inserts,
    )
    connection.commit()
    return {
        "resolved_table_rows_written": len(inserts),
        "resolved_table_rows_unresolved": unresolved,
    }


def sync_canonical_watchers_and_lotus(connection: sqlite3.Connection) -> dict[str, int]:
    cur = connection.cursor()
    cur.execute("DELETE FROM fantasy_player_map_stat_points WHERE stat_name IN ('watchers_taken', 'lotus')")
    inserted = cur.execute(
        """
        INSERT INTO fantasy_player_map_stat_points (
            match_id,
            account_id,
            team_name,
            stat_name,
            raw_value,
            base_points,
            base_points_column,
            source_table
        )
        SELECT
            match_id,
            account_id,
            team_name,
            normalized_stat_name,
            raw_value,
            base_points,
            scoring_points_column,
            'replay_player_metric_resolved'
        FROM replay_player_metric_resolved
        WHERE source_name = 'source2_demo'
          AND normalized_stat_name IN ('watchers_taken', 'lotus')
        """
    ).rowcount
    connection.commit()
    return {"canonical_rows_inserted": int(inserted or 0)}


def normalize_scoring_rules(connection: sqlite3.Connection) -> None:
    cur = connection.cursor()
    version_row = cur.execute(
        """
        SELECT formula_version
        FROM battlepass_scoring_rules
        ORDER BY formula_version DESC
        LIMIT 1
        """
    ).fetchone()
    if not version_row:
        return
    version = str(version_row[0])
    normalized = {
        "kills": 1.07,
        "deaths_base": 19.50,
        "deaths_each": -1.95,
        "creep_score": 0.03,
        "gpm": 0.02,
        "madstone": 0.13,
        "tower_kills": 3.52,
        "observer_wards": 1.17,
        "camps_stacked": 2.34,
        "runes_grabbed": 1.41,
        "watchers_taken": 1.47,
        "lotus_used": 1.76,
        "great_lotus_used": 3.52,
        "greater_lotus_used": 7.04,
        "roshan_kills": 11.72,
        "teamfight_participation_max": 21.24,
        "stuns_sec": 0.10,
        "tormentor_kills": 8.79,
        "courier_kills": 7.03,
        "first_blood": 19.34,
        "smoke_used": 2.93,
    }
    cur.executemany(
        """
        UPDATE battlepass_scoring_rules
        SET coefficient = ?
        WHERE formula_version = ?
          AND metric = ?
        """,
        [(value, version, metric) for metric, value in normalized.items()],
    )
    connection.commit()


def write_metadata(connection: sqlite3.Connection) -> None:
    cur = connection.cursor()
    cur.executemany(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
        [
            ("replay_player_metric_resolution", "completed"),
            ("replay_player_metric_resolution_method", "opendota_player_slot_to_replay_team_slot_exact_match"),
            ("replay_player_metric_resolution_utc", cur.execute("SELECT datetime('now')").fetchone()[0]),
            ("watchers_lotus_canonical_source", "replay_player_metric_resolved"),
        ],
    )
    connection.commit()


def collect_summary(connection: sqlite3.Connection) -> dict[str, object]:
    cur = connection.cursor()
    stats = {}
    for stat_name in ["watchers_taken", "lotus", "tormentor_kills"]:
        row = cur.execute(
            """
            SELECT
                COUNT(*) AS rows_total,
                SUM(CASE WHEN raw_value <> 0 THEN 1 ELSE 0 END) AS nonzero_rows,
                ROUND(MAX(raw_value), 4) AS max_raw_value,
                ROUND(MAX(base_points), 4) AS max_base_points
            FROM replay_player_metric_resolved
            WHERE normalized_stat_name = ?
            """,
            (stat_name,),
        ).fetchone()
        stats[stat_name] = {
            "rows_total": int(row[0] or 0),
            "nonzero_rows": int(row[1] or 0),
            "max_raw_value": row[2],
            "max_base_points": row[3],
        }

    canonical = {}
    for stat_name in ["watchers_taken", "lotus"]:
        row = cur.execute(
            """
            SELECT
                COUNT(*) AS rows_total,
                SUM(CASE WHEN raw_value <> 0 THEN 1 ELSE 0 END) AS nonzero_rows,
                ROUND(MAX(raw_value), 4) AS max_raw_value,
                ROUND(MAX(base_points), 4) AS max_base_points
            FROM fantasy_player_map_stat_points
            WHERE stat_name = ?
            """,
            (stat_name,),
        ).fetchone()
        canonical[stat_name] = {
            "rows_total": int(row[0] or 0),
            "nonzero_rows": int(row[1] or 0),
            "max_raw_value": row[2],
            "max_base_points": row[3],
        }
    return {
        "resolved_stats": stats,
        "canonical_stats": canonical,
    }


def main() -> None:
    args = parse_args()
    db_path = resolve_db_path(PROJECT_ROOT, args.db_path or None).resolve()
    connection = sqlite3.connect(str(db_path))
    try:
        ensure_schema(connection)
        normalize_scoring_rules(connection)
        slot_lookup = build_slot_lookup(connection)
        resolution = resolve_replay_account_ids(connection, slot_lookup)
        resolved_table = rebuild_resolved_table(connection, slot_lookup)
        canonical = sync_canonical_watchers_and_lotus(connection)
        write_metadata(connection)
        summary = collect_summary(connection)
    finally:
        connection.close()

    print(
        json.dumps(
            {
                "db_path": str(db_path),
                "slot_lookup_rows": len(slot_lookup),
                **resolution,
                **resolved_table,
                **canonical,
                **summary,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
DEFAULT_DB_PATH = canonical_db_path(PROJECT_ROOT)
