from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from fantasy_reliability_foundation import rank_scale_1_100
from project_db import resolve_db_path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = resolve_db_path(PROJECT_ROOT)

TARGET_WEIGHTS = {
    "player_map_score": 0.20,
    "player_series_mean": 0.25,
    "player_series_top1": 0.55,
    "role_slot_map_score": 0.20,
    "role_slot_series_mean": 0.25,
    "role_slot_series_top1": 0.55,
}
SPLIT_WEIGHTS = {
    "group_to_playoff": 0.40,
    "temporal_60_40": 0.60,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS banner_rescoring_runs (
            run_id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            ti2026_only INTEGER NOT NULL CHECK (ti2026_only IN (0, 1)),
            source_policy TEXT NOT NULL,
            notes TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS banner_rescoring_entity_scores (
            run_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_key TEXT NOT NULL,
            team_name TEXT NOT NULL,
            official_name TEXT,
            official_position INTEGER,
            role_group TEXT,
            role_slot TEXT,
            player_names TEXT,
            ti2026_qualified INTEGER NOT NULL,
            profile_id TEXT NOT NULL,
            predicted_anchor_score REAL NOT NULL,
            p90_anchor_score REAL NOT NULL,
            p_top1_anchor REAL NOT NULL,
            p_top3_anchor REAL NOT NULL,
            p_top5_anchor REAL NOT NULL,
            expected_rank_anchor REAL NOT NULL,
            stability_index REAL NOT NULL,
            rank_strength_index REAL NOT NULL,
            surface_quality_index REAL NOT NULL,
            rescore_raw REAL NOT NULL,
            rescore_score_1_100 REAL NOT NULL,
            target_mix_notes TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, entity_key)
        );

        DROP VIEW IF EXISTS analytics_banner_rescoring_players;
        CREATE VIEW analytics_banner_rescoring_players AS
        SELECT
            s.*,
            CASE WHEN s.run_id LIKE '%::ti2026' THEN 'ti2026' ELSE 'all' END AS rescoring_scope
        FROM banner_rescoring_entity_scores s
        WHERE s.entity_type = 'player';

        DROP VIEW IF EXISTS analytics_banner_rescoring_role_slots;
        CREATE VIEW analytics_banner_rescoring_role_slots AS
        SELECT
            s.*,
            CASE WHEN s.run_id LIKE '%::ti2026' THEN 'ti2026' ELSE 'all' END AS rescoring_scope
        FROM banner_rescoring_entity_scores s
        WHERE s.entity_type = 'role_slot';
        """
    )
    con.commit()


def load_source(con: sqlite3.Connection, entity_type: str, ti2026_only: bool) -> pd.DataFrame:
    prod_view = "analytics_prediction_production_players" if entity_type == "player" else "analytics_prediction_production_role_slots"
    mc_view = "analytics_prediction_monte_carlo_players" if entity_type == "player" else "analytics_prediction_monte_carlo_role_slots"
    prod = pd.read_sql_query(f"SELECT * FROM {prod_view}", con)
    mc = pd.read_sql_query(f"SELECT * FROM {mc_view}", con)
    if ti2026_only:
        prod = prod[prod["team_name"].notna()].copy()
        mc = mc[mc["ti2026_qualified"] == 1].copy()
    if ti2026_only and "official_name" in prod.columns:
        prod = prod.merge(
            mc[["entity_key", "target_id", "split_name", "ti2026_qualified"]].drop_duplicates(),
            on=["entity_key", "target_id", "split_name"],
            how="left",
        )
        prod = prod[prod["ti2026_qualified"].fillna(0).astype(int) == 1].copy()
    merged = prod.merge(
        mc[
            [
                "entity_key",
                "target_id",
                "split_name",
                "simulated_std_score",
                "p_top1",
                "p_top3",
                "p_top5",
                "expected_rank",
                "p90_sim_score",
                "ti2026_qualified",
            ]
        ],
        on=["entity_key", "target_id", "split_name"],
        how="left",
    )
    merged["target_weight"] = merged["target_id"].map(TARGET_WEIGHTS).fillna(0.0)
    merged["split_weight"] = merged["split_name"].map(SPLIT_WEIGHTS).fillna(0.0)
    merged["combined_weight"] = merged["target_weight"] * merged["split_weight"]
    merged["surface_quality"] = 0.55 * merged["metric_entity_spearman"].astype(float) + 0.45 * merged["metric_ndcg_5"].astype(float)
    return merged[merged["combined_weight"] > 0].copy()


def weighted_average(values: pd.Series, weights: pd.Series) -> float:
    frame = pd.DataFrame({"value": values, "weight": weights}).dropna()
    if frame.empty or frame["weight"].sum() <= 0:
        return 0.0
    return float((frame["value"].astype(float) * frame["weight"].astype(float)).sum() / frame["weight"].astype(float).sum())


def aggregate_entity_scores(source: pd.DataFrame, entity_type: str, profile_id: str) -> pd.DataFrame:
    if source.empty:
        return source
    rows: list[dict[str, Any]] = []
    group_cols = ["entity_key", "team_name"]
    for _, block in source.groupby(group_cols, sort=False):
        first = block.iloc[0]
        weights = block["combined_weight"].astype(float)
        row = {
            "entity_type": entity_type,
            "entity_key": first["entity_key"],
            "team_name": first["team_name"],
            "official_name": first.get("official_name"),
            "official_position": first.get("official_position"),
            "role_group": first.get("role_group"),
            "role_slot": first.get("role_slot"),
            "player_names": first.get("player_names"),
            "ti2026_qualified": int(block.get("ti2026_qualified", pd.Series([0])).fillna(0).astype(int).max()),
            "profile_id": profile_id,
            "predicted_anchor_score": weighted_average(block["predicted_score"], weights),
            "p90_anchor_score": weighted_average(block["p90_sim_score"].fillna(block["predicted_score"]), weights),
            "p_top1_anchor": weighted_average(block["p_top1"].fillna(0.0), weights),
            "p_top3_anchor": weighted_average(block["p_top3"].fillna(0.0), weights),
            "p_top5_anchor": weighted_average(block["p_top5"].fillna(0.0), weights),
            "expected_rank_anchor": weighted_average(block["expected_rank"].fillna(0.0), weights),
            "simulated_std_anchor": weighted_average(block["simulated_std_score"].fillna(0.0), weights),
            "surface_quality_index": weighted_average(block["surface_quality"], weights),
            "target_mix_notes": "0.20 map + 0.25 series_mean + 0.55 series_top1, with split weights 0.40 group_to_playoff + 0.60 temporal_60_40.",
        }
        rows.append(row)
    frame = pd.DataFrame(rows)
    segment_col = "role_group" if entity_type == "player" else "role_slot"
    frame["predicted_rank_index"] = 0.0
    frame["p90_rank_index"] = 0.0
    frame["stability_index"] = 0.0
    frame["rank_strength_index"] = 0.0
    frame["rescore_raw"] = 0.0
    frame["rescore_score_1_100"] = 1.0
    for _, idx in frame.groupby(segment_col).groups.items():
        block = frame.loc[idx].copy()
        frame.loc[idx, "predicted_rank_index"] = normalize_high(block["predicted_anchor_score"])
        frame.loc[idx, "p90_rank_index"] = normalize_high(block["p90_anchor_score"])
        frame.loc[idx, "stability_index"] = normalize_low(block["simulated_std_anchor"])
        frame.loc[idx, "rank_strength_index"] = normalize_low(block["expected_rank_anchor"])
        frame.loc[idx, "rescore_raw"] = (
            0.40 * frame.loc[idx, "predicted_rank_index"].astype(float)
            + 0.20 * frame.loc[idx, "p90_rank_index"].astype(float)
            + 0.15 * frame.loc[idx, "p_top3_anchor"].astype(float)
            + 0.10 * frame.loc[idx, "stability_index"].astype(float)
            + 0.10 * frame.loc[idx, "rank_strength_index"].astype(float)
            + 0.05 * frame.loc[idx, "surface_quality_index"].astype(float)
        )
        frame.loc[idx, "rescore_score_1_100"] = rank_scale_1_100(frame.loc[idx, "rescore_raw"].astype(float))
    return frame.sort_values([segment_col, "rescore_score_1_100", "rescore_raw"], ascending=[True, False, False]).reset_index(drop=True)


def normalize_high(values: pd.Series) -> pd.Series:
    values = values.astype(float)
    if len(values) <= 1 or values.max() == values.min():
        return pd.Series([1.0] * len(values), index=values.index)
    return (values - values.min()) / (values.max() - values.min())


def normalize_low(values: pd.Series) -> pd.Series:
    values = values.astype(float)
    if len(values) <= 1 or values.max() == values.min():
        return pd.Series([1.0] * len(values), index=values.index)
    return 1.0 - (values - values.min()) / (values.max() - values.min())


def persist(con: sqlite3.Connection, entity_type: str, profile_id: str, ti2026_only: bool, frame: pd.DataFrame) -> str:
    run_id = f"banner_rescoring::{entity_type}::{'ti2026' if ti2026_only else 'all'}"
    cur = con.cursor()
    cur.execute("DELETE FROM banner_rescoring_entity_scores WHERE run_id = ?", (run_id,))
    cur.execute("DELETE FROM banner_rescoring_runs WHERE run_id = ?", (run_id,))
    cur.execute(
        """
        INSERT INTO banner_rescoring_runs(
            run_id, profile_id, entity_type, ti2026_only, source_policy, notes, created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            profile_id,
            entity_type,
            int(ti2026_only),
            "Weighted production prediction + weighted Monte Carlo diagnostics",
            "Banner rescoring layer built on top of production prediction and Monte Carlo surfaces.",
            utc_now(),
        ),
    )
    if not frame.empty:
        rows = []
        for row in frame.itertuples(index=False):
            rows.append(
                (
                    run_id,
                    entity_type,
                    row.entity_key,
                    row.team_name,
                    row.official_name,
                    None if pd.isna(row.official_position) else int(row.official_position),
                    row.role_group,
                    row.role_slot,
                    row.player_names,
                    int(row.ti2026_qualified),
                    row.profile_id,
                    float(row.predicted_anchor_score),
                    float(row.p90_anchor_score),
                    float(row.p_top1_anchor),
                    float(row.p_top3_anchor),
                    float(row.p_top5_anchor),
                    float(row.expected_rank_anchor),
                    float(row.stability_index),
                    float(row.rank_strength_index),
                    float(row.surface_quality_index),
                    float(row.rescore_raw),
                    float(row.rescore_score_1_100),
                    row.target_mix_notes,
                    utc_now(),
                )
            )
        cur.executemany(
            """
            INSERT OR REPLACE INTO banner_rescoring_entity_scores(
                run_id, entity_type, entity_key, team_name, official_name, official_position, role_group,
                role_slot, player_names, ti2026_qualified, profile_id, predicted_anchor_score,
                p90_anchor_score, p_top1_anchor, p_top3_anchor, p_top5_anchor, expected_rank_anchor,
                stability_index, rank_strength_index, surface_quality_index, rescore_raw,
                rescore_score_1_100, target_mix_notes, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    con.commit()
    return run_id


def default_profile_id(con: sqlite3.Connection) -> str:
    row = con.execute(
        """
        SELECT profile_id
        FROM fantasy_scoring_profiles
        WHERE is_default = 1
        LIMIT 1
        """
    ).fetchone()
    if not row:
        raise RuntimeError("No default fantasy profile")
    return str(row[0])


def build_banner_rescoring(db_path: Path = DB_PATH) -> dict[str, Any]:
    con = sqlite3.connect(str(db_path))
    try:
        create_schema(con)
        profile_id = default_profile_id(con)
        run_ids: list[str] = []
        summary_rows: list[dict[str, Any]] = []
        for ti2026_only in (False, True):
            for entity_type in ("player", "role_slot"):
                source = load_source(con, entity_type, ti2026_only)
                frame = aggregate_entity_scores(source, entity_type, profile_id)
                run_id = persist(con, entity_type, profile_id, ti2026_only, frame)
                run_ids.append(run_id)
                summary_rows.append(
                    {
                        "entity_type": entity_type,
                        "ti2026_only": int(ti2026_only),
                        "rows": int(len(frame)),
                        "avg_rescore": float(frame["rescore_score_1_100"].mean()) if not frame.empty else 0.0,
                        "avg_p_top3": float(frame["p_top3_anchor"].mean()) if not frame.empty else 0.0,
                    }
                )
        return {"profile_id": profile_id, "run_ids": run_ids, "summary": pd.DataFrame(summary_rows)}
    finally:
        con.close()
