from __future__ import annotations

import json
import math
import random
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from fantasy_rng_episode import (
    EpisodeContext,
    _offer_payload,
    _sample_offers,
    _summarize_action_from_state,
    build_episode_context,
    evaluate_slots,
)
from fantasy_rng_foundation import (
    BENCHMARK_DB_PATH,
    DEFAULT_PRESET_PATH,
    TARGET_DB_PATH,
    build_rng_policy_foundation,
    enumerate_candidate_actions,
)
from fantasy_roll_simulator import RollAction, apply_roll_action
from project_db import infer_project_root_from_db_path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_PATH = PROJECT_ROOT / "reports" / "rng_self_learning_model_v1.json"

NUMERIC_FEATURES = [
    "slot_index",
    "current_multiplier",
    "baseline_intrinsic_value_raw",
    "expected_delta_raw",
    "median_delta_raw",
    "p75_delta_raw",
    "p90_delta_raw",
    "positive_rate",
    "downside_rate",
]

CATEGORICAL_FEATURES = [
    "risk_profile",
    "token_type",
    "role_scope",
    "current_stat_name",
    "current_quality_tier",
    "current_trait_name",
]


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
    except Exception:
        return default
    if math.isnan(value):
        return default
    return value


def latest_policy_run_id(con: sqlite3.Connection, profile_id: str | None = None) -> str | None:
    if profile_id:
        row = con.execute(
            """
            SELECT run_id
            FROM fantasy_rng_policy_runs
            WHERE profile_id = ?
            ORDER BY created_at_utc DESC
            LIMIT 1
            """,
            (profile_id,),
        ).fetchone()
    else:
        row = con.execute(
            """
            SELECT run_id
            FROM fantasy_rng_policy_runs
            ORDER BY created_at_utc DESC
            LIMIT 1
            """
        ).fetchone()
    return str(row[0]) if row else None


def load_transition_learning_frame(con: sqlite3.Connection, run_id: str | None = None, profile_id: str | None = None) -> pd.DataFrame:
    if run_id is None:
        run_id = latest_policy_run_id(con, profile_id=profile_id)
    if not run_id:
        return pd.DataFrame()
    query = """
        SELECT
            a.run_id,
            a.action_id,
            a.risk_profile,
            a.token_type,
            a.role_scope,
            a.slot_index,
            a.current_stat_name,
            a.current_quality_tier,
            a.current_trait_name,
            a.current_multiplier,
            a.baseline_intrinsic_value_raw,
            a.expected_delta_raw,
            a.median_delta_raw,
            a.p75_delta_raw,
            a.p90_delta_raw,
            a.positive_rate,
            a.downside_rate,
            t.simulation_index,
            t.delta_raw AS target_delta_raw,
            t.next_intrinsic_value_raw
        FROM fantasy_rng_action_rollups a
        JOIN fantasy_rng_transition_samples t
          ON t.run_id = a.run_id
         AND t.action_id = a.action_id
        WHERE a.run_id = ?
        ORDER BY a.action_id, t.simulation_index
    """
    return pd.read_sql_query(query, con, params=(run_id,))


def _fit_categories(df: pd.DataFrame) -> dict[str, list[str]]:
    categories: dict[str, list[str]] = {}
    for feature in CATEGORICAL_FEATURES:
        values = sorted({str(value) for value in df[feature].fillna("").tolist()})
        categories[feature] = values
    return categories


def _row_to_features(row: dict[str, Any], categories: dict[str, list[str]]) -> np.ndarray:
    values: list[float] = [1.0]
    for feature in NUMERIC_FEATURES:
        values.append(safe_float(row.get(feature, 0.0)))
    for feature in CATEGORICAL_FEATURES:
        raw = str(row.get(feature, "") or "")
        for category in categories[feature]:
            values.append(1.0 if raw == category else 0.0)
    return np.asarray(values, dtype=float)


def build_feature_matrix(df: pd.DataFrame, categories: dict[str, list[str]] | None = None) -> tuple[np.ndarray, list[str], dict[str, list[str]]]:
    if categories is None:
        categories = _fit_categories(df)
    feature_names = ["bias"] + NUMERIC_FEATURES[:]
    for feature in CATEGORICAL_FEATURES:
        for category in categories[feature]:
            feature_names.append(f"{feature}={category}")
    matrix = np.vstack([_row_to_features(row, categories) for row in df.to_dict(orient="records")])
    return matrix, feature_names, categories


