from __future__ import annotations

import sqlite3
from dataclasses import dataclass
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


MODEL_ID = "gbdt_rank_v1"
FEATURE_COLUMNS = feature_columns()
DEFAULT_PARAM_GRID = (
    (16, 0.05),
    (24, 0.05),
    (24, 0.08),
    (40, 0.05),
    (40, 0.08),
)


@dataclass
class Stump:
    feature_idx: int
    threshold: float
    left_value: float
    right_value: float
    gain: float

    def predict(self, X: np.ndarray) -> np.ndarray:
        mask = X[:, self.feature_idx] <= self.threshold
        out = np.full(X.shape[0], self.right_value, dtype=float)
        out[mask] = self.left_value
        return out


def create_gbdt_schema(con: sqlite3.Connection) -> None:
    create_schema(con)
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS gbdt_prediction_runs (
            run_id TEXT PRIMARY KEY,
            target_id TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            split_name TEXT NOT NULL,
            model_id TEXT NOT NULL,
            n_estimators INTEGER NOT NULL,
            learning_rate REAL NOT NULL,
            feature_set TEXT NOT NULL,
            train_label TEXT NOT NULL,
            test_label TEXT NOT NULL,
            notes TEXT,
            created_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS gbdt_prediction_outputs (
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

        CREATE TABLE IF NOT EXISTS gbdt_evaluation_reports (
            run_id TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            metric_value REAL NOT NULL,
            metric_scope TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, metric_name, metric_scope)
        );

        CREATE TABLE IF NOT EXISTS gbdt_tuning_reports (
            run_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            split_name TEXT NOT NULL,
            n_estimators INTEGER NOT NULL,
            learning_rate REAL NOT NULL,
            metric_name TEXT NOT NULL,
            metric_value REAL NOT NULL,
            metric_scope TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, n_estimators, learning_rate, metric_name, metric_scope)
        );

        CREATE TABLE IF NOT EXISTS gbdt_feature_importance (
            run_id TEXT NOT NULL,
            feature_name TEXT NOT NULL,
            total_gain REAL NOT NULL,
            split_count INTEGER NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, feature_name)
        );

        DROP VIEW IF EXISTS analytics_prediction_gbdt_evaluation;
        CREATE VIEW analytics_prediction_gbdt_evaluation AS
        SELECT
            r.run_id,
            r.target_id,
            r.profile_id,
            r.split_name,
            r.model_id,
            r.n_estimators,
            r.learning_rate,
            r.feature_set,
            e.metric_name,
            e.metric_value,
            e.metric_scope,
            r.created_at_utc
        FROM gbdt_prediction_runs r
        JOIN gbdt_evaluation_reports e
          ON e.run_id = r.run_id;

        DROP VIEW IF EXISTS analytics_prediction_gbdt_importance;
        CREATE VIEW analytics_prediction_gbdt_importance AS
        SELECT
            i.run_id,
            r.target_id,
            r.split_name,
            r.n_estimators,
            r.learning_rate,
            i.feature_name,
            i.total_gain,
            i.split_count,
            r.created_at_utc
        FROM gbdt_feature_importance i
        JOIN gbdt_prediction_runs r
          ON r.run_id = i.run_id;
        """
    )
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


def ranking_sample_weights(train: pd.DataFrame) -> np.ndarray:
    frame = train.copy()
    group_col = "role_group" if frame["entity_type"].iloc[0] == "player" else "role_slot"
    pct = frame.groupby(group_col)["target_score"].rank(pct=True, method="average").astype(float)
    return (1.0 + 2.5 * pct.to_numpy()) ** 1.2


def weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    denom = float(np.sum(weights))
    if denom <= 0:
        return 0.0
    return float(np.sum(values * weights) / denom)


def fit_best_stump(X: np.ndarray, residual: np.ndarray, weights: np.ndarray) -> Stump:
    total_pred = weighted_mean(residual, weights)
    total_loss = float(np.sum(weights * (residual - total_pred) ** 2))
    best = Stump(0, float(X[0, 0]) if X.size else 0.0, 0.0, 0.0, -1.0)
    n_samples, n_features = X.shape
    for j in range(n_features):
        values = X[:, j]
        order = np.argsort(values)
        xs = values[order]
        ys = residual[order]
        ws = weights[order]
        if len(np.unique(xs)) < 2:
            continue
        prefix_w = np.cumsum(ws)
        prefix_yw = np.cumsum(ws * ys)
        prefix_y2w = np.cumsum(ws * ys * ys)
        total_w = prefix_w[-1]
        total_yw = prefix_yw[-1]
        total_y2w = prefix_y2w[-1]
        for i in range(1, n_samples):
            if xs[i] == xs[i - 1]:
                continue
            left_w = prefix_w[i - 1]
            right_w = total_w - left_w
            if left_w <= 0 or right_w <= 0:
                continue
            left_yw = prefix_yw[i - 1]
            right_yw = total_yw - left_yw
            left_pred = left_yw / left_w
            right_pred = right_yw / right_w
            left_loss = prefix_y2w[i - 1] - (left_yw * left_yw) / left_w
            right_loss = (total_y2w - prefix_y2w[i - 1]) - (right_yw * right_yw) / right_w
            gain = total_loss - float(left_loss + right_loss)
            if gain > best.gain:
                best = Stump(
                    feature_idx=j,
                    threshold=float((xs[i - 1] + xs[i]) / 2.0),
                    left_value=float(left_pred),
                    right_value=float(right_pred),
                    gain=float(gain),
                )
    return best


def fit_gbdt_rank(X: np.ndarray, y: np.ndarray, weights: np.ndarray, n_estimators: int, learning_rate: float) -> tuple[float, list[Stump]]:
    base = weighted_mean(y, weights)
    pred = np.full(len(y), base, dtype=float)
    stumps: list[Stump] = []
    for _ in range(n_estimators):
        residual = y - pred
        stump = fit_best_stump(X, residual, weights)
        if stump.gain <= 1e-9:
            break
        pred += learning_rate * stump.predict(X)
        stumps.append(stump)
    return base, stumps


def predict_gbdt_rank(X: np.ndarray, base: float, stumps: list[Stump], learning_rate: float) -> np.ndarray:
    pred = np.full(X.shape[0], base, dtype=float)
    for stump in stumps:
        pred += learning_rate * stump.predict(X)
    return pred


def predict_frame(train: pd.DataFrame, scored: pd.DataFrame, n_estimators: int, learning_rate: float) -> tuple[np.ndarray, pd.DataFrame, list[Stump]]:
    train = with_team_segment_key(train)
    scored = with_team_segment_key(scored)
    train_features = build_feature_frame(train, train)
    scored_features = build_feature_frame(train, scored)
    X_train = train_features[FEATURE_COLUMNS].astype(float).to_numpy()
    X_scored = scored_features[FEATURE_COLUMNS].astype(float).to_numpy()
    y_train = train["target_score"].astype(float).to_numpy()
    weights = ranking_sample_weights(train)
    base, stumps = fit_gbdt_rank(X_train, y_train, weights, n_estimators, learning_rate)
    preds = predict_gbdt_rank(X_scored, base, stumps, learning_rate)
    return preds, scored_features, stumps


def build_predictions_for_run(
    target_id: str,
    profile_id: str,
    split_name: str,
    train: pd.DataFrame,
    test: pd.DataFrame,
    n_estimators: int,
    learning_rate: float,
) -> tuple[pd.DataFrame, list[Stump]]:
    if train.empty or test.empty:
        return test.iloc[0:0].copy(), []
    preds, test_features, stumps = predict_frame(train, test, n_estimators, learning_rate)
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
    return pd.DataFrame(rows), stumps


def tuning_key(metrics: dict[str, float]) -> tuple[float, float, float, float]:
    return (
        safe_float(metrics.get("entity_spearman"), 0.0),
        safe_float(metrics.get("ndcg_5"), 0.0),
        safe_float(metrics.get("top5_overlap"), 0.0),
        -safe_float(metrics.get("mae"), 1e18),
    )


def tune_params(train: pd.DataFrame, param_grid: tuple[tuple[int, float], ...]) -> tuple[tuple[int, float], list[dict[str, float]]]:
    inner_train, inner_val = inner_validation_split(train)
    if inner_train.empty or inner_val.empty:
        return param_grid[0], []
    best = param_grid[0]
    best_key = (-1e18, -1e18, -1e18, -1e18)
    rows: list[dict[str, float]] = []
    for n_estimators, learning_rate in param_grid:
        preds, _ = build_predictions_for_run("tuning", "tuning", "inner_validation", inner_train, inner_val, n_estimators, learning_rate)
        metrics = {f"{scope}::{name}": value for name, value, scope in compute_run_metrics(preds)}
        row = {
            "n_estimators": float(n_estimators),
            "learning_rate": float(learning_rate),
            "mae": safe_float(metrics.get("row::mae")),
            "spearman_row": safe_float(metrics.get("row::spearman")),
            "entity_spearman": safe_float(metrics.get("entity::entity_spearman")),
            "top5_overlap": safe_float(metrics.get("entity::top5_overlap")),
            "ndcg_5": safe_float(metrics.get("entity::ndcg_5")),
            "regret_at_1": safe_float(metrics.get("entity::regret_at_1")),
        }
        rows.append(row)
        current = tuning_key(row)
        if current > best_key:
            best_key = current
            best = (n_estimators, learning_rate)
    return best, rows


def feature_importance_rows(stumps: list[Stump]) -> dict[str, dict[str, float]]:
    importance: dict[str, dict[str, float]] = {}
    for stump in stumps:
        name = FEATURE_COLUMNS[stump.feature_idx]
        block = importance.setdefault(name, {"total_gain": 0.0, "split_count": 0.0})
        block["total_gain"] += float(stump.gain)
        block["split_count"] += 1.0
    return importance


def store_run(
    con: sqlite3.Connection,
    target_id: str,
    profile_id: str,
    split_name: str,
    train_label: str,
    test_label: str,
    n_estimators: int,
    learning_rate: float,
    tuning_rows: list[dict[str, float]],
    predictions: pd.DataFrame,
    stumps: list[Stump],
) -> str:
    run_id = f"gbdt::{target_id}::{split_name}::{MODEL_ID}"
    now = utc_now()
    cur = con.cursor()
    cur.execute("DELETE FROM gbdt_prediction_outputs WHERE run_id = ?", (run_id,))
    cur.execute("DELETE FROM gbdt_evaluation_reports WHERE run_id = ?", (run_id,))
    cur.execute("DELETE FROM gbdt_tuning_reports WHERE run_id = ?", (run_id,))
    cur.execute("DELETE FROM gbdt_feature_importance WHERE run_id = ?", (run_id,))
    cur.execute("DELETE FROM gbdt_prediction_runs WHERE run_id = ?", (run_id,))
    cur.execute(
        """
        INSERT INTO gbdt_prediction_runs(
            run_id, target_id, profile_id, split_name, model_id, n_estimators, learning_rate,
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
            int(n_estimators),
            float(learning_rate),
            ",".join(FEATURE_COLUMNS),
            train_label,
            test_label,
            "GBDT rank v1 is a lightweight in-project boosted-stump ranker. It uses ranking-oriented sample weights to emphasize ceiling picks rather than only mean error.",
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
            INSERT OR REPLACE INTO gbdt_prediction_outputs(
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
            INSERT OR REPLACE INTO gbdt_evaluation_reports(run_id, metric_name, metric_value, metric_scope, created_at_utc)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, metric_name, float(metric_value), metric_scope, now),
        )
    for row in tuning_rows:
        for metric_name in ["mae", "spearman_row", "entity_spearman", "top5_overlap", "ndcg_5", "regret_at_1"]:
            metric_scope = "row" if metric_name in {"mae", "spearman_row"} else "entity"
            cur.execute(
                """
                INSERT OR REPLACE INTO gbdt_tuning_reports(
                    run_id, target_id, split_name, n_estimators, learning_rate, metric_name, metric_value, metric_scope, created_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    target_id,
                    split_name,
                    int(row["n_estimators"]),
                    float(row["learning_rate"]),
                    metric_name,
                    float(row[metric_name]),
                    metric_scope,
                    now,
                ),
            )
    for feature_name, block in feature_importance_rows(stumps).items():
        cur.execute(
            """
            INSERT OR REPLACE INTO gbdt_feature_importance(run_id, feature_name, total_gain, split_count, created_at_utc)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, feature_name, float(block["total_gain"]), int(block["split_count"]), now),
        )
    con.commit()
    return run_id


