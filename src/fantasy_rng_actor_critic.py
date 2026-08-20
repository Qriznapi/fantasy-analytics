from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from fantasy_rng_policy_models import _fit_categories, _fit_logistic, _matrix, _payload_frame, _predict_logistic


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _state_spec(frame: pd.DataFrame) -> tuple[list[str], list[str]]:
    cols = [col for col in frame.columns if col.startswith("state_") and col != "state_slot_state_json"]
    return [col for col in cols if frame[col].dtype != object], [col for col in cols if frame[col].dtype == object]


def _ridge_fit(X: np.ndarray, y: np.ndarray, alpha: float) -> dict[str, list[float] | float]:
    mean, std = X.mean(axis=0), X.std(axis=0)
    std[std == 0] = 1.0
    norm = (X - mean) / std
    y_mean = float(y.mean())
    coef = np.linalg.solve(norm.T @ norm + float(alpha) * np.eye(norm.shape[1]), norm.T @ (y - y_mean))
    return {"coef": coef.tolist(), "x_mean": mean.tolist(), "x_std": std.tolist(), "y_mean": y_mean}


def _ridge_predict(X: np.ndarray, model: dict[str, list[float] | float]) -> np.ndarray:
    mean, std, coef = np.asarray(model["x_mean"]), np.asarray(model["x_std"]), np.asarray(model["coef"])
    return float(model["y_mean"]) + ((X - mean) / np.where(std == 0, 1.0, std)) @ coef


def predict_critic_rows(frame: pd.DataFrame, critic_artifact: dict[str, object]) -> np.ndarray:
    matrix = _matrix(
        frame,
        numeric_cols=list(critic_artifact["numeric_cols"]),
        categorical_cols=list(critic_artifact["categorical_cols"]),
        categories=dict(critic_artifact["categories"]),
    )
    return _ridge_predict(matrix, dict(critic_artifact["ridge"]))


def create_schema(con: sqlite3.Connection) -> None:
    con.executescript("""
        CREATE TABLE IF NOT EXISTS fantasy_rng_actor_critic_runs (
            run_id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL, critic_alpha REAL NOT NULL,
            advantage_temperature REAL NOT NULL, train_rows INTEGER NOT NULL, test_rows INTEGER NOT NULL,
            critic_mae REAL NOT NULL, actor_top1_acc REAL NOT NULL, created_at_utc TEXT NOT NULL, notes TEXT
        );
        CREATE TABLE IF NOT EXISTS fantasy_rng_actor_critic_outputs (
            run_id TEXT NOT NULL, episode_index INTEGER NOT NULL, step_index INTEGER NOT NULL,
            offer_rank_in_set INTEGER NOT NULL, action_id TEXT NOT NULL, is_chosen INTEGER NOT NULL,
            mc_return REAL NOT NULL, critic_return REAL NOT NULL, advantage REAL NOT NULL,
            actor_probability REAL NOT NULL, split_bucket TEXT NOT NULL,
            PRIMARY KEY (run_id, episode_index, step_index, offer_rank_in_set)
        );
    """)
    con.commit()


