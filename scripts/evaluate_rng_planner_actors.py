from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fantasy_rng_planner_actor_eval import evaluate_planner_actors
from fantasy_rng_slot_rl import load_slot_model


def main() -> None:
    parser = argparse.ArgumentParser(description="Matched base-planner versus candidate-planner evaluation.")
    parser.add_argument("--db-path", required=True); parser.add_argument("--profile-id", required=True)
    parser.add_argument("--base-artifact", required=True); parser.add_argument("--candidate-artifact", required=True); parser.add_argument("--output-json", required=True)
    parser.add_argument("--episodes", type=int, default=24); parser.add_argument("--seed", type=int, default=120001); parser.add_argument("--rollouts", type=int, default=4); parser.add_argument("--horizon", type=int, default=6)
    parser.add_argument("--preference-weight", type=float, default=.10); parser.add_argument("--strategy-prior-weight", type=float, default=1.0)
    parser.add_argument("--base-critic-leaf-weight", type=float, default=0.0)
    parser.add_argument("--candidate-critic-leaf-weight", type=float, default=0.0)
    parser.add_argument("--token-preset", default=str(ROOT / "configs" / "rng_tokens" / "observed_run1_8_materials_blended_red_tilt_v4.json")); parser.add_argument("--initial-state-preset", default=str(ROOT / "configs" / "rng_initial_states" / "starters_conservative_v4.json"))
    args = parser.parse_args()
    base_model, base_artifact = load_slot_model(Path(args.base_artifact)); base_model.eval()
    candidate_model, candidate_artifact = load_slot_model(Path(args.candidate_artifact)); candidate_model.eval()
    report = evaluate_planner_actors(db_path=Path(args.db_path), profile_id=args.profile_id, base_model=base_model, base_artifact=base_artifact, candidate_model=candidate_model, candidate_artifact=candidate_artifact, token_preset=Path(args.token_preset), starter_preset=Path(args.initial_state_preset), episodes=args.episodes, seed=args.seed, rollouts=args.rollouts, horizon=args.horizon, preference_weight=args.preference_weight, strategy_prior_weight=args.strategy_prior_weight, base_critic_leaf_weight=args.base_critic_leaf_weight, candidate_critic_leaf_weight=args.candidate_critic_leaf_weight)
    Path(args.output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "episode_rows"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
