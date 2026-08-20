"""Extract and evaluate planner counterfactual action values from the offline warehouse."""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from fantasy_rng_actor_critic import _ridge_fit, _ridge_predict
from fantasy_rng_features import build_offer_rows_from_state
from fantasy_rng_policy_models import _fit_categories, _matrix


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS fantasy_rng_offline_counterfactual_builds (
          dataset_id TEXT PRIMARY KEY, source_dataset_id TEXT NOT NULL, decision_count INTEGER NOT NULL,
          row_count INTEGER NOT NULL, selected_action_coverage REAL NOT NULL, created_at_utc TEXT NOT NULL, notes TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fantasy_rng_offline_counterfactual_actions (
          dataset_id TEXT NOT NULL, episode_index INTEGER NOT NULL, step_index INTEGER NOT NULL,
          candidate_rank INTEGER NOT NULL, action_index INTEGER NOT NULL, action_id TEXT NOT NULL,
          planner_utility REAL NOT NULL, planner_mean REAL NOT NULL, planner_p25 REAL NOT NULL, planner_p90 REAL NOT NULL,
          is_planner_best INTEGER NOT NULL, is_behavior_selected INTEGER NOT NULL, feature_payload_json TEXT NOT NULL,
          PRIMARY KEY(dataset_id, episode_index, step_index, candidate_rank)
        );
        CREATE TABLE IF NOT EXISTS fantasy_rng_offline_counterfactual_ranker_runs (
          run_id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL, alpha REAL NOT NULL, train_rows INTEGER NOT NULL,
          test_rows INTEGER NOT NULL, metrics_json TEXT NOT NULL, created_at_utc TEXT NOT NULL
        );
        """
    )
    con.commit()


def build_counterfactual_actions(con: sqlite3.Connection, *, source_dataset_id: str, dataset_id: str) -> dict[str, Any]:
    create_schema(con)
    rows = con.execute(
        """
        SELECT episode_index, step_index, objective_mode, state_value_before, behavior_action_index,
               state_slots_json, offers_json, planner_candidates_json
        FROM fantasy_rng_offline_trajectory_steps
        WHERE dataset_id = ? ORDER BY episode_index, step_index
        """,
        (source_dataset_id,),
    ).fetchall()
    if not rows:
        raise RuntimeError(f"No trajectory rows for {source_dataset_id}")
    inserted: list[tuple[Any, ...]] = []
    selected_seen = 0
    for episode, step, objective, state_value, selected_index, slots_json, offers_json, candidates_json in rows:
        slots, offers, candidates = json.loads(slots_json), json.loads(offers_json), json.loads(candidates_json)
        candidate_indices = {int(item["action_index"]) for item in candidates}
        scoped = [dict(offers[index]) for index in sorted(candidate_indices)]
        features = build_offer_rows_from_state(slots, scoped, baseline_value_before=float(state_value), step_index=int(step), max_steps=30, episode_index=int(episode))
        candidate_by_index = {int(item["action_index"]): item for item in candidates}
        best_index = max(candidate_by_index, key=lambda index: float(candidate_by_index[index]["utility"]))
        selected_seen += int(int(selected_index) in candidate_by_index)
        for rank, (action_index, feature) in enumerate(zip(sorted(candidate_indices), features)):
            candidate = candidate_by_index[action_index]
            feature["q_target"] = float(candidate["utility"] - float(state_value))
            feature["state_objective_safe"] = int(objective == "safe")
            feature["state_objective_ceiling"] = int(objective == "ceiling")
            inserted.append((
                dataset_id, int(episode), int(step), int(rank), int(action_index), str(feature["offer_action_id"]),
                float(candidate["utility"]), float(candidate["mean"]), float(candidate["p25"]), float(candidate["p90"]),
                int(action_index == best_index), int(action_index == int(selected_index)), json.dumps(feature, ensure_ascii=False),
            ))
    con.execute("DELETE FROM fantasy_rng_offline_counterfactual_actions WHERE dataset_id = ?", (dataset_id,))
    con.execute("DELETE FROM fantasy_rng_offline_counterfactual_builds WHERE dataset_id = ?", (dataset_id,))
    con.executemany("INSERT INTO fantasy_rng_offline_counterfactual_actions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", inserted)
    con.execute(
        "INSERT INTO fantasy_rng_offline_counterfactual_builds VALUES (?, ?, ?, ?, ?, ?, ?)",
        (dataset_id, source_dataset_id, len(rows), len(inserted), selected_seen / len(rows), _now(), "Top-k planner counterfactual action utilities from full trajectory warehouse."),
    )
    con.commit()
    return {"dataset_id": dataset_id, "source_dataset_id": source_dataset_id, "decisions": len(rows), "rows": len(inserted), "selected_action_coverage": selected_seen / len(rows)}


def _load_frame(con: sqlite3.Connection, dataset_id: str) -> pd.DataFrame:
    raw = pd.read_sql_query(
        "SELECT episode_index, step_index, is_planner_best, feature_payload_json FROM fantasy_rng_offline_counterfactual_actions WHERE dataset_id = ? ORDER BY episode_index, step_index, candidate_rank",
        con, params=(dataset_id,),
    )
    frame = pd.DataFrame([json.loads(value) for value in raw["feature_payload_json"]])
    frame["episode_index"] = raw["episode_index"].to_numpy()
    frame["step_index"] = raw["step_index"].to_numpy()
    frame["is_planner_best"] = raw["is_planner_best"].to_numpy()
    return frame


def _feature_spec(frame: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Feature schema for this ranker, robust to pandas StringDtype."""
    excluded = {
        "episode_index", "step_index", "q_target", "is_planner_best",
        "state_slot_state_json", "offer_action_id", "offer_is_chosen",
    }
    candidates = [column for column in frame.columns if (column.startswith("state_") or column.startswith("offer_")) and column not in excluded]
    categorical = [column for column in candidates if not pd.api.types.is_numeric_dtype(frame[column])]
    numeric = [column for column in candidates if column not in categorical]
    return sorted(numeric), sorted(categorical)


def train_counterfactual_ranker(con: sqlite3.Connection, *, dataset_id: str, alpha: float = 100.0) -> dict[str, Any]:
    create_schema(con)
    frame = _load_frame(con, dataset_id)
    if frame.empty:
        raise RuntimeError(f"No counterfactual actions for {dataset_id}")
    episodes = sorted(frame["episode_index"].astype(int).unique())
    holdout = set(episodes[-max(1, math.ceil(len(episodes) * 0.25)):])
    train, test = frame[~frame.episode_index.isin(holdout)].copy(), frame[frame.episode_index.isin(holdout)].copy()
    numeric, categorical = _feature_spec(train)
    categories = _fit_categories(train, categorical)
    model = _ridge_fit(_matrix(train, numeric_cols=numeric, categorical_cols=categorical, categories=categories), train["q_target"].astype(float).to_numpy(), alpha)
    test["prediction"] = _ridge_predict(_matrix(test, numeric_cols=numeric, categorical_cols=categorical, categories=categories), model)
    top1: list[float] = []
    for _, group in test.groupby(["episode_index", "step_index"], sort=False):
        top1.append(float(group.loc[group.prediction.idxmax(), "is_planner_best"]))
    y = test["q_target"].astype(float)
    metrics = {
        "mae": float(np.mean(np.abs(y - test.prediction))),
        "spearman": float(y.rank().corr(test.prediction.rank(), method="pearson") or 0.0),
        "planner_candidate_top1": float(np.mean(top1)),
        "holdout_decisions": len(top1),
    }
    artifact = {"artifact_type": "rng_offline_counterfactual_ridge_v1", "dataset_id": dataset_id, "alpha": alpha, "numeric_cols": numeric, "categorical_cols": categorical, "categories": categories, "ridge": model, "metrics": metrics}
    run_id = f"rng_offline_counterfactual_ranker::{dataset_id}::{_now()}"
    con.execute("INSERT INTO fantasy_rng_offline_counterfactual_ranker_runs VALUES (?, ?, ?, ?, ?, ?, ?)", (run_id, dataset_id, alpha, len(train), len(test), json.dumps(metrics), _now()))
    con.commit()
    return {"run_id": run_id, "artifact": artifact, "metrics": metrics, "train_rows": len(train), "test_rows": len(test)}