def train_actor_critic(db_path: Path, *, dataset_id: str, critic_alpha: float = 25.0, advantage_temperature: float = 3000.0) -> dict[str, object]:
    con = sqlite3.connect(str(db_path), timeout=60.0)
    try:
        create_schema(con)
        frame = _payload_frame(con, dataset_id)
        if frame.empty:
            raise RuntimeError(f"No samples for {dataset_id}")
        chosen = frame[frame["offer_is_chosen"].astype(int) == 1].copy()
        chosen["mc_return"] = chosen["target_episode_final_value"].astype(float) - chosen["state_banner_value"].astype(float)
        episodes = sorted(chosen["episode_index"].astype(int).unique())
        holdout = set(episodes[-max(1, math.ceil(len(episodes) * 0.25)):])
        state_num, state_cat = _state_spec(chosen)
        categories = _fit_categories(chosen[~chosen["episode_index"].isin(holdout)], state_cat)
        X_state = _matrix(chosen, numeric_cols=state_num, categorical_cols=state_cat, categories=categories)
        train_mask = ~chosen["episode_index"].isin(holdout)
        critic = _ridge_fit(X_state[train_mask.to_numpy()], chosen.loc[train_mask, "mc_return"].to_numpy(dtype=float), critic_alpha)
        chosen["critic_return"] = _ridge_predict(X_state, critic)
        chosen["advantage"] = chosen["mc_return"] - chosen["critic_return"]
        advantage_map = chosen.set_index(["episode_index", "step_index"])["advantage"].to_dict()
        frame["advantage"] = [float(advantage_map.get((int(row.episode_index), int(row.step_index)), 0.0)) for row in frame.itertuples()]
        train = frame[~frame["episode_index"].isin(holdout)].copy()
        test = frame[frame["episode_index"].isin(holdout)].copy()
        from fantasy_rng_policy_models import _feature_spec
        num, cat = _feature_spec(train)
        actor_categories = _fit_categories(train, cat)
        X_train = _matrix(train, numeric_cols=num, categorical_cols=cat, categories=actor_categories)
        X_test = _matrix(test, numeric_cols=num, categorical_cols=cat, categories=actor_categories)
        y_train = train["offer_is_chosen"].astype(float).to_numpy()
        weights = np.ones(len(train), dtype=float)
        selected = y_train == 1
        weights[selected] = np.clip(np.exp(np.clip(train.loc[selected, "advantage"].to_numpy(dtype=float) / advantage_temperature, -3, 3)), 0.05, 20.0)
        logistic = _fit_logistic(X_train, y_train, alpha=1.0, epochs=400, learning_rate=0.04, sample_weight=weights)
        probs = _predict_logistic(X_test, logistic)
        test = test.copy(); test["actor_probability"] = probs
        hits = []
        for _, group in test.groupby(["episode_index", "step_index"]):
            hits.append(int(group.loc[group["actor_probability"].idxmax(), "offer_is_chosen"]) == 1)
        critic_test = chosen[chosen["episode_index"].isin(holdout)]
        critic_mae = float(np.abs(critic_test["mc_return"] - critic_test["critic_return"]).mean())
        artifact = {"numeric_cols": num, "categorical_cols": cat, "categories": actor_categories, "logistic": logistic}
        run_id = f"rng_actor_critic::{dataset_id}::{_now()}"
        con.execute("INSERT INTO fantasy_rng_actor_critic_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (run_id, dataset_id, critic_alpha, advantage_temperature, len(train), len(test), critic_mae, float(np.mean(hits) if hits else 0.0), _now(), "Monte-Carlo state-return critic + advantage-weighted actor."))
        output = test[["episode_index", "step_index", "offer_rank_in_set", "offer_action_id", "offer_is_chosen", "advantage", "actor_probability"]].copy()
        output["mc_return"] = [float(chosen.set_index(["episode_index", "step_index"]).loc[(int(r.episode_index), int(r.step_index)), "mc_return"]) for r in output.itertuples()]
        output["critic_return"] = [float(chosen.set_index(["episode_index", "step_index"]).loc[(int(r.episode_index), int(r.step_index)), "critic_return"]) for r in output.itertuples()]
        con.executemany("INSERT INTO fantasy_rng_actor_critic_outputs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [(run_id, int(r.episode_index), int(r.step_index), int(r.offer_rank_in_set), str(r.offer_action_id), int(r.offer_is_chosen), float(r.mc_return), float(r.critic_return), float(r.advantage), float(r.actor_probability), "test") for r in output.itertuples()])
        con.commit()
        critic_artifact = {"numeric_cols": state_num, "categorical_cols": state_cat, "categories": categories, "ridge": critic}
        return {"run_id": run_id, "artifact": artifact, "critic_artifact": critic_artifact, "critic_mae": critic_mae, "actor_top1_acc": float(np.mean(hits) if hits else 0.0), "train_rows": len(train), "test_rows": len(test)}
    finally:
        con.close()
