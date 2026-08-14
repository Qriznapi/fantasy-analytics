from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from fantasy_prediction_foundation import (
    DB_PATH,
    build_predictions_for_run as build_baseline_predictions,
    create_schema,
    default_profile_id,
    load_target_dataset,
    safe_float,
    utc_now,
)
from fantasy_prediction_gbdt import build_predictions_for_run as build_gbdt_predictions
from fantasy_prediction_quantile import build_predictions_for_run as build_quantile_predictions
from fantasy_prediction_ridge import build_predictions_for_run as build_ridge_predictions


DEFAULT_SPLIT_NAME = "temporal_60_40"
DEFAULT_PLAYER_TARGET = "player_series_top1"
DEFAULT_ROLE_SLOT_TARGET = "role_slot_series_top1"


def create_production_schema(con: sqlite3.Connection) -> None:
    create_schema(con)
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS production_prediction_model_choices (
            target_id TEXT NOT NULL,
            split_name TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            chosen_family TEXT NOT NULL,
            chosen_model_id TEXT NOT NULL,
            param_a REAL,
            param_b REAL,
            metric_entity_spearman REAL NOT NULL,
            metric_ndcg_5 REAL NOT NULL,
            metric_top5_overlap REAL NOT NULL,
            metric_mae REAL NOT NULL,
            metric_regret_at_1 REAL NOT NULL,
            selection_reason TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (target_id, split_name)
        );

        CREATE TABLE IF NOT EXISTS production_prediction_entity_scores (
            target_id TEXT NOT NULL,
            split_name TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_key TEXT NOT NULL,
            chosen_family TEXT NOT NULL,
            chosen_model_id TEXT NOT NULL,
            team_name TEXT NOT NULL,
            official_name TEXT,
            official_position INTEGER,
            role_group TEXT,
            role_slot TEXT,
            player_names TEXT,
            account_id INTEGER,
            account_ids TEXT,
            latest_match_id INTEGER,
            latest_series_key TEXT,
            latest_series_id INTEGER,
            latest_observation_date TEXT,
            latest_stage_bucket TEXT,
            maps_observed INTEGER NOT NULL,
            predicted_score REAL NOT NULL,
            q25 REAL,
            q50 REAL,
            q75 REAL,
            q90 REAL,
            train_rows_used INTEGER NOT NULL,
            created_at_utc TEXT NOT NULL,
            PRIMARY KEY (target_id, split_name, entity_key)
        );

        DROP VIEW IF EXISTS analytics_prediction_production_players;
        CREATE VIEW analytics_prediction_production_players AS
        SELECT
            s.target_id,
            s.split_name,
            s.profile_id,
            s.entity_key,
            s.chosen_family,
            s.chosen_model_id,
            s.team_name,
            s.official_name,
            s.official_position,
            s.role_group,
            s.predicted_score,
            s.q25,
            s.q50,
            s.q75,
            s.q90,
            s.maps_observed,
            s.train_rows_used,
            s.latest_observation_date,
            c.metric_entity_spearman,
            c.metric_ndcg_5,
            c.metric_top5_overlap,
            c.metric_mae,
            c.metric_regret_at_1
        FROM production_prediction_entity_scores s
        JOIN production_prediction_model_choices c
          ON c.target_id = s.target_id
         AND c.split_name = s.split_name
        WHERE s.entity_type = 'player';

        DROP VIEW IF EXISTS analytics_prediction_production_role_slots;
        CREATE VIEW analytics_prediction_production_role_slots AS
        SELECT
            s.target_id,
            s.split_name,
            s.profile_id,
            s.entity_key,
            s.chosen_family,
            s.chosen_model_id,
            s.team_name,
            s.role_slot,
            s.player_names,
            s.predicted_score,
            s.q25,
            s.q50,
            s.q75,
            s.q90,
            s.maps_observed,
            s.train_rows_used,
            s.latest_observation_date,
            c.metric_entity_spearman,
            c.metric_ndcg_5,
            c.metric_top5_overlap,
            c.metric_mae,
            c.metric_regret_at_1
        FROM production_prediction_entity_scores s
        JOIN production_prediction_model_choices c
          ON c.target_id = s.target_id
         AND c.split_name = s.split_name
        WHERE s.entity_type = 'role_slot';

        DROP VIEW IF EXISTS analytics_prediction_production_model_choices;
        CREATE VIEW analytics_prediction_production_model_choices AS
        SELECT *
        FROM production_prediction_model_choices;
        """
    )
    con.commit()


def collect_candidates(con: sqlite3.Connection) -> pd.DataFrame:
    baseline = pd.read_sql_query(
        """
        SELECT
            r.target_id,
            r.split_name,
            r.model_id AS source_model_id,
            'baseline' AS chosen_family,
            NULL AS param_a,
            NULL AS param_b,
            MAX(CASE WHEN e.metric_name = 'mae' AND e.metric_scope = 'row' THEN e.metric_value END) AS mae,
            MAX(CASE WHEN e.metric_name = 'entity_spearman' AND e.metric_scope = 'entity' THEN e.metric_value END) AS entity_spearman,
            MAX(CASE WHEN e.metric_name = 'top5_overlap' AND e.metric_scope = 'entity' THEN e.metric_value END) AS top5_overlap,
            MAX(CASE WHEN e.metric_name = 'ndcg_5' AND e.metric_scope = 'entity' THEN e.metric_value END) AS ndcg_5,
            MAX(CASE WHEN e.metric_name = 'regret_at_1' AND e.metric_scope = 'entity' THEN e.metric_value END) AS regret_at_1
        FROM foundation_prediction_runs r
        JOIN foundation_evaluation_reports e
          ON e.run_id = r.run_id
        GROUP BY r.target_id, r.split_name, r.model_id
        """,
        con,
    )
    ridge = pd.read_sql_query(
        """
        SELECT
            r.target_id,
            r.split_name,
            r.model_id AS source_model_id,
            'ridge' AS chosen_family,
            r.alpha AS param_a,
            NULL AS param_b,
            MAX(CASE WHEN e.metric_name = 'mae' AND e.metric_scope = 'row' THEN e.metric_value END) AS mae,
            MAX(CASE WHEN e.metric_name = 'entity_spearman' AND e.metric_scope = 'entity' THEN e.metric_value END) AS entity_spearman,
            MAX(CASE WHEN e.metric_name = 'top5_overlap' AND e.metric_scope = 'entity' THEN e.metric_value END) AS top5_overlap,
            MAX(CASE WHEN e.metric_name = 'ndcg_5' AND e.metric_scope = 'entity' THEN e.metric_value END) AS ndcg_5,
            MAX(CASE WHEN e.metric_name = 'regret_at_1' AND e.metric_scope = 'entity' THEN e.metric_value END) AS regret_at_1
        FROM ridge_prediction_runs r
        JOIN ridge_evaluation_reports e
          ON e.run_id = r.run_id
        GROUP BY r.target_id, r.split_name, r.model_id, r.alpha
        """,
        con,
    )
    quantile = pd.read_sql_query(
        """
        SELECT
            r.target_id,
            r.split_name,
            r.model_id AS source_model_id,
            'quantile' AS chosen_family,
            NULL AS param_a,
            NULL AS param_b,
            MAX(CASE WHEN e.metric_name = 'mae' AND e.metric_scope = 'row' THEN e.metric_value END) AS mae,
            MAX(CASE WHEN e.metric_name = 'entity_spearman' AND e.metric_scope = 'entity' THEN e.metric_value END) AS entity_spearman,
            MAX(CASE WHEN e.metric_name = 'top5_overlap' AND e.metric_scope = 'entity' THEN e.metric_value END) AS top5_overlap,
            MAX(CASE WHEN e.metric_name = 'ndcg_5' AND e.metric_scope = 'entity' THEN e.metric_value END) AS ndcg_5,
            MAX(CASE WHEN e.metric_name = 'regret_at_1' AND e.metric_scope = 'entity' THEN e.metric_value END) AS regret_at_1
        FROM quantile_prediction_runs r
        JOIN quantile_evaluation_reports e
          ON e.run_id = r.run_id
        GROUP BY r.target_id, r.split_name, r.model_id
        """,
        con,
    )
    gbdt = pd.read_sql_query(
        """
        SELECT
            r.target_id,
            r.split_name,
            r.model_id AS source_model_id,
            'gbdt' AS chosen_family,
            r.n_estimators AS param_a,
            r.learning_rate AS param_b,
            MAX(CASE WHEN e.metric_name = 'mae' AND e.metric_scope = 'row' THEN e.metric_value END) AS mae,
            MAX(CASE WHEN e.metric_name = 'entity_spearman' AND e.metric_scope = 'entity' THEN e.metric_value END) AS entity_spearman,
            MAX(CASE WHEN e.metric_name = 'top5_overlap' AND e.metric_scope = 'entity' THEN e.metric_value END) AS top5_overlap,
            MAX(CASE WHEN e.metric_name = 'ndcg_5' AND e.metric_scope = 'entity' THEN e.metric_value END) AS ndcg_5,
            MAX(CASE WHEN e.metric_name = 'regret_at_1' AND e.metric_scope = 'entity' THEN e.metric_value END) AS regret_at_1
        FROM gbdt_prediction_runs r
        JOIN gbdt_evaluation_reports e
          ON e.run_id = r.run_id
        GROUP BY r.target_id, r.split_name, r.model_id, r.n_estimators, r.learning_rate
        """,
        con,
    )
    return pd.concat([baseline, ridge, quantile, gbdt], ignore_index=True)


def choose_champion_rows(candidates: pd.DataFrame) -> pd.DataFrame:
    ranked = candidates.sort_values(
        ["target_id", "split_name", "entity_spearman", "ndcg_5", "top5_overlap", "mae", "regret_at_1"],
        ascending=[True, True, False, False, False, True, True],
    )
    winners = ranked.groupby(["target_id", "split_name"], as_index=False, sort=False).head(1).reset_index(drop=True)
    winners["entity_type"] = winners["target_id"].map(lambda x: "player" if str(x).startswith("player_") else "role_slot")
    winners["chosen_model_id"] = winners["source_model_id"].astype(str)
    winners["selection_reason"] = (
        "Chosen as production champion by lexicographic ranking on entity_spearman, ndcg_5, top5_overlap, mae, regret_at_1."
    )
    return winners[
        [
            "target_id",
            "split_name",
            "entity_type",
            "chosen_family",
            "chosen_model_id",
            "param_a",
            "param_b",
            "entity_spearman",
            "ndcg_5",
            "top5_overlap",
            "mae",
            "regret_at_1",
            "selection_reason",
        ]
    ].copy()


def latest_rows(df: pd.DataFrame) -> pd.DataFrame:
    ordered = df.sort_values(["entity_key", "observation_date", "observation_key"])
    return ordered.groupby("entity_key", as_index=False, sort=False).tail(1).reset_index(drop=True)


def score_with_choice(
    choice: pd.Series,
    profile_id: str,
    df_full: pd.DataFrame,
) -> pd.DataFrame:
    target_id = str(choice["target_id"])
    split_name = str(choice["split_name"])
    family = str(choice["chosen_family"])
    latest = latest_rows(df_full)
    if family == "baseline":
        preds = build_baseline_predictions(
            target_id=target_id,
            profile_id=profile_id,
            split_name=split_name,
            model_id=str(choice["chosen_model_id"]),
            train=df_full,
            test=latest,
        ).copy()
        preds["q25"] = None
        preds["q50"] = None
        preds["q75"] = None
        preds["q90"] = None
        return preds
    if family == "ridge":
        preds = build_ridge_predictions(
            target_id=target_id,
            profile_id=profile_id,
            split_name=split_name,
            train=df_full,
            test=latest,
            alpha=float(choice["param_a"]),
        ).copy()
        preds["q25"] = None
        preds["q50"] = None
        preds["q75"] = None
        preds["q90"] = None
        return preds
    if family == "quantile":
        return build_quantile_predictions(
            target_id=target_id,
            profile_id=profile_id,
            split_name=split_name,
            train=df_full,
            test=latest,
        ).copy()
    if family == "gbdt":
        preds, _ = build_gbdt_predictions(
            target_id=target_id,
            profile_id=profile_id,
            split_name=split_name,
            train=df_full,
            test=latest,
            n_estimators=int(choice["param_a"]),
            learning_rate=float(choice["param_b"]),
        )
        preds = preds.copy()
        preds["q25"] = None
        preds["q50"] = None
        preds["q75"] = None
        preds["q90"] = None
        return preds
    raise ValueError(f"Unsupported production family: {family}")


def build_prediction_production(db_path: Path = DB_PATH) -> dict[str, Any]:
    con = sqlite3.connect(str(db_path))
    try:
        create_production_schema(con)
        profile_id = default_profile_id(con)
        con.execute("DELETE FROM production_prediction_model_choices")
        con.execute("DELETE FROM production_prediction_entity_scores")
        con.commit()

        candidates = collect_candidates(con)
        winners = choose_champion_rows(candidates)
        now = utc_now()
        choice_rows = []
        score_rows = []
        for _, choice in winners.iterrows():
            choice_rows.append(
                (
                    choice["target_id"],
                    choice["split_name"],
                    choice["entity_type"],
                    choice["chosen_family"],
                    choice["chosen_model_id"],
                    None if pd.isna(choice["param_a"]) else float(choice["param_a"]),
                    None if pd.isna(choice["param_b"]) else float(choice["param_b"]),
                    float(choice["entity_spearman"]),
                    float(choice["ndcg_5"]),
                    float(choice["top5_overlap"]),
                    float(choice["mae"]),
                    float(choice["regret_at_1"]),
                    str(choice["selection_reason"]),
                    now,
                )
            )
            df_full = load_target_dataset(con, str(choice["target_id"]), profile_id)
            scored = score_with_choice(choice, profile_id, df_full)
            latest_meta = latest_rows(df_full).set_index("entity_key")
            for row in scored.itertuples(index=False):
                meta = latest_meta.loc[row.entity_key]
                score_rows.append(
                    (
                        choice["target_id"],
                        choice["split_name"],
                        profile_id,
                        row.entity_type,
                        row.entity_key,
                        choice["chosen_family"],
                        choice["chosen_model_id"],
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
                        int(safe_float(meta["maps_in_observation"], 1.0)),
                        float(row.predicted_score),
                        None if "q25" not in scored.columns or pd.isna(getattr(row, "q25", None)) else float(row.q25),
                        None if "q50" not in scored.columns or pd.isna(getattr(row, "q50", None)) else float(row.q50),
                        None if "q75" not in scored.columns or pd.isna(getattr(row, "q75", None)) else float(row.q75),
                        None if "q90" not in scored.columns or pd.isna(getattr(row, "q90", None)) else float(row.q90),
                        int(row.train_rows_used),
                        now,
                    )
                )
        con.executemany(
            """
            INSERT INTO production_prediction_model_choices(
                target_id, split_name, entity_type, chosen_family, chosen_model_id, param_a, param_b,
                metric_entity_spearman, metric_ndcg_5, metric_top5_overlap, metric_mae, metric_regret_at_1,
                selection_reason, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            choice_rows,
        )
        con.executemany(
            """
            INSERT INTO production_prediction_entity_scores(
                target_id, split_name, profile_id, entity_type, entity_key, chosen_family, chosen_model_id,
                team_name, official_name, official_position, role_group, role_slot, player_names, account_id,
                account_ids, latest_match_id, latest_series_key, latest_series_id, latest_observation_date,
                latest_stage_bucket, maps_observed, predicted_score, q25, q50, q75, q90, train_rows_used, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            score_rows,
        )
        con.commit()
        summary = pd.read_sql_query(
            """
            SELECT target_id, split_name, chosen_family, chosen_model_id, param_a, param_b,
                   metric_entity_spearman, metric_ndcg_5, metric_top5_overlap, metric_mae, metric_regret_at_1
            FROM analytics_prediction_production_model_choices
            ORDER BY target_id, split_name
            """,
            con,
        )
        return {"profile_id": profile_id, "choices": summary}
    finally:
        con.close()
