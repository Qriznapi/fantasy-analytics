from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fantasy_rng_slot_rl import load_slot_model,ppo_train_slot,save_slot_model
p=argparse.ArgumentParser(description='PPO for slot-aware exact-token actor.');p.add_argument('--db-path',required=True);p.add_argument('--profile-id',required=True);p.add_argument('--artifact-in',required=True);p.add_argument('--artifact-out',required=True);p.add_argument('--updates',type=int,default=4);p.add_argument('--episodes-per-update',type=int,default=8);p.add_argument('--seed',type=int,default=4501);p.add_argument('--bc-dataset-id',default='');p.add_argument('--bc-weight',type=float,default=.25);p.add_argument('--learning-rate',type=float,default=3e-4);p.add_argument('--anchor-artifact',default='');p.add_argument('--anchor-kl-weight',type=float,default=0.0);p.add_argument('--checkpoint-dir',default='');p.add_argument('--output-json',required=True);a=p.parse_args()
m,x=load_slot_model(Path(a.artifact_in));d=Path(a.checkpoint_dir) if a.checkpoint_dir else None
anchor=None
if a.anchor_artifact:
    anchor,_=load_slot_model(Path(a.anchor_artifact))
if d: d.mkdir(parents=True,exist_ok=True)
def checkpoint(i,model):
    if d: save_slot_model(d/f'update_{i:03d}.pt',model,x)
r=ppo_train_slot(m,x,profile_id=a.profile_id,db_path=Path(a.db_path),updates=a.updates,episodes_per_update=a.episodes_per_update,seed=a.seed,token_preset=ROOT/'configs/rng_tokens/observed_run1_8_materials_blended_red_tilt_v4.json',starter_preset=ROOT/'configs/rng_initial_states/starters_conservative_v4.json',bc_dataset_id=a.bc_dataset_id,bc_weight=a.bc_weight,learning_rate=a.learning_rate,anchor_model=anchor,anchor_kl_weight=a.anchor_kl_weight,on_update=checkpoint);save_slot_model(Path(a.artifact_out),m,x);Path(a.output_json).write_text(json.dumps({**r,'artifact':a.artifact_out},ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(r,ensure_ascii=False,indent=2))
