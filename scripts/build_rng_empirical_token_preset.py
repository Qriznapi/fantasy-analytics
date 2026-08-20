from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fantasy_rng_empirical import build_empirical_token_preset_payload, write_empirical_token_preset  # noqa: E402


DEFAULT_REPORT_PATH = PROJECT_ROOT / "reports" / "rng_token_frequency_observed.csv"
DEFAULT_PRESET_PATH = PROJECT_ROOT / "configs" / "rng_tokens" / "observed_run1_8_empirical_v1.json"
DEFAULT_REPORT_OUT_CSV = PROJECT_ROOT / "reports" / "rng_token_frequency_adjusted_v1.csv"
DEFAULT_REPORT_OUT_MD = PROJECT_ROOT / "reports" / "rng_token_frequency_adjusted_v1.md"
DEFAULT_ADJUSTMENTS = {
    "quality_first_green": 2,
    "stat_last_red": -2,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build empirical RNG token preset from observed run frequencies.")
    parser.add_argument("--report-csv", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--preset-out", default=str(DEFAULT_PRESET_PATH))
    parser.add_argument("--report-out-csv", default=str(DEFAULT_REPORT_OUT_CSV))
    parser.add_argument("--report-out-md", default=str(DEFAULT_REPORT_OUT_MD))
    parser.add_argument("--adjustments-json", default=json.dumps(DEFAULT_ADJUSTMENTS, ensure_ascii=False))
    return parser.parse_args()


def write_adjusted_reports(payload: dict[str, object], csv_path: Path, md_path: Path) -> None:
    rows = list(payload["token_offer_distribution"])  # type: ignore[index]
    fieldnames = [
        "token_id",
        "family",
        "scope",
        "color_group",
        "generic_token_type",
        "exact_observed_count",
        "manual_adjustment",
        "adjusted_count",
        "adjusted_probability",
    ]
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})

    lines = [
        "# Adjusted RNG token frequency",
        "",
        f"- preset_id: `{payload['preset_id']}`",
        f"- observed_total_adjusted_count: `{payload['observed_total_adjusted_count']}`",
        f"- manual_adjustments: `{json.dumps(payload['manual_count_adjustments'], ensure_ascii=False)}`",
        "",
        "| token_id | family | scope | color | exact_count | adjustment | adjusted_count | adjusted_prob |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['token_id']} | {row['family']} | {row['scope']} | {row['color_group'] or '-'} | "
            f"{row['exact_observed_count']} | {row['manual_adjustment']} | {row['adjusted_count']} | "
            f"{float(row['adjusted_probability']):.6f} |"
        )
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    report_csv = Path(args.report_csv)
    preset_out = Path(args.preset_out)
    report_out_csv = Path(args.report_out_csv)
    report_out_md = Path(args.report_out_md)
    adjustments = json.loads(args.adjustments_json)

    payload = build_empirical_token_preset_payload(
        report_csv_path=report_csv,
        adjustments=adjustments,
        preset_id="observed_run1_8_empirical_v1",
        display_name="Observed run1-8 empirical token preset",
        description=(
            "Empirical token preset seeded from observed runs 1-8. "
            "It keeps the existing generic optimizer pipeline compatible via family-level offer weights, "
            "while also storing a token_id-level offer distribution for the later high-fidelity token engine."
        ),
    )
    write_empirical_token_preset(payload, preset_out)
    write_adjusted_reports(payload, report_out_csv, report_out_md)
    print(
        json.dumps(
            {
                "preset_out": str(preset_out),
                "report_out_csv": str(report_out_csv),
                "report_out_md": str(report_out_md),
                "observed_total_adjusted_count": payload["observed_total_adjusted_count"],
                "manual_adjustments": payload["manual_count_adjustments"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
