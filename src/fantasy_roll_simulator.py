from __future__ import annotations

import json
import random
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from fantasy_rng_initial_state import load_initial_state_preset
from fantasy_roll_objective import (
    compute_banner_intrinsic_value,
    load_role_stat_benchmarks,
    load_rule_maps,
)
from project_db import resolve_db_path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = resolve_db_path(PROJECT_ROOT, event_id="ti2026")
BENCHMARK_DB_PATH = resolve_db_path(PROJECT_ROOT, event_id="ewc2026")
STARTER_PRIOR_PATH = PROJECT_ROOT / "configs" / "rng_initial_states" / "starters_conservative_v4.json"


@dataclass
class RollAction:
    token_type: str
    role_scope: str
    slot_index: int
    action_scope: str = "slot"
    target_color_group: str = ""


def _weighted_choice(rng: random.Random, rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(max(float(row.get("weight", 0.0)), 0.0) for row in rows)
    if total <= 0:
        return rows[0]
    threshold = rng.random() * total
    running = 0.0
    for row in rows:
        running += max(float(row.get("weight", 0.0)), 0.0)
        if running >= threshold:
            return row
    return rows[-1]


def load_banner_slots(con: sqlite3.Connection, profile_id: str) -> list[dict[str, Any]]:
    df = pd.read_sql_query(
        """
        SELECT *
        FROM fantasy_banner_instance_slots
        WHERE profile_id = ?
          AND enabled = 1
        ORDER BY role_scope, slot_index
        """,
        con,
        params=(profile_id,),
    )
    return df.to_dict(orient="records")


def load_template_color_map(con: sqlite3.Connection, template_id: str | None) -> dict[tuple[str, int], str]:
    if not template_id:
        return {}
    df = pd.read_sql_query(
        """
        SELECT role_scope, slot_index, allowed_color_group
        FROM fantasy_banner_template_slots
        WHERE template_id = ?
        """,
        con,
        params=(template_id,),
    )
    return {
        (str(row["role_scope"]), int(row["slot_index"])): str(row["allowed_color_group"])
        for _, row in df.iterrows()
    }


def load_profile_meta(con: sqlite3.Connection, profile_id: str) -> dict[str, Any]:
    row = con.execute(
        """
        SELECT profile_id, event_id, template_id, profile_name
        FROM fantasy_banner_instances
        WHERE profile_id = ?
        """,
        (profile_id,),
    ).fetchone()
    if not row:
        raise RuntimeError(f"Unknown complex banner profile_id={profile_id}")
    return {
        "profile_id": row[0],
        "event_id": row[1],
        "template_id": row[2],
        "profile_name": row[3],
    }


def load_stat_catalog_by_color(con: sqlite3.Connection) -> dict[str, list[str]]:
    df = pd.read_sql_query(
        """
        SELECT stat_name, LOWER(COALESCE(emblem_color, 'unknown')) AS color_group
        FROM fantasy_scoring_stat_catalog
        """,
        con,
    )
    color_map: dict[str, list[str]] = {}
    for color_group, group in df.groupby("color_group"):
        color_map[str(color_group)] = sorted({str(value) for value in group["stat_name"].tolist()})
    return color_map


def load_rng_boost_priors() -> dict[str, Any]:
    if not STARTER_PRIOR_PATH.exists():
        return {}
    return load_initial_state_preset(STARTER_PRIOR_PATH)


def _global_weight_map(rows: list[dict[str, Any]], key_name: str) -> dict[str, float]:
    return {str(row[key_name]): float(row.get("weight", 0.0)) for row in rows}


def _color_stat_weight_map(payload: dict[str, Any]) -> dict[str, dict[str, float]]:
    color_rows = payload.get("global_priors", {}).get("generic_color_stat_weights", {})
    result: dict[str, dict[str, float]] = {}
    for color_group, rows in color_rows.items():
        result[str(color_group)] = {str(row["stat_name"]): float(row.get("weight", 0.0)) for row in rows}
    return result


def load_roll_distributions(con: sqlite3.Connection, rule_id: str) -> list[dict[str, Any]]:
    df = pd.read_sql_query(
        """
        SELECT *
        FROM fantasy_banner_roll_distributions
        WHERE rule_id = ?
        """,
        con,
        params=(rule_id,),
    )
    return df.to_dict(orient="records")


def seed_default_roll_distributions(con: sqlite3.Connection) -> None:
    color_map = load_stat_catalog_by_color(con)
    quality_df = pd.read_sql_query("SELECT quality_tier, roll_weight FROM fantasy_banner_quality_rules", con)
    trait_df = pd.read_sql_query("SELECT trait_name, roll_weight FROM fantasy_banner_trait_rules", con)
    starter_priors = load_rng_boost_priors()
    quality_weight_override = _global_weight_map(starter_priors.get("global_priors", {}).get("quality_weights", []), "quality_tier")
    trait_weight_override = _global_weight_map(starter_priors.get("global_priors", {}).get("trait_weights", []), "trait_name")
    color_stat_override = _color_stat_weight_map(starter_priors)
    cur = con.cursor()
    cur.execute("DELETE FROM fantasy_banner_roll_distributions WHERE rule_id LIKE 'ti2026_generic_%'")

    rows: list[tuple[Any, ...]] = []
    for color_group, stats in color_map.items():
        for stat_name in stats:
            stat_weight = float(color_stat_override.get(color_group, {}).get(stat_name, 1.0))
            rows.append(
                (
                    "ti2026_generic_reroll_stat_v1",
                    "stat_name",
                    stat_name,
                    "",
                    color_group,
                    stat_weight,
                    "Generic stat reroll weighted by starter-observed color/stat prior when available.",
                )
            )
            rows.append(
                (
                    "ti2026_generic_reroll_emblem_v1",
                    "stat_name",
                    stat_name,
                    "",
                    color_group,
                    stat_weight,
                    "Generic emblem reroll stat branch weighted by starter-observed color/stat prior when available.",
                )
            )
    for _, row in quality_df.iterrows():
        weight = float(quality_weight_override.get(str(row["quality_tier"]), row["roll_weight"]))
        rows.append(
            (
                "ti2026_generic_reroll_quality_v1",
                "quality_tier",
                row["quality_tier"],
                "",
                "",
                weight,
                "Generic quality reroll boosted toward more common observed tiers when available.",
            )
        )
        rows.append(
            (
                "ti2026_generic_reroll_emblem_v1",
                "quality_tier",
                row["quality_tier"],
                "",
                "",
                weight,
                "Generic emblem reroll quality branch boosted toward more common observed tiers when available.",
            )
        )
    for _, row in trait_df.iterrows():
        weight = float(trait_weight_override.get(str(row["trait_name"]), row["roll_weight"]))
        rows.append(
            (
                "ti2026_generic_reroll_trait_v1",
                "trait_name",
                row["trait_name"],
                "",
                "",
                weight,
                "Generic trait reroll boosted toward more common observed traits when available.",
            )
        )
        rows.append(
            (
                "ti2026_generic_reroll_emblem_v1",
                "trait_name",
                row["trait_name"],
                "",
                "",
                weight,
                "Generic emblem reroll trait branch boosted toward more common observed traits when available.",
            )
        )
    cur.executemany(
        """
        INSERT OR REPLACE INTO fantasy_banner_roll_distributions(
            rule_id, item_kind, item_value, role_scope, allowed_color_group, weight, notes, updated_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        rows,
    )
    con.commit()


def _distribution_subset(
    distributions: list[dict[str, Any]],
    *,
    item_kind: str,
    allowed_color_group: str = "",
) -> list[dict[str, Any]]:
    rows = [row for row in distributions if str(row["item_kind"]) == item_kind]
    if allowed_color_group:
        scoped = [row for row in rows if str(row.get("allowed_color_group", "")) == allowed_color_group]
        if scoped:
            return scoped
    return rows


def build_distribution_index(distributions: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    index: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in distributions:
        key = (str(row.get("item_kind", "")), str(row.get("allowed_color_group", "")))
        index.setdefault(key, []).append(row)
    return index


def apply_roll_action(
    slots: list[dict[str, Any]],
    action: RollAction,
    *,
    distributions: list[dict[str, Any]] | None = None,
    distribution_index: dict[tuple[str, str], list[dict[str, Any]]] | None = None,
    template_color_map: dict[tuple[str, int], str],
    rng: random.Random,
) -> list[dict[str, Any]]:
    updated = [dict(slot) for slot in slots]
    if distribution_index is None:
        distribution_index = build_distribution_index(distributions or [])

    tier_order = ("tier_i", "tier_ii", "tier_iii", "tier_iv", "tier_v")

    def shift_tier(slot: dict[str, Any], direction: int) -> bool:
        current = str(slot.get("quality_tier", "")).lower()
        if current not in tier_order:
            return False
        target = max(0, min(len(tier_order) - 1, tier_order.index(current) + direction))
        if target == tier_order.index(current):
            return False
        slot["quality_tier"] = tier_order[target]
        return True

    role_slots = [slot for slot in updated if str(slot.get("role_scope", "")) == action.role_scope]
    if action.action_scope == "role_quality_shift_plus1":
        eligible = [slot for slot in role_slots if str(slot.get("quality_tier", "")).lower() in tier_order[:-1]]
        if eligible:
            shift_tier(eligible[int(rng.random() * len(eligible))], +1)
        return updated
    if action.action_scope == "role_quality_shift_plus2_minus1":
        upward = [slot for slot in role_slots if str(slot.get("quality_tier", "")).lower() in tier_order[:-1]]
        selected_up: list[dict[str, Any]] = []
        # The game wording refers to two increases and one decrease, so an
        # emblem cannot be both increased and decreased in the same operation.
        while upward and len(selected_up) < 2:
            selected_up.append(upward.pop(int(rng.random() * len(upward))))
        for slot in selected_up:
            shift_tier(slot, +1)
        upward_ids = {id(slot) for slot in selected_up}
        downward = [slot for slot in role_slots if id(slot) not in upward_ids and str(slot.get("quality_tier", "")).lower() in tier_order[1:]]
        if downward:
            shift_tier(downward[int(rng.random() * len(downward))], -1)
        return updated
    def stat_choices(slot: dict[str, Any], allowed_color: str) -> list[dict[str, Any]]:
        used = {str(item.get("stat_name", "")) for item in updated if str(item.get("role_scope")) == action.role_scope and int(item.get("slot_index", -1)) != int(slot.get("slot_index", -1))}
        rows = distribution_index.get(("stat_name", allowed_color)) or distribution_index.get(("stat_name", "")) or []
        return [item for item in rows if str(item.get("item_value", "")) != str(slot.get("stat_name", "")) and str(item.get("item_value", "")) not in used]
    def quality_choices(slot: dict[str, Any]) -> list[dict[str, Any]]:
        return [item for item in (distribution_index.get(("quality_tier", "")) or []) if str(item.get("item_value", "")) != str(slot.get("quality_tier", ""))]
    def trait_choices(slot: dict[str, Any]) -> list[dict[str, Any]]:
        # A trait reroll must change the selected emblem.  Duplicate traits on
        # different emblems remain valid (for example, Friendly needs three).
        return [
            item
            for item in (distribution_index.get(("trait_name", "")) or [])
            if str(item.get("item_value", "")) != str(slot.get("trait_name", ""))
        ]
    random_target: int | None = None
    if action.action_scope == "role_color_random":
        eligible = [int(slot["slot_index"]) for slot in updated if str(slot["role_scope"]) == action.role_scope and str(slot.get("color_group", "")).lower() == str(action.target_color_group).lower()]
        if eligible:
            random_target = eligible[int(rng.random() * len(eligible))]
    for slot in updated:
        targets_slot = str(slot["role_scope"]) == action.role_scope and int(slot["slot_index"]) == int(action.slot_index)
        targets_role_color = (
            action.action_scope == "role_color_all"
            and str(slot["role_scope"]) == action.role_scope
            and str(slot.get("color_group", "")).lower() == str(action.target_color_group).lower()
        )
        targets_random_color = action.action_scope == "role_color_random" and str(slot["role_scope"]) == action.role_scope and int(slot["slot_index"]) == random_target
        if targets_slot or targets_role_color or targets_random_color:
            allowed_color = template_color_map.get((action.role_scope, action.slot_index), str(slot.get("color_group") or ""))
            if action.token_type == "reroll_stat":
                choices = stat_choices(slot, allowed_color)
                if choices: slot["stat_name"] = _weighted_choice(rng, choices)["item_value"]
                slot["color_group"] = allowed_color
            elif action.token_type == "reroll_quality":
                choices = quality_choices(slot)
                if choices: slot["quality_tier"] = _weighted_choice(rng, choices)["item_value"]
            elif action.token_type == "reroll_trait":
                choices = trait_choices(slot)
                if choices:
                    slot["trait_name"] = _weighted_choice(rng, choices)["item_value"]
            elif action.token_type == "reroll_emblem":
                slot["color_group"] = allowed_color
                stats = stat_choices(slot, allowed_color); qualities = quality_choices(slot)
                stat_choice = _weighted_choice(rng, stats) if stats else None
                quality_choice = _weighted_choice(rng, qualities) if qualities else None
                traits = trait_choices(slot)
                trait_choice = _weighted_choice(rng, traits) if traits else None
                if stat_choice: slot["stat_name"] = stat_choice["item_value"]
                if quality_choice: slot["quality_tier"] = quality_choice["item_value"]
                if trait_choice:
                    slot["trait_name"] = trait_choice["item_value"]
            # Slot actions affect one emblem; role-color actions affect every matching emblem.
            if action.action_scope != "role_color_all":
                break
    return updated


def evaluate_banner_state(
    con: sqlite3.Connection,
    slots: list[dict[str, Any]],
    *,
    objective_mode: str = "balanced",
    benchmark_df: pd.DataFrame | None = None,
    quality_map: dict[str, dict[str, Any]] | None = None,
    trait_map: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if quality_map is None or trait_map is None:
        quality_map, trait_map = load_rule_maps(con)
    benchmarks = benchmark_df if benchmark_df is not None else load_role_stat_benchmarks(con)
    return compute_banner_intrinsic_value(
        slots,
        benchmarks,
        quality_map,
        trait_map,
        objective_mode=objective_mode,
    )


def simulate_rollouts(
    *,
    profile_id: str,
    db_path: Path = DB_PATH,
    benchmark_db_path: Path = BENCHMARK_DB_PATH,
    benchmark_event_id: str = "ewc2026",
    actions: list[RollAction],
    simulations: int = 1000,
    objective_mode: str = "balanced",
    seed: int = 7,
    example_count: int = 3,
    return_outcomes: bool = False,
) -> dict[str, Any]:
    con = sqlite3.connect(str(db_path))
    benchmark_con = sqlite3.connect(str(benchmark_db_path))
    try:
        meta = load_profile_meta(con, profile_id)
        seed_default_roll_distributions(con)
        base_slots = load_banner_slots(con, profile_id)
        template_color_map = load_template_color_map(con, meta["template_id"])
        quality_map, trait_map = load_rule_maps(con)
        benchmark_df = load_role_stat_benchmarks(benchmark_con)
        distribution_indices: dict[str, dict[tuple[str, str], list[dict[str, Any]]]] = {}
        for action in actions:
            rule_id = f"ti2026_generic_{action.token_type}_v1"
            if rule_id not in distribution_indices:
                distribution_indices[rule_id] = build_distribution_index(load_roll_distributions(con, rule_id))
        baseline_eval = evaluate_banner_state(
            con,
            base_slots,
            objective_mode=objective_mode,
            benchmark_df=benchmark_df,
            quality_map=quality_map,
            trait_map=trait_map,
        )
        outcomes: list[float] = []
        state_examples: list[dict[str, Any]] = []
        for sim_idx in range(simulations):
            rng = random.Random(seed + sim_idx)
            slots = [dict(slot) for slot in base_slots]
            for action in actions:
                rule_id = f"ti2026_generic_{action.token_type}_v1"
                slots = apply_roll_action(
                    slots,
                    action,
                    distribution_index=distribution_indices[rule_id],
                    template_color_map=template_color_map,
                    rng=rng,
                )
            scored = evaluate_banner_state(
                con,
                slots,
                objective_mode=objective_mode,
                benchmark_df=benchmark_df,
                quality_map=quality_map,
                trait_map=trait_map,
            )
            outcomes.append(float(scored["intrinsic_value_raw"]))
            if sim_idx < max(0, int(example_count)):
                state_examples.append(
                    {
                        "simulation_index": sim_idx,
                        "intrinsic_value_raw": scored["intrinsic_value_raw"],
                        "slots": scored["evaluated_slots"],
                    }
                )
        if not outcomes:
            expected_value = baseline_eval["intrinsic_value_raw"]
            median_value = baseline_eval["intrinsic_value_raw"]
            p75_value = baseline_eval["intrinsic_value_raw"]
            p90_value = baseline_eval["intrinsic_value_raw"]
            min_value = baseline_eval["intrinsic_value_raw"]
            max_value = baseline_eval["intrinsic_value_raw"]
            positive_rate = 0.0
            downside_rate = 0.0
        else:
            sorted_outcomes = sorted(outcomes)
            expected_value = sum(outcomes) / len(outcomes)
            median_value = sorted_outcomes[int((len(sorted_outcomes) - 1) * 0.50)]
            p75_value = sorted_outcomes[int((len(sorted_outcomes) - 1) * 0.75)]
            p90_value = sorted_outcomes[int((len(sorted_outcomes) - 1) * 0.90)]
            min_value = sorted_outcomes[0]
            max_value = sorted_outcomes[-1]
            baseline_value = float(baseline_eval["intrinsic_value_raw"])
            positive_rate = sum(1 for value in outcomes if value > baseline_value) / len(outcomes)
            downside_rate = sum(1 for value in outcomes if value < baseline_value) / len(outcomes)
        baseline_value = float(baseline_eval["intrinsic_value_raw"])
        expected_delta = expected_value - baseline_value
        median_delta = median_value - baseline_value
        p75_delta = p75_value - baseline_value
        p90_delta = p90_value - baseline_value
        min_delta = min_value - baseline_value
        max_delta = max_value - baseline_value
        return {
            "profile_id": profile_id,
            "event_id": meta["event_id"],
            "benchmark_event_id": benchmark_event_id,
            "benchmark_db_path": str(benchmark_db_path),
            "objective_mode": objective_mode,
            "baseline_intrinsic_value_raw": baseline_value,
            "expected_intrinsic_value_raw": round(expected_value, 4),
            "median_intrinsic_value_raw": round(median_value, 4),
            "p75_intrinsic_value_raw": round(p75_value, 4),
            "p90_intrinsic_value_raw": round(p90_value, 4),
            "min_intrinsic_value_raw": round(min_value, 4),
            "max_intrinsic_value_raw": round(max_value, 4),
            "expected_delta_raw": round(expected_delta, 4),
            "median_delta_raw": round(median_delta, 4),
            "p75_delta_raw": round(p75_delta, 4),
            "p90_delta_raw": round(p90_delta, 4),
            "min_delta_raw": round(min_delta, 4),
            "max_delta_raw": round(max_delta, 4),
            "positive_rate": round(positive_rate, 6),
            "downside_rate": round(downside_rate, 6),
            "simulations": simulations,
            "actions": [action.__dict__ for action in actions],
            "state_examples": state_examples if example_count > 0 else [],
            "outcomes": [round(float(value), 4) for value in outcomes] if return_outcomes else [],
        }
    finally:
        benchmark_con.close()
        con.close()


def actions_from_json(payload: str) -> list[RollAction]:
    data = json.loads(payload)
    return [
        RollAction(
            token_type=str(item["token_type"]),
            role_scope=str(item["role_scope"]),
            slot_index=int(item["slot_index"]),
        )
        for item in data
    ]
