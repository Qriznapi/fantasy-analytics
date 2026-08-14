from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from fantasy_prediction_foundation import DB_PATH, default_profile_id, percentile, safe_float, spearman_corr


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def pearson_corr(left: pd.Series, right: pd.Series) -> float:
    if len(left) < 2 or len(right) < 2:
        return 0.0
    if left.nunique(dropna=False) <= 1 or right.nunique(dropna=False) <= 1:
        return 0.0
    corr = left.astype(float).corr(right.astype(float), method="pearson")
    if pd.isna(corr):
        return 0.0
    return float(corr)


def positive_p75(values: pd.Series) -> float:
    positive = [safe_float(v) for v in values.tolist() if safe_float(v) > 1e-9]
    if not positive:
        return float("inf")
    return percentile(positive, 0.75)


def create_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS stat_signal_summary (
            profile_id TEXT NOT NULL,
            scope_type TEXT NOT NULL,
            scope_key TEXT NOT NULL,
            population_scope TEXT NOT NULL,
            stat_name TEXT NOT NULL,
            observations INTEGER NOT NULL,
            mean_x1 REAL NOT NULL,
            p75_x1 REAL NOT NULL,
            p90_x1 REAL NOT NULL,
            max_x1 REAL NOT NULL,
            std_x1 REAL NOT NULL,
            nonzero_share REAL NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (profile_id, scope_type, scope_key, population_scope, stat_name)
        );

        CREATE TABLE IF NOT EXISTS stat_synergy_matrix (
            profile_id TEXT NOT NULL,
            scope_type TEXT NOT NULL,
            scope_key TEXT NOT NULL,
            population_scope TEXT NOT NULL,
            stat_left TEXT NOT NULL,
            stat_right TEXT NOT NULL,
            observations INTEGER NOT NULL,
            left_nonzero_share REAL NOT NULL,
            right_nonzero_share REAL NOT NULL,
            both_nonzero_share REAL NOT NULL,
            pearson REAL NOT NULL,
            spearman REAL NOT NULL,
            cohit_p75_rate REAL NOT NULL,
            anti_hit_p75_rate REAL NOT NULL,
            joint_mean_x1 REAL NOT NULL,
            joint_p75_x1 REAL NOT NULL,
            joint_p90_x1 REAL NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (profile_id, scope_type, scope_key, population_scope, stat_left, stat_right)
        );

        DROP VIEW IF EXISTS analytics_stat_signal_summary;
        CREATE VIEW analytics_stat_signal_summary AS
        SELECT *
        FROM stat_signal_summary;

        DROP VIEW IF EXISTS analytics_stat_synergy_matrix;
        CREATE VIEW analytics_stat_synergy_matrix AS
        SELECT *
        FROM stat_synergy_matrix;
        """
    )


def load_player_stat_frame(con: sqlite3.Connection, profile_id: str) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT
            m.profile_id,
            m.match_id,
            m.match_date,
            COALESCE(CAST(m.series_id AS TEXT), 'match:' || CAST(m.match_id AS TEXT)) AS series_key,
            m.team_name,
            m.account_id,
            m.official_name,
            m.official_position,
            m.role_group,
            m.stage_name,
            m.stage_bucket,
            CASE WHEN ti.team_name IS NULL THEN 0 ELSE 1 END AS ti2026_qualified,
            ti.qualification_path,
            ti.region AS ti_region,
            s.stat_name,
            s.base_points
        FROM fantasy_player_map_scores m
        JOIN fantasy_player_map_stat_points s
          ON s.match_id = m.match_id
         AND s.account_id = m.account_id
         AND s.team_name = m.team_name
        LEFT JOIN analytics_ti2026_teams ti
          ON ti.team_name = m.team_name
        WHERE m.profile_id = ?
        ORDER BY m.team_name, m.official_position, m.match_date, m.match_id, s.stat_name
        """,
        con,
        params=(profile_id,),
    )


