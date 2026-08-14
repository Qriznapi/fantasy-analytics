from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project_db import resolve_db_path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = resolve_db_path(PROJECT_ROOT)

VALID_ROLE_SCOPES = {"core", "mid", "support", "all", "pos1", "pos2", "pos3", "pos4", "pos5"}
VALID_TITLE_SLOTS = {"prefix", "suffix"}
BLUE_TITLE_HERO_NAMES = {
    "Ancient Apparition",
    "Arc Warden",
    "Brewmaster",
    "Crystal Maiden",
    "Dark Seer",
    "Disruptor",
    "Dawnbreaker",
    "Faceless Void",
    "Io",
    "Kunkka",
    "Lich",
    "Medusa",
    "Mirana",
    "Morphling",
    "Night Stalker",
    "Oracle",
    "Puck",
    "Razor",
    "Shadow Demon",
    "Skywrath Mage",
    "Slardar",
    "Slark",
    "Storm Spirit",
    "Tiny",
    "Underlord",
    "Vengeful Spirit",
    "Venomancer",
    "Winter Wyvern",
    "Zeus",
}


def rebuild_public_scoring_views(connection: sqlite3.Connection) -> None:
    cur = connection.cursor()
    cur.execute("DROP VIEW IF EXISTS analytics_scoring_titles")
    cur.execute(
        """
        CREATE VIEW analytics_scoring_titles AS
        SELECT
            t.profile_id,
            t.title_slot,
            t.title_name,
            t.role_scope,
            t.bonus_pct,
            t.condition_metric,
            t.condition_operator,
            t.condition_value,
            t.enabled,
            t.notes
        FROM fantasy_scoring_profile_titles t
        JOIN fantasy_scoring_profiles p
          ON p.profile_id = t.profile_id
         AND p.is_default = 1
        """
    )
    cur.execute("DROP VIEW IF EXISTS analytics_player_maps")
    cur.execute(
        """
        CREATE VIEW analytics_player_maps AS
        SELECT
            s.*,
            CASE WHEN ti.team_name IS NOT NULL THEN 1 ELSE 0 END AS ti2026_qualified,
            ti.qualification_path,
            ti.region AS ti_region
        FROM fantasy_player_map_scores s
        JOIN fantasy_scoring_profiles p
          ON p.profile_id = s.profile_id
         AND p.is_default = 1
        LEFT JOIN analytics_ti2026_teams ti
          ON ti.team_name = s.team_name
        """
    )


