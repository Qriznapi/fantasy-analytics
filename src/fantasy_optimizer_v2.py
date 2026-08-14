from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from fantasy_prediction_foundation import DB_PATH, load_target_dataset, ndcg_at_k, spearman_corr, top_k_overlap
from fantasy_reliability_foundation import rank_scale_1_100, safe_float


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS foundation_optimizer_v2_runs (
            run_id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            ti2026_only INTEGER NOT NULL CHECK (ti2026_only IN (0, 1)),
            notes TEXT,
            created_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS foundation_optimizer_v2_recommendations (
            run_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_key TEXT NOT NULL,
            team_name TEXT NOT NULL,
            official_name TEXT,
            official_position INTEGER,
            role_group TEXT,
            role_slot TEXT,
            player_names TEXT,
            account_id INTEGER,
            account_ids TEXT,
            ti2026_qualified INTEGER NOT NULL,
            qualification_path TEXT,
            ti_region TEXT,
            optimizer_v2_raw_score REAL NOT NULL,
            optimizer_v2_score_1_100 REAL NOT NULL,
            series_top1_p75 REAL NOT NULL,
            series_mean_p75 REAL NOT NULL,
            map_p75_score REAL NOT NULL,
            top_stat_share REAL NOT NULL,
            volatility_ratio REAL NOT NULL,
            sample_weight REAL NOT NULL,
            recommendation_note TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, entity_key)
        );

        CREATE TABLE IF NOT EXISTS foundation_optimizer_v2_backtest (
            run_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            optimizer_scope TEXT NOT NULL,
            entity_key TEXT NOT NULL,
            team_name TEXT NOT NULL,
            segment_key TEXT NOT NULL,
            predicted_score REAL NOT NULL,
            actual_test_score REAL NOT NULL,
            abs_error REAL NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, entity_key)
        );

        CREATE TABLE IF NOT EXISTS foundation_optimizer_v2_evaluation_reports (
            run_id TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            metric_scope TEXT NOT NULL,
            metric_value REAL NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, metric_name, metric_scope)
        );

        DROP VIEW IF EXISTS analytics_optimizer_v2_players;
        CREATE VIEW analytics_optimizer_v2_players AS
        SELECT
            r.*,
            CASE WHEN r.run_id LIKE '%::ti2026' THEN 'ti2026' ELSE 'all' END AS optimizer_scope
        FROM foundation_optimizer_v2_recommendations r
        WHERE entity_type = 'player';

        DROP VIEW IF EXISTS analytics_optimizer_v2_role_slots;
        CREATE VIEW analytics_optimizer_v2_role_slots AS
        SELECT
            r.*,
            CASE WHEN r.run_id LIKE '%::ti2026' THEN 'ti2026' ELSE 'all' END AS optimizer_scope
        FROM foundation_optimizer_v2_recommendations r
        WHERE entity_type = 'role_slot';

        DROP VIEW IF EXISTS analytics_optimizer_v2_backtest;
        CREATE VIEW analytics_optimizer_v2_backtest AS
        SELECT * FROM foundation_optimizer_v2_backtest;

        DROP VIEW IF EXISTS analytics_optimizer_v2_evaluation;
        CREATE VIEW analytics_optimizer_v2_evaluation AS
        SELECT
            r.run_id,
            r.entity_type,
            CASE WHEN r.run_id LIKE '%::ti2026' THEN 'ti2026' ELSE 'all' END AS optimizer_scope,
            e.metric_name,
            e.metric_scope,
            e.metric_value,
            r.created_at_utc
        FROM foundation_optimizer_v2_runs r
        JOIN foundation_optimizer_v2_evaluation_reports e
          ON e.run_id = r.run_id;
        """
    )


def load_source(con: sqlite3.Connection, entity_type: str, ti2026_only: bool) -> pd.DataFrame:
    view = "analytics_reliable_players_foundation" if entity_type == "player" else "analytics_reliable_role_slots_foundation"
    where = "WHERE ti2026_qualified = 1" if ti2026_only else ""
    return pd.read_sql_query(f"SELECT * FROM {view} {where} ORDER BY team_name", con)


def score_frame(df: pd.DataFrame, entity_type: str) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    if entity_type == "player":
        df["optimizer_v2_raw_score"] = (
            0.8 * df["series_top1_p75"].astype(float)
            + 0.1 * df["series_mean_p75"].astype(float)
            - 80.0 * df["top_stat_share"].astype(float)
            - 240.0 * df["volatility_ratio"].astype(float)
        )
    else:
        df["optimizer_v2_raw_score"] = (
            0.5 * df["series_top1_p75"].astype(float)
            + 0.1 * df["series_mean_p75"].astype(float)
            - 120.0 * df["sample_weight"].astype(float)
        )
    segment_col = "role_group" if entity_type == "player" else "role_slot"
    df["optimizer_v2_score_1_100"] = 1.0
    for _, idx in df.groupby(segment_col).groups.items():
        df.loc[idx, "optimizer_v2_score_1_100"] = rank_scale_1_100(df.loc[idx, "optimizer_v2_raw_score"])
    df["recommendation_note"] = (
        "Optimizer v2 candidate: conservative ceiling-first ranker built from top1/mean upper-quantiles with lightweight penalties."
    )
    return df.sort_values([segment_col, "optimizer_v2_score_1_100", "optimizer_v2_raw_score"], ascending=[True, False, False]).reset_index(drop=True)


def build_actuals(con: sqlite3.Connection, profile_id: str, entity_type: str, ti2026_only: bool) -> pd.DataFrame:
    prefix = "player" if entity_type == "player" else "role_slot"
    mean_df = load_target_dataset(con, f"{prefix}_series_mean", profile_id)
    top1_df = load_target_dataset(con, f"{prefix}_series_top1", profile_id)
    mean_df = mean_df[mean_df["stage_bucket"] != "group_stage"].copy()
    top1_df = top1_df[top1_df["stage_bucket"] != "group_stage"].copy()
    if ti2026_only:
        mean_df = mean_df[mean_df["ti2026_qualified"] == 1].copy()
        top1_df = top1_df[top1_df["ti2026_qualified"] == 1].copy()
    mean_actual = mean_df.groupby("entity_key", as_index=False).agg(
        actual_mean=("target_score", "mean"),
        team_name=("team_name", "first"),
        role_group=("role_group", "first"),
        role_slot=("role_slot", "first"),
    )
    top1_actual = top1_df.groupby("entity_key", as_index=False).agg(actual_top1=("target_score", "mean"))
    actual = mean_actual.merge(top1_actual, on="entity_key", how="outer").fillna(0.0)
    actual["actual_test_score"] = 0.60 * actual["actual_mean"].astype(float) + 0.40 * actual["actual_top1"].astype(float)
    actual["segment_key"] = actual["role_group"] if entity_type == "player" else actual["role_slot"]
    return actual[["entity_key", "team_name", "segment_key", "actual_test_score"]].copy()


def persist_frame(con: sqlite3.Connection, entity_type: str, profile_id: str, ti2026_only: bool, df: pd.DataFrame) -> str:
    run_id = f"optimizer_v2::{entity_type}::{'ti2026' if ti2026_only else 'all'}"
    now = utc_now()
    cur = con.cursor()
    cur.execute("DELETE FROM foundation_optimizer_v2_recommendations WHERE run_id = ?", (run_id,))
    cur.execute("DELETE FROM foundation_optimizer_v2_backtest WHERE run_id = ?", (run_id,))
    cur.execute("DELETE FROM foundation_optimizer_v2_evaluation_reports WHERE run_id = ?", (run_id,))
    cur.execute("DELETE FROM foundation_optimizer_v2_runs WHERE run_id = ?", (run_id,))
    cur.execute(
        """
        INSERT INTO foundation_optimizer_v2_runs(run_id, profile_id, entity_type, ti2026_only, notes, created_at_utc)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            profile_id,
            entity_type,
            int(ti2026_only),
            "Optimizer v2 candidate: conservative ceiling-first ranker built from top1/mean upper-quantiles with lightweight penalties.",
            now,
        ),
    )
    rows = []
    for row in df.itertuples(index=False):
        rows.append(
            (
                run_id,
                entity_type,
                row.entity_key,
                row.team_name,
                getattr(row, "official_name", None),
                None if pd.isna(getattr(row, "official_position", None)) else int(row.official_position),
                getattr(row, "role_group", None),
                getattr(row, "role_slot", None),
                getattr(row, "player_names", None),
                None if pd.isna(getattr(row, "account_id", None)) else int(row.account_id),
                getattr(row, "account_ids", None),
                int(row.ti2026_qualified),
                row.qualification_path,
                row.ti_region,
                float(row.optimizer_v2_raw_score),
                float(row.optimizer_v2_score_1_100),
                float(row.series_top1_p75),
                float(row.series_mean_p75),
                float(row.map_p75_score),
                float(row.top_stat_share),
                float(row.volatility_ratio),
                float(row.sample_weight),
                row.recommendation_note,
                now,
            )
        )
    cur.executemany(
        """
        INSERT OR REPLACE INTO foundation_optimizer_v2_recommendations(
            run_id, entity_type, entity_key, team_name, official_name, official_position, role_group,
            role_slot, player_names, account_id, account_ids, ti2026_qualified, qualification_path, ti_region,
            optimizer_v2_raw_score, optimizer_v2_score_1_100, series_top1_p75, series_mean_p75, map_p75_score,
            top_stat_share, volatility_ratio, sample_weight, recommendation_note, created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    con.commit()
    return run_id


def store_backtest_and_evaluation(con: sqlite3.Connection, run_id: str, entity_type: str, scored: pd.DataFrame, actual: pd.DataFrame) -> pd.DataFrame:
    now = utc_now()
    cur = con.cursor()
    merged = scored.merge(actual, on=["entity_key", "team_name"], how="inner")
    if merged.empty:
        con.commit()
        return merged
    segment_col = "role_group" if entity_type == "player" else "role_slot"
    optimizer_scope = "ti2026" if run_id.endswith("::ti2026") else "all"
    for row in merged.itertuples(index=False):
        cur.execute(
            """
            INSERT OR REPLACE INTO foundation_optimizer_v2_backtest(
                run_id, entity_type, optimizer_scope, entity_key, team_name, segment_key, predicted_score,
                actual_test_score, abs_error, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                entity_type,
                optimizer_scope,
                row.entity_key,
                row.team_name,
                getattr(row, segment_col),
                float(row.optimizer_v2_raw_score),
                float(row.actual_test_score),
                abs(float(row.optimizer_v2_raw_score) - float(row.actual_test_score)),
                now,
            ),
        )
    metrics = [
        ("mae", "entity", float(merged["optimizer_v2_raw_score"].sub(merged["actual_test_score"]).abs().mean())),
        ("spearman", "entity", spearman_corr(merged["actual_test_score"], merged["optimizer_v2_raw_score"])),
        ("top3_overlap", "entity", top_k_overlap(merged["actual_test_score"], merged["optimizer_v2_raw_score"], 3)),
        ("top5_overlap", "entity", top_k_overlap(merged["actual_test_score"], merged["optimizer_v2_raw_score"], 5)),
        ("top10_overlap", "entity", top_k_overlap(merged["actual_test_score"], merged["optimizer_v2_raw_score"], 10)),
        ("ndcg_5", "entity", ndcg_at_k(merged["actual_test_score"], merged["optimizer_v2_raw_score"], 5)),
        ("ndcg_10", "entity", ndcg_at_k(merged["actual_test_score"], merged["optimizer_v2_raw_score"], 10)),
    ]
    actual_best = float(merged["actual_test_score"].max())
    best_idx = merged["optimizer_v2_raw_score"].astype(float).idxmax()
    best_actual = float(merged.loc[best_idx, "actual_test_score"])
    metrics.append(("regret_at_1", "entity", max(0.0, actual_best - best_actual)))
    cur.executemany(
        """
        INSERT OR REPLACE INTO foundation_optimizer_v2_evaluation_reports(run_id, metric_name, metric_scope, metric_value, created_at_utc)
        VALUES (?, ?, ?, ?, ?)
        """,
        [(run_id, metric_name, metric_scope, float(metric_value), now) for metric_name, metric_scope, metric_value in metrics],
    )
    con.commit()
    return merged


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


