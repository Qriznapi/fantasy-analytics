from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.nn import functional as F

from fantasy_rng_env import RNGEnvironment
from fantasy_rng_features import build_offer_rows_from_state
from fantasy_rng_slot_neural import SlotAwareActorCritic, pack
from fantasy_rng_q_critic import _load_frame


def load_slot_model(path: Path) -> tuple[SlotAwareActorCritic, dict[str, Any]]:
    artifact = torch.load(path, map_location="cpu", weights_only=False)
    model = SlotAwareActorCritic(artifact["vocab"]); model.load_state_dict(artifact["state_dict"]); return model, artifact


def save_slot_model(path: Path, model: SlotAwareActorCritic, artifact: dict[str, Any]) -> None:
    payload = dict(artifact); payload["state_dict"] = {k: v.detach().cpu() for k, v in model.state_dict().items()}; torch.save(payload, path)


def _rows(env: RNGEnvironment, offers: list[object]) -> pd.DataFrame:
    payload = [{"action_id": x.action_id, "token_id": x.token_id, "token_type": x.token_type, "role_scope": x.role_scope, "slot_index": x.slot_index, "current_stat_name": x.current_stat_name, "current_quality_tier": x.current_quality_tier, "current_trait_name": x.current_trait_name, "current_multiplier": x.current_multiplier, "is_refresh_action": int(x.is_refresh_action), "action_scope": x.action_scope, "target_color_group": x.target_color_group} for x in offers]
    rows = build_offer_rows_from_state(env.state_slots(), payload, baseline_value_before=env.current_value(), step_index=env.max_steps-env.steps_remaining()+1, max_steps=env.max_steps, episode_index=0)
    for row in rows:
        row["q_target"] = 0.0; row["state_objective_safe"] = int(env.objective_mode == "safe"); row["state_objective_ceiling"] = int(env.objective_mode == "ceiling")
    return pd.DataFrame(rows)


def observation(env: RNGEnvironment, offers: list[object], artifact: dict[str, Any]) -> dict[str, torch.Tensor]:
    data = pack(_rows(env, offers), artifact["vocab"])
    return {key: torch.tensor(value) for key, value in data.items() if key not in {"labels", "q"}}


