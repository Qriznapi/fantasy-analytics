from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import torch

from fantasy_rng_env import RNGEnvironment, RNGOffer
from fantasy_rng_neural_rl import _observation, load_model
from fantasy_rng_slot_planner import choose_planned_action
from fantasy_rng_slot_rl import load_slot_model, observation as slot_observation


def slot_text(env: RNGEnvironment) -> str:
    return "\n".join(
        f"{slot['role_scope']:<7} #{slot['slot_index']} | {slot['color_group']:<5} | {slot['stat_name']:<24} | {slot['quality_tier']:<8} | {slot['trait_name']:<10} | x{float(slot['multiplier']):.2f}"
        for slot in env.state_slots()
    )


def load_policy(path: Path) -> tuple[str, torch.nn.Module, dict]:
    payload = torch.load(path, map_location="cpu", weights_only=False)
    if "vocab" in payload:
        model, artifact = load_slot_model(path)
        return "slot", model.eval(), artifact
    model, artifact = load_model(path)
    return "mlp", model.eval(), artifact


def choose_model_action(kind: str, model: torch.nn.Module, artifact: dict, env: RNGEnvironment, actions: list[RNGOffer], *, planner: bool, planner_rollouts: int, planner_horizon: int, seed: int) -> tuple[int, dict]:
    if kind == "slot":
        if planner:
            audit = choose_planned_action(model, artifact, env, actions, top_k=3, rollouts=planner_rollouts, horizon=planner_horizon, risk_mode=env.objective_mode, seed=seed)
            return int(audit["chosen_action_index"]), audit
        with torch.no_grad():
            obs = slot_observation(env, actions, artifact)
            logits, _, _ = model(obs["slots"], obs["slot_mult"], obs["actions"], obs["action_num"], obs["state_num"], obs["mask"])
        return int(logits.argmax(dim=1).item()), {"planner": "disabled"}
    with torch.no_grad():
        logits, _, _ = model(_observation(env, actions, artifact["schema"]), torch.ones((1, len(actions)), dtype=torch.bool))
    return int(logits.argmax(dim=1).item()), {"planner": "unsupported_for_mlp"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Play the same token schedule against an MLP or slot-aware policy.")
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--objective", choices=["safe", "balanced", "ceiling"], default="balanced")
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--planner", action="store_true", help="Rerank slot actor choices with short rollouts.")
    parser.add_argument("--planner-rollouts", type=int, default=4)
    parser.add_argument("--planner-horizon", type=int, default=6)
    parser.add_argument("--token-preset", default=str(ROOT / "configs" / "rng_tokens" / "observed_run1_8_materials_blended_red_tilt_v4.json"))
    parser.add_argument("--initial-state-preset", default=str(ROOT / "configs" / "rng_initial_states" / "starters_conservative_v4.json"))
    parser.add_argument("--replay-dir", default=str(ROOT / "reports" / "human_vs_model"))
    args = parser.parse_args()

    kind, model, artifact = load_policy(Path(args.artifact))
    common = dict(profile_id=args.profile_id, db_path=Path(args.db_path), preset_path=Path(args.token_preset), initial_state_preset_path=Path(args.initial_state_preset), objective_mode=args.objective, max_steps=args.max_steps)
    human = RNGEnvironment(**common, seed=args.seed)
    model_env = RNGEnvironment(**common, seed=args.seed)
    schedule = RNGEnvironment(**common, seed=args.seed + 9_999)
    human.reset(seed=args.seed)
    model_env.reset(seed=args.seed)
    replay = {"seed": args.seed, "objective": args.objective, "artifact": args.artifact, "policy_kind": kind, "planner": bool(args.planner and kind == "slot"), "steps": []}
    print(f"\nHuman vs {kind} model. Choose a token, then its legal role; q exits early.\n")
    while not human.done():
        tokens = schedule.sample_token_offers()
        print(f"\n=== Step {args.max_steps - human.steps_remaining() + 1}/{args.max_steps} | rolls left: {human.steps_remaining()} ===")
        print(f"Your value: {human.current_value():.2f} | Model value: {model_env.current_value():.2f}\n{slot_text(human)}")
        for index, token in enumerate(tokens):
            print(f"[{index}] {token.token_id} | {token.action_scope} {token.target_color_group}".rstrip())
        print(f"[{len(tokens)}] refresh / skip")
        while True:
            choice = input("Your choice: ").strip().lower()
            if choice in {"q", "quit", "exit"}:
                return
            if choice.isdigit() and 0 <= int(choice) <= len(tokens):
                token_choice = int(choice)
                break
            print(f"Enter 0..{len(tokens)}, or q.")
        human_actions = [] if token_choice == len(tokens) else human.legal_actions_for_token(tokens[token_choice].token_id)
        if human_actions:
            print("Roles: " + ", ".join(f"[{i}] {item.role_scope}" for i, item in enumerate(human_actions)))
            while True:
                raw = input("Role choice: ").strip()
                if raw.isdigit() and 0 <= int(raw) < len(human_actions):
                    human_action = human_actions[int(raw)]
                    break
                print(f"Enter 0..{len(human_actions) - 1}.")
        else:
            human_action = RNGOffer("refresh_offers", "refresh_offers", "refresh_offers", "global", -1, "", "", "", 0.0, 1.0, True)
        model_actions = [action for token in tokens for action in model_env.legal_actions_for_token(token.token_id)]
        model_actions.append(RNGOffer("refresh_offers", "refresh_offers", "refresh_offers", "global", -1, "", "", "", 0.0, 1.0, True))
        model_index, audit = choose_model_action(kind, model, artifact, model_env, model_actions, planner=args.planner, planner_rollouts=args.planner_rollouts, planner_horizon=args.planner_horizon, seed=args.seed + human.steps_remaining())
        model_action = model_actions[model_index]
        human_result = human.step_action(human_action)
        model_result = model_env.step_action(model_action)
        print(f"Model chose {model_action.token_id} -> {model_action.role_scope}; deltas: you {human_result.delta_value:+.2f}, model {model_result.delta_value:+.2f}")
        replay["steps"].append({"step": human_result.step_index, "tokens": [item.__dict__ for item in tokens], "human_action": human_action.__dict__, "model_action": model_action.__dict__, "model_audit": audit, "human_value": human_result.value_after, "model_value": model_result.value_after})
    replay["human_final_value"] = human.current_value()
    replay["model_final_value"] = model_env.current_value()
    replay["winner"] = "human" if replay["human_final_value"] > replay["model_final_value"] else "model"
    out_dir = Path(args.replay_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"rng_vs_model_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.write_text(json.dumps(replay, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nFinal: you {replay['human_final_value']:.2f}, model {replay['model_final_value']:.2f}. Winner: {replay['winner']}.\nSaved: {out}")


if __name__ == "__main__":
    main()
