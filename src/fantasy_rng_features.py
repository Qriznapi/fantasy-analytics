from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any

import pandas as pd


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
    except Exception:
        return default
    if pd.isna(value):
        return default
    return value


def parse_slot_state_json(payload: str | None) -> list[dict[str, Any]]:
    if not payload:
        return []
    try:
        rows = json.loads(payload)
    except Exception:
        return []
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)]


def parse_offer_set_json(payload: str | None) -> list[dict[str, Any]]:
    if not payload:
        return []
    try:
        rows = json.loads(payload)
    except Exception:
        return []
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)]


def serialize_slot_state(slots: list[dict[str, Any]]) -> str:
    return json.dumps(slots, ensure_ascii=False, sort_keys=True)


def _ordered_slots(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [dict(slot) for slot in slots],
        key=lambda item: (str(item.get("role_scope", "")), int(item.get("slot_index", 0))),
    )


def build_state_features(
    slots: list[dict[str, Any]],
    *,
    baseline_value_before: float = 0.0,
    step_index: int = 0,
    max_steps: int = 30,
) -> dict[str, Any]:
    ordered = _ordered_slots(slots)
    multipliers = [safe_float(slot.get("multiplier", 0.0)) for slot in ordered]
    role_values: defaultdict[str, float] = defaultdict(float)
    role_counts: defaultdict[str, int] = defaultdict(int)
    color_counts: Counter[str] = Counter()
    quality_counts: Counter[str] = Counter()
    trait_counts: Counter[str] = Counter()
    stat_counts: Counter[str] = Counter()

    for slot in ordered:
        role_scope = str(slot.get("role_scope", ""))
        color_group = str(slot.get("color_group", "")).lower()
        quality_tier = str(slot.get("quality_tier", "")).lower()
        trait_name = str(slot.get("trait_name", "")).lower()
        stat_name = str(slot.get("stat_name", "")).lower()
        value = safe_float(slot.get("multiplier", 0.0))

        role_values[role_scope] += value
        role_counts[role_scope] += 1
        if color_group:
            color_counts[color_group] += 1
        if quality_tier:
            quality_counts[quality_tier] += 1
        if trait_name:
            trait_counts[trait_name] += 1
        if stat_name:
            stat_counts[stat_name] += 1

    highest = max(multipliers) if multipliers else 0.0
    lowest = min(multipliers) if multipliers else 0.0
    mean_value = sum(multipliers) / len(multipliers) if multipliers else 0.0
    variance = (
        sum((value - mean_value) ** 2 for value in multipliers) / len(multipliers)
        if multipliers
        else 0.0
    )
    slots_by_role = defaultdict(list)
    for slot in ordered:
        slots_by_role[str(slot.get("role_scope", ""))].append(safe_float(slot.get("multiplier", 0.0)))

    result: dict[str, Any] = {
        "state_step_index": int(step_index),
        "state_rolls_left": max(0, int(max_steps) - int(step_index)),
        "state_progress_ratio": (float(step_index) / max(1.0, float(max_steps))),
        "state_slot_count": int(len(ordered)),
        "state_banner_value": safe_float(baseline_value_before),
        "state_multiplier_min": lowest,
        "state_multiplier_max": highest,
        "state_multiplier_mean": mean_value,
        "state_multiplier_var": variance,
        "state_color_red_count": int(color_counts.get("red", 0)),
        "state_color_green_count": int(color_counts.get("green", 0)),
        "state_color_blue_count": int(color_counts.get("blue", 0)),
        "state_quality_tier_i_count": int(quality_counts.get("tier_i", 0)),
        "state_quality_tier_ii_count": int(quality_counts.get("tier_ii", 0)),
        "state_quality_tier_iii_count": int(quality_counts.get("tier_iii", 0)),
        "state_quality_tier_iv_count": int(quality_counts.get("tier_iv", 0)),
        "state_quality_tier_v_count": int(quality_counts.get("tier_v", 0)),
        "state_trait_vampiric_count": int(trait_counts.get("vampiric", 0)),
        "state_trait_benevolent_count": int(trait_counts.get("benevolent", 0)),
        "state_trait_unique_count": int(trait_counts.get("unique", 0)),
        "state_trait_friendly_count": int(trait_counts.get("friendly", 0)),
        "state_trait_fractal_count": int(trait_counts.get("fractal", 0)),
        "state_role_core_value": safe_float(role_values.get("core", 0.0)),
        "state_role_mid_value": safe_float(role_values.get("mid", 0.0)),
        "state_role_support_value": safe_float(role_values.get("support", 0.0)),
        "state_role_core_mean": (
            safe_float(role_values.get("core", 0.0)) / max(1, int(role_counts.get("core", 0)))
        ),
        "state_role_mid_mean": (
            safe_float(role_values.get("mid", 0.0)) / max(1, int(role_counts.get("mid", 0)))
        ),
        "state_role_support_mean": (
            safe_float(role_values.get("support", 0.0)) / max(1, int(role_counts.get("support", 0)))
        ),
        "state_unique_stat_count": int(len(stat_counts)),
        "state_duplicate_stat_slots": int(sum(count - 1 for count in stat_counts.values() if count > 1)),
    }

    for stat_name, count in sorted(stat_counts.items()):
        result[f"state_stat_count__{stat_name}"] = int(count)
    return result


