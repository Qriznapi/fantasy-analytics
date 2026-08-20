"""Offline Monte-Carlo and fitted-Q evaluation for planner trajectory warehouses.

This module evaluates the behavior policy recorded in a warehouse.  It is a
diagnostic/value-learning prerequisite for conservative offline policy updates;
it does not by itself produce a new actor.
"""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from fantasy_rng_actor_critic import _ridge_fit, _ridge_predict


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS fantasy_rng_offline_fqe_runs (
          run_id TEXT PRIMARY KEY,
          dataset_id TEXT NOT NULL,
          alpha REAL NOT NULL,
          iterations INTEGER NOT NULL,
          train_rows INTEGER NOT NULL,
          test_rows INTEGER NOT NULL,
          metrics_json TEXT NOT NULL,
          created_at_utc TEXT NOT NULL,
          notes TEXT NOT NULL
        );
        """
    )
    con.commit()


def _quality_value(value: Any) -> float:
    return {"tier_i": 1.0, "tier_ii": 2.0, "tier_iii": 3.0, "tier_iv": 4.0, "tier_v": 5.0}.get(str(value).lower(), 0.0)


def _read_rows(con: sqlite3.Connection, dataset_id: str) -> pd.DataFrame:
    raw = pd.read_sql_query(
        """
        SELECT episode_index, step_index, objective_mode, state_value_before,
               immediate_reward, return_to_go, behavior_action_index,
               behavior_action_json, state_slots_json, actor_probs_json
        FROM fantasy_rng_offline_trajectory_steps
        WHERE dataset_id = ?
        ORDER BY episode_index, step_index
        """,
        con,
        params=(dataset_id,),
    )
    if raw.empty:
        raise RuntimeError(f"No warehouse steps found for dataset_id={dataset_id}")

    features: list[dict[str, Any]] = []
    for row in raw.itertuples(index=False):
        action = json.loads(row.behavior_action_json)
        slots = json.loads(row.state_slots_json)
        item: dict[str, Any] = {
            "episode_index": int(row.episode_index),
            "step_index": int(row.step_index),
            "steps_remaining": float(31 - int(row.step_index)),
            "state_value_before": float(row.state_value_before),
            "immediate_reward": float(row.immediate_reward),
            "return_to_go": float(row.return_to_go),
            "objective_mode": str(row.objective_mode),
            "token_type": str(action.get("token_type", "")),
            "role_scope": str(action.get("role_scope", "")),
            "action_scope": str(action.get("action_scope", "")),
            "target_color_group": str(action.get("target_color_group", "neutral") or "neutral"),
        }
        probs = json.loads(row.actor_probs_json)
        index = int(row.behavior_action_index)
        item["behavior_action_probability"] = float(probs[index]) if 0 <= index < len(probs) else 0.0
        for role in ("core", "mid", "support"):
            role_slots = [slot for slot in slots if str(slot.get("role_scope")) == role]
            item[f"{role}_quality_mean"] = float(np.mean([_quality_value(slot.get("quality_tier")) for slot in role_slots])) if role_slots else 0.0
            for trait in ("fractal", "benevolent", "vampiric", "unique", "friendly"):
                item[f"{role}_{trait}_count"] = float(sum(str(slot.get("trait_name", "")).lower() == trait for slot in role_slots))
        features.append(item)
    return pd.DataFrame(features)


def _feature_spec(frame: pd.DataFrame) -> tuple[list[str], list[str]]:
    excluded = {"episode_index", "step_index", "immediate_reward", "return_to_go"}
    categorical = [
        column
        for column in frame.columns
        if column not in excluded and not pd.api.types.is_numeric_dtype(frame[column])
    ]
    numeric = [column for column in frame.columns if column not in excluded and column not in categorical]
    return numeric, categorical


def _categories(frame: pd.DataFrame, columns: list[str]) -> dict[str, list[str]]:
    return {column: sorted({str(value) for value in frame[column].fillna("")}) for column in columns}


def _matrix(frame: pd.DataFrame, numeric: list[str], categorical: list[str], categories: dict[str, list[str]]) -> np.ndarray:
    parts = [frame[column].astype(float).to_numpy().reshape(-1, 1) for column in numeric]
    for column in categorical:
        values = frame[column].fillna("").astype(str)
        for category in categories[column]:
            parts.append((values == category).astype(float).to_numpy().reshape(-1, 1))
    return np.hstack(parts) if parts else np.zeros((len(frame), 0), dtype=float)


def _metrics(y: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    error = y - prediction
    variance = float(np.var(y))
    explained_variance = float(1.0 - np.var(error) / variance) if variance > 1e-12 else 0.0
    rank_corr = pd.Series(y).rank().corr(pd.Series(prediction).rank(), method="pearson")
    return {
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "spearman": float(rank_corr if pd.notna(rank_corr) else 0.0),
        "explained_variance": explained_variance,
    }


def train_offline_fqe(
    con: sqlite3.Connection,
    *,
    dataset_id: str,
    alpha: float = 100.0,
    iterations: int = 20,
) -> dict[str, Any]:
    """Fit behavior-policy FQE and a direct Monte-Carlo baseline by episode split."""
    create_schema(con)
    frame = _read_rows(con, dataset_id)
    episodes = sorted(frame["episode_index"].unique())
    holdout_count = max(1, math.ceil(len(episodes) * 0.25))
    holdout = set(episodes[-holdout_count:])
    train = frame[~frame["episode_index"].isin(holdout)].copy().reset_index(drop=True)
    test = frame[frame["episode_index"].isin(holdout)].copy().reset_index(drop=True)
    numeric, categorical = _feature_spec(train)
    categories = _categories(train, categorical)
    x_train = _matrix(train, numeric, categorical, categories)
    x_test = _matrix(test, numeric, categorical, categories)

    # Direct MC regression is the unbiased-but-high-variance reference.
    mc_model = _ridge_fit(x_train, train["return_to_go"].to_numpy(), alpha)
    mc_prediction = _ridge_predict(x_test, mc_model)

    # FQE recursively evaluates the recorded planner behavior: r + Q(s', a').
    next_index = {
        (int(row.episode_index), int(row.step_index)): index
        for index, row in train.iterrows()
    }
    fqe_model: dict[str, Any] | None = None
    targets = train["immediate_reward"].to_numpy(dtype=float)
    bellman_mae: list[float] = []
    for _ in range(max(1, int(iterations))):
        fqe_model = _ridge_fit(x_train, targets, alpha)
        prediction = _ridge_predict(x_train, fqe_model)
        next_values = np.zeros(len(train), dtype=float)
        for index, row in train.iterrows():
            next_row = next_index.get((int(row.episode_index), int(row.step_index) + 1))
            if next_row is not None:
                next_values[index] = prediction[next_row]
        updated = train["immediate_reward"].to_numpy(dtype=float) + next_values
        bellman_mae.append(float(np.mean(np.abs(updated - prediction))))
        targets = updated
    assert fqe_model is not None
    fqe_prediction = _ridge_predict(x_test, fqe_model)
    y_test = test["return_to_go"].to_numpy(dtype=float)
    metrics = {
        "monte_carlo": _metrics(y_test, mc_prediction),
        "fqe": _metrics(y_test, fqe_prediction),
        "fqe_train_bellman_mae_first": bellman_mae[0],
        "fqe_train_bellman_mae_last": bellman_mae[-1],
        "holdout_episodes": len(holdout),
        "holdout_steps": len(test),
    }
    artifact = {
        "artifact_type": "rng_offline_behavior_fqe_ridge_v1",
        "dataset_id": dataset_id,
        "alpha": float(alpha),
        "iterations": int(iterations),
        "numeric_cols": numeric,
        "categorical_cols": categorical,
        "categories": categories,
        "monte_carlo_model": mc_model,
        "fqe_model": fqe_model,
        "metrics": metrics,
        "notes": "Evaluates the recorded planner behavior; not an actor-promotion model.",
    }
    run_id = f"rng_offline_fqe::{dataset_id}::{_now()}"
    con.execute(
        "INSERT INTO fantasy_rng_offline_fqe_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, dataset_id, float(alpha), int(iterations), len(train), len(test), json.dumps(metrics), _now(), artifact["notes"]),
    )
    con.commit()
    return {"run_id": run_id, "artifact": artifact, "metrics": metrics, "train_rows": len(train), "test_rows": len(test)}