def ppo_train_slot(model: SlotAwareActorCritic, artifact: dict[str, Any], *, profile_id: str, db_path: Path, updates: int, episodes_per_update: int, seed: int, token_preset: Path, starter_preset: Path, bc_dataset_id: str = "", bc_weight: float = 0.25, learning_rate: float = 3e-4, anchor_model: SlotAwareActorCritic | None = None, anchor_kl_weight: float = 0.0, on_update: Callable[[int, SlotAwareActorCritic], None] | None = None) -> dict[str, Any]:
    opt=torch.optim.AdamW(model.parameters(),lr=learning_rate); history=[]; objectives=("safe","balanced","ceiling")
    bc=None
    if bc_dataset_id:
        con=__import__('sqlite3').connect(str(db_path))
        try: bc=pack(_load_frame(con,bc_dataset_id),artifact["vocab"])
        finally: con.close()
    if anchor_model is not None:
        anchor_model.eval()
        for parameter in anchor_model.parameters():
            parameter.requires_grad_(False)
    rng=np.random.default_rng(seed)
    for update in range(updates):
        steps=[]
        for ep in range(episodes_per_update):
            env=RNGEnvironment(profile_id=profile_id,db_path=db_path,preset_path=token_preset,initial_state_preset_path=starter_preset,objective_mode=objectives[(update*episodes_per_update+ep)%3],max_steps=30,seed=seed+update*10000+ep); env.reset(seed=seed+update*10000+ep); trail=[]
            while not env.done():
                offers=env.sample_decision_offers(); obs=observation(env,offers,artifact)
                with torch.no_grad(): logits,_,value=model(obs["slots"],obs["slot_mult"],obs["actions"],obs["action_num"],obs["state_num"],obs["mask"]); dist=torch.distributions.Categorical(logits=logits); action=dist.sample()
                result=env.step(int(action)); trail.append({"obs":obs,"action":int(action),"logp":float(dist.log_prob(action)),"value":float(value),"reward":float(result.delta_value)})
            advantage=0.0; next_value=0.0
            for item in reversed(trail):
                advantage=item["reward"]+.99*next_value-item["value"]+.99*.95*advantage; item["adv"]=advantage; item["ret"]=advantage+item["value"]; next_value=item["value"]
            steps.extend(trail)
        adv=np.array([x["adv"] for x in steps],dtype=np.float32); adv=(adv-adv.mean())/max(adv.std(),1e-6)
        returns=np.array([x["ret"] for x in steps],dtype=np.float32)
        returns=(returns-returns.mean())/max(returns.std(),1e-6)
        for item,a,target in zip(steps,adv,returns): item["adv"]=float(a); item["ret_target"]=float(target)
        for _ in range(4):
            loss=0.0
            for item in steps:
                o=item["obs"]; logits,_,value=model(o["slots"],o["slot_mult"],o["actions"],o["action_num"],o["state_num"],o["mask"]); dist=torch.distributions.Categorical(logits=logits); ratio=torch.exp(dist.log_prob(torch.tensor(item["action"]))-torch.tensor(item["logp"])); policy=-torch.minimum(ratio*item["adv"],torch.clamp(ratio,.85,1.15)*item["adv"]); value_target=torch.full_like(value,float(item["ret_target"])); loss=loss+policy+.5*F.smooth_l1_loss(value,value_target)-.01*dist.entropy()
                if anchor_model is not None and anchor_kl_weight > 0:
                    with torch.no_grad(): anchor_logits,_,_=anchor_model(o["slots"],o["slot_mult"],o["actions"],o["action_num"],o["state_num"],o["mask"])
                    loss=loss+anchor_kl_weight*F.kl_div(F.log_softmax(logits,dim=1),F.softmax(anchor_logits,dim=1),reduction="batchmean")
            loss=loss/len(steps)
            if bc is not None and bc_weight > 0:
                ids=rng.choice(len(bc["labels"]),size=min(128,len(bc["labels"])),replace=False)
                b={key:torch.tensor(value[ids]) for key,value in bc.items()}
                bc_logits,_,_=model(b["slots"],b["slot_mult"],b["actions"],b["action_num"],b["state_num"],b["mask"])
                loss=loss+bc_weight*F.cross_entropy(bc_logits,b["labels"])
            opt.zero_grad(); loss.backward(); nn.utils.clip_grad_norm_(model.parameters(),1.0); opt.step()
        history.append({"update":update+1,"steps":len(steps),"mean_reward":float(np.mean([x["reward"] for x in steps])),"bc_weight":bc_weight if bc is not None else 0.0,"learning_rate":learning_rate,"anchor_kl_weight":anchor_kl_weight if anchor_model is not None else 0.0})
        if on_update: on_update(update+1,model)
    return {"history":history}


def simulate_slot_model(model: SlotAwareActorCritic, artifact: dict[str, Any], *, profile_id: str, db_path: Path, scenario: dict[str, Any], seeds: list[int], episodes_per_seed: int) -> pd.DataFrame:
    root=Path(__file__).resolve().parents[1]; token=root/scenario["token_preset_path"]; starter=root/scenario["initial_state_preset_path"]; rows=[]
    for seed in seeds:
        for episode in range(episodes_per_seed):
            episode_seed=seed*10000+episode; env=RNGEnvironment(profile_id=profile_id,db_path=db_path,preset_path=token,initial_state_preset_path=starter,objective_mode=scenario["objective_mode"],max_steps=30,seed=episode_seed); env.reset(seed=episode_seed); initial=env.current_value()
            while not env.done():
                offers=env.sample_decision_offers(); o=observation(env,offers,artifact)
                with torch.no_grad(): logits,_,_=model(o["slots"],o["slot_mult"],o["actions"],o["action_num"],o["state_num"],o["mask"])
                env.step(int(logits.argmax(1)))
            rows.append({"scenario_id":scenario["scenario_id"],"objective_mode":scenario["objective_mode"],"seed":seed,"episode_index":episode,"initial_value":initial,"final_value":env.current_value()})
    return pd.DataFrame(rows)
