from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.nn import functional as F

from fantasy_rng_q_critic import _load_frame

SLOT_FIELDS = ("role_scope", "slot_index", "color_group", "stat_name", "quality_tier", "trait_name")
ACTION_FIELDS = ("offer_token_id", "offer_role_scope", "offer_action_scope", "offer_target_color_group", "offer_slot_index")


def _vocab(values: list[str]) -> dict[str, int]:
    return {value: index + 1 for index, value in enumerate(sorted(set(values)))}


def fit_vocab(frame: pd.DataFrame) -> dict[str, dict[str, int]]:
    slot_values: dict[str, list[str]] = {field: [] for field in SLOT_FIELDS}
    for payload in frame["state_slot_state_json"].fillna("[]"):
        for slot in json.loads(str(payload)):
            for field in SLOT_FIELDS:
                slot_values[field].append(str(slot.get(field, "")))
    return {"slot": {field: _vocab(values) for field, values in slot_values.items()}, "action": {field: _vocab(frame.get(field, pd.Series(dtype=str)).fillna("").astype(str).tolist()) for field in ACTION_FIELDS}}


def _ids(values: list[str], vocab: dict[str, int]) -> list[int]:
    return [vocab.get(value, 0) for value in values]


def pack(frame: pd.DataFrame, vocab: dict[str, Any]) -> dict[str, np.ndarray]:
    groups = list(frame.groupby(["episode_index", "step_index"], sort=False).groups.values())
    max_actions = max(len(group) for group in groups)
    n = len(groups)
    slots = np.zeros((n, 15, len(SLOT_FIELDS)), dtype=np.int64)
    slot_mult = np.zeros((n, 15, 1), dtype=np.float32)
    actions = np.zeros((n, max_actions, len(ACTION_FIELDS)), dtype=np.int64)
    action_num = np.zeros((n, max_actions, 4), dtype=np.float32)
    mask = np.zeros((n, max_actions), dtype=bool); labels = np.zeros(n, dtype=np.int64); q = np.zeros((n, max_actions), dtype=np.float32)
    state_num = np.zeros((n, 5), dtype=np.float32)
    for gi, indices in enumerate(groups):
        rows = frame.loc[list(indices)].reset_index(drop=True); slot_rows = sorted(json.loads(str(rows.loc[0, "state_slot_state_json"])), key=lambda x: (str(x.get("role_scope", "")), int(x.get("slot_index", 0))))[:15]
        for si, slot in enumerate(slot_rows):
            slots[gi, si] = [vocab["slot"][field].get(str(slot.get(field, "")), 0) for field in SLOT_FIELDS]
            slot_mult[gi, si, 0] = float(slot.get("multiplier", 0.0) or 0.0)
        count = len(rows); mask[gi, :count] = True
        for ai, row in rows.iterrows():
            actions[gi, ai] = [vocab["action"][field].get(str(row.get(field, "")), 0) for field in ACTION_FIELDS]
            action_num[gi, ai] = [float(row.get(field, 0.0) or 0.0) for field in ("offer_current_multiplier", "offer_expected_delta", "offer_p75_delta", "offer_p90_delta")]
        values = pd.to_numeric(rows["q_target"], errors="coerce").fillna(0.0).to_numpy(dtype=np.float32); q[gi, :count] = values; labels[gi] = int(np.argmax(values))
        state_num[gi] = [float(rows.loc[0].get(field, 0.0) or 0.0) for field in ("state_banner_value", "state_rolls_left", "state_progress_ratio", "state_objective_safe", "state_objective_ceiling")]
    return {"slots": slots, "slot_mult": slot_mult, "actions": actions, "action_num": action_num, "mask": mask, "labels": labels, "q": q, "state_num": state_num}