def train_ridge_delta_model(
    df: pd.DataFrame,
    *,
    alpha: float = 25.0,
    test_fraction: float = 0.2,
    seed: int = 7,
) -> dict[str, Any]:
    if df.empty:
        raise RuntimeError("Transition learning frame is empty; build RNG foundation with sample_store_limit > 0 first.")
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(df))
    test_size = max(1, int(len(df) * test_fraction))
    test_idx = perm[:test_size]
    train_idx = perm[test_size:]
    if len(train_idx) == 0:
        train_idx = perm
        test_idx = perm[:1]

    train_df = df.iloc[train_idx].reset_index(drop=True)
    test_df = df.iloc[test_idx].reset_index(drop=True)

    x_train, feature_names, categories = build_feature_matrix(train_df)
    y_train = train_df["target_delta_raw"].astype(float).to_numpy()
    x_test, _, _ = build_feature_matrix(test_df, categories=categories)
    y_test = test_df["target_delta_raw"].astype(float).to_numpy()

    reg = np.eye(x_train.shape[1], dtype=float) * float(alpha)
    reg[0, 0] = 0.0
    beta = np.linalg.solve(x_train.T @ x_train + reg, x_train.T @ y_train)

    train_pred = x_train @ beta
    test_pred = x_test @ beta

    action_eval = test_df[["action_id", "target_delta_raw"]].copy()
    action_eval["pred_delta_raw"] = test_pred
    grouped = action_eval.groupby("action_id", as_index=False).agg(
        actual_mean=("target_delta_raw", "mean"),
        pred_mean=("pred_delta_raw", "mean"),
    )
    spearman = grouped["actual_mean"].rank().corr(grouped["pred_mean"].rank(), method="pearson") if len(grouped) > 1 else 1.0

    return {
        "alpha": float(alpha),
        "test_fraction": float(test_fraction),
        "feature_names": feature_names,
        "categories": categories,
        "coefficients": beta.tolist(),
        "metrics": {
            "train_rows": int(len(train_df)),
            "test_rows": int(len(test_df)),
            "train_mae": float(np.mean(np.abs(train_pred - y_train))),
            "test_mae": float(np.mean(np.abs(test_pred - y_test))),
            "train_rmse": float(np.sqrt(np.mean((train_pred - y_train) ** 2))),
            "test_rmse": float(np.sqrt(np.mean((test_pred - y_test) ** 2))),
            "test_action_spearman": float(spearman if not math.isnan(float(spearman)) else 0.0),
        },
    }


