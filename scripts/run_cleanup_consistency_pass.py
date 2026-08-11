from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "ewc_2026_fantasy_compact.sqlite"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the post-backfill database cleanup and consistency pass.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    return parser.parse_args()


def sync_summary_backfill_columns(connection: sqlite3.Connection) -> None:
    stat_column_map = [
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
    cur = connection.cursor()
    for stat_name, raw_col, points_col in stat_column_map:
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
    cur.execute(
        """
        UPDATE player_game_fantasy_summary
        SET score_from_runes = ROUND(COALESCE(runes_grabbed_points, 0) * COALESCE(multiplier_runes_grabbed, 0), 6),
            score_from_watchers = ROUND(COALESCE(watchers_taken_points, 0) * COALESCE(multiplier_watchers_taken, 0), 6),
            score_from_lotuses = ROUND(COALESCE(lotus_points, 0) * COALESCE(multiplier_lotus, 0), 6)
        """
    )


def sync_default_profile_score_to_summary(connection: sqlite3.Connection) -> None:
    cur = connection.cursor()
    default_profile_id = cur.execute(
        "SELECT profile_id FROM fantasy_scoring_profiles WHERE is_default = 1 ORDER BY profile_id LIMIT 1"
    ).fetchone()
    if not default_profile_id:
        raise RuntimeError("No default fantasy scoring profile found.")
    profile_id = default_profile_id[0]
    cur.execute("UPDATE player_game_fantasy_summary SET player_map_fantasy_score = 0")
    cur.execute(
        """
        UPDATE player_game_fantasy_summary
        SET player_map_fantasy_score = (
                SELECT fps.fantasy_score
                FROM fantasy_player_map_scores fps
                WHERE fps.profile_id = ?
                  AND fps.match_id = player_game_fantasy_summary.match_id
                  AND fps.account_id = player_game_fantasy_summary.account_id
                  AND fps.team_name = player_game_fantasy_summary.team_name
            ),
            scoring_version = ?,
            data_quality_note = 'player_map_fantasy_score synced to default profile layer'
        WHERE EXISTS (
            SELECT 1
            FROM fantasy_player_map_scores fps
            WHERE fps.profile_id = ?
              AND fps.match_id = player_game_fantasy_summary.match_id
              AND fps.account_id = player_game_fantasy_summary.account_id
              AND fps.team_name = player_game_fantasy_summary.team_name
        )
        """,
        (profile_id, f"default_profile_sync:{profile_id}", profile_id),
    )


def sync_registry_score_aggregates(connection: sqlite3.Connection) -> None:
    cur = connection.cursor()
    default_profile_id = cur.execute(
        "SELECT profile_id FROM fantasy_scoring_profiles WHERE is_default = 1 ORDER BY profile_id LIMIT 1"
    ).fetchone()[0]
    cur.execute(
        """
        UPDATE player_identity_registry
        SET avg_fantasy_score = (
                SELECT ROUND(AVG(fps.fantasy_score), 2)
                FROM fantasy_player_map_scores fps
                WHERE fps.profile_id = ?
                  AND fps.account_id = player_identity_registry.account_id
                  AND fps.team_name = player_identity_registry.team_name
            ),
            best_map_fantasy_score = (
                SELECT ROUND(MAX(fps.fantasy_score), 2)
                FROM fantasy_player_map_scores fps
                WHERE fps.profile_id = ?
                  AND fps.account_id = player_identity_registry.account_id
                  AND fps.team_name = player_identity_registry.team_name
            )
        """,
        (default_profile_id, default_profile_id),
    )


def fill_player_match_stats_hero_name(connection: sqlite3.Connection) -> None:
    cur = connection.cursor()
    cur.execute(
        """
        UPDATE player_match_stats
        SET hero_name = (
                SELECT COALESCE(pg.hero_name, dh.localized_name)
                FROM player_game_fantasy_summary pg
                LEFT JOIN dota_heroes dh
                  ON dh.hero_id = player_match_stats.hero_id
                WHERE pg.match_id = player_match_stats.match_id
                  AND pg.account_id = player_match_stats.account_id
                  AND pg.team_name = player_match_stats.team_name
                LIMIT 1
            )
        WHERE hero_name IS NULL
        """
    )
    cur.execute(
        """
        UPDATE player_match_stats
        SET hero_name = (
                SELECT localized_name
                FROM dota_heroes dh
                WHERE dh.hero_id = player_match_stats.hero_id
            )
        WHERE hero_name IS NULL
        """
    )


def update_stat_catalog_status(connection: sqlite3.Connection) -> None:
    cur = connection.cursor()
    cur.execute(
        """
        UPDATE fantasy_scoring_stat_catalog
        SET coverage_status = CASE stat_name
            WHEN 'wards_placed' THEN 'filled_backfill'
            WHEN 'camps_stacked' THEN 'filled_backfill'
            WHEN 'runes_grabbed' THEN 'filled_backfill'
            WHEN 'roshan_kills' THEN 'filled_backfill'
            WHEN 'stuns' THEN 'filled_backfill'
            WHEN 'courier_kills' THEN 'filled_backfill'
            WHEN 'first_blood' THEN 'filled_backfill'
            WHEN 'smokes_used' THEN 'filled_backfill'
            WHEN 'tormentor_kills' THEN 'filled_approximation'
            WHEN 'watchers_taken' THEN 'source_needed'
            WHEN 'lotus' THEN 'source_needed'
            WHEN 'kills' THEN 'filled_existing'
            WHEN 'deaths' THEN 'filled_existing'
            WHEN 'creep_score' THEN 'filled_existing'
            WHEN 'gpm' THEN 'filled_existing'
            WHEN 'teamfight_participation' THEN 'filled_existing'
            ELSE coverage_status
        END
        """
    )


def rebuild_player_map_role_category_stats_view(connection: sqlite3.Connection) -> None:
    view_sql = Path(PROJECT_ROOT / "scripts" / "refresh_role_category_stats_view.py").read_text(encoding="utf-8")
    marker = 'VIEW_SQL = """'
    start = view_sql.index(marker) + len(marker)
    end = view_sql.index('"""', start)
    sql = view_sql[start:end]
    cur = connection.cursor()
    cur.execute("DROP VIEW IF EXISTS player_map_role_category_stats")
    cur.execute("DROP TABLE IF EXISTS player_map_role_category_stats")
    cur.execute(sql)


def write_cleanup_metadata(connection: sqlite3.Connection) -> None:
    cur = connection.cursor()
    cur.executemany(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
        [
            ("cleanup_consistency_pass", "completed"),
            ("cleanup_consistency_pass_utc", cur.execute("SELECT datetime('now')").fetchone()[0]),
            ("player_map_role_category_stats_object_type", "view"),
            ("player_map_fantasy_score_source", "fantasy_player_map_scores.default_profile"),
        ],
    )


def collect_summary(connection: sqlite3.Connection) -> dict[str, object]:
    cur = connection.cursor()
    return {
        "hero_name_filled_rows": cur.execute("SELECT SUM(CASE WHEN hero_name IS NOT NULL THEN 1 ELSE 0 END) FROM player_match_stats").fetchone()[0],
        "summary_nonzero_wards": cur.execute("SELECT SUM(CASE WHEN COALESCE(observer_wards_placed,0)<>0 THEN 1 ELSE 0 END) FROM player_game_fantasy_summary").fetchone()[0],
        "summary_nonzero_stuns": cur.execute("SELECT SUM(CASE WHEN COALESCE(stuns_sec,0)<>0 THEN 1 ELSE 0 END) FROM player_game_fantasy_summary").fetchone()[0],
        "summary_nonzero_tormentor": cur.execute("SELECT SUM(CASE WHEN COALESCE(tormentor_kills,0)<>0 THEN 1 ELSE 0 END) FROM player_game_fantasy_summary").fetchone()[0],
        "role_category_object_type": cur.execute("SELECT type FROM sqlite_master WHERE name='player_map_role_category_stats'").fetchone()[0],
        "registry_avg_score_nonnull": cur.execute("SELECT SUM(CASE WHEN avg_fantasy_score IS NOT NULL THEN 1 ELSE 0 END) FROM player_identity_registry").fetchone()[0],
    }


def main() -> None:
    args = parse_args()
    db_path = Path(args.db_path).resolve()
    connection = sqlite3.connect(db_path)
    try:
        sync_summary_backfill_columns(connection)
        sync_default_profile_score_to_summary(connection)
        sync_registry_score_aggregates(connection)
        fill_player_match_stats_hero_name(connection)
        update_stat_catalog_status(connection)
        rebuild_player_map_role_category_stats_view(connection)
        write_cleanup_metadata(connection)
        connection.commit()
        summary = collect_summary(connection)
    finally:
        connection.close()
    print(json.dumps({"db_path": str(db_path), "summary": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
