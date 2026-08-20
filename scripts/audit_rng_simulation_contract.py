"""Fast invariants audit for the exact-token banner simulator.

This does not assess model skill.  It checks the mechanics shared by the UI,
warehouse generator and PPO environment before a model is trained on them.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fantasy_rng_env import RNGEnvironment
from fantasy_rng_slot_planner import choose_planned_action
from fantasy_rng_slot_rl import load_slot_model


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", default=str(ROOT / "data" / "ti_2026_fantasy_compact.sqlite"))
    parser.add_argument("--profile-id", default="ti2026_playoff_observed_nothingtogay_v1")
    parser.add_argument("--model", default=str(ROOT / "models" / "rng_neural_slot_selfplay_selected_v1.pt"))
    parser.add_argument("--episodes", type=int, default=100)
    args = parser.parse_args()

    env = RNGEnvironment(
        profile_id=args.profile_id,
        db_path=Path(args.db_path),
        preset_path=ROOT / "configs" / "rng_tokens" / "observed_run1_8_materials_blended_red_tilt_v4.json",
        initial_state_preset_path=ROOT / "configs" / "rng_initial_states" / "starters_conservative_v4.json",
        max_steps=30,
    )
    model, artifact = load_slot_model(Path(args.model))
    model.eval()
    checked_steps = 0
    for episode in range(args.episodes):
        env.reset(seed=50_000 + episode)
        for _ in range(env.max_steps):
            token_offers = env.sample_token_offers()
            assert len(token_offers) == 3
            assert len({offer.token_id for offer in token_offers}) == 3
            refresh = next(action for action in env.sample_decision_offers() if action.is_refresh_action)
            # sample_decision_offers() samples again, so build one valid decision
            # set from its own token offers for planner auditing.
            decision_offers = env.sample_decision_offers()
            decision = choose_planned_action(
                model, artifact, env, decision_offers, top_k=3, rollouts=1,
                horizon=1, include_refresh_candidate=True,
            )
            candidate_ids = [row["token_id"] for row in decision["candidates"]]
            assert candidate_ids[-1] == "refresh_offers"
            assert len(candidate_ids) == 4
            assert len(set(candidate_ids[:-1])) == 3
            # Refresh is a deliberate no-op that spends one of 30 operations.
            snapshot = env.state_slots()
            result = env.step_action(refresh)
            assert result.value_before == result.value_after
            assert env.state_slots() == snapshot
            assert result.step_index == 1
            checked_steps += 1
            # Start a fresh state next iteration: this audit needs one step only.
            break
        for role in ("core", "mid", "support"):
            slots = [slot for slot in env.state_slots() if slot["role_scope"] == role]
            assert len(slots) == 5
            assert len({slot["stat_name"] for slot in slots}) == len(slots)
            assert all(slot["quality_tier"] in {"tier_i", "tier_ii", "tier_iii", "tier_iv", "tier_v"} for slot in slots)
    print(f"PASS: {args.episodes} reset states, {checked_steps} exact-token decisions, refresh and uniqueness invariants")


if __name__ == "__main__":
    main()
