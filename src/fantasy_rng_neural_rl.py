from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from fantasy_rng_env import RNGEnvironment
from fantasy_rng_features import build_offer_rows_from_state
from fantasy_rng_neural import NeuralActorCritic, _feature_matrix


def load_model(artifact_path: Path) -> tuple[NeuralActorCritic, dict[str, Any]]:
    artifact = torch.load(artifact_path, map_location="cpu", weights_only=False)
    model = NeuralActorCritic(len(artifact["schema"]["x_mean"]), hidden_dim=int(artifact["hidden_dim"]))
    model.load_state_dict(artifact["state_dict"])
    return model, artifact


def save_model(path: Path, model: NeuralActorCritic, artifact: dict[str, Any]) -> None:
    payload = dict(artifact)
    payload["state_dict"] = {key: value.detach().cpu() for key, value in model.state_dict().items()}
    torch.save(payload, path)


def _offer_payload(offers: list[object]) -> list[dict[str, object]]:
    return [{"action_id": item.action_id, "token_id": item.token_id, "token_type": item.token_type, "role_scope": item.role_scope, "slot_index": item.slot_index, "current_stat_name": item.current_stat_name, "current_quality_tier": item.current_quality_tier, "current_trait_name": item.current_trait_name, "current_multiplier": item.current_multiplier, "is_refresh_action": int(item.is_refresh_action), "action_scope": item.action_scope, "target_color_group": item.target_color_group} for item in offers]


def _objective_features(rows: list[dict[str, object]], objective_mode: str) -> None:
    for row in rows:
        row["state_objective_safe"] = int(objective_mode == "safe")
        row["state_objective_balanced"] = int(objective_mode == "balanced")
        row["state_objective_ceiling"] = int(objective_mode == "ceiling")


def _observation(env: RNGEnvironment, offers: list[object], schema: dict[str, Any]) -> torch.Tensor:
    rows = build_offer_rows_from_state(env.state_slots(), _offer_payload(offers), baseline_value_before=env.current_value(), step_index=env.max_steps - env.steps_remaining() + 1, max_steps=env.max_steps)
    _objective_features(rows, env.objective_mode)
    return torch.tensor(_feature_matrix(__import__("pandas").DataFrame(rows), schema)).unsqueeze(0)


