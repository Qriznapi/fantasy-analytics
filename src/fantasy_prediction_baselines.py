from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from fantasy_banner_optimizer import default_profile_id, player_series, role_slot_series
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


def spearman_corr(actual: pd.Series, predicted: pd.Series) -> float:
    if len(actual) < 2 or len(predicted) < 2:
        return 0.0
    ranked_actual = actual.rank(method="average")
    ranked_predicted = predicted.rank(method="average")
    corr = ranked_actual.corr(ranked_predicted, method="pearson")
    if pd.isna(corr):
        return 0.0
    return float(corr)


@dataclass(frozen=True)
class SplitDefinition:
    split_name: str
    train_label: str
    test_label: str


PLAYER_SERIES_TARGET = "player_series_best2"
ROLE_SLOT_SERIES_TARGET = "role_slot_series_best2"

BASELINE_MODELS = (
    "global_mean",
    "role_mean",
    "entity_mean",
    "entity_p75",
    "recent_mean_3",
    "recent_p75_3",
    "team_role_mean",
    "shrunk_mean",
)

SPLITS = (
    SplitDefinition("group_to_playoff", "group_stage_only", "non_group_stage"),
    SplitDefinition("temporal_60_40", "first_60_percent_per_entity", "last_40_percent_per_entity"),
)


