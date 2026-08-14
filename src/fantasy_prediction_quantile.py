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


MODEL_ID = "quantile_linear_v1"
FEATURE_COLUMNS = feature_columns()
QUANTILES = (0.25, 0.50, 0.75, 0.90)
DEFAULT_L2 = 0.01
DEFAULT_EPOCHS = 450
DEFAULT_LR = 0.03


def create_quantile_schema(con: sqlite3.Connection) -> None:
    create_schema(con)
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS quantile_prediction_runs (
            run_id TEXT PRIMARY KEY,
            target_id TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            split_name TEXT NOT NULL,
            model_id TEXT NOT NULL,
            feature_set TEXT NOT NULL,
            quantiles TEXT NOT NULL,
            train_label TEXT NOT NULL,
            test_label TEXT NOT NULL,
            notes TEXT,
            created_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS quantile_prediction_outputs (
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
            q25 REAL NOT NULL,
            q50 REAL NOT NULL,
            q75 REAL NOT NULL,
            q90 REAL NOT NULL,
            abs_error REAL NOT NULL,
            train_rows_used INTEGER NOT NULL,
            fallback_label TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, entity_key, observation_key)
        );

        CREATE TABLE IF NOT EXISTS quantile_evaluation_reports (
            run_id TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            metric_value REAL NOT NULL,
            metric_scope TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, metric_name, metric_scope)
        );

        DROP VIEW IF EXISTS analytics_prediction_quantile_evaluation;
        CREATE VIEW analytics_prediction_quantile_evaluation AS
        SELECT
            r.run_id,
            r.target_id,
            r.profile_id,
            r.split_name,
            r.model_id,
            r.feature_set,
            r.quantiles,
            e.metric_name,
            e.metric_value,
            e.metric_scope,
            r.created_at_utc
        FROM quantile_prediction_runs r
        JOIN quantile_evaluation_reports e
          ON e.run_id = r.run_id;
        """
    )
    con.commit()


def standardize(train_features: pd.DataFrame, scored_features: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    X_train = train_features[FEATURE_COLUMNS].astype(float).to_numpy()
    X_scored = scored_features[FEATURE_COLUMNS].astype(float).to_numpy()
    x_mean = X_train.mean(axis=0)
    x_std = X_train.std(axis=0)
    x_std[x_std == 0.0] = 1.0
    return (X_train - x_mean) / x_std, (X_scored - x_mean) / x_std


def fit_quantile_linear(
    X: np.ndarray,
    y: np.ndarray,
    q: float,
    *,
    l2: float = DEFAULT_L2,
    epochs: int = DEFAULT_EPOCHS,
    lr: float = DEFAULT_LR,
) -> tuple[np.ndarray, float]:
    w = np.zeros(X.shape[1], dtype=float)
    b = float(np.median(y)) if len(y) else 0.0
    n = max(1, len(y))
    for epoch in range(epochs):
        pred = X @ w + b
        err = y - pred
        grad_sign = np.where(err > 0.0, -q, 1.0 - q)
        step = lr / np.sqrt(epoch + 1.0)
        grad_w = (X.T @ grad_sign) / n + l2 * w
        grad_b = float(np.mean(grad_sign))
        w -= step * grad_w
        b -= step * grad_b
    return w, b


def pinball_loss(y: np.ndarray, pred: np.ndarray, q: float) -> float:
    err = y - pred
    return float(np.mean(np.maximum(q * err, (q - 1.0) * err)))


def quantile_metrics(frame: pd.DataFrame) -> list[tuple[str, float, str]]:
    actual = frame["actual_score"].astype(float).to_numpy()
    q25 = frame["q25"].astype(float).to_numpy()
    q50 = frame["q50"].astype(float).to_numpy()
    q75 = frame["q75"].astype(float).to_numpy()
    q90 = frame["q90"].astype(float).to_numpy()
    return [
        ("pinball_q25", pinball_loss(actual, q25, 0.25), "row"),
        ("pinball_q50", pinball_loss(actual, q50, 0.50), "row"),
        ("pinball_q75", pinball_loss(actual, q75, 0.75), "row"),
        ("pinball_q90", pinball_loss(actual, q90, 0.90), "row"),
        ("coverage_q25", float(np.mean(actual <= q25)), "row"),
        ("coverage_q50", float(np.mean(actual <= q50)), "row"),
        ("coverage_q75", float(np.mean(actual <= q75)), "row"),
        ("coverage_q90", float(np.mean(actual <= q90)), "row"),
        ("band_width_q25_q75", float(np.mean(q75 - q25)), "row"),
    ]


def build_predictions_for_run(
    target_id: str,
    profile_id: str,
    split_name: str,
    train: pd.DataFrame,
    test: pd.DataFrame,
) -> pd.DataFrame:
    if train.empty or test.empty:
        return test.iloc[0:0].copy()
    train = with_team_segment_key(train)
    test = with_team_segment_key(test)
    train_features = build_feature_frame(train, train)
    test_features = build_feature_frame(train, test)
    X_train, X_test = standardize(train_features, test_features)
    y_train = train["target_score"].astype(float).to_numpy()

    preds: dict[float, np.ndarray] = {}
    for q in QUANTILES:
        w, b = fit_quantile_linear(X_train, y_train, q)
        preds[q] = X_test @ w + b

    rows: list[dict[str, Any]] = []
    for idx, (_, row) in enumerate(test.iterrows()):
        q25 = safe_float(preds[0.25][idx])
        q50 = safe_float(preds[0.50][idx])
        q75 = safe_float(preds[0.75][idx])
        q90 = safe_float(preds[0.90][idx])
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
                "predicted_score": q50,
                "q25": min(q25, q50),
                "q50": q50,
                "q75": max(q50, q75),
                "q90": max(max(q50, q75), q90),
                "abs_error": abs(safe_float(row["target_score"]) - q50),
                "train_rows_used": int(test_features.iloc[idx]["train_count"]) if idx < len(test_features) else 0,
                "fallback_label": MODEL_ID,
            }
        )
    return pd.DataFrame(rows)


def store_run(
    con: sqlite3.Connection,
    target_id: str,
    profile_id: str,
    split_name: str,
    train_label: str,
    test_label: str,
    predictions: pd.DataFrame,
) -> str:
    run_id = f"quantile::{target_id}::{split_name}::{MODEL_ID}"
    now = utc_now()
    cur = con.cursor()
    cur.execute("DELETE FROM quantile_prediction_outputs WHERE run_id = ?", (run_id,))
    cur.execute("DELETE FROM quantile_evaluation_reports WHERE run_id = ?", (run_id,))
    cur.execute("DELETE FROM quantile_prediction_runs WHERE run_id = ?", (run_id,))
    cur.execute(
        """
        INSERT INTO quantile_prediction_runs(
            run_id, target_id, profile_id, split_name, model_id, feature_set, quantiles,
            train_label, test_label, notes, created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            target_id,
            profile_id,
            split_name,
            MODEL_ID,
            ",".join(FEATURE_COLUMNS),
            ",".join(str(q) for q in QUANTILES),
            train_label,
            test_label,
            "Linear quantile layer with richer shared features. q50 acts as the point estimate; q25/q75/q90 expose uncertainty structure.",
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
                    float(row.q25),
                    float(row.q50),
                    float(row.q75),
                    float(row.q90),
                    float(row.abs_error),
                    int(row.train_rows_used),
                    row.fallback_label,
                    now,
                )
            )
        cur.executemany(
            """
            INSERT OR REPLACE INTO quantile_prediction_outputs(
                run_id, target_id, profile_id, split_name, model_id, entity_type, entity_key, observation_key,
                team_name, official_name, official_position, role_group, role_slot, player_names, account_id,
                account_ids, match_id, series_key, series_id, observation_date, stage_bucket, actual_score,
                predicted_score, q25, q50, q75, q90, abs_error, train_rows_used, fallback_label, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    for metric_name, metric_value, metric_scope in compute_run_metrics(predictions):
        cur.execute(
            """
            INSERT OR REPLACE INTO quantile_evaluation_reports(run_id, metric_name, metric_value, metric_scope, created_at_utc)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, metric_name, float(metric_value), metric_scope, now),
        )
    for metric_name, metric_value, metric_scope in quantile_metrics(predictions):
        cur.execute(
            """
            INSERT OR REPLACE INTO quantile_evaluation_reports(run_id, metric_name, metric_value, metric_scope, created_at_utc)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, metric_name, float(metric_value), metric_scope, now),
        )
    con.commit()
    return run_id


def build_prediction_quantile(db_path: Path = DB_PATH) -> dict[str, Any]:
    con = sqlite3.connect(str(db_path))
    try:
        create_quantile_schema(con)
        profile_id = default_profile_id(con)
        con.execute("DELETE FROM quantile_prediction_outputs")
        con.execute("DELETE FROM quantile_evaluation_reports")
        con.execute("DELETE FROM quantile_prediction_runs")
        con.commit()
        run_ids: list[str] = []
        for spec in TARGET_SPECS:
            df = load_target_dataset(con, spec.target_id, profile_id)
            for split in SPLITS:
                train, test = build_split(df, split.split_name)
                if train.empty or test.empty:
                    continue
                preds = build_predictions_for_run(spec.target_id, profile_id, split.split_name, train, test)
                run_ids.append(store_run(con, spec.target_id, profile_id, split.split_name, split.train_label, split.test_label, preds))
        summary = pd.read_sql_query(
            """
            SELECT
                r.target_id,
                r.split_name,
                MAX(CASE WHEN e.metric_name = 'mae' THEN e.metric_value END) AS mae,
                MAX(CASE WHEN e.metric_name = 'entity_spearman' THEN e.metric_value END) AS spearman_entity,
                MAX(CASE WHEN e.metric_name = 'pinball_q75' THEN e.metric_value END) AS pinball_q75,
                MAX(CASE WHEN e.metric_name = 'coverage_q75' THEN e.metric_value END) AS coverage_q75,
                MAX(CASE WHEN e.metric_name = 'band_width_q25_q75' THEN e.metric_value END) AS band_width_q25_q75
            FROM quantile_prediction_runs r
            JOIN quantile_evaluation_reports e
              ON e.run_id = r.run_id
            WHERE r.profile_id = ?
            GROUP BY r.target_id, r.split_name
            ORDER BY r.target_id, r.split_name
            """,
            con,
            params=(profile_id,),
        )
        return {"profile_id": profile_id, "run_ids": run_ids, "summary": summary}
    finally:
        con.close()
