from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from project_db import resolve_db_path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = resolve_db_path(PROJECT_ROOT)


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


def spearman_corr(actual: pd.Series, predicted: pd.Series) -> float:
    if len(actual) < 2 or len(predicted) < 2:
        return 0.0
    if actual.nunique(dropna=False) <= 1 or predicted.nunique(dropna=False) <= 1:
        return 0.0
    ranked_actual = actual.rank(method="average")
    ranked_predicted = predicted.rank(method="average")
    corr = ranked_actual.corr(ranked_predicted, method="pearson")
    if pd.isna(corr):
        return 0.0
    return float(corr)


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


def ndcg_at_k(actual: pd.Series, predicted: pd.Series, k: int) -> float:
    if len(actual) == 0:
        return 0.0
    frame = pd.DataFrame({"actual": actual.astype(float), "predicted": predicted.astype(float)})
    frame = frame.sort_values("predicted", ascending=False).head(k).reset_index(drop=True)
    dcg = 0.0
    for idx, value in enumerate(frame["actual"].tolist(), start=1):
        dcg += value / math.log2(idx + 1.0)
    ideal = actual.astype(float).sort_values(ascending=False).head(k).tolist()
    idcg = 0.0
    for idx, value in enumerate(ideal, start=1):
        idcg += value / math.log2(idx + 1.0)
    if idcg <= 0:
        return 0.0
    return dcg / idcg


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


@dataclass(frozen=True)
class TargetSpec:
    target_id: str
    entity_type: str
    source_level: str
    aggregation_policy: str
    description: str


TARGET_SPECS = (
    TargetSpec("player_map_score", "player", "map", "identity", "Player fantasy score on a single map."),
    TargetSpec("player_series_mean", "player", "series", "mean", "Mean player fantasy score across maps in a series."),
    TargetSpec("player_series_top1", "player", "series", "top1", "Best single-map player fantasy score inside a series."),
    TargetSpec("role_slot_map_score", "role_slot", "map", "identity", "Role-slot fantasy score on a single map."),
    TargetSpec("role_slot_series_mean", "role_slot", "series", "mean", "Mean role-slot fantasy score across maps in a series."),
    TargetSpec("role_slot_series_top1", "role_slot", "series", "top1", "Best single-map role-slot fantasy score inside a series."),
)

TARGET_BY_ID = {spec.target_id: spec for spec in TARGET_SPECS}
BASELINE_MODELS = (
    "global_mean",
    "segment_mean",
    "entity_mean",
    "entity_p75",
    "recent_mean_5",
    "recent_p75_5",
    "team_segment_mean",
    "shrunk_mean",
)


@dataclass(frozen=True)
class SplitDefinition:
    split_name: str
    train_label: str
    test_label: str


SPLITS = (
    SplitDefinition("group_to_playoff", "group_stage_only", "non_group_stage"),
    SplitDefinition("temporal_60_40", "first_60_percent_per_entity", "last_40_percent_per_entity"),
)


