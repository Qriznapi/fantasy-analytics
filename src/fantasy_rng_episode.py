from __future__ import annotations

import json
import math
import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from fantasy_rng_foundation import (
    BENCHMARK_DB_PATH,
    DEFAULT_PRESET_PATH,
    TARGET_DB_PATH,
    enumerate_candidate_actions,
    load_token_preset,
    rank_scale_1_100,
    safe_float,
)
from fantasy_roll_objective import compute_banner_intrinsic_value, load_role_stat_benchmarks, load_rule_maps
from fantasy_roll_simulator import (
    RollAction,
    apply_roll_action,
    build_distribution_index,
    load_banner_slots,
    load_profile_meta,
    load_roll_distributions,
    load_template_color_map,
    seed_default_roll_distributions,
)


DEFAULT_POLICIES = (
    "random",
    "greedy_expected",
    "greedy_p75",
    "scheduled_balanced",
    "scheduled_aggressive",
    "scheduled_conservative",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class EpisodeContext:
    profile_id: str
    event_id: str
    benchmark_event_id: str
    base_slots: list[dict[str, Any]]
    template_color_map: dict[tuple[str, int], str]
    benchmark_df: pd.DataFrame
    quality_map: dict[str, dict[str, Any]]
    trait_map: dict[str, dict[str, Any]]
    distribution_indices: dict[str, dict[tuple[str, str], list[dict[str, Any]]]]
    preset: dict[str, Any]


def create_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS fantasy_rng_episode_runs (
            run_id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            event_id TEXT NOT NULL,
            benchmark_event_id TEXT NOT NULL,
            preset_id TEXT NOT NULL,
            preset_path TEXT NOT NULL,
            objective_mode TEXT NOT NULL,
            policies_json TEXT NOT NULL,
            episodes_per_policy INTEGER NOT NULL,
            max_steps INTEGER NOT NULL,
            offers_per_step INTEGER NOT NULL,
            eval_sims_per_offer INTEGER NOT NULL,
            created_at_utc TEXT NOT NULL,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS fantasy_rng_episode_steps (
            run_id TEXT NOT NULL,
            policy_name TEXT NOT NULL,
            episode_index INTEGER NOT NULL,
            step_index INTEGER NOT NULL,
            steps_remaining_before INTEGER NOT NULL,
            baseline_value_before REAL NOT NULL,
            slot_state_before_json TEXT NOT NULL DEFAULT '[]',
            offer_set_json TEXT NOT NULL,
            chosen_offer_index INTEGER NOT NULL,
            chosen_action_id TEXT NOT NULL,
            chosen_token_type TEXT NOT NULL,
            chosen_role_scope TEXT NOT NULL,
            chosen_slot_index INTEGER NOT NULL,
            chosen_policy_score REAL NOT NULL,
            chosen_expected_delta REAL NOT NULL,
            chosen_p75_delta REAL NOT NULL,
            chosen_p90_delta REAL NOT NULL,
            realized_value_after REAL NOT NULL,
            realized_delta REAL NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, policy_name, episode_index, step_index)
        );

        CREATE TABLE IF NOT EXISTS fantasy_rng_episode_summaries (
            run_id TEXT NOT NULL,
            policy_name TEXT NOT NULL,
            episode_index INTEGER NOT NULL,
            steps_played INTEGER NOT NULL,
            initial_value REAL NOT NULL,
            final_value REAL NOT NULL,
            total_delta REAL NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, policy_name, episode_index)
        );
        """
    )
    columns = {str(row[1]) for row in con.execute("PRAGMA table_info(fantasy_rng_episode_steps)").fetchall()}
    if "slot_state_before_json" not in columns:
        con.execute(
            "ALTER TABLE fantasy_rng_episode_steps ADD COLUMN slot_state_before_json TEXT NOT NULL DEFAULT '[]'"
        )
    rebuild_views(con)


def rebuild_views(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        DROP VIEW IF EXISTS analytics_rng_episode_runs;
        CREATE VIEW analytics_rng_episode_runs AS
        SELECT * FROM fantasy_rng_episode_runs;

        DROP VIEW IF EXISTS analytics_rng_episode_summaries;
        CREATE VIEW analytics_rng_episode_summaries AS
        SELECT s.*
        FROM fantasy_rng_episode_summaries s
        JOIN (
            SELECT profile_id, MAX(created_at_utc) AS created_at_utc
            FROM fantasy_rng_episode_runs
            GROUP BY profile_id
        ) latest
          ON 1=1
        JOIN fantasy_rng_episode_runs r
          ON r.run_id = s.run_id
         AND r.profile_id = latest.profile_id
         AND r.created_at_utc = latest.created_at_utc;

        DROP VIEW IF EXISTS analytics_rng_episode_policy_summary;
        CREATE VIEW analytics_rng_episode_policy_summary AS
        SELECT
            run_id,
            policy_name,
            COUNT(*) AS episodes,
            AVG(final_value) AS avg_final_value,
            AVG(total_delta) AS avg_total_delta,
            MIN(final_value) AS min_final_value,
            MAX(final_value) AS max_final_value
        FROM analytics_rng_episode_summaries
        GROUP BY run_id, policy_name;
        """
    )


