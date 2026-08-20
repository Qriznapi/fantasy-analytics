"""Build a color-balanced derivative of the immutable observed token preset."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "configs" / "rng_tokens" / "observed_run1_8_empirical_v1.json"
DEFAULT_OUTPUT = ROOT / "configs" / "rng_tokens" / "observed_run1_8_color_balanced_v2.json"
COLORS = ("red", "green", "blue")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a color-balanced RNG token preset.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    rows = payload["token_offer_distribution"]
    totals: dict[str, float] = defaultdict(float)
    for row in rows:
        color = str(row.get("color_group", "")).lower()
        if color in COLORS:
            totals[color] += float(row.get("adjusted_count", 0.0))
    target = sum(totals.values()) / len(COLORS)
    scales = {color: target / totals[color] for color in COLORS}

    for row in rows:
        color = str(row.get("color_group", "")).lower()
        original = float(row.get("adjusted_count", 0.0))
        if color in scales:
            row["source_adjusted_count"] = original
            row["color_balance_scale"] = round(scales[color], 8)
            row["adjusted_count"] = round(original * scales[color], 6)
        else:
            row["color_balance_scale"] = 1.0
    total = sum(float(row.get("adjusted_count", 0.0)) for row in rows)
    for row in rows:
        row["adjusted_probability"] = round(float(row.get("adjusted_count", 0.0)) / total, 10) if total else 0.0

    payload["preset_id"] = "observed_run1_8_color_balanced_v2"
    payload["display_name"] = "Observed run1-8 color-balanced token preset v2"
    payload["description"] = (
        "Derived from the immutable observed run1-8 preset. Keeps each color's observed "
        "token-family and scope mix, but rescales color totals to equal red/green/blue mass."
    )
    payload["inventory_mode"] = "color_balanced_derivative_of_empirical_observed_counts_v1"
    payload["source_preset"] = str(Path(args.input).name)
    payload["color_balance_target_count"] = round(target, 6)
    payload["color_balance_scales"] = {key: round(value, 8) for key, value in scales.items()}
    payload["observed_total_adjusted_count"] = round(total, 6)
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "target_per_color": target, "scales": scales}, ensure_ascii=False))


if __name__ == "__main__":
    main()