def create_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS prediction_target_registry (
            target_id TEXT PRIMARY KEY,
            entity_type TEXT NOT NULL,
            source_level TEXT NOT NULL,
            aggregation_policy TEXT NOT NULL,
            description TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS dataset_prediction_targets (
            target_id TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_key TEXT NOT NULL,
            observation_key TEXT NOT NULL,
            source_level TEXT NOT NULL,
            aggregation_policy TEXT NOT NULL,
            team_name TEXT NOT NULL,
            official_name TEXT,
            official_position INTEGER,
            role_group TEXT,
            role_slot TEXT,
            player_names TEXT,
            account_id INTEGER,
            account_ids TEXT,
            match_id INTEGER,
            series_key TEXT,
            series_id INTEGER,
            observation_date TEXT,
            stage_bucket TEXT,
            stage_name TEXT,
            maps_in_observation INTEGER NOT NULL,
            target_score REAL NOT NULL,
            ti2026_qualified INTEGER NOT NULL,
            qualification_path TEXT,
            ti_region TEXT,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (target_id, profile_id, entity_key, observation_key)
        );

        CREATE TABLE IF NOT EXISTS foundation_model_registry (
            model_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            description TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (model_id, target_id)
        );

        CREATE TABLE IF NOT EXISTS foundation_prediction_runs (
            run_id TEXT PRIMARY KEY,
            target_id TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            split_name TEXT NOT NULL,
            model_id TEXT NOT NULL,
            train_label TEXT NOT NULL,
            test_label TEXT NOT NULL,
            notes TEXT,
            created_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS foundation_prediction_outputs (
            run_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            split_name TEXT NOT NULL,
            model_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_key TEXT NOT NULL,
            observation_key TEXT NOT NULL,
            team_name TEXT NOT NULL,
            official_name TEXT,
            official_position INTEGER,
            role_group TEXT,
            role_slot TEXT,
            player_names TEXT,
            account_id INTEGER,
            account_ids TEXT,
            match_id INTEGER,
            series_key TEXT,
            series_id INTEGER,
            observation_date TEXT,
            stage_bucket TEXT,
            actual_score REAL NOT NULL,
            predicted_score REAL NOT NULL,
            abs_error REAL NOT NULL,
            train_rows_used INTEGER NOT NULL,
            fallback_label TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, entity_key, observation_key)
        );

        CREATE TABLE IF NOT EXISTS foundation_evaluation_reports (
            run_id TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            metric_value REAL NOT NULL,
            metric_scope TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, metric_name, metric_scope)
        );

        DROP VIEW IF EXISTS analytics_prediction_foundation_evaluation;
        CREATE VIEW analytics_prediction_foundation_evaluation AS
        SELECT
            r.run_id,
            r.target_id,
            r.profile_id,
            r.split_name,
            r.model_id,
            e.metric_name,
            e.metric_value,
            e.metric_scope,
            r.created_at_utc
        FROM foundation_prediction_runs r
        JOIN foundation_evaluation_reports e
          ON e.run_id = r.run_id;
        """
    )


def register_target_and_models(con: sqlite3.Connection) -> None:
    now = utc_now()
    cur = con.cursor()
    for spec in TARGET_SPECS:
        cur.execute(
            """
            INSERT OR REPLACE INTO prediction_target_registry(
                target_id, entity_type, source_level, aggregation_policy, description, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (spec.target_id, spec.entity_type, spec.source_level, spec.aggregation_policy, spec.description, now),
        )
    descriptions = {
        "global_mean": "Single global train mean.",
        "segment_mean": "Mean inside role_group or role_slot.",
        "entity_mean": "Historical entity mean with segment/global fallback.",
        "entity_p75": "Historical entity p75 with segment/global fallback.",
        "recent_mean_5": "Mean over the last five train observations for the entity.",
        "recent_p75_5": "P75 over the last five train observations for the entity.",
        "team_segment_mean": "Mean inside team+segment.",
        "shrunk_mean": "Shrink entity mean toward team-segment and segment means.",
    }
    for spec in TARGET_SPECS:
        for model_id, description in descriptions.items():
            cur.execute(
                """
                INSERT OR REPLACE INTO foundation_model_registry(model_id, target_id, description, created_at_utc)
                VALUES (?, ?, ?, ?)
                """,
                (model_id, spec.target_id, description, now),
            )


def build_player_map_frame(con: sqlite3.Connection, profile_id: str) -> pd.DataFrame:
    df = pd.read_sql_query(
        """
        SELECT
            m.profile_id,
            m.match_id,
            m.match_date,
            m.series_id,
            COALESCE(CAST(m.series_id AS TEXT), 'match:' || CAST(m.match_id AS TEXT)) AS series_key,
            m.account_id,
            m.team_name,
            m.official_name,
            m.official_position,
            m.role_group,
            m.stage_name,
            m.stage_bucket,
            m.fantasy_score,
            CASE WHEN ti.team_name IS NULL THEN 0 ELSE 1 END AS ti2026_qualified,
            ti.qualification_path,
            ti.region AS ti_region
        FROM fantasy_player_map_scores m
        LEFT JOIN analytics_ti2026_teams ti
          ON ti.team_name = m.team_name
        WHERE m.profile_id = ?
        ORDER BY m.team_name, m.account_id, m.match_date, m.match_id
        """,
        con,
        params=(profile_id,),
    )
    df["entity_type"] = "player"
    df["entity_key"] = df["team_name"].astype(str) + "::" + df["account_id"].astype(str)
    df["observation_key"] = "map:" + df["match_id"].astype(str)
    df["source_level"] = "map"
    df["aggregation_policy"] = "identity"
    df["role_slot"] = None
    df["player_names"] = None
    df["account_ids"] = None
    df["maps_in_observation"] = 1
    df["target_score"] = df["fantasy_score"].astype(float)
    df["observation_date"] = df["match_date"]
    return df