def _policy_rule_id(token_type: str) -> str:
    return f"ti2026_generic_{token_type}_v1"


def build_episode_context(
    *,
    profile_id: str,
    db_path: Path = TARGET_DB_PATH,
    benchmark_db_path: Path = BENCHMARK_DB_PATH,
    benchmark_event_id: str = "ewc2026",
    preset_path: Path = DEFAULT_PRESET_PATH,
) -> EpisodeContext:
    target_con = sqlite3.connect(str(db_path))
    benchmark_con = sqlite3.connect(str(benchmark_db_path))
    try:
        seed_default_roll_distributions(target_con)
        meta = load_profile_meta(target_con, profile_id)
        base_slots = load_banner_slots(target_con, profile_id)
        template_color_map = load_template_color_map(target_con, meta["template_id"])
        benchmark_df = load_role_stat_benchmarks(benchmark_con)
        quality_map, trait_map = load_rule_maps(target_con)
        distribution_indices: dict[str, dict[tuple[str, str], list[dict[str, Any]]]] = {}
        for token_type in ["reroll_stat", "reroll_quality", "reroll_trait", "reroll_emblem"]:
            rule_id = _policy_rule_id(token_type)
            distribution_indices[rule_id] = build_distribution_index(load_roll_distributions(target_con, rule_id))
        preset = load_token_preset(preset_path)
        return EpisodeContext(
            profile_id=profile_id,
            event_id=meta["event_id"],
            benchmark_event_id=benchmark_event_id,
            base_slots=[dict(slot) for slot in base_slots],
            template_color_map=template_color_map,
            benchmark_df=benchmark_df,
            quality_map=quality_map,
            trait_map=trait_map,
            distribution_indices=distribution_indices,
            preset=preset,
        )
    finally:
        benchmark_con.close()
        target_con.close()


def evaluate_slots(slots: list[dict[str, Any]], ctx: EpisodeContext, objective_mode: str) -> float:
    result = compute_banner_intrinsic_value(
        slots,
        ctx.benchmark_df,
        ctx.quality_map,
        ctx.trait_map,
        objective_mode=objective_mode,
    )
    return safe_float(result["intrinsic_value_raw"])


def _sample_offers(rng: random.Random, action_specs: list[dict[str, Any]], offers_per_step: int) -> list[dict[str, Any]]:
    if not action_specs:
        return []
    pool = [dict(item) for item in action_specs]
    selected: list[dict[str, Any]] = []
    target = min(int(offers_per_step), len(pool))
    while pool and len(selected) < target:
        total_weight = sum(max(safe_float(item.get("offer_weight", 1.0), 1.0), 0.0) for item in pool)
        if total_weight <= 0:
            selected.append(pool.pop(0))
            continue
        threshold = rng.random() * total_weight
        running = 0.0
        chosen_index = len(pool) - 1
        for idx, item in enumerate(pool):
            running += max(safe_float(item.get("offer_weight", 1.0), 1.0), 0.0)
            if running >= threshold:
                chosen_index = idx
                break
        selected.append(pool.pop(chosen_index))
    return selected


