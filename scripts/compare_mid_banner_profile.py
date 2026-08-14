from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_profile_constructor import EXAMPLE_BANNER_SPEC, create_or_replace_banner_profile  # noqa: E402


DB_PATH = PROJECT_ROOT / "data" / "ewc_2026_fantasy_compact.sqlite"
PROFILE_ID = "example_constructor_same_as_current"
MID_NAMES = ("Nisha", "bzm")


def build_profile(con: sqlite3.Connection) -> str:
    return create_or_replace_banner_profile(
        con,
        PROFILE_ID,
        EXAMPLE_BANNER_SPEC,
        profile_name="Example profile from constructor",
        description="Current notebook banner profile",
        set_default=False,
        commit=True,
    )


def query_df(con: sqlite3.Connection, sql: str, params: tuple | list = ()) -> pd.DataFrame:
    return pd.read_sql_query(sql, con, params=params)


def main() -> None:
    con = sqlite3.connect(DB_PATH)
    try:
        profile_id = build_profile(con)
        print(f"profile_id={profile_id}")

        pick_value = query_df(
            con,
            """
            SELECT official_name, team_name, official_position, maps_seen,
                   total_fantasy_score, avg_score, best_score, floor_score,
                   avg_abs_deviation, consistency_score, ceiling_score, pick_value_score
            FROM fantasy_pick_value
            WHERE profile_id = ?
              AND official_name IN (?, ?)
            ORDER BY official_name
            """,
            (profile_id, *MID_NAMES),
        )
        print("\n[pick_value]")
        print(pick_value.to_string(index=False))

        series_compare = query_df(
            con,
            """
            WITH series_scores AS (
                SELECT profile_id, official_name, team_name,
                       COALESCE(CAST(series_id AS TEXT), 'match:' || CAST(match_id AS TEXT)) AS series_key,
                       fantasy_score,
                       ROW_NUMBER() OVER (
                           PARTITION BY profile_id, official_name, team_name, COALESCE(CAST(series_id AS TEXT), 'match:' || CAST(match_id AS TEXT))
                           ORDER BY fantasy_score DESC, match_id DESC
                       ) AS rn
                FROM fantasy_player_map_scores
                WHERE profile_id = ?
                  AND official_name IN (?, ?)
            )
            SELECT official_name, team_name,
                   COUNT(DISTINCT series_key) AS series_seen,
                   ROUND(AVG(fantasy_score), 2) AS avg_map_score,
                   ROUND(AVG(CASE WHEN rn <= 2 THEN fantasy_score END), 2) AS avg_top2_map_score,
                   ROUND(MAX(CASE WHEN rn = 1 THEN fantasy_score END), 2) AS best_series_top1,
                   ROUND(MAX(CASE WHEN rn <= 2 THEN fantasy_score END), 2) AS best_map_inside_series
            FROM series_scores
            GROUP BY official_name, team_name
            ORDER BY official_name
            """,
            (profile_id, *MID_NAMES),
        )
        print("\n[series_compare]")
        print(series_compare.to_string(index=False))

        stat_compare = query_df(
            con,
            """
            SELECT m.official_name, m.team_name, sp.stat_name,
                   ROUND(AVG(sp.base_points), 2) AS avg_base_points,
                   ROUND(MAX(sp.base_points), 2) AS max_base_points,
                   ROUND(AVG(sp.base_points * ps.multiplier), 2) AS avg_weighted_points,
                   ROUND(MAX(sp.base_points * ps.multiplier), 2) AS max_weighted_points,
                   COUNT(*) AS maps
            FROM fantasy_player_map_scores m
            JOIN fantasy_player_map_stat_points sp
              ON sp.match_id = m.match_id
             AND sp.account_id = m.account_id
             AND sp.team_name = m.team_name
            JOIN fantasy_scoring_profile_stats ps
              ON ps.profile_id = m.profile_id
             AND ps.stat_name = sp.stat_name
             AND ps.role_scope = 'mid'
            WHERE m.profile_id = ?
              AND m.official_name IN (?, ?)
              AND sp.stat_name IN ('creep_score', 'runes_grabbed', 'teamfight_participation')
            GROUP BY m.official_name, m.team_name, sp.stat_name
            ORDER BY m.official_name, sp.stat_name
            """,
            (profile_id, *MID_NAMES),
        )
        print("\n[stat_compare]")
        print(stat_compare.to_string(index=False))

        top_maps = query_df(
            con,
            """
            SELECT official_name, team_name, match_id, match_date, stage_name, hero_name, fantasy_score, score_breakdown_json
            FROM fantasy_player_map_scores
            WHERE profile_id = ?
              AND official_name IN (?, ?)
            ORDER BY official_name, fantasy_score DESC
            LIMIT 12
            """,
            (profile_id, *MID_NAMES),
        )
        print("\n[top_maps]")
        for _, row in top_maps.iterrows():
            print(
                row["official_name"],
                row["team_name"],
                int(row["match_id"]),
                row["match_date"],
                row["stage_name"],
                row["hero_name"],
                float(row["fantasy_score"]),
            )
            print(row["score_breakdown_json"])

        layers = {
            "foundation": """
                SELECT official_name, team_name, sample_maps, sample_series,
                       map_mean_score, map_p75_score, series_mean_p75, series_top1_p75,
                       reliability_score_1_100, low_estimate, expected_estimate, high_estimate,
                       stat_balance_score, volatility_ratio, confidence_label
                FROM analytics_reliable_players_foundation
                WHERE official_name IN (?, ?)
                ORDER BY official_name
            """,
            "optimizer_v2_ti2026": """
                SELECT official_name, team_name, optimizer_v2_score_1_100, optimizer_v2_raw_score,
                       series_top1_p75, series_mean_p75, map_p75_score,
                       top_stat_share, volatility_ratio, sample_weight
                FROM analytics_optimizer_v2_players
                WHERE optimizer_scope = 'ti2026'
                  AND official_name IN (?, ?)
                ORDER BY official_name
            """,
            "rescoring_ti2026": """
                SELECT official_name, team_name, rescore_score_1_100,
                       predicted_anchor_score, p90_anchor_score,
                       p_top1_anchor, p_top3_anchor, p_top5_anchor,
                       expected_rank_anchor, stability_index, rank_strength_index, surface_quality_index
                FROM analytics_banner_rescoring_players
                WHERE rescoring_scope = 'ti2026'
                  AND official_name IN (?, ?)
                ORDER BY official_name
            """,
            "decision_balanced_ti2026": """
                SELECT official_name, team_name, decision_score_1_100, decision_raw, rationale
                FROM analytics_banner_decision_players
                WHERE decision_scope = 'ti2026'
                  AND risk_profile = 'balanced'
                  AND official_name IN (?, ?)
                ORDER BY official_name
            """,
            "decision_aggressive_ti2026": """
                SELECT official_name, team_name, decision_score_1_100, decision_raw, rationale
                FROM analytics_banner_decision_players
                WHERE decision_scope = 'ti2026'
                  AND risk_profile = 'aggressive'
                  AND official_name IN (?, ?)
                ORDER BY official_name
            """,
            "decision_conservative_ti2026": """
                SELECT official_name, team_name, decision_score_1_100, decision_raw, rationale
                FROM analytics_banner_decision_players
                WHERE decision_scope = 'ti2026'
                  AND risk_profile = 'conservative'
                  AND official_name IN (?, ?)
                ORDER BY official_name
            """,
            "mc_series_mean_temporal": """
                SELECT official_name, team_name, predicted_score, p_top1, p_top3, p_top5,
                       expected_rank, simulated_std_score, p90_sim_score
                FROM analytics_prediction_monte_carlo_players
                WHERE target_id = 'player_series_mean'
                  AND split_name = 'temporal_60_40'
                  AND official_name IN (?, ?)
                ORDER BY official_name
            """,
            "mc_series_top1_temporal": """
                SELECT official_name, team_name, predicted_score, p_top1, p_top3, p_top5,
                       expected_rank, simulated_std_score, p90_sim_score
                FROM analytics_prediction_monte_carlo_players
                WHERE target_id = 'player_series_top1'
                  AND split_name = 'temporal_60_40'
                  AND official_name IN (?, ?)
                ORDER BY official_name
            """,
        }
        for layer_name, sql in layers.items():
            df = query_df(con, sql, MID_NAMES)
            print(f"\n[{layer_name}]")
            print(df.to_string(index=False))
    finally:
        con.close()


if __name__ == "__main__":
    main()
