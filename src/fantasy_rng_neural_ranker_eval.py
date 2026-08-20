"""Independent matched evaluation for a counterfactual neural ranker.

The ranker is never promoted from offline top-1 accuracy alone.  It must first
rerank the same four candidates (three tokens plus Refresh) considered by the
Monte-Carlo planner, then be compared through complete 30-roll sessions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

from fantasy_rng_env import RNGEnvironment, RNGOffer
from fantasy_rng_slot_neural import SlotAwareActorCritic, SlotAwareCrossAttentionRanker
from fantasy_rng_slot_planner import choose_planned_action
from fantasy_rng_slot_rl import observation


def load_neural_ranker(path: Path) -> tuple[SlotAwareActorCritic, dict[str, Any]]:
    artifact = torch.load(path, map_location="cpu", weights_only=False)
    model_cls = SlotAwareCrossAttentionRanker if artifact.get("architecture") == "cross_attention_v2" else SlotAwareActorCritic
    model = model_cls(artifact["vocab"])
    model.load_state_dict(artifact["state_dict"])
    model.eval()
    return model, artifact


def _ranker_action(
    model: SlotAwareActorCritic,
    artifact: dict[str, Any],
    env: RNGEnvironment,
    offers: list[RNGOffer],
    candidate_indices: list[int],
) -> tuple[int, list[float]]:
    candidate_offers = [offers[index] for index in candidate_indices]
    with torch.no_grad():
        obs = observation(env, candidate_offers, artifact)
        _, q_values, _ = model(
            obs["slots"], obs["slot_mult"], obs["actions"],
            obs["action_num"], obs["state_num"], obs["mask"],
        )
    local_index = int(q_values.masked_fill(~obs["mask"], -1e9).argmax(1).item())
    return int(candidate_indices[local_index]), q_values.squeeze(0).tolist()


def _offers_for_tokens(env: RNGEnvironment, tokens: list[object]) -> list[RNGOffer]:
    """Expand one external three-token offer schedule for a particular state."""
    actions = [action for token in tokens for action in env.legal_actions_for_token(token.token_id)]
    actions.append(RNGOffer(
        "refresh_offers", "refresh_offers", "refresh_offers", "global", -1,
        "", "", "", 0.0, 1.0, True,
    ))
    return actions


def _bootstrap_ci(values: np.ndarray, *, seed: int, samples: int = 2_000) -> list[float]:
    if len(values) == 0:
        return [0.0, 0.0]
    rng = np.random.default_rng(seed)
    means = np.empty(samples, dtype=float)
    for index in range(samples):
        means[index] = float(rng.choice(values, size=len(values), replace=True).mean())
    return [float(np.quantile(means, .025)), float(np.quantile(means, .975))]


def evaluate_ranker_against_planner(
    *,
    db_path: Path,
    profile_id: str,
    actor_model: SlotAwareActorCritic,
    actor_artifact: dict[str, Any],
    ranker_model: SlotAwareActorCritic,
    ranker_artifact: dict[str, Any],
    token_preset: Path,
    starter_preset: Path,
    episodes: int = 24,
    seed: int = 74001,
    rollouts: int = 4,
    horizon: int = 6,
    preference_weight: float = 0.10,
    strategy_prior_weight: float = 0.0,
) -> dict[str, Any]:
    """Run two policies from matched initial seeds; each uses its own future state."""
    objectives = ("safe", "balanced", "ceiling")
    episode_rows: list[dict[str, Any]] = []
    decision_matches = 0
    decision_count = 0
    for episode_index in range(episodes):
        episode_seed = seed + episode_index
        common = dict(
            profile_id=profile_id, db_path=db_path, preset_path=token_preset,
            initial_state_preset_path=starter_preset,
            objective_mode=objectives[episode_index % len(objectives)], max_steps=30,
        )
        planner_env = RNGEnvironment(**common, seed=episode_seed)
        ranker_env = RNGEnvironment(**common, seed=episode_seed)
        # Offers are external to player actions in the actual client.  Sharing
        # this schedule removes avoidable variance from the matched comparison.
        offer_schedule = RNGEnvironment(**common, seed=episode_seed + 5_000_000)
        planner_env.reset(seed=episode_seed)
        ranker_env.reset(seed=episode_seed)
        offer_schedule.reset(seed=episode_seed + 5_000_000)
        while not planner_env.done() and not ranker_env.done():
            token_offers = offer_schedule.sample_token_offers()
            planner_offers = _offers_for_tokens(planner_env, token_offers)
            ranker_offers = _offers_for_tokens(ranker_env, token_offers)
            planner_choice = choose_planned_action(
                actor_model, actor_artifact, planner_env, planner_offers,
                top_k=3, rollouts=rollouts,
                horizon=min(horizon, planner_env.steps_remaining()),
                risk_mode=planner_env.objective_mode,
                seed=episode_seed * 100 + planner_env.steps_remaining(),
                include_refresh_candidate=True,
                preference_weight=preference_weight,
                strategy_prior_weight=strategy_prior_weight,
            )
            planner_indices = [int(row["action_index"]) for row in planner_choice["candidates"]]
            ranked_choice, _ = _ranker_action(
                ranker_model, ranker_artifact, planner_env, planner_offers, planner_indices
            )
            decision_count += 1
            decision_matches += int(ranked_choice == int(planner_choice["chosen_action_index"]))
            ranker_teacher_choice = choose_planned_action(
                actor_model, actor_artifact, ranker_env, ranker_offers,
                top_k=3, rollouts=rollouts,
                horizon=min(horizon, ranker_env.steps_remaining()),
                risk_mode=ranker_env.objective_mode,
                seed=episode_seed * 1_000 + ranker_env.steps_remaining(),
                include_refresh_candidate=True,
                preference_weight=preference_weight,
                strategy_prior_weight=strategy_prior_weight,
            )
            indices = [int(row["action_index"]) for row in ranker_teacher_choice["candidates"]]
            chosen, _ = _ranker_action(ranker_model, ranker_artifact, ranker_env, ranker_offers, indices)
            planner_env.step_action(planner_offers[int(planner_choice["chosen_action_index"])])
            ranker_env.step_action(ranker_offers[chosen])

        planner_final = float(planner_env.current_value())
        ranker_final = float(ranker_env.current_value())
        episode_rows.append({
            "episode_index": episode_index,
            "seed": episode_seed,
            "objective_mode": planner_env.objective_mode,
            "planner_final": planner_final,
            "ranker_final": ranker_final,
            "ranker_minus_planner": ranker_final - planner_final,
        })
    frame = pd.DataFrame(episode_rows)
    deltas = frame["ranker_minus_planner"].to_numpy(dtype=float)
    return {
        "episodes": episodes,
        "preference_weight": float(preference_weight),
        "strategy_prior_weight": float(strategy_prior_weight),
        "shared_offer_schedule": True,
        "decision_agreement_on_planner_states": float(decision_matches / max(1, decision_count)),
        "planner_mean_final": float(frame["planner_final"].mean()),
        "ranker_mean_final": float(frame["ranker_final"].mean()),
        "ranker_minus_planner_mean": float(deltas.mean()),
        "ranker_minus_planner_ci95": _bootstrap_ci(deltas, seed=seed + 17),
        "episodes_by_objective": frame.groupby("objective_mode")["ranker_minus_planner"].agg(["count", "mean"]).round(3).reset_index().to_dict(orient="records"),
        "promotion_rule": "Do not promote if the CI materially favors planner; rerun with >=100 matched episodes before any promotion decision.",
        "episode_rows": episode_rows,
    }
