from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from fantasy_prediction_foundation import (
    load_target_dataset,
    ndcg_at_k,
    spearman_corr,
    top_k_overlap,
)
from project_db import resolve_db_path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = resolve_db_path(PROJECT_ROOT)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def rank_scale_1_100(values: pd.Series) -> pd.Series:
    if len(values) == 0:
        return values
    if len(values) == 1:
        return pd.Series([100.0], index=values.index)
    ranks = values.rank(method="average", ascending=True)
    return (1.0 + 99.0 * (ranks - 1.0) / (len(values) - 1.0)).round(2)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
    except Exception:
        return default
    if math.isnan(value):
        return default
    return value


def create_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS foundation_optimizer_runs (
            run_id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            ti2026_only INTEGER NOT NULL CHECK (ti2026_only IN (0, 1)),
            notes TEXT,
            created_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS foundation_optimizer_recommendations (
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
            optimizer_raw_score REAL NOT NULL,
            optimizer_score_1_100 REAL NOT NULL,
            expected_estimate REAL NOT NULL,
            high_estimate REAL NOT NULL,
            low_estimate REAL NOT NULL,
            reliability_score_1_100 REAL NOT NULL,
            map_p75_score REAL NOT NULL,
            series_mean_p75 REAL NOT NULL,
            series_top1_p75 REAL NOT NULL,
            stat_balance_score REAL NOT NULL,
            volatility_ratio REAL NOT NULL,
            sample_weight REAL NOT NULL,
            confidence_label TEXT NOT NULL,
            data_quality_label TEXT NOT NULL,
            recommendation_note TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, entity_key)
        );

        CREATE TABLE IF NOT EXISTS foundation_optimizer_backtest (
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

        CREATE TABLE IF NOT EXISTS foundation_optimizer_evaluation_reports (
            run_id TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            metric_scope TEXT NOT NULL,
            metric_value REAL NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, metric_name, metric_scope)
        );

        CREATE TABLE IF NOT EXISTS foundation_optimizer_baseline_reports (
            run_id TEXT NOT NULL,
            baseline_id TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            metric_scope TEXT NOT NULL,
            segment_key TEXT NOT NULL,
            metric_value REAL NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, baseline_id, metric_name, metric_scope, segment_key)
        );

        DROP VIEW IF EXISTS analytics_optimizer_players_foundation;
        CREATE VIEW analytics_optimizer_players_foundation AS
        SELECT
            r.*,
            CASE
                WHEN r.run_id LIKE '%::ti2026' THEN 'ti2026'
                ELSE 'all'
            END AS optimizer_scope
        FROM foundation_optimizer_recommendations
        r
        WHERE entity_type = 'player';

        DROP VIEW IF EXISTS analytics_optimizer_role_slots_foundation;
        CREATE VIEW analytics_optimizer_role_slots_foundation AS
        SELECT
            r.*,
            CASE
                WHEN r.run_id LIKE '%::ti2026' THEN 'ti2026'
                ELSE 'all'
            END AS optimizer_scope
        FROM foundation_optimizer_recommendations
        r
        WHERE entity_type = 'role_slot';

        DROP VIEW IF EXISTS analytics_optimizer_foundation_backtest;
        CREATE VIEW analytics_optimizer_foundation_backtest AS
        SELECT *
        FROM foundation_optimizer_backtest;

        DROP VIEW IF EXISTS analytics_optimizer_foundation_evaluation;
        CREATE VIEW analytics_optimizer_foundation_evaluation AS
        SELECT
            r.run_id,
            r.entity_type,
            CASE
                WHEN r.run_id LIKE '%::ti2026' THEN 'ti2026'
                ELSE 'all'
            END AS optimizer_scope,
            e.metric_name,
            e.metric_scope,
            e.metric_value,
            r.created_at_utc
        FROM foundation_optimizer_runs r
        JOIN foundation_optimizer_evaluation_reports e
          ON e.run_id = r.run_id;

        DROP VIEW IF EXISTS analytics_optimizer_foundation_baselines;
        CREATE VIEW analytics_optimizer_foundation_baselines AS
        SELECT
            r.run_id,
            r.entity_type,
            CASE
                WHEN r.run_id LIKE '%::ti2026' THEN 'ti2026'
                ELSE 'all'
            END AS optimizer_scope,
            b.baseline_id,
            b.metric_name,
            b.metric_scope,
            b.segment_key,
            b.metric_value,
            r.created_at_utc
        FROM foundation_optimizer_runs r
        JOIN foundation_optimizer_baseline_reports b
          ON b.run_id = r.run_id;
        """
    )


def load_source(con: sqlite3.Connection, entity_type: str, ti2026_only: bool) -> pd.DataFrame:
    view = "analytics_reliable_players_foundation" if entity_type == "player" else "analytics_reliable_role_slots_foundation"
    where = "WHERE ti2026_qualified = 1" if ti2026_only else ""
    return pd.read_sql_query(
        f"""
        SELECT *
        FROM {view}
        {where}
        ORDER BY team_name
        """,
        con,
    )


def score_frame(df: pd.DataFrame, entity_type: str) -> pd.DataFrame:
    if df.empty:
        return df
    band_width = (df["high_estimate"].astype(float) - df["low_estimate"].astype(float)).clip(lower=0.0)
    df = df.copy()
    if entity_type == "player":
        df["optimizer_raw_score"] = (
            0.18 * df["expected_estimate"].astype(float)
            + 0.18 * df["high_estimate"].astype(float)
            + 0.24 * df["series_top1_p75"].astype(float)
            + 0.16 * df["series_mean_p75"].astype(float)
            + 0.10 * df["map_p75_score"].astype(float)
            + 0.08 * df["recent_series_top1_3"].astype(float)
            + 2.0 * df["reliability_score_1_100"].astype(float)
            + 650.0 * df["stat_balance_score"].astype(float)
            - 120.0 * df["sample_weight"].astype(float)
            - 0.05 * band_width
            - 250.0 * df["volatility_ratio"].astype(float)
            - 360.0 * df["top_stat_share"].astype(float)
        ).clip(lower=0.0)
    else:
        df["optimizer_raw_score"] = (
            0.12 * df["expected_estimate"].astype(float)
            + 0.18 * df["high_estimate"].astype(float)
            + 0.28 * df["series_top1_p75"].astype(float)
            + 0.10 * df["series_mean_p75"].astype(float)
            + 0.14 * df["map_p75_score"].astype(float)
            + 0.08 * df["recent_series_top1_3"].astype(float)
            + 1.0 * df["reliability_score_1_100"].astype(float)
            + 700.0 * df["stat_balance_score"].astype(float)
            - 150.0 * df["sample_weight"].astype(float)
            - 0.03 * band_width
            - 220.0 * df["volatility_ratio"].astype(float)
            - 380.0 * df["top_stat_share"].astype(float)
        ).clip(lower=0.0)
    segment_col = "role_group" if entity_type == "player" else "role_slot"
    df["optimizer_score_1_100"] = 1.0
    for _, idx in df.groupby(segment_col).groups.items():
        df.loc[idx, "optimizer_score_1_100"] = rank_scale_1_100(df.loc[idx, "optimizer_raw_score"])
    df["recommendation_note"] = df.apply(
        lambda row: (
            "Foundation optimizer: strong upside with balanced stat profile."
            if safe_float(row["stat_balance_score"]) >= 0.70 and safe_float(row["volatility_ratio"]) <= 0.40
            else "Foundation optimizer: playable upside, but monitor volatility/context."
        ),
        axis=1,
    )
    return df.sort_values([segment_col, "optimizer_score_1_100", "optimizer_raw_score"], ascending=[True, False, False]).reset_index(drop=True)


def persist_frame(
    con: sqlite3.Connection,
    entity_type: str,
    profile_id: str,
    ti2026_only: bool,
    df: pd.DataFrame,
) -> str:
    run_id = f"foundation_optimizer::{entity_type}::{'ti2026' if ti2026_only else 'all'}"
    now = utc_now()
    cur = con.cursor()
    cur.execute("DELETE FROM foundation_optimizer_recommendations WHERE run_id = ?", (run_id,))
    cur.execute("DELETE FROM foundation_optimizer_runs WHERE run_id = ?", (run_id,))
    cur.execute(
        """
        INSERT INTO foundation_optimizer_runs(run_id, profile_id, entity_type, ti2026_only, notes, created_at_utc)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            profile_id,
            entity_type,
            int(ti2026_only),
            "Foundation optimizer built from expected/high estimates, p75 metrics, stat balance, and volatility penalties.",
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
                float(row.optimizer_raw_score),
                float(row.optimizer_score_1_100),
                float(row.expected_estimate),
                float(row.high_estimate),
                float(row.low_estimate),
                float(row.reliability_score_1_100),
                float(row.map_p75_score),
                float(row.series_mean_p75),
                float(row.series_top1_p75),
                float(row.stat_balance_score),
                float(row.volatility_ratio),
                float(row.sample_weight),
                row.confidence_label,
                row.data_quality_label,
                row.recommendation_note,
                now,
            )
        )
    cur.executemany(
        """
        INSERT OR REPLACE INTO foundation_optimizer_recommendations(
            run_id, entity_type, entity_key, team_name, official_name, official_position, role_group,
            role_slot, player_names, account_id, account_ids, ti2026_qualified, qualification_path,
            ti_region, optimizer_raw_score, optimizer_score_1_100, expected_estimate, high_estimate,
            low_estimate, reliability_score_1_100, map_p75_score, series_mean_p75, series_top1_p75,
            stat_balance_score, volatility_ratio, sample_weight, confidence_label, data_quality_label,
            recommendation_note, created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    con.commit()
    return run_id


def build_optimizer_actuals(
    con: sqlite3.Connection,
    profile_id: str,
    entity_type: str,
    ti2026_only: bool,
) -> pd.DataFrame:
    prefix = "player" if entity_type == "player" else "role_slot"
    mean_df = load_target_dataset(con, f"{prefix}_series_mean", profile_id)
    top1_df = load_target_dataset(con, f"{prefix}_series_top1", profile_id)
    mean_df = mean_df[mean_df["stage_bucket"] != "group_stage"].copy()
    top1_df = top1_df[top1_df["stage_bucket"] != "group_stage"].copy()
    if ti2026_only:
        mean_df = mean_df[mean_df["ti2026_qualified"] == 1].copy()
        top1_df = top1_df[top1_df["ti2026_qualified"] == 1].copy()
    if mean_df.empty and top1_df.empty:
        return pd.DataFrame()

    mean_actual = (
        mean_df.groupby("entity_key", as_index=False)
        .agg(
            actual_mean=("target_score", "mean"),
            team_name=("team_name", "first"),
            role_group=("role_group", "first"),
            role_slot=("role_slot", "first"),
        )
    )
    top1_actual = (
        top1_df.groupby("entity_key", as_index=False)
        .agg(actual_top1=("target_score", "mean"))
    )
    actual = mean_actual.merge(top1_actual, on="entity_key", how="outer").fillna(0.0)
    actual["actual_test_score"] = 0.60 * actual["actual_mean"].astype(float) + 0.40 * actual["actual_top1"].astype(float)
    actual["segment_key"] = actual["role_group"] if entity_type == "player" else actual["role_slot"]
    return actual[["entity_key", "team_name", "segment_key", "actual_test_score"]].copy()


def store_backtest_and_evaluation(
    con: sqlite3.Connection,
    run_id: str,
    entity_type: str,
    scored: pd.DataFrame,
    actual: pd.DataFrame,
) -> pd.DataFrame:
    now = utc_now()
    cur = con.cursor()
    cur.execute("DELETE FROM foundation_optimizer_backtest WHERE run_id = ?", (run_id,))
    cur.execute("DELETE FROM foundation_optimizer_evaluation_reports WHERE run_id = ?", (run_id,))
    if scored.empty or actual.empty:
        con.commit()
        return pd.DataFrame()

    segment_col = "role_group" if entity_type == "player" else "role_slot"
    optimizer_scope = "ti2026" if run_id.endswith("::ti2026") else "all"
    merged = scored.merge(actual, on=["entity_key", "team_name"], how="inner")
    if merged.empty:
        con.commit()
        return merged

    for row in merged.itertuples(index=False):
        cur.execute(
            """
            INSERT OR REPLACE INTO foundation_optimizer_backtest(
                run_id, entity_type, optimizer_scope, entity_key, team_name,
                segment_key, predicted_score, actual_test_score, abs_error, created_at_utc
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
                float(row.optimizer_raw_score),
                float(row.actual_test_score),
                abs(float(row.optimizer_raw_score) - float(row.actual_test_score)),
                now,
            ),
        )

    metrics: list[tuple[str, str, float]] = [
        ("mae", "entity", float(merged["optimizer_raw_score"].sub(merged["actual_test_score"]).abs().mean())),
        ("spearman", "entity", spearman_corr(merged["actual_test_score"], merged["optimizer_raw_score"])),
        ("top3_overlap", "entity", top_k_overlap(merged["actual_test_score"], merged["optimizer_raw_score"], 3)),
        ("top5_overlap", "entity", top_k_overlap(merged["actual_test_score"], merged["optimizer_raw_score"], 5)),
        ("top10_overlap", "entity", top_k_overlap(merged["actual_test_score"], merged["optimizer_raw_score"], 10)),
        ("ndcg_5", "entity", ndcg_at_k(merged["actual_test_score"], merged["optimizer_raw_score"], 5)),
        ("ndcg_10", "entity", ndcg_at_k(merged["actual_test_score"], merged["optimizer_raw_score"], 10)),
    ]
    actual_best = float(merged["actual_test_score"].max()) if not merged.empty else 0.0
    if not merged.empty:
        predicted_best_idx = merged["optimizer_raw_score"].astype(float).idxmax()
        predicted_best_actual = float(merged.loc[predicted_best_idx, "actual_test_score"])
    else:
        predicted_best_actual = 0.0
    metrics.append(("regret_at_1", "entity", max(0.0, actual_best - predicted_best_actual)))

    for segment_value, block in merged.groupby(segment_col, sort=False):
        if block.empty:
            continue
        metrics.extend(
            [
                (f"{segment_value}__spearman", "segment", spearman_corr(block["actual_test_score"], block["optimizer_raw_score"])),
                (f"{segment_value}__top3_overlap", "segment", top_k_overlap(block["actual_test_score"], block["optimizer_raw_score"], 3)),
                (f"{segment_value}__ndcg_5", "segment", ndcg_at_k(block["actual_test_score"], block["optimizer_raw_score"], 5)),
            ]
        )

    cur.executemany(
        """
        INSERT OR REPLACE INTO foundation_optimizer_evaluation_reports(
            run_id, metric_name, metric_scope, metric_value, created_at_utc
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        [(run_id, metric_name, metric_scope, float(metric_value), now) for metric_name, metric_scope, metric_value in metrics],
    )
    con.commit()
    return merged


def baseline_score_frame(scored: pd.DataFrame, baseline_id: str) -> pd.Series:
    if baseline_id == "expected_only":
        return scored["expected_estimate"].astype(float)
    if baseline_id == "high_only":
        return scored["high_estimate"].astype(float)
    if baseline_id == "reliability_only":
        return scored["reliability_raw_score"].astype(float)
    if baseline_id == "top1_p75_only":
        return scored["series_top1_p75"].astype(float)
    if baseline_id == "ceiling_blend":
        return (
            0.55 * scored["series_top1_p75"].astype(float)
            + 0.25 * scored["series_mean_p75"].astype(float)
            + 0.20 * scored["map_p75_score"].astype(float)
        )
    raise ValueError(f"Unsupported baseline_id={baseline_id!r}")


def store_baseline_reports(
    con: sqlite3.Connection,
    run_id: str,
    entity_type: str,
    merged: pd.DataFrame,
) -> None:
    now = utc_now()
    cur = con.cursor()
    cur.execute("DELETE FROM foundation_optimizer_baseline_reports WHERE run_id = ?", (run_id,))
    if merged.empty:
        con.commit()
        return

    segment_col = "role_group" if entity_type == "player" else "role_slot"
    baselines = ["expected_only", "high_only", "reliability_only", "top1_p75_only", "ceiling_blend"]
    rows: list[tuple[Any, ...]] = []
    for baseline_id in baselines:
        predicted = baseline_score_frame(merged, baseline_id)
        entity_metrics = [
            ("mae", "entity", "all", float(predicted.sub(merged["actual_test_score"]).abs().mean())),
            ("spearman", "entity", "all", spearman_corr(merged["actual_test_score"], predicted)),
            ("top5_overlap", "entity", "all", top_k_overlap(merged["actual_test_score"], predicted, 5)),
            ("ndcg_5", "entity", "all", ndcg_at_k(merged["actual_test_score"], predicted, 5)),
        ]
        actual_best = float(merged["actual_test_score"].max())
        best_idx = predicted.astype(float).idxmax()
        best_actual = float(merged.loc[best_idx, "actual_test_score"])
        entity_metrics.append(("regret_at_1", "entity", "all", max(0.0, actual_best - best_actual)))
        for metric_name, metric_scope, segment_key, metric_value in entity_metrics:
            rows.append((run_id, baseline_id, metric_name, metric_scope, segment_key, float(metric_value), now))
        for segment_value, block in merged.groupby(segment_col, sort=False):
            pred_block = baseline_score_frame(block, baseline_id)
            segment_metrics = [
                ("spearman", "segment", str(segment_value), spearman_corr(block["actual_test_score"], pred_block)),
                ("top3_overlap", "segment", str(segment_value), top_k_overlap(block["actual_test_score"], pred_block, 3)),
                ("ndcg_5", "segment", str(segment_value), ndcg_at_k(block["actual_test_score"], pred_block, 5)),
            ]
            actual_best_seg = float(block["actual_test_score"].max())
            best_seg_idx = pred_block.astype(float).idxmax()
            best_seg_actual = float(block.loc[best_seg_idx, "actual_test_score"])
            segment_metrics.append(("regret_at_1", "segment", str(segment_value), max(0.0, actual_best_seg - best_seg_actual)))
            for metric_name, metric_scope, segment_key, metric_value in segment_metrics:
                rows.append((run_id, baseline_id, metric_name, metric_scope, segment_key, float(metric_value), now))

    cur.executemany(
        """
        INSERT OR REPLACE INTO foundation_optimizer_baseline_reports(
            run_id, baseline_id, metric_name, metric_scope, segment_key, metric_value, created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    con.commit()


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


def build_optimizer_foundation(db_path: Path = DB_PATH) -> dict[str, Any]:
    con = sqlite3.connect(str(db_path))
    try:
        create_schema(con)
        profile_id = default_profile_id(con)
        run_ids: list[str] = []
        summary: list[dict[str, Any]] = []
        for ti2026_only in (False, True):
            for entity_type in ("player", "role_slot"):
                source = load_source(con, entity_type, ti2026_only)
                scored = score_frame(source, entity_type)
                run_id = persist_frame(con, entity_type, profile_id, ti2026_only, scored)
                run_ids.append(run_id)
                actual = build_optimizer_actuals(con, profile_id, entity_type, ti2026_only)
                merged = store_backtest_and_evaluation(con, run_id, entity_type, scored, actual)
                store_baseline_reports(con, run_id, entity_type, merged)
                segment_col = "role_group" if entity_type == "player" else "role_slot"
                summary.append(
                    {
                        "entity_type": entity_type,
                        "ti2026_only": int(ti2026_only),
                        "rows": int(len(scored)),
                        "rows_backtested": int(len(merged)),
                        "segments": int(scored[segment_col].nunique()) if not scored.empty else 0,
                        "avg_optimizer_score": float(scored["optimizer_score_1_100"].mean()) if not scored.empty else 0.0,
                        "spearman": spearman_corr(merged["actual_test_score"], merged["optimizer_raw_score"]) if not merged.empty else 0.0,
                        "top5_overlap": top_k_overlap(merged["actual_test_score"], merged["optimizer_raw_score"], 5) if not merged.empty else 0.0,
                    }
                )
        return {"profile_id": profile_id, "run_ids": run_ids, "summary": pd.DataFrame(summary)}
    finally:
        con.close()


if __name__ == "__main__":
    result = build_optimizer_foundation()
    print(f"profile_id={result['profile_id']}")
    print(f"run_ids={len(result['run_ids'])}")
    print(result["summary"].to_string(index=False))
