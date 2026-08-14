from __future__ import annotations

import json
import sqlite3
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from enrichment.opendota_backfill import (
    ensure_backfill_schema,
    extract_opendota_stat_rows,
    refresh_backfill_views,
    refresh_stat_catalog_metadata,
    upsert_raw_payload,
    upsert_stage_rows,
    upsert_stat_points_from_staging,
)
from fantasy_profile_constructor import recalculate_profile_scores
from tournament_config import load_tournament_config, resolve_event_db_path
from tournament_identity import (
    RosterTeam,
    canonical_team_name,
    load_prior_identities,
    parse_ti2026_participants_from_raw,
    resolve_team_identity,
    serialize_roster_text,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

LIQUIPEDIA_RAW_URL = "https://liquipedia.net/dota2/The_International/2026?action=raw"
OPENDOTA_MATCH_URL = "https://api.opendota.com/api/matches/{match_id}"
OPENDOTA_LEAGUE_MATCHES_URL = "https://api.opendota.com/api/leagues/{league_id}/matches"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def iso_date_from_unix(timestamp: int | None) -> str | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(int(timestamp), timezone.utc).date().isoformat()


def fetch_text(url: str, *, timeout_sec: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout_sec) as response:
        return response.read().decode("utf-8")


def fetch_json(url: str, *, timeout_sec: int = 30) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout_sec) as response:
        return json.loads(response.read().decode("utf-8"))


def stage_fields_for_date(config_stage_rules: dict[str, Any], match_date: str | None) -> dict[str, Any]:
    if not match_date:
        return {
            "stage_name": "Unknown",
            "stage_bucket": "unknown",
            "stage_bucket_label": "Unknown",
            "is_group_stage_bucket": 0,
            "is_main_playoff": 0,
            "stage_sort": 999,
        }
    group_start = str(config_stage_rules.get("group_stage_start", "1900-01-01"))
    group_end = str(config_stage_rules.get("group_stage_end", "1900-01-01"))
    main_start = str(config_stage_rules.get("main_event_start", "9999-12-31"))
    main_end = str(config_stage_rules.get("main_event_end", "9999-12-31"))
    if group_start <= match_date <= group_end:
        return {
            "stage_name": "Group Stage",
            "stage_bucket": "group_stage",
            "stage_bucket_label": "Group Stage",
            "is_group_stage_bucket": 1,
            "is_main_playoff": 0,
            "stage_sort": 1,
        }
    if main_start <= match_date <= main_end:
        return {
            "stage_name": "Main Event",
            "stage_bucket": "playoff",
            "stage_bucket_label": "Playoffs",
            "is_group_stage_bucket": 0,
            "is_main_playoff": 1,
            "stage_sort": 2,
        }
    return {
        "stage_name": "Elimination Round",
        "stage_bucket": "group_stage",
        "stage_bucket_label": "Group Stage",
        "is_group_stage_bucket": 1,
        "is_main_playoff": 0,
        "stage_sort": 1,
    }


def upsert_metadata(con: sqlite3.Connection, items: dict[str, Any]) -> None:
    con.executemany(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
        [(str(key), str(value)) for key, value in items.items()],
    )


def upsert_source_page(con: sqlite3.Connection, source_name: str, url: str, *, status: str, notes: str = "") -> None:
    con.execute(
        """
        INSERT OR REPLACE INTO source_pages(source_name, url, fetched_at_utc, status, cache_file, sha256, notes)
        VALUES (?, ?, ?, ?, NULL, NULL, ?)
        """,
        (source_name, url, utc_now(), status, notes),
    )


