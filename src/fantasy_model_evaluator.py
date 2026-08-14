from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from fantasy_prediction_foundation import DB_PATH, ndcg_at_k, safe_float, spearman_corr, top_k_overlap
from project_db import resolve_db_path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = resolve_db_path(PROJECT_ROOT)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class EvalRun:
    evaluation_key: str
    layer_group: str
    surface_family: str
    surface_name: str
    entity_type: str
    task_group: str
    target_id: str | None
    split_name: str | None
    optimizer_scope: str | None
    metric_mode: str
    comparable_flag: int
    notes: str


def create_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS unified_evaluation_runs (
            evaluation_key TEXT PRIMARY KEY,
            layer_group TEXT NOT NULL,
            surface_family TEXT NOT NULL,
            surface_name TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            task_group TEXT NOT NULL,
            target_id TEXT,
            split_name TEXT,
            optimizer_scope TEXT,
            metric_mode TEXT NOT NULL,
            comparable_flag INTEGER NOT NULL,
            notes TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS unified_evaluation_metrics (
            evaluation_key TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            metric_scope TEXT NOT NULL,
            metric_value REAL NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (evaluation_key, metric_name, metric_scope)
        );

        DROP VIEW IF EXISTS analytics_unified_evaluation_metrics;
        CREATE VIEW analytics_unified_evaluation_metrics AS
        SELECT
            r.evaluation_key,
            r.layer_group,
            r.surface_family,
            r.surface_name,
            r.entity_type,
            r.task_group,
            r.target_id,
            r.split_name,
            r.optimizer_scope,
            r.metric_mode,
            r.comparable_flag,
            m.metric_name,
            m.metric_scope,
            m.metric_value,
            r.notes,
            r.created_at_utc
        FROM unified_evaluation_runs r
        JOIN unified_evaluation_metrics m
          ON m.evaluation_key = r.evaluation_key;

        DROP VIEW IF EXISTS analytics_unified_evaluation_summary;
        CREATE VIEW analytics_unified_evaluation_summary AS
        SELECT
            r.evaluation_key,
            r.layer_group,
            r.surface_family,
            r.surface_name,
            r.entity_type,
            r.task_group,
            r.target_id,
            r.split_name,
            r.optimizer_scope,
            r.metric_mode,
            r.comparable_flag,
            MAX(CASE WHEN m.metric_name = 'mae' AND m.metric_scope = 'entity' THEN m.metric_value END) AS mae_entity,
            MAX(CASE WHEN m.metric_name = 'mae' AND m.metric_scope = 'row' THEN m.metric_value END) AS mae_row,
            MAX(CASE WHEN m.metric_name IN ('spearman', 'entity_spearman') AND m.metric_scope = 'entity' THEN m.metric_value END) AS spearman_entity,
            MAX(CASE WHEN m.metric_name = 'top3_overlap' AND m.metric_scope = 'entity' THEN m.metric_value END) AS top3_overlap,
            MAX(CASE WHEN m.metric_name = 'top5_overlap' AND m.metric_scope = 'entity' THEN m.metric_value END) AS top5_overlap,
            MAX(CASE WHEN m.metric_name = 'top10_overlap' AND m.metric_scope = 'entity' THEN m.metric_value END) AS top10_overlap,
            MAX(CASE WHEN m.metric_name = 'ndcg_5' AND m.metric_scope = 'entity' THEN m.metric_value END) AS ndcg_5,
            MAX(CASE WHEN m.metric_name = 'ndcg_10' AND m.metric_scope = 'entity' THEN m.metric_value END) AS ndcg_10,
            MAX(CASE WHEN m.metric_name = 'regret_at_1' AND m.metric_scope = 'entity' THEN m.metric_value END) AS regret_at_1,
            MAX(CASE WHEN m.metric_name = 'avg_p_top1' AND m.metric_scope = 'diagnostic' THEN m.metric_value END) AS avg_p_top1,
            MAX(CASE WHEN m.metric_name = 'avg_p_top3' AND m.metric_scope = 'diagnostic' THEN m.metric_value END) AS avg_p_top3,
            MAX(CASE WHEN m.metric_name = 'avg_p_top5' AND m.metric_scope = 'diagnostic' THEN m.metric_value END) AS avg_p_top5,
            MAX(CASE WHEN m.metric_name = 'avg_simulated_std_score' AND m.metric_scope = 'diagnostic' THEN m.metric_value END) AS avg_simulated_std_score,
            r.notes,
            r.created_at_utc
        FROM unified_evaluation_runs r
        JOIN unified_evaluation_metrics m
          ON m.evaluation_key = r.evaluation_key
        GROUP BY
            r.evaluation_key, r.layer_group, r.surface_family, r.surface_name, r.entity_type, r.task_group,
            r.target_id, r.split_name, r.optimizer_scope, r.metric_mode, r.comparable_flag, r.notes, r.created_at_utc;

        DROP VIEW IF EXISTS analytics_unified_evaluation_leaderboard;
        CREATE VIEW analytics_unified_evaluation_leaderboard AS
        SELECT *
        FROM analytics_unified_evaluation_summary
        ORDER BY
            comparable_flag DESC,
            task_group,
            COALESCE(target_id, ''),
            COALESCE(split_name, ''),
            COALESCE(optimizer_scope, ''),
            spearman_entity DESC,
            ndcg_5 DESC,
            top5_overlap DESC,
            COALESCE(mae_entity, mae_row) ASC,
            regret_at_1 ASC;
        """
    )
    con.commit()


def load_prediction_runs(con: sqlite3.Connection) -> tuple[list[EvalRun], list[tuple[str, str, str, float]]]:
    runs: list[EvalRun] = []
    metrics: list[tuple[str, str, str, float]] = []

    frame = pd.read_sql_query(
        """
        SELECT
            r.run_id AS evaluation_key,
            'prediction' AS layer_group,
            'baseline' AS surface_family,
            r.model_id AS surface_name,
            CASE WHEN r.target_id LIKE 'player_%' THEN 'player' ELSE 'role_slot' END AS entity_type,
            'prediction' AS task_group,
            r.target_id,
            r.split_name,
            NULL AS optimizer_scope,
            'backtest' AS metric_mode,
            1 AS comparable_flag,
            'Prediction foundation baseline evaluation.' AS notes,
            e.metric_name,
            e.metric_scope,
            e.metric_value
        FROM foundation_prediction_runs r
        JOIN foundation_evaluation_reports e
          ON e.run_id = r.run_id
        """,
        con,
    )
    for evaluation_key, block in frame.groupby("evaluation_key", sort=False):
        row = block.iloc[0]
        runs.append(
            EvalRun(
                evaluation_key=evaluation_key,
                layer_group=row["layer_group"],
                surface_family=row["surface_family"],
                surface_name=row["surface_name"],
                entity_type=row["entity_type"],
                task_group=row["task_group"],
                target_id=row["target_id"],
                split_name=row["split_name"],
                optimizer_scope=None,
                metric_mode=row["metric_mode"],
                comparable_flag=int(row["comparable_flag"]),
                notes=row["notes"],
            )
        )
        for metric_row in block.itertuples(index=False):
            metrics.append((evaluation_key, metric_row.metric_name, metric_row.metric_scope, float(metric_row.metric_value)))

    for table_name, run_table, metric_table, family_name, surface_name_expr in [
        ("ridge", "ridge_prediction_runs", "ridge_evaluation_reports", "ridge", "'ridge_v2(alpha=' || CAST(r.alpha AS TEXT) || ')'"),
        ("quantile", "quantile_prediction_runs", "quantile_evaluation_reports", "quantile", "'quantile_linear_v1'"),
        ("gbdt", "gbdt_prediction_runs", "gbdt_evaluation_reports", "gbdt", "'gbdt_rank_v1(trees=' || CAST(r.n_estimators AS TEXT) || ',lr=' || CAST(r.learning_rate AS TEXT) || ')'"),
    ]:
        frame = pd.read_sql_query(
            f"""
            SELECT
                r.run_id AS evaluation_key,
                'prediction' AS layer_group,
                '{family_name}' AS surface_family,
                {surface_name_expr} AS surface_name,
                CASE WHEN r.target_id LIKE 'player_%' THEN 'player' ELSE 'role_slot' END AS entity_type,
                'prediction' AS task_group,
                r.target_id,
                r.split_name,
                NULL AS optimizer_scope,
                'backtest' AS metric_mode,
                1 AS comparable_flag,
                '{table_name} prediction evaluation.' AS notes,
                e.metric_name,
                e.metric_scope,
                e.metric_value
            FROM {run_table} r
            JOIN {metric_table} e
              ON e.run_id = r.run_id
            """,
            con,
        )
        for evaluation_key, block in frame.groupby("evaluation_key", sort=False):
            row = block.iloc[0]
            runs.append(
                EvalRun(
                    evaluation_key=evaluation_key,
                    layer_group=row["layer_group"],
                    surface_family=row["surface_family"],
                    surface_name=row["surface_name"],
                    entity_type=row["entity_type"],
                    task_group=row["task_group"],
                    target_id=row["target_id"],
                    split_name=row["split_name"],
                    optimizer_scope=None,
                    metric_mode=row["metric_mode"],
                    comparable_flag=int(row["comparable_flag"]),
                    notes=row["notes"],
                )
            )
            for metric_row in block.itertuples(index=False):
                metrics.append((evaluation_key, metric_row.metric_name, metric_row.metric_scope, float(metric_row.metric_value)))

    frame = pd.read_sql_query(
        """
        SELECT
            'production::' || target_id || '::' || split_name || '::' || entity_type AS evaluation_key,
            'prediction' AS layer_group,
            'production' AS surface_family,
            chosen_family || '::' || chosen_model_id AS surface_name,
            entity_type,
            'prediction' AS task_group,
            target_id,
            split_name,
            NULL AS optimizer_scope,
            'backtest' AS metric_mode,
            1 AS comparable_flag,
            selection_reason AS notes,
            metric_entity_spearman,
            metric_ndcg_5,
            metric_top5_overlap,
            metric_mae,
            metric_regret_at_1
        FROM analytics_prediction_production_model_choices
        """,
        con,
    )
    for row in frame.itertuples(index=False):
        runs.append(
            EvalRun(
                evaluation_key=row.evaluation_key,
                layer_group=row.layer_group,
                surface_family=row.surface_family,
                surface_name=row.surface_name,
                entity_type=row.entity_type,
                task_group=row.task_group,
                target_id=row.target_id,
                split_name=row.split_name,
                optimizer_scope=None,
                metric_mode=row.metric_mode,
                comparable_flag=int(row.comparable_flag),
                notes=row.notes,
            )
        )
        metrics.extend(
            [
                (row.evaluation_key, "entity_spearman", "entity", float(row.metric_entity_spearman)),
                (row.evaluation_key, "ndcg_5", "entity", float(row.metric_ndcg_5)),
                (row.evaluation_key, "top5_overlap", "entity", float(row.metric_top5_overlap)),
                (row.evaluation_key, "mae", "entity", float(row.metric_mae)),
                (row.evaluation_key, "regret_at_1", "entity", float(row.metric_regret_at_1)),
            ]
        )

    return runs, metrics


def load_reliability_runs(con: sqlite3.Connection) -> tuple[list[EvalRun], list[tuple[str, str, str, float]]]:
    runs: list[EvalRun] = []
    metrics: list[tuple[str, str, str, float]] = []
    backtest = pd.read_sql_query(
        """
        SELECT
            r.run_id,
            r.entity_type,
            b.segment_key,
            b.entity_key,
            b.predicted_score,
            b.actual_test_score
        FROM foundation_reliability_backtest b
        JOIN foundation_reliability_runs r
          ON r.run_id = b.run_id
        ORDER BY r.run_id, b.segment_key, b.entity_key
        """,
        con,
    )
    for (run_id, entity_type), block in backtest.groupby(["run_id", "entity_type"], sort=False):
        evaluation_key = f"eval::{run_id}"
        runs.append(
            EvalRun(
                evaluation_key=evaluation_key,
                layer_group="reliability",
                surface_family="reliability_foundation",
                surface_name=run_id.split("::")[-1],
                entity_type=entity_type,
                task_group="reliability",
                target_id=None,
                split_name="group_to_playoff",
                optimizer_scope="all",
                metric_mode="backtest",
                comparable_flag=1,
                notes="Reliability foundation backtest against non-group-stage blended actuals.",
            )
        )
        actual = block["actual_test_score"].astype(float)
        predicted = block["predicted_score"].astype(float)
        metrics.extend(
            [
                (evaluation_key, "mae", "entity", float((actual - predicted).abs().mean())),
                (evaluation_key, "spearman", "entity", spearman_corr(actual, predicted)),
                (evaluation_key, "top3_overlap", "entity", top_k_overlap(actual, predicted, 3)),
                (evaluation_key, "top5_overlap", "entity", top_k_overlap(actual, predicted, 5)),
                (evaluation_key, "top10_overlap", "entity", top_k_overlap(actual, predicted, 10)),
                (evaluation_key, "ndcg_5", "entity", ndcg_at_k(actual, predicted, 5)),
                (evaluation_key, "ndcg_10", "entity", ndcg_at_k(actual, predicted, 10)),
            ]
        )
        predicted_best_key = block.loc[predicted.idxmax(), "entity_key"] if not block.empty else None
        if predicted_best_key is not None:
            picked_actual = safe_float(block.loc[block["entity_key"] == predicted_best_key, "actual_test_score"].iloc[0])
            metrics.append((evaluation_key, "regret_at_1", "entity", float(actual.max() - picked_actual)))
    return runs, metrics


def load_optimizer_runs(con: sqlite3.Connection) -> tuple[list[EvalRun], list[tuple[str, str, str, float]]]:
    runs: list[EvalRun] = []
    metrics: list[tuple[str, str, str, float]] = []
    for view_name, family in [
        ("analytics_optimizer_foundation_evaluation", "optimizer_foundation"),
        ("analytics_optimizer_v2_evaluation", "optimizer_v2"),
    ]:
        frame = pd.read_sql_query(
            f"""
            SELECT run_id, entity_type, optimizer_scope, metric_name, metric_scope, metric_value
            FROM {view_name}
            """,
            con,
        )
        for (run_id, entity_type, optimizer_scope), block in frame.groupby(["run_id", "entity_type", "optimizer_scope"], sort=False):
            evaluation_key = f"eval::{run_id}"
            runs.append(
                EvalRun(
                    evaluation_key=evaluation_key,
                    layer_group="optimizer",
                    surface_family=family,
                    surface_name=run_id.split("::")[-1],
                    entity_type=entity_type,
                    task_group="optimizer",
                    target_id=None,
                    split_name="group_to_playoff",
                    optimizer_scope=optimizer_scope,
                    metric_mode="backtest",
                    comparable_flag=1,
                    notes=f"{family} backtest metrics.",
                )
            )
            for metric_row in block.itertuples(index=False):
                metrics.append((evaluation_key, metric_row.metric_name, metric_row.metric_scope, float(metric_row.metric_value)))
    return runs, metrics


def load_monte_carlo_diagnostics(con: sqlite3.Connection) -> tuple[list[EvalRun], list[tuple[str, str, str, float]]]:
    runs: list[EvalRun] = []
    metrics: list[tuple[str, str, str, float]] = []
    frame = pd.read_sql_query(
        """
        SELECT
            r.run_id,
            r.target_id,
            r.split_name,
            r.entity_type,
            AVG(x.p_top1) AS avg_p_top1,
            AVG(x.p_top3) AS avg_p_top3,
            AVG(x.p_top5) AS avg_p_top5,
            AVG(x.simulated_std_score) AS avg_simulated_std_score
        FROM production_monte_carlo_runs r
        JOIN production_monte_carlo_entity_results x
          ON x.run_id = r.run_id
        GROUP BY r.run_id, r.target_id, r.split_name, r.entity_type
        """,
        con,
    )
    for row in frame.itertuples(index=False):
        evaluation_key = f"diag::{row.run_id}"
        runs.append(
            EvalRun(
                evaluation_key=evaluation_key,
                layer_group="simulation",
                surface_family="monte_carlo",
                surface_name="production_monte_carlo",
                entity_type=row.entity_type,
                task_group="simulation",
                target_id=row.target_id,
                split_name=row.split_name,
                optimizer_scope=None,
                metric_mode="diagnostic_only",
                comparable_flag=0,
                notes="Monte Carlo diagnostic layer built on top of production predictions.",
            )
        )
        metrics.extend(
            [
                (evaluation_key, "avg_p_top1", "diagnostic", float(row.avg_p_top1)),
                (evaluation_key, "avg_p_top3", "diagnostic", float(row.avg_p_top3)),
                (evaluation_key, "avg_p_top5", "diagnostic", float(row.avg_p_top5)),
                (evaluation_key, "avg_simulated_std_score", "diagnostic", float(row.avg_simulated_std_score)),
            ]
        )
    return runs, metrics


def store(con: sqlite3.Connection, runs: list[EvalRun], metrics: list[tuple[str, str, str, float]]) -> None:
    con.execute("DELETE FROM unified_evaluation_metrics")
    con.execute("DELETE FROM unified_evaluation_runs")
    now = utc_now()
    con.executemany(
        """
        INSERT INTO unified_evaluation_runs(
            evaluation_key, layer_group, surface_family, surface_name, entity_type, task_group,
            target_id, split_name, optimizer_scope, metric_mode, comparable_flag, notes, created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                run.evaluation_key,
                run.layer_group,
                run.surface_family,
                run.surface_name,
                run.entity_type,
                run.task_group,
                run.target_id,
                run.split_name,
                run.optimizer_scope,
                run.metric_mode,
                run.comparable_flag,
                run.notes,
                now,
            )
            for run in runs
        ],
    )
    con.executemany(
        """
        INSERT INTO unified_evaluation_metrics(
            evaluation_key, metric_name, metric_scope, metric_value, created_at_utc
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        [(evaluation_key, metric_name, metric_scope, float(metric_value), now) for evaluation_key, metric_name, metric_scope, metric_value in metrics],
    )
    con.commit()


def build_unified_evaluation(db_path: Path = DB_PATH) -> dict[str, Any]:
    con = sqlite3.connect(str(db_path))
    try:
        create_schema(con)
        runs: list[EvalRun] = []
        metrics: list[tuple[str, str, str, float]] = []
        for loader in [
            load_prediction_runs,
            load_reliability_runs,
            load_optimizer_runs,
            load_monte_carlo_diagnostics,
        ]:
            sub_runs, sub_metrics = loader(con)
            runs.extend(sub_runs)
            metrics.extend(sub_metrics)
        store(con, runs, metrics)
        summary = pd.read_sql_query(
            """
            SELECT *
            FROM analytics_unified_evaluation_leaderboard
            """,
            con,
        )
        return {
            "runs_written": len(runs),
            "metrics_written": len(metrics),
            "summary": summary,
        }
    finally:
        con.close()
