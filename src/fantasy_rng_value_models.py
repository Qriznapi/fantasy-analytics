from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from fantasy_rng_features import build_offer_rows_from_state
from fantasy_rng_training_dataset import create_schema as create_training_schema
from project_db import resolve_db_path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = resolve_db_path(PROJECT_ROOT, event_id="ti2026")
REGRESSION_MODEL_ID = "rng_ridge_future_gain_v1"
CHOICE_MODEL_ID = "rng_logistic_choice_v1"
DEFAULT_ALPHA = 25.0
DEFAULT_EPOCHS = 250
DEFAULT_LR = 0.05
DEFAULT_TEACHER_POLICIES = ("scheduled_balanced",)


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


def create_schema(con: sqlite3.Connection) -> None:
    create_training_schema(con)
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS fantasy_rng_value_model_runs (
            run_id TEXT PRIMARY KEY,
            dataset_id TEXT NOT NULL,
            profile_id TEXT,
            split_name TEXT NOT NULL,
            teacher_policies_json TEXT NOT NULL,
            regression_model_id TEXT NOT NULL,
            choice_model_id TEXT NOT NULL,
            alpha REAL NOT NULL,
            epochs INTEGER NOT NULL,
            learning_rate REAL NOT NULL,
            train_rows INTEGER NOT NULL,
            test_rows INTEGER NOT NULL,
            chosen_train_rows INTEGER NOT NULL,
            chosen_test_rows INTEGER NOT NULL,
            created_at_utc TEXT NOT NULL,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS fantasy_rng_value_model_outputs (
            run_id TEXT NOT NULL,
            dataset_id TEXT NOT NULL,
            policy_name TEXT NOT NULL,
            episode_index INTEGER NOT NULL,
            step_index INTEGER NOT NULL,
            offer_rank_in_set INTEGER NOT NULL,
            offer_action_id TEXT NOT NULL,
            offer_is_chosen INTEGER NOT NULL,
            target_future_gain REAL NOT NULL,
            predicted_future_gain REAL NOT NULL,
            predicted_choice_prob REAL NOT NULL,
            baseline_expected_choice INTEGER NOT NULL,
            baseline_p75_choice INTEGER NOT NULL,
            split_bucket TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, policy_name, episode_index, step_index, offer_rank_in_set)
        );

        CREATE TABLE IF NOT EXISTS fantasy_rng_value_evaluation_reports (
            run_id TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            metric_value REAL NOT NULL,
            metric_scope TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, metric_name, metric_scope)
        );

        DROP VIEW IF EXISTS analytics_rng_value_evaluation;
        CREATE VIEW analytics_rng_value_evaluation AS
        SELECT
            r.run_id,
            r.dataset_id,
            r.profile_id,
            r.split_name,
            r.teacher_policies_json,
            r.regression_model_id,
            r.choice_model_id,
            r.alpha,
            r.epochs,
            r.learning_rate,
            e.metric_name,
            e.metric_value,
            e.metric_scope,
            r.created_at_utc
        FROM fantasy_rng_value_model_runs r
        JOIN fantasy_rng_value_evaluation_reports e
          ON e.run_id = r.run_id;
        """
    )
    con.commit()


def latest_dataset_id(con: sqlite3.Connection) -> str | None:
    row = con.execute(
        """
        SELECT dataset_id
        FROM fantasy_rng_training_builds
        ORDER BY created_at_utc DESC
        LIMIT 1
        """
    ).fetchone()
    return str(row[0]) if row else None


def load_training_frame(
    con: sqlite3.Connection,
    *,
    dataset_id: str,
    teacher_policies: tuple[str, ...] = DEFAULT_TEACHER_POLICIES,
) -> pd.DataFrame:
    df = pd.read_sql_query(
        """
        SELECT *
        FROM fantasy_rng_training_samples
        WHERE dataset_id = ?
        """,
        con,
        params=(dataset_id,),
    )
    if df.empty:
        return df
    payload_rows = [json.loads(text) for text in df["feature_payload_json"].tolist()]
    frame = pd.DataFrame(payload_rows)
    if teacher_policies:
        frame = frame[frame["policy_name"].astype(str).isin([str(item) for item in teacher_policies])].copy()
    frame = frame.reset_index(drop=True)
    return frame


def episode_split(frame: pd.DataFrame, *, test_fraction: float = 0.25) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_parts: list[pd.DataFrame] = []
    test_parts: list[pd.DataFrame] = []
    for _, group in frame.groupby("policy_name", sort=False):
        ordered = group.sort_values(["episode_index", "step_index", "offer_rank_in_set"]).reset_index(drop=True)
        episodes = sorted({int(value) for value in ordered["episode_index"].tolist()})
        if len(episodes) <= 1:
            train_parts.append(ordered.copy())
            continue
        test_count = max(1, int(math.ceil(len(episodes) * test_fraction)))
        test_episodes = set(episodes[-test_count:])
        train_parts.append(ordered[~ordered["episode_index"].isin(test_episodes)].copy())
        test_parts.append(ordered[ordered["episode_index"].isin(test_episodes)].copy())
    train = pd.concat(train_parts, ignore_index=True) if train_parts else frame.iloc[0:0].copy()
    test = pd.concat(test_parts, ignore_index=True) if test_parts else frame.iloc[0:0].copy()
    return train, test


def feature_spec(frame: pd.DataFrame) -> tuple[list[str], list[str]]:
    exclude = {
        "run_id",
        "policy_name",
        "episode_index",
        "step_index",
        "max_steps",
        "state_slot_state_json",
        "target_episode_final_value",
        "target_future_gain",
        "target_realized_delta",
        "chosen_action_id",
        "chosen_token_type",
        "chosen_role_scope",
        "chosen_slot_index",
        "offer_rank_in_set",
        "offer_action_id",
        "offer_is_chosen",
    }
    numeric_cols: list[str] = []
    categorical_cols: list[str] = []
    for col in frame.columns:
        if col in exclude:
            continue
        if col.startswith("state_") or col.startswith("offer_"):
            if frame[col].dtype == object:
                categorical_cols.append(col)
            else:
                numeric_cols.append(col)
    for col in list(categorical_cols):
        if col in {"offer_expected_delta", "offer_p75_delta", "offer_p90_delta", "offer_slot_index"}:
            categorical_cols.remove(col)
            numeric_cols.append(col)
    numeric_cols = sorted(set(numeric_cols))
    categorical_cols = sorted(set(categorical_cols))
    return numeric_cols, categorical_cols


def one_hot_fit(train: pd.DataFrame, categorical_cols: list[str]) -> dict[str, list[str]]:
    categories: dict[str, list[str]] = {}
    for col in categorical_cols:
        values = sorted({str(value) for value in train[col].fillna("").tolist()})
        categories[col] = values
    return categories


def build_matrix(
    frame: pd.DataFrame,
    *,
    numeric_cols: list[str],
    categorical_cols: list[str],
    categories: dict[str, list[str]],
) -> tuple[np.ndarray, list[str]]:
    base = frame.copy()
    for col in numeric_cols:
        if col not in base.columns:
            base[col] = 0.0
        base[col] = pd.to_numeric(base[col], errors="coerce").fillna(0.0)
    feature_names = list(numeric_cols)
    parts = [base[numeric_cols].to_numpy(dtype=float)] if numeric_cols else []
    for col in categorical_cols:
        if col not in base.columns:
            base[col] = ""
        raw = base[col].fillna("").astype(str)
        for category in categories[col]:
            parts.append((raw == category).astype(float).to_numpy().reshape(-1, 1))
            feature_names.append(f"{col}={category}")
    if not parts:
        return np.zeros((len(frame), 0), dtype=float), feature_names
    return np.hstack(parts), feature_names


def score_offer_rows(
    frame: pd.DataFrame,
    model_artifact: dict[str, Any],
) -> pd.DataFrame:
    scored = frame.copy()
    numeric_cols = list(model_artifact["numeric_cols"])
    categorical_cols = list(model_artifact["categorical_cols"])
    categories = {str(k): list(v) for k, v in model_artifact["categories"].items()}
    X, _ = build_matrix(
        scored,
        numeric_cols=numeric_cols,
        categorical_cols=categorical_cols,
        categories=categories,
    )
    reg = model_artifact["regression"]
    clf = model_artifact["choice"]
    scored["predicted_future_gain"] = predict_ridge(
        X,
        np.asarray(reg["coef"], dtype=float),
        np.asarray(reg["x_mean"], dtype=float),
        np.asarray(reg["x_std"], dtype=float),
        float(reg["y_mean"]),
    )
    scored["predicted_choice_prob"] = predict_logistic_choice(
        X,
        np.asarray(clf["w"], dtype=float),
        float(clf["b"]),
        np.asarray(clf["x_mean"], dtype=float),
        np.asarray(clf["x_std"], dtype=float),
    )
    return scored


def score_offer_set_from_state(
    slots: list[dict[str, Any]],
    offers: list[dict[str, Any]],
    *,
    baseline_value_before: float,
    step_index: int,
    max_steps: int,
    model_artifact: dict[str, Any],
) -> pd.DataFrame:
    rows = build_offer_rows_from_state(
        slots,
        offers,
        baseline_value_before=baseline_value_before,
        step_index=step_index,
        max_steps=max_steps,
    )
    if not rows:
        return pd.DataFrame()
    return score_offer_rows(pd.DataFrame(rows), model_artifact)


def fit_ridge(X: np.ndarray, y: np.ndarray, alpha: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    if X.size == 0:
        return np.zeros(0, dtype=float), np.zeros(0, dtype=float), np.ones(0, dtype=float), float(np.mean(y) if len(y) else 0.0)
    x_mean = X.mean(axis=0)
    x_std = X.std(axis=0)
    x_std[x_std == 0.0] = 1.0
    y_mean = float(np.mean(y)) if len(y) else 0.0
    Xs = (X - x_mean) / x_std
    yc = y - y_mean
    reg = alpha * np.eye(Xs.shape[1], dtype=float)
    coef = np.linalg.solve(Xs.T @ Xs + reg, Xs.T @ yc)
    return coef, x_mean, x_std, y_mean


def predict_ridge(X: np.ndarray, coef: np.ndarray, x_mean: np.ndarray, x_std: np.ndarray, y_mean: float) -> np.ndarray:
    if X.size == 0:
        return np.full(len(X), y_mean, dtype=float)
    Xs = (X - x_mean) / x_std
    return y_mean + Xs @ coef


def fit_logistic_choice(
    X: np.ndarray,
    y: np.ndarray,
    *,
    epochs: int = DEFAULT_EPOCHS,
    lr: float = DEFAULT_LR,
    l2: float = 0.001,
) -> tuple[np.ndarray, float, np.ndarray, np.ndarray]:
    if X.size == 0:
        return np.zeros(0, dtype=float), 0.0, np.zeros(0, dtype=float), np.ones(0, dtype=float)
    x_mean = X.mean(axis=0)
    x_std = X.std(axis=0)
    x_std[x_std == 0.0] = 1.0
    Xs = (X - x_mean) / x_std
    w = np.zeros(Xs.shape[1], dtype=float)
    b = 0.0
    n = max(1, len(y))
    for epoch in range(max(1, int(epochs))):
        logits = Xs @ w + b
        probs = 1.0 / (1.0 + np.exp(-np.clip(logits, -30.0, 30.0)))
        err = probs - y
        step = lr / math.sqrt(epoch + 1.0)
        grad_w = (Xs.T @ err) / n + l2 * w
        grad_b = float(np.mean(err))
        w -= step * grad_w
        b -= step * grad_b
    return w, b, x_mean, x_std


def predict_logistic_choice(X: np.ndarray, w: np.ndarray, b: float, x_mean: np.ndarray, x_std: np.ndarray) -> np.ndarray:
    if X.size == 0:
        return np.zeros(len(X), dtype=float)
    Xs = (X - x_mean) / x_std
    logits = Xs @ w + b
    return 1.0 / (1.0 + np.exp(-np.clip(logits, -30.0, 30.0)))


def regression_metrics(actual: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    if len(actual) == 0:
        return {"mae": 0.0, "rmse": 0.0, "row_spearman": 0.0}
    actual_s = pd.Series(actual)
    pred_s = pd.Series(pred)
    spearman = actual_s.rank().corr(pred_s.rank(), method="pearson")
    return {
        "mae": float(np.mean(np.abs(actual - pred))),
        "rmse": float(np.sqrt(np.mean((actual - pred) ** 2))),
        "row_spearman": float(0.0 if pd.isna(spearman) else spearman),
    }


def _choice_accuracy(frame: pd.DataFrame, score_col: str) -> float:
    if frame.empty:
        return 0.0
    wins = 0
    total = 0
    for _, group in frame.groupby(["policy_name", "episode_index", "step_index"], sort=False):
        total += 1
        best_idx = group[score_col].astype(float).idxmax()
        if int(frame.loc[best_idx, "offer_is_chosen"]) == 1:
            wins += 1
    return float(wins / total) if total else 0.0


def _avg_prob_on_chosen(frame: pd.DataFrame, prob_col: str) -> float:
    chosen = frame[frame["offer_is_chosen"].astype(int) == 1]
    if chosen.empty:
        return 0.0
    return float(chosen[prob_col].astype(float).mean())


def train_rng_value_models(
    *,
    db_path: Path = DB_PATH,
    dataset_id: str,
    teacher_policies: tuple[str, ...] = DEFAULT_TEACHER_POLICIES,
    alpha: float = DEFAULT_ALPHA,
    epochs: int = DEFAULT_EPOCHS,
    lr: float = DEFAULT_LR,
) -> dict[str, Any]:
    con = sqlite3.connect(str(db_path))
    try:
        create_schema(con)
        dataset = load_training_frame(con, dataset_id=dataset_id, teacher_policies=teacher_policies)
        if dataset.empty:
            raise RuntimeError("RNG training dataset is empty after teacher policy filtering.")
        meta = con.execute(
            "SELECT source_episode_run_id FROM fantasy_rng_training_builds WHERE dataset_id = ?",
            (dataset_id,),
        ).fetchone()
        source_episode_run_id = str(meta[0]) if meta else ""
    finally:
        con.close()

    train_df, test_df = episode_split(dataset)
    if test_df.empty:
        test_df = train_df.copy()
    numeric_cols, categorical_cols = feature_spec(train_df)
    categories = one_hot_fit(train_df, categorical_cols)

    chosen_train = train_df[train_df["offer_is_chosen"].astype(int) == 1].copy()
    chosen_test = test_df[test_df["offer_is_chosen"].astype(int) == 1].copy()

    X_train_reg, feature_names = build_matrix(
        chosen_train,
        numeric_cols=numeric_cols,
        categorical_cols=categorical_cols,
        categories=categories,
    )
    y_train_reg = chosen_train["target_future_gain"].astype(float).to_numpy()
    coef, x_mean, x_std, y_mean = fit_ridge(X_train_reg, y_train_reg, alpha)

    X_test_chosen, _ = build_matrix(
        chosen_test,
        numeric_cols=numeric_cols,
        categorical_cols=categorical_cols,
        categories=categories,
    )
    pred_chosen = predict_ridge(X_test_chosen, coef, x_mean, x_std, y_mean)
    reg_metrics = regression_metrics(chosen_test["target_future_gain"].astype(float).to_numpy(), pred_chosen)

    X_train_all, _ = build_matrix(
        train_df,
        numeric_cols=numeric_cols,
        categorical_cols=categorical_cols,
        categories=categories,
    )
    y_train_choice = train_df["offer_is_chosen"].astype(float).to_numpy()
    w, b, cx_mean, cx_std = fit_logistic_choice(X_train_all, y_train_choice, epochs=epochs, lr=lr)

    X_test_all, _ = build_matrix(
        test_df,
        numeric_cols=numeric_cols,
        categorical_cols=categorical_cols,
        categories=categories,
    )
    test_scored = test_df.copy()
    test_scored["predicted_future_gain"] = predict_ridge(X_test_all, coef, x_mean, x_std, y_mean)
    test_scored["predicted_choice_prob"] = predict_logistic_choice(X_test_all, w, b, cx_mean, cx_std)
    test_scored["baseline_expected_choice"] = 0
    test_scored["baseline_p75_choice"] = 0
    for _, group in test_scored.groupby(["policy_name", "episode_index", "step_index"], sort=False):
        exp_idx = group["offer_expected_delta"].astype(float).idxmax()
        p75_idx = group["offer_p75_delta"].astype(float).idxmax()
        test_scored.loc[exp_idx, "baseline_expected_choice"] = 1
        test_scored.loc[p75_idx, "baseline_p75_choice"] = 1

    choice_metrics = {
        "model_choice_top1_acc": _choice_accuracy(test_scored, "predicted_choice_prob"),
        "baseline_expected_top1_acc": _choice_accuracy(test_scored, "baseline_expected_choice"),
        "baseline_p75_top1_acc": _choice_accuracy(test_scored, "baseline_p75_choice"),
        "avg_prob_on_true_choice": _avg_prob_on_chosen(test_scored, "predicted_choice_prob"),
    }

    model_artifact = {
        "dataset_id": dataset_id,
        "teacher_policies": list(teacher_policies),
        "numeric_cols": numeric_cols,
        "categorical_cols": categorical_cols,
        "categories": categories,
        "feature_names": feature_names,
        "regression": {
            "model_id": REGRESSION_MODEL_ID,
            "coef": coef.tolist(),
            "x_mean": x_mean.tolist(),
            "x_std": x_std.tolist(),
            "y_mean": float(y_mean),
        },
        "choice": {
            "model_id": CHOICE_MODEL_ID,
            "w": w.tolist(),
            "b": float(b),
            "x_mean": cx_mean.tolist(),
            "x_std": cx_std.tolist(),
        },
    }

    run_id = f"rng_value::{dataset_id}::{utc_now()}"
    con = sqlite3.connect(str(db_path))
    try:
        create_schema(con)
        cur = con.cursor()
        cur.execute("DELETE FROM fantasy_rng_value_model_outputs WHERE run_id = ?", (run_id,))
        cur.execute("DELETE FROM fantasy_rng_value_evaluation_reports WHERE run_id = ?", (run_id,))
        cur.execute("DELETE FROM fantasy_rng_value_model_runs WHERE run_id = ?", (run_id,))
        cur.execute(
            """
            INSERT INTO fantasy_rng_value_model_runs(
                run_id, dataset_id, profile_id, split_name, teacher_policies_json, regression_model_id, choice_model_id,
                alpha, epochs, learning_rate, train_rows, test_rows, chosen_train_rows, chosen_test_rows, created_at_utc, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                dataset_id,
                source_episode_run_id,
                "episode_holdout_v1",
                json.dumps(list(teacher_policies), ensure_ascii=False),
                REGRESSION_MODEL_ID,
                CHOICE_MODEL_ID,
                float(alpha),
                int(epochs),
                float(lr),
                int(len(train_df)),
                int(len(test_df)),
                int(len(chosen_train)),
                int(len(chosen_test)),
                utc_now(),
                "Richer RNG feature layer: ridge on chosen future_gain plus logistic choice imitation over teacher policies.",
            ),
        )
        if not test_scored.empty:
            cur.executemany(
                """
                INSERT OR REPLACE INTO fantasy_rng_value_model_outputs(
                    run_id, dataset_id, policy_name, episode_index, step_index, offer_rank_in_set, offer_action_id,
                    offer_is_chosen, target_future_gain, predicted_future_gain, predicted_choice_prob,
                    baseline_expected_choice, baseline_p75_choice, split_bucket, created_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        dataset_id,
                        str(row.policy_name),
                        int(row.episode_index),
                        int(row.step_index),
                        int(row.offer_rank_in_set),
                        str(row.offer_action_id),
                        int(row.offer_is_chosen),
                        float(row.target_future_gain),
                        float(row.predicted_future_gain),
                        float(row.predicted_choice_prob),
                        int(row.baseline_expected_choice),
                        int(row.baseline_p75_choice),
                        "test",
                        utc_now(),
                    )
                    for row in test_scored.itertuples(index=False)
                ],
            )
        metric_rows = []
        for name, value in {**reg_metrics, **choice_metrics}.items():
            scope = "chosen_rows" if name in {"mae", "rmse", "row_spearman"} else "step_choice"
            metric_rows.append((run_id, name, float(value), scope, utc_now()))
        cur.executemany(
            """
            INSERT OR REPLACE INTO fantasy_rng_value_evaluation_reports(run_id, metric_name, metric_value, metric_scope, created_at_utc)
            VALUES (?, ?, ?, ?, ?)
            """,
            metric_rows,
        )
        con.commit()
    finally:
        con.close()

    return {
        "run_id": run_id,
        "dataset_id": dataset_id,
        "teacher_policies": teacher_policies,
        "train_rows": len(train_df),
        "test_rows": len(test_df),
        "chosen_train_rows": len(chosen_train),
        "chosen_test_rows": len(chosen_test),
        "feature_names": feature_names,
        "numeric_cols": numeric_cols,
        "categorical_cols": categorical_cols,
        "model_artifact": model_artifact,
        "regression_metrics": reg_metrics,
        "choice_metrics": choice_metrics,
        "test_scored": test_scored,
    }
