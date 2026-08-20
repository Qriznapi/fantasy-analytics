from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


def create_schema(con: sqlite3.Connection) -> None:
    con.executescript("""
        CREATE TABLE IF NOT EXISTS fantasy_rng_offline_trajectory_builds (
          dataset_id TEXT PRIMARY KEY, source_artifact TEXT NOT NULL, planner_config_json TEXT NOT NULL,
          episode_count INTEGER NOT NULL, step_count INTEGER NOT NULL, created_at_utc TEXT NOT NULL, notes TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fantasy_rng_offline_trajectory_steps (
          dataset_id TEXT NOT NULL, episode_index INTEGER NOT NULL, step_index INTEGER NOT NULL,
          episode_seed INTEGER NOT NULL, objective_mode TEXT NOT NULL, state_value_before REAL NOT NULL,
          state_value_after REAL NOT NULL, final_value REAL NOT NULL, return_to_go REAL NOT NULL,
          immediate_reward REAL NOT NULL, behavior_action_index INTEGER NOT NULL, behavior_action_json TEXT NOT NULL,
          state_slots_json TEXT NOT NULL, offers_json TEXT NOT NULL, actor_logits_json TEXT NOT NULL,
          actor_probs_json TEXT NOT NULL, planner_candidates_json TEXT NOT NULL, created_at_utc TEXT NOT NULL,
          PRIMARY KEY(dataset_id, episode_index, step_index)
        );
    """)
    con.commit()


def replace_dataset(con: sqlite3.Connection, *, dataset_id: str, source_artifact: str, planner_config: dict[str, Any], episodes: list[list[dict[str, Any]]]) -> dict[str, int]:
    create_schema(con)
    rows = [step for episode in episodes for step in episode]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    con.execute("DELETE FROM fantasy_rng_offline_trajectory_steps WHERE dataset_id = ?", (dataset_id,))
    con.execute("DELETE FROM fantasy_rng_offline_trajectory_builds WHERE dataset_id = ?", (dataset_id,))
    con.executemany(
        "INSERT INTO fantasy_rng_offline_trajectory_steps VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(
            dataset_id, int(row["episode_index"]), int(row["step_index"]), int(row["episode_seed"]), row["objective_mode"],
            float(row["state_value_before"]), float(row["state_value_after"]), float(row["final_value"]), float(row["return_to_go"]), float(row["immediate_reward"]),
            int(row["behavior_action_index"]), json.dumps(row["behavior_action"], ensure_ascii=False), json.dumps(row["state_slots"], ensure_ascii=False),
            json.dumps(row["offers"], ensure_ascii=False), json.dumps(row["actor_logits"]), json.dumps(row["actor_probs"]), json.dumps(row["planner_candidates"], ensure_ascii=False), now,
        ) for row in rows],
    )
    con.execute(
        "INSERT INTO fantasy_rng_offline_trajectory_builds VALUES (?, ?, ?, ?, ?, ?, ?)",
        (dataset_id, source_artifact, json.dumps(planner_config, ensure_ascii=False), len(episodes), len(rows), now, "Full planner trajectories with final return and behavior actor probabilities."),
    )
    con.commit()
    return {"episodes": len(episodes), "steps": len(rows)}
