from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import torch

from fantasy_rng_env import RNGEnvironment, RNGOffer
from fantasy_rng_slot_neural import SlotAwareActorCritic
from fantasy_rng_slot_rl import observation
from fantasy_rng_strategy_prior import strategy_action_breakdown


def _terminal_critic_value(model: SlotAwareActorCritic, artifact: dict[str, Any], env: RNGEnvironment, offers: list[RNGOffer]) -> float | None:
    """Return raw V(s) only for a checkpoint trained with terminal labels."""
    spec = artifact.get("terminal_critic")
    if not isinstance(spec, dict):
        return None
    mean = spec.get("normalization_mean")
    std = spec.get("normalization_std")
    if mean is None or std is None:
        return None
    with torch.no_grad():
        obs = observation(env, offers, artifact)
        logits, q_values, _ = model(obs["slots"], obs["slot_mult"], obs["actions"], obs["action_num"], obs["state_num"], obs["mask"])
        # Do not greedily maximize an extrapolated Q for an unseen action. The
        # actor-weighted expectation is conservative and remains close to the
        # planner behaviour that generated the terminal labels.
        probs = torch.softmax(logits, dim=1)
        value = (probs * q_values).sum(dim=1)
    return float(value.item()) * float(std) + float(mean)


def choose_planned_action(model: SlotAwareActorCritic, artifact: dict[str, Any], env: RNGEnvironment, offers: list[RNGOffer], *, top_k: int = 3, rollouts: int = 8, horizon: int = 8, risk_mode: str = "mean", seed: int = 1, include_refresh_candidate: bool = True, preference_weight: float = 0.0, strategy_prior_weight: float = 0.0, critic_leaf_weight: float = 0.0) -> dict[str, Any]:
    """Actor proposes actions; common-horizon rollouts rerank only its best candidates."""
    with torch.no_grad():
        obs = observation(env, offers, artifact)
        logits, _, _ = model(obs["slots"], obs["slot_mult"], obs["actions"], obs["action_num"], obs["state_num"], obs["mask"])
    ranking = torch.argsort(logits.squeeze(0), descending=True).tolist()
    candidates = ranking[:min(top_k, len(offers))]
    # Refresh is a genuine fourth player decision, not merely a UI escape hatch.
    # In counterfactual warehouse mode it is evaluated even if the actor did not
    # place it in its top-k token proposals.
    if include_refresh_candidate:
        refresh_index = next((index for index, offer in enumerate(offers) if offer.is_refresh_action), None)
        if refresh_index is not None:
            # The game first offers exactly three token IDs; only after choosing
            # one does the player choose its role target.  Keep the actor's best
            # legal role for *each offered token*, then add Refresh.  Selecting
            # the global top three role-actions could otherwise include two
            # targets for one token and silently remove another player choice.
            seen_tokens: set[str] = set()
            candidates = []
            token_indices: dict[str, list[int]] = {}
            for index in ranking:
                if index != refresh_index:
                    token_indices.setdefault(str(offers[index].token_id), []).append(index)
            for token_id, indices in token_indices.items():
                if token_id in seen_tokens:
                    continue
                # A token is offered first and the player then targets a role.
                # When a strategy prior is active, use it to select the most
                # meaningful legal role for that token instead of blindly
                # inheriting the base actor's arbitrary role preference.
                plan_rows = [(index, strategy_action_breakdown(env.state_slots(), offers[index])) for index in indices]
                max_bonus = max(float(plan["bonus"]) for _, plan in plan_rows)
                if strategy_prior_weight > 0.0 and max_bonus != 0.0:
                    chosen_index = max(plan_rows, key=lambda item: (float(item[1]["bonus"]), float(logits.squeeze(0)[item[0]])))[0]
                else:
                    chosen_index = indices[0]
                seen_tokens.add(token_id)
                candidates.append(chosen_index)
                if len(candidates) >= top_k:
                    break
            candidates.append(refresh_index)
    summaries = []
    for action_index in candidates:
        outcomes = []
        for rollout_index in range(rollouts):
            sim = env.clone(seed=seed + action_index * 10_000 + rollout_index)
            sim._last_offers = [RNGOffer(**item.__dict__) for item in offers]
            sim.step(action_index)
            remaining = min(horizon - 1, sim.steps_remaining())
            for _ in range(max(0, remaining)):
                future = sim.sample_decision_offers()
                with torch.no_grad():
                    future_obs = observation(sim, future, artifact)
                    future_logits, _, _ = model(future_obs["slots"], future_obs["slot_mult"], future_obs["actions"], future_obs["action_num"], future_obs["state_num"], future_obs["mask"])
                sim.step(int(future_logits.argmax(1).item()))
            rollout_value = float(sim.current_guided_value(preference_weight))
            # A critic only bootstraps the tail of a short rollout. Keeping the
            # blend bounded makes the exact environment rollout authoritative.
            if critic_leaf_weight > 0.0 and sim.steps_remaining() > 0:
                leaf_offers = sim.sample_decision_offers()
                leaf_value = _terminal_critic_value(model, artifact, sim, leaf_offers)
                if leaf_value is not None:
                    rollout_value = (1.0 - critic_leaf_weight) * rollout_value + critic_leaf_weight * leaf_value
            outcomes.append(rollout_value)
        values = np.asarray(outcomes, dtype=float)
        official_utility = float(np.quantile(values, .25) if risk_mode == "safe" else np.quantile(values, .90) if risk_mode == "ceiling" else values.mean())
        plan = strategy_action_breakdown(env.state_slots(), offers[action_index])
        utility = official_utility + float(strategy_prior_weight) * float(plan["bonus"])
        summaries.append({"action_index": int(action_index), "token_id": offers[action_index].token_id, "role_scope": offers[action_index].role_scope, "utility": utility, "official_utility": official_utility, "mean": float(values.mean()), "p25": float(np.quantile(values,.25)), "p90": float(np.quantile(values,.90)), "preference_weight": float(preference_weight), "strategy_prior_weight": float(strategy_prior_weight), "strategy_prior_bonus": float(plan["bonus"]), "strategy_prior_reasons": plan["reasons"]})
    best = max(summaries, key=lambda row: row["utility"])
    return {"chosen_action_index": int(best["action_index"]), "candidates": summaries}