def build_role_slot_map_frame(con: sqlite3.Connection, profile_id: str) -> pd.DataFrame:
    df = pd.read_sql_query(
        """
        WITH series_lookup AS (
            SELECT
                profile_id,
                match_id,
                team_name,
                MAX(series_id) AS series_id,
                COALESCE(CAST(MAX(series_id) AS TEXT), 'match:' || CAST(match_id AS TEXT)) AS series_key
            FROM fantasy_player_map_scores
            WHERE profile_id = ?
            GROUP BY profile_id, match_id, team_name
        )
        SELECT
            r.profile_id,
            r.match_id,
            r.match_date,
            s.series_id,
            s.series_key,
            r.team_name,
            NULL AS official_name,
            NULL AS official_position,
            NULL AS role_group,
            'core_pair' AS role_slot,
            r.core_players AS player_names,
            NULL AS account_id,
            NULL AS account_ids,
            r.stage_name,
            r.stage_bucket,
            r.avg_core_fantasy_score AS fantasy_score,
            r.ti2026_qualified,
            r.qualification_path,
            r.ti_region
        FROM analytics_team_role_maps r
        LEFT JOIN series_lookup s
          ON s.profile_id = r.profile_id
         AND s.match_id = r.match_id
         AND s.team_name = r.team_name
        WHERE r.profile_id = ?
        UNION ALL
        SELECT
            r.profile_id,
            r.match_id,
            r.match_date,
            s.series_id,
            s.series_key,
            r.team_name,
            NULL AS official_name,
            NULL AS official_position,
            NULL AS role_group,
            'mid_single' AS role_slot,
            r.mid_player AS player_names,
            NULL AS account_id,
            NULL AS account_ids,
            r.stage_name,
            r.stage_bucket,
            r.mid_fantasy_score AS fantasy_score,
            r.ti2026_qualified,
            r.qualification_path,
            r.ti_region
        FROM analytics_team_role_maps r
        LEFT JOIN series_lookup s
          ON s.profile_id = r.profile_id
         AND s.match_id = r.match_id
         AND s.team_name = r.team_name
        WHERE r.profile_id = ?
        UNION ALL
        SELECT
            r.profile_id,
            r.match_id,
            r.match_date,
            s.series_id,
            s.series_key,
            r.team_name,
            NULL AS official_name,
            NULL AS official_position,
            NULL AS role_group,
            'support_pair' AS role_slot,
            r.support_players AS player_names,
            NULL AS account_id,
            NULL AS account_ids,
            r.stage_name,
            r.stage_bucket,
            r.avg_support_fantasy_score AS fantasy_score,
            r.ti2026_qualified,
            r.qualification_path,
            r.ti_region
        FROM analytics_team_role_maps r
        LEFT JOIN series_lookup s
          ON s.profile_id = r.profile_id
         AND s.match_id = r.match_id
         AND s.team_name = r.team_name
        WHERE r.profile_id = ?
        """,
        con,
        params=(profile_id, profile_id, profile_id, profile_id),
    )
    df = df.sort_values(["team_name", "role_slot", "match_date", "match_id"]).reset_index(drop=True)
    df["entity_type"] = "role_slot"
    df["entity_key"] = df["team_name"].astype(str) + "::" + df["role_slot"].astype(str)
    df["observation_key"] = "map:" + df["match_id"].astype(str)
    df["source_level"] = "map"
    df["aggregation_policy"] = "identity"
    df["maps_in_observation"] = 1
    df["target_score"] = df["fantasy_score"].astype(float)
    df["observation_date"] = df["match_date"]
    return df


