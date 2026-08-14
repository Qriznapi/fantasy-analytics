from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from fantasy_prediction_foundation import (
    DB_PATH,
    default_profile_id,
    load_target_dataset,
    percentile,
    safe_float,
    spearman_corr,
)
from project_db import resolve_db_path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = resolve_db_path(PROJECT_ROOT)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def std_population(values: list[float]) -> float:
    values = [safe_float(v) for v in values if v is not None]
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def rank_scale_1_100(values: pd.Series) -> pd.Series:
    if len(values) == 0:
        return values
    if len(values) == 1:
        return pd.Series([100.0], index=values.index)
    ranks = values.rank(method="average", ascending=True)
    return (1.0 + 99.0 * (ranks - 1.0) / (len(values) - 1.0)).round(2)


def top_k_overlap(actual: pd.Series, predicted: pd.Series, k: int) -> float:
    if len(actual) == 0:
        return 0.0
    frame = pd.DataFrame({"actual": actual, "predicted": predicted})
    actual_top = set(frame.sort_values("actual", ascending=False).head(k).index.tolist())
    predicted_top = set(frame.sort_values("predicted", ascending=False).head(k).index.tolist())
    denom = min(k, len(frame))
    if denom == 0:
        return 0.0
    return len(actual_top & predicted_top) / float(denom)