def build_optimizer_v2(db_path: Path = DB_PATH) -> dict[str, Any]:
    con = sqlite3.connect(str(db_path))
    try:
        create_schema(con)
        profile_id = default_profile_id(con)
        summary: list[dict[str, Any]] = []
        run_ids: list[str] = []
        for ti2026_only in (False, True):
            for entity_type in ("player", "role_slot"):
                source = load_source(con, entity_type, ti2026_only)
                scored = score_frame(source, entity_type)
                run_id = persist_frame(con, entity_type, profile_id, ti2026_only, scored)
                run_ids.append(run_id)
                actual = build_actuals(con, profile_id, entity_type, ti2026_only)
                merged = store_backtest_and_evaluation(con, run_id, entity_type, scored, actual)
                summary.append(
                    {
                        "entity_type": entity_type,
                        "ti2026_only": int(ti2026_only),
                        "rows": int(len(scored)),
                        "rows_backtested": int(len(merged)),
                        "spearman": spearman_corr(merged["actual_test_score"], merged["optimizer_v2_raw_score"]) if not merged.empty else 0.0,
                        "top5_overlap": top_k_overlap(merged["actual_test_score"], merged["optimizer_v2_raw_score"], 5) if not merged.empty else 0.0,
                    }
                )
        return {"profile_id": profile_id, "run_ids": run_ids, "summary": pd.DataFrame(summary)}
    finally:
        con.close()


if __name__ == "__main__":
    result = build_optimizer_v2()
    print(f"profile_id={result['profile_id']}")
    print(f"optimizer_v2_runs={len(result['run_ids'])}")
    print(result["summary"].to_string(index=False))
