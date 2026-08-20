"""Nonlinear slot-aware ranker for planner counterfactual action values."""

from __future__ import annotations

import json
import math
import sqlite3
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
from torch.nn import functional as F

from fantasy_rng_offline_counterfactual import _load_frame
from fantasy_rng_slot_neural import SlotAwareCrossAttentionRanker, SlotAwareActorCritic, fit_vocab, pack


def _batch(data: dict[str, np.ndarray], ids: np.ndarray) -> dict[str, torch.Tensor]:
    return {key: torch.tensor(value[ids]) for key, value in data.items()}


def train_neural_counterfactual_ranker(
    *,
    db_path: Path,
    dataset_id: str,
    artifact_out: Path,
    epochs: int = 18,
    learning_rate: float = 2e-4,
    seed: int = 73001,
    architecture: str = "cross_attention_v2",
    target_temperature: float = 0.35,
    batch_size: int = 32,
    early_stopping_patience: int = 12,
    min_epochs: int = 20,
    lr_patience: int = 5,
    lr_factor: float = 0.5,
) -> dict[str, Any]:
    torch.manual_seed(seed)
    torch.set_num_threads(1)
    con = sqlite3.connect(str(db_path))
    try:
        frame = _load_frame(con, dataset_id)
    finally:
        con.close()
    if frame.empty:
        raise RuntimeError(f"No counterfactual rows for {dataset_id}")
    episodes = sorted(frame.episode_index.astype(int).unique())
    holdout = set(episodes[-max(1, math.ceil(len(episodes) * .25)):])
    train_frame, test_frame = frame[~frame.episode_index.isin(holdout)].copy(), frame[frame.episode_index.isin(holdout)].copy()
    vocab = fit_vocab(train_frame)
    train, test = pack(train_frame, vocab), pack(test_frame, vocab)
    if architecture == "cross_attention_v2":
        model = SlotAwareCrossAttentionRanker(vocab)
    elif architecture == "pooled_v1":
        model = SlotAwareActorCritic(vocab)
    else:
        raise ValueError(f"Unsupported architecture={architecture!r}")
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="max", factor=lr_factor, patience=lr_patience,
        threshold=1e-4, min_lr=learning_rate * 0.0625,
    )
    q_mean = float(train["q"][train["mask"]].mean()); q_std = float(train["q"][train["mask"]].std()) or 1.0
    ids = np.arange(len(train["labels"])); rng = np.random.default_rng(seed); history: list[dict[str, float]] = []
    def evaluate(data: dict[str, np.ndarray]) -> dict[str, float]:
        model.eval()
        actor_hits: list[np.ndarray] = []; q_hits: list[np.ndarray] = []
        q_true: list[np.ndarray] = []; q_pred: list[np.ndarray] = []
        for start in range(0, len(data["labels"]), 256):
            index = np.arange(start, min(start + 256, len(data["labels"]))); b = _batch(data, index)
            with torch.no_grad(): logits, q_values, _ = model(b["slots"], b["slot_mult"], b["actions"], b["action_num"], b["state_num"], b["mask"])
            q_hits.append((q_values.masked_fill(~b["mask"], -1e9).argmax(1).numpy() == b["labels"].numpy()))
            actor_hits.append((logits.argmax(1).numpy() == b["labels"].numpy()))
            q_true.append(b["q"][b["mask"]].numpy()); q_pred.append(q_values[b["mask"]].numpy() * q_std + q_mean)
        true, pred = np.concatenate(q_true), np.concatenate(q_pred)
        return {"actor_top1": float(np.mean(np.concatenate(actor_hits))), "q_top1": float(np.mean(np.concatenate(q_hits))), "q_mae": float(np.mean(np.abs(true - pred))), "q_spearman": float(pd.Series(true).rank().corr(pd.Series(pred).rank(), method="pearson") or 0.0), "decisions": int(len(data["labels"]))}

    best_state: dict[str, torch.Tensor] | None = None
    best_epoch = 0
    best_score = float("-inf")
    stale_epochs = 0
    model.train()
    for epoch in range(epochs):
        rng.shuffle(ids); losses: list[float] = []
        for start in range(0, len(ids), batch_size):
            index = ids[start:start + batch_size]; b = _batch(train, index)
            logits, q_values, _ = model(b["slots"], b["slot_mult"], b["actions"], b["action_num"], b["state_num"], b["mask"])
            q_target = (b["q"] - q_mean) / q_std
            # Planner utilities are Monte-Carlo estimates, so retain ranking
            # information among all four choices instead of treating one noisy
            # argmax as an absolute label.
            valid_q = b["q"].masked_fill(~b["mask"], 0.0)
            valid_count = b["mask"].sum(dim=1, keepdim=True).clamp_min(1)
            row_mean = valid_q.sum(dim=1, keepdim=True) / valid_count
            row_var = (((valid_q - row_mean) ** 2) * b["mask"]).sum(dim=1, keepdim=True) / valid_count
            target_logits = (b["q"] - row_mean) / torch.sqrt(row_var + 1e-6)
            target_logits = target_logits / max(float(target_temperature), 1e-6)
            target_logits = target_logits.masked_fill(~b["mask"], -1e9)
            soft_target = torch.softmax(target_logits, dim=1)
            listwise = F.kl_div(torch.log_softmax(logits, dim=1), soft_target, reduction="batchmean")
            ce = F.cross_entropy(logits, b["labels"])
            q_loss = F.mse_loss(q_values[b["mask"]], q_target[b["mask"]])
            loss = .35 * ce + .65 * listwise + .5 * q_loss
            optimizer.zero_grad(); loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0); optimizer.step()
            losses.append(float(loss.detach()))
        holdout_metrics = evaluate(test)
        # The UI ranker chooses from the Q head, so Q top-1 is the primary
        # early-stopping signal. Spearman only resolves close ties.
        holdout_score = float(holdout_metrics["q_top1"] + .01 * holdout_metrics["q_spearman"])
        scheduler.step(holdout_score)
        current_lr = float(optimizer.param_groups[0]["lr"])
        history.append({"epoch": float(epoch + 1), "loss": float(np.mean(losses)), "holdout_q_top1": float(holdout_metrics["q_top1"]), "holdout_q_spearman": float(holdout_metrics["q_spearman"]), "learning_rate": current_lr})
        if holdout_score > best_score + 1e-6:
            best_score = holdout_score
            best_epoch = epoch + 1
            best_state = deepcopy(model.state_dict())
            stale_epochs = 0
        else:
            stale_epochs += 1
        print(
            f"[ranker] epoch {epoch + 1}/{epochs}: loss={history[-1]['loss']:.5f} q_top1={holdout_metrics['q_top1']:.4f} lr={current_lr:.2e}",
            flush=True,
        )
        if epoch + 1 >= min_epochs and stale_epochs >= early_stopping_patience:
            print(f"[ranker] early stop at epoch {epoch + 1}; best epoch={best_epoch}", flush=True)
            break
        model.train()
    if best_state is not None:
        model.load_state_dict(best_state)
    metrics = {"train": evaluate(train), "holdout": evaluate(test), "holdout_episodes": len(holdout)}
    payload = {"artifact_type": f"rng_offline_counterfactual_slot_ranker_{architecture}", "dataset_id": dataset_id, "vocab": vocab, "state_dict": {key: value.detach().cpu() for key, value in model.state_dict().items()}, "q_mean": q_mean, "q_std": q_std, "epochs_requested": epochs, "best_epoch": best_epoch, "best_holdout_score": best_score, "learning_rate": learning_rate, "architecture": architecture, "target_temperature": target_temperature, "early_stopping_patience": early_stopping_patience, "metrics": metrics, "note": "Experimental counterfactual ranker; requires comparison with Monte-Carlo planner."}
    torch.save(payload, artifact_out)
    return {"artifact_out": str(artifact_out), "metrics": metrics, "history": history}