def create_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS foundation_reliability_runs (
            run_id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            target_policy TEXT NOT NULL,
            train_scope TEXT NOT NULL,
            test_scope TEXT NOT NULL,
            notes TEXT,
            created_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS foundation_reliability_entity_scores (
            run_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_key TEXT NOT NULL,
            team_name TEXT NOT NULL,
            official_name TEXT,
            official_position INTEGER,
            role_group TEXT,
            role_slot TEXT,
            player_names TEXT,
            account_id INTEGER,
            account_ids TEXT,
            ti2026_qualified INTEGER NOT NULL,
            qualification_path TEXT,
            ti_region TEXT,
            sample_maps INTEGER NOT NULL,
            sample_series INTEGER NOT NULL,
            map_mean_score REAL NOT NULL,
            map_p75_score REAL NOT NULL,
            map_p90_score REAL NOT NULL,
            map_floor_score REAL NOT NULL,
            map_std_score REAL NOT NULL,
            series_mean_avg REAL NOT NULL,
            series_mean_p75 REAL NOT NULL,
            series_top1_avg REAL NOT NULL,
            series_top1_p75 REAL NOT NULL,
            series_top1_p90 REAL NOT NULL,
            recent_map_mean_5 REAL NOT NULL,
            recent_series_mean_3 REAL NOT NULL,
            recent_series_top1_3 REAL NOT NULL,
            team_segment_strength REAL NOT NULL,
            positive_stat_count INTEGER NOT NULL,
            top_stat_share REAL NOT NULL,
            stat_balance_score REAL NOT NULL,
            volatility_ratio REAL NOT NULL,
            sample_weight REAL NOT NULL,
            reliability_raw_score REAL NOT NULL,
            reliability_score_1_100 REAL NOT NULL,
            low_estimate REAL NOT NULL,
            expected_estimate REAL NOT NULL,
            high_estimate REAL NOT NULL,
            confidence_label TEXT NOT NULL,
            data_quality_label TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, entity_key)
        );

        CREATE TABLE IF NOT EXISTS foundation_reliability_backtest (
            run_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_key TEXT NOT NULL,
            team_name TEXT NOT NULL,
            segment_key TEXT NOT NULL,
            predicted_score REAL NOT NULL,
            actual_test_score REAL NOT NULL,
            abs_error REAL NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, entity_key)
        );

        DROP VIEW IF EXISTS analytics_reliable_players_foundation;
        CREATE VIEW analytics_reliable_players_foundation AS
        SELECT *
        FROM foundation_reliability_entity_scores
        WHERE entity_type = 'player';

        DROP VIEW IF EXISTS analytics_reliable_role_slots_foundation;
        CREATE VIEW analytics_reliable_role_slots_foundation AS
        SELECT *
        FROM foundation_reliability_entity_scores
        WHERE entity_type = 'role_slot';

        DROP VIEW IF EXISTS analytics_reliability_foundation_backtest;
        CREATE VIEW analytics_reliability_foundation_backtest AS
        SELECT *
        FROM foundation_reliability_backtest;
        """
    )


def load_stat_profile_frame(con: sqlite3.Connection, profile_id: str, entity_type: str) -> pd.DataFrame:
    player_stats = pd.read_sql_query(
        """
        SELECT
            m.profile_id,
            m.match_id,
            m.match_date,
            m.team_name,
            m.account_id,
            m.official_name,
            m.official_position,
            m.role_group,
            s.stat_name,
            s.base_points
        FROM fantasy_player_map_scores m
        JOIN fantasy_player_map_stat_points s
          ON s.match_id = m.match_id
         AND s.account_id = m.account_id
         AND s.team_name = m.team_name
        WHERE m.profile_id = ?
        ORDER BY m.team_name, m.account_id, m.match_date, m.match_id, s.stat_name
        """,
        con,
        params=(profile_id,),
    )
    if entity_type == "player":
        player_stats["entity_key"] = player_stats["team_name"].astype(str) + "::" + player_stats["account_id"].astype(str)
        player_stats["observation_key"] = player_stats["entity_key"] + "::map:" + player_stats["match_id"].astype(str)
        return player_stats

    frame = player_stats.copy()
    frame["role_slot"] = None
    frame.loc[frame["official_position"].isin([1, 3]), "role_slot"] = "core_pair"
    frame.loc[frame["official_position"] == 2, "role_slot"] = "mid_single"
    frame.loc[frame["official_position"].isin([4, 5]), "role_slot"] = "support_pair"
    frame = frame[frame["role_slot"].notna()].copy()
    grouped = (
        frame.groupby(
            ["match_id", "match_date", "team_name", "role_slot", "stat_name"],
            dropna=False,
            as_index=False,
        )["base_points"]
        .mean()
    )
    grouped["entity_key"] = grouped["team_name"].astype(str) + "::" + grouped["role_slot"].astype(str)
    grouped["observation_key"] = grouped["entity_key"] + "::map:" + grouped["match_id"].astype(str)
    return grouped


def build_stat_profile_features(stat_frame: pd.DataFrame) -> dict[str, dict[str, float]]:
    payload: dict[str, dict[str, float]] = {}
    for entity_key, group in stat_frame.groupby("entity_key", sort=False):
        wide = (
            group.pivot_table(
                index="observation_key",
                columns="stat_name",
                values="base_points",
                aggfunc="sum",
                fill_value=0.0,
            )
            .astype(float)
        )
        if wide.empty:
            payload[str(entity_key)] = {
                "positive_stat_count": 0.0,
                "top_stat_share": 1.0,
                "stat_balance_score": 0.0,
            }
            continue
        p75_by_stat = {col: percentile(wide[col].tolist(), 0.75) for col in wide.columns}
        positive = {stat: value for stat, value in p75_by_stat.items() if value > 1e-9}
        positive_stat_count = float(len(positive))
        positive_total = sum(positive.values())
        top_stat_share = max(positive.values()) / positive_total if positive_total > 1e-9 else 1.0
        breadth = min(1.0, positive_stat_count / 6.0)
        balance = max(0.0, 1.0 - top_stat_share)
        payload[str(entity_key)] = {
            "positive_stat_count": positive_stat_count,
            "top_stat_share": safe_float(top_stat_share),
            "stat_balance_score": safe_float(breadth * balance),
        }
    return payload


def recent_mean(values: list[float], n: int) -> float:
    if not values:
        return 0.0
    recent = values[-n:]
    return safe_float(sum(recent) / len(recent))


def build_entity_scores(
    profile_id: str,
    entity_type: str,
    map_df: pd.DataFrame,
    series_mean_df: pd.DataFrame,
    series_top1_df: pd.DataFrame,
    stat_features: dict[str, dict[str, float]],
) -> pd.DataFrame:
    map_df = map_df.sort_values(["entity_key", "observation_date", "observation_key"]).copy()
    series_mean_df = series_mean_df.sort_values(["entity_key", "observation_date", "observation_key"]).copy()
    series_top1_df = series_top1_df.sort_values(["entity_key", "observation_date", "observation_key"]).copy()

    segment_col = "role_group" if entity_type == "player" else "role_slot"
    team_segment_means = (
        series_mean_df.assign(team_segment_key=series_mean_df["team_name"].astype(str) + "::" + series_mean_df[segment_col].astype(str))
        .groupby("team_segment_key")["target_score"]
        .mean()
        .to_dict()
    )
    segment_global_means = series_mean_df.groupby(segment_col)["target_score"].mean().to_dict()

    rows: list[dict[str, Any]] = []
    entity_keys = sorted(set(map_df["entity_key"]).intersection(series_mean_df["entity_key"]).intersection(series_top1_df["entity_key"]))
    for entity_key in entity_keys:
        map_group = map_df[map_df["entity_key"] == entity_key].copy()
        mean_group = series_mean_df[series_mean_df["entity_key"] == entity_key].copy()
        top1_group = series_top1_df[series_top1_df["entity_key"] == entity_key].copy()
        if map_group.empty or mean_group.empty or top1_group.empty:
            continue
        first = mean_group.iloc[0]
        segment_value = str(first[segment_col])
        team_segment_key = f"{first['team_name']}::{segment_value}"
        map_scores = map_group["target_score"].astype(float).tolist()
        series_mean_scores = mean_group["target_score"].astype(float).tolist()
        series_top1_scores = top1_group["target_score"].astype(float).tolist()
        map_mean = safe_float(sum(map_scores) / len(map_scores))
        map_p75 = percentile(map_scores, 0.75)
        map_p90 = percentile(map_scores, 0.90)
        map_floor = min(map_scores) if map_scores else 0.0
        map_std = std_population(map_scores)
        series_mean_avg = safe_float(sum(series_mean_scores) / len(series_mean_scores))
        series_mean_p75 = percentile(series_mean_scores, 0.75)
        series_top1_avg = safe_float(sum(series_top1_scores) / len(series_top1_scores))
        series_top1_p75 = percentile(series_top1_scores, 0.75)
        series_top1_p90 = percentile(series_top1_scores, 0.90)
        recent_map_mean_5 = recent_mean(map_scores, 5)
        recent_series_mean_3 = recent_mean(series_mean_scores, 3)
        recent_series_top1_3 = recent_mean(series_top1_scores, 3)
        team_segment_strength = safe_float(team_segment_means.get(team_segment_key, segment_global_means.get(segment_value, series_mean_avg)))
        stat_feature = stat_features.get(entity_key, {})
        positive_stat_count = int(stat_feature.get("positive_stat_count", 0.0))
        top_stat_share = safe_float(stat_feature.get("top_stat_share", 1.0))
        stat_balance_score = safe_float(stat_feature.get("stat_balance_score", 0.0))
        sample_maps = len(map_scores)
        sample_series = len(series_mean_scores)
        sample_weight = min(1.0, sample_series / (sample_series + 4.0))
        volatility_ratio = min(2.0, map_std / max(map_mean, 1.0))
        ceiling_component = (
            0.30 * series_top1_p75
            + 0.22 * series_mean_p75
            + 0.16 * map_p75
            + 0.12 * recent_series_top1_3
            + 0.10 * recent_series_mean_3
            + 0.10 * series_top1_p90
        )
        stability_component = (
            0.35 * series_mean_avg
            + 0.20 * map_mean
            + 0.15 * map_floor
            + 0.15 * recent_map_mean_5
            + 0.15 * team_segment_strength
        )
        raw = (
            sample_weight * (0.60 * ceiling_component + 0.40 * stability_component)
            + 0.10 * team_segment_strength
            + 400.0 * stat_balance_score
            - 0.18 * map_std
            - 250.0 * volatility_ratio * top_stat_share
        )
        expected = max(0.0, raw)
        downside = max(0.0, expected - (0.45 * map_std + 1200.0 * (1.0 - sample_weight) + 300.0 * top_stat_share))
        upside = expected + 0.35 * map_std + 500.0 * sample_weight + 250.0 * stat_balance_score
        if sample_series >= 8 and volatility_ratio <= 0.55:
            confidence = "high"
        elif sample_series >= 4 and volatility_ratio <= 0.90:
            confidence = "medium"
        else:
            confidence = "low"
        data_quality = "support_context_sensitive" if entity_type == "player" and first.get("role_group") == "support" else "foundation_v1"
        if entity_type == "role_slot" and first.get("role_slot") == "support_pair":
            data_quality = "support_context_sensitive"
        rows.append(
            {
                "entity_type": entity_type,
                "entity_key": entity_key,
                "team_name": first["team_name"],
                "official_name": first["official_name"] if entity_type == "player" else None,
                "official_position": first["official_position"] if entity_type == "player" else None,
                "role_group": first["role_group"] if entity_type == "player" else None,
                "role_slot": first["role_slot"] if entity_type == "role_slot" else None,
                "player_names": first["player_names"] if entity_type == "role_slot" else None,
                "account_id": first["account_id"] if entity_type == "player" else None,
                "account_ids": first["account_ids"] if entity_type == "role_slot" else None,
                "ti2026_qualified": int(first["ti2026_qualified"]),
                "qualification_path": first["qualification_path"],
                "ti_region": first["ti_region"],
                "sample_maps": sample_maps,
                "sample_series": sample_series,
                "map_mean_score": map_mean,
                "map_p75_score": map_p75,
                "map_p90_score": map_p90,
                "map_floor_score": map_floor,
                "map_std_score": map_std,
                "series_mean_avg": series_mean_avg,
                "series_mean_p75": series_mean_p75,
                "series_top1_avg": series_top1_avg,
                "series_top1_p75": series_top1_p75,
                "series_top1_p90": series_top1_p90,
                "recent_map_mean_5": recent_map_mean_5,
                "recent_series_mean_3": recent_series_mean_3,
                "recent_series_top1_3": recent_series_top1_3,
                "team_segment_strength": team_segment_strength,
                "positive_stat_count": positive_stat_count,
                "top_stat_share": top_stat_share,
                "stat_balance_score": stat_balance_score,
                "volatility_ratio": volatility_ratio,
                "sample_weight": sample_weight,
                "reliability_raw_score": expected,
                "low_estimate": downside,
                "expected_estimate": expected,
                "high_estimate": upside,
                "confidence_label": confidence,
                "data_quality_label": data_quality,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    segment_rank_col = "role_group" if entity_type == "player" else "role_slot"
    frame["reliability_score_1_100"] = 1.0
    for _, idx in frame.groupby(segment_rank_col).groups.items():
        frame.loc[idx, "reliability_score_1_100"] = rank_scale_1_100(frame.loc[idx, "reliability_raw_score"])
    return frame.sort_values([segment_rank_col, "reliability_score_1_100", "reliability_raw_score"], ascending=[True, False, False]).reset_index(drop=True)


def build_playoff_actuals(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return (
        df.groupby("entity_key", as_index=False)
        .agg(actual_test_score=("target_score", "mean"), team_name=("team_name", "first"))
    )


def store_scores_and_backtest(
    con: sqlite3.Connection,
    profile_id: str,
    entity_type: str,
    score_frame: pd.DataFrame,
    actual_frame: pd.DataFrame,
) -> str:
    run_id = f"reliability_foundation::{entity_type}::series_mean_plus_top1_v1"
    now = utc_now()
    cur = con.cursor()
    cur.execute("DELETE FROM foundation_reliability_entity_scores WHERE run_id = ?", (run_id,))
    cur.execute("DELETE FROM foundation_reliability_backtest WHERE run_id = ?", (run_id,))
    cur.execute("DELETE FROM foundation_reliability_runs WHERE run_id = ?", (run_id,))
    cur.execute(
        """
        INSERT INTO foundation_reliability_runs(
            run_id, profile_id, entity_type, target_policy, train_scope, test_scope, notes, created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            profile_id,
            entity_type,
            "series_mean_plus_top1_v1",
            "group_stage_only",
            "non_group_stage_mean_actual",
            "Foundation reliability built from map, series_mean, series_top1, stat balance, and volatility features.",
            now,
        ),
    )
    if not score_frame.empty:
        rows = []
        for row in score_frame.itertuples(index=False):
            rows.append(
                (
                    run_id,
                    row.entity_type,
                    row.entity_key,
                    row.team_name,
                    row.official_name,
                    None if pd.isna(row.official_position) else int(row.official_position),
                    row.role_group,
                    row.role_slot,
                    row.player_names,
                    None if pd.isna(row.account_id) else int(row.account_id),
                    row.account_ids,
                    int(row.ti2026_qualified),
                    row.qualification_path,
                    row.ti_region,
                    int(row.sample_maps),
                    int(row.sample_series),
                    float(row.map_mean_score),
                    float(row.map_p75_score),
                    float(row.map_p90_score),
                    float(row.map_floor_score),
                    float(row.map_std_score),
                    float(row.series_mean_avg),
                    float(row.series_mean_p75),
                    float(row.series_top1_avg),
                    float(row.series_top1_p75),
                    float(row.series_top1_p90),
                    float(row.recent_map_mean_5),
                    float(row.recent_series_mean_3),
                    float(row.recent_series_top1_3),
                    float(row.team_segment_strength),
                    int(row.positive_stat_count),
                    float(row.top_stat_share),
                    float(row.stat_balance_score),
                    float(row.volatility_ratio),
                    float(row.sample_weight),
                    float(row.reliability_raw_score),
                    float(row.reliability_score_1_100),
                    float(row.low_estimate),
                    float(row.expected_estimate),
                    float(row.high_estimate),
                    row.confidence_label,
                    row.data_quality_label,
                    now,
                )
            )
        cur.executemany(
            """
            INSERT OR REPLACE INTO foundation_reliability_entity_scores(
                run_id, entity_type, entity_key, team_name, official_name, official_position, role_group, role_slot,
                player_names, account_id, account_ids, ti2026_qualified, qualification_path, ti_region, sample_maps,
                sample_series, map_mean_score, map_p75_score, map_p90_score, map_floor_score, map_std_score,
                series_mean_avg, series_mean_p75, series_top1_avg, series_top1_p75, series_top1_p90,
                recent_map_mean_5, recent_series_mean_3, recent_series_top1_3, team_segment_strength,
                positive_stat_count, top_stat_share, stat_balance_score, volatility_ratio, sample_weight,
                reliability_raw_score, reliability_score_1_100, low_estimate, expected_estimate, high_estimate,
                confidence_label, data_quality_label, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    if not score_frame.empty and not actual_frame.empty:
        merged = score_frame.merge(actual_frame, on=["entity_key", "team_name"], how="inner")
        segment_key_col = "role_group" if entity_type == "player" else "role_slot"
        for row in merged.itertuples(index=False):
            cur.execute(
                """
                INSERT OR REPLACE INTO foundation_reliability_backtest(
                    run_id, entity_type, entity_key, team_name, segment_key, predicted_score, actual_test_score, abs_error, created_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    entity_type,
                    row.entity_key,
                    row.team_name,
                    getattr(row, segment_key_col),
                    float(row.reliability_raw_score),
                    float(row.actual_test_score),
                    abs(float(row.reliability_raw_score) - float(row.actual_test_score)),
                    now,
                ),
            )
    con.commit()
    return run_id