def ensure_title_schema(connection: sqlite3.Connection) -> None:
    cur = connection.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS fantasy_scoring_profile_titles (
            profile_id TEXT NOT NULL,
            title_slot TEXT NOT NULL CHECK (title_slot IN ('prefix', 'suffix')),
            title_name TEXT NOT NULL,
            role_scope TEXT NOT NULL DEFAULT 'all',
            bonus_pct REAL NOT NULL DEFAULT 0,
            condition_metric TEXT NOT NULL DEFAULT 'always',
            condition_operator TEXT NOT NULL DEFAULT '>=',
            condition_value REAL NOT NULL DEFAULT 0,
            enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
            source TEXT NOT NULL DEFAULT 'manual_title_rule',
            notes TEXT,
            created_at_utc TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at_utc TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (profile_id, title_slot),
            FOREIGN KEY (profile_id) REFERENCES fantasy_scoring_profiles(profile_id) ON DELETE CASCADE
        )
        """
    )
    columns = {
        row[1]
        for row in cur.execute("PRAGMA table_info(fantasy_player_map_scores)").fetchall()
    }
    if "title_bonus_points" not in columns:
        cur.execute(
            "ALTER TABLE fantasy_player_map_scores ADD COLUMN title_bonus_points REAL NOT NULL DEFAULT 0"
        )
    rebuild_public_scoring_views(connection)


def title_metric_expr_sql(
    *,
    summary_alias: str = "f",
    selected_alias: str = "s",
    title_alias: str = "t",
    hero_alias: str = "dh",
    series_alias: str = "sc",
) -> str:
    blue_hero_list = ", ".join("'" + name.replace("'", "''") + "'" for name in sorted(BLUE_TITLE_HERO_NAMES))
    metric_map = {
        "always": "1",
        "fantasy_score": f"{selected_alias}.fantasy_score_raw",
        "base_points_total": f"{selected_alias}.base_points_total",
        "profile_bonus_points": f"{selected_alias}.profile_bonus_points",
        "won": f"{summary_alias}.won",
        "duration_sec": f"{summary_alias}.duration_sec",
        "kills": f"{summary_alias}.kills",
        "deaths": f"{summary_alias}.deaths",
        "assists": f"{summary_alias}.assists",
        "last_hits": f"{summary_alias}.last_hits",
        "denies": f"{summary_alias}.denies",
        "creep_score": f"{summary_alias}.creep_score",
        "gpm": f"{summary_alias}.gpm",
        "xpm": f"{summary_alias}.xpm",
        "observer_wards_placed": f"{summary_alias}.observer_wards_placed",
        "wards_placed": f"{summary_alias}.observer_wards_placed",
        "camps_stacked": f"{summary_alias}.camps_stacked",
        "runes_grabbed": f"{summary_alias}.runes_grabbed",
        "watchers_taken": f"{summary_alias}.watchers_taken",
        "lotus_units": f"{summary_alias}.lotus_units",
        "lotus": f"{summary_alias}.lotus_units",
        "roshan_kills": f"{summary_alias}.roshan_kills",
        "tormentor_kills": f"{summary_alias}.tormentor_kills",
        "courier_kills": f"{summary_alias}.courier_kills",
        "first_blood": f"{summary_alias}.first_blood",
        "stuns_sec": f"{summary_alias}.stuns_sec",
        "smokes_used": f"{summary_alias}.smokes_used",
        "team_kills": f"{summary_alias}.team_kills",
        "teamfight_participation_ratio": f"{summary_alias}.teamfight_participation_ratio",
        "teamfight_participation": f"{summary_alias}.teamfight_participation_ratio",
        "is_agility_hero": f"CASE WHEN COALESCE({hero_alias}.primary_attr, '') = 'agi' THEN 1 ELSE 0 END",
        "is_strength_hero": f"CASE WHEN COALESCE({hero_alias}.primary_attr, '') = 'str' THEN 1 ELSE 0 END",
        "is_intelligence_hero": f"CASE WHEN COALESCE({hero_alias}.primary_attr, '') = 'int' THEN 1 ELSE 0 END",
        "is_universal_hero": f"CASE WHEN COALESCE({hero_alias}.primary_attr, '') = 'all' THEN 1 ELSE 0 END",
        "is_blue_title_hero": f"CASE WHEN COALESCE({summary_alias}.hero_name, '') IN ({blue_hero_list}) THEN 1 ELSE 0 END",
        "is_last_possible_match_of_series": (
            f"CASE WHEN COALESCE({series_alias}.map_number_in_series, 0) = COALESCE({series_alias}.max_possible_maps, 0) "
            f"THEN 1 ELSE 0 END"
        ),
    }
    parts = [f"WHEN {title_alias}.condition_metric = '{metric}' THEN {expr}" for metric, expr in metric_map.items()]
    return "CASE " + " ".join(parts) + " ELSE NULL END"


def title_condition_sql(
    *,
    summary_alias: str = "f",
    selected_alias: str = "s",
    title_alias: str = "t",
    hero_alias: str = "dh",
    series_alias: str = "sc",
) -> str:
    metric_expr = title_metric_expr_sql(
        summary_alias=summary_alias,
        selected_alias=selected_alias,
        title_alias=title_alias,
        hero_alias=hero_alias,
        series_alias=series_alias,
    )
    return f"""
    CASE
        WHEN {title_alias}.condition_metric = 'always' THEN 1
        WHEN ({metric_expr}) IS NULL THEN 0
        WHEN {title_alias}.condition_operator = '>=' AND ({metric_expr}) >= {title_alias}.condition_value THEN 1
        WHEN {title_alias}.condition_operator = '>'  AND ({metric_expr}) >  {title_alias}.condition_value THEN 1
        WHEN {title_alias}.condition_operator = '<=' AND ({metric_expr}) <= {title_alias}.condition_value THEN 1
        WHEN {title_alias}.condition_operator = '<'  AND ({metric_expr}) <  {title_alias}.condition_value THEN 1
        WHEN {title_alias}.condition_operator = '='  AND ABS(({metric_expr}) - {title_alias}.condition_value) < 1e-9 THEN 1
        ELSE 0
    END
    """


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_profile_id(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower()).strip("_")
    if not value:
        raise ValueError("profile_id cannot be empty")
    return value


def role_case_sql(alias: str = "pir") -> str:
    return (
        f"CASE "
        f"WHEN {alias}.official_position IN (1, 3) THEN 'core' "
        f"WHEN {alias}.official_position = 2 THEN 'mid' "
        f"WHEN {alias}.official_position IN (4, 5) THEN 'support' "
        f"ELSE 'unknown' END"
    )


def _profile_rows_from_banner_spec(
    profile_id: str,
    banner_spec: dict[str, list[dict[str, Any] | tuple[str, float]]],
) -> list[tuple[str, str, str, float, int, str, str]]:
    rows = []
    for role_scope, entries in banner_spec.items():
        if role_scope not in VALID_ROLE_SCOPES:
            raise ValueError(f"Unsupported role_scope={role_scope!r}")
        for index, entry in enumerate(entries, start=1):
            if isinstance(entry, dict):
                stat_name = str(entry["stat_name"])
                multiplier = float(entry.get("multiplier", 1.0))
                enabled = int(entry.get("enabled", 1))
                notes = str(entry.get("notes", f"banner_slot={index}"))
            else:
                stat_name = str(entry[0])
                multiplier = float(entry[1])
                enabled = 1
                notes = f"banner_slot={index}"
            rows.append((profile_id, role_scope, stat_name, multiplier, enabled, "user_banner_constructor", notes))
    return rows


def _banner_rows_from_banner_spec(
    profile_id: str,
    banner_spec: dict[str, list[dict[str, Any] | tuple[str, float]]],
) -> list[tuple[str, str, int, str, float, str | None, str | None, str]]:
    rows = []
    for role_scope, entries in banner_spec.items():
        for index, entry in enumerate(entries, start=1):
            if isinstance(entry, dict):
                stat_name = str(entry["stat_name"])
                multiplier = float(entry.get("multiplier", 1.0))
                quality = entry.get("quality_tier")
                trait = entry.get("trait")
                notes = str(entry.get("notes", "user banner constructor"))
            else:
                stat_name = str(entry[0])
                multiplier = float(entry[1])
                quality = None
                trait = None
                notes = "user banner constructor"
            rows.append((profile_id, role_scope, index, stat_name, multiplier, quality, trait, notes))
    return rows


def _title_rows_from_spec(
    profile_id: str,
    title_spec: list[dict[str, Any]],
) -> list[tuple[str, str, str, str, float, str, str, float, int, str, str]]:
    rows = []
    for entry in title_spec:
        title_slot = str(entry["title_slot"]).lower().strip()
        if title_slot not in VALID_TITLE_SLOTS:
            raise ValueError(f"Unsupported title_slot={title_slot!r}")
        role_scope = str(entry.get("role_scope", "all")).lower().strip()
        if role_scope not in VALID_ROLE_SCOPES:
            raise ValueError(f"Unsupported role_scope={role_scope!r}")
        rows.append(
            (
                profile_id,
                title_slot,
                str(entry["title_name"]),
                role_scope,
                float(entry.get("bonus_pct", 0.0)),
                str(entry.get("condition_metric", "always")),
                str(entry.get("condition_operator", ">=")),
                float(entry.get("condition_value", 0.0)),
                int(entry.get("enabled", 1)),
                str(entry.get("source", "manual_title_rule")),
                str(entry.get("notes", "")),
            )
        )
    return rows


def create_or_replace_banner_profile(
    connection: sqlite3.Connection,
    profile_id: str,
    banner_spec: dict[str, list[dict[str, Any] | tuple[str, float]]],
    *,
    title_spec: list[dict[str, Any]] | None = None,
    profile_name: str | None = None,
    owner_name: str = "local_user",
    set_default: bool = False,
    description: str | None = None,
    commit: bool = True,
) -> str:
    """Create/update a fantasy banner profile and recalculate all dependent scores.

    banner_spec example:
        {
            "core": [("kills", 2.5), ("creep_score", 2.5), ("teamfight_participation", 1.8)],
            "mid": [("creep_score", 2.7), ("runes_grabbed", 1.8), ("teamfight_participation", 2.7)],
            "support": [("lotus", 3.2), ("watchers_taken", 2.1), ("teamfight_participation", 1.5)],
        }
    """

    profile_id = normalize_profile_id(profile_id)
    profile_name = profile_name or profile_id
    description = description or "User-created fantasy banner profile."
    cur = connection.cursor()
    ensure_title_schema(connection)

    if set_default:
        cur.execute("UPDATE fantasy_scoring_profiles SET is_default = 0")

    cur.execute(
        """
        INSERT OR REPLACE INTO fantasy_scoring_profiles(
            profile_id, profile_name, owner_name, profile_type, base_formula_version,
            role_resolution_method, description, is_default, updated_at_utc, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)
        """,
        (
            profile_id,
            profile_name,
            owner_name,
            "banner_profile",
            "battlepass_base_points_v1",
            "liquipedia_official_position",
            description,
            1 if set_default else 0,
            "Created by fantasy_profile_constructor.create_or_replace_banner_profile",
        ),
    )
    cur.execute("DELETE FROM fantasy_scoring_profile_stats WHERE profile_id = ?", (profile_id,))
    cur.execute("DELETE FROM fantasy_scoring_profile_banners WHERE profile_id = ?", (profile_id,))
    cur.executemany(
        """
        INSERT OR REPLACE INTO fantasy_scoring_profile_stats(
            profile_id, role_scope, stat_name, multiplier, enabled, source, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        _profile_rows_from_banner_spec(profile_id, banner_spec),
    )
    cur.executemany(
        """
        INSERT OR REPLACE INTO fantasy_scoring_profile_banners(
            profile_id, role_scope, banner_slot, stat_name, multiplier,
            quality_tier, trait, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        _banner_rows_from_banner_spec(profile_id, banner_spec),
    )
    if title_spec is not None:
        cur.execute("DELETE FROM fantasy_scoring_profile_titles WHERE profile_id = ?", (profile_id,))
        if title_spec:
            cur.executemany(
                """
                INSERT OR REPLACE INTO fantasy_scoring_profile_titles(
                    profile_id, title_slot, title_name, role_scope, bonus_pct,
                    condition_metric, condition_operator, condition_value,
                    enabled, source, notes, updated_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                _title_rows_from_spec(profile_id, title_spec),
            )

    recalculate_profile_scores(connection, profile_id)
    if commit:
        connection.commit()
    return profile_id


def set_profile_title_rules(
    connection: sqlite3.Connection,
    profile_id: str,
    title_spec: list[dict[str, Any]],
    *,
    commit: bool = True,
) -> str:
    profile_id = normalize_profile_id(profile_id)
    ensure_title_schema(connection)
    cur = connection.cursor()
    cur.execute("DELETE FROM fantasy_scoring_profile_titles WHERE profile_id = ?", (profile_id,))
    if title_spec:
        cur.executemany(
            """
            INSERT OR REPLACE INTO fantasy_scoring_profile_titles(
                profile_id, title_slot, title_name, role_scope, bonus_pct,
                condition_metric, condition_operator, condition_value,
                enabled, source, notes, updated_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            _title_rows_from_spec(profile_id, title_spec),
        )
    recalculate_profile_scores(connection, profile_id)
    if commit:
        connection.commit()
    return profile_id


def recalculate_profile_scores(connection: sqlite3.Connection, profile_id: str) -> None:
    cur = connection.cursor()
    role_case = role_case_sql("pir")
    ensure_title_schema(connection)
    title_condition = title_condition_sql(
        summary_alias="f",
        selected_alias="s",
        title_alias="t",
        hero_alias="dh",
        series_alias="sc",
    )

    cur.execute("DELETE FROM fantasy_player_map_scores WHERE profile_id = ?", (profile_id,))
    cur.execute(
        f"""
        INSERT OR REPLACE INTO fantasy_player_map_scores(
            profile_id, match_id, match_date, series_id, league_id, account_id,
            team_name, opponent_name, official_name, official_position, role_group,
            hero_name, side, won, duration_sec, base_points_total, profile_bonus_points, title_bonus_points,
            fantasy_score, score_breakdown_json, scoring_source, data_quality_note,
            stage_name, stage_bucket, stage_bucket_label, is_group_stage_bucket,
            is_main_playoff, stage_sort
        )
        WITH selected_stats AS (
            SELECT
                f.match_id,
                f.match_date,
                f.series_id,
                f.league_id,
                f.account_id,
                f.team_name,
                f.opponent_name,
                pir.official_name,
                pir.official_position,
                {role_case} AS role_group,
                f.hero_name,
                f.side,
                f.won,
                f.duration_sec,
                SUM(sp.base_points) AS base_points_total,
                ROUND(SUM(sp.base_points * (ps.multiplier - 1.0)), 6) AS profile_bonus_points,
                ROUND(SUM(sp.base_points * ps.multiplier), 6) AS fantasy_score_raw,
                json_group_object(
                    ps.role_scope || ':' || ps.stat_name,
                    json_object(
                        'base_points', ROUND(sp.base_points, 4),
                        'multiplier', ROUND(ps.multiplier, 4),
                        'weighted_points', ROUND(sp.base_points * ps.multiplier, 4)
                    )
                ) AS selected_stat_scores_json,
                m.stage_name,
                m.stage_bucket,
                m.stage_bucket_label,
                m.is_group_stage_bucket,
                m.is_main_playoff,
                m.stage_sort
            FROM player_game_fantasy_summary f
            JOIN matches m
              ON m.match_id = f.match_id
            JOIN player_identity_registry pir
              ON pir.account_id = f.account_id
             AND pir.team_name = f.team_name
            JOIN fantasy_player_map_stat_points sp
              ON sp.match_id = f.match_id
             AND sp.account_id = f.account_id
             AND sp.team_name = f.team_name
            JOIN fantasy_scoring_profile_stats ps
              ON ps.profile_id = ?
             AND ps.enabled = 1
             AND ps.stat_name = sp.stat_name
             AND (
                    ps.role_scope = 'all'
                 OR ps.role_scope = {role_case}
                 OR ps.role_scope = 'pos' || CAST(pir.official_position AS TEXT)
             )
            GROUP BY
                f.match_id, f.match_date, f.series_id, f.league_id, f.account_id,
                f.team_name, f.opponent_name, pir.official_name, pir.official_position,
                f.hero_name, f.side, f.won, f.duration_sec,
                m.stage_name, m.stage_bucket, m.stage_bucket_label,
                m.is_group_stage_bucket, m.is_main_playoff, m.stage_sort
        ),
        series_context AS (
            SELECT
                m.match_id,
                m.series_id,
                ROW_NUMBER() OVER (
                    PARTITION BY COALESCE(CAST(m.series_id AS TEXT), 'match:' || CAST(m.match_id AS TEXT))
                    ORDER BY m.match_date, m.match_id
                ) AS map_number_in_series,
                CASE
                    WHEN LOWER(COALESCE(m.stage_name, '')) LIKE '%grand final%' THEN 5
                    WHEN m.series_id IS NULL THEN 1
                    ELSE 3
                END AS max_possible_maps
            FROM matches m
        ),
        title_candidates AS (
            SELECT
                s.match_id,
                s.account_id,
                s.team_name,
                t.title_slot,
                t.title_name,
                t.role_scope,
                t.bonus_pct,
                t.condition_metric,
                t.condition_operator,
                t.condition_value,
                {title_condition} AS triggered,
                CASE
                    WHEN {title_condition} = 1 THEN ROUND(s.fantasy_score_raw * (t.bonus_pct / 100.0), 6)
                    ELSE 0
                END AS bonus_points
            FROM selected_stats s
            JOIN player_game_fantasy_summary f
              ON f.match_id = s.match_id
             AND f.account_id = s.account_id
             AND f.team_name = s.team_name
            LEFT JOIN dota_heroes dh
              ON dh.hero_id = f.hero_id
            LEFT JOIN series_context sc
              ON sc.match_id = s.match_id
            JOIN fantasy_scoring_profile_titles t
              ON t.profile_id = ?
             AND t.enabled = 1
             AND (
                    t.role_scope = 'all'
                 OR t.role_scope = s.role_group
                 OR t.role_scope = 'pos' || CAST(s.official_position AS TEXT)
             )
        ),
        title_bonus AS (
            SELECT
                match_id,
                account_id,
                team_name,
                ROUND(SUM(bonus_points), 6) AS title_bonus_points,
                json_group_object(
                    title_slot || ':' || title_name,
                    json_object(
                        'role_scope', role_scope,
                        'bonus_pct', ROUND(bonus_pct, 4),
                        'condition_metric', condition_metric,
                        'condition_operator', condition_operator,
                        'condition_value', ROUND(condition_value, 4),
                        'triggered', triggered,
                        'bonus_points', ROUND(bonus_points, 4)
                    )
                ) AS title_scores_json
            FROM title_candidates
            GROUP BY match_id, account_id, team_name
        )
        SELECT
            ? AS profile_id,
            s.match_id,
            s.match_date,
            s.series_id,
            s.league_id,
            s.account_id,
            s.team_name,
            s.opponent_name,
            s.official_name,
            s.official_position,
            s.role_group,
            s.hero_name,
            s.side,
            s.won,
            s.duration_sec,
            ROUND(s.base_points_total, 2) AS base_points_total,
            ROUND(s.profile_bonus_points, 2) AS profile_bonus_points,
            ROUND(COALESCE(tb.title_bonus_points, 0), 2) AS title_bonus_points,
            ROUND(s.fantasy_score_raw + COALESCE(tb.title_bonus_points, 0), 2) AS fantasy_score,
            json_object(
                'base_points_total', ROUND(s.base_points_total, 4),
                'profile_bonus_points', ROUND(s.profile_bonus_points, 4),
                'title_bonus_points', ROUND(COALESCE(tb.title_bonus_points, 0), 4),
                'selected_stat_scores', json(COALESCE(s.selected_stat_scores_json, '{{}}')),
                'title_scores', json(COALESCE(tb.title_scores_json, '{{}}')),
                'formula', 'sum_selected_stat_points_plus_optional_title_bonus_by_official_role'
            ) AS score_breakdown_json,
            'recalculated_from_selected_stat_points_and_optional_titles' AS scoring_source,
            'official_liquipedia_roles' AS data_quality_note,
            s.stage_name,
            s.stage_bucket,
            s.stage_bucket_label,
            s.is_group_stage_bucket,
            s.is_main_playoff,
            s.stage_sort
        FROM selected_stats s
        LEFT JOIN title_bonus tb
          ON tb.match_id = s.match_id
         AND tb.account_id = s.account_id
         AND tb.team_name = s.team_name
        """,
        (profile_id, profile_id, profile_id),
    )

    cur.execute("DELETE FROM fantasy_team_role_map_scores WHERE profile_id = ?", (profile_id,))
    cur.execute(
        """
        INSERT OR REPLACE INTO fantasy_team_role_map_scores(
            profile_id, match_id, match_date, team_name, opponent_name, role_category,
            included_positions, players_count, player_names, account_ids, hero_names,
            role_category_fantasy_score, stored_player_scores_sum, aggregation_method,
            data_quality_note, stage_name, stage_bucket, stage_bucket_label,
            is_group_stage_bucket, is_main_playoff, stage_sort
        )
        WITH base AS (
            SELECT
                *,
                CASE
                    WHEN official_position IN (1, 3) THEN 'core_avg'
                    WHEN official_position = 2 THEN 'mid'
                    WHEN official_position IN (4, 5) THEN 'support_avg'
                END AS role_category
            FROM fantasy_player_map_scores
            WHERE profile_id = ?
              AND official_position BETWEEN 1 AND 5
        )
        SELECT
            profile_id,
            match_id,
            match_date,
            team_name,
            opponent_name,
            role_category,
            GROUP_CONCAT(DISTINCT CAST(official_position AS TEXT)) AS included_positions,
            COUNT(*) AS players_count,
            GROUP_CONCAT(official_name, ', ') AS player_names,
            GROUP_CONCAT(CAST(account_id AS TEXT), ', ') AS account_ids,
            GROUP_CONCAT(COALESCE(hero_name, ''), ', ') AS hero_names,
            ROUND(AVG(fantasy_score), 2) AS role_category_fantasy_score,
            ROUND(SUM(fantasy_score), 2) AS stored_player_scores_sum,
            CASE
                WHEN role_category = 'mid' THEN 'single_official_pos2'
                WHEN role_category = 'core_avg' THEN 'average_official_pos1_pos3'
                WHEN role_category = 'support_avg' THEN 'average_official_pos4_pos5'
            END AS aggregation_method,
            CASE
                WHEN role_category = 'mid' AND COUNT(*) = 1 THEN 'complete_official_positions'
                WHEN role_category IN ('core_avg', 'support_avg') AND COUNT(*) = 2 THEN 'complete_official_positions'
                ELSE 'incomplete_role_category_players'
            END AS data_quality_note,
            MAX(stage_name),
            MAX(stage_bucket),
            MAX(stage_bucket_label),
            MAX(is_group_stage_bucket),
            MAX(is_main_playoff),
            MAX(stage_sort)
        FROM base
        GROUP BY profile_id, match_id, match_date, team_name, opponent_name, role_category
        """,
        (profile_id,),
    )

    cur.execute("DELETE FROM fantasy_pick_value WHERE profile_id = ?", (profile_id,))
    cur.execute(
        """
        INSERT OR REPLACE INTO fantasy_pick_value(
            profile_id, account_id, team_name, official_name, official_position,
            role_group, maps_seen, total_fantasy_score, avg_score, best_score,
            floor_score, avg_abs_deviation, consistency_score, ceiling_score,
            pick_value_score
        )
        WITH player_avg AS (
            SELECT
                profile_id,
                account_id,
                team_name,
                official_name,
                official_position,
                role_group,
                COUNT(*) AS maps_seen,
                ROUND(SUM(fantasy_score), 2) AS total_fantasy_score,
                AVG(fantasy_score) AS avg_score,
                MAX(fantasy_score) AS best_score,
                MIN(fantasy_score) AS floor_score
            FROM fantasy_player_map_scores
            WHERE profile_id = ?
            GROUP BY profile_id, account_id, team_name, official_name, official_position, role_group
        ),
        deviation AS (
            SELECT
                s.profile_id,
                s.account_id,
                s.team_name,
                AVG(ABS(s.fantasy_score - a.avg_score)) AS avg_abs_deviation
            FROM fantasy_player_map_scores s
            JOIN player_avg a
              ON a.profile_id = s.profile_id
             AND a.account_id = s.account_id
             AND a.team_name = s.team_name
            GROUP BY s.profile_id, s.account_id, s.team_name
        )
        SELECT
            a.profile_id,
            a.account_id,
            a.team_name,
            a.official_name,
            a.official_position,
            a.role_group,
            a.maps_seen,
            a.total_fantasy_score,
            ROUND(a.avg_score, 2) AS avg_score,
            ROUND(a.best_score, 2) AS best_score,
            ROUND(a.floor_score, 2) AS floor_score,
            ROUND(d.avg_abs_deviation, 2) AS avg_abs_deviation,
            ROUND(10000.0 / (100.0 + COALESCE(d.avg_abs_deviation, 0)), 2) AS consistency_score,
            ROUND(a.best_score - a.avg_score, 2) AS ceiling_score,
            ROUND(
                0.50 * a.avg_score
              + 0.30 * a.best_score
              + 0.20 * a.floor_score
              - 0.15 * COALESCE(d.avg_abs_deviation, 0),
                2
            ) AS pick_value_score
        FROM player_avg a
        JOIN deviation d
          ON d.profile_id = a.profile_id
         AND d.account_id = a.account_id
         AND d.team_name = a.team_name
        """,
        (profile_id,),
    )


EXAMPLE_BANNER_SPEC = {
    "core": [
        ("kills", 2.5),
        ("creep_score", 2.5),
        ("teamfight_participation", 1.8),
    ],
    "mid": [
        ("creep_score", 2.7),
        ("runes_grabbed", 1.8),
        ("teamfight_participation", 2.7),
    ],
    "support": [
        ("lotus", 3.2),
        ("watchers_taken", 2.1),
        ("teamfight_participation", 1.5),
    ],
}


def create_example_profile(db_path: Path = DB_PATH) -> str:
    con = sqlite3.connect(db_path)
    profile_id = create_or_replace_banner_profile(
        con,
        "example_constructor_same_as_current",
        EXAMPLE_BANNER_SPEC,
        profile_name="Example profile from constructor",
        description="Validation profile generated by the reusable fantasy banner constructor.",
        set_default=False,
        commit=True,
    )
    con.close()
    return profile_id


if __name__ == "__main__":
    created = create_example_profile()
    print(json.dumps({"created_profile_id": created}, ensure_ascii=False, indent=2))
