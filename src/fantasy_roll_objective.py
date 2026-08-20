from __future__ import annotations

import math
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from project_db import resolve_db_path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = resolve_db_path(PROJECT_ROOT, event_id="ewc2026")

ROLE_SCOPE_TO_CATEGORY = {
    "core": "core_avg",
    "mid": "mid",
    "support": "support_avg",
}

POINTS_COLUMN_TO_STAT = {
    "kills_points": "kills",
    "deaths_points": "deaths",
    "creep_score_points": "creep_score",
    "gpm_points": "gpm",
    "wards_points": "wards_placed",
    "camps_stacked_points": "camps_stacked",
    "runes_grabbed_points": "runes_grabbed",
    "watchers_taken_points": "watchers_taken",
    "lotus_points": "lotus",
    "roshan_points": "roshan_kills",
    "teamfight_participation_points": "teamfight_participation",
    "stuns_points": "stuns",
    "tormentor_points": "tormentor_kills",
    "courier_points": "courier_kills",
    "first_blood_points": "first_blood",
    "smokes_points": "smokes_used",
}


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


def load_role_stat_benchmarks(
    con: sqlite3.Connection,
) -> pd.DataFrame:
    wide = pd.read_sql_query(
        """
        SELECT rms.*
        FROM player_map_role_category_stats rms
        WHERE rms.role_category IN ('core_avg', 'mid', 'support_avg')
        """,
        con,
    )
    rows: list[dict[str, Any]] = []
    for _, row in wide.iterrows():
        for points_col, stat_name in POINTS_COLUMN_TO_STAT.items():
            value = safe_float(row.get(points_col, 0.0))
            rows.append(
                {
                    "role_category": row["role_category"],
                    "stat_name": stat_name,
                    "points_x1": value,
                }
            )
    long_df = pd.DataFrame(rows)
    summary_rows: list[dict[str, Any]] = []
    for (role_category, stat_name), group in long_df.groupby(["role_category", "stat_name"], sort=False):
        values = group["points_x1"].astype(float).tolist()
        nonzero_rate = float((group["points_x1"].astype(float) > 0).mean()) if len(group) else 0.0
        summary_rows.append(
            {
                "role_category": role_category,
                "stat_name": stat_name,
                "avg_x1": round(sum(values) / len(values), 4) if values else 0.0,
                "p75_x1": round(percentile(values, 0.75), 4),
                "p90_x1": round(percentile(values, 0.90), 4),
                "max_x1": round(max(values) if values else 0.0, 4),
                "nonzero_rate": round(nonzero_rate, 4),
            }
        )
    return pd.DataFrame(summary_rows)


