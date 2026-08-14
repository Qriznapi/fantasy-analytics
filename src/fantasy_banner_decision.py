from __future__ import annotations

import itertools
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from fantasy_reliability_foundation import rank_scale_1_100
from project_db import resolve_db_path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = resolve_db_path(PROJECT_ROOT)

RISK_PROFILES: dict[str, dict[str, float]] = {
    "conservative": {
        "predicted_anchor_score": 0.45,
        "p_top5_anchor": 0.25,
        "stability_index": 0.20,
        "rank_strength_index": 0.10,
    },
    "balanced": {
        "predicted_anchor_score": 0.35,
        "p_top3_anchor": 0.20,
        "p90_anchor_score": 0.20,
        "stability_index": 0.15,
        "rank_strength_index": 0.10,
    },
    "aggressive": {
        "predicted_anchor_score": 0.25,
        "p_top1_anchor": 0.30,
        "p90_anchor_score": 0.25,
        "p_top3_anchor": 0.10,
        "rank_strength_index": 0.10,
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS banner_decision_runs (
            run_id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            risk_profile TEXT NOT NULL,
            ti2026_only INTEGER NOT NULL CHECK (ti2026_only IN (0, 1)),
            source_policy TEXT NOT NULL,
            notes TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS banner_decision_entity_scores (
            run_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            risk_profile TEXT NOT NULL,
            entity_key TEXT NOT NULL,
            team_name TEXT NOT NULL,
            official_name TEXT,
            official_position INTEGER,
            role_group TEXT,
            role_slot TEXT,
            player_names TEXT,
            ti2026_qualified INTEGER NOT NULL,
            decision_raw REAL NOT NULL,
            decision_score_1_100 REAL NOT NULL,
            rationale TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, entity_key)
        );

        CREATE TABLE IF NOT EXISTS banner_decision_lineups (
            run_id TEXT NOT NULL,
            risk_profile TEXT NOT NULL,
            lineup_rank INTEGER NOT NULL,
            core_team_name TEXT NOT NULL,
            core_players TEXT NOT NULL,
            core_decision_score REAL NOT NULL,
            mid_team_name TEXT NOT NULL,
            mid_player TEXT NOT NULL,
            mid_decision_score REAL NOT NULL,
            support_team_name TEXT NOT NULL,
            support_players TEXT NOT NULL,
            support_decision_score REAL NOT NULL,
            lineup_raw REAL NOT NULL,
            lineup_score_1_100 REAL NOT NULL,
            rationale TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, lineup_rank)
        );

        DROP VIEW IF EXISTS analytics_banner_decision_players;
        CREATE VIEW analytics_banner_decision_players AS
        SELECT
            d.*,
            CASE WHEN d.run_id LIKE '%::ti2026' THEN 'ti2026' ELSE 'all' END AS decision_scope
        FROM banner_decision_entity_scores d
        WHERE d.entity_type = 'player';

        DROP VIEW IF EXISTS analytics_banner_decision_role_slots;
        CREATE VIEW analytics_banner_decision_role_slots AS
        SELECT
            d.*,
            CASE WHEN d.run_id LIKE '%::ti2026' THEN 'ti2026' ELSE 'all' END AS decision_scope
        FROM banner_decision_entity_scores d
        WHERE d.entity_type = 'role_slot';

        DROP VIEW IF EXISTS analytics_banner_decision_lineups;
        CREATE VIEW analytics_banner_decision_lineups AS
        SELECT
            l.*,
            CASE WHEN l.run_id LIKE '%::ti2026' THEN 'ti2026' ELSE 'all' END AS decision_scope
        FROM banner_decision_lineups l;
        """
    )
    con.commit()


def load_rescoring(con: sqlite3.Connection, entity_type: str, ti2026_only: bool) -> pd.DataFrame:
    scope_pattern = "%::ti2026" if ti2026_only else "%::all"
    return pd.read_sql_query(
        """
        SELECT *
        FROM banner_rescoring_entity_scores
        WHERE entity_type = ?
          AND run_id LIKE ?
        """,
        con,
        params=(entity_type, scope_pattern),
    )


def normalize_high(values: pd.Series) -> pd.Series:
    values = values.astype(float)
    if len(values) <= 1 or values.max() == values.min():
        return pd.Series([1.0] * len(values), index=values.index)
    return (values - values.min()) / (values.max() - values.min())


def decision_frame(source: pd.DataFrame, entity_type: str, risk_profile: str) -> pd.DataFrame:
    if source.empty:
        return source
    weights = RISK_PROFILES[risk_profile]
    df = source.copy()
    segment_col = "role_group" if entity_type == "player" else "role_slot"
    for feature in ["predicted_anchor_score", "p90_anchor_score"]:
        df[f"{feature}_norm"] = 0.0
    for _, idx in df.groupby(segment_col).groups.items():
        df.loc[idx, "predicted_anchor_score_norm"] = normalize_high(df.loc[idx, "predicted_anchor_score"])
        df.loc[idx, "p90_anchor_score_norm"] = normalize_high(df.loc[idx, "p90_anchor_score"])
        raw = pd.Series(0.0, index=idx, dtype=float)
        for feature_name, weight in weights.items():
            column = f"{feature_name}_norm" if f"{feature_name}_norm" in df.columns else feature_name
            raw = raw.add(weight * df.loc[idx, column].astype(float), fill_value=0.0)
        df.loc[idx, "decision_raw"] = raw
        df.loc[idx, "decision_score_1_100"] = rank_scale_1_100(df.loc[idx, "decision_raw"].astype(float))
    df["risk_profile"] = risk_profile
    df["rationale"] = (
        "Risk-profile decision score derived from banner rescoring anchor plus Monte Carlo upside/stability signals."
    )
    return df.sort_values([segment_col, "decision_score_1_100", "decision_raw"], ascending=[True, False, False]).reset_index(drop=True)


def persist_entity_scores(
    con: sqlite3.Connection,
    entity_type: str,
    profile_id: str,
    ti2026_only: bool,
    risk_profile: str,
    frame: pd.DataFrame,
) -> str:
    run_id = f"banner_decision::{entity_type}::{risk_profile}::{'ti2026' if ti2026_only else 'all'}"
    cur = con.cursor()
    cur.execute("DELETE FROM banner_decision_entity_scores WHERE run_id = ?", (run_id,))
    cur.execute("DELETE FROM banner_decision_runs WHERE run_id = ?", (run_id,))
    cur.execute(
        """
        INSERT INTO banner_decision_runs(
            run_id, profile_id, entity_type, risk_profile, ti2026_only, source_policy, notes, created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            profile_id,
            entity_type,
            risk_profile,
            int(ti2026_only),
            "Decision layer over banner rescoring",
            "Practical banner decision layer with conservative, balanced, and aggressive risk profiles.",
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
                    risk_profile,
                    row.entity_key,
                    row.team_name,
                    row.official_name,
                    None if pd.isna(row.official_position) else int(row.official_position),
                    row.role_group,
                    row.role_slot,
                    row.player_names,
                    int(row.ti2026_qualified),
                    float(row.decision_raw),
                    float(row.decision_score_1_100),
                    row.rationale,
                    utc_now(),
                )
            )
        cur.executemany(
            """
            INSERT OR REPLACE INTO banner_decision_entity_scores(
                run_id, entity_type, risk_profile, entity_key, team_name, official_name, official_position,
                role_group, role_slot, player_names, ti2026_qualified, decision_raw, decision_score_1_100,
                rationale, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    con.commit()
    return run_id


def build_lineups(frame: pd.DataFrame, risk_profile: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    core = frame[frame["role_slot"] == "core_pair"].nlargest(8, "decision_raw").copy()
    mid = frame[frame["role_slot"] == "mid_single"].nlargest(8, "decision_raw").copy()
    support = frame[frame["role_slot"] == "support_pair"].nlargest(8, "decision_raw").copy()
    rows: list[dict[str, Any]] = []
    for core_row, mid_row, support_row in itertools.product(core.itertuples(index=False), mid.itertuples(index=False), support.itertuples(index=False)):
        teams = {core_row.team_name, mid_row.team_name, support_row.team_name}
        if len(teams) < 3:
            continue
        lineup_raw = (float(core_row.decision_raw) + float(mid_row.decision_raw) + float(support_row.decision_raw)) / 3.0
        rows.append(
            {
                "risk_profile": risk_profile,
                "core_team_name": core_row.team_name,
                "core_players": core_row.player_names,
                "core_decision_score": float(core_row.decision_score_1_100),
                "mid_team_name": mid_row.team_name,
                "mid_player": mid_row.player_names,
                "mid_decision_score": float(mid_row.decision_score_1_100),
                "support_team_name": support_row.team_name,
                "support_players": support_row.player_names,
                "support_decision_score": float(support_row.decision_score_1_100),
                "lineup_raw": lineup_raw,
                "rationale": "Three-team lineup built from risk-profile role-slot scores with team uniqueness constraint.",
            }
        )
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    result = result.sort_values(["lineup_raw", "core_decision_score", "mid_decision_score", "support_decision_score"], ascending=[False, False, False, False]).reset_index(drop=True)
    result["lineup_score_1_100"] = rank_scale_1_100(result["lineup_raw"].astype(float))
    result["lineup_rank"] = range(1, len(result) + 1)
    return result.head(25).copy()


def persist_lineups(con: sqlite3.Connection, run_id: str, risk_profile: str, lineups: pd.DataFrame) -> None:
    cur = con.cursor()
    cur.execute("DELETE FROM banner_decision_lineups WHERE run_id = ?", (run_id,))
    if not lineups.empty:
        rows = []
        for row in lineups.itertuples(index=False):
            rows.append(
                (
                    run_id,
                    risk_profile,
                    int(row.lineup_rank),
                    row.core_team_name,
                    row.core_players,
                    float(row.core_decision_score),
                    row.mid_team_name,
                    row.mid_player,
                    float(row.mid_decision_score),
                    row.support_team_name,
                    row.support_players,
                    float(row.support_decision_score),
                    float(row.lineup_raw),
                    float(row.lineup_score_1_100),
                    row.rationale,
                    utc_now(),
                )
            )
        cur.executemany(
            """
            INSERT OR REPLACE INTO banner_decision_lineups(
                run_id, risk_profile, lineup_rank, core_team_name, core_players, core_decision_score,
                mid_team_name, mid_player, mid_decision_score, support_team_name, support_players,
                support_decision_score, lineup_raw, lineup_score_1_100, rationale, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    con.commit()


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


def build_banner_decision(db_path: Path = DB_PATH) -> dict[str, Any]:
    con = sqlite3.connect(str(db_path))
    try:
        create_schema(con)
        profile_id = default_profile_id(con)
        run_ids: list[str] = []
        summary_rows: list[dict[str, Any]] = []
        for ti2026_only in (False, True):
            for risk_profile in RISK_PROFILES:
                for entity_type in ("player", "role_slot"):
                    source = load_rescoring(con, entity_type, ti2026_only)
                    frame = decision_frame(source, entity_type, risk_profile)
                    run_id = persist_entity_scores(con, entity_type, profile_id, ti2026_only, risk_profile, frame)
                    run_ids.append(run_id)
                    if entity_type == "role_slot":
                        persist_lineups(con, run_id, risk_profile, build_lineups(frame, risk_profile))
                    summary_rows.append(
                        {
                            "entity_type": entity_type,
                            "ti2026_only": int(ti2026_only),
                            "risk_profile": risk_profile,
                            "rows": int(len(frame)),
                            "avg_decision": float(frame["decision_score_1_100"].mean()) if not frame.empty else 0.0,
                        }
                    )
        return {"profile_id": profile_id, "run_ids": run_ids, "summary": pd.DataFrame(summary_rows)}
    finally:
        con.close()
