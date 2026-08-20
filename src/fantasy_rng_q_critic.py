from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from fantasy_rng_actor_critic import _ridge_fit, _ridge_predict
from fantasy_rng_policy_models import _feature_spec, _fit_categories, _matrix


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_schema(con: sqlite3.Connection) -> None:
    con.executescript("""
        CREATE TABLE IF NOT EXISTS fantasy_rng_counterfactual_builds (
          dataset_id TEXT PRIMARY KEY, source_dataset_id TEXT NOT NULL, row_count INTEGER NOT NULL,
          created_at_utc TEXT NOT NULL, notes TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fantasy_rng_counterfactual_offers (
          dataset_id TEXT NOT NULL, episode_index INTEGER NOT NULL, step_index INTEGER NOT NULL,
          offer_rank INTEGER NOT NULL, action_id TEXT NOT NULL, q_target REAL NOT NULL,
          is_teacher_best INTEGER NOT NULL, feature_payload_json TEXT NOT NULL,
          PRIMARY KEY(dataset_id, episode_index, step_index, offer_rank)
        );
        CREATE TABLE IF NOT EXISTS fantasy_rng_q_critic_runs (
          run_id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL, alpha REAL NOT NULL,
          train_rows INTEGER NOT NULL, test_rows INTEGER NOT NULL, metrics_json TEXT NOT NULL,
          created_at_utc TEXT NOT NULL
        );
    """)
    con.commit()


def build_counterfactual_dataset(con: sqlite3.Connection, *, source_dataset_id: str, dataset_id: str) -> dict[str, Any]:
    create_schema(con)
    raw = pd.read_sql_query(
        "SELECT episode_index, step_index, offer_rank_in_set, offer_action_id, feature_payload_json "
        "FROM fantasy_rng_training_samples WHERE dataset_id = ? "
        "ORDER BY episode_index, step_index, offer_rank_in_set",
        con,
        params=(source_dataset_id,),
    )
    if raw.empty:
        raise RuntimeError(f"No RNG rows found for {source_dataset_id}")
    frame = pd.DataFrame([json.loads(value) for value in raw["feature_payload_json"]])
    for column in ["episode_index", "step_index", "offer_rank_in_set", "offer_action_id"]:
        if column not in frame:
            frame[column] = raw[column].to_list()
    # Teacher rollouts expose a label for every offered token, not only the selected one.
    frame["q_target"] = pd.to_numeric(frame.get("target_future_gain", 0.0), errors="coerce").fillna(0.0)
    frame["is_teacher_best"] = 0
    for _, indices in frame.groupby(["episode_index", "step_index"], sort=False).groups.items():
        best_index = frame.loc[list(indices), "q_target"].idxmax()
        frame.loc[best_index, "is_teacher_best"] = 1
    con.execute("DELETE FROM fantasy_rng_counterfactual_offers WHERE dataset_id = ?", (dataset_id,))
    con.execute("DELETE FROM fantasy_rng_counterfactual_builds WHERE dataset_id = ?", (dataset_id,))
    con.executemany(
        "INSERT INTO fantasy_rng_counterfactual_offers VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                dataset_id, int(row.episode_index), int(row.step_index), int(row.offer_rank_in_set),
                str(row.offer_action_id), float(row.q_target), int(row.is_teacher_best),
                json.dumps(row._asdict(), ensure_ascii=False, default=str),
            )
            for row in frame.itertuples()
        ],
    )
    con.execute(
        "INSERT INTO fantasy_rng_counterfactual_builds VALUES (?, ?, ?, ?, ?)",
        (dataset_id, source_dataset_id, len(frame), _now(), "All offered actions labelled with teacher rollout future-gain utility."),
    )
    con.commit()
    return {"dataset_id": dataset_id, "source_dataset_id": source_dataset_id, "rows": int(len(frame))}


def _load_frame(con: sqlite3.Connection, dataset_id: str) -> pd.DataFrame:
    raw = pd.read_sql_query(
        "SELECT feature_payload_json FROM fantasy_rng_counterfactual_offers WHERE dataset_id = ? "
        "ORDER BY episode_index, step_index, offer_rank",
        con,
        params=(dataset_id,),
    )
    return pd.DataFrame([json.loads(value) for value in raw["feature_payload_json"]]) if not raw.empty else raw


def train_q_critic(con: sqlite3.Connection, *, dataset_id: str, alpha: float = 50.0) -> dict[str, Any]:
    create_schema(con)
    frame = _load_frame(con, dataset_id)
    if frame.empty:
        raise RuntimeError(f"No counterfactual rows for {dataset_id}")
    episodes = sorted(frame["episode_index"].astype(int).unique())
    holdout_count = max(1, math.ceil(len(episodes) * 0.25))
    holdout = set(episodes[-holdout_count:])
    train = frame[~frame["episode_index"].isin(holdout)].copy()
    test = frame[frame["episode_index"].isin(holdout)].copy()
    numeric, categorical = _feature_spec(train)
    categories = _fit_categories(train, categorical)
    x_train = _matrix(train, numeric_cols=numeric, categorical_cols=categorical, categories=categories)
    x_test = _matrix(test, numeric_cols=numeric, categorical_cols=categorical, categories=categories)
    ridge = _ridge_fit(x_train, train["q_target"].astype(float).to_numpy(), alpha)
    test["q_prediction"] = _ridge_predict(x_test, ridge)
    y = test["q_target"].astype(float)
    mae = float(np.abs(y - test["q_prediction"]).mean())
    spearman = float(y.rank().corr(test["q_prediction"].rank(), method="pearson") or 0.0)
    top1: list[float] = []
    for _, group in test.groupby(["episode_index", "step_index"], sort=False):
        predicted = group.loc[group["q_prediction"].idxmax()]
        top1.append(float(predicted["is_teacher_best"]))
    metrics = {"mae": mae, "spearman": spearman, "top1_accuracy": float(np.mean(top1) if top1 else 0.0), "test_decisions": len(top1)}
    artifact = {"numeric_cols": numeric, "categorical_cols": categorical, "categories": categories, "ridge": ridge, "target": "teacher_rollout_future_gain"}
    run_id = f"rng_q_critic::{dataset_id}::{_now()}"
    con.execute("INSERT INTO fantasy_rng_q_critic_runs VALUES (?, ?, ?, ?, ?, ?, ?)", (run_id, dataset_id, alpha, len(train), len(test), json.dumps(metrics), _now()))
    con.commit()
    return {"run_id": run_id, "artifact": artifact, "metrics": metrics, "train_rows": len(train), "test_rows": len(test)}


def predict_q_rows(frame: pd.DataFrame, artifact: dict[str, Any]) -> np.ndarray:
    matrix = _matrix(frame, numeric_cols=list(artifact["numeric_cols"]), categorical_cols=list(artifact["categorical_cols"]), categories=dict(artifact["categories"]))
    return _ridge_predict(matrix, dict(artifact["ridge"]))