def aggregate_frame(frame: pd.DataFrame, spec: TargetSpec) -> pd.DataFrame:
    if spec.source_level == "map":
        result = frame.copy()
        result["target_id"] = spec.target_id
        return result

    group_cols = [
        "profile_id",
        "entity_type",
        "entity_key",
        "team_name",
        "official_name",
        "official_position",
        "role_group",
        "role_slot",
        "player_names",
        "account_id",
        "account_ids",
        "series_key",
        "series_id",
        "stage_bucket",
        "stage_name",
        "ti2026_qualified",
        "qualification_path",
        "ti_region",
    ]
    rows: list[dict[str, Any]] = []
    for keys, group in frame.groupby(group_cols, dropna=False, sort=False):
        payload = dict(zip(group_cols, keys))
        group = group.sort_values(["match_date", "match_id"])
        values = group["target_score"].astype(float).tolist()
        if spec.aggregation_policy == "mean":
            target_score = safe_float(sum(values) / len(values))
        elif spec.aggregation_policy == "top1":
            target_score = safe_float(max(values))
        else:
            raise ValueError(f"Unsupported aggregation_policy={spec.aggregation_policy!r}")
        rows.append(
            {
                **payload,
                "target_id": spec.target_id,
                "observation_key": str(payload["series_key"]),
                "source_level": spec.source_level,
                "aggregation_policy": spec.aggregation_policy,
                "match_id": None,
                "observation_date": group["match_date"].min(),
                "maps_in_observation": int(len(group)),
                "target_score": target_score,
            }
        )
    return pd.DataFrame(rows)