def create_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS dataset_player_series_targets (
            profile_id TEXT NOT NULL,
            entity_key TEXT NOT NULL,
            account_id INTEGER NOT NULL,
            team_name TEXT NOT NULL,
            official_name TEXT,
            official_position INTEGER,
            role_group TEXT,
            series_key TEXT NOT NULL,
            series_id INTEGER,
            series_start_date TEXT,
            stage_bucket TEXT,
            best2_series_score REAL NOT NULL,
            ti2026_qualified INTEGER NOT NULL,
            qualification_path TEXT,
            ti_region TEXT,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (profile_id, entity_key, series_key)
        );

        CREATE TABLE IF NOT EXISTS dataset_role_slot_series_targets (
            profile_id TEXT NOT NULL,
            entity_key TEXT NOT NULL,
            team_name TEXT NOT NULL,
            role_slot TEXT NOT NULL,
            player_names TEXT,
            account_ids TEXT,
            series_key TEXT NOT NULL,
            series_id INTEGER,
            series_start_date TEXT,
            stage_bucket TEXT,
            best2_series_score REAL NOT NULL,
            ti2026_qualified INTEGER NOT NULL,
            qualification_path TEXT,
            ti_region TEXT,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (profile_id, entity_key, series_key)
        );

        CREATE TABLE IF NOT EXISTS baseline_model_registry (
            model_id TEXT PRIMARY KEY,
            target_type TEXT NOT NULL,
            description TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS baseline_prediction_runs (
            run_id TEXT PRIMARY KEY,
            target_type TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            split_name TEXT NOT NULL,
            model_id TEXT NOT NULL,
            train_label TEXT NOT NULL,
            test_label TEXT NOT NULL,
            notes TEXT,
            created_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS baseline_prediction_outputs (
            run_id TEXT NOT NULL,
            entity_key TEXT NOT NULL,
            series_key TEXT NOT NULL,
            target_type TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            split_name TEXT NOT NULL,
            model_id TEXT NOT NULL,
            team_name TEXT NOT NULL,
            official_name TEXT,
            official_position INTEGER,
            role_group TEXT,
            role_slot TEXT,
            stage_bucket TEXT,
            actual_score REAL NOT NULL,
            predicted_score REAL NOT NULL,
            abs_error REAL NOT NULL,
            train_rows_used INTEGER NOT NULL,
            fallback_label TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, entity_key, series_key)
        );

        CREATE TABLE IF NOT EXISTS baseline_evaluation_reports (
            run_id TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            metric_value REAL NOT NULL,
            metric_scope TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (run_id, metric_name, metric_scope)
        );

        DROP VIEW IF EXISTS analytics_baseline_evaluation;
        CREATE VIEW analytics_baseline_evaluation AS
        SELECT
            r.run_id,
            r.target_type,
            r.profile_id,
            r.split_name,
            r.model_id,
            e.metric_name,
            e.metric_value,
            e.metric_scope,
            r.created_at_utc
        FROM baseline_prediction_runs r
        JOIN baseline_evaluation_reports e
          ON e.run_id = r.run_id;
        """
    )


def rebuild_series_datasets(con: sqlite3.Connection, profile_id: str | None = None) -> tuple[int, int]:
    profile_id = profile_id or default_profile_id(con)
    now = utc_now()

    player_df = player_series(con, profile_id, ti2026_only=False).copy()
    player_df["entity_key"] = player_df["team_name"].astype(str) + "::" + player_df["account_id"].astype(str)
    player_rows = [
        (
            profile_id,
            row["entity_key"],
            int(row["account_id"]),
            row["team_name"],
            row["official_name"],
            None if pd.isna(row["official_position"]) else int(row["official_position"]),
            row["role_group"],
            row["series_key"],
            None if pd.isna(row["series_id"]) else int(row["series_id"]),
            row["series_start_date"],
            row["stage_bucket"],
            safe_float(row["best2_series_score"]),
            int(row["ti2026_qualified"]),
            row["qualification_path"],
            row["ti_region"],
            now,
        )
        for _, row in player_df.iterrows()
    ]

    role_df = role_slot_series(con, profile_id, ti2026_only=False).copy()
    role_df["entity_key"] = role_df["team_name"].astype(str) + "::" + role_df["role_slot"].astype(str)
    role_rows = [
        (
            profile_id,
            row["entity_key"],
            row["team_name"],
            row["role_slot"],
            row["player_names"],
            row["account_ids"],
            row["series_key"],
            None if pd.isna(row["series_id"]) else int(row["series_id"]),
            row["series_start_date"],
            row["stage_bucket"],
            safe_float(row["best2_series_score"]),
            int(row["ti2026_qualified"]),
            row["qualification_path"],
            row["ti_region"],
            now,
        )
        for _, row in role_df.iterrows()
    ]

    cur = con.cursor()
    cur.execute("DELETE FROM dataset_player_series_targets WHERE profile_id = ?", (profile_id,))
    cur.execute("DELETE FROM dataset_role_slot_series_targets WHERE profile_id = ?", (profile_id,))
    cur.executemany(
        """
        INSERT OR REPLACE INTO dataset_player_series_targets(
            profile_id, entity_key, account_id, team_name, official_name, official_position,
            role_group, series_key, series_id, series_start_date, stage_bucket,
            best2_series_score, ti2026_qualified, qualification_path, ti_region, created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        player_rows,
    )
    cur.executemany(
        """
        INSERT OR REPLACE INTO dataset_role_slot_series_targets(
            profile_id, entity_key, team_name, role_slot, player_names, account_ids,
            series_key, series_id, series_start_date, stage_bucket, best2_series_score,
            ti2026_qualified, qualification_path, ti_region, created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        role_rows,
    )
    register_models(con)
    con.commit()
    return len(player_rows), len(role_rows)


def register_models(con: sqlite3.Connection) -> None:
    now = utc_now()
    descriptions = {
        "global_mean": "Single global train mean.",
        "role_mean": "Mean inside role_group or role_slot.",
        "entity_mean": "Historical entity mean with role/global fallback.",
        "entity_p75": "Historical entity p75 with role/global fallback.",
        "recent_mean_3": "Mean over the last three train series for the entity.",
        "recent_p75_3": "P75 over the last three train series for the entity.",
        "team_role_mean": "Mean inside team+role_group or team+role_slot.",
        "shrunk_mean": "Shrink entity mean toward team-role and role means.",
    }
    cur = con.cursor()
    for target_type in (PLAYER_SERIES_TARGET, ROLE_SLOT_SERIES_TARGET):
        for model_id, description in descriptions.items():
            cur.execute(
                """
                INSERT OR REPLACE INTO baseline_model_registry(model_id, target_type, description, created_at_utc)
                VALUES (?, ?, ?, ?)
                """,
                (model_id, target_type, description, now),
            )


def load_dataset(con: sqlite3.Connection, target_type: str, profile_id: str) -> pd.DataFrame:
    if target_type == PLAYER_SERIES_TARGET:
        df = pd.read_sql_query(
            """
            SELECT profile_id, entity_key, account_id, team_name, official_name, official_position,
                   role_group, series_key, series_id, series_start_date, stage_bucket,
                   best2_series_score, ti2026_qualified, qualification_path, ti_region
            FROM dataset_player_series_targets
            WHERE profile_id = ?
            ORDER BY entity_key, series_start_date, series_key
            """,
            con,
            params=(profile_id,),
        )
    elif target_type == ROLE_SLOT_SERIES_TARGET:
        df = pd.read_sql_query(
            """
            SELECT profile_id, entity_key, team_name, role_slot, player_names, account_ids,
                   series_key, series_id, series_start_date, stage_bucket,
                   best2_series_score, ti2026_qualified, qualification_path, ti_region
            FROM dataset_role_slot_series_targets
            WHERE profile_id = ?
            ORDER BY entity_key, series_start_date, series_key
            """,
            con,
            params=(profile_id,),
        )
    else:
        raise ValueError(f"Unsupported target_type={target_type!r}")
    df["best2_series_score"] = df["best2_series_score"].astype(float)
    df["series_start_date"] = pd.to_datetime(df["series_start_date"], errors="coerce")
    return df


def split_group_to_playoff(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = df[df["stage_bucket"] == "group_stage"].copy()
    test = df[df["stage_bucket"] != "group_stage"].copy()
    return train, test


def split_temporal_60_40(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_parts: list[pd.DataFrame] = []
    test_parts: list[pd.DataFrame] = []
    for _, group in df.groupby("entity_key", sort=False):
        group = group.sort_values(["series_start_date", "series_key"]).reset_index(drop=True)
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


def role_column(target_type: str) -> str:
    return "role_group" if target_type == PLAYER_SERIES_TARGET else "role_slot"


def team_role_column(target_type: str) -> str:
    return "team_role_key"


def prepare_train_frame(train: pd.DataFrame, target_type: str) -> pd.DataFrame:
    frame = train.copy()
    role_col = role_column(target_type)
    frame[team_role_column(target_type)] = frame["team_name"].astype(str) + "::" + frame[role_col].astype(str)
    return frame


def entity_recent_values(train: pd.DataFrame, entity_key: str, limit: int) -> list[float]:
    values = (
        train.loc[train["entity_key"] == entity_key]
        .sort_values(["series_start_date", "series_key"])["best2_series_score"]
        .astype(float)
        .tolist()
    )
    if not values:
        return []
    return values[-limit:]


def predict_value(
    model_id: str,
    row: pd.Series,
    train: pd.DataFrame,
    target_type: str,
    global_mean: float,
    role_means: dict[str, float],
    entity_groups: dict[str, list[float]],
    team_role_means: dict[str, float],
) -> tuple[float, int, str]:
    role_col = role_column(target_type)
    row_role = str(row[role_col])
    entity_key = str(row["entity_key"])
    team_role_key = str(row[team_role_column(target_type)])

    role_mean = safe_float(role_means.get(row_role, global_mean), global_mean)
    entity_values = entity_groups.get(entity_key, [])
    train_rows_used = len(entity_values)

    if model_id == "global_mean":
        return global_mean, int(len(train)), "global_mean"
    if model_id == "role_mean":
        return role_mean, int(len(train)), "role_mean"
    if model_id == "team_role_mean":
        if team_role_key in team_role_means:
            return safe_float(team_role_means[team_role_key], role_mean), train_rows_used, "team_role_mean"
        return role_mean, train_rows_used, "role_mean_fallback"
    if model_id == "entity_mean":
        if entity_values:
            return safe_float(sum(entity_values) / len(entity_values), role_mean), train_rows_used, "entity_mean"
        return role_mean, train_rows_used, "role_mean_fallback"
    if model_id == "entity_p75":
        if entity_values:
            return percentile(entity_values, 0.75), train_rows_used, "entity_p75"
        return role_mean, train_rows_used, "role_mean_fallback"
    if model_id == "recent_mean_3":
        recent = entity_values[-3:]
        if recent:
            return safe_float(sum(recent) / len(recent), role_mean), len(recent), "recent_mean_3"
        return role_mean, train_rows_used, "role_mean_fallback"
    if model_id == "recent_p75_3":
        recent = entity_values[-3:]
        if recent:
            return percentile(recent, 0.75), len(recent), "recent_p75_3"
        return role_mean, train_rows_used, "role_mean_fallback"
    if model_id == "shrunk_mean":
        team_role_mean = safe_float(team_role_means.get(team_role_key, role_mean), role_mean)
        if not entity_values:
            return 0.65 * team_role_mean + 0.35 * role_mean, train_rows_used, "shrunk_team_role"
        entity_mean = safe_float(sum(entity_values) / len(entity_values), role_mean)
        player_weight = min(0.80, len(entity_values) / (len(entity_values) + 5.0))
        pred = player_weight * entity_mean + (1.0 - player_weight) * (0.60 * team_role_mean + 0.40 * role_mean)
        return pred, train_rows_used, "shrunk_entity_role"
    raise ValueError(f"Unsupported baseline model_id={model_id!r}")


def build_predictions_for_run(
    profile_id: str,
    target_type: str,
    split_name: str,
    model_id: str,
    train: pd.DataFrame,
    test: pd.DataFrame,
) -> pd.DataFrame:
    if train.empty or test.empty:
        return test.iloc[0:0].copy()
    role_col = role_column(target_type)
    train = prepare_train_frame(train, target_type)
    test = test.copy()
    test[team_role_column(target_type)] = test["team_name"].astype(str) + "::" + test[role_col].astype(str)

    global_mean = safe_float(train["best2_series_score"].mean())
    role_means = train.groupby(role_col)["best2_series_score"].mean().to_dict()
    entity_groups = (
        train.sort_values(["series_start_date", "series_key"])
        .groupby("entity_key")["best2_series_score"]
        .apply(lambda s: [safe_float(v) for v in s.tolist()])
        .to_dict()
    )
    team_role_means = train.groupby(team_role_column(target_type))["best2_series_score"].mean().to_dict()

    rows: list[dict[str, Any]] = []
    for _, row in test.iterrows():
        predicted, train_rows_used, fallback_label = predict_value(
            model_id,
            row,
            train,
            target_type,
            global_mean,
            role_means,
            entity_groups,
            team_role_means,
        )
        rows.append(
            {
                "profile_id": profile_id,
                "target_type": target_type,
                "split_name": split_name,
                "model_id": model_id,
                "entity_key": row["entity_key"],
                "series_key": row["series_key"],
                "team_name": row["team_name"],
                "official_name": row["official_name"] if "official_name" in row else None,
                "official_position": row["official_position"] if "official_position" in row else None,
                "role_group": row["role_group"] if "role_group" in row else None,
                "role_slot": row["role_slot"] if "role_slot" in row else None,
                "stage_bucket": row["stage_bucket"],
                "actual_score": safe_float(row["best2_series_score"]),
                "predicted_score": safe_float(predicted),
                "abs_error": abs(safe_float(row["best2_series_score"]) - safe_float(predicted)),
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
    ]
    metrics.append(("spearman", spearman_corr(actual, predicted), "row"))

    entity_frame = (
        predictions.groupby("entity_key", as_index=False)
        .agg(
            predicted_score=("predicted_score", "mean"),
            actual_score=("actual_score", "mean"),
        )
        .set_index("entity_key")
    )
    entity_actual = entity_frame["actual_score"]
    entity_predicted = entity_frame["predicted_score"]
    entity_spearman = spearman_corr(entity_actual, entity_predicted)
    metrics.extend(
        [
            ("entities_tested", float(len(entity_frame)), "entity"),
            ("entity_spearman", entity_spearman, "entity"),
            ("top3_overlap", float(top_k_overlap(entity_actual, entity_predicted, 3)), "entity"),
            ("top5_overlap", float(top_k_overlap(entity_actual, entity_predicted, 5)), "entity"),
            ("top10_overlap", float(top_k_overlap(entity_actual, entity_predicted, 10)), "entity"),
            ("ndcg_at_5", float(ndcg_at_k(entity_actual, entity_predicted, 5)), "entity"),
            ("ndcg_at_10", float(ndcg_at_k(entity_actual, entity_predicted, 10)), "entity"),
        ]
    )

    oracle_best = float(entity_actual.max()) if len(entity_actual) else 0.0
    predicted_top1 = entity_frame.sort_values("predicted_score", ascending=False).head(1)["actual_score"]
    predicted_top3 = entity_frame.sort_values("predicted_score", ascending=False).head(3)["actual_score"]
    top1_actual = float(predicted_top1.iloc[0]) if len(predicted_top1) else 0.0
    top3_best = float(predicted_top3.max()) if len(predicted_top3) else 0.0
    metrics.extend(
        [
            ("regret_at_1", oracle_best - top1_actual, "entity"),
            ("regret_at_3_best", oracle_best - top3_best, "entity"),
        ]
    )
    return metrics


def persist_run(
    con: sqlite3.Connection,
    run_id: str,
    profile_id: str,
    target_type: str,
    split: SplitDefinition,
    model_id: str,
    predictions: pd.DataFrame,
) -> None:
    cur = con.cursor()
    now = utc_now()
    cur.execute("DELETE FROM baseline_prediction_outputs WHERE run_id = ?", (run_id,))
    cur.execute("DELETE FROM baseline_evaluation_reports WHERE run_id = ?", (run_id,))
    cur.execute("DELETE FROM baseline_prediction_runs WHERE run_id = ?", (run_id,))
    cur.execute(
        """
        INSERT INTO baseline_prediction_runs(
            run_id, target_type, profile_id, split_name, model_id,
            train_label, test_label, notes, created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            target_type,
            profile_id,
            split.split_name,
            model_id,
            split.train_label,
            split.test_label,
            "Baseline evaluation over best2 series targets.",
            now,
        ),
    )

    if not predictions.empty:
        rows = []
        for _, row in predictions.iterrows():
            rows.append(
                (
                    run_id,
                    row["entity_key"],
                    row["series_key"],
                    target_type,
                    profile_id,
                    split.split_name,
                    model_id,
                    row["team_name"],
                    row["official_name"],
                    None if pd.isna(row["official_position"]) else int(row["official_position"]),
                    row["role_group"],
                    row["role_slot"],
                    row["stage_bucket"],
                    safe_float(row["actual_score"]),
                    safe_float(row["predicted_score"]),
                    safe_float(row["abs_error"]),
                    int(row["train_rows_used"]),
                    row["fallback_label"],
                    now,
                )
            )
        cur.executemany(
            """
            INSERT OR REPLACE INTO baseline_prediction_outputs(
                run_id, entity_key, series_key, target_type, profile_id, split_name, model_id,
                team_name, official_name, official_position, role_group, role_slot, stage_bucket,
                actual_score, predicted_score, abs_error, train_rows_used, fallback_label, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    metric_rows = [
        (run_id, metric_name, safe_float(metric_value), metric_scope, now)
        for metric_name, metric_value, metric_scope in compute_run_metrics(predictions)
    ]
    cur.executemany(
        """
        INSERT OR REPLACE INTO baseline_evaluation_reports(
            run_id, metric_name, metric_value, metric_scope, created_at_utc
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        metric_rows,
    )
    con.commit()


def run_all_baselines(con: sqlite3.Connection, profile_id: str | None = None) -> list[str]:
    profile_id = profile_id or default_profile_id(con)
    run_ids: list[str] = []
    for target_type in (PLAYER_SERIES_TARGET, ROLE_SLOT_SERIES_TARGET):
        dataset = load_dataset(con, target_type, profile_id)
        for split in SPLITS:
            train, test = build_split(dataset, split.split_name)
            for model_id in BASELINE_MODELS:
                run_id = f"baseline_{profile_id}_{target_type}_{split.split_name}_{model_id}"
                predictions = build_predictions_for_run(profile_id, target_type, split.split_name, model_id, train, test)
                persist_run(con, run_id, profile_id, target_type, split, model_id, predictions)
                run_ids.append(run_id)
    return run_ids


def build_prediction_baselines(db_path: Path = DB_PATH, profile_id: str | None = None) -> dict[str, Any]:
    con = sqlite3.connect(db_path)
    try:
        create_schema(con)
        profile_id = profile_id or default_profile_id(con)
        player_rows, role_rows = rebuild_series_datasets(con, profile_id)
        run_ids = run_all_baselines(con, profile_id)
        summary = pd.read_sql_query(
            """
            SELECT run_id, target_type, split_name, model_id,
                   MAX(CASE WHEN metric_name = 'mae' THEN metric_value END) AS mae,
                   MAX(CASE WHEN metric_name = 'spearman' THEN metric_value END) AS spearman,
                   MAX(CASE WHEN metric_name = 'top5_overlap' THEN metric_value END) AS top5_overlap,
                   MAX(CASE WHEN metric_name = 'regret_at_1' THEN metric_value END) AS regret_at_1
            FROM analytics_baseline_evaluation
            WHERE profile_id = ?
            GROUP BY run_id, target_type, split_name, model_id
            ORDER BY target_type, split_name, mae ASC, top5_overlap DESC
            """,
            con,
            params=(profile_id,),
        )
        return {
            "profile_id": profile_id,
            "player_rows": player_rows,
            "role_slot_rows": role_rows,
            "run_ids": run_ids,
            "summary": summary,
        }
    finally:
        con.close()
