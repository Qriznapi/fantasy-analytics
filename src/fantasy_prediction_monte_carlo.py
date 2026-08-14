from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from fantasy_prediction_foundation import DB_PATH, create_schema, utc_now


DEFAULT_SIMULATIONS = 4000
DEFAULT_SEED = 20260812


def create_monte_carlo_schema(con: sqlite3.Connection) -> None:
    create_schema(con)
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS production_monte_carlo_runs (
            run_id TEXT PRIMARY KEY,
            target_id TEXT NOT NULL,
            split_name TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            simulations INTEGER NOT NULL,
            seed INTEGER NOT NULL,
            notes TEXT,
            created_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS production_monte_carlo_entity_results (
            run_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            split_name TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_key TEXT NOT NULL,
            team_name TEXT NOT NULL,
            official_name TEXT,
            official_position INTEGER,
            role_group TEXT,
            role_slot TEXT,
            player_names TEXT,
            segment_key TEXT NOT NULL,
            predicted_score REAL NOT NULL,
            simulated_mean_score REAL NOT NULL,
            simulated_std_score REAL NOT NULL,
            p_top1 REAL NOT NULL,
            p_top3 REAL NOT NULL,
            p_top5 REAL NOT NULL,
            expected_rank REAL NOT NULL,
            p_above_segment_mean REAL NOT NULL,
            p90_sim_score REAL NOT NULL,
            ti2026_qualified INTEGER NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, entity_key)
        );

        DROP VIEW IF EXISTS analytics_prediction_monte_carlo_players;
        CREATE VIEW analytics_prediction_monte_carlo_players AS
        SELECT *
        FROM production_monte_carlo_entity_results
        WHERE entity_type = 'player';

        DROP VIEW IF EXISTS analytics_prediction_monte_carlo_role_slots;
        CREATE VIEW analytics_prediction_monte_carlo_role_slots AS
        SELECT *
        FROM production_monte_carlo_entity_results
        WHERE entity_type = 'role_slot';
        """
    )
    con.commit()


def uncertainty_sigma(frame: pd.DataFrame) -> pd.Series:
    if {"q25", "q75"}.issubset(frame.columns):
        band = frame["q75"].astype(float) - frame["q25"].astype(float)
        sigma = band / 1.349
        sigma = sigma.where(np.isfinite(sigma) & (sigma > 0), np.nan)
    else:
        sigma = pd.Series(np.nan, index=frame.index)
    fallback = frame["metric_mae"].astype(float).clip(lower=250.0) * 0.80
    return sigma.fillna(fallback).clip(lower=250.0)


def simulate_segment(
    block: pd.DataFrame,
    simulations: int,
    rng: np.random.Generator,
) -> pd.DataFrame:
    means = block["predicted_score"].astype(float).to_numpy()
    sigmas = block["sigma"].astype(float).to_numpy()
    draws = rng.normal(loc=means, scale=sigmas, size=(simulations, len(block)))
    ranks = np.argsort(np.argsort(-draws, axis=1), axis=1) + 1
    segment_means = draws.mean(axis=1, keepdims=True)
    rows: list[dict[str, Any]] = []
    for idx, (_, row) in enumerate(block.iterrows()):
        sim_scores = draws[:, idx]
        sim_ranks = ranks[:, idx]
        rows.append(
            {
                "entity_key": row["entity_key"],
                "simulated_mean_score": float(np.mean(sim_scores)),
                "simulated_std_score": float(np.std(sim_scores)),
                "p_top1": float(np.mean(sim_ranks <= 1)),
                "p_top3": float(np.mean(sim_ranks <= min(3, len(block)))),
                "p_top5": float(np.mean(sim_ranks <= min(5, len(block)))),
                "expected_rank": float(np.mean(sim_ranks)),
                "p_above_segment_mean": float(np.mean(sim_scores > segment_means[:, 0])),
                "p90_sim_score": float(np.percentile(sim_scores, 90.0)),
            }
        )
    return pd.DataFrame(rows)


def build_prediction_monte_carlo(
    db_path: Path = DB_PATH,
    simulations: int = DEFAULT_SIMULATIONS,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    con = sqlite3.connect(str(db_path))
    try:
        create_monte_carlo_schema(con)
        con.execute("DELETE FROM production_monte_carlo_entity_results")
        con.execute("DELETE FROM production_monte_carlo_runs")
        con.commit()

        players = pd.read_sql_query(
            """
            SELECT p.*,
                   CASE WHEN EXISTS (
                       SELECT 1 FROM analytics_ti2026_teams t
                       WHERE t.team_name = p.team_name
                         AND t.has_ewc_player_data = 1
                   ) THEN 1 ELSE 0 END AS ti2026_qualified
            FROM analytics_prediction_production_players p
            """,
            con,
        )
        slots = pd.read_sql_query(
            """
            SELECT s.*,
                   CASE WHEN EXISTS (
                       SELECT 1 FROM analytics_ti2026_teams t
                       WHERE t.team_name = s.team_name
                         AND t.has_ewc_player_data = 1
                   ) THEN 1 ELSE 0 END AS ti2026_qualified
            FROM analytics_prediction_production_role_slots s
            """,
            con,
        )
        rows_written = 0
        run_rows = []
        result_rows = []
        rng = np.random.default_rng(seed)
        for entity_type, frame, segcol in [
            ("player", players, "role_group"),
            ("role_slot", slots, "role_slot"),
        ]:
            if frame.empty:
                continue
            frame = frame.copy()
            frame["sigma"] = uncertainty_sigma(frame)
            for (target_id, split_name), target_block in frame.groupby(["target_id", "split_name"], sort=False):
                run_id = f"monte_carlo::{entity_type}::{target_id}::{split_name}"
                run_rows.append(
                    (
                        run_id,
                        target_id,
                        split_name,
                        entity_type,
                        int(simulations),
                        int(seed),
                        "Monte Carlo simulation over production prediction scores using normal draws with q-band or MAE-based uncertainty scale.",
                        utc_now(),
                    )
                )
                for segment_key, segment_block in target_block.groupby(segcol, sort=False):
                    sim = simulate_segment(segment_block, simulations, rng)
                    merged = segment_block.merge(sim, on="entity_key", how="left")
                    for row in merged.itertuples(index=False):
                        result_rows.append(
                            (
                                run_id,
                                target_id,
                                split_name,
                                entity_type,
                                row.entity_key,
                                row.team_name,
                                getattr(row, "official_name", None),
                                None if pd.isna(getattr(row, "official_position", None)) else int(row.official_position),
                                getattr(row, "role_group", None),
                                getattr(row, "role_slot", None),
                                getattr(row, "player_names", None),
                                str(segment_key),
                                float(row.predicted_score),
                                float(row.simulated_mean_score),
                                float(row.simulated_std_score),
                                float(row.p_top1),
                                float(row.p_top3),
                                float(row.p_top5),
                                float(row.expected_rank),
                                float(row.p_above_segment_mean),
                                float(row.p90_sim_score),
                                int(row.ti2026_qualified),
                                utc_now(),
                            )
                        )
                        rows_written += 1
        con.executemany(
            """
            INSERT INTO production_monte_carlo_runs(
                run_id, target_id, split_name, entity_type, simulations, seed, notes, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            run_rows,
        )
        con.executemany(
            """
            INSERT INTO production_monte_carlo_entity_results(
                run_id, target_id, split_name, entity_type, entity_key, team_name, official_name,
                official_position, role_group, role_slot, player_names, segment_key, predicted_score,
                simulated_mean_score, simulated_std_score, p_top1, p_top3, p_top5, expected_rank,
                p_above_segment_mean, p90_sim_score, ti2026_qualified, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            result_rows,
        )
        con.commit()
        summary = pd.read_sql_query(
            """
            SELECT target_id, split_name, entity_type, segment_key,
                   COUNT(*) AS entities,
                   AVG(p_top1) AS avg_p_top1,
                   AVG(p_top3) AS avg_p_top3,
                   AVG(simulated_std_score) AS avg_sim_std
            FROM production_monte_carlo_entity_results
            GROUP BY target_id, split_name, entity_type, segment_key
            ORDER BY target_id, split_name, entity_type, segment_key
            """,
            con,
        )
        return {"rows_written": rows_written, "summary": summary}
    finally:
        con.close()