def rebuild_target_datasets(con: sqlite3.Connection, profile_id: str | None = None) -> int:
    profile_id = profile_id or default_profile_id(con)
    now = utc_now()

    player_maps = build_player_map_frame(con, profile_id)
    role_maps = build_role_slot_map_frame(con, profile_id)
    target_frames: list[pd.DataFrame] = []
    for spec in TARGET_SPECS:
        source_frame = player_maps if spec.entity_type == "player" else role_maps
        target_frames.append(aggregate_frame(source_frame, spec))
    full = pd.concat(target_frames, ignore_index=True)
    full["created_at_utc"] = now

    ordered_cols = [
        "target_id",
        "profile_id",
        "entity_type",
        "entity_key",
        "observation_key",
        "source_level",
        "aggregation_policy",
        "team_name",
        "official_name",
        "official_position",
        "role_group",
        "role_slot",
        "player_names",
        "account_id",
        "account_ids",
        "match_id",
        "series_key",
        "series_id",
        "observation_date",
        "stage_bucket",
        "stage_name",
        "maps_in_observation",
        "target_score",
        "ti2026_qualified",
        "qualification_path",
        "ti_region",
        "created_at_utc",
    ]
    full = full[ordered_cols].copy()

    cur = con.cursor()
    cur.execute("DELETE FROM dataset_prediction_targets WHERE profile_id = ?", (profile_id,))
    cur.executemany(
        """
        INSERT OR REPLACE INTO dataset_prediction_targets(
            target_id, profile_id, entity_type, entity_key, observation_key, source_level,
            aggregation_policy, team_name, official_name, official_position, role_group,
            role_slot, player_names, account_id, account_ids, match_id, series_key, series_id,
            observation_date, stage_bucket, stage_name, maps_in_observation, target_score,
            ti2026_qualified, qualification_path, ti_region, created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [tuple(row) for row in full.itertuples(index=False, name=None)],
    )
    register_target_and_models(con)
    con.commit()
    return len(full)


def load_target_dataset(con: sqlite3.Connection, target_id: str, profile_id: str) -> pd.DataFrame:
    df = pd.read_sql_query(
        """
        SELECT *
        FROM dataset_prediction_targets
        WHERE target_id = ?
          AND profile_id = ?
        ORDER BY entity_key, observation_date, observation_key
        """,
        con,
        params=(target_id, profile_id),
    )
    df["target_score"] = df["target_score"].astype(float)
    df["observation_date"] = pd.to_datetime(df["observation_date"], errors="coerce")
    return df


def split_group_to_playoff(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = df[df["stage_bucket"] == "group_stage"].copy()
    test = df[df["stage_bucket"] != "group_stage"].copy()
    return train, test


def split_temporal_60_40(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_parts: list[pd.DataFrame] = []
    test_parts: list[pd.DataFrame] = []
    for _, group in df.groupby("entity_key", sort=False):
        group = group.sort_values(["observation_date", "observation_key"]).reset_index(drop=True)
        if len(group) < 2:
            continue
        train_n = max(1, math.ceil(len(group) * 0.60))
        if train_n >= len(group):
            train_n = len(group) - 1
        train_parts.append(group.iloc[:train_n].copy())
        test_parts.append(group.iloc[train_n:].copy())
    train = pd.concat(train_parts, ignore_index=True) if train_parts else df.iloc[0:0].copy()
    test = pd.concat(test_parts, ignore_index=True) if test_parts else df.iloc[0:0].copy()
    return train, test


def build_split(df: pd.DataFrame, split_name: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    if split_name == "group_to_playoff":
        return split_group_to_playoff(df)
    if split_name == "temporal_60_40":
        return split_temporal_60_40(df)
    raise ValueError(f"Unsupported split_name={split_name!r}")


def segment_column(df: pd.DataFrame) -> str:
    return "role_group" if df["entity_type"].iloc[0] == "player" else "role_slot"


def prepare_train_frame(train: pd.DataFrame) -> pd.DataFrame:
    frame = train.copy()
    segment_col = segment_column(frame)
    frame["team_segment_key"] = frame["team_name"].astype(str) + "::" + frame[segment_col].astype(str)
    return frame


def predict_value(
    model_id: str,
    row: pd.Series,
    train: pd.DataFrame,
    global_mean: float,
    segment_means: dict[str, float],
    entity_groups: dict[str, list[float]],
    team_segment_means: dict[str, float],
    segment_col: str,
) -> tuple[float, int, str]:
    row_segment = str(row[segment_col])
    entity_key = str(row["entity_key"])
    team_segment_key = str(row["team_segment_key"])

    segment_mean = safe_float(segment_means.get(row_segment, global_mean), global_mean)
    entity_values = entity_groups.get(entity_key, [])
    train_rows_used = len(entity_values)

    if model_id == "global_mean":
        return global_mean, int(len(train)), "global_mean"
    if model_id == "segment_mean":
        return segment_mean, int(len(train)), "segment_mean"
    if model_id == "team_segment_mean":
        if team_segment_key in team_segment_means:
            return safe_float(team_segment_means[team_segment_key], segment_mean), train_rows_used, "team_segment_mean"
        return segment_mean, train_rows_used, "segment_mean_fallback"
    if model_id == "entity_mean":
        if entity_values:
            return safe_float(sum(entity_values) / len(entity_values), segment_mean), train_rows_used, "entity_mean"
        return segment_mean, train_rows_used, "segment_mean_fallback"
    if model_id == "entity_p75":
        if entity_values:
            return percentile(entity_values, 0.75), train_rows_used, "entity_p75"
        return segment_mean, train_rows_used, "segment_mean_fallback"
    if model_id == "recent_mean_5":
        recent = entity_values[-5:]
        if recent:
            return safe_float(sum(recent) / len(recent), segment_mean), len(recent), "recent_mean_5"
        return segment_mean, train_rows_used, "segment_mean_fallback"
    if model_id == "recent_p75_5":
        recent = entity_values[-5:]
        if recent:
            return percentile(recent, 0.75), len(recent), "recent_p75_5"
        return segment_mean, train_rows_used, "segment_mean_fallback"
    if model_id == "shrunk_mean":
        team_segment_mean = safe_float(team_segment_means.get(team_segment_key, segment_mean), segment_mean)
        if not entity_values:
            return 0.65 * team_segment_mean + 0.35 * segment_mean, train_rows_used, "shrunk_team_segment"
        entity_mean = safe_float(sum(entity_values) / len(entity_values), segment_mean)
        entity_weight = min(0.80, len(entity_values) / (len(entity_values) + 5.0))
        pred = entity_weight * entity_mean + (1.0 - entity_weight) * (0.60 * team_segment_mean + 0.40 * segment_mean)
        return pred, train_rows_used, "shrunk_entity_segment"
    raise ValueError(f"Unsupported model_id={model_id!r}")


def build_predictions_for_run(
    target_id: str,
    profile_id: str,
    split_name: str,
    model_id: str,
    train: pd.DataFrame,
    test: pd.DataFrame,
) -> pd.DataFrame:
    if train.empty or test.empty:
        return test.iloc[0:0].copy()
    train = prepare_train_frame(train)
    test = test.copy()
    segment_col = segment_column(train)
    test["team_segment_key"] = test["team_name"].astype(str) + "::" + test[segment_col].astype(str)

    global_mean = safe_float(train["target_score"].mean())
    segment_means = train.groupby(segment_col)["target_score"].mean().to_dict()
    entity_groups = (
        train.sort_values(["observation_date", "observation_key"])
        .groupby("entity_key")["target_score"]
        .apply(lambda s: [safe_float(v) for v in s.tolist()])
        .to_dict()
    )
    team_segment_means = train.groupby("team_segment_key")["target_score"].mean().to_dict()

    rows: list[dict[str, Any]] = []
    for _, row in test.iterrows():
        predicted, train_rows_used, fallback_label = predict_value(
            model_id,
            row,
            train,
            global_mean,
            segment_means,
            entity_groups,
            team_segment_means,
            segment_col,
        )
        rows.append(
            {
                "target_id": target_id,
                "profile_id": profile_id,
                "split_name": split_name,
                "model_id": model_id,
                "entity_type": row["entity_type"],
                "entity_key": row["entity_key"],
                "observation_key": row["observation_key"],
                "team_name": row["team_name"],
                "official_name": row["official_name"],
                "official_position": row["official_position"],
                "role_group": row["role_group"],
                "role_slot": row["role_slot"],
                "player_names": row["player_names"],
                "account_id": row["account_id"],
                "account_ids": row["account_ids"],
                "match_id": row["match_id"],
                "series_key": row["series_key"],
                "series_id": row["series_id"],
                "observation_date": row["observation_date"],
                "stage_bucket": row["stage_bucket"],
                "actual_score": safe_float(row["target_score"]),
                "predicted_score": safe_float(predicted),
                "abs_error": abs(safe_float(row["target_score"]) - safe_float(predicted)),
                "train_rows_used": int(train_rows_used),
                "fallback_label": fallback_label,
            }
        )
    return pd.DataFrame(rows)


def compute_run_metrics(predictions: pd.DataFrame) -> list[tuple[str, float, str]]:
    if predictions.empty:
        return []
    actual = predictions["actual_score"].astype(float)
    predicted = predictions["predicted_score"].astype(float)
    metrics: list[tuple[str, float, str]] = [
        ("rows_tested", float(len(predictions)), "row"),
        ("mae", float((actual - predicted).abs().mean()), "row"),
        ("rmse", float((((actual - predicted) ** 2).mean()) ** 0.5), "row"),
        ("median_ae", float((actual - predicted).abs().median()), "row"),
        ("spearman", spearman_corr(actual, predicted), "row"),
    ]
    entity_frame = (
        predictions.groupby("entity_key", as_index=False)
        .agg(predicted_score=("predicted_score", "mean"), actual_score=("actual_score", "mean"))
        .set_index("entity_key")
    )
    metrics.extend(
        [
            ("entities_tested", float(len(entity_frame)), "entity"),
            ("entity_spearman", spearman_corr(entity_frame["actual_score"], entity_frame["predicted_score"]), "entity"),
            ("top3_overlap", top_k_overlap(entity_frame["actual_score"], entity_frame["predicted_score"], 3), "entity"),
            ("top5_overlap", top_k_overlap(entity_frame["actual_score"], entity_frame["predicted_score"], 5), "entity"),
            ("top10_overlap", top_k_overlap(entity_frame["actual_score"], entity_frame["predicted_score"], 10), "entity"),
            ("ndcg_5", ndcg_at_k(entity_frame["actual_score"], entity_frame["predicted_score"], 5), "entity"),
            ("ndcg_10", ndcg_at_k(entity_frame["actual_score"], entity_frame["predicted_score"], 10), "entity"),
        ]
    )
    actual_best = float(entity_frame["actual_score"].max()) if not entity_frame.empty else 0.0
    predicted_best_key = entity_frame["predicted_score"].idxmax() if not entity_frame.empty else None
    regret_at_1 = 0.0
    if predicted_best_key is not None:
        regret_at_1 = actual_best - safe_float(entity_frame.loc[predicted_best_key, "actual_score"])
    metrics.append(("regret_at_1", regret_at_1, "entity"))
    return metrics


def store_run(
    con: sqlite3.Connection,
    target_id: str,
    profile_id: str,
    split: SplitDefinition,
    model_id: str,
    predictions: pd.DataFrame,
) -> str:
    run_id = f"foundation::{target_id}::{split.split_name}::{model_id}"
    now = utc_now()
    cur = con.cursor()
    cur.execute("DELETE FROM foundation_prediction_outputs WHERE run_id = ?", (run_id,))
    cur.execute("DELETE FROM foundation_evaluation_reports WHERE run_id = ?", (run_id,))
    cur.execute("DELETE FROM foundation_prediction_runs WHERE run_id = ?", (run_id,))
    cur.execute(
        """
        INSERT INTO foundation_prediction_runs(
            run_id, target_id, profile_id, split_name, model_id, train_label, test_label, notes, created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            target_id,
            profile_id,
            split.split_name,
            model_id,
            split.train_label,
            split.test_label,
            "Foundation prediction layer built from map-first targets and generic aggregation policies.",
            now,
        ),
    )
    if not predictions.empty:
        rows = []
        for row in predictions.itertuples(index=False):
            rows.append(
                (
                    run_id,
                    row.target_id,
                    row.profile_id,
                    row.split_name,
                    row.model_id,
                    row.entity_type,
                    row.entity_key,
                    row.observation_key,
                    row.team_name,
                    row.official_name,
                    None if pd.isna(row.official_position) else int(row.official_position),
                    row.role_group,
                    row.role_slot,
                    row.player_names,
                    None if pd.isna(row.account_id) else int(row.account_id),
                    row.account_ids,
                    None if pd.isna(row.match_id) else int(row.match_id),
                    row.series_key,
                    None if pd.isna(row.series_id) else int(row.series_id),
                    None if pd.isna(row.observation_date) else str(pd.Timestamp(row.observation_date).date()),
                    row.stage_bucket,
                    float(row.actual_score),
                    float(row.predicted_score),
                    float(row.abs_error),
                    int(row.train_rows_used),
                    row.fallback_label,
                    now,
                )
            )
        cur.executemany(
            """
            INSERT OR REPLACE INTO foundation_prediction_outputs(
                run_id, target_id, profile_id, split_name, model_id, entity_type, entity_key, observation_key,
                team_name, official_name, official_position, role_group, role_slot, player_names, account_id,
                account_ids, match_id, series_key, series_id, observation_date, stage_bucket, actual_score,
                predicted_score, abs_error, train_rows_used, fallback_label, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    for metric_name, metric_value, metric_scope in compute_run_metrics(predictions):
        cur.execute(
            """
            INSERT OR REPLACE INTO foundation_evaluation_reports(run_id, metric_name, metric_value, metric_scope, created_at_utc)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, metric_name, float(metric_value), metric_scope, now),
        )
    con.commit()
    return run_id


