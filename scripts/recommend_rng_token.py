from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fantasy_rng_actor_critic import predict_critic_rows  # noqa: E402
from fantasy_rng_env import RNGEnvironment  # noqa: E402
from fantasy_rng_policy_models import score_policy_offer_set_from_state  # noqa: E402
from fantasy_rng_q_critic import predict_q_rows  # noqa: E402
from fantasy_rng_ranking import score_offer_set_with_ranker  # noqa: E402
from fantasy_rng_registry import load_champion, persist_inference  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Give one traceable RNG token recommendation from the registered champion.")
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--token-preset", default="")
    parser.add_argument("--initial-state-preset", default="")
    parser.add_argument("--objective-mode", choices=["safe", "balanced", "ceiling"], default="balanced")
    parser.add_argument("--q-critic-artifact", default="", help="Optional action-value critic; keeps registry champion unchanged.")
    parser.add_argument("--ranker-artifact", default="", help="Optional leakage-free pairwise ranker; combines equally with Q when both are supplied.")
    parser.add_argument("--output-json", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    con = sqlite3.connect(args.db_path)
    try:
        champion = load_champion(con)
        actor = json.loads(Path(champion["actor_artifact_path"]).read_text(encoding="utf-8"))
        critic_path = champion.get("critic_artifact_path")
        critic = json.loads(Path(critic_path).read_text(encoding="utf-8")) if critic_path else None
        q_critic = json.loads(Path(args.q_critic_artifact).read_text(encoding="utf-8")) if args.q_critic_artifact else None
        ranker = json.loads(Path(args.ranker_artifact).read_text(encoding="utf-8")) if args.ranker_artifact else None
        env = RNGEnvironment(
            profile_id=args.profile_id, db_path=Path(args.db_path), seed=args.seed, max_steps=args.max_steps,
            preset_path=Path(args.token_preset) if args.token_preset else ROOT / "configs" / "rng_tokens" / "observed_run1_8_materials_blended_red_tilt_v4.json",
            initial_state_preset_path=Path(args.initial_state_preset) if args.initial_state_preset else None,
            objective_mode=args.objective_mode,
        )
        env.reset(seed=args.seed)
        offers = env.sample_offers()
        rows = score_policy_offer_set_from_state(
            env.state_slots(), [offer.__dict__ for offer in offers], baseline_value_before=env.current_value(),
            step_index=1, max_steps=args.max_steps, artifact=actor,
        )
        raw = rows["predicted_prob"].astype(float).to_numpy()
        probabilities = np.exp(raw - raw.max()); probabilities /= probabilities.sum()
        rows["policy_probability"] = probabilities
        rows["critic_return"] = predict_critic_rows(rows, critic) if critic else np.nan
        rows["q_action_value"] = predict_q_rows(rows, q_critic) if q_critic else np.nan
        ranker_rows = score_offer_set_with_ranker(
            slots=env.state_slots(), offers=[offer.__dict__ for offer in offers],
            baseline_value_before=env.current_value(), step_index=1, max_steps=args.max_steps, artifact=ranker,
        ) if ranker else None
        rows["ranker_score"] = ranker_rows["ranking_score"].to_numpy() if ranker_rows is not None else np.nan
        if q_critic and ranker:
            q_z = (rows["q_action_value"] - rows["q_action_value"].mean()) / max(1e-9, float(rows["q_action_value"].std(ddof=0)))
            r_z = (rows["ranker_score"] - rows["ranker_score"].mean()) / max(1e-9, float(rows["ranker_score"].std(ddof=0)))
            rows["decision_score"] = q_z + r_z
        elif q_critic:
            rows["decision_score"] = rows["q_action_value"]
        elif ranker:
            rows["decision_score"] = rows["ranker_score"]
        else:
            rows["decision_score"] = rows["policy_probability"]
        chosen_index = int(rows["decision_score"].idxmax())
        selected = rows.loc[chosen_index].to_dict()
        entropy = float(-np.sum(probabilities * np.log(np.clip(probabilities, 1e-12, 1.0))))
        max_entropy = math.log(max(2, len(probabilities)))
        confidence = float(selected["policy_probability"])
        risk_flag = "high" if critic is None or confidence < 0.40 or entropy / max_entropy > 0.90 else ("medium" if confidence < 0.55 else "low")
        critic_return = selected["critic_return"]
        advantage = float(selected["q_action_value"] - rows["q_action_value"].astype(float).mean()) if q_critic else (float(critic_return * (confidence - float(probabilities.mean()))) if not np.isnan(critic_return) else None)
        action_label = "refresh offers" if bool(selected["offer_is_refresh_action"]) else f"{selected['offer_token_type']} on {selected['offer_role_scope']} slot {int(selected['offer_slot_index'])}"
        reason = (f"Highest fixed 50/50 standardized Q+ranker score among {len(rows)} current choices; {action_label}." if q_critic and ranker else (f"Highest action-value Q estimate ({float(selected['q_action_value']):.2f}) among {len(rows)} current choices; {action_label}." if q_critic else (f"Highest pairwise ranker score ({float(selected['ranker_score']):.3f}) among {len(rows)} current choices; {action_label}." if ranker else f"Highest normalized policy probability ({confidence:.1%}) among {len(rows)} current choices; {action_label}.")))
        payload = {
            "policy_version": champion["policy_version"], "profile_id": args.profile_id, "seed": args.seed,
            "objective_mode": args.objective_mode, "initial_banner_value": float(env.current_value()),
            "recommended_offer_index": chosen_index, "recommended_action": action_label,
            "policy_probability": confidence, "critic_return": None if np.isnan(critic_return) else float(critic_return),
            "q_action_value": None if np.isnan(selected["q_action_value"]) else float(selected["q_action_value"]),
            "ranker_score": None if np.isnan(selected["ranker_score"]) else float(selected["ranker_score"]),
            "decision_score": float(selected["decision_score"]),
            "advantage_estimate": advantage, "offer_set_entropy": entropy, "risk_flag": risk_flag,
            "reason": reason,
            "all_offers": rows[["offer_action_id", "offer_token_type", "offer_role_scope", "offer_slot_index", "offer_current_stat_name", "policy_probability", "critic_return", "q_action_value", "ranker_score", "decision_score"]].to_dict(orient="records"),
        }
        payload["inference_id"] = persist_inference(con, policy_version=champion["policy_version"], profile_id=args.profile_id, seed=args.seed, payload=payload)
    finally:
        con.close()
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output_json:
        Path(args.output_json).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
