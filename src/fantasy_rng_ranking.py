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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS fantasy_rng_pairwise_builds (
            dataset_id TEXT PRIMARY KEY,
            source_dataset_id TEXT NOT NULL,
            row_count INTEGER NOT NULL,
            created_at_utc TEXT NOT NULL,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS fantasy_rng_pairwise_samples (
            dataset_id TEXT NOT NULL,
            episode_index INTEGER NOT NULL,
            step_index INTEGER NOT NULL,
            left_offer_rank INTEGER NOT NULL,
            right_offer_rank INTEGER NOT NULL,
            left_action_id TEXT NOT NULL,
            right_action_id TEXT NOT NULL,
            label_left_better INTEGER NOT NULL,
            feature_payload_json TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (dataset_id, episode_index, step_index, left_offer_rank, right_offer_rank)
        );

        CREATE TABLE IF NOT EXISTS fantasy_rng_ranking_model_runs (
            run_id TEXT PRIMARY KEY,
            dataset_id TEXT NOT NULL,
            alpha REAL NOT NULL,
            epochs INTEGER NOT NULL,
            learning_rate REAL NOT NULL,
            train_rows INTEGER NOT NULL,
            test_rows INTEGER NOT NULL,
            created_at_utc TEXT NOT NULL,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS fantasy_rng_ranking_model_eval (
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


def _load_payload_frame(con: sqlite3.Connection, source_dataset_id: str) -> pd.DataFrame:
    df = pd.read_sql_query(
        """
        SELECT feature_payload_json
        FROM fantasy_rng_training_samples
        WHERE dataset_id = ?
        ORDER BY episode_index, step_index, offer_rank_in_set
        """,
        con,
        params=(source_dataset_id,),
    )
    if df.empty:
        return df
    return pd.DataFrame([json.loads(text) for text in df["feature_payload_json"].tolist()])


def build_pairwise_frame(source_frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, step_group in source_frame.groupby(["episode_index", "step_index"], sort=False):
        items = step_group.to_dict(orient="records")
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                left = items[i]
                right = items[j]
                left_score = float(left.get("target_future_gain", 0.0))
                right_score = float(right.get("target_future_gain", 0.0))
                if left_score == right_score:
                    continue
                feature_row = {
                    "episode_index": int(left.get("episode_index", 0)),
                    "step_index": int(left.get("step_index", 0)),
                    "left_offer_rank": int(left.get("offer_rank_in_set", 0)),
                    "right_offer_rank": int(right.get("offer_rank_in_set", 0)),
                    "left_action_id": str(left.get("offer_action_id", "")),
                    "right_action_id": str(right.get("offer_action_id", "")),
                    "label_left_better": 1 if left_score > right_score else 0,
                }
                numeric_keys = [
                    "state_banner_value",
                    "state_rolls_left",
                    "state_progress_ratio",
                    "offer_expected_delta",
                    "offer_p75_delta",
                    "offer_p90_delta",
                    "offer_current_multiplier",
                ]
                for key in numeric_keys:
                    feature_row[f"left_{key}"] = float(left.get(key, 0.0) or 0.0)
                    feature_row[f"right_{key}"] = float(right.get(key, 0.0) or 0.0)
                    feature_row[f"diff_{key}"] = float(left.get(key, 0.0) or 0.0) - float(right.get(key, 0.0) or 0.0)
                categorical_keys = [
                    "offer_action_id",
                    "offer_token_type",
                    "offer_role_scope",
                    "offer_current_stat_name",
                    "offer_current_quality_tier",
                    "offer_current_trait_name",
                ]
                for key in categorical_keys:
                    feature_row[f"left_{key}"] = str(left.get(key, ""))
                    feature_row[f"right_{key}"] = str(right.get(key, ""))
                rows.append(feature_row)
    return pd.DataFrame(rows)


def persist_pairwise_dataset(
    con: sqlite3.Connection,
    *,
    dataset_id: str,
    source_dataset_id: str,
    frame: pd.DataFrame,
) -> None:
    create_schema(con)
    cur = con.cursor()
    cur.execute("DELETE FROM fantasy_rng_pairwise_samples WHERE dataset_id = ?", (dataset_id,))
    cur.execute(
        """
        INSERT OR REPLACE INTO fantasy_rng_pairwise_builds(
            dataset_id, source_dataset_id, row_count, created_at_utc, notes
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            dataset_id,
            source_dataset_id,
            int(len(frame)),
            utc_now(),
            "Pairwise offer-ranking dataset derived from RNG self-play samples.",
        ),
    )
    if not frame.empty:
        rows = [
            (
                dataset_id,
                int(item["episode_index"]),
                int(item["step_index"]),
                int(item["left_offer_rank"]),
                int(item["right_offer_rank"]),
                str(item["left_action_id"]),
                str(item["right_action_id"]),
                int(item["label_left_better"]),
                json.dumps(item, ensure_ascii=False, sort_keys=True),
                utc_now(),
            )
            for item in frame.to_dict(orient="records")
        ]
        cur.executemany(
            """
            INSERT OR REPLACE INTO fantasy_rng_pairwise_samples(
                dataset_id, episode_index, step_index, left_offer_rank, right_offer_rank,
                left_action_id, right_action_id, label_left_better, feature_payload_json, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    con.commit()


def _matrix(frame: pd.DataFrame, numeric_cols: list[str], categorical_cols: list[str], categories: dict[str, list[str]]) -> np.ndarray:
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


def _feature_spec(frame: pd.DataFrame) -> tuple[list[str], list[str]]:
    meta_cols = {
        "episode_index",
        "step_index",
        "left_offer_rank",
        "right_offer_rank",
        "label_left_better",
    }
    numeric_cols: list[str] = []
    categorical_cols: list[str] = []
    for col in frame.columns:
        if col in meta_cols:
            continue
        if frame[col].dtype == object:
            categorical_cols.append(col)
        else:
            numeric_cols.append(col)
    return sorted(set(numeric_cols)), sorted(set(categorical_cols))


def _score_pairwise_rows(frame: pd.DataFrame, artifact: dict[str, Any]) -> np.ndarray:
    numeric_cols = list(artifact["numeric_cols"])
    categorical_cols = list(artifact["categorical_cols"])
    categories = {str(k): list(v) for k, v in artifact["categories"].items()}
    X = _matrix(frame, numeric_cols, categorical_cols, categories)
    w = np.asarray(artifact["w"], dtype=float)
    x_mean = np.asarray(artifact["x_mean"], dtype=float)
    x_std = np.asarray(artifact["x_std"], dtype=float)
    if X.size == 0 or len(w) == 0:
        logits = np.zeros(len(frame), dtype=float)
    else:
        Xn = (X - x_mean) / np.where(x_std == 0, 1.0, x_std)
        logits = Xn @ w + float(artifact["b"])
    return 1.0 / (1.0 + np.exp(-np.clip(logits, -30, 30)))


def score_offer_set_with_ranker(
    *,
    slots: list[dict[str, Any]],
    offers: list[dict[str, Any]],
    baseline_value_before: float,
    step_index: int,
    max_steps: int,
    artifact: dict[str, Any],
) -> pd.DataFrame:
    offer_frame = pd.DataFrame(
        build_offer_rows_from_state(
            slots,
            offers,
            baseline_value_before=baseline_value_before,
            step_index=step_index,
            max_steps=max_steps,
        )
    )
    if offer_frame.empty:
        return offer_frame
    scores = np.zeros(len(offer_frame), dtype=float)
    counts = np.zeros(len(offer_frame), dtype=float)
    items = offer_frame.to_dict(orient="records")
    pair_rows: list[dict[str, Any]] = []
    pair_indices: list[tuple[int, int]] = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            left = items[i]
            right = items[j]
            feature_row = {
                "episode_index": 0,
                "step_index": 0,
                "left_offer_rank": int(left.get("offer_rank_in_set", i)),
                "right_offer_rank": int(right.get("offer_rank_in_set", j)),
                "left_action_id": str(left.get("offer_action_id", "")),
                "right_action_id": str(right.get("offer_action_id", "")),
                "label_left_better": 0,
            }
            numeric_keys = [
                "state_banner_value",
                "state_rolls_left",
                "state_progress_ratio",
                "offer_expected_delta",
                "offer_p75_delta",
                "offer_p90_delta",
                "offer_current_multiplier",
            ]
            categorical_keys = [
                "offer_action_id",
                "offer_token_type",
                "offer_role_scope",
                "offer_current_stat_name",
                "offer_current_quality_tier",
                "offer_current_trait_name",
            ]
            for key in numeric_keys:
                lv = float(left.get(key, 0.0) or 0.0)
                rv = float(right.get(key, 0.0) or 0.0)
                feature_row[f"left_{key}"] = lv
                feature_row[f"right_{key}"] = rv
                feature_row[f"diff_{key}"] = lv - rv
            for key in categorical_keys:
                feature_row[f"left_{key}"] = str(left.get(key, ""))
                feature_row[f"right_{key}"] = str(right.get(key, ""))
            pair_rows.append(feature_row)
            pair_indices.append((i, j))
    if pair_rows:
        pair_probs = _score_pairwise_rows(pd.DataFrame(pair_rows), artifact)
        for (i, j), prob_left_better in zip(pair_indices, pair_probs):
            scores[i] += float(prob_left_better)
            scores[j] += float(1.0 - prob_left_better)
            counts[i] += 1.0
            counts[j] += 1.0
    offer_frame["ranking_score"] = [float(scores[idx] / counts[idx]) if counts[idx] > 0 else 0.0 for idx in range(len(offer_frame))]
    return offer_frame


def train_pairwise_ranking_model(
    db_path: Path,
    *,
    source_dataset_id: str,
    alpha: float = 1.0,
    epochs: int = 300,
    learning_rate: float = 0.05,
) -> dict[str, Any]:
    con = sqlite3.connect(str(db_path))
    try:
        create_schema(con)
        source_frame = _load_payload_frame(con, source_dataset_id)
        if source_frame.empty:
            raise RuntimeError(f"No self-play rows found for dataset_id={source_dataset_id}")
        pairwise_dataset_id = f"rng_pairwise::{source_dataset_id}"
        pairwise = build_pairwise_frame(source_frame)
        persist_pairwise_dataset(con, dataset_id=pairwise_dataset_id, source_dataset_id=source_dataset_id, frame=pairwise)
        episodes = sorted({int(v) for v in pairwise["episode_index"].tolist()}) if not pairwise.empty else []
        if len(episodes) <= 1:
            train = pairwise.copy()
            test = pairwise.copy()
        else:
            test_count = max(1, int(math.ceil(len(episodes) * 0.25)))
            test_episodes = set(episodes[-test_count:])
            train = pairwise[~pairwise["episode_index"].isin(test_episodes)].copy()
            test = pairwise[pairwise["episode_index"].isin(test_episodes)].copy()
        numeric_cols, categorical_cols = _feature_spec(train)
        categories = {col: sorted({str(v) for v in train[col].fillna("").tolist()}) for col in categorical_cols}
        X_train = _matrix(train, numeric_cols, categorical_cols, categories)
        X_test = _matrix(test, numeric_cols, categorical_cols, categories)
        y_train = train["label_left_better"].fillna(0).astype(int).to_numpy(dtype=float)
        y_test = test["label_left_better"].fillna(0).astype(int).to_numpy(dtype=float)
        x_mean = X_train.mean(axis=0) if len(X_train) else np.zeros(0, dtype=float)
        x_std = X_train.std(axis=0) if len(X_train) else np.ones(0, dtype=float)
        x_std[x_std == 0] = 1.0
        Xn = (X_train - x_mean) / x_std if len(X_train) else X_train
        w = np.zeros(Xn.shape[1], dtype=float) if Xn.ndim == 2 else np.zeros(0, dtype=float)
        b = 0.0
        for _ in range(max(1, int(epochs))):
            logits = Xn @ w + b if len(w) else np.zeros(len(y_train), dtype=float)
            probs = 1.0 / (1.0 + np.exp(-np.clip(logits, -30, 30)))
            grad_w = (Xn.T @ (probs - y_train)) / max(1, len(y_train)) + alpha * w / max(1, len(y_train)) if len(w) else np.zeros(0, dtype=float)
            grad_b = float(np.mean(probs - y_train))
            if len(w):
                w -= learning_rate * grad_w
            b -= learning_rate * grad_b
        Xtn = (X_test - x_mean) / x_std if len(X_test) else X_test
        test_logits = Xtn @ w + b if len(w) else np.zeros(len(y_test), dtype=float)
        test_probs = 1.0 / (1.0 + np.exp(-np.clip(test_logits, -30, 30)))
        test_pred = (test_probs >= 0.5).astype(int)
        acc = float((test_pred == y_test).mean()) if len(y_test) else 0.0
        run_id = f"rng_ranking::{source_dataset_id}::{utc_now()}"
        cur = con.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO fantasy_rng_ranking_model_runs(
                run_id, dataset_id, alpha, epochs, learning_rate, train_rows, test_rows, created_at_utc, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                pairwise_dataset_id,
                float(alpha),
                int(epochs),
                float(learning_rate),
                int(len(train)),
                int(len(test)),
                utc_now(),
                "Pairwise ranking model over self-play offer comparisons.",
            ),
        )
        cur.execute(
            """
            INSERT OR REPLACE INTO fantasy_rng_ranking_model_eval(
                run_id, metric_name, metric_value, metric_scope, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, "metric_pairwise_acc", acc, "test", utc_now()),
        )
        con.commit()
        return {
            "run_id": run_id,
            "pairwise_dataset_id": pairwise_dataset_id,
            "metrics": {"metric_pairwise_acc": acc},
            "artifact": {
                "numeric_cols": numeric_cols,
                "categorical_cols": categorical_cols,
                "categories": categories,
                "w": w.tolist(),
                "b": float(b),
                "x_mean": x_mean.tolist(),
                "x_std": x_std.tolist(),
            },
        }
    finally:
        con.close()