def ppo_train(
    *,
    model: NeuralActorCritic,
    artifact: dict[str, Any],
    profile_id: str,
    db_path: Path,
    updates: int = 4,
    episodes_per_update: int = 8,
    max_steps: int = 30,
    learning_rate: float = 3e-4,
    ppo_epochs: int = 4,
    clip_epsilon: float = 0.15,
    entropy_coef: float = 0.01,
    value_coef: float = 0.5,
    gamma: float = 0.99,
    gae_lambda: float = 0.95,
    seed: int = 811,
    token_preset: Path | None = None,
    initial_state_preset: Path | None = None,
    sampled_start_probability: float = 1.0,
    on_update: Callable[[int, NeuralActorCritic, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    rng = np.random.default_rng(seed)
    history = []
    objectives = ["safe", "balanced", "ceiling"]
    if not 0.0 <= sampled_start_probability <= 1.0:
        raise ValueError("sampled_start_probability must be between 0 and 1")
    for update in range(updates):
        trajectories = []
        for episode in range(episodes_per_update):
            objective = objectives[(update * episodes_per_update + episode) % len(objectives)]
            use_sampled_start = initial_state_preset is not None and rng.random() < sampled_start_probability
            env = RNGEnvironment(profile_id=profile_id, db_path=db_path, preset_path=token_preset or RNGEnvironment.__init__.__kwdefaults__["preset_path"], initial_state_preset_path=initial_state_preset if use_sampled_start else None, objective_mode=objective, max_steps=max_steps, seed=seed + update * 10_000 + episode)
            env.reset(seed=seed + update * 10_000 + episode)
            episode_steps = []
            while not env.done():
                offers = env.sample_decision_offers(); x = _observation(env, offers, artifact["schema"]); mask = torch.ones((1, x.shape[1]), dtype=torch.bool)
                with torch.no_grad():
                    logits, _, value = model(x, mask); dist = torch.distributions.Categorical(logits=logits); action = dist.sample()
                result = env.step(int(action.item()))
                episode_steps.append({"x": x.squeeze(0), "mask": mask.squeeze(0), "action": int(action.item()), "logprob": float(dist.log_prob(action).item()), "value": float(value.item()), "reward": float(result.delta_value)})
            next_advantage = 0.0; next_value = 0.0
            for step in reversed(episode_steps):
                delta = step["reward"] + gamma * next_value - step["value"]
                next_advantage = delta + gamma * gae_lambda * next_advantage
                step["advantage"] = next_advantage; step["return"] = next_advantage + step["value"]; next_value = step["value"]
            trajectories.extend(episode_steps)
        advantages = np.asarray([step["advantage"] for step in trajectories], dtype=np.float32)
        advantages = (advantages - advantages.mean()) / max(1e-6, advantages.std())
        for step, advantage in zip(trajectories, advantages): step["advantage"] = float(advantage)
        x = torch.stack([step["x"] for step in trajectories]); mask = torch.stack([step["mask"] for step in trajectories]); actions = torch.tensor([step["action"] for step in trajectories]); old_logprobs = torch.tensor([step["logprob"] for step in trajectories]); returns = torch.tensor([step["return"] for step in trajectories]); advantages_t = torch.tensor([step["advantage"] for step in trajectories])
        kl_values = []; entropy_values = []
        for _ in range(ppo_epochs):
            logits, _, values = model(x, mask); dist = torch.distributions.Categorical(logits=logits); logprobs = dist.log_prob(actions); ratio = torch.exp(logprobs - old_logprobs); clipped = torch.clamp(ratio, 1 - clip_epsilon, 1 + clip_epsilon)
            policy_loss = -torch.minimum(ratio * advantages_t, clipped * advantages_t).mean(); value_loss = F.mse_loss(values, returns); entropy = dist.entropy().mean(); loss = policy_loss + value_coef * value_loss - entropy_coef * entropy
            optimizer.zero_grad(); loss.backward(); nn.utils.clip_grad_norm_(model.parameters(), 1.0); optimizer.step()
            kl_values.append(float((old_logprobs - logprobs).mean().item())); entropy_values.append(float(entropy.item()))
        update_metrics = {"update": update + 1, "episodes": episodes_per_update, "mean_step_reward": float(np.mean([step["reward"] for step in trajectories])), "mean_return": float(np.mean([step["return"] for step in trajectories])), "mean_kl": float(np.mean(kl_values)), "entropy": float(np.mean(entropy_values))}
        history.append(update_metrics)
        if on_update is not None:
            on_update(update + 1, model, update_metrics)
    return {"history": history, "sampled_start_probability": sampled_start_probability}


def simulate_neural_scenario(
    *,
    model: NeuralActorCritic,
    artifact: dict[str, Any],
    profile_id: str,
    db_path: Path,
    scenario: dict[str, Any],
    seeds: list[int],
    episodes_per_seed: int,
    max_steps: int,
) -> "__import__('pandas').DataFrame":
    import pandas as pd
    rows = []
    root = Path(__file__).resolve().parents[1]
    token_path = Path(scenario.get("token_preset_path", ""))
    if not token_path.is_absolute(): token_path = root / token_path
    starter_value = scenario.get("initial_state_preset_path")
    starter_path = (root / starter_value) if starter_value else None
    for seed in seeds:
        for episode in range(episodes_per_seed):
            episode_seed = int(seed) * 10_000 + episode
            env = RNGEnvironment(profile_id=profile_id, db_path=db_path, preset_path=token_path, initial_state_preset_path=starter_path, objective_mode=str(scenario["objective_mode"]), max_steps=max_steps, seed=episode_seed)
            env.reset(seed=episode_seed); initial = float(env.current_value())
            while not env.done():
                offers = env.sample_decision_offers(); x = _observation(env, offers, artifact["schema"]); mask = torch.ones((1, x.shape[1]), dtype=torch.bool)
                with torch.no_grad(): logits, _, _ = model(x, mask)
                env.step(int(logits.argmax(dim=1).item()))
            final = float(env.current_value())
            rows.append({"scenario_id": scenario["scenario_id"], "objective_mode": scenario["objective_mode"], "seed": seed, "episode_index": episode, "initial_value": initial, "final_value": final, "total_delta": final - initial})
    return pd.DataFrame(rows)
