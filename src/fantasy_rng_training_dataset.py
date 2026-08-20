from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from fantasy_rng_features import build_training_rows_from_episode_step


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS fantasy_rng_training_builds (
            dataset_id TEXT PRIMARY KEY,
            source_episode_run_id TEXT NOT NULL,
            policy_filter TEXT,
            chosen_only INTEGER NOT NULL,
            row_count INTEGER NOT NULL,
            created_at_utc TEXT NOT NULL,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS fantasy_rng_training_samples (
            dataset_id TEXT NOT NULL,
            source_run_id TEXT NOT NULL,
            policy_name TEXT NOT NULL,
            episode_index INTEGER NOT NULL,
            step_index INTEGER NOT NULL,
            offer_rank_in_set INTEGER NOT NULL,
            offer_action_id TEXT NOT NULL,
            offer_token_type TEXT,
            offer_role_scope TEXT,
            offer_slot_index INTEGER,
            offer_is_chosen INTEGER NOT NULL,
            target_episode_final_value REAL,
            target_future_gain REAL,
            target_realized_delta REAL,
            feature_payload_json TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (dataset_id, policy_name, episode_index, step_index, offer_rank_in_set)
        );

        DROP VIEW IF EXISTS analytics_rng_training_samples;
        CREATE VIEW analytics_rng_training_samples AS
        SELECT s.*
        FROM fantasy_rng_training_samples s
        JOIN fantasy_rng_training_builds b
          ON b.dataset_id = s.dataset_id;
        """
    )


def latest_episode_run_id(con: sqlite3.Connection, profile_id: str | None = None) -> str | None:
    if profile_id:
        row = con.execute(
            """
            SELECT run_id
            FROM fantasy_rng_episode_runs
            WHERE profile_id = ?
            ORDER BY created_at_utc DESC
            LIMIT 1
            """,
            (profile_id,),
        ).fetchone()
    else:
        row = con.execute(
            """
            SELECT run_id
            FROM fantasy_rng_episode_runs
            ORDER BY created_at_utc DESC
            LIMIT 1
            """
        ).fetchone()
    return str(row[0]) if row else None


def build_training_dataset_frame(
    con: sqlite3.Connection,
    *,
    source_episode_run_id: str,
    policy_names: list[str] | None = None,
    chosen_only: bool = False,
) -> pd.DataFrame:
    params: list[Any] = [source_episode_run_id]
    where = ["st.run_id = ?"]
    if policy_names:
        placeholders = ", ".join(["?"] * len(policy_names))
        where.append(f"st.policy_name IN ({placeholders})")
        params.extend(policy_names)
    query = f"""
        SELECT
            st.run_id,
            st.policy_name,
            st.episode_index,
            st.step_index,
            st.steps_remaining_before,
            st.baseline_value_before,
            st.slot_state_before_json,
            st.offer_set_json,
            st.chosen_offer_index,
            st.chosen_action_id,
            st.chosen_token_type,
            st.chosen_role_scope,
            st.chosen_slot_index,
            st.realized_delta,
            su.final_value,
            er.max_steps
        FROM fantasy_rng_episode_steps st
        JOIN fantasy_rng_episode_summaries su
          ON su.run_id = st.run_id
         AND su.policy_name = st.policy_name
         AND su.episode_index = st.episode_index
        JOIN fantasy_rng_episode_runs er
          ON er.run_id = st.run_id
        WHERE {" AND ".join(where)}
        ORDER BY st.policy_name, st.episode_index, st.step_index
    """
    step_df = pd.read_sql_query(query, con, params=params)
    rows: list[dict[str, Any]] = []
    for step_row in step_df.to_dict(orient="records"):
        step_samples = build_training_rows_from_episode_step(
            step_row,
            episode_final_value=float(step_row["final_value"]),
            max_steps=int(step_row["max_steps"]),
        )
        if chosen_only:
            step_samples = [row for row in step_samples if int(row.get("offer_is_chosen", 0)) == 1]
        rows.extend(step_samples)
    return pd.DataFrame(rows)


def persist_training_dataset(
    con: sqlite3.Connection,
    frame: pd.DataFrame,
    *,
    dataset_id: str,
    source_episode_run_id: str,
    policy_filter: str = "",
    chosen_only: bool = False,
    notes: str = "",
) -> None:
    create_schema(con)
    cur = con.cursor()
    cur.execute("DELETE FROM fantasy_rng_training_samples WHERE dataset_id = ?", (dataset_id,))
    cur.execute(
        """
        INSERT OR REPLACE INTO fantasy_rng_training_builds(
            dataset_id, source_episode_run_id, policy_filter, chosen_only, row_count, created_at_utc, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            dataset_id,
            source_episode_run_id,
            policy_filter,
            1 if chosen_only else 0,
            int(len(frame)),
            utc_now(),
            notes,
        ),
    )
    if not frame.empty:
        rows = []
        for item in frame.to_dict(orient="records"):
            rows.append(
                (
                    dataset_id,
                    str(item.get("run_id", "")),
                    str(item.get("policy_name", "")),
                    int(item.get("episode_index", 0)),
                    int(item.get("step_index", 0)),
                    int(item.get("offer_rank_in_set", 0)),
                    str(item.get("offer_action_id", "")),
                    str(item.get("offer_token_type", "")),
                    str(item.get("offer_role_scope", "")),
                    int(item.get("offer_slot_index", 0)),
                    int(item.get("offer_is_chosen", 0)),
                    float(item.get("target_episode_final_value", 0.0)),
                    float(item.get("target_future_gain", 0.0)),
                    float(item.get("target_realized_delta", 0.0)),
                    json.dumps(item, ensure_ascii=False, sort_keys=True),
                    utc_now(),
                )
            )
        cur.executemany(
            """
            INSERT OR REPLACE INTO fantasy_rng_training_samples(
                dataset_id, source_run_id, policy_name, episode_index, step_index, offer_rank_in_set,
                offer_action_id, offer_token_type, offer_role_scope, offer_slot_index, offer_is_chosen,
                target_episode_final_value, target_future_gain, target_realized_delta, feature_payload_json, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    con.commit()


def build_and_persist_training_dataset(
    db_path: Path,
    *,
    source_episode_run_id: str,
    policy_names: list[str] | None = None,
    chosen_only: bool = False,
) -> tuple[str, pd.DataFrame]:
    dataset_id = f"rng_train::{source_episode_run_id}::{'chosen' if chosen_only else 'offers'}"
    con = sqlite3.connect(str(db_path))
    try:
        frame = build_training_dataset_frame(
            con,
            source_episode_run_id=source_episode_run_id,
            policy_names=policy_names,
            chosen_only=chosen_only,
        )
        persist_training_dataset(
            con,
            frame,
            dataset_id=dataset_id,
            source_episode_run_id=source_episode_run_id,
            policy_filter=",".join(policy_names or []),
            chosen_only=chosen_only,
            notes="Expanded offer-level dataset from RNG episode trajectories with state + offer features.",
        )
    finally:
        con.close()
    return dataset_id, frame