def build_prediction_foundation(db_path: Path = DB_PATH) -> dict[str, Any]:
    con = sqlite3.connect(str(db_path))
    try:
        create_schema(con)
        profile_id = default_profile_id(con)
        target_rows = rebuild_target_datasets(con, profile_id=profile_id)

        run_ids: list[str] = []
        for spec in TARGET_SPECS:
            df = load_target_dataset(con, spec.target_id, profile_id)
            for split in SPLITS:
                train, test = build_split(df, split.split_name)
                if train.empty or test.empty:
                    continue
                for model_id in BASELINE_MODELS:
                    predictions = build_predictions_for_run(spec.target_id, profile_id, split.split_name, model_id, train, test)
                    run_ids.append(store_run(con, spec.target_id, profile_id, split, model_id, predictions))

        summary = pd.read_sql_query(
            """
            SELECT
                r.target_id,
                r.split_name,
                r.model_id,
                MAX(CASE WHEN e.metric_name = 'mae' AND e.metric_scope = 'row' THEN e.metric_value END) AS mae,
                MAX(CASE WHEN e.metric_name = 'spearman' AND e.metric_scope = 'row' THEN e.metric_value END) AS spearman_row,
                MAX(CASE WHEN e.metric_name = 'entity_spearman' AND e.metric_scope = 'entity' THEN e.metric_value END) AS spearman_entity,
                MAX(CASE WHEN e.metric_name = 'top5_overlap' AND e.metric_scope = 'entity' THEN e.metric_value END) AS top5_overlap,
                MAX(CASE WHEN e.metric_name = 'regret_at_1' AND e.metric_scope = 'entity' THEN e.metric_value END) AS regret_at_1
            FROM foundation_prediction_runs r
            JOIN foundation_evaluation_reports e
              ON e.run_id = r.run_id
            WHERE r.profile_id = ?
            GROUP BY r.target_id, r.split_name, r.model_id
            ORDER BY r.target_id, r.split_name, mae ASC, spearman_entity DESC
            """,
            con,
            params=(profile_id,),
        )
        return {
            "profile_id": profile_id,
            "target_rows": target_rows,
            "run_ids": run_ids,
            "summary": summary,
        }
    finally:
        con.close()
