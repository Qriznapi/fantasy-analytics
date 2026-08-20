from __future__ import annotations

import json
import sqlite3
from typing import Any

import numpy as np
import pandas as pd

from fantasy_rng_actor_critic import _ridge_fit, _ridge_predict, _state_spec
from fantasy_rng_policy_models import _fit_categories, _matrix


def create_replay_schema(con: sqlite3.Connection) -> None:
    con.executescript("""
    CREATE TABLE IF NOT EXISTS fantasy_rng_rl_run_metadata (
      run_id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL, actor_source TEXT NOT NULL,
      environment_config_json TEXT NOT NULL, token_distribution_version TEXT NOT NULL,
      created_at_utc TEXT NOT NULL, critic_metrics_json TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS fantasy_rng_rl_replay_steps (
      run_id TEXT NOT NULL, episode_index INTEGER NOT NULL, step_index INTEGER NOT NULL,
      offer_rank INTEGER NOT NULL, chosen INTEGER NOT NULL, policy_probability REAL NOT NULL,
      chosen_log_prob REAL NOT NULL, immediate_delta REAL NOT NULL, terminal_value REAL NOT NULL,
      mc_return REAL NOT NULL, critic_return REAL NOT NULL, advantage REAL NOT NULL,
      feature_payload_json TEXT NOT NULL,
      PRIMARY KEY(run_id, episode_index, step_index, offer_rank)
    );
    DROP VIEW IF EXISTS analytics_rng_rl_runs;
    CREATE VIEW analytics_rng_rl_runs AS
    SELECT r.run_id, r.dataset_id, r.episodes, r.max_steps, r.avg_reward, r.created_at_utc,
           m.actor_source, m.environment_config_json, m.token_distribution_version, m.critic_metrics_json
    FROM fantasy_rng_rl_runs r LEFT JOIN fantasy_rng_rl_run_metadata m USING(run_id);
    """)
    con.commit()


def cross_fitted_critic(frame: pd.DataFrame, *, folds: int = 3, alpha: float = 25.0) -> tuple[pd.DataFrame, dict[str, Any]]:
    chosen = frame[frame["chosen"].astype(int) == 1].copy()
    state_num, state_cat = _state_spec(chosen)
    episodes = sorted(chosen["episode_index"].astype(int).unique())
    fold_count = max(2, min(int(folds), len(episodes))) if len(episodes) > 1 else 1
    predictions = pd.Series(index=chosen.index, dtype=float)
    for fold in range(fold_count):
        test_mask = (chosen["episode_index"].astype(int) % fold_count) == fold if fold_count > 1 else pd.Series(True, index=chosen.index)
        train = chosen[~test_mask] if fold_count > 1 else chosen
        test = chosen[test_mask]
        categories = _fit_categories(train, state_cat)
        x_train = _matrix(train, numeric_cols=state_num, categorical_cols=state_cat, categories=categories)
        x_test = _matrix(test, numeric_cols=state_num, categorical_cols=state_cat, categories=categories)
        model = _ridge_fit(x_train, train["mc_return"].to_numpy(dtype=float), alpha)
        predictions.loc[test.index] = _ridge_predict(x_test, model)
    chosen["critic_return"] = predictions.fillna(chosen["mc_return"].mean()).astype(float)
    chosen["advantage"] = chosen["mc_return"].astype(float) - chosen["critic_return"].astype(float)
    mapping = chosen.set_index(["episode_index", "step_index"])[["critic_return", "advantage"]]
    out = frame.copy()
    out["critic_return"] = [float(mapping.loc[(int(row.episode_index), int(row.step_index)), "critic_return"]) for row in out.itertuples()]
    out["advantage"] = [float(mapping.loc[(int(row.episode_index), int(row.step_index)), "advantage"]) for row in out.itertuples()]
    actual = chosen["mc_return"].astype(float)
    pred = chosen["critic_return"].astype(float)
    variance = float(np.var(actual))
    explained = float(1.0 - np.var(actual - pred) / variance) if variance > 1e-9 else 0.0
    metrics = {
        "folds": fold_count,
        "critic_mae": float(np.abs(actual - pred).mean()),
        "critic_spearman": float(actual.rank().corr(pred.rank(), method="pearson") or 0.0),
        "critic_explained_variance": explained,
        "advantage_mean": float(chosen["advantage"].mean()),
        "advantage_std": float(chosen["advantage"].std(ddof=0)),
    }
    return out, metrics


def persist_replay(con: sqlite3.Connection, *, run_id: str, frame: pd.DataFrame, metadata: dict[str, Any]) -> None:
    create_replay_schema(con)
    con.execute("DELETE FROM fantasy_rng_rl_replay_steps WHERE run_id = ?", (run_id,))
    con.execute("INSERT OR REPLACE INTO fantasy_rng_rl_run_metadata VALUES (?, ?, ?, ?, ?, ?, ?)", (
        run_id, metadata["dataset_id"], metadata["actor_source"], json.dumps(metadata["environment"], ensure_ascii=False),
        metadata["token_distribution_version"], metadata["created_at_utc"], json.dumps(metadata["critic_metrics"], ensure_ascii=False),
    ))
    con.executemany("INSERT INTO fantasy_rng_rl_replay_steps VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
        (run_id, int(r.episode_index), int(r.step_index), int(r.offer_rank_in_set), int(r.chosen), float(r.policy_probability),
         float(r.chosen_log_prob), float(r.realized_delta), float(r.terminal_value), float(r.mc_return),
         float(r.critic_return), float(r.advantage), json.dumps(r._asdict(), ensure_ascii=False, default=str))
        for r in frame.itertuples()
    ])
    con.commit()
