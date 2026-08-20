from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from fantasy_rng_slot_neural import train_slot_bootstrap
p=argparse.ArgumentParser(description='Train slot-aware attention bootstrap.'); p.add_argument('--db-path',required=True); p.add_argument('--dataset-id',required=True); p.add_argument('--artifact-output',required=True); p.add_argument('--epochs',type=int,default=25); p.add_argument('--seed',type=int,default=17); p.add_argument('--output-json',required=True); a=p.parse_args()
r=train_slot_bootstrap(Path(a.db_path),a.dataset_id,a.epochs,a.seed); torch=__import__('torch'); torch.save(r['artifact'],a.artifact_output); Path(a.output_json).write_text(json.dumps({"artifact_path":a.artifact_output,"metrics":r['metrics']},ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(r['metrics'],ensure_ascii=False,indent=2))
