from __future__ import annotations

import json
import random
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from fantasy_rng_episode import (
    DEFAULT_PRESET_PATH,
    TARGET_DB_PATH,
    BENCHMARK_DB_PATH,
    _sample_offers,
    _summarize_action_from_state,
    build_episode_context,
    evaluate_slots,
)
from fantasy_rng_foundation import enumerate_candidate_actions
from fantasy_rng_value_models import (
    DEFAULT_TEACHER_POLICIES,
    latest_dataset_id,
    score_offer_set_from_state,
    train_rng_value_models,
)
from fantasy_roll_simulator import RollAction, apply_roll_action


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
    except Exception:
        return default
    if pd.isna(value):
        return default
    return value


def create_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS fantasy_rng_planner_runs (
            run_id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            dataset_id TEXT NOT NULL,
            planner_mode TEXT NOT NULL,
            planning_horizon INTEGER NOT NULL,
            rollout_sims_per_offer INTEGER NOT NULL,
            eval_sims_per_offer INTEGER NOT NULL,
            episodes INTEGER NOT NULL,
            max_steps INTEGER NOT NULL,
            offers_per_step INTEGER NOT NULL,
            teacher_policies_json TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS fantasy_rng_planner_episode_summaries (
            run_id TEXT NOT NULL,
            episode_index INTEGER NOT NULL,
            initial_value REAL NOT NULL,
            final_value REAL NOT NULL,
            total_delta REAL NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, episode_index)
        );

        CREATE TABLE IF NOT EXISTS fantasy_rng_planner_step_choices (
            run_id TEXT NOT NULL,
            episode_index INTEGER NOT NULL,
            step_index INTEGER NOT NULL,
            baseline_value_before REAL NOT NULL,
            chosen_action_id TEXT NOT NULL,
            chosen_token_type TEXT NOT NULL,
            chosen_role_scope TEXT NOT NULL,
            chosen_slot_index INTEGER NOT NULL,
            chosen_plan_score REAL NOT NULL,
            chosen_predicted_future_gain REAL NOT NULL,
            chosen_predicted_choice_prob REAL NOT NULL,
            chosen_rollout_mean REAL NOT NULL,
            chosen_rollout_p75 REAL NOT NULL,
            chosen_rollout_p90 REAL NOT NULL,
            chosen_rollout_max REAL NOT NULL,
            realized_value_after REAL NOT NULL,
            realized_delta REAL NOT NULL,
            offer_set_json TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, episode_index, step_index)
        );
        """
    )
    con.commit()


def planner_utility(
    *,
    planner_mode: str,
    rollout_mean: float,
    rollout_p75: float,
    rollout_p90: float,
    rollout_max: float,
    predicted_future_gain: float,
    predicted_choice_prob: float,
) -> float:
    if planner_mode == "safe":
        return 0.55 * rollout_p75 + 0.20 * rollout_mean + 0.15 * predicted_future_gain + 0.10 * predicted_choice_prob * 1000.0
    if planner_mode == "ceiling":
        return 0.35 * rollout_p90 + 0.30 * rollout_max + 0.20 * rollout_mean + 0.10 * predicted_future_gain + 0.05 * predicted_choice_prob * 1000.0
    return 0.40 * rollout_mean + 0.25 * rollout_p75 + 0.15 * rollout_p90 + 0.15 * predicted_future_gain + 0.05 * predicted_choice_prob * 1000.0


def _score_offer_candidates(
    *,
    slots: list[dict[str, Any]],
    offer_summaries: list[dict[str, Any]],
    baseline_value_before: float,
    step_index: int,
    max_steps: int,
    model_artifact: dict[str, Any],
) -> pd.DataFrame:
    offers = []
    for item in offer_summaries:
        offers.append(
            {
                "action_id": item["action"]["action_id"],
                "token_type": item["action"]["token_type"],
                "role_scope": item["action"]["role_scope"],
                "slot_index": int(item["action"]["slot_index"]),
                "current_stat_name": item["action"]["current_stat_name"],
                "current_quality_tier": item["action"]["current_quality_tier"],
                "current_trait_name": item["action"]["current_trait_name"],
                "expected_delta": safe_float(item["summary"]["expected_delta"]),
                "p75_delta": safe_float(item["summary"]["p75_delta"]),
                "p90_delta": safe_float(item["summary"]["p90_delta"]),
            }
        )
    return score_offer_set_from_state(
        slots,
        offers,
        baseline_value_before=baseline_value_before,
        step_index=step_index,
        max_steps=max_steps,
        model_artifact=model_artifact,
    )


def _choose_offer_greedily(
    *,
    scored_offers: pd.DataFrame,
    planner_mode: str,
) -> int:
    if scored_offers.empty:
        return -1
    if planner_mode == "safe":
        score = 0.6 * scored_offers["offer_p75_delta"].astype(float) + 0.4 * scored_offers["predicted_choice_prob"].astype(float) * 1000.0
    elif planner_mode == "ceiling":
        score = 0.55 * scored_offers["offer_p90_delta"].astype(float) + 0.45 * scored_offers["predicted_future_gain"].astype(float)
    else:
        score = 0.5 * scored_offers["predicted_future_gain"].astype(float) + 0.5 * scored_offers["offer_p75_delta"].astype(float)
    return int(score.idxmax())


def _continue_with_model_policy(
    *,
    slots: list[dict[str, Any]],
    ctx,
    action_specs: list[dict[str, Any]],
    rng: random.Random,
    model_artifact: dict[str, Any],
    planner_mode: str,
    objective_mode: str,
    start_step_index: int,
    continuation_steps: int,
    max_steps: int,
    offers_per_step: int,
    eval_sims_per_offer: int,
) -> float:
    current_slots = [dict(slot) for slot in slots]
    for local_step in range(max(0, int(continuation_steps))):
        global_step_index = int(start_step_index) + local_step
        if global_step_index >= int(max_steps):
            break
        offers = _sample_offers(rng, action_specs, offers_per_step)
        if not offers:
            break
        offer_summaries = []
        for offer_index, action in enumerate(offers):
            summary = _summarize_action_from_state(
                slots=current_slots,
                action_spec=action,
                ctx=ctx,
                objective_mode=objective_mode,
                rng_seed=900000 + global_step_index * 100 + offer_index + rng.randrange(100000),
                eval_sims_per_offer=eval_sims_per_offer,
            )
            offer_summaries.append({"action": action, "summary": summary})
        baseline_value_before = evaluate_slots(current_slots, ctx, objective_mode)
        scored = _score_offer_candidates(
            slots=current_slots,
            offer_summaries=offer_summaries,
            baseline_value_before=baseline_value_before,
            step_index=global_step_index + 1,
            max_steps=max_steps,
            model_artifact=model_artifact,
        )
        chosen_row_index = _choose_offer_greedily(scored_offers=scored, planner_mode=planner_mode)
        if chosen_row_index < 0:
            break
        chosen = offer_summaries[chosen_row_index]
        current_slots = apply_roll_action(
            current_slots,
            RollAction(
                token_type=str(chosen["action"]["token_type"]),
                role_scope=str(chosen["action"]["role_scope"]),
                slot_index=int(chosen["action"]["slot_index"]),
            ),
            distribution_index=ctx.distribution_indices[f"ti2026_generic_{chosen['action']['token_type']}_v1"],
            template_color_map=ctx.template_color_map,
            rng=rng,
        )
    return evaluate_slots(current_slots, ctx, objective_mode)


def _plan_offer(
    *,
    slots: list[dict[str, Any]],
    action: dict[str, Any],
    immediate_scored_row: dict[str, Any],
    ctx,
    action_specs: list[dict[str, Any]],
    model_artifact: dict[str, Any],
    planner_mode: str,
    objective_mode: str,
    step_index: int,
    max_steps: int,
    offers_per_step: int,
    eval_sims_per_offer: int,
    rollout_sims_per_offer: int,
    planning_horizon: int,
    rng_seed: int,
) -> dict[str, Any]:
    rollout_values: list[float] = []
    for sim_idx in range(max(1, int(rollout_sims_per_offer))):
        rng = random.Random(rng_seed + sim_idx)
        next_slots = apply_roll_action(
            [dict(slot) for slot in slots],
            RollAction(
                token_type=str(action["token_type"]),
                role_scope=str(action["role_scope"]),
                slot_index=int(action["slot_index"]),
            ),
            distribution_index=ctx.distribution_indices[f"ti2026_generic_{action['token_type']}_v1"],
            template_color_map=ctx.template_color_map,
            rng=rng,
        )
        final_value = _continue_with_model_policy(
            slots=next_slots,
            ctx=ctx,
            action_specs=action_specs,
            rng=rng,
            model_artifact=model_artifact,
            planner_mode=planner_mode,
            objective_mode=objective_mode,
            start_step_index=step_index + 1,
            continuation_steps=max(0, int(planning_horizon) - 1),
            max_steps=max_steps,
            offers_per_step=offers_per_step,
            eval_sims_per_offer=eval_sims_per_offer,
        )
        rollout_values.append(float(final_value))
    ordered = sorted(rollout_values)
    rollout_mean = float(sum(ordered) / len(ordered))
    rollout_p75 = float(ordered[int((len(ordered) - 1) * 0.75)])
    rollout_p90 = float(ordered[int((len(ordered) - 1) * 0.90)])
    rollout_max = float(max(ordered))
    predicted_future_gain = safe_float(immediate_scored_row["predicted_future_gain"])
    predicted_choice_prob = safe_float(immediate_scored_row["predicted_choice_prob"])
    plan_score = planner_utility(
        planner_mode=planner_mode,
        rollout_mean=rollout_mean,
        rollout_p75=rollout_p75,
        rollout_p90=rollout_p90,
        rollout_max=rollout_max,
        predicted_future_gain=predicted_future_gain,
        predicted_choice_prob=predicted_choice_prob,
    )
    return {
        "action_id": str(action["action_id"]),
        "token_type": str(action["token_type"]),
        "role_scope": str(action["role_scope"]),
        "slot_index": int(action["slot_index"]),
        "predicted_future_gain": predicted_future_gain,
        "predicted_choice_prob": predicted_choice_prob,
        "rollout_mean": rollout_mean,
        "rollout_p75": rollout_p75,
        "rollout_p90": rollout_p90,
        "rollout_max": rollout_max,
        "plan_score": float(plan_score),
    }


def simulate_planner_episodes(
    *,
    profile_id: str,
    db_path: Path = TARGET_DB_PATH,
    benchmark_db_path: Path = BENCHMARK_DB_PATH,
    benchmark_event_id: str = "ewc2026",
    preset_path: Path = DEFAULT_PRESET_PATH,
    dataset_id: str | None = None,
    teacher_policies: tuple[str, ...] = DEFAULT_TEACHER_POLICIES,
    planner_mode: str = "balanced",
    objective_mode: str = "balanced",
    planning_horizon: int = 4,
    rollout_sims_per_offer: int = 12,
    eval_sims_per_offer: int = 8,
    episodes: int = 12,
    max_steps: int = 30,
    offers_per_step: int = 3,
    seed: int = 41,
) -> dict[str, Any]:
    con = sqlite3.connect(str(db_path))
    try:
        create_schema(con)
        resolved_dataset_id = dataset_id or latest_dataset_id(con)
    finally:
        con.close()
    if not resolved_dataset_id:
        raise RuntimeError("No RNG training dataset available for planner. Build one first.")

    model_result = train_rng_value_models(
        db_path=db_path,
        dataset_id=resolved_dataset_id,
        teacher_policies=teacher_policies,
    )
    model_artifact = model_result["model_artifact"]
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

    run_id = f"rng_planner::{profile_id}::{utc_now()}"
    step_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    for episode_index in range(int(episodes)):
        rng = random.Random(seed + episode_index)
        slots = [dict(slot) for slot in ctx.base_slots]
        initial_value = evaluate_slots(slots, ctx, objective_mode)
        current_value = initial_value
        for step_index in range(1, int(max_steps) + 1):
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
                    rng_seed=seed * 100000 + episode_index * 1000 + step_index * 100 + offer_index,
                    eval_sims_per_offer=eval_sims_per_offer,
                )
                offer_summaries.append({"action": action, "summary": summary})
            scored_now = _score_offer_candidates(
                slots=slots,
                offer_summaries=offer_summaries,
                baseline_value_before=current_value,
                step_index=step_index,
                max_steps=max_steps,
                model_artifact=model_artifact,
            )
            planned_rows = []
            for offer_index, item in enumerate(offer_summaries):
                planned_rows.append(
                    _plan_offer(
                        slots=slots,
                        action=item["action"],
                        immediate_scored_row=scored_now.iloc[offer_index].to_dict(),
                        ctx=ctx,
                        action_specs=action_specs,
                        model_artifact=model_artifact,
                        planner_mode=planner_mode,
                        objective_mode=objective_mode,
                        step_index=step_index,
                        max_steps=max_steps,
                        offers_per_step=offers_per_step,
                        eval_sims_per_offer=eval_sims_per_offer,
                        rollout_sims_per_offer=rollout_sims_per_offer,
                        planning_horizon=planning_horizon,
                        rng_seed=seed * 1000000 + episode_index * 10000 + step_index * 100 + offer_index,
                    )
                )
            chosen_plan = sorted(planned_rows, key=lambda item: (item["plan_score"], item["rollout_mean"]), reverse=True)[0]
            chosen = next(item for item in offer_summaries if item["action"]["action_id"] == chosen_plan["action_id"])
            slots = apply_roll_action(
                [dict(slot) for slot in slots],
                RollAction(
                    token_type=str(chosen["action"]["token_type"]),
                    role_scope=str(chosen["action"]["role_scope"]),
                    slot_index=int(chosen["action"]["slot_index"]),
                ),
                distribution_index=ctx.distribution_indices[f"ti2026_generic_{chosen['action']['token_type']}_v1"],
                template_color_map=ctx.template_color_map,
                rng=rng,
            )
            next_value = evaluate_slots(slots, ctx, objective_mode)
            step_rows.append(
                {
                    "run_id": run_id,
                    "episode_index": int(episode_index),
                    "step_index": int(step_index),
                    "baseline_value_before": float(current_value),
                    "chosen_action_id": chosen_plan["action_id"],
                    "chosen_token_type": chosen_plan["token_type"],
                    "chosen_role_scope": chosen_plan["role_scope"],
                    "chosen_slot_index": int(chosen_plan["slot_index"]),
                    "chosen_plan_score": float(chosen_plan["plan_score"]),
                    "chosen_predicted_future_gain": float(chosen_plan["predicted_future_gain"]),
                    "chosen_predicted_choice_prob": float(chosen_plan["predicted_choice_prob"]),
                    "chosen_rollout_mean": float(chosen_plan["rollout_mean"]),
                    "chosen_rollout_p75": float(chosen_plan["rollout_p75"]),
                    "chosen_rollout_p90": float(chosen_plan["rollout_p90"]),
                    "chosen_rollout_max": float(chosen_plan["rollout_max"]),
                    "realized_value_after": float(next_value),
                    "realized_delta": float(next_value - current_value),
                    "offer_set_json": json.dumps(planned_rows, ensure_ascii=False),
                }
            )
            current_value = next_value
        summary_rows.append(
            {
                "run_id": run_id,
                "episode_index": int(episode_index),
                "initial_value": float(initial_value),
                "final_value": float(current_value),
                "total_delta": float(current_value - initial_value),
            }
        )

    step_df = pd.DataFrame(step_rows)
    summary_df = pd.DataFrame(summary_rows)

    con = sqlite3.connect(str(db_path))
    try:
        create_schema(con)
        cur = con.cursor()
        cur.execute("DELETE FROM fantasy_rng_planner_episode_summaries WHERE run_id = ?", (run_id,))
        cur.execute("DELETE FROM fantasy_rng_planner_step_choices WHERE run_id = ?", (run_id,))
        cur.execute("DELETE FROM fantasy_rng_planner_runs WHERE run_id = ?", (run_id,))
        cur.execute(
            """
            INSERT INTO fantasy_rng_planner_runs(
                run_id, profile_id, dataset_id, planner_mode, planning_horizon, rollout_sims_per_offer,
                eval_sims_per_offer, episodes, max_steps, offers_per_step, teacher_policies_json, created_at_utc, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                profile_id,
                resolved_dataset_id,
                planner_mode,
                int(planning_horizon),
                int(rollout_sims_per_offer),
                int(eval_sims_per_offer),
                int(episodes),
                int(max_steps),
                int(offers_per_step),
                json.dumps(list(teacher_policies), ensure_ascii=False),
                utc_now(),
                "Value-model-guided planner with short rollout lookahead and mode-specific utility aggregation.",
            ),
        )
        if not summary_df.empty:
            cur.executemany(
                """
                INSERT OR REPLACE INTO fantasy_rng_planner_episode_summaries(
                    run_id, episode_index, initial_value, final_value, total_delta, created_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        row.run_id,
                        int(row.episode_index),
                        float(row.initial_value),
                        float(row.final_value),
                        float(row.total_delta),
                        utc_now(),
                    )
                    for row in summary_df.itertuples(index=False)
                ],
            )
        if not step_df.empty:
            cur.executemany(
                """
                INSERT OR REPLACE INTO fantasy_rng_planner_step_choices(
                    run_id, episode_index, step_index, baseline_value_before, chosen_action_id, chosen_token_type,
                    chosen_role_scope, chosen_slot_index, chosen_plan_score, chosen_predicted_future_gain,
                    chosen_predicted_choice_prob, chosen_rollout_mean, chosen_rollout_p75, chosen_rollout_p90,
                    chosen_rollout_max, realized_value_after, realized_delta, offer_set_json, created_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        row.run_id,
                        int(row.episode_index),
                        int(row.step_index),
                        float(row.baseline_value_before),
                        row.chosen_action_id,
                        row.chosen_token_type,
                        row.chosen_role_scope,
                        int(row.chosen_slot_index),
                        float(row.chosen_plan_score),
                        float(row.chosen_predicted_future_gain),
                        float(row.chosen_predicted_choice_prob),
                        float(row.chosen_rollout_mean),
                        float(row.chosen_rollout_p75),
                        float(row.chosen_rollout_p90),
                        float(row.chosen_rollout_max),
                        float(row.realized_value_after),
                        float(row.realized_delta),
                        row.offer_set_json,
                        utc_now(),
                    )
                    for row in step_df.itertuples(index=False)
                ],
            )
        con.commit()
    finally:
        con.close()

    return {
        "run_id": run_id,
        "dataset_id": resolved_dataset_id,
        "planner_mode": planner_mode,
        "model_result": model_result,
        "summary_df": summary_df,
        "step_df": step_df,
        "metrics": {
            "episodes": int(len(summary_df)),
            "avg_final_value": float(summary_df["final_value"].mean()) if not summary_df.empty else 0.0,
            "avg_total_delta": float(summary_df["total_delta"].mean()) if not summary_df.empty else 0.0,
            "min_final_value": float(summary_df["final_value"].min()) if not summary_df.empty else 0.0,
            "max_final_value": float(summary_df["final_value"].max()) if not summary_df.empty else 0.0,
        },
    }
