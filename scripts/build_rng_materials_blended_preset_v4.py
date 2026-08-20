"""Build the active token preset from equal old/materials distribution blending."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPECIAL = ("quality_shift_plus1", "quality_shift_plus2_minus1")
COLORS = ("red", "green", "blue")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the color-balanced materials blend v4 preset.")
    parser.add_argument("--empirical", default=str(ROOT / "configs" / "rng_tokens" / "observed_run1_8_empirical_v1.json"))
    parser.add_argument("--base", default=str(ROOT / "configs" / "rng_tokens" / "observed_run1_8_color_balanced_v2.json"))
    parser.add_argument("--materials", default=str(ROOT / "data" / "raw" / "rng_token_observations" / "materials_sheets_1_2.csv"))
    parser.add_argument("--output", default=str(ROOT / "configs" / "rng_tokens" / "observed_run1_8_materials_blended_red_tilt_v4.json"))
    parser.add_argument("--quality-shifts-per-session", type=float, default=7.0)
    parser.add_argument("--offers-per-session", type=int, default=90)
    parser.add_argument("--support-floor", type=float, default=0.001)
    parser.add_argument("--red-ordinary-share", type=float, default=0.35)
    args = parser.parse_args()
    if not 0 < args.quality_shifts_per_session < args.offers_per_session:
        raise ValueError("quality-shifts-per-session must be between 0 and offers-per-session")
    if not 1 / 3 <= args.red_ordinary_share < 1:
        raise ValueError("red-ordinary-share must be at least one third and below one")

    empirical = json.loads(Path(args.empirical).read_text(encoding="utf-8"))
    payload = json.loads(Path(args.base).read_text(encoding="utf-8"))
    empirical_rows = {str(row["token_id"]): row for row in empirical["token_offer_distribution"]}
    material_counts = Counter(row["token_id"] for row in csv.DictReader(Path(args.materials).open(encoding="utf-8-sig")))
    empirical_total = sum(float(row.get("exact_observed_count", 0.0)) for row in empirical_rows.values())
    material_total = sum(material_counts.values())
    rows = payload["token_offer_distribution"]

    raw: dict[str, float] = {}
    for row in rows:
        token_id = str(row["token_id"])
        old_probability = float(empirical_rows.get(token_id, {}).get("exact_observed_count", 0.0)) / empirical_total
        material_probability = material_counts[token_id] / material_total
        raw[token_id] = 0.5 * old_probability + 0.5 * material_probability
        row["old_empirical_probability"] = round(old_probability, 10)
        row["materials_probability"] = round(material_probability, 10)
        row["blend_weight_old"] = 0.5
        row["blend_weight_materials"] = 0.5
        if raw[token_id] == 0.0:
            # Keep known game tokens available even when both small source
            # samples missed them; this is support smoothing, not evidence.
            raw[token_id] = args.support_floor
            row["support_floor_applied"] = True
        else:
            row["support_floor_applied"] = False

    shift_mass = args.quality_shifts_per_session / args.offers_per_session
    shift_raw = sum(raw[token_id] for token_id in SPECIAL)
    if shift_raw <= 0:
        raise ValueError("No quality-shift mass in source distributions")
    non_special = [row for row in rows if str(row["token_id"]) not in SPECIAL]
    by_color = {color: [row for row in non_special if str(row.get("color_group", "")).lower() == color] for color in COLORS}
    ordinary_mass = 1.0 - shift_mass
    target_color_mass = {
        "red": ordinary_mass * args.red_ordinary_share,
        "green": ordinary_mass * (1.0 - args.red_ordinary_share) / 2.0,
        "blue": ordinary_mass * (1.0 - args.red_ordinary_share) / 2.0,
    }
    probabilities: dict[str, float] = {}
    for color, color_rows in by_color.items():
        total = sum(raw[str(row["token_id"])] for row in color_rows)
        if total <= 0:
            raise ValueError(f"No blended probability mass for color {color}")
        for row in color_rows:
            token_id = str(row["token_id"])
            probabilities[token_id] = target_color_mass[color] * raw[token_id] / total
    for token_id in SPECIAL:
        probabilities[token_id] = shift_mass * raw[token_id] / shift_raw

    for row in rows:
        token_id = str(row["token_id"])
        probability = probabilities[token_id]
        row["adjusted_probability"] = round(probability, 10)
        row["adjusted_count"] = round(probability * 100_000, 6)
        row["blend_raw_probability"] = round(raw[token_id], 10)
        row["color_balance_scale"] = None
        row["training_prior_scale"] = None
    total = sum(float(row["adjusted_count"]) for row in rows)
    family_weights: Counter[str] = Counter()
    for row in rows:
        family_weights[str(row.get("generic_token_type", ""))] += float(row["adjusted_count"])
    for spec in payload.get("token_specs", []):
        spec["offer_weight"] = round(family_weights.get(str(spec.get("token_type", "")), 0.0), 6)

    payload.update({
        "preset_id": "observed_run1_8_materials_blended_red_tilt_v4",
        "display_name": "Equal empirical/materials blend with small red tilt and quality-shift anchor v4",
        "description": "Equal blend of immutable empirical_v1 and materials sheets 1-2 token probabilities. Ordinary token mass has a small 35% red / 32.5% green / 32.5% blue tilt; special quality-shift mass is anchored to seven expected appearances per 90 offers.",
        "inventory_mode": "equal_probability_blend_empirical_v1_materials_sheets_1_2_red_tilt_v4",
        "source_presets": [Path(args.empirical).name, Path(args.base).name],
        "materials_records": str(Path(args.materials).resolve()),
        "materials_offer_count": material_total,
        "support_floor_probability": args.support_floor,
        "blend_weight": {"empirical_v1": 0.5, "materials_sheets_1_2": 0.5},
        "color_balance": {"ordinary_token_mass_by_color": {key: round(value, 10) for key, value in target_color_mass.items()}, "ordinary_color_shares": {"red": args.red_ordinary_share, "green": (1.0 - args.red_ordinary_share) / 2.0, "blue": (1.0 - args.red_ordinary_share) / 2.0}},
        "quality_shift_training_prior": {
            "token_ids": list(SPECIAL),
            "target_expected_appearances_per_30_roll_session": args.quality_shifts_per_session,
            "offers_per_session": args.offers_per_session,
            "target_combined_offer_probability": round(shift_mass, 10),
            "reason": "Materials sample supports 7-10 shifts per session; seven remains the conservative anchor.",
        },
        "observed_total_adjusted_count": round(total, 6),
    })
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(Path(args.output).resolve()), "color_target": target_color_mass, "quality_shift_mass": shift_mass}, ensure_ascii=False))


if __name__ == "__main__":
    main()
