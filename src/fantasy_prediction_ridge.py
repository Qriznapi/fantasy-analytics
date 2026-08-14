from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from fantasy_prediction_features import build_feature_frame, feature_columns, with_team_segment_key
from fantasy_prediction_foundation import (
    DB_PATH,
    SPLITS,
    TARGET_SPECS,
    build_split,
    compute_run_metrics,
    create_schema,
    default_profile_id,
    load_target_dataset,
    safe_float,
    utc_now,
)


MODEL_ID = "ridge_v2"
DEFAULT_ALPHA_GRID = (0.25, 0.5, 1.0, 2.0, 5.0, 12.0, 25.0, 50.0, 100.0)
FEATURE_COLUMNS = feature_columns()


def create_ridge_schema(con: sqlite3.Connection) -> None:
    create_schema(con)
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS ridge_prediction_runs (
            run_id TEXT PRIMARY KEY,
            target_id TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            split_name TEXT NOT NULL,
            model_id TEXT NOT NULL,
            alpha REAL NOT NULL,
            tuned_on_split TEXT NOT NULL,
            feature_set TEXT NOT NULL,
            train_label TEXT NOT NULL,
            test_label TEXT NOT NULL,
            notes TEXT,
            created_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS ridge_prediction_outputs (
            run_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            split_name TEXT NOT NULL,
            model_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_key TEXT NOT NULL,
            observation_key TEXT NOT NULL,
            team_name TEXT NOT NULL,
            official_name TEXT,
            official_position INTEGER,
            role_group TEXT,
            role_slot TEXT,
            player_names TEXT,
            account_id INTEGER,
            account_ids TEXT,
            match_id INTEGER,
            series_key TEXT,
            series_id INTEGER,
            observation_date TEXT,
            stage_bucket TEXT,
            actual_score REAL NOT NULL,
            predicted_score REAL NOT NULL,
            abs_error REAL NOT NULL,
            train_rows_used INTEGER NOT NULL,
            fallback_label TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, entity_key, observation_key)
        );

        CREATE TABLE IF NOT EXISTS ridge_evaluation_reports (
            run_id TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            metric_value REAL NOT NULL,
            metric_scope TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, metric_name, metric_scope)
        );

        CREATE TABLE IF NOT EXISTS ridge_tuning_reports (
            run_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            split_name TEXT NOT NULL,
            alpha REAL NOT NULL,
            metric_name TEXT NOT NULL,
            metric_value REAL NOT NULL,
            metric_scope TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, alpha, metric_name, metric_scope)
        );

        DROP VIEW IF EXISTS analytics_prediction_ridge_evaluation;
        CREATE VIEW analytics_prediction_ridge_evaluation AS
        SELECT
            r.run_id,
            r.target_id,
            r.profile_id,
            r.split_name,
            r.model_id,
            r.alpha,
            r.tuned_on_split,
            r.feature_set,
            e.metric_name,
            e.metric_value,
            e.metric_scope,
            r.created_at_utc
        FROM ridge_prediction_runs r
        JOIN ridge_evaluation_reports e
          ON e.run_id = r.run_id;

        DROP VIEW IF EXISTS analytics_prediction_ridge_tuning;
        CREATE VIEW analytics_prediction_ridge_tuning AS
        SELECT
            t.run_id,
            t.target_id,
            t.split_name,
            t.alpha,
            t.metric_name,
            t.metric_value,
            t.metric_scope,
            r.model_id,
            r.tuned_on_split,
            r.created_at_utc
        FROM ridge_tuning_reports t
        JOIN ridge_prediction_runs r
          ON r.run_id = t.run_id;
        """
    )
    existing = {
        str(row[1]): str(row[2]).upper()
        for row in con.execute("PRAGMA table_info(ridge_prediction_runs)").fetchall()
    }
    if "tuned_on_split" not in existing:
        con.execute("ALTER TABLE ridge_prediction_runs ADD COLUMN tuned_on_split TEXT NOT NULL DEFAULT 'legacy_unknown'")
    con.commit()


def inner_validation_split(train: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_parts: list[pd.DataFrame] = []
    val_parts: list[pd.DataFrame] = []
    for _, group in train.groupby("entity_key", sort=False):
        group = group.sort_values(["observation_date", "observation_key"]).reset_index(drop=True)
        if len(group) < 3:
            continue
        cut = max(1, int(np.floor(len(group) * 0.75)))
        if cut >= len(group):
            cut = len(group) - 1
        train_parts.append(group.iloc[:cut].copy())
        val_parts.append(group.iloc[cut:].copy())
    if not train_parts or not val_parts:
        return train.iloc[0:0].copy(), train.iloc[0:0].copy()
    return pd.concat(train_parts, ignore_index=True), pd.concat(val_parts, ignore_index=True)


def fit_ridge(X: np.ndarray, y: np.ndarray, alpha: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    x_mean = X.mean(axis=0)
    x_std = X.std(axis=0)
    x_std[x_std == 0.0] = 1.0
    y_mean = float(y.mean()) if len(y) else 0.0
    Xs = (X - x_mean) / x_std
    yc = y - y_mean
    penalty = alpha * np.eye(Xs.shape[1], dtype=float)
    coef = np.linalg.solve(Xs.T @ Xs + penalty, Xs.T @ yc)
    return coef, x_mean, x_std, y_mean


def predict_ridge(X: np.ndarray, coef: np.ndarray, x_mean: np.ndarray, x_std: np.ndarray, y_mean: float) -> np.ndarray:
    Xs = (X - x_mean) / x_std
    return y_mean + Xs @ coef


def predict_frame(train: pd.DataFrame, scored: pd.DataFrame, alpha: float) -> tuple[np.ndarray, pd.DataFrame]:
    train = with_team_segment_key(train)
    scored = with_team_segment_key(scored)
    train_features = build_feature_frame(train, train)
    scored_features = build_feature_frame(train, scored)
    X_train = train_features[FEATURE_COLUMNS].astype(float).to_numpy()
    y_train = train["target_score"].astype(float).to_numpy()
    coef, x_mean, x_std, y_mean = fit_ridge(X_train, y_train, alpha)
    preds = predict_ridge(scored_features[FEATURE_COLUMNS].astype(float).to_numpy(), coef, x_mean, x_std, y_mean)
    return preds, scored_features


def build_predictions_for_run(
    target_id: str,
    profile_id: str,
    split_name: str,
    train: pd.DataFrame,
    test: pd.DataFrame,
    alpha: float,
) -> pd.DataFrame:
    if train.empty or test.empty:
        return test.iloc[0:0].copy()
    preds, test_features = predict_frame(train, test, alpha)
    rows: list[dict[str, Any]] = []
    for idx, (_, row) in enumerate(test.iterrows()):
        rows.append(
            {
                "target_id": target_id,
                "profile_id": profile_id,
                "split_name": split_name,
                "model_id": MODEL_ID,
                "entity_type": row["entity_type"],
                "entity_key": row["entity_key"],
                "observation_key": row["observation_key"],
                "team_name": row["team_name"],
                "official_name": row["official_name"],
                "official_position": row["official_position"],
                "role_group": row["role_group"],
                "role_slot": row["role_slot"],
                "player_names": row["player_names"],
                "account_id": row["account_id"],
                "account_ids": row["account_ids"],
                "match_id": row["match_id"],
                "series_key": row["series_key"],
                "series_id": row["series_id"],
                "observation_date": row["observation_date"],
                "stage_bucket": row["stage_bucket"],
                "actual_score": safe_float(row["target_score"]),
                "predicted_score": safe_float(preds[idx]),
                "abs_error": abs(safe_float(row["target_score"]) - safe_float(preds[idx])),
                "train_rows_used": int(test_features.iloc[idx]["train_count"]) if idx < len(test_features) else 0,
                "fallback_label": MODEL_ID,
            }
        )
    return pd.DataFrame(rows)


def alpha_sort_key(metrics: dict[str, float]) -> tuple[float, float, float, float]:
    return (
        safe_float(metrics.get("entity_spearman"), 0.0),
        safe_float(metrics.get("ndcg_5"), 0.0),
        safe_float(metrics.get("top5_overlap"), 0.0),
        -safe_float(metrics.get("mae"), 1e18),
    )


def tune_alpha(train: pd.DataFrame, alpha_grid: tuple[float, ...]) -> tuple[float, list[dict[str, float]]]:
    inner_train, inner_val = inner_validation_split(train)
    if inner_train.empty or inner_val.empty:
        return float(alpha_grid[0]), []
    tuning_rows: list[dict[str, float]] = []
    best_alpha = float(alpha_grid[0])
    best_key = (-1e18, -1e18, -1e18, -1e18)
    for alpha in alpha_grid:
        preds = build_predictions_for_run(
            target_id="tuning",
            profile_id="tuning",
            split_name="inner_validation",
            train=inner_train,
            test=inner_val,
            alpha=float(alpha),
        )
        metrics = {f"{scope}::{name}": value for name, value, scope in compute_run_metrics(preds)}
        row = {
            "alpha": float(alpha),
            "mae": safe_float(metrics.get("row::mae")),
            "spearman_row": safe_float(metrics.get("row::spearman")),
            "entity_spearman": safe_float(metrics.get("entity::entity_spearman")),
            "top5_overlap": safe_float(metrics.get("entity::top5_overlap")),
            "ndcg_5": safe_float(metrics.get("entity::ndcg_5")),
            "regret_at_1": safe_float(metrics.get("entity::regret_at_1")),
        }
        tuning_rows.append(row)
        current_key = alpha_sort_key(row)
        if current_key > best_key:
            best_key = current_key
            best_alpha = float(alpha)
    return best_alpha, tuning_rows


def store_run(
    con: sqlite3.Connection,
    target_id: str,
    profile_id: str,
    split_name: str,
    train_label: str,
    test_label: str,
    alpha: float,
    tuning_rows: list[dict[str, float]],
    predictions: pd.DataFrame,
) -> str:
    run_id = f"ridge::{target_id}::{split_name}::{MODEL_ID}"
    now = utc_now()
    cur = con.cursor()
    cur.execute("DELETE FROM ridge_prediction_outputs WHERE run_id = ?", (run_id,))
    cur.execute("DELETE FROM ridge_evaluation_reports WHERE run_id = ?", (run_id,))
    cur.execute("DELETE FROM ridge_tuning_reports WHERE run_id = ?", (run_id,))
    cur.execute("DELETE FROM ridge_prediction_runs WHERE run_id = ?", (run_id,))
    cur.execute(
        """
        INSERT INTO ridge_prediction_runs(
            run_id, target_id, profile_id, split_name, model_id, alpha, tuned_on_split,
            feature_set, train_label, test_label, notes, created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            target_id,
            profile_id,
            split_name,
            MODEL_ID,
            float(alpha),
            "entity_temporal_75_25_inside_train",
            ",".join(FEATURE_COLUMNS),
            train_label,
            test_label,
            "Ridge v2 uses tuned alpha plus richer entity/recent/segment interaction features from the map-first target dataset.",
            now,
        ),
    )
    if not predictions.empty:
        rows = []
        for row in predictions.itertuples(index=False):
            rows.append(
                (
                    run_id,
                    row.target_id,
                    row.profile_id,
                    row.split_name,
                    row.model_id,
                    row.entity_type,
                    row.entity_key,
                    row.observation_key,
                    row.team_name,
                    row.official_name,
                    None if pd.isna(row.official_position) else int(row.official_position),
                    row.role_group,
                    row.role_slot,
                    row.player_names,
                    None if pd.isna(row.account_id) else int(row.account_id),
                    row.account_ids,
                    None if pd.isna(row.match_id) else int(row.match_id),
                    row.series_key,
                    None if pd.isna(row.series_id) else int(row.series_id),
                    None if pd.isna(row.observation_date) else str(pd.Timestamp(row.observation_date).date()),
                    row.stage_bucket,
                    float(row.actual_score),
                    float(row.predicted_score),
                    float(row.abs_error),
                    int(row.train_rows_used),
                    row.fallback_label,
                    now,
                )
            )
        cur.executemany(
            """
            INSERT OR REPLACE INTO ridge_prediction_outputs(
                run_id, target_id, profile_id, split_name, model_id, entity_type, entity_key, observation_key,
                team_name, official_name, official_position, role_group, role_slot, player_names, account_id,
                account_ids, match_id, series_key, series_id, observation_date, stage_bucket, actual_score,
                predicted_score, abs_error, train_rows_used, fallback_label, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    for metric_name, metric_value, metric_scope in compute_run_metrics(predictions):
        cur.execute(
            """
            INSERT OR REPLACE INTO ridge_evaluation_reports(run_id, metric_name, metric_value, metric_scope, created_at_utc)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, metric_name, float(metric_value), metric_scope, now),
        )
    for row in tuning_rows:
        for metric_name in ["mae", "spearman_row", "entity_spearman", "top5_overlap", "ndcg_5", "regret_at_1"]:
            metric_scope = "row" if metric_name in {"mae", "spearman_row"} else "entity"
            cur.execute(
                """
                INSERT OR REPLACE INTO ridge_tuning_reports(
                    run_id, target_id, split_name, alpha, metric_name, metric_value, metric_scope, created_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    target_id,
                    split_name,
                    float(row["alpha"]),
                    metric_name,
                    float(row[metric_name]),
                    metric_scope,
                    now,
                ),
            )
    con.commit()
    return run_id


def build_prediction_ridge(
    db_path: Path = DB_PATH,
    alpha_grid: tuple[float, ...] = DEFAULT_ALPHA_GRID,
) -> dict[str, Any]:
    con = sqlite3.connect(str(db_path))
    try:
        create_ridge_schema(con)
        profile_id = default_profile_id(con)
        con.execute("DELETE FROM ridge_prediction_outputs")
        con.execute("DELETE FROM ridge_evaluation_reports")
        con.execute("DELETE FROM ridge_tuning_reports")
        con.execute("DELETE FROM ridge_prediction_runs")
        con.commit()
        run_ids: list[str] = []
        chosen: list[dict[str, Any]] = []
        for spec in TARGET_SPECS:
            df = load_target_dataset(con, spec.target_id, profile_id)
            for split in SPLITS:
                train, test = build_split(df, split.split_name)
                if train.empty or test.empty:
                    continue
                alpha, tuning_rows = tune_alpha(train, tuple(float(a) for a in alpha_grid))
                preds = build_predictions_for_run(spec.target_id, profile_id, split.split_name, train, test, alpha)
                run_ids.append(
                    store_run(
                        con,
                        spec.target_id,
                        profile_id,
                        split.split_name,
                        split.train_label,
                        split.test_label,
                        alpha,
                        tuning_rows,
                        preds,
                    )
                )
                chosen.append(
                    {
                        "target_id": spec.target_id,
                        "split_name": split.split_name,
                        "selected_alpha": alpha,
                    }
                )
        summary = pd.read_sql_query(
            """
            SELECT
                r.target_id,
                r.split_name,
                r.model_id,
                r.alpha,
                MAX(CASE WHEN e.metric_name = 'mae' AND e.metric_scope = 'row' THEN e.metric_value END) AS mae,
                MAX(CASE WHEN e.metric_name = 'spearman' AND e.metric_scope = 'row' THEN e.metric_value END) AS spearman_row,
                MAX(CASE WHEN e.metric_name = 'entity_spearman' AND e.metric_scope = 'entity' THEN e.metric_value END) AS spearman_entity,
                MAX(CASE WHEN e.metric_name = 'top5_overlap' AND e.metric_scope = 'entity' THEN e.metric_value END) AS top5_overlap,
                MAX(CASE WHEN e.metric_name = 'regret_at_1' AND e.metric_scope = 'entity' THEN e.metric_value END) AS regret_at_1
            FROM ridge_prediction_runs r
            JOIN ridge_evaluation_reports e
              ON e.run_id = r.run_id
            WHERE r.profile_id = ?
            GROUP BY r.target_id, r.split_name, r.model_id, r.alpha
            ORDER BY r.target_id, r.split_name
            """,
            con,
            params=(profile_id,),
        )
        return {
            "profile_id": profile_id,
            "run_ids": run_ids,
            "summary": summary,
            "selected_alphas": pd.DataFrame(chosen),
        }
    finally:
        con.close()