def build_prediction_gbdt(
    db_path: Path = DB_PATH,
    param_grid: tuple[tuple[int, float], ...] = DEFAULT_PARAM_GRID,
) -> dict[str, Any]:
    con = sqlite3.connect(str(db_path))
    try:
        create_gbdt_schema(con)
        profile_id = default_profile_id(con)
        con.execute("DELETE FROM gbdt_prediction_outputs")
        con.execute("DELETE FROM gbdt_evaluation_reports")
        con.execute("DELETE FROM gbdt_tuning_reports")
        con.execute("DELETE FROM gbdt_feature_importance")
        con.execute("DELETE FROM gbdt_prediction_runs")
        con.commit()
        run_ids: list[str] = []
        chosen: list[dict[str, Any]] = []
        for spec in TARGET_SPECS:
            df = load_target_dataset(con, spec.target_id, profile_id)
            for split in SPLITS:
                train, test = build_split(df, split.split_name)
                if train.empty or test.empty:
                    continue
                (n_estimators, learning_rate), tuning_rows = tune_params(train, param_grid)
                preds, stumps = build_predictions_for_run(spec.target_id, profile_id, split.split_name, train, test, n_estimators, learning_rate)
                run_ids.append(
                    store_run(
                        con,
                        spec.target_id,
                        profile_id,
                        split.split_name,
                        split.train_label,
                        split.test_label,
                        n_estimators,
                        learning_rate,
                        tuning_rows,
                        preds,
                        stumps,
                    )
                )
                chosen.append(
                    {
                        "target_id": spec.target_id,
                        "split_name": split.split_name,
                        "selected_n_estimators": n_estimators,
                        "selected_learning_rate": learning_rate,
                    }
                )
        summary = pd.read_sql_query(
            """
            SELECT
                r.target_id,
                r.split_name,
                r.n_estimators,
                r.learning_rate,
                MAX(CASE WHEN e.metric_name = 'mae' AND e.metric_scope = 'row' THEN e.metric_value END) AS mae,
                MAX(CASE WHEN e.metric_name = 'entity_spearman' AND e.metric_scope = 'entity' THEN e.metric_value END) AS spearman_entity,
                MAX(CASE WHEN e.metric_name = 'top5_overlap' AND e.metric_scope = 'entity' THEN e.metric_value END) AS top5_overlap,
                MAX(CASE WHEN e.metric_name = 'ndcg_5' AND e.metric_scope = 'entity' THEN e.metric_value END) AS ndcg_5,
                MAX(CASE WHEN e.metric_name = 'regret_at_1' AND e.metric_scope = 'entity' THEN e.metric_value END) AS regret_at_1
            FROM gbdt_prediction_runs r
            JOIN gbdt_evaluation_reports e
              ON e.run_id = r.run_id
            WHERE r.profile_id = ?
            GROUP BY r.target_id, r.split_name, r.n_estimators, r.learning_rate
            ORDER BY r.target_id, r.split_name
            """,
            con,
            params=(profile_id,),
        )
        return {
            "profile_id": profile_id,
            "run_ids": run_ids,
            "summary": summary,
            "selected_params": pd.DataFrame(chosen),
        }
    finally:
        con.close()
