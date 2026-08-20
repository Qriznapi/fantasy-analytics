from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from project_db import resolve_db_path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = resolve_db_path(PROJECT_ROOT, event_id="ti2026")

ROLE_SLOT_MAP = {
    "core_avg": "core_pair",
    "mid": "mid_single",
    "support_avg": "support_pair",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
    except Exception:
        return default
    if math.isnan(value):
        return default
    return value


def percentile(values: list[float], q: float) -> float:
    values = sorted(safe_float(v) for v in values if v is not None)
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    pos = (len(values) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return values[lo]
    return values[lo] * (hi - pos) + values[hi] * (pos - lo)


def std_population(values: list[float]) -> float:
    values = [safe_float(v) for v in values if v is not None]
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def top_mean(values: list[float], n: int) -> float:
    values = sorted((safe_float(v) for v in values if v is not None), reverse=True)
    if not values:
        return 0.0
    return sum(values[:n]) / min(n, len(values))


def rank_scale_1_100(values: pd.Series) -> pd.Series:
    if len(values) == 0:
        return values
    if len(values) == 1:
        return pd.Series([100.0], index=values.index)
    ranks = values.rank(method="average", ascending=True)
    return (1.0 + 99.0 * (ranks - 1.0) / (len(values) - 1.0)).round(2)


def feature_block(values: list[float]) -> dict[str, float]:
    values = [safe_float(v) for v in values if v is not None]
    if not values:
        return {
            "rows_seen": 0.0,
            "avg_score": 0.0,
            "p75_score": 0.0,
            "p90_score": 0.0,
            "best_score": 0.0,
            "floor_score": 0.0,
            "std_score": 0.0,
            "top2_avg": 0.0,
            "ceiling_gap": 0.0,
            "consistency_ratio": 0.0,
            "value_raw": 0.0,
        }
    desc = sorted(values, reverse=True)
    best = desc[0]
    second = desc[1] if len(desc) > 1 else best
    avg = sum(values) / len(values)
    p75 = percentile(values, 0.75)
    p90 = percentile(values, 0.90)
    floor = min(values)
    std = std_population(values)
    top2 = top_mean(values, 2)
    ceiling_gap = max(0.0, best - p75)
    consistency_ratio = p75 / best if best > 0 else 0.0
    raw = (
        0.32 * p75
        + 0.24 * avg
        + 0.16 * p90
        + 0.12 * best
        + 0.08 * top2
        + 0.08 * floor
        - 0.10 * std
        - 0.06 * ceiling_gap
    )
    return {
        "rows_seen": float(len(values)),
        "avg_score": avg,
        "p75_score": p75,
        "p90_score": p90,
        "best_score": best,
        "floor_score": floor,
        "std_score": std,
        "top2_avg": top2,
        "ceiling_gap": ceiling_gap,
        "consistency_ratio": consistency_ratio,
        "value_raw": max(0.0, raw),
    }


def create_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS fantasy_complex_banner_runs (
            run_id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            event_id TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            ti2026_only INTEGER NOT NULL CHECK (ti2026_only IN (0, 1)),
            source_notes TEXT
        );

        CREATE TABLE IF NOT EXISTS fantasy_complex_banner_player_scores (
            run_id TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            event_id TEXT NOT NULL,
            account_id INTEGER NOT NULL,
            team_name TEXT NOT NULL,
            official_name TEXT NOT NULL,
            official_position INTEGER NOT NULL,
            role_group TEXT NOT NULL,
            maps_seen INTEGER NOT NULL,
            series_seen INTEGER NOT NULL,
            avg_map_score REAL NOT NULL,
            p75_map_score REAL NOT NULL,
            p90_map_score REAL NOT NULL,
            best_map_score REAL NOT NULL,
            avg_series_score REAL NOT NULL,
            p75_series_score REAL NOT NULL,
            p90_series_score REAL NOT NULL,
            best_series_score REAL NOT NULL,
            floor_series_score REAL NOT NULL,
            std_series_score REAL NOT NULL,
            consistency_ratio REAL NOT NULL,
            value_raw REAL NOT NULL,
            value_score_1_100 REAL NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, account_id, team_name)
        );

        CREATE TABLE IF NOT EXISTS fantasy_complex_banner_role_scores (
            run_id TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            event_id TEXT NOT NULL,
            role_slot TEXT NOT NULL,
            team_name TEXT NOT NULL,
            player_names TEXT NOT NULL,
            account_ids TEXT NOT NULL,
            maps_seen INTEGER NOT NULL,
            series_seen INTEGER NOT NULL,
            avg_map_score REAL NOT NULL,
            p75_map_score REAL NOT NULL,
            p90_map_score REAL NOT NULL,
            best_map_score REAL NOT NULL,
            avg_series_score REAL NOT NULL,
            p75_series_score REAL NOT NULL,
            p90_series_score REAL NOT NULL,
            best_series_score REAL NOT NULL,
            floor_series_score REAL NOT NULL,
            std_series_score REAL NOT NULL,
            consistency_ratio REAL NOT NULL,
            value_raw REAL NOT NULL,
            value_score_1_100 REAL NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, role_slot, team_name)
        );

        CREATE TABLE IF NOT EXISTS fantasy_complex_banner_lineup_scores (
            run_id TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            event_id TEXT NOT NULL,
            lineup_rank INTEGER NOT NULL,
            core_team TEXT NOT NULL,
            core_players TEXT NOT NULL,
            mid_team TEXT NOT NULL,
            mid_players TEXT NOT NULL,
            support_team TEXT NOT NULL,
            support_players TEXT NOT NULL,
            lineup_value_raw REAL NOT NULL,
            lineup_score_1_100 REAL NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, lineup_rank)
        );
        """
    )


def rebuild_views(con: sqlite3.Connection) -> None:
    cur = con.cursor()
    cur.execute("DROP VIEW IF EXISTS analytics_complex_banner_scores_players")
    cur.execute(
        """
        CREATE VIEW analytics_complex_banner_scores_players AS
        SELECT p.*
        FROM fantasy_complex_banner_player_scores p
        JOIN (
            SELECT profile_id, MAX(created_at_utc) AS created_at_utc
            FROM fantasy_complex_banner_runs
            GROUP BY profile_id
        ) latest
          ON latest.profile_id = p.profile_id
        JOIN fantasy_complex_banner_runs r
          ON r.run_id = p.run_id
         AND r.created_at_utc = latest.created_at_utc
        """
    )
    cur.execute("DROP VIEW IF EXISTS analytics_complex_banner_scores_role_slots")
    cur.execute(
        """
        CREATE VIEW analytics_complex_banner_scores_role_slots AS
        SELECT s.*
        FROM fantasy_complex_banner_role_scores s
        JOIN (
            SELECT profile_id, MAX(created_at_utc) AS created_at_utc
            FROM fantasy_complex_banner_runs
            GROUP BY profile_id
        ) latest
          ON latest.profile_id = s.profile_id
        JOIN fantasy_complex_banner_runs r
          ON r.run_id = s.run_id
         AND r.created_at_utc = latest.created_at_utc
        """
    )
    cur.execute("DROP VIEW IF EXISTS analytics_complex_banner_scores_lineups")
    cur.execute(
        """
        CREATE VIEW analytics_complex_banner_scores_lineups AS
        SELECT l.*
        FROM fantasy_complex_banner_lineup_scores l
        JOIN (
            SELECT profile_id, MAX(created_at_utc) AS created_at_utc
            FROM fantasy_complex_banner_runs
            GROUP BY profile_id
        ) latest
          ON latest.profile_id = l.profile_id
        JOIN fantasy_complex_banner_runs r
          ON r.run_id = l.run_id
         AND r.created_at_utc = latest.created_at_utc
        """
    )


def _default_complex_profile_id(con: sqlite3.Connection) -> str:
    row = con.execute(
        """
        SELECT profile_id
        FROM fantasy_banner_instances
        WHERE event_id = 'ti2026'
        ORDER BY updated_at_utc DESC, profile_id DESC
        LIMIT 1
        """
    ).fetchone()
    if not row:
        raise RuntimeError("No complex banner profile found in fantasy_banner_instances.")
    return str(row[0])


def _player_maps(con: sqlite3.Connection, profile_id: str, ti2026_only: bool) -> pd.DataFrame:
    ti_join = (
        "JOIN analytics_ti2026_teams ti ON ti.team_name = s.team_name"
        if ti2026_only
        else "LEFT JOIN analytics_ti2026_teams ti ON ti.team_name = s.team_name"
    )
    return pd.read_sql_query(
        f"""
        SELECT
            s.profile_id,
            s.match_id,
            s.match_date,
            COALESCE(CAST(s.series_id AS TEXT), 'match:' || CAST(s.match_id AS TEXT)) AS series_key,
            s.account_id,
            s.team_name,
            s.official_name,
            s.official_position,
            s.role_group,
            s.fantasy_score
        FROM fantasy_player_map_scores s
        {ti_join}
        WHERE s.profile_id = ?
          AND s.official_position BETWEEN 1 AND 5
        """,
        con,
        params=(profile_id,),
    )


def _player_series(map_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (account_id, team_name, official_name, official_position, role_group, series_key), group in map_df.groupby(
        ["account_id", "team_name", "official_name", "official_position", "role_group", "series_key"],
        sort=False,
    ):
        top2 = group["fantasy_score"].sort_values(ascending=False).head(2).sum()
        rows.append(
            {
                "account_id": int(account_id),
                "team_name": team_name,
                "official_name": official_name,
                "official_position": int(official_position),
                "role_group": role_group,
                "series_key": series_key,
                "series_score": float(top2),
            }
        )
    return pd.DataFrame(rows)


def _role_maps(con: sqlite3.Connection, profile_id: str, ti2026_only: bool) -> pd.DataFrame:
    ti_join = (
        "JOIN analytics_ti2026_teams ti ON ti.team_name = s.team_name"
        if ti2026_only
        else "LEFT JOIN analytics_ti2026_teams ti ON ti.team_name = s.team_name"
    )
    raw = pd.read_sql_query(
        f"""
        SELECT
            s.profile_id,
            s.match_id,
            s.match_date,
            COALESCE(CAST(m.series_id AS TEXT), 'match:' || CAST(s.match_id AS TEXT)) AS series_key,
            s.team_name,
            s.role_category,
            s.player_names,
            s.account_ids,
            s.role_category_fantasy_score
        FROM fantasy_team_role_map_scores s
        JOIN matches m
          ON m.match_id = s.match_id
        {ti_join}
        WHERE s.profile_id = ?
          AND s.role_category IN ('core_avg', 'mid', 'support_avg')
        """,
        con,
        params=(profile_id,),
    )
    raw["role_slot"] = raw["role_category"].map(ROLE_SLOT_MAP)
    return raw


def _role_series(role_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (role_slot, team_name, player_names, account_ids, series_key), group in role_df.groupby(
        ["role_slot", "team_name", "player_names", "account_ids", "series_key"],
        sort=False,
    ):
        top2 = group["role_category_fantasy_score"].sort_values(ascending=False).head(2).sum()
        rows.append(
            {
                "role_slot": role_slot,
                "team_name": team_name,
                "player_names": player_names,
                "account_ids": account_ids,
                "series_key": series_key,
                "series_score": float(top2),
            }
        )
    return pd.DataFrame(rows)


def _summarize_player_scores(map_df: pd.DataFrame, series_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (account_id, team_name, official_name, official_position, role_group), group in map_df.groupby(
        ["account_id", "team_name", "official_name", "official_position", "role_group"],
        sort=False,
    ):
        map_scores = group["fantasy_score"].astype(float).tolist()
        series_scores = (
            series_df[
                (series_df["account_id"] == account_id)
                & (series_df["team_name"] == team_name)
            ]["series_score"].astype(float).tolist()
        )
        map_block = feature_block(map_scores)
        series_block = feature_block(series_scores)
        rows.append(
            {
                "account_id": int(account_id),
                "team_name": team_name,
                "official_name": official_name,
                "official_position": int(official_position),
                "role_group": role_group,
                "maps_seen": int(len(map_scores)),
                "series_seen": int(len(series_scores)),
                "avg_map_score": round(map_block["avg_score"], 2),
                "p75_map_score": round(map_block["p75_score"], 2),
                "p90_map_score": round(map_block["p90_score"], 2),
                "best_map_score": round(map_block["best_score"], 2),
                "avg_series_score": round(series_block["avg_score"], 2),
                "p75_series_score": round(series_block["p75_score"], 2),
                "p90_series_score": round(series_block["p90_score"], 2),
                "best_series_score": round(series_block["best_score"], 2),
                "floor_series_score": round(series_block["floor_score"], 2),
                "std_series_score": round(series_block["std_score"], 2),
                "consistency_ratio": round(series_block["consistency_ratio"], 4),
                "value_raw": round(series_block["value_raw"], 4),
            }
        )
    out = pd.DataFrame(rows)
    if not out.empty:
        out["value_score_1_100"] = rank_scale_1_100(out["value_raw"]).round(2)
    return out.sort_values(
        ["value_score_1_100", "p75_series_score", "best_series_score"],
        ascending=False,
    ).reset_index(drop=True)


def _summarize_role_scores(role_df: pd.DataFrame, series_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (role_slot, team_name, player_names, account_ids), group in role_df.groupby(
        ["role_slot", "team_name", "player_names", "account_ids"],
        sort=False,
    ):
        map_scores = group["role_category_fantasy_score"].astype(float).tolist()
        series_scores = (
            series_df[
                (series_df["role_slot"] == role_slot)
                & (series_df["team_name"] == team_name)
            ]["series_score"].astype(float).tolist()
        )
        map_block = feature_block(map_scores)
        series_block = feature_block(series_scores)
        rows.append(
            {
                "role_slot": role_slot,
                "team_name": team_name,
                "player_names": player_names,
                "account_ids": account_ids,
                "maps_seen": int(len(map_scores)),
                "series_seen": int(len(series_scores)),
                "avg_map_score": round(map_block["avg_score"], 2),
                "p75_map_score": round(map_block["p75_score"], 2),
                "p90_map_score": round(map_block["p90_score"], 2),
                "best_map_score": round(map_block["best_score"], 2),
                "avg_series_score": round(series_block["avg_score"], 2),
                "p75_series_score": round(series_block["p75_score"], 2),
                "p90_series_score": round(series_block["p90_score"], 2),
                "best_series_score": round(series_block["best_score"], 2),
                "floor_series_score": round(series_block["floor_score"], 2),
                "std_series_score": round(series_block["std_score"], 2),
                "consistency_ratio": round(series_block["consistency_ratio"], 4),
                "value_raw": round(series_block["value_raw"], 4),
            }
        )
    out = pd.DataFrame(rows)
    if not out.empty:
        out["value_score_1_100"] = rank_scale_1_100(out["value_raw"]).round(2)
    return out.sort_values(
        ["role_slot", "value_score_1_100", "p75_series_score", "best_series_score"],
        ascending=[True, False, False, False],
    ).reset_index(drop=True)


def _build_lineups(role_df: pd.DataFrame, top_k_per_role: int = 5) -> pd.DataFrame:
    if role_df.empty:
        return pd.DataFrame()
    pools: dict[str, pd.DataFrame] = {}
    for role_slot in ("core_pair", "mid_single", "support_pair"):
        subset = role_df[role_df["role_slot"] == role_slot].head(top_k_per_role).copy()
        if subset.empty:
            return pd.DataFrame()
        pools[role_slot] = subset
    rows: list[dict[str, Any]] = []
    for _, core in pools["core_pair"].iterrows():
        for _, mid in pools["mid_single"].iterrows():
            for _, support in pools["support_pair"].iterrows():
                lineup_raw = float(core["value_raw"]) + float(mid["value_raw"]) + float(support["value_raw"])
                rows.append(
                    {
                        "core_team": core["team_name"],
                        "core_players": core["player_names"],
                        "mid_team": mid["team_name"],
                        "mid_players": mid["player_names"],
                        "support_team": support["team_name"],
                        "support_players": support["player_names"],
                        "lineup_value_raw": round(lineup_raw, 4),
                    }
                )
    out = pd.DataFrame(rows).sort_values("lineup_value_raw", ascending=False).reset_index(drop=True)
    out = out.head(20).copy()
    out["lineup_rank"] = range(1, len(out) + 1)
    out["lineup_score_1_100"] = rank_scale_1_100(out["lineup_value_raw"]).round(2)
    return out[[
        "lineup_rank",
        "core_team",
        "core_players",
        "mid_team",
        "mid_players",
        "support_team",
        "support_players",
        "lineup_value_raw",
        "lineup_score_1_100",
    ]]


def build_complex_banner_optimizer(
    *,
    profile_id: str | None = None,
    db_path: Path = DB_PATH,
    ti2026_only: bool = True,
) -> dict[str, Any]:
    con = sqlite3.connect(str(db_path))
    try:
        create_schema(con)
        rebuild_views(con)
        if profile_id is None:
            profile_id = _default_complex_profile_id(con)
        event_row = con.execute(
            "SELECT COALESCE(event_id, 'ti2026') FROM fantasy_banner_instances WHERE profile_id = ?",
            (profile_id,),
        ).fetchone()
        event_id = str(event_row[0]) if event_row else "ti2026"
        run_id = f"complex_banner::{profile_id}::{utc_now()}"

        player_map_df = _player_maps(con, profile_id, ti2026_only)
        player_series_df = _player_series(player_map_df) if not player_map_df.empty else pd.DataFrame()
        player_scores = _summarize_player_scores(player_map_df, player_series_df)

        role_map_df = _role_maps(con, profile_id, ti2026_only)
        role_series_df = _role_series(role_map_df) if not role_map_df.empty else pd.DataFrame()
        role_scores = _summarize_role_scores(role_map_df, role_series_df)
        lineup_scores = _build_lineups(role_scores)

        cur = con.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO fantasy_complex_banner_runs(
                run_id, profile_id, event_id, created_at_utc, ti2026_only, source_notes
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                profile_id,
                event_id,
                utc_now(),
                1 if ti2026_only else 0,
                "Complex playoff banner evaluation built from fantasy_player_map_scores and fantasy_team_role_map_scores.",
            ),
        )
        cur.execute("DELETE FROM fantasy_complex_banner_player_scores WHERE run_id = ?", (run_id,))
        cur.execute("DELETE FROM fantasy_complex_banner_role_scores WHERE run_id = ?", (run_id,))
        cur.execute("DELETE FROM fantasy_complex_banner_lineup_scores WHERE run_id = ?", (run_id,))

        if not player_scores.empty:
            cur.executemany(
                """
                INSERT INTO fantasy_complex_banner_player_scores(
                    run_id, profile_id, event_id, account_id, team_name, official_name, official_position, role_group,
                    maps_seen, series_seen, avg_map_score, p75_map_score, p90_map_score, best_map_score,
                    avg_series_score, p75_series_score, p90_series_score, best_series_score, floor_series_score,
                    std_series_score, consistency_ratio, value_raw, value_score_1_100, created_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        profile_id,
                        event_id,
                        int(row.account_id),
                        row.team_name,
                        row.official_name,
                        int(row.official_position),
                        row.role_group,
                        int(row.maps_seen),
                        int(row.series_seen),
                        float(row.avg_map_score),
                        float(row.p75_map_score),
                        float(row.p90_map_score),
                        float(row.best_map_score),
                        float(row.avg_series_score),
                        float(row.p75_series_score),
                        float(row.p90_series_score),
                        float(row.best_series_score),
                        float(row.floor_series_score),
                        float(row.std_series_score),
                        float(row.consistency_ratio),
                        float(row.value_raw),
                        float(row.value_score_1_100),
                        utc_now(),
                    )
                    for row in player_scores.itertuples(index=False)
                ],
            )
        if not role_scores.empty:
            cur.executemany(
                """
                INSERT INTO fantasy_complex_banner_role_scores(
                    run_id, profile_id, event_id, role_slot, team_name, player_names, account_ids,
                    maps_seen, series_seen, avg_map_score, p75_map_score, p90_map_score, best_map_score,
                    avg_series_score, p75_series_score, p90_series_score, best_series_score, floor_series_score,
                    std_series_score, consistency_ratio, value_raw, value_score_1_100, created_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        profile_id,
                        event_id,
                        row.role_slot,
                        row.team_name,
                        row.player_names,
                        row.account_ids,
                        int(row.maps_seen),
                        int(row.series_seen),
                        float(row.avg_map_score),
                        float(row.p75_map_score),
                        float(row.p90_map_score),
                        float(row.best_map_score),
                        float(row.avg_series_score),
                        float(row.p75_series_score),
                        float(row.p90_series_score),
                        float(row.best_series_score),
                        float(row.floor_series_score),
                        float(row.std_series_score),
                        float(row.consistency_ratio),
                        float(row.value_raw),
                        float(row.value_score_1_100),
                        utc_now(),
                    )
                    for row in role_scores.itertuples(index=False)
                ],
            )
        if not lineup_scores.empty:
            cur.executemany(
                """
                INSERT INTO fantasy_complex_banner_lineup_scores(
                    run_id, profile_id, event_id, lineup_rank, core_team, core_players,
                    mid_team, mid_players, support_team, support_players,
                    lineup_value_raw, lineup_score_1_100, created_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        profile_id,
                        event_id,
                        int(row.lineup_rank),
                        row.core_team,
                        row.core_players,
                        row.mid_team,
                        row.mid_players,
                        row.support_team,
                        row.support_players,
                        float(row.lineup_value_raw),
                        float(row.lineup_score_1_100),
                        utc_now(),
                    )
                    for row in lineup_scores.itertuples(index=False)
                ],
            )
        con.commit()
        rebuild_views(con)
        summary = pd.DataFrame(
            [
                {
                    "profile_id": profile_id,
                    "event_id": event_id,
                    "player_rows": int(len(player_scores)),
                    "role_rows": int(len(role_scores)),
                    "lineup_rows": int(len(lineup_scores)),
                }
            ]
        )
        return {
            "run_id": run_id,
            "profile_id": profile_id,
            "event_id": event_id,
            "player_scores": player_scores,
            "role_scores": role_scores,
            "lineup_scores": lineup_scores,
            "summary": summary,
        }
    finally:
        con.close()