class SlotAwareActorCritic(nn.Module):
    def __init__(self, vocab: dict[str, Any], emb: int = 16, hidden: int = 128) -> None:
        super().__init__(); self.vocab = vocab
        self.slot_emb = nn.ModuleList([nn.Embedding(len(vocab["slot"][f]) + 1, emb) for f in SLOT_FIELDS])
        self.action_emb = nn.ModuleList([nn.Embedding(len(vocab["action"][f]) + 1, emb) for f in ACTION_FIELDS])
        self.slot_proj = nn.Linear(len(SLOT_FIELDS) * emb + 1, hidden)
        layer = nn.TransformerEncoderLayer(d_model=hidden, nhead=4, batch_first=True, dim_feedforward=hidden * 2, dropout=0.1)
        self.encoder = nn.TransformerEncoder(layer, num_layers=2)
        self.state_proj = nn.Sequential(nn.Linear(hidden + 5, hidden), nn.ReLU())
        self.action_proj = nn.Sequential(nn.Linear(len(ACTION_FIELDS) * emb + 4, hidden), nn.ReLU())
        self.actor = nn.Linear(hidden * 2, 1); self.q_head = nn.Linear(hidden * 2, 1); self.value = nn.Linear(hidden, 1)

    def forward(self, slots: torch.Tensor, slot_mult: torch.Tensor, actions: torch.Tensor, action_num: torch.Tensor, state_num: torch.Tensor, mask: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        s = torch.cat([emb(slots[:, :, i]) for i, emb in enumerate(self.slot_emb)] + [slot_mult], dim=-1); s = self.encoder(self.slot_proj(s)); state = self.state_proj(torch.cat([s.mean(dim=1), state_num], dim=-1))
        a = torch.cat([emb(actions[:, :, i]) for i, emb in enumerate(self.action_emb)] + [action_num], dim=-1); a = self.action_proj(a)
        joined = torch.cat([state.unsqueeze(1).expand(-1, a.shape[1], -1), a], dim=-1)
        logits = self.actor(joined).squeeze(-1).masked_fill(~mask, -1e9)
        q = self.q_head(joined).squeeze(-1)
        # Terminal targets are z-scored before the critic loss. The state
        # includes raw banner value, so bound V in normalized space to prevent
        # an untrained linear head from exploding on a large scalar feature.
        value = self.value(state).squeeze(-1).clamp(-8.0, 8.0)
        return logits, q, value


class SlotAwareCrossAttentionRanker(SlotAwareActorCritic):
    """Ranker that lets every offered action attend to the concrete banner slots."""

    def __init__(self, vocab: dict[str, Any], emb: int = 16, hidden: int = 128) -> None:
        super().__init__(vocab, emb=emb, hidden=hidden)
        self.slot_key = nn.Linear(hidden, hidden, bias=False)
        self.action_query = nn.Linear(hidden, hidden, bias=False)
        self.cross_actor = nn.Linear(hidden * 3, 1)
        self.cross_q_head = nn.Linear(hidden * 3, 1)

    def forward(self, slots: torch.Tensor, slot_mult: torch.Tensor, actions: torch.Tensor, action_num: torch.Tensor, state_num: torch.Tensor, mask: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        s = torch.cat([emb(slots[:, :, i]) for i, emb in enumerate(self.slot_emb)] + [slot_mult], dim=-1)
        s = self.encoder(self.slot_proj(s))
        state = self.state_proj(torch.cat([s.mean(dim=1), state_num], dim=-1))
        a = torch.cat([emb(actions[:, :, i]) for i, emb in enumerate(self.action_emb)] + [action_num], dim=-1)
        a = self.action_proj(a)
        scale = float(s.shape[-1]) ** -0.5
        weights = torch.softmax(torch.matmul(self.action_query(a), self.slot_key(s).transpose(1, 2)) * scale, dim=-1)
        context = torch.matmul(weights, s)
        joined = torch.cat([state.unsqueeze(1).expand(-1, a.shape[1], -1), a, context], dim=-1)
        logits = self.cross_actor(joined).squeeze(-1).masked_fill(~mask, -1e9)
        q = self.cross_q_head(joined).squeeze(-1)
        return logits, q, self.value(state).squeeze(-1).clamp(-8.0, 8.0)


def train_slot_bootstrap(db_path: Path, dataset_id: str, epochs: int = 25, seed: int = 17) -> dict[str, Any]:
    torch.manual_seed(seed); con = sqlite3.connect(str(db_path))
    try: frame = _load_frame(con, dataset_id)
    finally: con.close()
    episodes = sorted(frame["episode_index"].astype(int).unique()); holdout = set(episodes[-max(1, len(episodes)//4):]); train_f=frame[~frame.episode_index.isin(holdout)].copy(); test_f=frame[frame.episode_index.isin(holdout)].copy()
    vocab=fit_vocab(train_f); train=pack(train_f,vocab); test=pack(test_f,vocab); model=SlotAwareActorCritic(vocab); opt=torch.optim.AdamW(model.parameters(),lr=3e-4,weight_decay=1e-4)
    q_mean=float(train["q"][train["mask"]].mean()); q_std=float(train["q"][train["mask"]].std()) or 1.0
    def tensors(data: dict[str,np.ndarray]): return {k:torch.tensor(v) for k,v in data.items()}
    tr=tensors(train); te=tensors(test)
    for _ in range(epochs):
        logits,q,v=model(tr["slots"],tr["slot_mult"],tr["actions"],tr["action_num"],tr["state_num"],tr["mask"]); qt=(tr["q"]-q_mean)/q_std; loss=F.cross_entropy(logits,tr["labels"])+.5*F.mse_loss(q[tr["mask"]],qt[tr["mask"]])+.25*F.mse_loss(v,qt.masked_fill(~tr["mask"],-1e9).max(1).values); opt.zero_grad(); loss.backward(); nn.utils.clip_grad_norm_(model.parameters(),1.0); opt.step()
    with torch.no_grad():
        logits,q,_=model(te["slots"],te["slot_mult"],te["actions"],te["action_num"],te["state_num"],te["mask"]); metrics={"actor_top1":float((logits.argmax(1)==te["labels"]).float().mean()),"q_top1":float((q.masked_fill(~te["mask"],-1e9).argmax(1)==te["labels"]).float().mean()),"test_decisions":int(len(test["labels"]))}
    return {"artifact":{"vocab":vocab,"state_dict":model.state_dict(),"q_mean":q_mean,"q_std":q_std},"metrics":metrics}
