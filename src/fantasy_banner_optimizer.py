from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "ewc_2026_fantasy_compact.sqlite"

SUPPORT_CAVEAT = (
    "Support fantasy statistics are incomplete/low-confidence in this dataset; "
    "default optimizer recommendations focus on official positions 1-3 and core_pair/mid_single."
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
    except Exception:
        return default
    if math.isnan(value):
        return default
    return value


def percentile(values: list[float], q: float) -> float:
    values = sorted(safe_float(v) for v in values if v is not None)
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    pos = (len(values) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return values[lo]
    return values[lo] * (hi - pos) + values[hi] * (pos - lo)


def std_population(values: list[float]) -> float:
    values = [safe_float(v) for v in values if v is not None]
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def top_mean(values: list[float], n: int) -> float:
    values = sorted((safe_float(v) for v in values if v is not None), reverse=True)
    if not values:
        return 0.0
    return sum(values[:n]) / min(n, len(values))


def rank_scale_1_100(values: pd.Series) -> pd.Series:
    if len(values) == 0:
        return values
    if len(values) == 1:
        return pd.Series([100.0], index=values.index)
    ranks = values.rank(method="average", ascending=True)
    return (1.0 + 99.0 * (ranks - 1.0) / (len(values) - 1.0)).round(2)


def feature_block(scores: list[float]) -> dict[str, float]:
    scores = [safe_float(v) for v in scores if v is not None]
    if not scores:
        return {
            "series_seen": 0.0,
            "best2_series_score": 0.0,
            "second_best2_series_score": 0.0,
            "top2_series_avg": 0.0,
            "p75_series_score": 0.0,
            "avg_series_score": 0.0,
            "std_series_score": 0.0,
            "floor_series_score": 0.0,
            "spike_gap": 0.0,
            "repeatability_ratio": 0.0,
            "optimizer_raw_score": 0.0,
        }
    desc = sorted(scores, reverse=True)
    best = desc[0]
    second = desc[1] if len(desc) > 1 else best * 0.70
    avg = sum(scores) / len(scores)
    p75 = percentile(scores, 0.75)
    top2 = top_mean(scores, 2)
    std = std_population(scores)
    floor = min(scores)
    spike_gap = max(0.0, best - second)
    repeatability = second / best if best > 0 else 0.0
    raw = (
        0.30 * best
        + 0.24 * second
        + 0.18 * top2
        + 0.14 * p75
        + 0.08 * avg
        + 0.06 * floor
        - 0.20 * spike_gap
        - 0.08 * std
    )
    return {
        "series_seen": float(len(scores)),
        "best2_series_score": best,
        "second_best2_series_score": second,
        "top2_series_avg": top2,
        "p75_series_score": p75,
        "avg_series_score": avg,
        "std_series_score": std,
        "floor_series_score": floor,
        "spike_gap": spike_gap,
        "repeatability_ratio": repeatability,
        "optimizer_raw_score": max(0.0, raw),
    }


def default_profile_id(con: sqlite3.Connection) -> str:
    row = con.execute(
        """
        SELECT profile_id
        FROM fantasy_scoring_profiles
        WHERE is_default = 1
        LIMIT 1
        """
    ).fetchone()
    if not row:
        raise RuntimeError("No default fantasy profile")
    return str(row[0])


def create_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS fantasy_banner_optimizer_runs (
            run_id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            ti2026_only INTEGER NOT NULL CHECK (ti2026_only IN (0, 1)),
            include_support INTEGER NOT NULL CHECK (include_support IN (0, 1)),
            target_policy TEXT NOT NULL,
            scoring_notes TEXT,
            source_notes TEXT
        );

        CREATE TABLE IF NOT EXISTS fantasy_banner_optimizer_recommendations (
            run_id TEXT NOT NULL,
            recommendation_key TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            rank_in_segment INTEGER NOT NULL,
            optimizer_score_1_100 REAL NOT NULL,
            profile_id TEXT NOT NULL,
            team_name TEXT NOT NULL,
            official_name TEXT,
            official_position INTEGER,
            role_group TEXT,
            role_slot TEXT,
            player_names TEXT,
            account_id INTEGER,
            account_ids TEXT,
            predicted_score_raw REAL NOT NULL,
            best2_series_score REAL NOT NULL,
            second_best2_series_score REAL NOT NULL,
            top2_series_avg REAL NOT NULL,
            p75_series_score REAL NOT NULL,
            avg_series_score REAL NOT NULL,
            std_series_score REAL NOT NULL,
            floor_series_score REAL NOT NULL,
            spike_gap REAL NOT NULL,
            repeatability_ratio REAL NOT NULL,
            train_series_seen INTEGER NOT NULL,
            ti2026_qualified INTEGER NOT NULL,
            qualification_path TEXT,
            ti_region TEXT,
            data_quality_label TEXT,
            recommendation_note TEXT,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, recommendation_key)
        );
        """
    )


def player_series(con: sqlite3.Connection, profile_id: str, ti2026_only: bool) -> pd.DataFrame:
    ti_join = "JOIN analytics_ti2026_teams ti ON ti.team_name = s.team_name" if ti2026_only else "LEFT JOIN analytics_ti2026_teams ti ON ti.team_name = s.team_name"
    return pd.read_sql_query(
        f"""
        WITH map_scores AS (
            SELECT
                s.profile_id,
                COALESCE(CAST(s.series_id AS TEXT), 'match:' || CAST(s.match_id AS TEXT)) AS series_key,
                s.series_id,
                MIN(s.match_date) OVER (
                    PARTITION BY s.profile_id, COALESCE(CAST(s.series_id AS TEXT), 'match:' || CAST(s.match_id AS TEXT)),
                                 s.account_id, s.team_name
                ) AS series_start_date,
                s.stage_bucket,
                s.account_id,
                s.team_name,
                s.official_name,
                s.official_position,
                s.role_group,
                s.fantasy_score,
                CASE WHEN ti.team_name IS NULL THEN 0 ELSE 1 END AS ti2026_qualified,
                ti.qualification_path,
                ti.region AS ti_region
            FROM fantasy_player_map_scores s
            {ti_join}
            WHERE s.profile_id = ?
              AND s.stage_bucket IS NOT NULL
        ),
        ranked AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY profile_id, series_key, account_id, team_name
                       ORDER BY fantasy_score DESC
                   ) AS rn
            FROM map_scores
        )
        SELECT
            profile_id,
            series_key,
            series_id,
            series_start_date,
            stage_bucket,
            account_id,
            team_name,
            official_name,
            official_position,
            role_group,
            SUM(CASE WHEN rn <= 2 THEN fantasy_score ELSE 0 END) AS best2_series_score,
            MAX(ti2026_qualified) AS ti2026_qualified,
            MAX(qualification_path) AS qualification_path,
            MAX(ti_region) AS ti_region
        FROM ranked
        GROUP BY profile_id, series_key, series_id, series_start_date, stage_bucket,
                 account_id, team_name, official_name, official_position, role_group
        """,
        con,
        params=(profile_id,),
    )


def role_slot_series(con: sqlite3.Connection, profile_id: str, ti2026_only: bool) -> pd.DataFrame:
    ti_join = "JOIN analytics_ti2026_teams ti ON ti.team_name = s.team_name" if ti2026_only else "LEFT JOIN analytics_ti2026_teams ti ON ti.team_name = s.team_name"
    return pd.read_sql_query(
        f"""
        WITH map_scores AS (
            SELECT
                s.profile_id,
                COALESCE(CAST(p.series_id AS TEXT), 'match:' || CAST(s.match_id AS TEXT)) AS series_key,
                p.series_id,
                s.match_date,
                s.stage_bucket,
                s.team_name,
                CASE
                    WHEN s.role_category = 'core_avg' THEN 'core_pair'
                    WHEN s.role_category = 'mid' THEN 'mid_single'
                    WHEN s.role_category = 'support_avg' THEN 'support_pair'
                END AS role_slot,
                CASE
                    WHEN s.role_category = 'core_avg' THEN 'Average official pos1 + pos3'
                    WHEN s.role_category = 'mid' THEN 'Official pos2'
                    WHEN s.role_category = 'support_avg' THEN 'Average official pos4 + pos5'
                END AS role_slot_label,
                s.included_positions,
                s.player_names,
                s.account_ids,
                s.role_category_fantasy_score AS fantasy_score,
                CASE WHEN ti.team_name IS NULL THEN 0 ELSE 1 END AS ti2026_qualified,
                ti.qualification_path,
                ti.region AS ti_region
            FROM fantasy_team_role_map_scores s
            JOIN matches p
              ON p.match_id = s.match_id
            {ti_join}
            WHERE s.profile_id = ?
              AND s.stage_bucket IS NOT NULL
        ),
        ranked AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY profile_id, series_key, team_name, role_slot
                       ORDER BY fantasy_score DESC
                   ) AS rn
            FROM map_scores
        )
        SELECT
            profile_id,
            series_key,
            series_id,
            MIN(match_date) AS series_start_date,
            stage_bucket,
            team_name,
            role_slot,
            MAX(role_slot_label) AS role_slot_label,
            MAX(included_positions) AS included_positions,
            MAX(player_names) AS player_names,
            MAX(account_ids) AS account_ids,
            SUM(CASE WHEN rn <= 2 THEN fantasy_score ELSE 0 END) AS best2_series_score,
            MAX(ti2026_qualified) AS ti2026_qualified,
            MAX(qualification_path) AS qualification_path,
            MAX(ti_region) AS ti_region
        FROM ranked
        GROUP BY profile_id, series_key, series_id, stage_bucket, team_name, role_slot
        """,
        con,
        params=(profile_id,),
    )


def build_player_recs(series: pd.DataFrame, profile_id: str, include_support: bool) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    train = series[series["stage_bucket"] == "group_stage"].copy()
    for (_account_id, _team), group in train.groupby(["account_id", "team_name"], sort=False):
        group = group.sort_values(["series_start_date", "series_key"])
        first = group.iloc[0]
        features = feature_block(group["best2_series_score"].tolist())
        data_quality_label = "support_low_stat_coverage" if first["role_group"] == "support" else "usable_for_default_recommendations"
        if first["role_group"] == "support" and not include_support:
            continue
        rows.append(
            {
                "entity_type": "player",
                "profile_id": profile_id,
                "team_name": first["team_name"],
                "official_name": first["official_name"],
                "official_position": int(first["official_position"]),
                "role_group": first["role_group"],
                "role_slot": None,
                "player_names": None,
                "account_id": int(first["account_id"]),
                "account_ids": None,
                "ti2026_qualified": int(first["ti2026_qualified"]),
                "qualification_path": first["qualification_path"],
                "ti_region": first["ti_region"],
                "data_quality_label": data_quality_label,
                "recommendation_note": SUPPORT_CAVEAT if data_quality_label == "support_low_stat_coverage" else "Recommended by repeatable ceiling optimizer.",
                **features,
            }
        )
    return finalize_scores(pd.DataFrame(rows), "role_group")


def build_role_slot_recs(series: pd.DataFrame, profile_id: str, include_support: bool) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    train = series[series["stage_bucket"] == "group_stage"].copy()
    for (_team, _slot), group in train.groupby(["team_name", "role_slot"], sort=False):
        group = group.sort_values(["series_start_date", "series_key"])
        first = group.iloc[0]
        data_quality_label = "support_low_stat_coverage" if first["role_slot"] == "support_pair" else "usable_for_default_recommendations"
        if first["role_slot"] == "support_pair" and not include_support:
            continue
        features = feature_block(group["best2_series_score"].tolist())
        rows.append(
            {
                "entity_type": "role_slot",
                "profile_id": profile_id,
                "team_name": first["team_name"],
                "official_name": None,
                "official_position": None,
                "role_group": None,
                "role_slot": first["role_slot"],
                "player_names": first["player_names"],
                "account_id": None,
                "account_ids": first["account_ids"],
                "ti2026_qualified": int(first["ti2026_qualified"]),
                "qualification_path": first["qualification_path"],
                "ti_region": first["ti_region"],
                "data_quality_label": data_quality_label,
                "recommendation_note": SUPPORT_CAVEAT if data_quality_label == "support_low_stat_coverage" else "Recommended by repeatable ceiling optimizer.",
                **features,
            }
        )
    return finalize_scores(pd.DataFrame(rows), "role_slot")


def finalize_scores(df: pd.DataFrame, segment_col: str) -> pd.DataFrame:
    if df.empty:
        return df
    df["optimizer_score_1_100"] = 1.0
    for (_segment, idx) in df.groupby(segment_col).groups.items():
        df.loc[idx, "optimizer_score_1_100"] = rank_scale_1_100(df.loc[idx, "optimizer_raw_score"])
    df = df.sort_values([segment_col, "optimizer_score_1_100", "optimizer_raw_score"], ascending=[True, False, False])
    df["rank_in_segment"] = df.groupby(segment_col).cumcount() + 1
    for col in [
        "optimizer_raw_score",
        "optimizer_score_1_100",
        "best2_series_score",
        "second_best2_series_score",
        "top2_series_avg",
        "p75_series_score",
        "avg_series_score",
        "std_series_score",
        "floor_series_score",
        "spike_gap",
        "repeatability_ratio",
    ]:
        df[col] = df[col].astype(float).round(6)
    df["series_seen"] = df["series_seen"].astype(int)
    return df


def optimize_profile(
    con: sqlite3.Connection,
    profile_id: str | None = None,
    *,
    run_id: str | None = None,
    ti2026_only: bool = False,
    include_support: bool = False,
    persist: bool = True,
) -> tuple[str, pd.DataFrame, pd.DataFrame]:
    create_schema(con)
    profile_id = profile_id or default_profile_id(con)
    run_id = run_id or (
        f"optimizer_{profile_id}_{'ti2026' if ti2026_only else 'all'}_{'support' if include_support else 'core_mid'}"
    )
    ps = player_series(con, profile_id, ti2026_only)
    rs = role_slot_series(con, profile_id, ti2026_only)
    player_recs = build_player_recs(ps, profile_id, include_support)
    slot_recs = build_role_slot_recs(rs, profile_id, include_support)
    if persist:
        save_optimizer_run(con, run_id, profile_id, player_recs, slot_recs, ti2026_only, include_support)
    return run_id, player_recs, slot_recs


def save_optimizer_run(
    con: sqlite3.Connection,
    run_id: str,
    profile_id: str,
    player_recs: pd.DataFrame,
    slot_recs: pd.DataFrame,
    ti2026_only: bool,
    include_support: bool,
) -> None:
    cur = con.cursor()
    cur.execute("DELETE FROM fantasy_banner_optimizer_recommendations WHERE run_id = ?", (run_id,))
    cur.execute("DELETE FROM fantasy_banner_optimizer_runs WHERE run_id = ?", (run_id,))
    cur.execute(
        """
        INSERT INTO fantasy_banner_optimizer_runs(
            run_id, profile_id, created_at_utc, ti2026_only, include_support,
            target_policy, scoring_notes, source_notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            profile_id,
            utc_now(),
            int(ti2026_only),
            int(include_support),
            "best two maps of best/repeatable series; group_stage train signal",
            "Weighted repeatable ceiling with spike and volatility penalty; score 1-100 inside role/slot.",
            "Uses fantasy_player_map_scores and ti_qualified_teams when ti2026_only=1.",
        ),
    )
    combined = pd.concat([player_recs, slot_recs], ignore_index=True) if not player_recs.empty or not slot_recs.empty else pd.DataFrame()
    if combined.empty:
        con.commit()
        return
    insert_rows = []
    for row in combined.itertuples(index=False):
        recommendation_key = (
            f"player:{row.account_id}:{row.team_name}"
            if row.entity_type == "player"
            else f"role_slot:{row.team_name}:{row.role_slot}"
        )
        insert_rows.append(
            (
                run_id,
                recommendation_key,
                row.entity_type,
                int(row.rank_in_segment),
                float(row.optimizer_score_1_100),
                row.profile_id,
                row.team_name,
                row.official_name,
                None if pd.isna(row.official_position) else int(row.official_position),
                row.role_group,
                row.role_slot,
                row.player_names,
                None if pd.isna(row.account_id) else int(row.account_id),
                row.account_ids,
                float(row.optimizer_raw_score),
                float(row.best2_series_score),
                float(row.second_best2_series_score),
                float(row.top2_series_avg),
                float(row.p75_series_score),
                float(row.avg_series_score),
                float(row.std_series_score),
                float(row.floor_series_score),
                float(row.spike_gap),
                float(row.repeatability_ratio),
                int(row.series_seen),
                int(row.ti2026_qualified),
                row.qualification_path,
                row.ti_region,
                row.data_quality_label,
                row.recommendation_note,
                utc_now(),
            )
        )
    cur.executemany(
        """
        INSERT OR REPLACE INTO fantasy_banner_optimizer_recommendations(
            run_id, recommendation_key, entity_type, rank_in_segment, optimizer_score_1_100,
            profile_id, team_name, official_name, official_position, role_group,
            role_slot, player_names, account_id, account_ids, predicted_score_raw,
            best2_series_score, second_best2_series_score, top2_series_avg,
            p75_series_score, avg_series_score, std_series_score, floor_series_score,
            spike_gap, repeatability_ratio, train_series_seen, ti2026_qualified,
            qualification_path, ti_region, data_quality_label, recommendation_note,
            created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        insert_rows,
    )
    create_views(con)
    con.commit()


def create_views(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        DROP VIEW IF EXISTS analytics_optimizer_players;
        CREATE VIEW analytics_optimizer_players AS
        SELECT
            r.*,
            CASE
                WHEN r.run_id LIKE '%ti2026%' THEN 'ti2026'
                WHEN r.run_id LIKE '%all%' THEN 'all'
                ELSE 'custom'
            END AS optimizer_scope
        FROM fantasy_banner_optimizer_recommendations r
        WHERE r.entity_type = 'player';

        DROP VIEW IF EXISTS analytics_optimizer_role_slots;
        CREATE VIEW analytics_optimizer_role_slots AS
        SELECT
            r.*,
            CASE
                WHEN r.run_id LIKE '%ti2026%' THEN 'ti2026'
                WHEN r.run_id LIKE '%all%' THEN 'all'
                ELSE 'custom'
            END AS optimizer_scope
        FROM fantasy_banner_optimizer_recommendations r
        WHERE r.entity_type = 'role_slot';
        """
    )


def build_default_runs(db_path: Path = DB_PATH) -> None:
    con = sqlite3.connect(db_path)
    try:
        create_schema(con)
        profile_id = default_profile_id(con)
        optimize_profile(
            con,
            profile_id,
            run_id=f"optimizer_{profile_id}_all_core_mid",
            ti2026_only=False,
            include_support=False,
            persist=True,
        )
        optimize_profile(
            con,
            profile_id,
            run_id=f"optimizer_{profile_id}_ti2026_core_mid",
            ti2026_only=True,
            include_support=False,
            persist=True,
        )
        create_views(con)
        con.execute(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
            ("fantasy_banner_optimizer_version", "optimizer_v1_repeatable_ceiling_banner_profiles"),
        )
        con.execute(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
            ("fantasy_banner_optimizer_default_runs", f"optimizer_{profile_id}_all_core_mid, optimizer_{profile_id}_ti2026_core_mid"),
        )
        con.commit()
    finally:
        con.close()


if __name__ == "__main__":
    build_default_runs()
    print("fantasy banner optimizer default runs built")
