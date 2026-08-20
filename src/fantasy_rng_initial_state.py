from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any


def load_initial_state_preset(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.setdefault("preset_id", path.stem)
    payload.setdefault("role_rules", {})
    return payload


def validate_initial_state_preset(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    role_rules = payload.get("role_rules", {})
    for role_scope in ["core", "mid", "support"]:
        role_rule = role_rules.get(role_scope)
        if role_rule is None:
            errors.append(f"missing role rule for {role_scope}")
            continue
        fixed_slots = list(role_rule.get("fixed_slots", []))
        sampled_slots = list(role_rule.get("sampled_slots", []))
        overlap = sorted(set(fixed_slots) & set(sampled_slots))
        if overlap:
            errors.append(f"{role_scope} has overlapping fixed/sample slots: {overlap}")
    return errors


def _weighted_choice(rng: random.Random, weighted_items: list[dict[str, Any]], *, key_name: str) -> str:
    total = sum(max(float(item.get("weight", 0.0)), 0.0) for item in weighted_items)
    if total <= 0:
        return str(weighted_items[0][key_name])
    threshold = rng.random() * total
    running = 0.0
    for item in weighted_items:
        running += max(float(item.get("weight", 0.0)), 0.0)
        if running >= threshold:
            return str(item[key_name])
    return str(weighted_items[-1][key_name])


def sample_initial_slots_from_preset(
    base_slots: list[dict[str, Any]],
    preset: dict[str, Any],
    *,
    rng: random.Random,
) -> list[dict[str, Any]]:
    role_rules = preset.get("role_rules", {})
    global_priors = preset.get("global_priors", {})
    updated = [dict(slot) for slot in base_slots]
    slot_index = {(str(slot["role_scope"]), int(slot["slot_index"])): slot for slot in updated}
    for role_scope, rule in role_rules.items():
        role_slots = [slot for slot in updated if str(slot["role_scope"]) == str(role_scope)]
        slot_rules = list(rule.get("slot_priors", []))
        configured_indices = {int(item["slot_index"]) for item in slot_rules}
        # Only unchanged slots constrain a sampled start.  Previous code seeded
        # this set from every old profile slot, which silently prevented valid
        # first-slot outcomes before the new banner was sampled.
        used_stats_by_color: dict[str, set[str]] = {}
        for slot in role_slots:
            if int(slot["slot_index"]) in configured_indices:
                continue
            color = str(slot.get("color_group", "")).lower()
            used_stats_by_color.setdefault(color, set()).add(str(slot.get("stat_name", "")))
        # Avoid deterministic priority for slots that share a color while
        # retaining each slot's own prior weights.
        rng.shuffle(slot_rules)
        for slot_rule in slot_rules:
            key = (str(role_scope), int(slot_rule["slot_index"]))
            slot = slot_index.get(key)
            if slot is None:
                continue
            stat_rows = list(slot_rule.get("stat_weights", []))
            quality_rows = list(slot_rule.get("quality_weights", []))
            trait_rows = list(slot_rule.get("trait_weights", global_priors.get("trait_weights", [])))
            if stat_rows:
                color = str(slot.get("color_group", "")).lower()
                used_stats = used_stats_by_color.setdefault(color, set())
                valid_stats = [item for item in stat_rows if str(item.get("stat_name", "")) not in used_stats]
                slot["stat_name"] = _weighted_choice(rng, valid_stats or stat_rows, key_name="stat_name")
                used_stats.add(str(slot["stat_name"]))
            if quality_rows:
                valid_qualities = [item for item in quality_rows if str(item.get("quality_tier", "")) != str(slot.get("quality_tier", ""))]
                slot["quality_tier"] = _weighted_choice(rng, valid_qualities or quality_rows, key_name="quality_tier")
            if trait_rows:
                slot["trait_name"] = _weighted_choice(rng, trait_rows, key_name="trait_name")
    return updated