def ensure_event_support_tables(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS source_pages (
            source_name TEXT NOT NULL,
            url TEXT NOT NULL,
            fetched_at_utc TEXT,
            status TEXT NOT NULL,
            cache_file TEXT,
            sha256 TEXT,
            notes TEXT,
            PRIMARY KEY (source_name, url)
        )
        """
    )
    con.commit()


def begin_sync_run(con: sqlite3.Connection, *, event_id: str, source_name: str, notes: str) -> str:
    run_id = f"sync::{event_id}::{uuid4().hex[:12]}"
    con.execute(
        """
        INSERT INTO event_sync_runs(
            run_id, event_id, source_name, status, started_at_utc, notes
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (run_id, event_id, source_name, "running", utc_now(), notes),
    )
    con.commit()
    return run_id


def finish_sync_run(
    con: sqlite3.Connection,
    *,
    run_id: str,
    status: str,
    new_match_count: int,
    updated_match_count: int,
    failed_match_count: int,
    notes: str,
) -> None:
    con.execute(
        """
        UPDATE event_sync_runs
        SET status = ?,
            finished_at_utc = ?,
            new_match_count = ?,
            updated_match_count = ?,
            failed_match_count = ?,
            notes = ?
        WHERE run_id = ?
        """,
        (status, utc_now(), new_match_count, updated_match_count, failed_match_count, notes, run_id),
    )
    con.commit()


def record_sync_match_log(
    con: sqlite3.Connection,
    *,
    run_id: str,
    event_id: str,
    source_name: str,
    match_id: int,
    action_name: str,
    status: str,
    notes: str = "",
) -> None:
    con.execute(
        """
        INSERT OR REPLACE INTO event_sync_match_log(
            run_id, event_id, match_id, action_name, status, source_name, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, event_id, int(match_id), action_name, status, source_name, notes),
    )


def seed_stat_catalog_from_template(con: sqlite3.Connection, template_db_path: Path | None) -> int:
    if template_db_path is None or not template_db_path.exists():
        return 0
    current_count = con.execute("SELECT COUNT(*) FROM fantasy_scoring_stat_catalog").fetchone()[0]
    if current_count:
        return int(current_count)

    source = sqlite3.connect(str(template_db_path))
    try:
        source_cols = [row[1] for row in source.execute("PRAGMA table_info(fantasy_scoring_stat_catalog)").fetchall()]
        target_cols = [row[1] for row in con.execute("PRAGMA table_info(fantasy_scoring_stat_catalog)").fetchall()]
        shared_cols = [col for col in source_cols if col in target_cols]
        if not shared_cols:
            return 0
        quoted_cols = ", ".join(shared_cols)
        rows = source.execute(f"SELECT {quoted_cols} FROM fantasy_scoring_stat_catalog").fetchall()
        if rows:
            placeholders = ", ".join("?" for _ in shared_cols)
            con.executemany(
                f"INSERT INTO fantasy_scoring_stat_catalog({quoted_cols}) VALUES ({placeholders})",
                rows,
            )
            con.commit()
        return len(rows)
    finally:
        source.close()


def seed_team_aliases(con: sqlite3.Connection, teams: list[RosterTeam], observed_team_names: list[str]) -> None:
    rows = []
    for team in teams:
        rows.append((team.source_team_name, team.team_name, "liquipedia_ti2026", LIQUIPEDIA_RAW_URL))
        rows.append((team.team_name, team.team_name, "liquipedia_ti2026", LIQUIPEDIA_RAW_URL))
    for name in observed_team_names:
        canonical = canonical_team_name(name) or name
        rows.append((name, canonical, "opendota_ti2026", f"https://api.opendota.com/api/leagues/19719/matches"))
    deduped = {(alias, canonical, source_name, source_url) for alias, canonical, source_name, source_url in rows if alias and canonical}
    con.executemany(
        """
        INSERT OR REPLACE INTO team_aliases(alias, canonical_team_name, source_name, source_url)
        VALUES (?, ?, ?, ?)
        """,
        list(deduped),
    )


def load_hero_lookup(con: sqlite3.Connection) -> dict[int, str]:
    rows = con.execute("SELECT hero_id, localized_name FROM dota_heroes").fetchall()
    return {int(hero_id): str(localized_name) for hero_id, localized_name in rows}


def build_observed_identity_rows(payloads: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    team_rows: dict[str, dict[int, list[dict[str, Any]]]] = {}
    for payload in payloads:
        radiant_name = canonical_team_name(payload.get("radiant_name")) or payload.get("radiant_name")
        dire_name = canonical_team_name(payload.get("dire_name")) or payload.get("dire_name")
        for player in payload.get("players") or []:
            account_id = player.get("account_id")
            if account_id is None:
                continue
            team_name = radiant_name if player.get("isRadiant") else dire_name
            if not team_name:
                continue
            team_store = team_rows.setdefault(str(team_name), {})
            player_store = team_store.setdefault(int(account_id), [])
            player_store.append(
                {
                    "account_id": int(account_id),
                    "name": player.get("name"),
                    "personaname": player.get("personaname"),
                    "gpm": float(player.get("gold_per_min") or 0.0),
                    "last_hits": float(player.get("last_hits") or 0.0),
                    "xpm": float(player.get("xp_per_min") or 0.0),
                    "obs_placed": float(player.get("obs_placed") or player.get("observers_placed") or 0.0),
                }
            )
    aggregated: dict[str, list[dict[str, Any]]] = {}
    for team_name, players in team_rows.items():
        aggregated[team_name] = []
        for account_id, entries in players.items():
            aggregated[team_name].append(
                {
                    "account_id": account_id,
                    "name": next((entry["name"] for entry in entries if entry["name"]), None),
                    "personaname": next((entry["personaname"] for entry in entries if entry["personaname"]), None),
                    "maps_seen": len(entries),
                    "avg_gpm": sum(entry["gpm"] for entry in entries) / len(entries),
                    "avg_last_hits": sum(entry["last_hits"] for entry in entries) / len(entries),
                    "avg_xpm": sum(entry["xpm"] for entry in entries) / len(entries),
                    "avg_observers": sum(entry["obs_placed"] for entry in entries) / len(entries),
                }
            )
    return aggregated


def upsert_ti_qualified_teams(con: sqlite3.Connection, roster_teams: list[RosterTeam], event_id: str) -> None:
    con.execute("DELETE FROM ti_qualified_teams WHERE event_id = ?", (event_id,))
    rows = []
    for team in roster_teams:
        rows.append(
            (
                event_id,
                team.team_name,
                team.source_team_name,
                team.qualification_status,
                team.qualification_path,
                team.region,
                serialize_roster_text(team.players),
                "Liquipedia",
                LIQUIPEDIA_RAW_URL,
                None,
                utc_now(),
                "high",
                "bootstrapped_from_liquipedia_raw",
            )
        )
    con.executemany(
        """
        INSERT OR REPLACE INTO ti_qualified_teams(
            event_id, team_name, source_team_name, qualification_status, qualification_path, region,
            roster_text, source_name, source_url, secondary_source_url, checked_at_utc, confidence_label, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def upsert_liquipedia_rosters(con: sqlite3.Connection, roster_teams: list[RosterTeam], resolved_identity_rows: list[dict[str, Any]]) -> None:
    existing = {
        (str(row[0]), int(row[1])): {
            "account_id": row[2],
            "matched_names": row[3],
        }
        for row in con.execute(
            """
            SELECT db_team, official_position, account_id, matched_names
            FROM liquipedia_team_rosters
            """
        ).fetchall()
    }
    incoming_teams = sorted({team.team_name for team in roster_teams})
    if incoming_teams:
        placeholders = ",".join("?" for _ in incoming_teams)
        con.execute(f"DELETE FROM liquipedia_team_rosters WHERE db_team IN ({placeholders})", incoming_teams)
    by_team_and_pos = {(row["team_name"], int(row["official_position"])): row for row in resolved_identity_rows}
    rows = []
    for team in roster_teams:
        for player in team.players:
            identity = by_team_and_pos.get((team.team_name, player.official_position))
            fallback = existing.get((team.team_name, player.official_position), {})
            rows.append(
                (
                    team.team_name,
                    team.source_team_name,
                    int(identity["account_id"]) if identity else fallback.get("account_id"),
                    player.official_name,
                    player.official_position,
                    player.role_label,
                    player.role_group,
                    None,
                    None,
                    identity["db_player_name"] if identity else fallback.get("matched_names"),
                    LIQUIPEDIA_RAW_URL,
                    utc_now(),
                )
            )
    con.executemany(
        """
        INSERT OR REPLACE INTO liquipedia_team_rosters(
            db_team, liquipedia_team, account_id, official_name, official_position, role_label,
            role_group, liquipedia_link, liquipedia_id, matched_names, source_url, fetched_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def upsert_identity_registry(con: sqlite3.Connection, rows: list[dict[str, Any]]) -> None:
    incoming_teams = sorted({str(row["team_name"]) for row in rows})
    if incoming_teams:
        placeholders = ",".join("?" for _ in incoming_teams)
        con.execute(f"DELETE FROM player_identity_registry WHERE team_name IN ({placeholders})", incoming_teams)
    con.executemany(
        """
        INSERT OR REPLACE INTO player_identity_registry(
            account_id, team_name, official_name, db_player_name, public_personaname,
            official_position, role_label, role_group, position_source, identity_source,
            confidence_score, confidence_label, maps_seen, maps_at_position, avg_fantasy_score,
            best_map_fantasy_score, source_name, source_url, resolved_at_utc, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row["account_id"],
                row["team_name"],
                row["official_name"],
                row["db_player_name"],
                row["public_personaname"],
                row["official_position"],
                row["role_label"],
                row["role_group"],
                row["position_source"],
                row["identity_source"],
                row["confidence_score"],
                row["confidence_label"],
                row["maps_seen"],
                row["maps_at_position"],
                row["avg_fantasy_score"],
                row["best_map_fantasy_score"],
                row["source_name"],
                row["source_url"],
                utc_now(),
                row["notes"],
            )
            for row in rows
        ],
    )


def compute_deaths_points(raw_value: float) -> float:
    return max(0.0, 1950.0 - 195.0 * float(raw_value))


def compute_teamfight_points(ratio: float) -> float:
    ratio = max(0.0, min(1.0, float(ratio)))
    return 2124.0 * ratio


def stat_points_payload(player: dict[str, Any], *, team_kills: int, tormentor_kills: int) -> dict[str, float]:
    kills = float(player.get("kills") or 0.0)
    deaths = float(player.get("deaths") or 0.0)
    last_hits = float(player.get("last_hits") or 0.0)
    denies = float(player.get("denies") or 0.0)
    gpm = float(player.get("gold_per_min") or 0.0)
    wards = float(player.get("obs_placed") or player.get("observers_placed") or 0.0)
    camps = float(player.get("camps_stacked") or 0.0)
    runes = float(player.get("rune_pickups") or 0.0)
    watchers = 0.0
    lotus = 0.0
    roshan = float(player.get("roshans_killed") or 0.0)
    stuns = float(player.get("stuns") or 0.0)
    courier = float(player.get("courier_kills") or 0.0)
    first_blood = float(player.get("firstblood_claimed") or 0.0)
    smokes = float(((player.get("item_uses") or {}).get("smoke_of_deceit")) or 0.0)
    teamfight_ratio = 0.0 if team_kills <= 0 else min(1.0, (kills + float(player.get("assists") or 0.0)) / float(team_kills))
    return {
        "kills": kills,
        "deaths": deaths,
        "creep_score": last_hits + denies,
        "gpm": gpm,
        "wards_placed": wards,
        "camps_stacked": camps,
        "runes_grabbed": runes,
        "watchers_taken": watchers,
        "lotus": lotus,
        "roshan_kills": roshan,
        "teamfight_participation": teamfight_ratio,
        "stuns": stuns,
        "tormentor_kills": float(tormentor_kills),
        "courier_kills": courier,
        "first_blood": first_blood,
        "smokes_used": smokes,
    }


def base_points_for_stat(stat_name: str, raw_value: float) -> float:
    if stat_name == "kills":
        return 107.0 * raw_value
    if stat_name == "deaths":
        return compute_deaths_points(raw_value)
    if stat_name == "creep_score":
        return 3.0 * raw_value
    if stat_name == "gpm":
        return 2.0 * raw_value
    if stat_name == "wards_placed":
        return 117.0 * raw_value
    if stat_name == "camps_stacked":
        return 234.0 * raw_value
    if stat_name == "runes_grabbed":
        return 141.0 * raw_value
    if stat_name == "watchers_taken":
        return 147.0 * raw_value
    if stat_name == "lotus":
        return 176.0 * raw_value
    if stat_name == "roshan_kills":
        return 1172.0 * raw_value
    if stat_name == "teamfight_participation":
        return compute_teamfight_points(raw_value)
    if stat_name == "stuns":
        return 10.0 * raw_value
    if stat_name == "tormentor_kills":
        return 879.0 * raw_value
    if stat_name == "courier_kills":
        return 703.0 * raw_value
    if stat_name == "first_blood":
        return 1934.0 if raw_value > 0 else 0.0
    if stat_name == "smokes_used":
        return 293.0 * raw_value
    raise KeyError(stat_name)


def clear_match_rows(con: sqlite3.Connection, match_ids: list[int]) -> None:
    if not match_ids:
        return
    placeholders = ",".join("?" for _ in match_ids)
    for table_name, column_name in [
        ("matches", "match_id"),
        ("player_match_stats", "match_id"),
        ("team_match_stats", "match_id"),
        ("player_game_fantasy_summary", "match_id"),
        ("fantasy_player_map_stat_points", "match_id"),
        ("stg_player_match_enriched_stats", "match_id"),
    ]:
        con.execute(f"DELETE FROM {table_name} WHERE {column_name} IN ({placeholders})", match_ids)
    con.commit()


def insert_match_core_rows(
    con: sqlite3.Connection,
    *,
    payloads: list[dict[str, Any]],
    resolved_identity_rows: list[dict[str, Any]],
) -> dict[str, int]:
    hero_lookup = load_hero_lookup(con)
    identity_by_team_account = {(row["team_name"], int(row["account_id"])): row for row in resolved_identity_rows}
    stat_catalog = {
        stat_name: (raw_value_column, base_points_column)
        for stat_name, raw_value_column, base_points_column in con.execute(
            "SELECT stat_name, raw_value_column, base_points_column FROM fantasy_scoring_stat_catalog"
        ).fetchall()
    }

    match_rows = 0
    player_rows = 0
    team_rows = 0
    summary_rows = 0
    stat_point_rows = 0

    for payload in payloads:
        match_id = int(payload["match_id"])
        match_date = iso_date_from_unix(payload.get("start_time"))
        stage = stage_fields_for_date(load_tournament_config("ti2026").stage_rules, match_date)
        radiant_name = canonical_team_name(payload.get("radiant_name")) or str(payload.get("radiant_name"))
        dire_name = canonical_team_name(payload.get("dire_name")) or str(payload.get("dire_name"))

        con.execute(
            """
            INSERT OR REPLACE INTO matches(
                match_id, league_id, series_id, match_date, duration_sec, winner_name, loser_name,
                radiant_name, dire_name, radiant_score, dire_score, radiant_win, source_dotabuff_url,
                fetched_at_utc, quality_status, stage_name, stage_bucket, stage_bucket_label,
                is_group_stage_bucket, is_main_playoff, stage_sort
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                match_id,
                int(payload.get("leagueid") or 0),
                payload.get("series_id"),
                match_date,
                int(payload.get("duration") or 0),
                radiant_name if payload.get("radiant_win") else dire_name,
                dire_name if payload.get("radiant_win") else radiant_name,
                radiant_name,
                dire_name,
                int(payload.get("radiant_score") or 0),
                int(payload.get("dire_score") or 0),
                1 if payload.get("radiant_win") else 0,
                f"https://www.dotabuff.com/matches/{match_id}",
                utc_now(),
                "opendota_live_sync",
                stage["stage_name"],
                stage["stage_bucket"],
                stage["stage_bucket_label"],
                stage["is_group_stage_bucket"],
                stage["is_main_playoff"],
                stage["stage_sort"],
            ),
        )
        match_rows += 1

        radiant_score = int(payload.get("radiant_score") or 0)
        dire_score = int(payload.get("dire_score") or 0)
        team_infos = [
            (radiant_name, dire_name, "radiant", 1 if payload.get("radiant_win") else 0, radiant_score, dire_score),
            (dire_name, radiant_name, "dire", 0 if payload.get("radiant_win") else 1, dire_score, radiant_score),
        ]
        for team_name, opponent_name, side, won, kills, deaths in team_infos:
            con.execute(
                """
                INSERT OR REPLACE INTO team_match_stats(
                    match_id, team_name, opponent_name, side, won, kills, deaths, gold_per_min,
                    duration_sec, source_dotabuff_url, stage_name, stage_bucket, stage_bucket_label,
                    is_group_stage_bucket, is_main_playoff, stage_sort
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    match_id,
                    team_name,
                    opponent_name,
                    side,
                    won,
                    kills,
                    deaths,
                    int(payload.get("duration") or 0),
                    f"https://www.dotabuff.com/matches/{match_id}",
                    stage["stage_name"],
                    stage["stage_bucket"],
                    stage["stage_bucket_label"],
                    stage["is_group_stage_bucket"],
                    stage["is_main_playoff"],
                    stage["stage_sort"],
                ),
            )
            team_rows += 1

        tormentor_counts: dict[int, int] = {}
        for objective in payload.get("objectives") or []:
            if objective.get("type") == "CHAT_MESSAGE_MINIBOSS_KILL":
                player_slot = objective.get("player_slot")
                for player in payload.get("players") or []:
                    if player.get("player_slot") == player_slot and player.get("account_id") is not None:
                        account_id = int(player["account_id"])
                        tormentor_counts[account_id] = tormentor_counts.get(account_id, 0) + 1
                        break

        for player in payload.get("players") or []:
            account_id = player.get("account_id")
            if account_id is None:
                continue
            account_id = int(account_id)
            team_name = radiant_name if player.get("isRadiant") else dire_name
            opponent_name = dire_name if player.get("isRadiant") else radiant_name
            identity = identity_by_team_account.get((team_name, account_id))
            official_position = int(identity["official_position"]) if identity else None
            role_bucket = identity["role_group"] if identity else None
            hero_id = int(player.get("hero_id") or 0)
            hero_name = hero_lookup.get(hero_id, str(hero_id))

            con.execute(
                """
                INSERT OR REPLACE INTO player_match_stats(
                    match_id, team_name, side, account_id, player_name, hero_name, hero_id, position, kills,
                    deaths, assists, gold_per_min, xp_per_min, last_hits, denies, net_worth, hero_damage,
                    tower_damage, hero_healing, source_dotabuff_url, stage_name, stage_bucket,
                    stage_bucket_label, is_group_stage_bucket, is_main_playoff, stage_sort
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    match_id,
                    team_name,
                    "radiant" if player.get("isRadiant") else "dire",
                    account_id,
                    player.get("name") or player.get("personaname") or f"account_{account_id}",
                    hero_name,
                    hero_id,
                    official_position,
                    int(player.get("kills") or 0),
                    int(player.get("deaths") or 0),
                    int(player.get("assists") or 0),
                    int(player.get("gold_per_min") or 0),
                    int(player.get("xp_per_min") or 0),
                    int(player.get("last_hits") or 0),
                    int(player.get("denies") or 0),
                    int(player.get("net_worth") or 0),
                    int(player.get("hero_damage") or 0),
                    int(player.get("tower_damage") or 0),
                    int(player.get("hero_healing") or 0),
                    f"https://www.dotabuff.com/matches/{match_id}",
                    stage["stage_name"],
                    stage["stage_bucket"],
                    stage["stage_bucket_label"],
                    stage["is_group_stage_bucket"],
                    stage["is_main_playoff"],
                    stage["stage_sort"],
                ),
            )
            player_rows += 1

            raw_stats = stat_points_payload(
                player,
                team_kills=radiant_score if player.get("isRadiant") else dire_score,
                tormentor_kills=tormentor_counts.get(account_id, 0),
            )
            points = {stat_name: base_points_for_stat(stat_name, raw_value) for stat_name, raw_value in raw_stats.items()}
            total_score = sum(points.values())

            con.execute(
                """
                INSERT OR REPLACE INTO player_game_fantasy_summary(
                    league_id, series_id, match_id, match_date, team_name, opponent_name, player_name, account_id,
                    hero_id, hero_name, role_bucket, banner_name, side, won, duration_sec, kills, deaths, assists,
                    last_hits, denies, gpm, xpm, observer_wards_placed, camps_stacked, runes_grabbed, watchers_taken,
                    normal_lotus_used, great_lotus_used, greater_lotus_used, roshan_kills, tormentor_kills,
                    courier_kills, first_blood, stuns_sec, smokes_used, team_kills, teamfight_participation_ratio,
                    creep_score, lotus_units, kills_points, deaths_points, creep_score_points, gpm_points,
                    wards_points, camps_stacked_points, runes_grabbed_points, watchers_taken_points, lotus_points,
                    roshan_points, teamfight_participation_points, stuns_points, tormentor_points, courier_points,
                    first_blood_points, smokes_points, multiplier_kills, multiplier_creep_score,
                    multiplier_runes_grabbed, multiplier_watchers_taken, multiplier_lotus,
                    multiplier_teamfight_participation, score_from_kills, score_from_creep_score, score_from_runes,
                    score_from_watchers, score_from_lotuses, score_from_teamfight, player_map_fantasy_score,
                    scoring_version, teamfight_formula_used, lotus_formula_used, data_quality_note,
                    source_dotabuff_url, stage_name, stage_bucket, stage_bucket_label, is_group_stage_bucket,
                    is_main_playoff, stage_sort
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(payload.get("leagueid") or 0),
                    payload.get("series_id"),
                    match_id,
                    match_date,
                    team_name,
                    opponent_name,
                    player.get("name") or player.get("personaname") or (identity["official_name"] if identity else f"account_{account_id}"),
                    account_id,
                    hero_id,
                    hero_name,
                    role_bucket,
                    "x1_base_points",
                    "radiant" if player.get("isRadiant") else "dire",
                    1 if (player.get("isRadiant") and payload.get("radiant_win")) or ((not player.get("isRadiant")) and (not payload.get("radiant_win"))) else 0,
                    int(payload.get("duration") or 0),
                    int(raw_stats["kills"]),
                    int(raw_stats["deaths"]),
                    int(player.get("assists") or 0),
                    int(player.get("last_hits") or 0),
                    int(player.get("denies") or 0),
                    int(raw_stats["gpm"]),
                    int(player.get("xp_per_min") or 0),
                    int(raw_stats["wards_placed"]),
                    int(raw_stats["camps_stacked"]),
                    int(raw_stats["runes_grabbed"]),
                    int(raw_stats["watchers_taken"]),
                    0,
                    0,
                    0,
                    int(raw_stats["roshan_kills"]),
                    int(raw_stats["tormentor_kills"]),
                    int(raw_stats["courier_kills"]),
                    int(raw_stats["first_blood"]),
                    float(raw_stats["stuns"]),
                    int(raw_stats["smokes_used"]),
                    radiant_score if player.get("isRadiant") else dire_score,
                    float(raw_stats["teamfight_participation"]),
                    int(raw_stats["creep_score"]),
                    int(raw_stats["lotus"]),
                    float(points["kills"]),
                    float(points["deaths"]),
                    float(points["creep_score"]),
                    float(points["gpm"]),
                    float(points["wards_placed"]),
                    float(points["camps_stacked"]),
                    float(points["runes_grabbed"]),
                    float(points["watchers_taken"]),
                    float(points["lotus"]),
                    float(points["roshan_kills"]),
                    float(points["teamfight_participation"]),
                    float(points["stuns"]),
                    float(points["tormentor_kills"]),
                    float(points["courier_kills"]),
                    float(points["first_blood"]),
                    float(points["smokes_used"]),
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    float(points["kills"]),
                    float(points["creep_score"]),
                    float(points["runes_grabbed"]),
                    float(points["watchers_taken"]),
                    float(points["lotus"]),
                    float(points["teamfight_participation"]),
                    float(total_score),
                    "ti2026_live_sync_v1",
                    "min(1,(kills+assists)/team_kills)*2124",
                    "lotus_units*176",
                    "watchers/lotus not yet replay-enriched; values currently x0 from OpenDota-only sync",
                    f"https://www.dotabuff.com/matches/{match_id}",
                    stage["stage_name"],
                    stage["stage_bucket"],
                    stage["stage_bucket_label"],
                    stage["is_group_stage_bucket"],
                    stage["is_main_playoff"],
                    stage["stage_sort"],
                ),
            )
            summary_rows += 1

            for stat_name, raw_value in raw_stats.items():
                raw_col, points_col = stat_catalog.get(stat_name, (f"{stat_name}_raw", f"{stat_name}_points"))
                con.execute(
                    """
                    INSERT OR REPLACE INTO fantasy_player_map_stat_points(
                        match_id, account_id, team_name, stat_name, raw_value, base_points,
                        base_points_column, source_table, created_at_utc
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        match_id,
                        account_id,
                        team_name,
                        stat_name,
                        float(raw_value),
                        float(base_points_for_stat(stat_name, raw_value)),
                        points_col,
                        "player_game_fantasy_summary",
                        utc_now(),
                    ),
                )
                stat_point_rows += 1

    con.commit()
    return {
        "matches": match_rows,
        "player_match_stats": player_rows,
        "team_match_stats": team_rows,
        "player_game_fantasy_summary": summary_rows,
        "fantasy_player_map_stat_points": stat_point_rows,
    }


def update_identity_fantasy_stats(con: sqlite3.Connection) -> None:
    con.execute(
        """
        UPDATE player_identity_registry
        SET avg_fantasy_score = (
                SELECT ROUND(AVG(player_map_fantasy_score), 2)
                FROM player_game_fantasy_summary s
                WHERE s.account_id = player_identity_registry.account_id
                  AND s.team_name = player_identity_registry.team_name
            ),
            best_map_fantasy_score = (
                SELECT ROUND(MAX(player_map_fantasy_score), 2)
                FROM player_game_fantasy_summary s
                WHERE s.account_id = player_identity_registry.account_id
                  AND s.team_name = player_identity_registry.team_name
            )
        """
    )
    con.commit()


def rebuild_profiles(con: sqlite3.Connection) -> list[str]:
    profile_ids = [row[0] for row in con.execute("SELECT profile_id FROM fantasy_scoring_profiles").fetchall()]
    for profile_id in profile_ids:
        recalculate_profile_scores(con, str(profile_id))
    con.commit()
    return [str(profile_id) for profile_id in profile_ids]


def sync_ti2026(
    *,
    db_path: Path | None = None,
    sleep_sec: float = 0.2,
    timeout_sec: int = 30,
    limit_matches: int | None = None,
) -> dict[str, Any]:
    config = load_tournament_config("ti2026")
    target_db = db_path or resolve_event_db_path("ti2026")
    prior_db = resolve_event_db_path(config.schema_template_event_id or "ewc2026")
    con = sqlite3.connect(str(target_db))
    sync_run_id = ""
    try:
        ensure_event_support_tables(con)
        ensure_backfill_schema(con)
        seeded_stat_catalog_rows = seed_stat_catalog_from_template(con, prior_db)
        refresh_stat_catalog_metadata(con)
        sync_run_id = begin_sync_run(
            con,
            event_id="ti2026",
            source_name="liquipedia+opendota",
            notes="TI 2026 live sync started",
        )

        liquipedia_raw = fetch_text(LIQUIPEDIA_RAW_URL, timeout_sec=timeout_sec)
        raw_league_id, roster_teams = parse_ti2026_participants_from_raw(liquipedia_raw)
        league_id = config.opendota_league_id or raw_league_id
        if league_id is None:
            raise RuntimeError("Could not resolve TI 2026 OpenDota league id")

        league_matches = fetch_json(OPENDOTA_LEAGUE_MATCHES_URL.format(league_id=league_id), timeout_sec=timeout_sec)
        if limit_matches:
            league_matches = list(league_matches)[: int(limit_matches)]
        match_ids = [int(row["match_id"]) for row in league_matches]
        existing_match_ids = {
            int(row[0])
            for row in con.execute(
                f"SELECT match_id FROM matches WHERE match_id IN ({','.join('?' for _ in match_ids)})",
                match_ids,
            ).fetchall()
        } if match_ids else set()
        new_match_ids = sorted(set(match_ids) - existing_match_ids)
        updated_match_ids = sorted(existing_match_ids & set(match_ids))
        clear_match_rows(con, match_ids)
        payloads: list[dict[str, Any]] = []
        failed_match_ids: list[int] = []
        for index, match_id in enumerate(match_ids, start=1):
            try:
                payload = fetch_json(OPENDOTA_MATCH_URL.format(match_id=match_id), timeout_sec=timeout_sec)
            except Exception as exc:  # noqa: BLE001
                failed_match_ids.append(match_id)
                record_sync_match_log(
                    con,
                    run_id=sync_run_id,
                    event_id="ti2026",
                    source_name="opendota",
                    match_id=match_id,
                    action_name="fetch_match_payload",
                    status="error",
                    notes=str(exc)[:400],
                )
                con.commit()
                continue
            payloads.append(payload)
            upsert_raw_payload(
                con,
                source_name="opendota",
                match_id=match_id,
                payload=payload,
                http_status=200,
                parse_status="ok" if payload.get("players") else "empty_players",
                notes="ti2026 live sync",
            )
            record_sync_match_log(
                con,
                run_id=sync_run_id,
                event_id="ti2026",
                source_name="opendota",
                match_id=match_id,
                action_name="fetch_match_payload",
                status="ok",
                notes="new" if match_id in new_match_ids else "refresh",
            )
            if index != len(match_ids):
                time.sleep(sleep_sec)

        observed = build_observed_identity_rows(payloads)
        prior_identities = load_prior_identities(prior_db)

        resolved_identity_rows: list[dict[str, Any]] = []
        for team in roster_teams:
            resolved_identity_rows.extend(resolve_team_identity(team, observed.get(team.team_name, []), prior_identities))

        upsert_source_page(con, "Liquipedia TI2026 raw", LIQUIPEDIA_RAW_URL, status="http_200", notes="participants and stage bootstrap")
        upsert_source_page(
            con,
            "OpenDota TI2026 league matches",
            OPENDOTA_LEAGUE_MATCHES_URL.format(league_id=league_id),
            status="http_200",
            notes=f"{len(match_ids)} matches listed",
        )
        seed_team_aliases(con, roster_teams, [str(payload.get("radiant_name")) for payload in payloads] + [str(payload.get("dire_name")) for payload in payloads])
        upsert_ti_qualified_teams(con, roster_teams, "ti2026")
        upsert_identity_registry(con, resolved_identity_rows)
        upsert_liquipedia_rosters(con, roster_teams, resolved_identity_rows)
        upsert_metadata(
            con,
            {
                "event_id": "ti2026",
                "tournament_name": config.display_name,
                "source_liquipedia_url": LIQUIPEDIA_RAW_URL,
                "opendota_league_id": league_id,
                "liquipedia_participants_teams": len(roster_teams),
                "opendota_matches_loaded": len(match_ids),
                "last_ti2026_sync_utc": utc_now(),
            },
        )
        con.executemany(
            "INSERT OR REPLACE INTO tournament_info(key, value, source_url) VALUES (?, ?, ?)",
            [
                ("event_id", "ti2026", LIQUIPEDIA_RAW_URL),
                ("display_name", config.display_name, LIQUIPEDIA_RAW_URL),
                ("opendota_league_id", str(league_id), LIQUIPEDIA_RAW_URL),
                ("format", "Modified Swiss + Elimination Round + Main Event", LIQUIPEDIA_RAW_URL),
            ],
        )
        con.execute("DELETE FROM tournament_standings")
        con.executemany(
            """
            INSERT OR REPLACE INTO tournament_standings(team_name, canonical_team_name, placement, ti_qualified, source_url, parse_status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [(team.source_team_name, team.team_name, None, 1, LIQUIPEDIA_RAW_URL, "qualified_participants") for team in roster_teams],
        )
        counts = insert_match_core_rows(con, payloads=payloads, resolved_identity_rows=resolved_identity_rows)

        team_name_map = {
            (int(payload["match_id"]), int(player["account_id"])): (
                canonical_team_name(payload.get("radiant_name")) if player.get("isRadiant") else canonical_team_name(payload.get("dire_name"))
            )
            for payload in payloads
            for player in (payload.get("players") or [])
            if player.get("account_id") is not None
        }
        stage_rows_total = 0
        for payload in payloads:
            match_id = int(payload["match_id"])
            rows = extract_opendota_stat_rows(
                match_id=match_id,
                payload=payload,
                team_name_map=team_name_map,
            )
            upsert_stage_rows(con, rows)
            stage_rows_total += len(rows)
        upsert_stat_points_from_staging(con, source_name="opendota", run_id=f"ti2026_sync::{utc_now()}", restrict_to_staged_matches=True)
        refresh_backfill_views(con)
        rebuilt_profiles = rebuild_profiles(con)
        update_identity_fantasy_stats(con)
        finish_sync_run(
            con,
            run_id=sync_run_id,
            status="ok",
            new_match_count=len(new_match_ids),
            updated_match_count=len(updated_match_ids),
            failed_match_count=len(failed_match_ids),
            notes=f"Loaded {len(payloads)} payloads; failed={len(failed_match_ids)}",
        )
        con.commit()

        return {
            "event_id": "ti2026",
            "sync_run_id": sync_run_id,
            "league_id": league_id,
            "matches_loaded": len(match_ids),
            "payloads_loaded": len(payloads),
            "new_matches_loaded": len(new_match_ids),
            "updated_matches_loaded": len(updated_match_ids),
            "failed_matches": failed_match_ids,
            "roster_teams": len(roster_teams),
            "resolved_identity_rows": len(resolved_identity_rows),
            "seeded_stat_catalog_rows": seeded_stat_catalog_rows,
            "stage_rows_total": stage_rows_total,
            "recalculated_profiles": rebuilt_profiles,
            "table_rows_written": counts,
            "db_path": str(target_db),
        }
    except Exception as exc:  # noqa: BLE001
        if sync_run_id:
            finish_sync_run(
                con,
                run_id=sync_run_id,
                status="error",
                new_match_count=0,
                updated_match_count=0,
                failed_match_count=0,
                notes=str(exc)[:600],
            )
        raise
    finally:
        con.close()
