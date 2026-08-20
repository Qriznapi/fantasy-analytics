"""Deterministic checks for the official five-emblem trait rules.

Run directly with ``.venv\\Scripts\\python.exe tests\\test_banner_trait_rules.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_roll_objective import compute_effective_slot_bonus_pct, synchronize_effective_slot_fields
from fantasy_roll_simulator import RollAction, apply_roll_action
import random


QUALITY_RULES = {"tier_i": {"bonus_pct": 10.0}, "tier_ii": {"bonus_pct": 30.0}, "tier_iii": {"bonus_pct": 60.0}, "tier_iv": {"bonus_pct": 100.0}, "tier_v": {"bonus_pct": 150.0}}
TRAIT_RULES = {
    "benevolent": {"condition_kind": "always", "self_bonus_pct": 0.0, "adjacent_bonus_pct": 20.0, "adjacent_penalty_pct": 0.0},
    "vampiric": {"condition_kind": "always", "self_bonus_pct": 50.0, "adjacent_bonus_pct": 0.0, "adjacent_penalty_pct": 10.0},
    "unique": {"condition_kind": "only_one_same_trait", "self_bonus_pct": 30.0, "adjacent_bonus_pct": 0.0, "adjacent_penalty_pct": 0.0},
    "fractal": {"condition_kind": "all_qualities_distinct", "self_bonus_pct": 60.0, "adjacent_bonus_pct": 0.0, "adjacent_penalty_pct": 0.0},
    "friendly": {"condition_kind": "min_same_trait_count", "condition_min_count": 3, "self_bonus_pct": 50.0, "adjacent_bonus_pct": 0.0, "adjacent_penalty_pct": 0.0},
}


def slots(traits: list[str], qualities: list[str] | None = None) -> list[dict[str, object]]:
    qualities = qualities or ["tier_i"] * len(traits)
    return [
        {"role_scope": "core", "slot_index": index + 1, "stat_name": "kills", "quality_tier": qualities[index], "trait_name": trait}
        for index, trait in enumerate(traits)
    ]


def bonuses(items: list[dict[str, object]]) -> list[float]:
    return [float(item["effective_bonus_pct"]) for item in items]


def main() -> None:
    # Unique is evaluated within one role banner: one works, two do not.
    assert bonuses(compute_effective_slot_bonus_pct(slots(["unique", "benevolent"]), QUALITY_RULES, TRAIT_RULES)) == [60.0, 10.0]
    assert bonuses(compute_effective_slot_bonus_pct(slots(["unique", "unique"]), QUALITY_RULES, TRAIT_RULES)) == [10.0, 10.0]

    # Each adjacent emblem receives the full official amount, including at an edge.
    assert bonuses(compute_effective_slot_bonus_pct(slots(["vampiric", "unique"]), QUALITY_RULES, TRAIT_RULES)) == [60.0, 30.0]
    assert bonuses(compute_effective_slot_bonus_pct(slots(["unique", "benevolent", "unique"]), QUALITY_RULES, TRAIT_RULES)) == [30.0, 10.0, 30.0]

    # Fractal requires all qualities in this role banner to be distinct.
    assert bonuses(compute_effective_slot_bonus_pct(slots(["fractal", "unique"], ["tier_i", "tier_ii"]), QUALITY_RULES, TRAIT_RULES)) == [70.0, 60.0]
    assert bonuses(compute_effective_slot_bonus_pct(slots(["fractal", "unique"], ["tier_i", "tier_i"]), QUALITY_RULES, TRAIT_RULES)) == [10.0, 40.0]

    # Friendly is active only once its count inside the role banner reaches three.
    assert bonuses(compute_effective_slot_bonus_pct(slots(["friendly", "friendly", "friendly"]), QUALITY_RULES, TRAIT_RULES)) == [60.0, 60.0, 60.0]
    assert bonuses(compute_effective_slot_bonus_pct(slots(["friendly", "friendly"]), QUALITY_RULES, TRAIT_RULES)) == [10.0, 10.0]

    # The model-facing state must match the multiplier used by scoring.
    synced = synchronize_effective_slot_fields(slots(["vampiric", "unique"]), QUALITY_RULES, TRAIT_RULES)
    assert [item["multiplier"] for item in synced] == [1.6, 1.3]

    # Quality shifts are role-targeted, respect Tier I/V bounds and do not use
    # the same emblem for both sides of the +2/-1 operation.
    shifted = apply_roll_action(
        slots(["unique"] * 5, ["tier_i", "tier_ii", "tier_iii", "tier_iv", "tier_v"]),
        RollAction("reroll_quality", "core", -1, "role_quality_shift_plus2_minus1", ""),
        template_color_map={}, rng=random.Random(7),
    )
    before = [0, 1, 2, 3, 4]
    after = [{"tier_i": 0, "tier_ii": 1, "tier_iii": 2, "tier_iv": 3, "tier_v": 4}[item["quality_tier"]] for item in shifted]
    assert sum(after) - sum(before) == 1
    assert all(abs(new - old) <= 1 for old, new in zip(before, after))
    print("PASS: official trait-rule checks")


if __name__ == "__main__":
    main()