def simulate_planned_slot_model(model: SlotAwareActorCritic, artifact: dict[str, Any], *, profile_id: str, db_path: str | Any, scenario: dict[str, Any], seeds: list[int], episodes_per_seed: int, top_k: int = 3, rollouts: int = 4, horizon: int = 6) -> pd.DataFrame:
    """Evaluate actor-plus-planner on matched seeds without changing the learned policy."""
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    rows = []
    for seed in seeds:
        for episode in range(episodes_per_seed):
            episode_seed = seed * 10_000 + episode
            env = RNGEnvironment(profile_id=profile_id, db_path=db_path, preset_path=root / scenario["token_preset_path"], initial_state_preset_path=root / scenario["initial_state_preset_path"], objective_mode=scenario["objective_mode"], max_steps=30, seed=episode_seed)
            env.reset(seed=episode_seed)
            initial = env.current_value()
            while not env.done():
                offers = env.sample_decision_offers()
                decision = choose_planned_action(model, artifact, env, offers, top_k=top_k, rollouts=rollouts, horizon=min(horizon, env.steps_remaining()), risk_mode=env.objective_mode, seed=episode_seed * 100 + env.steps_remaining())
                env.step(int(decision["chosen_action_index"]))
            rows.append({"scenario_id": scenario["scenario_id"], "objective_mode": scenario["objective_mode"], "seed": seed, "episode_index": episode, "initial_value": initial, "final_value": env.current_value()})
    return pd.DataFrame(rows)