def compute_effective_slot_bonus_pct(
    slots: list[dict[str, Any]],
    quality_rules: dict[str, dict[str, Any]],
    trait_rules: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    computed: list[dict[str, Any]] = []
    qualities = [slot.get("quality_tier") for slot in slots]
    traits = [str(slot.get("trait_name") or "").lower() for slot in slots]
    all_qualities_distinct = all(q for q in qualities) and len(set(qualities)) == len(qualities)
    trait_counts = {trait: traits.count(trait) for trait in set(traits) if trait}

    for idx, slot in enumerate(slots):
        quality_tier = slot.get("quality_tier")
        trait_name = str(slot.get("trait_name") or "").lower()
        quality_bonus = safe_float((quality_rules.get(str(quality_tier).lower()) or {}).get("bonus_pct", 0.0))
        trait_rule = trait_rules.get(trait_name, {})
        self_bonus = 0.0
        adjacency_bonus = 0.0
        adjacency_penalty = 0.0
        condition_kind = trait_rule.get("condition_kind", "always")
        min_count = trait_rule.get("condition_min_count")
        trigger = False
        if trait_name:
            if condition_kind == "always":
                trigger = True
            elif condition_kind == "all_qualities_distinct":
                trigger = all_qualities_distinct
            elif condition_kind == "only_one_same_trait":
                trigger = trait_counts.get(trait_name, 0) == 1
            elif condition_kind == "min_same_trait_count":
                trigger = trait_counts.get(trait_name, 0) >= int(min_count or 0)
        if trigger:
            self_bonus += safe_float(trait_rule.get("self_bonus_pct", 0.0))
            # Store the per-neighbour effect.  A Benevolent/Vampiric emblem
            # applies its full value to each immediate neighbour, including
            # when it occupies an edge slot and has only one neighbour.
            if idx > 0 or idx < len(slots) - 1:
                adjacency_bonus = safe_float(trait_rule.get("adjacent_bonus_pct", 0.0))
                adjacency_penalty = safe_float(trait_rule.get("adjacent_penalty_pct", 0.0))
        computed.append(
            {
                **slot,
                "quality_bonus_pct_effective": quality_bonus,
                "trait_self_bonus_pct_effective": self_bonus,
                "trait_adjacent_bonus_out": adjacency_bonus,
                "trait_adjacent_penalty_out": adjacency_penalty,
                "trait_triggered": 1 if trigger else 0,
            }
        )

    for idx, slot in enumerate(computed):
        received = 0.0
        if idx > 0:
            left = computed[idx - 1]
            received += safe_float(left.get("trait_adjacent_bonus_out", 0.0))
            received -= safe_float(left.get("trait_adjacent_penalty_out", 0.0))
        if idx < len(computed) - 1:
            right = computed[idx + 1]
            received += safe_float(right.get("trait_adjacent_bonus_out", 0.0))
            received -= safe_float(right.get("trait_adjacent_penalty_out", 0.0))
        slot["trait_adjacent_net_received_pct"] = received
        slot["effective_bonus_pct"] = (
            safe_float(slot.get("quality_bonus_pct_effective", 0.0))
            + safe_float(slot.get("trait_self_bonus_pct_effective", 0.0))
            + received
        )
        slot["effective_multiplier"] = round(1.0 + slot["effective_bonus_pct"] / 100.0, 6)
    return computed


def synchronize_effective_slot_fields(
    slots: list[dict[str, Any]],
    quality_rules: dict[str, dict[str, Any]],
    trait_rules: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return slots with the model-facing multiplier synchronized to current rules.

    Trait interactions are local to a five-emblem role banner, so the effective
    multiplier must be recomputed separately for core, mid and support.
    """
    updated: list[dict[str, Any]] = [dict(slot) for slot in slots]
    by_key = {(str(slot.get("role_scope", "")), int(slot.get("slot_index", 0))): index for index, slot in enumerate(updated)}
    roles = sorted({str(slot.get("role_scope", "")) for slot in updated})
    for role_scope in roles:
        role_slots = sorted(
            [slot for slot in updated if str(slot.get("role_scope", "")) == role_scope],
            key=lambda item: int(item.get("slot_index", 0)),
        )
        for computed in compute_effective_slot_bonus_pct(role_slots, quality_rules, trait_rules):
            key = (str(computed.get("role_scope", "")), int(computed.get("slot_index", 0)))
            target = updated[by_key[key]]
            target.update(computed)
            target["multiplier"] = float(computed["effective_multiplier"])
    return updated


def compute_banner_intrinsic_value(
    slots: list[dict[str, Any]],
    benchmark_df: pd.DataFrame,
    quality_rules: dict[str, dict[str, Any]],
    trait_rules: dict[str, dict[str, Any]],
    *,
    objective_mode: str = "balanced",
) -> dict[str, Any]:
    role_groups: dict[str, list[dict[str, Any]]] = {}
    for slot in slots:
        role_groups.setdefault(str(slot["role_scope"]), []).append(slot)

    benchmark_map = {
        (row["role_category"], row["stat_name"]): row
        for _, row in benchmark_df.iterrows()
    }
    evaluated_slots: list[dict[str, Any]] = []
    total_value = 0.0
    for role_scope, group_slots in role_groups.items():
        ordered = sorted(group_slots, key=lambda item: int(item["slot_index"]))
        computed = compute_effective_slot_bonus_pct(ordered, quality_rules, trait_rules)
        role_category = ROLE_SCOPE_TO_CATEGORY.get(role_scope)
        for slot in computed:
            bench = benchmark_map.get((role_category, slot["stat_name"]), {})
            avg_x1 = safe_float(bench.get("avg_x1", 0.0))
            p75_x1 = safe_float(bench.get("p75_x1", 0.0))
            p90_x1 = safe_float(bench.get("p90_x1", 0.0))
            nonzero_rate = safe_float(bench.get("nonzero_rate", 1.0), 1.0)
            if objective_mode == "ceiling":
                anchor = 0.55 * p90_x1 + 0.35 * p75_x1 + 0.10 * avg_x1
            elif objective_mode == "safe":
                anchor = 0.50 * avg_x1 + 0.40 * p75_x1 + 0.10 * p90_x1
            else:
                anchor = 0.20 * avg_x1 + 0.55 * p75_x1 + 0.25 * p90_x1
            slot_value = anchor * safe_float(slot["effective_multiplier"]) * max(nonzero_rate, 0.10)
            total_value += slot_value
            evaluated_slots.append(
                {
                    **slot,
                    "benchmark_avg_x1": round(avg_x1, 4),
                    "benchmark_p75_x1": round(p75_x1, 4),
                    "benchmark_p90_x1": round(p90_x1, 4),
                    "benchmark_nonzero_rate": round(nonzero_rate, 4),
                    "slot_intrinsic_value": round(slot_value, 4),
                }
            )
    return {
        "objective_mode": objective_mode,
        "intrinsic_value_raw": round(total_value, 4),
        "evaluated_slots": evaluated_slots,
    }


def load_rule_maps(con: sqlite3.Connection) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    quality_df = pd.read_sql_query("SELECT * FROM fantasy_banner_quality_rules", con)
    trait_df = pd.read_sql_query("SELECT * FROM fantasy_banner_trait_rules", con)
    quality_map = {str(row["quality_tier"]).lower(): dict(row) for _, row in quality_df.iterrows()}
    trait_map = {str(row["trait_name"]).lower(): dict(row) for _, row in trait_df.iterrows()}
    return quality_map, trait_map
