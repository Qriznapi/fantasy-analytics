"""Inspectable strategic prior distilled from the TI reroll priority guide.

This is not a replacement for the official final-banner objective.  It gives
the planner a large, explicit preference for actions which can move a banner
towards the guide's targets.  The new neural ranker then learns those choices
from teacher trajectories, while later RL fine-tuning remains free to correct
the prior when simulation evidence is stronger.
"""

from __future__ import annotations

from collections import Counter
from typing import Any


# Values are in official-value units and intentionally encode the order in the
# guide.  They are used only with an explicit non-zero strategy-prior weight.
PRIORITY_BONUS = {
    "quality_plus_one": 20_000.0,
    "mid_runes": 15_000.0,
    "teamfight": 13_000.0,
    "core_mid_farm": 7_500.0,
    "friendly_third": 2_500.0,
    "quality_plus_two_minus_one": 2_000.0,
    "weak_trait": 750.0,
    "low_quality": 5_000.0,
    "important_low_quality": 4_000.0,
    "protected_stat_penalty": -18_000.0,
    "protected_trait_penalty": -13_000.0,
    "tier_v_quality_penalty": -18_000.0,
    "important_tier_iv_quality_penalty": -9_000.0,
}


def _role_slots(slots: list[dict[str, Any]], role: str) -> list[dict[str, Any]]:
    return [slot for slot in slots if str(slot.get("role_scope")) == role]


def _has(slots: list[dict[str, Any]], role: str, stat: str) -> bool:
    return any(str(slot.get("stat_name")) == stat for slot in _role_slots(slots, role))


def _tier_number(slot: dict[str, Any]) -> int:
    raw = str(slot.get("quality_tier", "tier_i"))
    return {"tier_i": 1, "tier_ii": 2, "tier_iii": 3, "tier_iv": 4, "tier_v": 5}.get(raw, 1)


def _targets(slots: list[dict[str, Any]], offer: Any) -> list[dict[str, Any]]:
    """Conservative set of slots which one action can mutate."""
    role = str(getattr(offer, "role_scope", ""))
    color = str(getattr(offer, "target_color_group", ""))
    eligible = [slot for slot in _role_slots(slots, role) if not color or str(slot.get("color_group")) == color]
    slot_index = int(getattr(offer, "slot_index", -1))
    if slot_index > 0:
        return [slot for slot in eligible if int(slot.get("slot_index", -2)) == slot_index]
    return eligible


def _is_important(role: str, stat: str) -> bool:
    return (role == "mid" and stat in {"runes_grabbed", "creep_score", "gpm", "teamfight_participation"}) or (role == "core" and stat in {"creep_score", "gpm", "teamfight_participation"}) or (role == "support" and stat == "teamfight_participation")


def _protected_trait_slots(role_slots: list[dict[str, Any]]) -> set[int]:
    """Return traits that already produce a meaningful realised benefit."""
    friendly_active = Counter(str(slot.get("trait_name", "")) for slot in role_slots)["friendly"] >= 3
    protected: set[int] = set()
    for slot in role_slots:
        trait = str(slot.get("trait_name", ""))
        self_bonus = float(slot.get("trait_self_bonus_pct_effective", 0.0))
        adjacent_out = float(slot.get("trait_adjacent_bonus_out", 0.0))
        triggered = bool(slot.get("trait_triggered", False))
        # Friendly is valuable only after its set condition is live. Unique,
        # Fractal and Vampiric are protected only when their current state
        # actually yields a bonus; Benevolent is protected through adjacency.
        if (trait == "friendly" and friendly_active) or self_bonus >= 30.0 or adjacent_out > 0.0 or (triggered and trait in {"unique", "fractal", "vampiric"}):
            protected.add(int(slot["slot_index"]))
    return protected