def save_model_payload(model_payload: dict[str, Any], out_path: Path = DEFAULT_MODEL_PATH) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(model_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def load_model_payload(path: Path = DEFAULT_MODEL_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def predict_delta_rows(rows: list[dict[str, Any]], model_payload: dict[str, Any]) -> np.ndarray:
    categories = {key: list(value) for key, value in model_payload["categories"].items()}
    matrix = np.vstack([_row_to_features(row, categories) for row in rows])
    beta = np.asarray(model_payload["coefficients"], dtype=float)
    return matrix @ beta


def score_action_rollups(rollup_df: pd.DataFrame, model_payload: dict[str, Any]) -> pd.DataFrame:
    rows = rollup_df.to_dict(orient="records")
    scores = predict_delta_rows(rows, model_payload)
    out = rollup_df.copy()
    out["model_pred_delta_raw"] = scores
    return out.sort_values("model_pred_delta_raw", ascending=False).reset_index(drop=True)


def _format_slot_token(slot: dict[str, Any]) -> str:
    role_scope = str(slot.get("role_scope", ""))
    slot_index = int(slot.get("slot_index", 0))
    stat_name = str(slot.get("stat_name", ""))
    quality_tier = str(slot.get("quality_tier", ""))
    trait_name = str(slot.get("trait_name", ""))
    multiplier = safe_float(slot.get("multiplier", 0.0))
    return f"{role_scope}[{slot_index}]={stat_name}/{quality_tier}/{trait_name}/{multiplier:.2f}"


def summarize_slot_state(slots: list[dict[str, Any]]) -> str:
    ordered = sorted(
        [dict(slot) for slot in slots],
        key=lambda item: (str(item.get("role_scope", "")), int(item.get("slot_index", 0))),
    )
    return " | ".join(_format_slot_token(slot) for slot in ordered)


def _offer_feature_row(action: dict[str, Any], summary: dict[str, Any], *, risk_profile: str) -> dict[str, Any]:
    return {
        "risk_profile": risk_profile,
        "token_type": action["token_type"],
        "role_scope": action["role_scope"],
        "slot_index": int(action["slot_index"]),
        "current_stat_name": action["current_stat_name"],
        "current_quality_tier": action["current_quality_tier"],
        "current_trait_name": action["current_trait_name"],
        "current_multiplier": safe_float(action.get("current_multiplier", 1.0), 1.0),
        "baseline_intrinsic_value_raw": safe_float(summary["baseline_value_before"]),
        "expected_delta_raw": safe_float(summary["expected_delta"]),
        "median_delta_raw": safe_float(summary["median_delta"]),
        "p75_delta_raw": safe_float(summary["p75_delta"]),
        "p90_delta_raw": safe_float(summary["p90_delta"]),
        "positive_rate": safe_float(summary["positive_rate"]),
        "downside_rate": max(0.0, 1.0 - safe_float(summary["positive_rate"])),
    }


def simulate_learned_policy_episodes(
    *,
    profile_id: str,
    model_payload: dict[str, Any],
    db_path: Path = TARGET_DB_PATH,
    benchmark_db_path: Path = BENCHMARK_DB_PATH,
    benchmark_event_id: str = "ewc2026",
    preset_path: Path = DEFAULT_PRESET_PATH,
    objective_mode: str = "balanced",
    episodes: int = 40,
    max_steps: int = 30,
    offers_per_step: int = 3,
    eval_sims_per_offer: int = 24,
    seed: int = 17,
    risk_profile: str = "balanced",
    progress_every: int = 0,
) -> dict[str, Any]:
    ctx = build_episode_context(
        profile_id=profile_id,
        db_path=db_path,
        benchmark_db_path=benchmark_db_path,
        benchmark_event_id=benchmark_event_id,
        preset_path=preset_path,
    )
    target_con = sqlite3.connect(str(db_path))
    try:
        action_specs = enumerate_candidate_actions(target_con, profile_id, ctx.preset)
    finally:
        target_con.close()

    episode_rows: list[dict[str, Any]] = []
    progress_rows: list[dict[str, Any]] = []
    best_episode_steps_df = pd.DataFrame()
    best_episode_summary: dict[str, Any] | None = None
    for episode_index in range(int(episodes)):
        rng = random.Random(seed + episode_index)
        slots = [dict(slot) for slot in ctx.base_slots]
        initial_value = evaluate_slots(slots, ctx, objective_mode)
        initial_snapshot = summarize_slot_state(slots)
        baseline_before = initial_value
        start_row_index = len(episode_rows)
        for step_index in range(int(max_steps)):
            offers = _sample_offers(rng, action_specs, offers_per_step)
            if not offers:
                break
            offer_summaries = []
            for offer_index, action in enumerate(offers):
                summary = _summarize_action_from_state(
                    slots=slots,
                    action_spec=action,
                    ctx=ctx,
                    objective_mode=objective_mode,
                    rng_seed=seed * 10000 + episode_index * 1000 + step_index * 10 + offer_index,
                    eval_sims_per_offer=eval_sims_per_offer,
                )
                offer_summaries.append({"action": action, "summary": summary})
            score_rows = [_offer_feature_row(item["action"], item["summary"], risk_profile=risk_profile) for item in offer_summaries]
            preds = predict_delta_rows(score_rows, model_payload)
            chosen_index = int(np.argmax(preds))
            chosen = offer_summaries[chosen_index]
            slots = apply_roll_action(
                slots,
                RollAction(
                    token_type=str(chosen["action"]["token_type"]),
                    role_scope=str(chosen["action"]["role_scope"]),
                    slot_index=int(chosen["action"]["slot_index"]),
                ),
                distribution_index=ctx.distribution_indices[f"ti2026_generic_{chosen['action']['token_type']}_v1"],
                template_color_map=ctx.template_color_map,
                rng=rng,
            )
            realized_value = evaluate_slots(slots, ctx, objective_mode)
            realized_delta = float(realized_value) - float(baseline_before)
            episode_rows.append(
                {
                    "episode_index": episode_index,
                    "step_index": step_index,
                    "chosen_action_id": chosen["action"]["action_id"],
                    "chosen_token_type": chosen["action"]["token_type"],
                    "chosen_role_scope": chosen["action"]["role_scope"],
                    "chosen_slot_index": int(chosen["action"]["slot_index"]),
                    "predicted_delta": float(preds[chosen_index]),
                    "expected_delta": float(chosen["summary"]["expected_delta"]),
                    "p75_delta": float(chosen["summary"]["p75_delta"]),
                    "realized_delta": realized_delta,
                    "baseline_before": float(baseline_before),
                    "realized_value_after": float(realized_value),
                    "offer_set_json": _offer_payload(offer_summaries),
                }
            )
            baseline_before = realized_value
        final_value = baseline_before
        episode_rows.append(
            {
                "episode_index": episode_index,
                "step_index": -1,
                "chosen_action_id": "__summary__",
                "chosen_token_type": "",
                "chosen_role_scope": "",
                "chosen_slot_index": -1,
                "predicted_delta": 0.0,
                "expected_delta": 0.0,
                "p75_delta": 0.0,
                "realized_delta": float(final_value) - float(initial_value),
                "baseline_before": float(initial_value),
                "realized_value_after": float(final_value),
                "offer_set_json": "[]",
                "initial_slot_state": initial_snapshot,
                "final_slot_state": summarize_slot_state(slots),
            }
        )
        if progress_every and ((episode_index + 1) % int(progress_every) == 0):
            progress_rows.append(
                {
                    "episode_index": int(episode_index),
                    "initial_value": float(initial_value),
                    "final_value": float(final_value),
                    "total_delta": float(final_value) - float(initial_value),
                    "initial_slot_state": initial_snapshot,
                    "final_slot_state": summarize_slot_state(slots),
                }
            )
        if best_episode_summary is None or float(final_value) > float(best_episode_summary["final_value"]):
            best_episode_summary = {
                "episode_index": int(episode_index),
                "initial_value": float(initial_value),
                "final_value": float(final_value),
                "total_delta": float(final_value) - float(initial_value),
                "initial_slot_state": initial_snapshot,
                "final_slot_state": summarize_slot_state(slots),
            }
            best_episode_steps_df = pd.DataFrame(episode_rows[start_row_index:]).copy()

    frame = pd.DataFrame(episode_rows)
    summary_df = frame[frame["step_index"] == -1].copy()
    return {
        "episodes": int(episodes),
        "avg_final_value": float(summary_df["realized_value_after"].mean()),
        "avg_total_delta": float(summary_df["realized_delta"].mean()),
        "min_final_value": float(summary_df["realized_value_after"].min()),
        "max_final_value": float(summary_df["realized_value_after"].max()),
        "summary_df": summary_df,
        "steps_df": frame[frame["step_index"] >= 0].copy(),
        "progress_df": pd.DataFrame(progress_rows),
        "best_episode_summary": best_episode_summary or {},
        "best_episode_steps_df": best_episode_steps_df,
    }


def run_self_learning_round(
    *,
    profile_id: str,
    db_path: Path = TARGET_DB_PATH,
    benchmark_db_path: Path = BENCHMARK_DB_PATH,
    benchmark_event_id: str = "ewc2026",
    preset_path: Path = DEFAULT_PRESET_PATH,
    objective_mode: str = "balanced",
    simulations_per_action: int = 400,
    sample_store_limit: int = 400,
    alpha: float = 25.0,
    test_fraction: float = 0.2,
    eval_episodes: int = 40,
    eval_sims_per_offer: int = 24,
    risk_profile: str = "balanced",
    progress_every: int = 0,
    model_out_path: Path | None = None,
) -> dict[str, Any]:
    project_root = infer_project_root_from_db_path(db_path)
    resolved_model_out_path = Path(model_out_path) if model_out_path is not None else project_root / "reports" / "rng_self_learning_model_v1.json"
    foundation_result = build_rng_policy_foundation(
        profile_id=profile_id,
        db_path=db_path,
        benchmark_db_path=benchmark_db_path,
        benchmark_event_id=benchmark_event_id,
        preset_path=preset_path,
        objective_mode=objective_mode,
        simulations_per_action=simulations_per_action,
        sample_store_limit=sample_store_limit,
    )
    con = sqlite3.connect(str(db_path))
    try:
        learn_df = load_transition_learning_frame(con, run_id=str(foundation_result["run_id"]))
    finally:
        con.close()
    model_payload = train_ridge_delta_model(
        learn_df,
        alpha=alpha,
        test_fraction=test_fraction,
    )
    model_payload["source_run_id"] = str(foundation_result["run_id"])
    model_payload["profile_id"] = str(profile_id)
    model_payload["preset_path"] = str(preset_path)
    save_model_payload(model_payload, resolved_model_out_path)
    eval_result = simulate_learned_policy_episodes(
        profile_id=profile_id,
        model_payload=model_payload,
        db_path=db_path,
        benchmark_db_path=benchmark_db_path,
        benchmark_event_id=benchmark_event_id,
        preset_path=preset_path,
        objective_mode=objective_mode,
        episodes=eval_episodes,
        eval_sims_per_offer=eval_sims_per_offer,
        risk_profile=risk_profile,
        progress_every=progress_every,
    )
    return {
        "foundation_result": foundation_result,
        "model_payload": model_payload,
        "model_out_path": resolved_model_out_path,
        "evaluation": {
            "episodes": eval_result["episodes"],
            "avg_final_value": eval_result["avg_final_value"],
            "avg_total_delta": eval_result["avg_total_delta"],
            "min_final_value": eval_result["min_final_value"],
            "max_final_value": eval_result["max_final_value"],
        },
        "summary_df": eval_result["summary_df"],
        "steps_df": eval_result["steps_df"],
        "progress_df": eval_result["progress_df"],
        "best_episode_summary": eval_result["best_episode_summary"],
        "best_episode_steps_df": eval_result["best_episode_steps_df"],
    }
