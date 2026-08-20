from __future__ import annotations

import csv
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ParsedToken:
    token_id: str
    family: str
    scope: str
    color_group: str | None
    generic_token_type: str


FAMILY_TO_GENERIC_TOKEN_TYPE = {
    "stat": "reroll_stat",
    "quality": "reroll_quality",
    "trait": "reroll_trait",
}


def parse_token_id(token_id: str) -> ParsedToken:
    if token_id == "quality_shift_plus1":
        return ParsedToken(
            token_id=token_id,
            family="quality",
            scope="shift_plus1",
            color_group=None,
            generic_token_type="reroll_quality",
        )
    if token_id == "quality_shift_plus2_minus1":
        return ParsedToken(
            token_id=token_id,
            family="quality",
            scope="shift_plus2_minus1",
            color_group=None,
            generic_token_type="reroll_quality",
        )
    parts = token_id.split("_")
    if len(parts) < 3:
        raise ValueError(f"Unrecognized token_id={token_id}")
    family = parts[0]
    color_group = parts[-1]
    scope = "_".join(parts[1:-1])
    generic_token_type = FAMILY_TO_GENERIC_TOKEN_TYPE.get(family)
    if generic_token_type is None:
        raise ValueError(f"Unsupported token family in token_id={token_id}")
    return ParsedToken(
        token_id=token_id,
        family=family,
        scope=scope,
        color_group=color_group,
        generic_token_type=generic_token_type,
    )


def read_exact_token_rows(report_csv_path: Path) -> list[dict[str, Any]]:
    with report_csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    out_rows: list[dict[str, Any]] = []
    for row in rows:
        token_id = str(row["token_id"])
        parsed = parse_token_id(token_id)
        out_rows.append(
            {
                "token_id": token_id,
                "exact_observed_count": int(float(row["exact_observed_count"] or 0)),
                "exact_observed_probability": float(row["exact_observed_probability"] or 0.0),
                "family": parsed.family,
                "scope": parsed.scope,
                "color_group": parsed.color_group or "",
                "generic_token_type": parsed.generic_token_type,
            }
        )
    return out_rows


def apply_manual_count_adjustments(
    rows: list[dict[str, Any]],
    adjustments: dict[str, int],
    *,
    max_abs_adjustment: int = 2,
) -> list[dict[str, Any]]:
    adjusted_rows: list[dict[str, Any]] = []
    for row in rows:
        token_id = str(row["token_id"])
        requested = int(adjustments.get(token_id, 0))
        if abs(requested) > max_abs_adjustment:
            requested = max_abs_adjustment if requested > 0 else -max_abs_adjustment
        adjusted_count = max(0, int(row["exact_observed_count"]) + requested)
        updated = dict(row)
        updated["manual_adjustment"] = requested
        updated["adjusted_count"] = adjusted_count
        adjusted_rows.append(updated)
    total = sum(int(row["adjusted_count"]) for row in adjusted_rows)
    for row in adjusted_rows:
        row["adjusted_probability"] = (float(row["adjusted_count"]) / total) if total > 0 else 0.0
    adjusted_rows.sort(key=lambda item: (-int(item["adjusted_count"]), str(item["token_id"])))
    return adjusted_rows


def aggregate_generic_token_type_weights(rows: list[dict[str, Any]]) -> dict[str, float]:
    weights: dict[str, float] = {}
    for row in rows:
        token_type = str(row["generic_token_type"])
        weights[token_type] = weights.get(token_type, 0.0) + float(row["adjusted_count"])
    return weights


def weighted_sample_without_replacement(
    rng: random.Random,
    items: list[dict[str, Any]],
    k: int,
    *,
    weight_key: str,
) -> list[dict[str, Any]]:
    pool = [dict(item) for item in items]
    selected: list[dict[str, Any]] = []
    target = min(max(int(k), 0), len(pool))
    while pool and len(selected) < target:
        total_weight = sum(max(float(item.get(weight_key, 0.0)), 0.0) for item in pool)
        if total_weight <= 0:
            choice = pool.pop(0)
            selected.append(choice)
            continue
        threshold = rng.random() * total_weight
        running = 0.0
        chosen_index = len(pool) - 1
        for idx, item in enumerate(pool):
            running += max(float(item.get(weight_key, 0.0)), 0.0)
            if running >= threshold:
                chosen_index = idx
                break
        selected.append(pool.pop(chosen_index))
    return selected


def build_empirical_token_preset_payload(
    *,
    report_csv_path: Path,
    adjustments: dict[str, int],
    preset_id: str,
    display_name: str,
    description: str,
) -> dict[str, Any]:
    base_rows = read_exact_token_rows(report_csv_path)
    adjusted_rows = apply_manual_count_adjustments(base_rows, adjustments)
    family_weights = aggregate_generic_token_type_weights(adjusted_rows)
    total_adjusted_count = sum(int(row["adjusted_count"]) for row in adjusted_rows)

    def _token_spec(token_type: str, display: str, notes: str) -> dict[str, Any]:
        return {
            "token_type": token_type,
            "display_name": display,
            "enabled": family_weights.get(token_type, 0.0) > 0,
            "max_uses": 1,
            "offer_weight": round(float(family_weights.get(token_type, 0.0)), 6),
            "role_scopes": ["core", "mid", "support"],
            "slot_indices": "all",
            "notes": notes,
        }

    payload = {
        "preset_id": preset_id,
        "display_name": display_name,
        "description": description,
        "inventory_mode": "empirical_observed_counts_v1",
        "benchmark_policy": "ewc2026_only",
        "default_objective_mode": "balanced",
        "source_report_csv": str(report_csv_path),
        "observed_total_adjusted_count": total_adjusted_count,
        "manual_count_adjustments": adjustments,
        "token_specs": [
            _token_spec(
                "reroll_stat",
                "Reroll stat",
                "Family-level offer weight derived from observed run1-8 token counts after light manual smoothing.",
            ),
            _token_spec(
                "reroll_quality",
                "Reroll quality",
                "Family-level offer weight derived from observed run1-8 token counts after light manual smoothing.",
            ),
            _token_spec(
                "reroll_trait",
                "Reroll trait",
                "Family-level offer weight derived from observed run1-8 token counts after light manual smoothing.",
            ),
            {
                "token_type": "reroll_emblem",
                "display_name": "Reroll full emblem",
                "enabled": False,
                "max_uses": 1,
                "offer_weight": 0.0,
                "role_scopes": ["core", "mid", "support"],
                "slot_indices": "all",
                "notes": "Disabled in the empirical preset because no direct evidence for this token family exists in the observed run1-8 sample.",
            },
        ],
        "token_offer_distribution": adjusted_rows,
    }
    return payload


def write_empirical_token_preset(payload: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
