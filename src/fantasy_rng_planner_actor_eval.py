"""Shared-offer matched evaluation for two actor-assisted planners."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from fantasy_rng_env import RNGEnvironment, RNGOffer
from fantasy_rng_slot_planner import choose_planned_action


def _offers_for_tokens(env: RNGEnvironment, tokens: list[object]) -> list[RNGOffer]:
    actions = [action for token in tokens for action in env.legal_actions_for_token(token.token_id)]
    actions.append(RNGOffer("refresh_offers", "refresh_offers", "refresh_offers", "global", -1, "", "", "", 0.0, 1.0, True))
    return actions


def _ci(values: np.ndarray, seed: int, samples: int = 2_000) -> list[float]:
    rng = np.random.default_rng(seed)
    means = [float(rng.choice(values, size=len(values), replace=True).mean()) for _ in range(samples)]
    return [float(np.quantile(means, .025)), float(np.quantile(means, .975))]


def evaluate_planner_actors(
    *, db_path: Path, profile_id: str, base_model: Any, base_artifact: dict[str, Any],
    candidate_model: Any, candidate_artifact: dict[str, Any], token_preset: Path,
    starter_preset: Path, episodes: int = 24, seed: int = 120001,
    rollouts: int = 4, horizon: int = 6, preference_weight: float = .10,
    strategy_prior_weight: float = 1.0, base_critic_leaf_weight: float = 0.0,
    candidate_critic_leaf_weight: float = 0.0,
) -> dict[str, Any]:
    objectives = ("safe", "balanced", "ceiling")
    rows: list[dict[str, Any]] = []
    for index in range(episodes):
        episode_seed = seed + index
        common = dict(profile_id=profile_id, db_path=db_path, preset_path=token_preset, initial_state_preset_path=starter_preset, objective_mode=objectives[index % 3], max_steps=30)
        base_env = RNGEnvironment(**common, seed=episode_seed)
        candidate_env = RNGEnvironment(**common, seed=episode_seed)
        schedule = RNGEnvironment(**common, seed=episode_seed + 5_000_000)
        base_env.reset(seed=episode_seed); candidate_env.reset(seed=episode_seed); schedule.reset(seed=episode_seed + 5_000_000)
        while not base_env.done():
            tokens = schedule.sample_token_offers()
            base_offers, candidate_offers = _offers_for_tokens(base_env, tokens), _offers_for_tokens(candidate_env, tokens)
            base_choice = choose_planned_action(base_model, base_artifact, base_env, base_offers, top_k=3, rollouts=rollouts, horizon=min(horizon, base_env.steps_remaining()), risk_mode=base_env.objective_mode, seed=episode_seed * 100 + base_env.steps_remaining(), include_refresh_candidate=True, preference_weight=preference_weight, strategy_prior_weight=strategy_prior_weight, critic_leaf_weight=base_critic_leaf_weight)
            candidate_choice = choose_planned_action(candidate_model, candidate_artifact, candidate_env, candidate_offers, top_k=3, rollouts=rollouts, horizon=min(horizon, candidate_env.steps_remaining()), risk_mode=candidate_env.objective_mode, seed=episode_seed * 100 + candidate_env.steps_remaining(), include_refresh_candidate=True, preference_weight=preference_weight, strategy_prior_weight=strategy_prior_weight, critic_leaf_weight=candidate_critic_leaf_weight)
            base_env.step_action(base_offers[int(base_choice["chosen_action_index"])])
            candidate_env.step_action(candidate_offers[int(candidate_choice["chosen_action_index"])])
        base_final, candidate_final = base_env.current_value(), candidate_env.current_value()
        rows.append({"episode_index": index, "seed": episode_seed, "objective_mode": base_env.objective_mode, "base_final": base_final, "candidate_final": candidate_final, "candidate_minus_base": candidate_final - base_final})
    frame = pd.DataFrame(rows)
    deltas = frame["candidate_minus_base"].to_numpy(dtype=float)
    return {
        "episodes": episodes, "shared_offer_schedule": True,
        "base_critic_leaf_weight": base_critic_leaf_weight,
        "candidate_critic_leaf_weight": candidate_critic_leaf_weight,
        "base_mean_final": float(frame.base_final.mean()), "candidate_mean_final": float(frame.candidate_final.mean()),
        "candidate_minus_base_mean": float(deltas.mean()), "candidate_minus_base_ci95": _ci(deltas, seed + 17),
        "by_objective": frame.groupby("objective_mode").candidate_minus_base.agg(["count", "mean"]).round(3).reset_index().to_dict(orient="records"),
        "episode_rows": rows,
    }


def evaluate_safe_router(
    *, db_path: Path, profile_id: str, base_model: Any, base_artifact: dict[str, Any],
    safe_model: Any, safe_artifact: dict[str, Any], token_preset: Path,
    starter_preset: Path, episodes: int = 24, seed: int = 140001,
    rollouts: int = 4, horizon: int = 6, preference_weight: float = .10,
    strategy_prior_weight: float = 1.0, safe_critic_leaf_weight: float = .30,
) -> dict[str, Any]:
    """Evaluate a conservative router against the immutable base planner.

    The candidate model is deliberately used only for `safe`; balanced and
    ceiling receive the exact baseline decision path. This makes the test a
    direct check of the one observed positive signal, without accidentally
    claiming a whole-policy replacement.
    """
    objectives = ("safe", "balanced", "ceiling")
    rows: list[dict[str, Any]] = []
    for index in range(episodes):
        episode_seed = seed + index
        objective = objectives[index % len(objectives)]
        common = dict(profile_id=profile_id, db_path=db_path, preset_path=token_preset, initial_state_preset_path=starter_preset, objective_mode=objective, max_steps=30)
        base_env = RNGEnvironment(**common, seed=episode_seed)
        router_env = RNGEnvironment(**common, seed=episode_seed)
        schedule = RNGEnvironment(**common, seed=episode_seed + 5_000_000)
        base_env.reset(seed=episode_seed); router_env.reset(seed=episode_seed); schedule.reset(seed=episode_seed + 5_000_000)
        routed = objective == "safe"
        model = safe_model if routed else base_model
        artifact = safe_artifact if routed else base_artifact
        critic_weight = safe_critic_leaf_weight if routed else 0.0
        while not base_env.done():
            tokens = schedule.sample_token_offers()
            base_offers = _offers_for_tokens(base_env, tokens)
            router_offers = _offers_for_tokens(router_env, tokens)
            base_choice = choose_planned_action(base_model, base_artifact, base_env, base_offers, top_k=3, rollouts=rollouts, horizon=min(horizon, base_env.steps_remaining()), risk_mode=objective, seed=episode_seed * 100 + base_env.steps_remaining(), include_refresh_candidate=True, preference_weight=preference_weight, strategy_prior_weight=strategy_prior_weight)
            routed_choice = choose_planned_action(model, artifact, router_env, router_offers, top_k=3, rollouts=rollouts, horizon=min(horizon, router_env.steps_remaining()), risk_mode=objective, seed=episode_seed * 100 + router_env.steps_remaining(), include_refresh_candidate=True, preference_weight=preference_weight, strategy_prior_weight=strategy_prior_weight, critic_leaf_weight=critic_weight)
            base_env.step_action(base_offers[int(base_choice["chosen_action_index"])])
            router_env.step_action(router_offers[int(routed_choice["chosen_action_index"])])
        delta = router_env.current_value() - base_env.current_value()
        rows.append({"episode_index": index, "seed": episode_seed, "objective_mode": objective, "router_component": "stage2_actor_critic" if routed else "baseline", "base_final": base_env.current_value(), "router_final": router_env.current_value(), "router_minus_base": delta})
    frame = pd.DataFrame(rows)
    deltas = frame["router_minus_base"].to_numpy(dtype=float)
    safe_deltas = frame.loc[frame.objective_mode == "safe", "router_minus_base"].to_numpy(dtype=float)
    return {
        "episodes": episodes,
        "shared_offer_schedule": True,
        "router": {"safe": "stage2_actor_critic", "balanced": "baseline", "ceiling": "baseline", "safe_critic_leaf_weight": safe_critic_leaf_weight},
        "base_mean_final": float(frame.base_final.mean()),
        "router_mean_final": float(frame.router_final.mean()),
        "router_minus_base_mean": float(deltas.mean()),
        "router_minus_base_ci95": _ci(deltas, seed + 17),
        "safe_router_minus_base_mean": float(safe_deltas.mean()),
        "safe_router_minus_base_ci95": _ci(safe_deltas, seed + 31),
        "by_objective": frame.groupby("objective_mode").router_minus_base.agg(["count", "mean"]).round(3).reset_index().to_dict(orient="records"),
        "episode_rows": rows,
    }
