from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .stat_source_map import STAT_POINT_FORMULAS, STAT_SOURCE_MAP


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "ewc_2026_fantasy_compact.sqlite"
OPENDOTA_BASE_URL = "https://api.opendota.com/api/matches"
TORMENTOR_OBJECTIVE_TYPE = "CHAT_MESSAGE_MINIBOSS_KILL"

OPENDOTA_SUPPORTED_STATS = [
    "first_blood",
    "stuns",
    "runes_grabbed",
    "wards_placed",
    "smokes_used",
    "camps_stacked",
    "courier_kills",
    "roshan_kills",
    "tormentor_kills",
]

BACKFILL_TRACKED_STATS = [
    "first_blood",
    "stuns",
    "runes_grabbed",
    "wards_placed",
    "smokes_used",
    "camps_stacked",
    "courier_kills",
    "roshan_kills",
    "watchers_taken",
    "lotus",
    "tormentor_kills",
]


@dataclass(slots=True)
class ExtractedStatRow:
    source_name: str
    match_id: int
    account_id: int
    team_name: str
    stat_name: str
    raw_value: float
    source_field_name: str
    extraction_method: str
    coverage_note: str


def _column_names(cur: sqlite3.Cursor, table_name: str) -> set[str]:
    return {row[1] for row in cur.execute(f"PRAGMA table_info('{table_name}')").fetchall()}


def _ensure_column(cur: sqlite3.Cursor, table_name: str, column_name: str, column_sql: str) -> None:
    if column_name not in _column_names(cur, table_name):
        cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")


def _tracked_stats_sql() -> str:
    return ", ".join(f"'{stat_name}'" for stat_name in BACKFILL_TRACKED_STATS)