def load_group_and_playoff_targets(con: sqlite3.Connection, profile_id: str, entity_type: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    prefix = "player" if entity_type == "player" else "role_slot"
    map_df = load_target_dataset(con, f"{prefix}_map_score", profile_id)
    series_mean_df = load_target_dataset(con, f"{prefix}_series_mean", profile_id)
    series_top1_df = load_target_dataset(con, f"{prefix}_series_top1", profile_id)
    return (
        map_df[map_df["stage_bucket"] == "group_stage"].copy(),
        map_df[map_df["stage_bucket"] != "group_stage"].copy(),
        series_mean_df[series_mean_df["stage_bucket"] == "group_stage"].copy(),
        series_mean_df[series_mean_df["stage_bucket"] != "group_stage"].copy(),
        series_top1_df[series_top1_df["stage_bucket"] == "group_stage"].copy(),
        series_top1_df[series_top1_df["stage_bucket"] != "group_stage"].copy(),
    )


def build_reliability_foundation(db_path: Path = DB_PATH) -> dict[str, Any]:
    con = sqlite3.connect(str(db_path))
    try:
        create_schema(con)
        profile_id = default_profile_id(con)
        run_ids: list[str] = []
        summaries: list[dict[str, Any]] = []
        for entity_type in ("player", "role_slot"):
            train_map, test_map, train_series_mean, test_series_mean, train_series_top1, test_series_top1 = load_group_and_playoff_targets(
                con, profile_id, entity_type
            )
            stat_features = build_stat_profile_features(load_stat_profile_frame(con, profile_id, entity_type))
            score_frame = build_entity_scores(
                profile_id,
                entity_type,
                train_map,
                train_series_mean,
                train_series_top1,
                stat_features,
            )
            if score_frame.empty:
                continue
            actual_playoff = build_playoff_actuals(test_series_mean.assign(target_score=0.60 * test_series_mean["target_score"]))
            top1_playoff = build_playoff_actuals(test_series_top1.assign(target_score=0.40 * test_series_top1["target_score"]))
            actual_playoff = (
                actual_playoff.merge(top1_playoff, on=["entity_key", "team_name"], how="outer", suffixes=("_mean", "_top1"))
                .fillna(0.0)
            )
            actual_playoff["actual_test_score"] = actual_playoff["actual_test_score_mean"] + actual_playoff["actual_test_score_top1"]
            actual_frame = actual_playoff[["entity_key", "team_name", "actual_test_score"]].copy()
            run_id = store_scores_and_backtest(con, profile_id, entity_type, score_frame, actual_frame)
            run_ids.append(run_id)
            merged = score_frame.merge(actual_frame, on=["entity_key", "team_name"], how="inner")
            segment_col = "role_group" if entity_type == "player" else "role_slot"
            summaries.append(
                {
                    "entity_type": entity_type,
                    "rows_scored": int(len(score_frame)),
                    "rows_backtested": int(len(merged)),
                    "spearman": spearman_corr(merged["actual_test_score"], merged["reliability_raw_score"]) if not merged.empty else 0.0,
                    "top5_overlap": top_k_overlap(merged["actual_test_score"], merged["reliability_raw_score"], 5) if not merged.empty else 0.0,
                    "segments": int(score_frame[segment_col].nunique()),
                }
            )
        return {"profile_id": profile_id, "run_ids": run_ids, "summary": pd.DataFrame(summaries)}
    finally:
        con.close()