def build_role_slot_stat_frame(player_stats: pd.DataFrame) -> pd.DataFrame:
    frame = player_stats.copy()
    frame["role_slot"] = None
    frame.loc[frame["official_position"].isin([1, 3]), "role_slot"] = "core_pair"
    frame.loc[frame["official_position"] == 2, "role_slot"] = "mid_single"
    frame.loc[frame["official_position"].isin([4, 5]), "role_slot"] = "support_pair"
    frame = frame[frame["role_slot"].notna()].copy()

    grouped = (
        frame.groupby(
            [
                "profile_id",
                "match_id",
                "match_date",
                "series_key",
                "team_name",
                "role_slot",
                "stage_name",
                "stage_bucket",
                "ti2026_qualified",
                "qualification_path",
                "ti_region",
                "stat_name",
            ],
            dropna=False,
            as_index=False,
        )["base_points"]
        .mean()
    )
    grouped["scope_type"] = "role_slot"
    grouped["scope_key"] = grouped["role_slot"]
    grouped["observation_key"] = grouped["team_name"].astype(str) + "::map:" + grouped["match_id"].astype(str)
    return grouped


def build_role_group_stat_frame(player_stats: pd.DataFrame) -> pd.DataFrame:
    frame = player_stats.copy()
    frame["scope_type"] = "role_group"
    frame["scope_key"] = frame["role_group"]
    frame["observation_key"] = (
        frame["team_name"].astype(str)
        + "::"
        + frame["account_id"].astype(str)
        + "::map:"
        + frame["match_id"].astype(str)
    )
    return frame.rename(columns={"base_points": "base_points"})


def summarize_single_stats(frame: pd.DataFrame, profile_id: str, scope_type: str, population_scope: str) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    now = utc_now()
    for (scope_key, stat_name), group in frame.groupby(["scope_key", "stat_name"], sort=False):
        values = group["base_points"].astype(float).tolist()
        nonzero_share = sum(1 for value in values if abs(value) > 1e-9) / float(len(values)) if values else 0.0
        std = float(pd.Series(values).std(ddof=0)) if values else 0.0
        rows.append(
            (
                profile_id,
                scope_type,
                str(scope_key),
                population_scope,
                str(stat_name),
                int(len(values)),
                safe_float(sum(values) / len(values) if values else 0.0),
                percentile(values, 0.75),
                percentile(values, 0.90),
                safe_float(max(values) if values else 0.0),
                safe_float(std),
                safe_float(nonzero_share),
                now,
            )
        )
    return rows


def summarize_synergy(frame: pd.DataFrame, profile_id: str, scope_type: str, population_scope: str) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    now = utc_now()
    for scope_key, group in frame.groupby("scope_key", sort=False):
        wide = (
            group.pivot_table(
                index="observation_key",
                columns="stat_name",
                values="base_points",
                aggfunc="sum",
                fill_value=0.0,
            )
            .sort_index(axis=1)
            .astype(float)
        )
        stats = wide.columns.tolist()
        for idx, stat_left in enumerate(stats):
            left_series = wide[stat_left]
            left_p75 = positive_p75(left_series)
            for stat_right in stats[idx + 1 :]:
                right_series = wide[stat_right]
                right_p75 = positive_p75(right_series)
                pair_sum = left_series + right_series
                both_nonzero = ((left_series.abs() > 1e-9) & (right_series.abs() > 1e-9)).mean()
                if math.isinf(left_p75) or math.isinf(right_p75):
                    cohit = 0.0
                    anti = 0.0
                else:
                    cohit = ((left_series >= left_p75) & (right_series >= right_p75)).mean()
                    anti = ((left_series >= left_p75) ^ (right_series >= right_p75)).mean()
                rows.append(
                    (
                        profile_id,
                        scope_type,
                        str(scope_key),
                        population_scope,
                        stat_left,
                        stat_right,
                        int(len(wide)),
                        safe_float((left_series.abs() > 1e-9).mean()),
                        safe_float((right_series.abs() > 1e-9).mean()),
                        safe_float(both_nonzero),
                        pearson_corr(left_series, right_series),
                        spearman_corr(left_series, right_series),
                        safe_float(cohit),
                        safe_float(anti),
                        safe_float(pair_sum.mean()),
                        percentile(pair_sum.tolist(), 0.75),
                        percentile(pair_sum.tolist(), 0.90),
                        now,
                    )
                )
    return rows