def refresh_backfill_views(con: sqlite3.Connection) -> None:
    tracked_stats = _tracked_stats_sql()
    cur = con.cursor()
    cur.execute("DROP VIEW IF EXISTS analytics_fantasy_backfill_coverage")
    cur.execute(
        f"""
        CREATE VIEW analytics_fantasy_backfill_coverage AS
        WITH target_stats AS (
            SELECT stat_name, preferred_source, fallback_source, source_field_name, coverage_status
            FROM fantasy_scoring_stat_catalog
            WHERE stat_name IN ({tracked_stats})
        ),
        expected AS (
            SELECT COUNT(*) * 10 AS expected_rows
            FROM matches
        ),
        final_counts AS (
            SELECT
                stat_name,
                COUNT(*) AS final_rows,
                SUM(CASE WHEN COALESCE(raw_value, 0) = 0 THEN 1 ELSE 0 END) AS zero_raw_rows,
                SUM(CASE WHEN COALESCE(raw_value, 0) != 0 THEN 1 ELSE 0 END) AS nonzero_raw_rows,
                ROUND(MIN(COALESCE(raw_value, 0)), 6) AS min_raw_value,
                ROUND(MAX(COALESCE(raw_value, 0)), 6) AS max_raw_value
            FROM fantasy_player_map_stat_points
            WHERE stat_name IN ({tracked_stats})
            GROUP BY stat_name
        ),
        stage_counts AS (
            SELECT
                stat_name,
                SUM(CASE WHEN coverage_note LIKE 'field_present%' THEN 1 ELSE 0 END) AS field_present_rows,
                SUM(CASE WHEN coverage_note LIKE 'field_absent_zero_assumed%' THEN 1 ELSE 0 END) AS sparse_zero_rows,
                SUM(CASE WHEN coverage_note = 'field_missing_in_payload' THEN 1 ELSE 0 END) AS source_missing_rows,
                SUM(CASE WHEN coverage_note LIKE 'objective_count_derived%' THEN 1 ELSE 0 END) AS objective_derived_rows,
                SUM(CASE WHEN coverage_note LIKE '%clamped_to_min_zero%' THEN 1 ELSE 0 END) AS clamped_rows
            FROM stg_player_match_enriched_stats
            WHERE stat_name IN ({tracked_stats})
            GROUP BY stat_name
        )
        SELECT
            t.stat_name,
            t.preferred_source,
            t.fallback_source,
            t.source_field_name,
            t.coverage_status,
            e.expected_rows,
            COALESCE(f.final_rows, 0) AS final_rows,
            CASE
                WHEN (
                    COALESCE(s.field_present_rows, 0)
                  + COALESCE(s.sparse_zero_rows, 0)
                  + COALESCE(s.source_missing_rows, 0)
                  + COALESCE(s.objective_derived_rows, 0)
                ) > 0 THEN 1
                ELSE 0
            END AS has_stage_evidence,
            CASE
                WHEN (
                    COALESCE(s.field_present_rows, 0)
                  + COALESCE(s.sparse_zero_rows, 0)
                  + COALESCE(s.source_missing_rows, 0)
                  + COALESCE(s.objective_derived_rows, 0)
                ) = 0
                 AND t.coverage_status = 'source_needed' THEN 0
                WHEN COALESCE(f.final_rows, 0) = e.expected_rows THEN 1
                ELSE 0
            END AS is_row_complete,
            COALESCE(f.zero_raw_rows, 0) AS zero_raw_rows,
            COALESCE(f.nonzero_raw_rows, 0) AS nonzero_raw_rows,
            COALESCE(s.field_present_rows, 0) AS field_present_rows,
            COALESCE(s.sparse_zero_rows, 0) AS sparse_zero_rows,
            COALESCE(s.source_missing_rows, 0) AS source_missing_rows,
            COALESCE(s.objective_derived_rows, 0) AS objective_derived_rows,
            COALESCE(s.clamped_rows, 0) AS clamped_rows,
            COALESCE(f.min_raw_value, 0) AS min_raw_value,
            COALESCE(f.max_raw_value, 0) AS max_raw_value
        FROM target_stats t
        CROSS JOIN expected e
        LEFT JOIN final_counts f
            ON f.stat_name = t.stat_name
        LEFT JOIN stage_counts s
            ON s.stat_name = t.stat_name
        ORDER BY t.stat_name
        """
    )
    cur.execute("DROP VIEW IF EXISTS analytics_fantasy_backfill_sanity")
    cur.execute(
        f"""
        CREATE VIEW analytics_fantasy_backfill_sanity AS
        SELECT
            stat_name,
            'source_missing_in_payload' AS issue_type,
            COUNT(*) AS issue_rows,
            NULL AS sample_min_value,
            NULL AS sample_max_value
        FROM stg_player_match_enriched_stats
        WHERE stat_name IN ({tracked_stats})
          AND coverage_note = 'field_missing_in_payload'
        GROUP BY stat_name

        UNION ALL

        SELECT
            stat_name,
            'sparse_zero_assumed' AS issue_type,
            COUNT(*) AS issue_rows,
            NULL AS sample_min_value,
            NULL AS sample_max_value
        FROM stg_player_match_enriched_stats
        WHERE stat_name IN ({tracked_stats})
          AND coverage_note LIKE 'field_absent_zero_assumed%'
        GROUP BY stat_name

        UNION ALL

        SELECT
            stat_name,
            'clamped_source_values' AS issue_type,
            COUNT(*) AS issue_rows,
            NULL AS sample_min_value,
            NULL AS sample_max_value
        FROM stg_player_match_enriched_stats
        WHERE stat_name IN ({tracked_stats})
          AND coverage_note LIKE '%clamped_to_min_zero%'
        GROUP BY stat_name

        UNION ALL

        SELECT
            stat_name,
            'negative_raw_value_in_final_table' AS issue_type,
            COUNT(*) AS issue_rows,
            ROUND(MIN(raw_value), 6) AS sample_min_value,
            ROUND(MAX(raw_value), 6) AS sample_max_value
        FROM fantasy_player_map_stat_points
        WHERE stat_name IN ({tracked_stats})
          AND raw_value < 0
        GROUP BY stat_name

        UNION ALL

        SELECT
            stat_name,
            'non_integer_count_metric' AS issue_type,
            COUNT(*) AS issue_rows,
            ROUND(MIN(raw_value), 6) AS sample_min_value,
            ROUND(MAX(raw_value), 6) AS sample_max_value
        FROM fantasy_player_map_stat_points
        WHERE stat_name IN (
            'first_blood', 'runes_grabbed', 'wards_placed', 'smokes_used',
            'camps_stacked', 'courier_kills', 'roshan_kills',
            'watchers_taken', 'lotus', 'tormentor_kills'
        )
          AND ABS(raw_value - ROUND(raw_value)) > 1e-9
        GROUP BY stat_name
        """
    )