def build_offer_features(
    offer: dict[str, Any],
    *,
    chosen_action_id: str = "",
) -> dict[str, Any]:
    return {
        "offer_action_id": str(offer.get("action_id", "")),
        "offer_token_id": str(offer.get("token_id", "")),
        "offer_token_type": str(offer.get("token_type", "")),
        "offer_role_scope": str(offer.get("role_scope", "")),
        "offer_slot_index": int(offer.get("slot_index", 0) or 0),
        "offer_current_stat_name": str(offer.get("current_stat_name", "")),
        "offer_current_quality_tier": str(offer.get("current_quality_tier", "")),
        "offer_current_trait_name": str(offer.get("current_trait_name", "")),
        "offer_current_multiplier": safe_float(offer.get("current_multiplier", 0.0)),
        "offer_is_refresh_action": int(offer.get("is_refresh_action", 0) or 0),
        "offer_action_scope": str(offer.get("action_scope", "slot")),
        "offer_target_color_group": str(offer.get("target_color_group", "")),
        "offer_expected_delta": safe_float(offer.get("expected_delta", 0.0)),
        "offer_p75_delta": safe_float(offer.get("p75_delta", 0.0)),
        "offer_p90_delta": safe_float(offer.get("p90_delta", 0.0)),
        "offer_is_chosen": 1 if str(offer.get("action_id", "")) == str(chosen_action_id) else 0,
    }


def build_offer_rows_from_state(
    slots: list[dict[str, Any]],
    offers: list[dict[str, Any]],
    *,
    baseline_value_before: float,
    step_index: int,
    max_steps: int,
    chosen_action_id: str = "",
    run_id: str = "",
    policy_name: str = "",
    episode_index: int = 0,
) -> list[dict[str, Any]]:
    common = {
        "run_id": str(run_id),
        "policy_name": str(policy_name),
        "episode_index": int(episode_index),
        "step_index": int(step_index),
        "max_steps": int(max_steps),
        "state_slot_state_json": serialize_slot_state(_ordered_slots(slots)),
        "target_episode_final_value": 0.0,
        "target_future_gain": 0.0,
        "target_realized_delta": 0.0,
        "chosen_action_id": str(chosen_action_id),
        "chosen_token_type": "",
        "chosen_role_scope": "",
        "chosen_slot_index": 0,
    }
    state_features = build_state_features(
        slots,
        baseline_value_before=baseline_value_before,
        step_index=step_index,
        max_steps=max_steps,
    )
    rows: list[dict[str, Any]] = []
    for offer_rank, offer in enumerate(offers):
        row = dict(common)
        row["offer_rank_in_set"] = int(offer_rank)
        row.update(state_features)
        row.update(build_offer_features(offer, chosen_action_id=chosen_action_id))
        rows.append(row)
    return rows


def build_training_rows_from_episode_step(
    step_row: dict[str, Any],
    *,
    episode_final_value: float,
    max_steps: int,
) -> list[dict[str, Any]]:
    slot_state_json = str(step_row.get("slot_state_before_json", "") or "")
    slots = parse_slot_state_json(slot_state_json)
    offers = parse_offer_set_json(step_row.get("offer_set_json"))
    baseline_value_before = safe_float(step_row.get("baseline_value_before", 0.0))
    step_index = int(step_row.get("step_index", 0))
    common = {
        "run_id": str(step_row.get("run_id", "")),
        "policy_name": str(step_row.get("policy_name", "")),
        "episode_index": int(step_row.get("episode_index", 0)),
        "step_index": step_index,
        "max_steps": int(max_steps),
        "state_slot_state_json": slot_state_json,
        "target_episode_final_value": safe_float(episode_final_value),
        "target_future_gain": safe_float(episode_final_value) - baseline_value_before,
        "target_realized_delta": safe_float(step_row.get("realized_delta", 0.0)),
        "chosen_action_id": str(step_row.get("chosen_action_id", "")),
        "chosen_token_type": str(step_row.get("chosen_token_type", "")),
        "chosen_role_scope": str(step_row.get("chosen_role_scope", "")),
        "chosen_slot_index": int(step_row.get("chosen_slot_index", 0) or 0),
    }
    state_features = build_state_features(
        slots,
        baseline_value_before=baseline_value_before,
        step_index=step_index,
        max_steps=max_steps,
    )
    rows: list[dict[str, Any]] = []
    for offer_rank, offer in enumerate(offers):
        row = dict(common)
        row["offer_rank_in_set"] = int(offer_rank)
        row.update(state_features)
        row.update(build_offer_features(offer, chosen_action_id=common["chosen_action_id"]))
        rows.append(row)
    return rows
