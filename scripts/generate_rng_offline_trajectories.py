from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fantasy_rng_env import RNGEnvironment
from fantasy_rng_offline_warehouse import replace_dataset
from fantasy_rng_slot_planner import choose_planned_action
from fantasy_rng_slot_rl import load_slot_model, observation


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate full planner trajectories for conservative offline RL.")
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--episodes", type=int, default=48)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--rollouts", type=int, default=4)
    parser.add_argument("--horizon", type=int, default=6)
    parser.add_argument("--token-preset", default=str(ROOT / "configs" / "rng_tokens" / "observed_run1_8_materials_blended_red_tilt_v4.json"))
    parser.add_argument("--initial-state-preset", default=str(ROOT / "configs" / "rng_initial_states" / "starters_conservative_v4.json"))
    parser.add_argument("--planner-preference-weight", type=float, default=0.10)
    parser.add_argument("--planner-strategy-prior-weight", type=float, default=0.0)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()
    started = time.perf_counter()

    model, artifact = load_slot_model(Path(args.artifact))
    model.eval()
    objectives = ("safe", "balanced", "ceiling")
    episodes = []
    for episode_index in range(args.episodes):
        episode_seed = args.seed + episode_index
        env = RNGEnvironment(profile_id=args.profile_id, db_path=Path(args.db_path), preset_path=Path(args.token_preset), initial_state_preset_path=Path(args.initial_state_preset), objective_mode=objectives[episode_index % 3], max_steps=30, seed=episode_seed)
        env.reset(seed=episode_seed)
        steps = []
        while not env.done():
            slots = env.state_slots()
            before = env.current_value()
            offers = env.sample_decision_offers()
            with torch.no_grad():
                obs = observation(env, offers, artifact)
                logits, _, _ = model(obs["slots"], obs["slot_mult"], obs["actions"], obs["action_num"], obs["state_num"], obs["mask"])
                probs = torch.softmax(logits, dim=1).squeeze(0).tolist()
            decision = choose_planned_action(model, artifact, env, offers, top_k=args.top_k, rollouts=args.rollouts, horizon=min(args.horizon, env.steps_remaining()), risk_mode=env.objective_mode, seed=episode_seed * 100 + env.steps_remaining(), include_refresh_candidate=True, preference_weight=args.planner_preference_weight, strategy_prior_weight=args.planner_strategy_prior_weight)
            action_index = int(decision["chosen_action_index"])
            result = env.step(action_index)
            steps.append({"episode_index": episode_index, "step_index": result.step_index, "episode_seed": episode_seed, "objective_mode": env.objective_mode, "state_value_before": before, "state_value_after": result.value_after, "immediate_reward": result.delta_value, "behavior_action_index": action_index, "behavior_action": offers[action_index].__dict__, "state_slots": slots, "offers": [offer.__dict__ for offer in offers], "actor_logits": logits.squeeze(0).tolist(), "actor_probs": probs, "planner_candidates": decision["candidates"]})
        final = env.current_value()
        for step in steps:
            step["final_value"] = final
            step["return_to_go"] = final - float(step["state_value_before"])
        episodes.append(steps)
    con = sqlite3.connect(args.db_path)
    try:
        counts = replace_dataset(
            con,
            dataset_id=args.dataset_id,
            source_artifact=str(Path(args.artifact).resolve()),
            planner_config={
                "top_k": args.top_k,
                "rollouts": args.rollouts,
                "horizon": args.horizon,
                "include_refresh_candidate": True,
                "planner_preference_weight": float(args.planner_preference_weight),
                "planner_strategy_prior_weight": float(args.planner_strategy_prior_weight),
                "token_preset": str(Path(args.token_preset).resolve()),
                "initial_state_preset": str(Path(args.initial_state_preset).resolve()),
            },
            episodes=episodes,
        )
    finally:
        con.close()
    elapsed = time.perf_counter() - started
    summary = {"dataset_id": args.dataset_id, "seed_start": args.seed, "episodes_requested": args.episodes, **counts, "elapsed_seconds": elapsed, "seconds_per_episode": elapsed / max(1, args.episodes), "objectives": {name: sum(1 for index in range(args.episodes) if objectives[index % 3] == name) for name in objectives}}
    Path(args.output_json).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