def ensure_backfill_schema(con: sqlite3.Connection) -> None:
    cur = con.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_match_source_payloads (
            source_name TEXT NOT NULL,
            match_id INTEGER NOT NULL,
            fetched_at_utc TEXT NOT NULL DEFAULT (datetime('now')),
            http_status INTEGER,
            parse_status TEXT,
            payload_json TEXT NOT NULL,
            payload_sha1 TEXT,
            notes TEXT,
            PRIMARY KEY (source_name, match_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_match_source_status (
            source_name TEXT NOT NULL,
            match_id INTEGER NOT NULL,
            fetch_attempts INTEGER NOT NULL DEFAULT 0,
            last_fetch_at_utc TEXT,
            last_success_at_utc TEXT,
            status TEXT NOT NULL,
            error_text TEXT,
            PRIMARY KEY (source_name, match_id)
        )
        """
    )
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

    _ensure_column(cur, "fantasy_scoring_stat_catalog", "preferred_source", "TEXT")
    _ensure_column(cur, "fantasy_scoring_stat_catalog", "fallback_source", "TEXT")
    _ensure_column(cur, "fantasy_scoring_stat_catalog", "source_field_name", "TEXT")
    _ensure_column(cur, "fantasy_scoring_stat_catalog", "coverage_status", "TEXT")
    _ensure_column(cur, "fantasy_scoring_stat_catalog", "emblem_color", "TEXT")

    refresh_backfill_views(con)
    con.commit()


def refresh_stat_catalog_metadata(con: sqlite3.Connection) -> None:
    cur = con.cursor()
    for stat_name, meta in STAT_SOURCE_MAP.items():
        cur.execute(
            """
            UPDATE fantasy_scoring_stat_catalog
            SET preferred_source = ?,
                fallback_source = ?,
                source_field_name = ?,
                coverage_status = ?
            WHERE stat_name = ?
            """,
            (
                meta["preferred_source"],
                meta["fallback_source"],
                meta["source_field_name"],
                meta["coverage_status"],
                stat_name,
            ),
        )
    con.commit()


def list_target_match_ids(con: sqlite3.Connection, limit: int | None = None) -> list[int]:
    sql = "SELECT match_id FROM matches ORDER BY match_date, match_id"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [int(row[0]) for row in con.execute(sql).fetchall()]


def load_team_name_map(con: sqlite3.Connection, match_ids: list[int]) -> dict[tuple[int, int], str]:
    if not match_ids:
        return {}
    placeholders = ",".join("?" for _ in match_ids)
    rows = con.execute(
        f"""
        SELECT DISTINCT match_id, account_id, team_name
        FROM player_game_fantasy_summary
        WHERE match_id IN ({placeholders})
        """,
        match_ids,
    ).fetchall()
    return {(int(match_id), int(account_id)): str(team_name) for match_id, account_id, team_name in rows if account_id is not None}


def load_cached_raw_payload(con: sqlite3.Connection, *, source_name: str, match_id: int) -> dict[str, Any] | None:
    row = con.execute(
        """
        SELECT payload_json
        FROM raw_match_source_payloads
        WHERE source_name = ?
          AND match_id = ?
        """,
        (source_name, match_id),
    ).fetchone()
    if not row:
        return None
    return json.loads(row[0])


def fetch_opendota_match_payload(match_id: int, *, timeout_sec: int = 30) -> tuple[dict[str, Any], int]:
    url = f"{OPENDOTA_BASE_URL}/{match_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "fantasy-analytics-backfill/0.1"})
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        body = resp.read()
        return json.loads(body.decode("utf-8")), getattr(resp, "status", 200)


def upsert_raw_payload(
    con: sqlite3.Connection,
    *,
    source_name: str,
    match_id: int,
    payload: dict[str, Any],
    http_status: int,
    parse_status: str,
    notes: str | None = None,
) -> None:
    payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    payload_sha1 = hashlib.sha1(payload_json.encode("utf-8")).hexdigest()
    cur = con.cursor()
    cur.execute(
        """
        INSERT OR REPLACE INTO raw_match_source_payloads(
            source_name, match_id, fetched_at_utc, http_status, parse_status,
            payload_json, payload_sha1, notes
        )
        VALUES (?, ?, datetime('now'), ?, ?, ?, ?, ?)
        """,
        (source_name, match_id, http_status, parse_status, payload_json, payload_sha1, notes),
    )
    cur.execute(
        """
        INSERT INTO raw_match_source_status(
            source_name, match_id, fetch_attempts, last_fetch_at_utc, last_success_at_utc, status, error_text
        )
        VALUES (?, ?, 1, datetime('now'), datetime('now'), ?, NULL)
        ON CONFLICT(source_name, match_id) DO UPDATE SET
            fetch_attempts = raw_match_source_status.fetch_attempts + 1,
            last_fetch_at_utc = datetime('now'),
            last_success_at_utc = datetime('now'),
            status = excluded.status,
            error_text = NULL
        """,
        (source_name, match_id, parse_status),
    )
    con.commit()


def mark_fetch_error(con: sqlite3.Connection, *, source_name: str, match_id: int, error_text: str) -> None:
    con.execute(
        """
        INSERT INTO raw_match_source_status(
            source_name, match_id, fetch_attempts, last_fetch_at_utc, status, error_text
        )
        VALUES (?, ?, 1, datetime('now'), 'error', ?)
        ON CONFLICT(source_name, match_id) DO UPDATE SET
            fetch_attempts = raw_match_source_status.fetch_attempts + 1,
            last_fetch_at_utc = datetime('now'),
            status = 'error',
            error_text = excluded.error_text
        """,
        (source_name, match_id, error_text[:1000]),
    )
    con.commit()


def _coerce_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _apply_stat_sanity(stat_name: str, raw_value: float, coverage_note: str) -> tuple[float, str]:
    meta = STAT_SOURCE_MAP.get(stat_name, {})
    min_allowed_raw = meta.get("min_allowed_raw")
    if min_allowed_raw is not None and raw_value < float(min_allowed_raw):
        return float(min_allowed_raw), f"{coverage_note};clamped_to_min_zero"
    return raw_value, coverage_note


def _extract_candidate_value(
    player_payload: dict[str, Any],
    field_names: list[str],
) -> tuple[str | None, float, str]:
    fallback_zero_field: str | None = None
    for field_name in field_names:
        if "." in field_name:
            current: Any = player_payload
            parts = field_name.split(".")
            found = True
            for part in parts[:-1]:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    found = False
                    break
            if not found:
                continue
            leaf = parts[-1]
            if isinstance(current, dict) and leaf in current:
                return field_name, _coerce_float(current[leaf]), "field_present"
            if isinstance(current, dict):
                fallback_zero_field = fallback_zero_field or field_name
        elif field_name in player_payload:
            return field_name, _coerce_float(player_payload.get(field_name)), "field_present"
    if fallback_zero_field:
        return fallback_zero_field, 0.0, "field_absent_zero_assumed"
    return None, 0.0, "field_missing_in_payload"


def _player_lookup_maps(payload: dict[str, Any]) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    players = payload.get("players") or []
    by_player_slot: dict[int, dict[str, Any]] = {}
    by_slot_index: dict[int, dict[str, Any]] = {}
    for slot_index, player in enumerate(players):
        by_slot_index[slot_index] = player
        player_slot = player.get("player_slot")
        if player_slot is not None:
            by_player_slot[int(player_slot)] = player
    return by_player_slot, by_slot_index


def _extract_tormentor_counts(payload: dict[str, Any]) -> dict[int, int]:
    by_player_slot, by_slot_index = _player_lookup_maps(payload)
    counts: dict[int, int] = {}
    for objective in payload.get("objectives") or []:
        if objective.get("type") != TORMENTOR_OBJECTIVE_TYPE:
            continue
        player: dict[str, Any] | None = None
        player_slot = objective.get("player_slot")
        slot_index = objective.get("slot")
        if player_slot is not None:
            player = by_player_slot.get(int(player_slot))
        if player is None and slot_index is not None:
            player = by_slot_index.get(int(slot_index))
        if not player:
            continue
        account_id = player.get("account_id")
        if account_id is None:
            continue
        counts[int(account_id)] = counts.get(int(account_id), 0) + 1
    return counts


def extract_opendota_stat_rows(
    *,
    match_id: int,
    payload: dict[str, Any],
    team_name_map: dict[tuple[int, int], str],
    stat_names: list[str] | None = None,
) -> list[ExtractedStatRow]:
    wanted = stat_names or OPENDOTA_SUPPORTED_STATS
    players = payload.get("players") or []
    rows: list[ExtractedStatRow] = []
    tormentor_counts = _extract_tormentor_counts(payload)

    for player in players:
        account_id = player.get("account_id")
        if account_id is None:
            continue
        account_id = int(account_id)
        team_name = team_name_map.get((match_id, account_id))
        if not team_name:
            continue

        for stat_name in wanted:
            meta = STAT_SOURCE_MAP.get(stat_name)
            if not meta or meta.get("preferred_source") != "opendota":
                continue
            if stat_name == "tormentor_kills":
                field_name = str(meta["source_field_name"])
                raw_value = float(tormentor_counts.get(account_id, 0))
                coverage_note = "objective_count_derived"
            else:
                field_name, raw_value, coverage_note = _extract_candidate_value(player, list(meta["candidate_fields"]))
            raw_value, coverage_note = _apply_stat_sanity(stat_name, raw_value, coverage_note)
            rows.append(
                ExtractedStatRow(
                    source_name="opendota",
                    match_id=match_id,
                    account_id=account_id,
                    team_name=team_name,
                    stat_name=stat_name,
                    raw_value=raw_value,
                    source_field_name=field_name or str(meta["source_field_name"]),
                    extraction_method="opendota_match_players",
                    coverage_note=coverage_note,
                )
            )
    return rows


def upsert_stage_rows(con: sqlite3.Connection, rows: list[ExtractedStatRow]) -> None:
    if not rows:
        return
    con.executemany(
        """
        INSERT OR REPLACE INTO stg_player_match_enriched_stats(
            source_name, match_id, account_id, team_name, stat_name, raw_value,
            source_field_name, extraction_method, coverage_note, created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        [
            (
                row.source_name,
                row.match_id,
                row.account_id,
                row.team_name,
                row.stat_name,
                row.raw_value,
                row.source_field_name,
                row.extraction_method,
                row.coverage_note,
            )
            for row in rows
        ],
    )
    con.commit()


def _base_points_from_raw(stat_name: str, raw_value: float) -> float:
    formula = STAT_POINT_FORMULAS[stat_name]
    if isinstance(formula, (int, float)):
        return round(raw_value * float(formula), 6)
    kind, value = formula
    if kind == "binary_bonus":
        return float(value) if raw_value > 0 else 0.0
    raise ValueError(f"Unsupported special formula for {stat_name}: {formula!r}")


def upsert_stat_points_from_staging(
    con: sqlite3.Connection,
    *,
    source_name: str = "opendota",
    stat_names: list[str] | None = None,
    run_id: str | None = None,
    restrict_to_staged_matches: bool = True,
) -> dict[str, int]:
    wanted = stat_names or OPENDOTA_SUPPORTED_STATS
    cur = con.cursor()
    stats_summary: dict[str, int] = {}

    for stat_name in wanted:
        staged_rows = cur.execute(
            """
            SELECT match_id, account_id, team_name, raw_value, source_field_name
            FROM stg_player_match_enriched_stats
            WHERE source_name = ?
              AND stat_name = ?
            """,
            (source_name, stat_name),
        ).fetchall()
        if not staged_rows:
            stats_summary[stat_name] = 0
            continue

        staged_match_ids = sorted({int(row[0]) for row in staged_rows})
        if restrict_to_staged_matches:
            placeholders = ",".join("?" for _ in staged_match_ids)
            cur.execute(
                f"""
                DELETE FROM fantasy_player_map_stat_points
                WHERE stat_name = ?
                  AND match_id IN ({placeholders})
                """,
                [stat_name, *staged_match_ids],
            )
        else:
            cur.execute(
                """
                DELETE FROM fantasy_player_map_stat_points
                WHERE stat_name = ?
                """,
                (stat_name,),
            )
        inserts = []
        nonzero_rows = 0
        for match_id, account_id, team_name, raw_value, source_field_name in staged_rows:
            raw_value = _coerce_float(raw_value)
            base_points = _base_points_from_raw(stat_name, raw_value)
            if raw_value != 0 or base_points != 0:
                nonzero_rows += 1
            inserts.append(
                (
                    int(match_id),
                    int(account_id),
                    str(team_name),
                    stat_name,
                    raw_value,
                    base_points,
                    f"{stat_name}_points_backfilled",
                    f"stg_player_match_enriched_stats:{source_field_name}",
                )
            )
        cur.executemany(
            """
            INSERT OR REPLACE INTO fantasy_player_map_stat_points(
                match_id, account_id, team_name, stat_name, raw_value, base_points,
                base_points_column, source_table, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            inserts,
        )
        stats_summary[stat_name] = len(inserts)
        if run_id:
            cur.execute(
                """
                INSERT INTO fantasy_stat_backfill_audit(
                    run_id, stat_name, source_name, rows_written, nonzero_rows, created_at_utc
                )
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                """,
                (run_id, stat_name, source_name, len(inserts), nonzero_rows),
            )
    con.commit()
    return stats_summary


def summarize_nonzero_coverage(con: sqlite3.Connection, *, table_name: str = "stg_player_match_enriched_stats") -> list[tuple[Any, ...]]:
    return con.execute(
        f"""
        SELECT
            stat_name,
            COUNT(*) AS total_rows,
            SUM(CASE WHEN COALESCE(raw_value, 0) != 0 THEN 1 ELSE 0 END) AS nonzero_rows,
            ROUND(MAX(COALESCE(raw_value, 0)), 4) AS max_raw_value
        FROM {table_name}
        GROUP BY stat_name
        ORDER BY stat_name
        """
    ).fetchall()


def fetch_many_opendota_matches(
    con: sqlite3.Connection,
    *,
    match_ids: list[int],
    write_raw: bool,
    write_stage: bool,
    sleep_sec: float = 0.5,
    timeout_sec: int = 30,
    overwrite_stage: bool = True,
    skip_existing_raw: bool = False,
    use_cached_raw: bool = False,
) -> dict[str, Any]:
    ensure_backfill_schema(con)
    refresh_stat_catalog_metadata(con)
    team_name_map = load_team_name_map(con, match_ids)

    processed_matches = 0
    fetch_errors: list[tuple[int, str]] = []
    stage_rows_total = 0
    detected_fields: dict[str, set[str]] = {stat_name: set() for stat_name in OPENDOTA_SUPPORTED_STATS}

    for index, match_id in enumerate(match_ids, start=1):
        try:
            if use_cached_raw:
                payload = load_cached_raw_payload(con, source_name="opendota", match_id=match_id)
                if payload is None:
                    fetch_errors.append((match_id, "cached raw payload not found"))
                    continue
                http_status = 200
            else:
                if skip_existing_raw:
                    existing = con.execute(
                        """
                        SELECT 1
                        FROM raw_match_source_payloads
                        WHERE source_name = 'opendota'
                          AND match_id = ?
                        """,
                        (match_id,),
                    ).fetchone()
                    if existing:
                        continue

                payload, http_status = fetch_opendota_match_payload(match_id, timeout_sec=timeout_sec)

            parse_status = "ok" if payload.get("players") else "empty_players"
            if write_raw and not use_cached_raw:
                upsert_raw_payload(
                    con,
                    source_name="opendota",
                    match_id=match_id,
                    payload=payload,
                    http_status=http_status,
                    parse_status=parse_status,
                )

            rows = extract_opendota_stat_rows(
                match_id=match_id,
                payload=payload,
                team_name_map=team_name_map,
            )
            if write_stage:
                if overwrite_stage:
                    con.execute(
                        """
                        DELETE FROM stg_player_match_enriched_stats
                        WHERE source_name = 'opendota'
                          AND match_id = ?
                        """,
                        (match_id,),
                    )
                    con.commit()
                upsert_stage_rows(con, rows)
            stage_rows_total += len(rows)
            for row in rows:
                if row.coverage_note == "field_present":
                    detected_fields[row.stat_name].add(row.source_field_name)
            processed_matches += 1
        except urllib.error.HTTPError as exc:
            fetch_errors.append((match_id, f"HTTP {exc.code}: {exc.reason}"))
            if write_raw:
                mark_fetch_error(con, source_name="opendota", match_id=match_id, error_text=f"HTTP {exc.code}: {exc.reason}")
        except Exception as exc:  # noqa: BLE001
            fetch_errors.append((match_id, str(exc)))
            if write_raw:
                mark_fetch_error(con, source_name="opendota", match_id=match_id, error_text=str(exc))

        if sleep_sec and index < len(match_ids):
            time.sleep(sleep_sec)

    return {
        "processed_matches": processed_matches,
        "stage_rows_total": stage_rows_total,
        "fetch_errors": fetch_errors,
        "detected_fields": {key: sorted(value) for key, value in detected_fields.items()},
        "coverage_summary": summarize_nonzero_coverage(con) if write_stage else [],
    }
