from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

import pandas as pd

from fantasy_rng_env import RNGEnvironment, RNGOffer
from fantasy_rng_features import build_offer_rows_from_state


@dataclass
class TeacherDecision:
    chosen_offer_index: int
    scored_offers: pd.DataFrame


def _offer_frame(
    env: RNGEnvironment,
    offers: list[RNGOffer],
    *,
    value_before: float,
) -> pd.DataFrame:
    offer_rows = [
        {
            "action_id": offer.action_id,
            "token_id": offer.token_id,
            "token_type": offer.token_type,
            "role_scope": offer.role_scope,
            "slot_index": offer.slot_index,
            "current_stat_name": offer.current_stat_name,
            "current_quality_tier": offer.current_quality_tier,
            "current_trait_name": offer.current_trait_name,
            "current_multiplier": offer.current_multiplier,
            "is_refresh_action": 1 if offer.is_refresh_action else 0,
            "action_scope": offer.action_scope,
            "target_color_group": offer.target_color_group,
            "expected_delta": 0.0,
            "p75_delta": 0.0,
            "p90_delta": 0.0,
        }
        for offer in offers
    ]
    rows = build_offer_rows_from_state(
        env.state_slots(),
        offer_rows,
        baseline_value_before=value_before,
        step_index=env.max_steps - env.steps_remaining() + 1,
        max_steps=env.max_steps,
    )
    return pd.DataFrame(rows)


def rollout_offer_value(
    env: RNGEnvironment,
    *,
    offer_index: int,
    rollout_count: int = 8,
    horizon: int | None = None,
    objective: str = "mean",
    seed_offset: int = 0,
    continuation_policy: str = "lookahead1",
) -> dict[str, float]:
    scores: list[float] = []
    horizon_steps = env.steps_remaining() if horizon is None else min(int(horizon), env.steps_remaining())
    for sim_idx in range(max(1, int(rollout_count))):
        clone = env.clone(seed=env.seed + seed_offset + sim_idx + offer_index * 1000)
        clone.step(offer_index)
        while not clone.done() and (clone.max_steps - clone.steps_remaining()) < env.max_steps - env.steps_remaining() + horizon_steps:
            offers = clone.sample_offers()
            if not offers:
                break
            local_best_idx = 0
            if continuation_policy == "sample":
                local_best_idx = clone.rng.randrange(len(offers))
            elif continuation_policy == "greedy_delta":
                local_best_score = float("-inf")
                for idx in range(len(offers)):
                    probe = clone.clone(seed=clone.seed + 50000 + idx)
                    value_before = probe.current_value()
                    result = probe.step(idx)
                    probe_score = float(result.delta_value + 0.15 * value_before / max(1, probe.max_steps))
                    if probe_score > local_best_score:
                        local_best_score = probe_score
                        local_best_idx = idx
            else:
                # One-step lookahead using cheap clones of the already initialized environment.
                local_best_score = float("-inf")
                for idx in range(len(offers)):
                    probe = clone.clone(seed=clone.seed + 50000 + idx)
                    probe.step(idx)
                    probe_score = probe.current_value()
                    if probe_score > local_best_score:
                        local_best_score = probe_score
                        local_best_idx = idx
            clone.step(local_best_idx)
        scores.append(float(clone.current_value()))
    ordered = sorted(scores)
    mean_score = float(sum(ordered) / len(ordered))
    p75_score = float(ordered[int((len(ordered) - 1) * 0.75)])
    p90_score = float(ordered[int((len(ordered) - 1) * 0.90)])
    max_score = float(max(ordered))
    if objective == "p75":
        utility = p75_score
    elif objective == "p90":
        utility = p90_score
    elif objective == "max":
        utility = max_score
    else:
        utility = mean_score
    return {
        "utility": utility,
        "rollout_mean": mean_score,
        "rollout_p75": p75_score,
        "rollout_p90": p90_score,
        "rollout_max": max_score,
    }


def choose_teacher_offer(
    env: RNGEnvironment,
    offers: list[RNGOffer],
    *,
    rollout_count: int = 8,
    horizon: int | None = None,
    objective: str = "mean",
    seed_offset: int = 0,
    continuation_policy: str = "lookahead1",
) -> TeacherDecision:
    value_before = env.current_value()
    scored = _offer_frame(env, offers, value_before=value_before)
    utilities: list[dict[str, float]] = []
    for idx in range(len(offers)):
        rollout_stats = rollout_offer_value(
            env,
            offer_index=idx,
            rollout_count=rollout_count,
            horizon=horizon,
            objective=objective,
            seed_offset=seed_offset,
            continuation_policy=continuation_policy,
        )
        utilities.append(rollout_stats)
    util_df = pd.DataFrame(utilities)
    scored = pd.concat([scored.reset_index(drop=True), util_df.reset_index(drop=True)], axis=1)
    scored["teacher_rank"] = scored["utility"].rank(method="first", ascending=False).astype(int)
    ordered_utilities = sorted([float(value) for value in scored["utility"].tolist()], reverse=True)
    best_utility = ordered_utilities[0] if ordered_utilities else 0.0
    second_utility = ordered_utilities[1] if len(ordered_utilities) > 1 else best_utility
    margin = float(best_utility - second_utility)
    confidence = float(margin / max(1.0, abs(best_utility)))
    scored["teacher_margin"] = margin
    scored["teacher_confidence"] = confidence
    chosen_idx = int(scored["utility"].astype(float).idxmax())
    return TeacherDecision(chosen_offer_index=chosen_idx, scored_offers=scored)
