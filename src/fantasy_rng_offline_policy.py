"""Behavior-constrained offline actor update from planner trajectory warehouses."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
from torch.nn import functional as F

from fantasy_rng_features import build_offer_rows_from_state
from fantasy_rng_slot_neural import pack
from fantasy_rng_slot_rl import load_slot_model, save_slot_model


def _warehouse_frame(con: sqlite3.Connection, dataset_id: str) -> tuple[pd.DataFrame, list[list[float]], np.ndarray]:
    rows = con.execute(
        """
        SELECT episode_index, step_index, objective_mode, state_value_before,
               return_to_go, final_value, behavior_action_index, behavior_action_json,
               state_slots_json, offers_json, actor_probs_json
        FROM fantasy_rng_offline_trajectory_steps
        WHERE dataset_id = ? ORDER BY episode_index, step_index
        """,
        (dataset_id,),
    ).fetchall()
    if not rows:
        raise RuntimeError(f"No rows in offline warehouse dataset {dataset_id}")
    output: list[dict[str, Any]] = []
    behavior_probs: list[list[float]] = []
    terminal_values: list[float] = []
    for episode, step, objective, state_value, return_to_go, final_value, chosen_index, chosen_json, slots_json, offers_json, probs_json in rows:
        slots, offers = json.loads(slots_json), json.loads(offers_json)
        chosen = json.loads(chosen_json)
        generated = build_offer_rows_from_state(
            slots, offers, baseline_value_before=float(state_value), step_index=int(step), max_steps=30,
            chosen_action_id=str(chosen.get("action_id", "")), episode_index=int(episode),
        )
        for index, item in enumerate(generated):
            item["q_target"] = 1.0 if index == int(chosen_index) else 0.0
            item["state_objective_safe"] = int(objective == "safe")
            item["state_objective_ceiling"] = int(objective == "ceiling")
            item["offline_return_to_go"] = float(return_to_go)
        output.extend(generated)
        behavior_probs.append([float(value) for value in json.loads(probs_json)])
        # Every decision in an episode has the same realized final banner value.
        # It is an unbiased label for V(s) only under the behaviour/planner policy,
        # which is precisely the conservative policy we distil at this stage.
        terminal_values.append(float(final_value))
    return pd.DataFrame(output), behavior_probs, np.asarray(terminal_values, dtype=np.float32)


def _tensors(data: dict[str, np.ndarray], indices: np.ndarray) -> dict[str, torch.Tensor]:
    return {key: torch.tensor(value[indices]) for key, value in data.items() if key not in {"labels", "q"}}


def train_conservative_offline_actor(
    *,
    db_path: Path,
    dataset_id: str,
    artifact_in: Path,
    artifact_out: Path,
    epochs: int = 8,
    learning_rate: float = 5e-5,
    kl_weight: float = 0.75,
    advantage_temperature: float = 2500.0,
    critic_weight: float = 0.35,
    seed: int = 61001,
    max_train_decisions: int = 0,
) -> dict[str, Any]:
    torch.manual_seed(seed)
    # Large batches are materially faster and more stable than thousands of
    # tiny Transformer passes on a CPU-only overnight environment.
    torch.set_num_threads(1)
    con = sqlite3.connect(str(db_path))
    try:
        frame, behavior_lists, terminal_values = _warehouse_frame(con, dataset_id)
    finally:
        con.close()
    model, artifact = load_slot_model(artifact_in)
    packed = pack(frame, artifact["vocab"])
    episodes = frame.groupby(["episode_index", "step_index"], sort=False)["episode_index"].first().astype(int).to_numpy()
    returns = frame.groupby(["episode_index", "step_index"], sort=False)["offline_return_to_go"].first().astype(float).to_numpy()
    objectives = frame.groupby(["episode_index", "step_index"], sort=False)["state_objective_safe"].first().to_numpy() + 2 * frame.groupby(["episode_index", "step_index"], sort=False)["state_objective_ceiling"].first().to_numpy()
    holdout_episodes = set(sorted(np.unique(episodes))[-max(1, len(np.unique(episodes)) // 4):])
    train_index = np.array([index for index, episode in enumerate(episodes) if episode not in holdout_episodes], dtype=int)
    test_index = np.array([index for index, episode in enumerate(episodes) if episode in holdout_episodes], dtype=int)
    if max_train_decisions > 0 and len(train_index) > max_train_decisions:
        train_index = np.random.default_rng(seed).choice(train_index, size=max_train_decisions, replace=False)
    critic_mean = float(terminal_values[train_index].mean())
    critic_std = float(terminal_values[train_index].std()) or 1.0
    critic_target = ((terminal_values - critic_mean) / critic_std).astype(np.float32)
    max_actions = packed["mask"].shape[1]
    behavior = np.zeros((len(behavior_lists), max_actions), dtype=np.float32)
    for index, values in enumerate(behavior_lists):
        behavior[index, : min(len(values), max_actions)] = values[:max_actions]
    # Per-step/objective return advantage prevents simply copying long-tail runs.
    advantage = np.zeros(len(returns), dtype=np.float32)
    for key in np.unique(np.stack([frame.groupby(["episode_index", "step_index"], sort=False)["step_index"].first().to_numpy(), objectives], axis=1), axis=0):
        selector = (frame.groupby(["episode_index", "step_index"], sort=False)["step_index"].first().to_numpy() == key[0]) & (objectives == key[1])
        scale = max(float(np.std(returns[selector])), 1.0)
        advantage[selector] = np.clip((returns[selector] - float(np.mean(returns[selector]))) / max(scale, advantage_temperature / 10.0), -2.0, 2.0)
    weights = np.exp(advantage / max(advantage_temperature / 1000.0, 1.0)).astype(np.float32)
    weights = np.clip(weights, 0.25, 4.0)

    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-4)
    rng = np.random.default_rng(seed)
    history: list[dict[str, float]] = []
    model.train()
    for epoch in range(epochs):
        shuffled = rng.permutation(train_index)
        losses: list[float] = []
        kls: list[float] = []
        for start in range(0, len(shuffled), 256):
            ids = shuffled[start:start + 256]
            batch = _tensors(packed, ids)
            labels = torch.tensor(packed["labels"][ids], dtype=torch.long)
            mask = batch["mask"]
            behavior_target = torch.tensor(behavior[ids]) * mask.float()
            behavior_target = behavior_target / behavior_target.sum(dim=1, keepdim=True).clamp_min(1e-8)
            logits, q_values, value = model(batch["slots"], batch["slot_mult"], batch["actions"], batch["action_num"], batch["state_num"], mask)
            ce_each = F.cross_entropy(logits, labels, reduction="none")
            ce = (ce_each * torch.tensor(weights[ids])).mean()
            kl = F.kl_div(F.log_softmax(logits, dim=1), behavior_target, reduction="batchmean")
            terminal = torch.tensor(critic_target[ids])
            selected_q = q_values.gather(1, labels.unsqueeze(1)).squeeze(1)
            # Q(s,a) is the operational critic: it retains action-specific
            # information and is used by the planner. V(s) is only a light
            # auxiliary target because the legacy shared state path contains
            # a large raw banner-value feature.
            critic_loss = F.smooth_l1_loss(selected_q, terminal) + 0.10 * F.smooth_l1_loss(value, terminal)
            loss = ce + kl_weight * kl + critic_weight * critic_loss
            optimizer.zero_grad(); loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0); optimizer.step()
            losses.append(float(loss.detach())); kls.append(float(kl.detach()))
        history.append({"epoch": float(epoch + 1), "loss": float(np.mean(losses)), "kl_to_behavior": float(np.mean(kls))})

    model.eval()
    def evaluate(ids: np.ndarray) -> dict[str, float]:
        predictions: list[np.ndarray] = []
        labels: list[np.ndarray] = []
        weighted_kl = 0.0
        for start in range(0, len(ids), 256):
            current = ids[start:start + 256]
            batch = _tensors(packed, current)
            with torch.no_grad():
                logits, _, _ = model(batch["slots"], batch["slot_mult"], batch["actions"], batch["action_num"], batch["state_num"], batch["mask"])
            behavior_target = torch.tensor(behavior[current]) * batch["mask"].float()
            behavior_target = behavior_target / behavior_target.sum(dim=1, keepdim=True).clamp_min(1e-8)
            weighted_kl += float(F.kl_div(F.log_softmax(logits, dim=1), behavior_target, reduction="batchmean")) * len(current)
            predictions.append(logits.argmax(1).numpy())
            labels.append(packed["labels"][current])
        with torch.no_grad():
            batch = _tensors(packed, ids)
            _, q_values, value = model(batch["slots"], batch["slot_mult"], batch["actions"], batch["action_num"], batch["state_num"], batch["mask"])
            labels_tensor = torch.tensor(packed["labels"][ids], dtype=torch.long)
            selected_q = q_values.gather(1, labels_tensor.unsqueeze(1)).squeeze(1).numpy() * critic_std + critic_mean
            value_raw = value.numpy() * critic_std + critic_mean
            target_raw = terminal_values[ids]
        return {
            "planner_behavior_top1": float(np.mean(np.concatenate(predictions) == np.concatenate(labels))),
            "kl_to_behavior": weighted_kl / max(1, len(ids)),
            "decisions": int(len(ids)),
            "terminal_value_mae": float(np.mean(np.abs(value_raw - target_raw))),
            "terminal_q_mae": float(np.mean(np.abs(selected_q - target_raw))),
            "terminal_value_spearman": float(pd.Series(value_raw).rank().corr(pd.Series(target_raw).rank(), method="pearson") or 0.0),
        }
    metrics = {"train": evaluate(train_index), "holdout": evaluate(test_index)}
    output = dict(artifact)
    output["offline_policy_update"] = {
        "parent_artifact": str(artifact_in.resolve()), "dataset_id": dataset_id, "epochs": epochs,
        "learning_rate": learning_rate, "kl_weight": kl_weight, "advantage_temperature": advantage_temperature,
        "max_train_decisions": max_train_decisions, "holdout_episodes": len(holdout_episodes), "metrics": metrics,
        "note": "Experimental behavior-constrained offline actor; requires matched evaluation before promotion.",
    }
    output["terminal_critic"] = {
        "target": "realized_final_banner_value_under_planner_behavior",
        "inference": "actor_probability_weighted_q",
        "normalization_mean": critic_mean,
        "normalization_std": critic_std,
        "critic_weight": critic_weight,
        "note": "Shared encoder V(s) and Q(s,a) heads. The operational bootstrap is actor-probability-weighted Q(s,a); V(s) is auxiliary. Use only as a bounded planner leaf bootstrap until matched evaluation promotes it.",
    }
    save_slot_model(artifact_out, model, output)
    return {"artifact_in": str(artifact_in), "artifact_out": str(artifact_out), "metrics": metrics, "history": history}