def _summarize_action_from_state(
    *,
    slots: list[dict[str, Any]],
    action_spec: dict[str, Any],
    ctx: EpisodeContext,
    objective_mode: str,
    rng_seed: int,
    eval_sims_per_offer: int,
) -> dict[str, Any]:
    baseline_value = evaluate_slots(slots, ctx, objective_mode)
    outcomes: list[float] = []
    for sim_idx in range(max(1, int(eval_sims_per_offer))):
        sim_rng = random.Random(rng_seed + sim_idx)
        next_slots = apply_roll_action(
            [dict(slot) for slot in slots],
            RollAction(
                token_type=str(action_spec["token_type"]),
                role_scope=str(action_spec["role_scope"]),
                slot_index=int(action_spec["slot_index"]),
            ),
            distribution_index=ctx.distribution_indices[_policy_rule_id(str(action_spec["token_type"]))],
            template_color_map=ctx.template_color_map,
            rng=sim_rng,
        )
        outcomes.append(evaluate_slots(next_slots, ctx, objective_mode))
    outcomes = sorted(outcomes)
    expected = sum(outcomes) / len(outcomes)
    median = outcomes[(len(outcomes) - 1) // 2]
    p75 = outcomes[int((len(outcomes) - 1) * 0.75)]
    p90 = outcomes[int((len(outcomes) - 1) * 0.90)]
    return {
        "baseline_value_before": round(baseline_value, 4),
        "expected_value_after": round(expected, 4),
        "median_value_after": round(median, 4),
        "p75_value_after": round(p75, 4),
        "p90_value_after": round(p90, 4),
        "expected_delta": round(expected - baseline_value, 4),
        "median_delta": round(median - baseline_value, 4),
        "p75_delta": round(p75 - baseline_value, 4),
        "p90_delta": round(p90 - baseline_value, 4),
        "positive_rate": round(sum(1 for value in outcomes if value > baseline_value) / len(outcomes), 6),
        "outcomes": [round(float(value), 4) for value in outcomes],
    }


def _policy_score(
    policy_name: str,
    summary: dict[str, Any],
    *,
    step_index: int,
    max_steps: int,
) -> float:
    phase = (max_steps - step_index) / max(1, max_steps - 1)
    expected_delta = safe_float(summary["expected_delta"])
    p75_delta = safe_float(summary["p75_delta"])
    p90_delta = safe_float(summary["p90_delta"])
    positive_rate = safe_float(summary["positive_rate"])

    if policy_name == "random":
        return 0.0
    if policy_name == "greedy_expected":
        return expected_delta
    if policy_name == "greedy_p75":
        return p75_delta
    if policy_name == "scheduled_aggressive":
        return (0.25 + 0.30 * phase) * expected_delta + (0.15 + 0.45 * phase) * p90_delta + 0.10 * positive_rate
    if policy_name == "scheduled_conservative":
        return (0.45 + 0.20 * (1.0 - phase)) * p75_delta + (0.25 - 0.10 * phase) * p90_delta + 0.20 * expected_delta + 0.10 * positive_rate
    return (0.35 + 0.10 * (1.0 - phase)) * expected_delta + 0.35 * p75_delta + (0.10 + 0.20 * phase) * p90_delta + 0.10 * positive_rate


def _choose_offer(
    policy_name: str,
    offer_summaries: list[dict[str, Any]],
    *,
    step_index: int,
    max_steps: int,
    rng: random.Random,
) -> int:
    if not offer_summaries:
        return -1
    if policy_name == "random":
        return rng.randrange(len(offer_summaries))
    scored = []
    for idx, item in enumerate(offer_summaries):
        score = _policy_score(policy_name, item["summary"], step_index=step_index, max_steps=max_steps)
        scored.append((score, idx))
        item["policy_score"] = round(float(score), 4)
    scored.sort(key=lambda pair: (pair[0], pair[1]), reverse=True)
    return scored[0][1]


def _offer_payload(offer_summaries: list[dict[str, Any]]) -> str:
    payload = []
    for item in offer_summaries:
        payload.append(
            {
                "action_id": item["action"]["action_id"],
                "token_type": item["action"]["token_type"],
                "role_scope": item["action"]["role_scope"],
                "slot_index": int(item["action"]["slot_index"]),
                "current_stat_name": item["action"]["current_stat_name"],
                "current_quality_tier": item["action"]["current_quality_tier"],
                "current_trait_name": item["action"]["current_trait_name"],
                "expected_delta": item["summary"]["expected_delta"],
                "p75_delta": item["summary"]["p75_delta"],
                "p90_delta": item["summary"]["p90_delta"],
            }
        )
    return json.dumps(payload, ensure_ascii=False)


def _slot_state_payload(slots: list[dict[str, Any]]) -> str:
    payload = []
    for slot in sorted([dict(item) for item in slots], key=lambda item: (str(item.get("role_scope", "")), int(item.get("slot_index", 0)))):
        payload.append(
            {
                "role_scope": str(slot.get("role_scope", "")),
                "slot_index": int(slot.get("slot_index", 0)),
                "stat_name": str(slot.get("stat_name", "")),
                "quality_tier": str(slot.get("quality_tier", "")),
                "trait_name": str(slot.get("trait_name", "")),
                "color_group": str(slot.get("color_group", "")),
                "multiplier": round(safe_float(slot.get("multiplier", 0.0)), 4),
            }
        )
    return json.dumps(payload, ensure_ascii=False)


def simulate_policy_episodes(
    *,
    profile_id: str,
    db_path: Path = TARGET_DB_PATH,
    benchmark_db_path: Path = BENCHMARK_DB_PATH,
    benchmark_event_id: str = "ewc2026",
    preset_path: Path = DEFAULT_PRESET_PATH,
    objective_mode: str = "balanced",
    policies: tuple[str, ...] = DEFAULT_POLICIES,
    episodes_per_policy: int = 20,
    max_steps: int = 30,
    offers_per_step: int = 3,
    eval_sims_per_offer: int = 12,
    seed: int = 17,
) -> dict[str, Any]:
    ctx = build_episode_context(
        profile_id=profile_id,
        db_path=db_path,
        benchmark_db_path=benchmark_db_path,
        benchmark_event_id=benchmark_event_id,
        preset_path=preset_path,
    )
    bootstrap_con = sqlite3.connect(str(db_path))
    try:
        create_schema(bootstrap_con)
        action_specs = enumerate_candidate_actions(bootstrap_con, profile_id, ctx.preset)
    finally:
        bootstrap_con.close()

    step_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    run_id = f"rng_episode::{profile_id}::{utc_now()}"
    for policy_index, policy_name in enumerate(policies):
        for episode_index in range(int(episodes_per_policy)):
            rng = random.Random(seed + 1000 * policy_index + episode_index)
            slots = [dict(slot) for slot in ctx.base_slots]
            initial_value = evaluate_slots(slots, ctx, objective_mode)
            current_value = initial_value
            for step_index in range(1, int(max_steps) + 1):
                offers = _sample_offers(rng, action_specs, offers_per_step)
                offer_summaries: list[dict[str, Any]] = []
                for offer_idx, offer in enumerate(offers):
                    summary = _summarize_action_from_state(
                        slots=slots,
                        action_spec=offer,
                        ctx=ctx,
                        objective_mode=objective_mode,
                        rng_seed=seed + 100000 * policy_index + 1000 * episode_index + 100 * step_index + offer_idx,
                        eval_sims_per_offer=eval_sims_per_offer,
                    )
                    offer_summaries.append({"action": offer, "summary": summary, "policy_score": 0.0})
                chosen_offer_index = _choose_offer(
                    policy_name,
                    offer_summaries,
                    step_index=step_index,
                    max_steps=max_steps,
                    rng=rng,
                )
                if chosen_offer_index < 0:
                    break
                chosen = offer_summaries[chosen_offer_index]
                slots = apply_roll_action(
                    [dict(slot) for slot in slots],
                    RollAction(
                        token_type=str(chosen["action"]["token_type"]),
                        role_scope=str(chosen["action"]["role_scope"]),
                        slot_index=int(chosen["action"]["slot_index"]),
                    ),
                    distribution_index=ctx.distribution_indices[_policy_rule_id(str(chosen["action"]["token_type"]))],
                    template_color_map=ctx.template_color_map,
                    rng=rng,
                )
                next_value = evaluate_slots(slots, ctx, objective_mode)
                step_rows.append(
                    {
                        "run_id": run_id,
                        "policy_name": policy_name,
                        "episode_index": int(episode_index),
                        "step_index": int(step_index),
                        "steps_remaining_before": int(max_steps - step_index + 1),
                        "baseline_value_before": round(current_value, 4),
                        "slot_state_before_json": _slot_state_payload(slots),
                        "offer_set_json": _offer_payload(offer_summaries),
                        "chosen_offer_index": int(chosen_offer_index),
                        "chosen_action_id": chosen["action"]["action_id"],
                        "chosen_token_type": chosen["action"]["token_type"],
                        "chosen_role_scope": chosen["action"]["role_scope"],
                        "chosen_slot_index": int(chosen["action"]["slot_index"]),
                        "chosen_policy_score": round(float(chosen.get("policy_score", 0.0)), 4),
                        "chosen_expected_delta": round(float(chosen["summary"]["expected_delta"]), 4),
                        "chosen_p75_delta": round(float(chosen["summary"]["p75_delta"]), 4),
                        "chosen_p90_delta": round(float(chosen["summary"]["p90_delta"]), 4),
                        "realized_value_after": round(next_value, 4),
                        "realized_delta": round(next_value - current_value, 4),
                    }
                )
                current_value = next_value
            summary_rows.append(
                {
                    "run_id": run_id,
                    "policy_name": policy_name,
                    "episode_index": int(episode_index),
                    "steps_played": int(max_steps),
                    "initial_value": round(initial_value, 4),
                    "final_value": round(current_value, 4),
                    "total_delta": round(current_value - initial_value, 4),
                }
            )

    step_df = pd.DataFrame(step_rows)
    summary_df = pd.DataFrame(summary_rows)
    if not summary_df.empty:
        policy_rank = (
            summary_df.groupby("policy_name", as_index=False)
            .agg(avg_final_value=("final_value", "mean"), avg_total_delta=("total_delta", "mean"))
            .sort_values(["avg_final_value", "avg_total_delta"], ascending=False)
            .reset_index(drop=True)
        )
        policy_rank["policy_score_1_100"] = rank_scale_1_100(policy_rank["avg_final_value"]).round(2)
    else:
        policy_rank = pd.DataFrame()

    con = sqlite3.connect(str(db_path))
    try:
        create_schema(con)
        cur = con.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO fantasy_rng_episode_runs(
                run_id, profile_id, event_id, benchmark_event_id, preset_id, preset_path, objective_mode,
                policies_json, episodes_per_policy, max_steps, offers_per_step, eval_sims_per_offer,
                created_at_utc, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                profile_id,
                ctx.event_id,
                benchmark_event_id,
                str(ctx.preset.get("preset_id", preset_path.stem)),
                str(preset_path),
                objective_mode,
                json.dumps(list(policies), ensure_ascii=False),
                int(episodes_per_policy),
                int(max_steps),
                int(offers_per_step),
                int(eval_sims_per_offer),
                utc_now(),
                "30-step RNG environment with three offers per step and baseline horizon-aware policies.",
            ),
        )
        cur.execute("DELETE FROM fantasy_rng_episode_steps WHERE run_id = ?", (run_id,))
        cur.execute("DELETE FROM fantasy_rng_episode_summaries WHERE run_id = ?", (run_id,))
        if not step_df.empty:
            cur.executemany(
                """
                INSERT OR REPLACE INTO fantasy_rng_episode_steps(
                    run_id, policy_name, episode_index, step_index, steps_remaining_before, baseline_value_before,
                    slot_state_before_json, offer_set_json, chosen_offer_index, chosen_action_id, chosen_token_type, chosen_role_scope,
                    chosen_slot_index, chosen_policy_score, chosen_expected_delta, chosen_p75_delta,
                    chosen_p90_delta, realized_value_after, realized_delta, created_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        row.run_id,
                        row.policy_name,
                        int(row.episode_index),
                        int(row.step_index),
                        int(row.steps_remaining_before),
                        float(row.baseline_value_before),
                        row.slot_state_before_json,
                        row.offer_set_json,
                        int(row.chosen_offer_index),
                        row.chosen_action_id,
                        row.chosen_token_type,
                        row.chosen_role_scope,
                        int(row.chosen_slot_index),
                        float(row.chosen_policy_score),
                        float(row.chosen_expected_delta),
                        float(row.chosen_p75_delta),
                        float(row.chosen_p90_delta),
                        float(row.realized_value_after),
                        float(row.realized_delta),
                        utc_now(),
                    )
                    for row in step_df.itertuples(index=False)
                ],
            )
        if not summary_df.empty:
            cur.executemany(
                """
                INSERT OR REPLACE INTO fantasy_rng_episode_summaries(
                    run_id, policy_name, episode_index, steps_played, initial_value, final_value, total_delta, created_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        row.run_id,
                        row.policy_name,
                        int(row.episode_index),
                        int(row.steps_played),
                        float(row.initial_value),
                        float(row.final_value),
                        float(row.total_delta),
                        utc_now(),
                    )
                    for row in summary_df.itertuples(index=False)
                ],
            )
        con.commit()
        rebuild_views(con)
    finally:
        con.close()

    return {
        "run_id": run_id,
        "profile_id": profile_id,
        "event_id": ctx.event_id,
        "benchmark_event_id": benchmark_event_id,
        "step_df": step_df,
        "summary_df": summary_df,
        "policy_rank_df": policy_rank,
    }
