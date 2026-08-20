"""Small, inspectable preference signal for banner planning.

The official intrinsic value remains the primary objective.  This layer only
breaks close planner choices toward patterns that are known to be strategically
valuable, without rewarding a stat independently of its role-specific value.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from fantasy_roll_objective import compute_banner_intrinsic_value


STAT_ROLE_WEIGHT = {
    ("core", "creep_score"): 0.10,
    ("mid", "creep_score"): 0.10,
    ("core", "gpm"): 0.08,
    ("mid", "gpm"): 0.09,
    ("core", "teamfight_participation"): 0.07,
    ("mid", "teamfight_participation"): 0.07,
    ("support", "teamfight_participation"): 0.07,
    ("mid", "runes_grabbed"): 0.13,
}
TIER_V_TARGET_WEIGHT = 0.08
FRIENDLY_SET_WEIGHT = 0.06


def preference_breakdown(slots: list[dict[str, Any]], ctx: Any, objective_mode: str) -> dict[str, Any]:
    evaluated = compute_banner_intrinsic_value(
        slots, ctx.benchmark_df, ctx.quality_map, ctx.trait_map,
        objective_mode=objective_mode,
    )["evaluated_slots"]
    total = 0.0
    by_reason: dict[str, float] = {}
    for slot in evaluated:
        role = str(slot["role_scope"])
        stat = str(slot["stat_name"])
        value = float(slot["slot_intrinsic_value"])
        weight = STAT_ROLE_WEIGHT.get((role, stat), 0.0)
        if weight:
            amount = value * weight
            total += amount
            by_reason[f"{role}:{stat}"] = by_reason.get(f"{role}:{stat}", 0.0) + amount
        if str(slot["quality_tier"]) == "tier_v" and weight:
            amount = value * TIER_V_TARGET_WEIGHT
            total += amount
            by_reason["tier_v_on_target_stat"] = by_reason.get("tier_v_on_target_stat", 0.0) + amount
    for role in {str(slot["role_scope"]) for slot in evaluated}:
        group = [slot for slot in evaluated if str(slot["role_scope"]) == role]
        if Counter(str(slot["trait_name"]) for slot in group)["friendly"] >= 3:
            amount = sum(float(slot["slot_intrinsic_value"]) for slot in group if str(slot["trait_name"]) == "friendly") * FRIENDLY_SET_WEIGHT
            total += amount
            by_reason[f"{role}:friendly_set"] = by_reason.get(f"{role}:friendly_set", 0.0) + amount
    return {"preference_bonus": float(total), "by_reason": by_reason}
