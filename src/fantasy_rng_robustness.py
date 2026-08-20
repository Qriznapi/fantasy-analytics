from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from fantasy_rng_env import RNGEnvironment
from fantasy_rng_foundation import DEFAULT_PRESET_PATH
from fantasy_rng_policy_models import score_policy_offer_set_from_state
from fantasy_rng_q_critic import predict_q_rows
from fantasy_rng_ranking import score_offer_set_with_ranker

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _project_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_scenarios(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    scenarios = list(payload.get("scenarios", []))
    if not scenarios:
        raise ValueError(f"No scenarios in {path}")
    required = {"scenario_id", "objective_mode"}
    for scenario in scenarios:
        missing = required - set(scenario)
        if missing:
            raise ValueError(f"Scenario is missing {sorted(missing)}: {scenario}")
    return scenarios


def simulate_policy_scenario(
    *,
    profile_id: str,
    db_path: Path,
    artifact: dict[str, Any],
    scenario: dict[str, Any],
    seeds: list[int],
    episodes_per_seed: int,
    max_steps: int,
    offers_per_step: int = 3,
) -> pd.DataFrame:
    """Run an actor deterministically on matched scenario seeds."""
    rows: list[dict[str, Any]] = []
    token_preset = _project_path(scenario.get("token_preset_path"))
    starter_preset = _project_path(scenario.get("initial_state_preset_path"))
    for seed in seeds:
        for episode_index in range(int(episodes_per_seed)):
            episode_seed = int(seed) * 10_000 + episode_index
            env = RNGEnvironment(
                profile_id=profile_id,
                db_path=db_path,
                preset_path=token_preset or DEFAULT_PRESET_PATH,
                initial_state_preset_path=starter_preset,
                objective_mode=str(scenario["objective_mode"]),
                max_steps=max_steps,
                offers_per_step=offers_per_step,
                seed=episode_seed,
            )
            env.reset(seed=episode_seed)
            initial_value = float(env.current_value())
            while not env.done():
                offers = env.sample_offers()
                offer_rows = [offer.__dict__ for offer in offers]
                scored = score_policy_offer_set_from_state(
                    env.state_slots(), offer_rows,
                    baseline_value_before=float(env.current_value()),
                    step_index=max_steps - env.steps_remaining() + 1,
                    max_steps=max_steps,
                    artifact=artifact,
                )
                env.step(int(scored["predicted_prob"].astype(float).idxmax()))
            final_value = float(env.current_value())
            rows.append({
                "scenario_id": str(scenario["scenario_id"]),
                "objective_mode": str(scenario["objective_mode"]),
                "seed": int(seed),
                "episode_index": episode_index,
                "initial_value": initial_value,
                "final_value": final_value,
                "total_delta": final_value - initial_value,
            })
    return pd.DataFrame(rows)


def simulate_q_ranker_ensemble_scenario(
    *,
    profile_id: str,
    db_path: Path,
    q_critic: dict[str, Any],
    ranker: dict[str, Any],
    scenario: dict[str, Any],
    seeds: list[int],
    episodes_per_seed: int,
    max_steps: int,
    offers_per_step: int = 3,
) -> pd.DataFrame:
    """Evaluate the fixed, untuned Q+pairwise ensemble on matched scenario seeds."""
    rows: list[dict[str, Any]] = []
    token_preset = _project_path(scenario.get("token_preset_path"))
    starter_preset = _project_path(scenario.get("initial_state_preset_path"))
    for seed in seeds:
        for episode_index in range(int(episodes_per_seed)):
            episode_seed = int(seed) * 10_000 + episode_index
            env = RNGEnvironment(
                profile_id=profile_id, db_path=db_path, preset_path=token_preset or DEFAULT_PRESET_PATH,
                initial_state_preset_path=starter_preset, objective_mode=str(scenario["objective_mode"]),
                max_steps=max_steps, offers_per_step=offers_per_step, seed=episode_seed,
            )
            env.reset(seed=episode_seed)
            initial_value = float(env.current_value())
            while not env.done():
                offers = env.sample_offers()
                offer_rows = [offer.__dict__ for offer in offers]
                value_before = float(env.current_value())
                step_index = max_steps - env.steps_remaining() + 1
                policy_rows = score_policy_offer_set_from_state(
                    env.state_slots(), offer_rows, baseline_value_before=value_before,
                    step_index=step_index, max_steps=max_steps,
                    # The feature builder is shared with actor scoring; an empty logistic is not needed here.
                    artifact={"numeric_cols": [], "categorical_cols": [], "categories": {}, "logistic": {"w": [], "b": 0.0, "x_mean": [], "x_std": []}},
                )
                policy_rows["q_score"] = predict_q_rows(policy_rows, q_critic)
                rank_rows = score_offer_set_with_ranker(
                    slots=env.state_slots(), offers=offer_rows, baseline_value_before=value_before,
                    step_index=step_index, max_steps=max_steps, artifact=ranker,
                )
                policy_rows["ranker_score"] = rank_rows["ranking_score"].to_numpy()
                q_std = float(policy_rows["q_score"].std(ddof=0)) or 1.0
                r_std = float(policy_rows["ranker_score"].std(ddof=0)) or 1.0
                policy_rows["ensemble_score"] = ((policy_rows["q_score"] - policy_rows["q_score"].mean()) / q_std) + ((policy_rows["ranker_score"] - policy_rows["ranker_score"].mean()) / r_std)
                env.step(int(policy_rows["ensemble_score"].idxmax()))
            final_value = float(env.current_value())
            rows.append({"scenario_id": str(scenario["scenario_id"]), "objective_mode": str(scenario["objective_mode"]), "seed": int(seed), "episode_index": episode_index, "initial_value": initial_value, "final_value": final_value, "total_delta": final_value - initial_value})
    return pd.DataFrame(rows)


def distribution_metrics(values: pd.Series) -> dict[str, float]:
    numeric = values.astype(float)
    return {
        "mean": float(numeric.mean()),
        "p10": float(numeric.quantile(0.10)),
        "p75": float(numeric.quantile(0.75)),
        "p90": float(numeric.quantile(0.90)),
        "max": float(numeric.max()),
    }


def paired_scenario_metrics(candidate: pd.DataFrame, reference: pd.DataFrame) -> dict[str, Any]:
    merged = candidate.merge(
        reference,
        on=["scenario_id", "seed", "episode_index"],
        suffixes=("_candidate", "_reference"),
        validate="one_to_one",
    )
    margins = merged["final_value_candidate"].astype(float) - merged["final_value_reference"].astype(float)
    n = len(margins)
    std = float(margins.std(ddof=1)) if n > 1 else 0.0
    mean = float(margins.mean()) if n else 0.0
    standard_error = std / math.sqrt(n) if n > 1 else 0.0
    ci_half_width = 1.96 * standard_error
    return {
        "paired_margin_mean": mean,
        "paired_margin_std": std,
        "paired_margin_se": standard_error,
        "paired_margin_ci95_low": mean - ci_half_width,
        "paired_margin_ci95_high": mean + ci_half_width,
        "paired_margin_ci95_excludes_zero": bool(mean - ci_half_width > 0 or mean + ci_half_width < 0),
        "win_rate": float((margins > 0).mean()) if n else 0.0,
        "sample_count": int(n),
    }


def persist_robustness_run(con: sqlite3.Connection, payload: dict[str, Any]) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS fantasy_rng_robustness_runs (
          run_id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL, profile_id TEXT NOT NULL,
          candidate_artifact TEXT NOT NULL, reference_artifact TEXT NOT NULL,
          scenario_config_path TEXT NOT NULL, metrics_json TEXT NOT NULL, created_at_utc TEXT NOT NULL
        )
    """)
    con.execute(
        "INSERT INTO fantasy_rng_robustness_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            payload["run_id"], payload["dataset_id"], payload["profile_id"],
            payload["candidate_artifact"], payload["reference_artifact"],
            payload["scenario_config_path"], json.dumps(payload, ensure_ascii=False),
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ),
    )
    con.commit()