def rebuild_stat_synergy(con: sqlite3.Connection, profile_id: str | None = None) -> dict[str, int]:
    create_schema(con)
    profile_id = profile_id or default_profile_id(con)
    player_stats = load_player_stat_frame(con, profile_id)
    role_group_frame = build_role_group_stat_frame(player_stats)
    role_slot_frame = build_role_slot_stat_frame(player_stats)

    populations = {
        "all_teams": lambda df: df,
        "ti2026_only": lambda df: df[df["ti2026_qualified"] == 1].copy(),
    }

    summary_rows: list[tuple[Any, ...]] = []
    synergy_rows: list[tuple[Any, ...]] = []
    for population_scope, selector in populations.items():
        group_frame = selector(role_group_frame)
        slot_frame = selector(role_slot_frame)
        if not group_frame.empty:
            summary_rows.extend(summarize_single_stats(group_frame, profile_id, "role_group", population_scope))
            synergy_rows.extend(summarize_synergy(group_frame, profile_id, "role_group", population_scope))
        if not slot_frame.empty:
            summary_rows.extend(summarize_single_stats(slot_frame, profile_id, "role_slot", population_scope))
            synergy_rows.extend(summarize_synergy(slot_frame, profile_id, "role_slot", population_scope))

    cur = con.cursor()
    cur.execute("DELETE FROM stat_signal_summary WHERE profile_id = ?", (profile_id,))
    cur.execute("DELETE FROM stat_synergy_matrix WHERE profile_id = ?", (profile_id,))
    if summary_rows:
        cur.executemany(
            """
            INSERT OR REPLACE INTO stat_signal_summary(
                profile_id, scope_type, scope_key, population_scope, stat_name, observations,
                mean_x1, p75_x1, p90_x1, max_x1, std_x1, nonzero_share, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            summary_rows,
        )
    if synergy_rows:
        cur.executemany(
            """
            INSERT OR REPLACE INTO stat_synergy_matrix(
                profile_id, scope_type, scope_key, population_scope, stat_left, stat_right,
                observations, left_nonzero_share, right_nonzero_share, both_nonzero_share,
                pearson, spearman, cohit_p75_rate, anti_hit_p75_rate,
                joint_mean_x1, joint_p75_x1, joint_p90_x1, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            synergy_rows,
        )
    con.commit()
    return {
        "signal_rows": len(summary_rows),
        "synergy_rows": len(synergy_rows),
    }


def build_stat_synergy(db_path: Path = DB_PATH) -> dict[str, Any]:
    con = sqlite3.connect(str(db_path))
    try:
        profile_id = default_profile_id(con)
        counts = rebuild_stat_synergy(con, profile_id=profile_id)
        top_pairs = pd.read_sql_query(
            """
            SELECT
                scope_type,
                scope_key,
                population_scope,
                stat_left,
                stat_right,
                observations,
                spearman,
                cohit_p75_rate,
                anti_hit_p75_rate,
                joint_p75_x1
            FROM stat_synergy_matrix
            WHERE profile_id = ?
            ORDER BY cohit_p75_rate DESC, joint_p75_x1 DESC, spearman DESC
            LIMIT 20
            """,
            con,
            params=(profile_id,),
        )
        return {"profile_id": profile_id, **counts, "top_pairs": top_pairs}
    finally:
        con.close()
