from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def resolve_db_path(project_root: Path = PROJECT_ROOT) -> Path:
    candidates = [
        project_root / "data" / "ewc_2026_fantasy_compact.sqlite",
        project_root / "data" / "db" / "ewc_2026_fantasy_compact.sqlite",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


DB_PATH = resolve_db_path()

VALID_ROLE_SCOPES = {"core", "mid", "support", "all", "pos1", "pos2", "pos3", "pos4", "pos5"}


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


def create_or_replace_banner_profile(
    connection: sqlite3.Connection,
    profile_id: str,
    banner_spec: dict[str, list[dict[str, Any] | tuple[str, float]]],
    *,
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

    recalculate_profile_scores(connection, profile_id)
    if commit:
        connection.commit()
    return profile_id


def recalculate_profile_scores(connection: sqlite3.Connection, profile_id: str) -> None:
    cur = connection.cursor()
    role_case = role_case_sql("pir")

    cur.execute("DELETE FROM fantasy_player_map_scores WHERE profile_id = ?", (profile_id,))
    cur.execute(
        f"""
        INSERT OR REPLACE INTO fantasy_player_map_scores(
            profile_id, match_id, match_date, series_id, league_id, account_id,
            team_name, opponent_name, official_name, official_position, role_group,
            hero_name, side, won, duration_sec, base_points_total, profile_bonus_points,
            fantasy_score, score_breakdown_json, scoring_source, data_quality_note,
            stage_name, stage_bucket, stage_bucket_label, is_group_stage_bucket,
            is_main_playoff, stage_sort
        )
        WITH player_base AS (
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
            GROUP BY
                f.match_id, f.match_date, f.series_id, f.league_id, f.account_id,
                f.team_name, f.opponent_name, pir.official_name, pir.official_position,
                f.hero_name, f.side, f.won, f.duration_sec,
                m.stage_name, m.stage_bucket, m.stage_bucket_label,
                m.is_group_stage_bucket, m.is_main_playoff, m.stage_sort
        ),
        profile_bonus AS (
            SELECT
                f.match_id,
                f.account_id,
                f.team_name,
                ROUND(SUM(sp.base_points * (ps.multiplier - 1.0)), 6) AS profile_bonus_points,
                json_group_object(
                    ps.role_scope || ':' || ps.stat_name,
                    ROUND(sp.base_points * ps.multiplier, 4)
                ) AS selected_stat_scores_json
            FROM player_game_fantasy_summary f
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
            GROUP BY f.match_id, f.account_id, f.team_name
        )
        SELECT
            ? AS profile_id,
            b.match_id,
            b.match_date,
            b.series_id,
            b.league_id,
            b.account_id,
            b.team_name,
            b.opponent_name,
            b.official_name,
            b.official_position,
            b.role_group,
            b.hero_name,
            b.side,
            b.won,
            b.duration_sec,
            ROUND(b.base_points_total, 2) AS base_points_total,
            ROUND(COALESCE(pb.profile_bonus_points, 0), 2) AS profile_bonus_points,
            ROUND(b.base_points_total + COALESCE(pb.profile_bonus_points, 0), 2) AS fantasy_score,
            json_object(
                'base_points_total', ROUND(b.base_points_total, 4),
                'profile_bonus_points', ROUND(COALESCE(pb.profile_bonus_points, 0), 4),
                'selected_stat_scores', COALESCE(pb.selected_stat_scores_json, '{{}}'),
                'formula', 'sum_all_base_points_plus_selected_stat_bonus_by_official_role'
            ) AS score_breakdown_json,
            'recalculated_from_stat_points_and_profile_constructor' AS scoring_source,
            'official_liquipedia_roles' AS data_quality_note,
            b.stage_name,
            b.stage_bucket,
            b.stage_bucket_label,
            b.is_group_stage_bucket,
            b.is_main_playoff,
            b.stage_sort
        FROM player_base b
        LEFT JOIN profile_bonus pb
          ON pb.match_id = b.match_id
         AND pb.account_id = b.account_id
         AND pb.team_name = b.team_name
        """,
        (profile_id, profile_id),
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
