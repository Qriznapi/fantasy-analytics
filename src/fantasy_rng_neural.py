from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.nn import functional as F

from fantasy_rng_policy_models import _feature_spec, _fit_categories, _matrix
from fantasy_rng_q_critic import _load_frame


class NeuralActorCritic(nn.Module):
    """Shared action encoder with policy, action-value, and state-value heads."""

    def __init__(self, input_dim: int, hidden_dim: int = 128) -> None:
        super().__init__()
        self.encoder = nn.Sequential(nn.Linear(input_dim, hidden_dim), nn.ReLU(), nn.Linear(hidden_dim, hidden_dim), nn.ReLU())
        self.actor_head = nn.Linear(hidden_dim, 1)
        self.q_head = nn.Linear(hidden_dim, 1)
        self.value_head = nn.Sequential(nn.Linear(hidden_dim, hidden_dim), nn.ReLU(), nn.Linear(hidden_dim, 1))

    def forward(self, features: torch.Tensor, mask: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        encoded = self.encoder(features)
        logits = self.actor_head(encoded).squeeze(-1).masked_fill(~mask, -1e9)
        q_values = self.q_head(encoded).squeeze(-1)
        denom = mask.sum(dim=1, keepdim=True).clamp(min=1)
        state_embedding = (encoded * mask.unsqueeze(-1)).sum(dim=1) / denom
        values = self.value_head(state_embedding).squeeze(-1)
        return logits, q_values, values


@dataclass
class NeuralDataset:
    features: np.ndarray
    mask: np.ndarray
    best_action: np.ndarray
    q_targets: np.ndarray
    episode_ids: np.ndarray


def fit_feature_schema(frame: pd.DataFrame) -> dict[str, Any]:
    numeric, categorical = _feature_spec(frame)
    categories = _fit_categories(frame, categorical)
    matrix = _matrix(frame, numeric_cols=numeric, categorical_cols=categorical, categories=categories)
    mean, std = matrix.mean(axis=0), matrix.std(axis=0)
    std[std < 1e-9] = 1.0
    return {"numeric_cols": numeric, "categorical_cols": categorical, "categories": categories, "x_mean": mean.tolist(), "x_std": std.tolist()}


def _feature_matrix(frame: pd.DataFrame, schema: dict[str, Any]) -> np.ndarray:
    raw = _matrix(frame, numeric_cols=list(schema["numeric_cols"]), categorical_cols=list(schema["categorical_cols"]), categories=dict(schema["categories"]))
    return ((raw - np.asarray(schema["x_mean"], dtype=float)) / np.asarray(schema["x_std"], dtype=float)).astype(np.float32)


def pack_offer_sets(frame: pd.DataFrame, schema: dict[str, Any]) -> NeuralDataset:
    matrix = _feature_matrix(frame, schema)
    work = frame.reset_index(drop=True).copy()
    groups = list(work.groupby(["episode_index", "step_index"], sort=False).groups.values())
    max_actions = max(len(indices) for indices in groups)
    features = np.zeros((len(groups), max_actions, matrix.shape[1]), dtype=np.float32)
    mask = np.zeros((len(groups), max_actions), dtype=bool)
    q_targets = np.zeros((len(groups), max_actions), dtype=np.float32)
    best_action = np.zeros(len(groups), dtype=np.int64)
    episode_ids = np.zeros(len(groups), dtype=np.int64)
    for group_index, indices in enumerate(groups):
        indices = list(indices)
        count = len(indices)
        features[group_index, :count] = matrix[indices]
        mask[group_index, :count] = True
        values = pd.to_numeric(work.loc[indices, "q_target"], errors="coerce").fillna(0.0).to_numpy(dtype=np.float32)
        q_targets[group_index, :count] = values
        best_action[group_index] = int(np.argmax(values))
        episode_ids[group_index] = int(work.loc[indices[0], "episode_index"])
    return NeuralDataset(features, mask, best_action, q_targets, episode_ids)


def train_bootstrap(
    db_path: Path,
    *,
    counterfactual_dataset_id: str,
    epochs: int = 20,
    batch_size: int = 128,
    learning_rate: float = 3e-4,
    hidden_dim: int = 128,
    seed: int = 17,
) -> dict[str, Any]:
    torch.manual_seed(seed)
    con = sqlite3.connect(str(db_path))
    try:
        frame = _load_frame(con, counterfactual_dataset_id)
    finally:
        con.close()
    if frame.empty:
        raise RuntimeError(f"No counterfactual offers for {counterfactual_dataset_id}")
    episodes = sorted(frame["episode_index"].astype(int).unique())
    holdout = set(episodes[-max(1, int(np.ceil(len(episodes) * .25))):])
    train_frame = frame[~frame["episode_index"].isin(holdout)].copy()
    test_frame = frame[frame["episode_index"].isin(holdout)].copy()
    schema = fit_feature_schema(train_frame)
    train = pack_offer_sets(train_frame, schema)
    test = pack_offer_sets(test_frame, schema)
    q_mean, q_std = float(train.q_targets[train.mask].mean()), float(train.q_targets[train.mask].std())
    q_std = q_std if q_std > 1e-9 else 1.0
    model = NeuralActorCritic(train.features.shape[-1], hidden_dim=hidden_dim)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-4)
    rng = np.random.default_rng(seed)
    for _ in range(epochs):
        for batch in np.array_split(rng.permutation(len(train.features)), max(1, int(np.ceil(len(train.features) / batch_size)))):
            x = torch.tensor(train.features[batch]); mask = torch.tensor(train.mask[batch]); labels = torch.tensor(train.best_action[batch])
            q_target = torch.tensor((train.q_targets[batch] - q_mean) / q_std)
            logits, q_values, values = model(x, mask)
            policy_loss = F.cross_entropy(logits, labels)
            q_loss = F.mse_loss(q_values[mask], q_target[mask])
            value_target = q_target.masked_fill(~mask, -1e9).max(dim=1).values
            value_loss = F.mse_loss(values, value_target)
            loss = policy_loss + 0.5 * q_loss + 0.25 * value_loss
            optimizer.zero_grad(); loss.backward(); nn.utils.clip_grad_norm_(model.parameters(), 1.0); optimizer.step()
    model.eval()
    with torch.no_grad():
        x = torch.tensor(test.features); mask = torch.tensor(test.mask); logits, q_values, _ = model(x, mask)
        actor_top1 = float((logits.argmax(dim=1).cpu().numpy() == test.best_action).mean())
        q_top1 = float((q_values.masked_fill(~mask, -1e9).argmax(dim=1).cpu().numpy() == test.best_action).mean())
        q_pred = q_values.cpu().numpy()[test.mask] * q_std + q_mean
        q_true = test.q_targets[test.mask]
        q_mae = float(np.abs(q_pred - q_true).mean())
    artifact = {"schema": schema, "hidden_dim": hidden_dim, "q_mean": q_mean, "q_std": q_std, "state_dict": {key: value.detach().cpu() for key, value in model.state_dict().items()}}
    return {"artifact": artifact, "metrics": {"actor_top1": actor_top1, "q_top1": q_top1, "q_mae": q_mae, "test_decisions": int(len(test.features))}, "train_decisions": int(len(train.features)), "test_decisions": int(len(test.features))}


def save_artifact(path: Path, artifact: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(artifact, path)
