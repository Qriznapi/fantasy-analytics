from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "ewc_2026_fantasy_compact.sqlite"


VIEW_SQL = """
CREATE VIEW player_map_role_category_stats AS
WITH default_profile AS (
    SELECT profile_id
    FROM fantasy_scoring_profiles
    WHERE is_default = 1
    ORDER BY profile_id
    LIMIT 1
),
base AS (
    SELECT
        pg.match_id,
        pg.match_date,
        pg.series_id,
        pg.league_id,
        pg.team_name,
        pg.opponent_name,
        pg.side,
        pg.won,
        pg.duration_sec,
        CASE
            WHEN pir.official_position IN (1, 3) THEN 'core_avg'
            WHEN pir.official_position = 2 THEN 'mid'
            WHEN pir.official_position IN (4, 5) THEN 'support_avg'
        END AS role_category,
        CASE
            WHEN pir.official_position IN (1, 3) THEN 'Average of official pos1 and pos3'
            WHEN pir.official_position = 2 THEN 'Official pos2 mid'
            WHEN pir.official_position IN (4, 5) THEN 'Average of official pos4 and pos5'
        END AS role_category_label,
        pir.official_position,
        pir.official_name,
        pg.account_id,
        pg.hero_name,
        pg.kills,
        pg.deaths,
        pg.assists,
        pg.last_hits,
        pg.denies,
        pg.creep_score,
        pg.gpm,
        pg.xpm,
        pg.observer_wards_placed,
        pg.camps_stacked,
        pg.runes_grabbed,
        pg.watchers_taken,
        pg.lotus_units,
        pg.roshan_kills,
        pg.tormentor_kills,
        pg.courier_kills,
        pg.first_blood,
        pg.stuns_sec,
        pg.smokes_used,
        pg.team_kills,
        pg.teamfight_participation_ratio,
        pg.kills_points,
        pg.deaths_points,
        pg.creep_score_points,
        pg.gpm_points,
        pg.wards_points,
        pg.camps_stacked_points,
        pg.runes_grabbed_points,
        pg.watchers_taken_points,
        pg.lotus_points,
        pg.roshan_points,
        pg.teamfight_participation_points,
        pg.stuns_points,
        pg.tormentor_points,
        pg.courier_points,
        pg.first_blood_points,
        pg.smokes_points,
        pg.score_from_kills,
        pg.score_from_creep_score,
        pg.score_from_runes,
        pg.score_from_watchers,
        pg.score_from_lotuses,
        pg.score_from_teamfight,
        COALESCE(fps.fantasy_score, 0) AS current_profile_fantasy_score,
        pir.confidence_score,
        pir.confidence_label,
        pg.source_dotabuff_url,
        pg.stage_name,
        pg.stage_bucket,
        pg.stage_bucket_label,
        pg.is_group_stage_bucket,
        pg.is_main_playoff,
        pg.stage_sort,
        dp.profile_id AS default_profile_id
    FROM player_game_fantasy_summary pg
    JOIN player_identity_registry pir
      ON pir.account_id = pg.account_id
     AND pir.team_name = pg.team_name
    CROSS JOIN default_profile dp
    LEFT JOIN fantasy_player_map_scores fps
      ON fps.profile_id = dp.profile_id
     AND fps.match_id = pg.match_id
     AND fps.account_id = pg.account_id
     AND fps.team_name = pg.team_name
    WHERE pir.official_position BETWEEN 1 AND 5
)
SELECT
    match_id,
    match_date,
    series_id,
    league_id,
    team_name,
    opponent_name,
    side,
    won,
    duration_sec,
    role_category,
    MAX(role_category_label) AS role_category_label,
    GROUP_CONCAT(DISTINCT CAST(official_position AS TEXT)) AS included_positions,
    COUNT(*) AS players_count,
    GROUP_CONCAT(official_name, ', ') AS player_names,
    GROUP_CONCAT(CAST(account_id AS TEXT), ', ') AS account_ids,
    GROUP_CONCAT(COALESCE(hero_name, ''), ', ') AS hero_names,
    ROUND(AVG(kills), 4) AS kills,
    ROUND(AVG(deaths), 4) AS deaths,
    ROUND(AVG(assists), 4) AS assists,
    ROUND(AVG(last_hits), 4) AS last_hits,
    ROUND(AVG(denies), 4) AS denies,
    ROUND(AVG(creep_score), 4) AS creep_score,
    ROUND(AVG(gpm), 4) AS gpm,
    ROUND(AVG(xpm), 4) AS xpm,
    ROUND(AVG(observer_wards_placed), 4) AS observer_wards_placed,
    ROUND(AVG(camps_stacked), 4) AS camps_stacked,
    ROUND(AVG(runes_grabbed), 4) AS runes_grabbed,
    ROUND(AVG(watchers_taken), 4) AS watchers_taken,
    ROUND(AVG(lotus_units), 4) AS lotus_units,
    ROUND(AVG(roshan_kills), 4) AS roshan_kills,
    ROUND(AVG(tormentor_kills), 4) AS tormentor_kills,
    ROUND(AVG(courier_kills), 4) AS courier_kills,
    ROUND(AVG(first_blood), 4) AS first_blood,
    ROUND(AVG(stuns_sec), 4) AS stuns_sec,
    ROUND(AVG(smokes_used), 4) AS smokes_used,
    ROUND(AVG(team_kills), 4) AS team_kills,
    ROUND(AVG(teamfight_participation_ratio), 4) AS teamfight_participation_ratio,
    ROUND(AVG(kills_points), 4) AS kills_points,
    ROUND(AVG(deaths_points), 4) AS deaths_points,
    ROUND(AVG(creep_score_points), 4) AS creep_score_points,
    ROUND(AVG(gpm_points), 4) AS gpm_points,
    ROUND(AVG(wards_points), 4) AS wards_points,
    ROUND(AVG(camps_stacked_points), 4) AS camps_stacked_points,
    ROUND(AVG(runes_grabbed_points), 4) AS runes_grabbed_points,
    ROUND(AVG(watchers_taken_points), 4) AS watchers_taken_points,
    ROUND(AVG(lotus_points), 4) AS lotus_points,
    ROUND(AVG(roshan_points), 4) AS roshan_points,
    ROUND(AVG(teamfight_participation_points), 4) AS teamfight_participation_points,
    ROUND(AVG(stuns_points), 4) AS stuns_points,
    ROUND(AVG(tormentor_points), 4) AS tormentor_points,
    ROUND(AVG(courier_points), 4) AS courier_points,
    ROUND(AVG(first_blood_points), 4) AS first_blood_points,
    ROUND(AVG(smokes_points), 4) AS smokes_points,
    ROUND(AVG(score_from_kills), 4) AS score_from_kills,
    ROUND(AVG(score_from_creep_score), 4) AS score_from_creep_score,
    ROUND(AVG(score_from_runes), 4) AS score_from_runes,
    ROUND(AVG(score_from_watchers), 4) AS score_from_watchers,
    ROUND(AVG(score_from_lotuses), 4) AS score_from_lotuses,
    ROUND(AVG(score_from_teamfight), 4) AS score_from_teamfight,
    ROUND(AVG(current_profile_fantasy_score), 4) AS role_category_fantasy_score,
    ROUND(SUM(current_profile_fantasy_score), 4) AS stored_player_scores_sum,
    ROUND(AVG(current_profile_fantasy_score), 4) AS stored_player_scores_avg,
    ROUND(MIN(confidence_score), 4) AS min_identity_confidence,
    GROUP_CONCAT(DISTINCT confidence_label) AS confidence_labels,
    CASE
        WHEN role_category = 'mid' THEN 'single_official_pos2'
        WHEN role_category = 'core_avg' THEN 'average_official_pos1_pos3'
        WHEN role_category = 'support_avg' THEN 'average_official_pos4_pos5'
    END AS aggregation_method,
    'official_position_complete_team_map' AS position_resolution_method,
    'current_default_profile_view_v1' AS scoring_version,
    MAX(source_dotabuff_url) AS source_dotabuff_url,
    CASE
        WHEN role_category = 'mid' AND COUNT(*) = 1 THEN 'complete_official_positions'
        WHEN role_category IN ('core_avg', 'support_avg') AND COUNT(*) = 2 THEN 'complete_official_positions'
        ELSE 'incomplete_role_category_players'
    END AS data_quality_note,
    datetime('now') AS created_at_utc,
    MAX(stage_name) AS stage_name,
    MAX(stage_bucket) AS stage_bucket,
    MAX(stage_bucket_label) AS stage_bucket_label,
    MAX(is_group_stage_bucket) AS is_group_stage_bucket,
    MAX(is_main_playoff) AS is_main_playoff,
    MAX(stage_sort) AS stage_sort
FROM base
GROUP BY
    match_id,
    match_date,
    series_id,
    league_id,
    team_name,
    opponent_name,
    side,
    won,
    duration_sec,
    role_category
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replace stale player_map_role_category_stats table with a current view.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    return parser.parse_args()


def rebuild_view(connection: sqlite3.Connection) -> None:
    cur = connection.cursor()
    cur.execute("DROP TABLE IF EXISTS player_map_role_category_stats")
    cur.execute("DROP VIEW IF EXISTS player_map_role_category_stats")
    cur.execute(VIEW_SQL)
    connection.commit()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db_path).resolve()
    connection = sqlite3.connect(db_path)
    try:
        rebuild_view(connection)
    finally:
        connection.close()
    print(f"recreated player_map_role_category_stats as view in {db_path}")


if __name__ == "__main__":
    main()
