from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from fantasy_prediction_foundation import safe_float


RICH_FEATURE_COLUMNS = [
    "entity_mean",
    "entity_p25",
    "entity_p75",
    "entity_p90",
    "recent_mean_3",
    "recent_mean_5",
    "recent_p75_5",
    "entity_max",
    "entity_min",
    "entity_std",
    "entity_cv",
    "range_span",
    "max_minus_mean",
    "p75_minus_mean",
    "recent_delta_mean",
    "recent_delta_p75",
    "team_segment_mean",
    "segment_mean",
    "global_mean",
    "entity_vs_segment",
    "entity_vs_team_segment",
    "team_vs_segment",
    "sample_weight",
    "sample_trust",
    "maps_in_observation",
    "role_code",
]


def segment_column(df: pd.DataFrame) -> str:
    return "role_group" if df["entity_type"].iloc[0] == "player" else "role_slot"


def with_team_segment_key(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy()
    segcol = segment_column(frame)
    frame["team_segment_key"] = frame["team_name"].astype(str) + "::" + frame[segcol].astype(str)
    return frame


def percentile(values: list[float], q: float) -> float:
    clean = sorted(safe_float(v) for v in values if v is not None)
    if not clean:
        return 0.0
    return float(np.percentile(np.asarray(clean, dtype=float), q * 100.0))


def role_code(entity_type: str, value: str | None) -> float:
    mapping_player = {"core": 1.0, "mid": 2.0, "support": 3.0}
    mapping_slot = {"core_pair": 1.0, "mid_single": 2.0, "support_pair": 3.0}
    if entity_type == "player":
        return mapping_player.get(str(value), 0.0)
    return mapping_slot.get(str(value), 0.0)


def history_features(train: pd.DataFrame) -> tuple[dict[str, list[float]], dict[str, float], dict[str, float], float]:
    entity_groups = (
        train.sort_values(["observation_date", "observation_key"])
        .groupby("entity_key")["target_score"]
        .apply(lambda s: [safe_float(v) for v in s.tolist()])
        .to_dict()
    )
    segcol = segment_column(train)
    segment_means = train.groupby(segcol)["target_score"].mean().to_dict()
    team_segment_means = train.groupby("team_segment_key")["target_score"].mean().to_dict()
    global_mean = safe_float(train["target_score"].mean())
    return entity_groups, segment_means, team_segment_means, global_mean


def feature_row(
    row: pd.Series,
    entity_groups: dict[str, list[float]],
    segment_means: dict[str, float],
    team_segment_means: dict[str, float],
    global_mean: float,
    segcol: str,
) -> dict[str, float]:
    entity_type = str(row["entity_type"])
    entity_key = str(row["entity_key"])
    segment_key = str(row[segcol])
    team_segment_key = str(row["team_segment_key"])
    values = [safe_float(v) for v in entity_groups.get(entity_key, [])]
    recent3 = values[-3:]
    recent5 = values[-5:]
    segment_mean = safe_float(segment_means.get(segment_key, global_mean), global_mean)
    team_segment_mean = safe_float(team_segment_means.get(team_segment_key, segment_mean), segment_mean)
    fallback = team_segment_mean if team_segment_mean else segment_mean

    entity_mean = safe_float(sum(values) / len(values), fallback) if values else fallback
    entity_p25 = percentile(values, 0.25) if values else fallback
    entity_p75 = percentile(values, 0.75) if values else fallback
    entity_p90 = percentile(values, 0.90) if values else entity_p75
    recent_mean_3 = safe_float(sum(recent3) / len(recent3), entity_mean) if recent3 else entity_mean
    recent_mean_5 = safe_float(sum(recent5) / len(recent5), entity_mean) if recent5 else entity_mean
    recent_p75_5 = percentile(recent5, 0.75) if recent5 else entity_p75
    entity_max = max(values) if values else fallback
    entity_min = min(values) if values else fallback
    entity_std = float(np.std(np.asarray(values, dtype=float))) if values else 0.0
    entity_cv = entity_std / entity_mean if entity_mean > 1e-9 else 0.0
    range_span = entity_max - entity_min
    max_minus_mean = entity_max - entity_mean
    p75_minus_mean = entity_p75 - entity_mean
    recent_delta_mean = recent_mean_5 - entity_mean
    recent_delta_p75 = recent_p75_5 - entity_p75
    entity_vs_segment = entity_mean - segment_mean
    entity_vs_team_segment = entity_mean - team_segment_mean
    team_vs_segment = team_segment_mean - segment_mean
    train_count = float(len(values))
    sample_weight = min(1.0, train_count / 8.0)
    sample_trust = min(1.0, np.log1p(train_count) / np.log(9.0))
    maps_in_observation = safe_float(row.get("maps_in_observation", 1.0), 1.0)
    role_value = row[segcol] if segcol in row else None

    return {
        "entity_mean": entity_mean,
        "entity_p25": entity_p25,
        "entity_p75": entity_p75,
        "entity_p90": entity_p90,
        "recent_mean_3": recent_mean_3,
        "recent_mean_5": recent_mean_5,
        "recent_p75_5": recent_p75_5,
        "entity_max": entity_max,
        "entity_min": entity_min,
        "entity_std": entity_std,
        "entity_cv": entity_cv,
        "range_span": range_span,
        "max_minus_mean": max_minus_mean,
        "p75_minus_mean": p75_minus_mean,
        "recent_delta_mean": recent_delta_mean,
        "recent_delta_p75": recent_delta_p75,
        "team_segment_mean": team_segment_mean,
        "segment_mean": segment_mean,
        "global_mean": global_mean,
        "entity_vs_segment": entity_vs_segment,
        "entity_vs_team_segment": entity_vs_team_segment,
        "team_vs_segment": team_vs_segment,
        "sample_weight": sample_weight,
        "sample_trust": sample_trust,
        "train_count": train_count,
        "maps_in_observation": maps_in_observation,
        "role_code": role_code(entity_type, role_value),
    }


def build_feature_frame(train: pd.DataFrame, scored: pd.DataFrame) -> pd.DataFrame:
    segcol = segment_column(train)
    entity_groups, segment_means, team_segment_means, global_mean = history_features(train)
    rows: list[dict[str, Any]] = []
    for _, row in scored.iterrows():
        rows.append(feature_row(row, entity_groups, segment_means, team_segment_means, global_mean, segcol))
    frame = pd.DataFrame(rows, index=scored.index)
    return frame


def feature_columns(include_train_count: bool = True) -> list[str]:
    cols = list(RICH_FEATURE_COLUMNS)
    if not include_train_count and "train_count" in cols:
        cols.remove("train_count")
    return cols
