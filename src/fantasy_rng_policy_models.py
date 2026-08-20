from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from fantasy_rng_training_dataset import create_schema as create_rng_training_schema
from fantasy_rng_features import build_offer_rows_from_state


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
    create_rng_training_schema(con)
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS fantasy_rng_policy_model_runs (
            run_id TEXT PRIMARY KEY,
            dataset_id TEXT NOT NULL,
            label_name TEXT NOT NULL,
            alpha REAL NOT NULL,
            epochs INTEGER NOT NULL,
            learning_rate REAL NOT NULL,
            train_rows INTEGER NOT NULL,
            test_rows INTEGER NOT NULL,
            created_at_utc TEXT NOT NULL,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS fantasy_rng_policy_model_outputs (
            run_id TEXT NOT NULL,
            dataset_id TEXT NOT NULL,
            episode_index INTEGER NOT NULL,
            step_index INTEGER NOT NULL,
            offer_rank_in_set INTEGER NOT NULL,
            offer_action_id TEXT NOT NULL,
            label_value INTEGER NOT NULL,
            predicted_prob REAL NOT NULL,
            split_bucket TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, episode_index, step_index, offer_rank_in_set)
        );

        CREATE TABLE IF NOT EXISTS fantasy_rng_policy_model_eval (
            run_id TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            metric_value REAL NOT NULL,
            metric_scope TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, metric_name, metric_scope)
        );
        """
    )
    con.commit()


def _payload_frame(con: sqlite3.Connection, dataset_id: str) -> pd.DataFrame:
    df = pd.read_sql_query(
        """
        SELECT dataset_id, episode_index, step_index, offer_rank_in_set, offer_action_id, feature_payload_json
        FROM fantasy_rng_training_samples
        WHERE dataset_id = ?
        ORDER BY episode_index, step_index, offer_rank_in_set
        """,
        con,
        params=(dataset_id,),
    )
    if df.empty:
        return df
    payloads = [json.loads(text) for text in df["feature_payload_json"].tolist()]
    frame = pd.DataFrame(payloads)
    for col in ["episode_index", "step_index", "offer_rank_in_set", "offer_action_id"]:
        if col not in frame.columns and col in df.columns:
            frame[col] = df[col].tolist()
    return frame


def _feature_spec(frame: pd.DataFrame) -> tuple[list[str], list[str]]:
    exclude = {
        "run_id",
        "policy_name",
        "episode_index",
        "step_index",
        "offer_rank_in_set",
        "offer_action_id",
        "offer_is_chosen",
        "teacher_action",
        "teacher_rank",
        "teacher_margin",
        "teacher_confidence",
        "teacher_weight",
        "target_episode_final_value",
        "target_future_gain",
        "target_realized_delta",
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
    return sorted(set(numeric_cols)), sorted(set(categorical_cols))


def _fit_categories(frame: pd.DataFrame, categorical_cols: list[str]) -> dict[str, list[str]]:
    return {col: sorted({str(v) for v in frame[col].fillna("").tolist()}) for col in categorical_cols}


def _matrix(
    frame: pd.DataFrame,
    *,
    numeric_cols: list[str],
    categorical_cols: list[str],
    categories: dict[str, list[str]],
) -> np.ndarray:
    work = frame.copy()
    parts: list[np.ndarray] = []
    for col in numeric_cols:
        if col not in work.columns:
            work[col] = 0.0
        work[col] = pd.to_numeric(work[col], errors="coerce").fillna(0.0)
    if numeric_cols:
        parts.append(work[numeric_cols].to_numpy(dtype=float))
    for col in categorical_cols:
        if col not in work.columns:
            work[col] = ""
        raw = work[col].fillna("").astype(str)
        for category in categories[col]:
            parts.append((raw == category).astype(float).to_numpy().reshape(-1, 1))
    if not parts:
        return np.zeros((len(frame), 0), dtype=float)
    return np.hstack(parts)


def _fit_logistic(
    X: np.ndarray,
    y: np.ndarray,
    *,
    alpha: float,
    epochs: int,
    learning_rate: float,
    sample_weight: np.ndarray | None = None,
) -> dict[str, Any]:
    if X.size == 0:
        return {"w": [], "b": 0.0, "x_mean": [], "x_std": []}
    x_mean = X.mean(axis=0)
    x_std = X.std(axis=0)
    x_std[x_std == 0] = 1.0
    Xn = (X - x_mean) / x_std
    w = np.zeros(Xn.shape[1], dtype=float)
    b = 0.0
    weights = sample_weight if sample_weight is not None else np.ones(len(y), dtype=float)
    weights = np.asarray(weights, dtype=float)
    weights = weights / max(1.0, float(weights.mean()))
    for _ in range(max(1, int(epochs))):
        logits = Xn @ w + b
        probs = 1.0 / (1.0 + np.exp(-np.clip(logits, -30, 30)))
        residual = (probs - y) * weights
        grad_w = (Xn.T @ residual) / max(1, len(y)) + alpha * w / max(1, len(y))
        grad_b = float(np.mean(residual))
        w -= learning_rate * grad_w
        b -= learning_rate * grad_b
    return {
        "w": w.tolist(),
        "b": float(b),
        "x_mean": x_mean.tolist(),
        "x_std": x_std.tolist(),
    }


def _predict_logistic(X: np.ndarray, artifact: dict[str, Any]) -> np.ndarray:
    if X.size == 0:
        return np.zeros(len(X), dtype=float)
    w = np.asarray(artifact["w"], dtype=float)
    x_mean = np.asarray(artifact["x_mean"], dtype=float)
    x_std = np.asarray(artifact["x_std"], dtype=float)
    Xn = (X - x_mean) / np.where(x_std == 0, 1.0, x_std)
    logits = Xn @ w + float(artifact["b"])
    return 1.0 / (1.0 + np.exp(-np.clip(logits, -30, 30)))


def score_policy_offer_rows(
    frame: pd.DataFrame,
    artifact: dict[str, Any],
) -> pd.DataFrame:
    scored = frame.copy()
    numeric_cols = list(artifact["numeric_cols"])
    categorical_cols = list(artifact["categorical_cols"])
    categories = {str(k): list(v) for k, v in artifact["categories"].items()}
    X = _matrix(
        scored,
        numeric_cols=numeric_cols,
        categorical_cols=categorical_cols,
        categories=categories,
    )
    probs = _predict_logistic(X, artifact["logistic"])
    scored["predicted_prob"] = probs
    return scored


def score_policy_offer_set_from_state(
    slots: list[dict[str, Any]],
    offers: list[dict[str, Any]],
    *,
    baseline_value_before: float,
    step_index: int,
    max_steps: int,
    artifact: dict[str, Any],
) -> pd.DataFrame:
    rows = build_offer_rows_from_state(
        slots,
        offers,
        baseline_value_before=baseline_value_before,
        step_index=step_index,
        max_steps=max_steps,
    )
    return score_policy_offer_rows(pd.DataFrame(rows), artifact)


def train_policy_choice_model(
    db_path: Path,
    *,
    dataset_id: str,
    label_name: str = "teacher_action",
    alpha: float = 1.0,
    epochs: int = 300,
    learning_rate: float = 0.05,
) -> dict[str, Any]:
    con = sqlite3.connect(str(db_path))
    try:
        create_schema(con)
        frame = _payload_frame(con, dataset_id)
        if frame.empty:
            raise RuntimeError(f"No RNG training samples found for dataset_id={dataset_id}")
        if label_name not in frame.columns:
            raise RuntimeError(f"Column {label_name} is missing in dataset_id={dataset_id}")
        episodes = sorted({int(v) for v in frame["episode_index"].tolist()})
        if len(episodes) <= 1:
            train = frame.copy()
            test = frame.copy()
        else:
            test_count = max(1, int(math.ceil(len(episodes) * 0.25)))
            test_episodes = set(episodes[-test_count:])
            train = frame[~frame["episode_index"].isin(test_episodes)].copy()
            test = frame[frame["episode_index"].isin(test_episodes)].copy()
        numeric_cols, categorical_cols = _feature_spec(train)
        categories = _fit_categories(train, categorical_cols)
        X_train = _matrix(train, numeric_cols=numeric_cols, categorical_cols=categorical_cols, categories=categories)
        X_test = _matrix(test, numeric_cols=numeric_cols, categorical_cols=categorical_cols, categories=categories)
        y_train = train[label_name].fillna(0).astype(int).to_numpy(dtype=float)
        y_test = test[label_name].fillna(0).astype(int).to_numpy(dtype=float)
        train_weight = pd.to_numeric(train.get("teacher_weight", 1.0), errors="coerce").fillna(1.0).to_numpy(dtype=float)
        artifact = _fit_logistic(
            X_train,
            y_train,
            alpha=float(alpha),
            epochs=int(epochs),
            learning_rate=float(learning_rate),
            sample_weight=train_weight,
        )
        p_test = _predict_logistic(X_test, artifact)
        out = test[["episode_index", "step_index", "offer_rank_in_set", "offer_action_id"]].copy()
        out["label_value"] = y_test.astype(int)
        out["predicted_prob"] = p_test
        grouped = out.groupby(["episode_index", "step_index"], sort=False)
        top1_hits = 0
        top1_total = 0
        for _, group in grouped:
            chosen_truth = group[group["label_value"] == 1]
            if chosen_truth.empty:
                continue
            top1_total += 1
            pred_row = group.sort_values("predicted_prob", ascending=False).iloc[0]
            if int(pred_row["label_value"]) == 1:
                top1_hits += 1
        top1_acc = float(top1_hits / top1_total) if top1_total else 0.0
        avg_true_prob = float(out.loc[out["label_value"] == 1, "predicted_prob"].mean()) if not out.empty else 0.0
        run_id = f"rng_policy::{dataset_id}::{utc_now()}"
        cur = con.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO fantasy_rng_policy_model_runs(
                run_id, dataset_id, label_name, alpha, epochs, learning_rate,
                train_rows, test_rows, created_at_utc, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                dataset_id,
                label_name,
                float(alpha),
                int(epochs),
                float(learning_rate),
                int(len(train)),
                int(len(test)),
                utc_now(),
                "Compact policy-choice model over synthetic RNG teacher labels.",
            ),
        )
        cur.execute("DELETE FROM fantasy_rng_policy_model_outputs WHERE run_id = ?", (run_id,))
        rows = [
            (
                run_id,
                dataset_id,
                int(row["episode_index"]),
                int(row["step_index"]),
                int(row["offer_rank_in_set"]),
                str(row["offer_action_id"]),
                int(row["label_value"]),
                float(row["predicted_prob"]),
                "test",
                utc_now(),
            )
            for row in out.to_dict(orient="records")
        ]
        cur.executemany(
            """
            INSERT OR REPLACE INTO fantasy_rng_policy_model_outputs(
                run_id, dataset_id, episode_index, step_index, offer_rank_in_set,
                offer_action_id, label_value, predicted_prob, split_bucket, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        for metric_name, metric_value in {
            "metric_top1_acc": top1_acc,
            "metric_avg_prob_on_true_choice": avg_true_prob,
        }.items():
            cur.execute(
                """
                INSERT OR REPLACE INTO fantasy_rng_policy_model_eval(
                    run_id, metric_name, metric_value, metric_scope, created_at_utc
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, metric_name, float(metric_value), "test", utc_now()),
            )
        con.commit()
        return {
            "run_id": run_id,
            "dataset_id": dataset_id,
            "label_name": label_name,
            "metrics": {
                "metric_top1_acc": top1_acc,
                "metric_avg_prob_on_true_choice": avg_true_prob,
            },
            "artifact": {
                "numeric_cols": numeric_cols,
                "categorical_cols": categorical_cols,
                "categories": categories,
                "label_name": label_name,
                "logistic": artifact,
            },
        }
    finally:
        con.close()