def strategy_action_breakdown(slots: list[dict[str, Any]], offer: Any) -> dict[str, Any]:
    """Score how closely one legal token+role choice follows the supplied guide."""
    if bool(getattr(offer, "is_refresh_action", False)):
        return {"bonus": 0.0, "reasons": []}

    role = str(getattr(offer, "role_scope", ""))
    token_id = str(getattr(offer, "token_id", ""))
    token_type = str(getattr(offer, "token_type", ""))
    color = str(getattr(offer, "target_color_group", ""))
    role_slots = _role_slots(slots, role)
    targets = _targets(slots, offer)
    reasons: list[str] = []
    bonus = 0.0

    # 1. Improve one random quality, on any banner, is the stated first rule.
    if token_id == "quality_shift_plus1":
        bonus += PRIORITY_BONUS["quality_plus_one"]
        reasons.append("quality_plus_one")

    # 2-5. A stat reroll can only move toward a desired stat within its colour.
    if token_type == "reroll_stat":
        if role == "mid" and color == "blue" and not _has(slots, "mid", "runes_grabbed"):
            bonus += PRIORITY_BONUS["mid_runes"]
            reasons.append("mid_runes")
        if role in {"core", "mid", "support"} and color == "green" and not _has(slots, role, "teamfight_participation"):
            bonus += PRIORITY_BONUS["teamfight"]
            reasons.append(f"{role}_teamfight")
        if role in {"core", "mid"} and color == "red":
            missing_farm = [stat for stat in ("creep_score", "gpm") if not _has(slots, role, stat)]
            # Never sacrifice an existing farm stat to chase the other one:
            # stat uniqueness makes that reroll incapable of completing a pair.
            touches_farm = any(str(slot.get("stat_name")) in {"creep_score", "gpm"} for slot in targets)
            if missing_farm and not touches_farm:
                bonus += PRIORITY_BONUS["core_mid_farm"]
                reasons.append(f"{role}_farm:{','.join(missing_farm)}")

        protected = set()
        # Individual target stats stay protected even before a full pair/set is
        # complete. The guide's target rule is about adding missing value, not
        # gambling away a value already obtained.
        if _has(slots, "mid", "runes_grabbed"):
            protected.add(("mid", "runes_grabbed"))
        for protected_role in ("core", "mid", "support"):
            if _has(slots, protected_role, "teamfight_participation"):
                protected.add((protected_role, "teamfight_participation"))
        for protected_role in ("core", "mid"):
            for farm_stat in ("creep_score", "gpm"):
                if _has(slots, protected_role, farm_stat):
                    protected.add((protected_role, farm_stat))
        touched_protected = [str(slot.get("stat_name")) for slot in targets if (role, str(slot.get("stat_name"))) in protected]
        if touched_protected:
            bonus += PRIORITY_BONUS["protected_stat_penalty"]
            reasons.append(f"protect:{','.join(touched_protected)}")

    # General quality rolls should focus on banners containing weak emblems,
    # particularly where a high-value stat is still Tier I/II.
    if token_type == "reroll_quality":
        low_slots = [slot for slot in targets if _tier_number(slot) <= 2]
        important_low = [slot for slot in low_slots if _is_important(role, str(slot.get("stat_name")))]
        if low_slots:
            bonus += PRIORITY_BONUS["low_quality"] * (1.0 + 0.25 * (len(low_slots) - 1))
            reasons.append(f"{role}_low_quality")
        if important_low:
            bonus += PRIORITY_BONUS["important_low_quality"]
            reasons.append(f"{role}_important_low_quality")
        tier_v = [slot for slot in targets if _tier_number(slot) == 5]
        important_tier_iv = [slot for slot in targets if _tier_number(slot) == 4 and _is_important(role, str(slot.get("stat_name")))]
        if tier_v:
            bonus += PRIORITY_BONUS["tier_v_quality_penalty"]
            reasons.append(f"protect_tier_v:{len(tier_v)}")
        if important_tier_iv:
            bonus += PRIORITY_BONUS["important_tier_iv_quality_penalty"]
            reasons.append(f"protect_important_tier_iv:{len(important_tier_iv)}")

    # 8. Only seek a Friendly reroll when it can complete a three-friendly set.
    friendly_count = Counter(str(slot.get("trait_name", "")) for slot in role_slots)["friendly"]
    if token_type == "reroll_trait" and friendly_count == 2:
        bonus += PRIORITY_BONUS["friendly_third"]
        reasons.append(f"{role}_friendly_third")

    # 9. The +2/-1 trade is conditional on a weak enough banner.
    low_quality_count = sum(_tier_number(slot) <= 3 for slot in role_slots)
    if token_id == "quality_shift_plus2_minus1" and low_quality_count >= 3:
        bonus += PRIORITY_BONUS["quality_plus_two_minus_one"]
        reasons.append(f"{role}_quality_trade")

    # 10. Trait rerolls are a low priority unless the current target is weak.
    if token_type == "reroll_trait" and getattr(offer, "slot_index", -1) >= 0:
        slot_index = int(getattr(offer, "slot_index"))
        current = next((slot for slot in role_slots if int(slot.get("slot_index", -2)) == slot_index), None)
        protected_now = _protected_trait_slots(role_slots)
        if current is not None and slot_index not in protected_now and float(current.get("trait_self_bonus_pct_effective", 0.0)) < 35.0:
            bonus += PRIORITY_BONUS["weak_trait"]
            reasons.append(f"{role}_weak_trait")

    if token_type == "reroll_trait":
        protected_traits = _protected_trait_slots(role_slots)
        touched_traits = [slot for slot in targets if int(slot.get("slot_index", -1)) in protected_traits]
        if touched_traits:
            bonus += PRIORITY_BONUS["protected_trait_penalty"]
            reasons.append(f"protect_trait:{','.join(str(slot.get('trait_name')) for slot in touched_traits)}")

    return {"bonus": float(bonus), "reasons": reasons}
