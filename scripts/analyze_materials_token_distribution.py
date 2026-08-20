"""Compare the imported manual token sample with the immutable empirical preset."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SPECIAL = {"quality_shift_plus1", "quality_shift_plus2_minus1"}


def _parts(token_id: str) -> tuple[str, str, str]:
    if token_id in SPECIAL:
        return "quality_shift", "any", token_id.removeprefix("quality_")
    family, remainder = token_id.split("_", 1)
    for scope in ("random_one", "first", "last", "all"):
        suffix = f"{scope}_"
        if remainder.startswith(suffix):
            return family, remainder.removeprefix(suffix), scope
    raise ValueError(f"Unrecognized normalized token ID: {token_id}")


def _rate(count: int, total: int) -> float:
    return count / total if total else 0.0


def _z(sample_count: int, sample_total: int, reference_probability: float) -> float | None:
    variance = sample_total * reference_probability * (1.0 - reference_probability)
    if variance <= 0:
        return None
    return (sample_count - sample_total * reference_probability) / math.sqrt(variance)


def _table(rows: list[dict[str, Any]]) -> list[str]:
    lines = ["| Token | Old count | Old % | Materials count | Materials % | Merged % | Delta pp | z vs old |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        z = "-" if row["z_vs_old"] is None else f"{row['z_vs_old']:+.2f}"
        lines.append(
            f"| `{row['token_id']}` | {row['old_count']} | {row['old_probability'] * 100:.2f} | "
            f"{row['materials_count']} | {row['materials_probability'] * 100:.2f} | {row['merged_probability'] * 100:.2f} | "
            f"{row['delta_pp']:+.2f} | {z} |"
        )
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze all imported manual RNG token observations.")
    parser.add_argument("--records", default=str(ROOT / "data" / "raw" / "rng_token_observations" / "materials_sheets_1_2.csv"))
    parser.add_argument("--empirical-preset", default=str(ROOT / "configs" / "rng_tokens" / "observed_run1_8_empirical_v1.json"))
    parser.add_argument("--output", default=str(ROOT / "reports" / "rng_token_materials_sheets_1_2_analysis.md"))
    args = parser.parse_args()

    records = list(csv.DictReader(Path(args.records).open(encoding="utf-8-sig")))
    observed = Counter(str(row["token_id"]) for row in records)
    preset = json.loads(Path(args.empirical_preset).read_text(encoding="utf-8"))
    old = {str(row["token_id"]): int(row.get("exact_observed_count", 0)) for row in preset["token_offer_distribution"]}
    old_total, sample_total = sum(old.values()), len(records)
    merged_total = old_total + sample_total

    token_rows: list[dict[str, Any]] = []
    for token_id in sorted(set(old) | set(observed)):
        old_count, material_count = old.get(token_id, 0), observed.get(token_id, 0)
        old_probability = _rate(old_count, old_total)
        token_rows.append({
            "token_id": token_id,
            "old_count": old_count,
            "old_probability": old_probability,
            "materials_count": material_count,
            "materials_probability": _rate(material_count, sample_total),
            "merged_probability": _rate(old_count + material_count, merged_total),
            "delta_pp": (_rate(material_count, sample_total) - old_probability) * 100,
            "z_vs_old": _z(material_count, sample_total, old_probability),
        })
    token_rows.sort(key=lambda row: (-row["materials_count"], row["token_id"]))

    def aggregate(key_fn):
        old_counts: Counter[str] = Counter(); sample_counts: Counter[str] = Counter()
        for token_id, count in old.items(): old_counts[key_fn(token_id)] += count
        for token_id, count in observed.items(): sample_counts[key_fn(token_id)] += count
        return [
            {"group": key, "old_count": old_counts[key], "old_probability": _rate(old_counts[key], old_total), "materials_count": sample_counts[key], "materials_probability": _rate(sample_counts[key], sample_total), "delta_pp": (_rate(sample_counts[key], sample_total) - _rate(old_counts[key], old_total)) * 100}
            for key in sorted(set(old_counts) | set(sample_counts))
        ]

    family = aggregate(lambda token_id: _parts(token_id)[0])
    color = aggregate(lambda token_id: _parts(token_id)[1])
    scope = aggregate(lambda token_id: _parts(token_id)[2])
    largest = sorted(token_rows, key=lambda row: abs(row["delta_pp"]), reverse=True)[:10]
    strong = [row for row in token_rows if row["z_vs_old"] is not None and abs(row["z_vs_old"]) >= 2.0]
    special_count = sum(observed[key] for key in SPECIAL)

    lines = [
        "# Materials Sheets 1-2 Token Distribution Analysis", "",
        "## Scope", "",
        f"- New manual sample: **{sample_total}** token offers (two 30-roll sheets).",
        f"- Immutable reference: **{old_total}** observed offers from `observed_run1_8_empirical_v1`.",
        f"- Hypothetical merged sample: **{merged_total}** offers. The source preset is not overwritten.",
        "- `z vs old` is a descriptive binomial standardized difference, not proof of a true production-rate change; the new sample is only 180 offers.", "",
        "## Family Mix", "",
        "| Family | Old % | Materials % | Delta pp |", "|---|---:|---:|---:|",
    ]
    lines += [f"| {row['group']} | {row['old_probability'] * 100:.2f} | {row['materials_probability'] * 100:.2f} | {row['delta_pp']:+.2f} |" for row in family]
    lines += ["", "## Color Mix", "", "| Color | Old % | Materials % | Delta pp |", "|---|---:|---:|---:|"]
    lines += [f"| {row['group']} | {row['old_probability'] * 100:.2f} | {row['materials_probability'] * 100:.2f} | {row['delta_pp']:+.2f} |" for row in color]
    lines += ["", "## Scope Mix", "", "| Scope | Old % | Materials % | Delta pp |", "|---|---:|---:|---:|"]
    lines += [f"| {row['group']} | {row['old_probability'] * 100:.2f} | {row['materials_probability'] * 100:.2f} | {row['delta_pp']:+.2f} |" for row in scope]
    lines += ["", "## All Token IDs", ""] + _table(token_rows)
    lines += ["", "## Interpretation", "", f"- Quality-shift tokens: **{special_count}/{sample_total} = {special_count / sample_total * 100:.2f}%**, equivalent to **{special_count / sample_total * 90:.1f}** appearances per 30-roll session."]
    largest_text = ", ".join(
        f"`{row['token_id']}` ({row['delta_pp']:+.2f} pp)" for row in largest
    )
    lines += [f"- Largest descriptive deviations: {largest_text}."]
    if strong:
        strong_text = ", ".join(
            f"`{row['token_id']}` ({row['z_vs_old']:+.2f})" for row in strong
        )
        lines += [f"- Tokens with |z| >= 2 in this small comparison: {strong_text}."]
    lines += ["- Recommendation: keep `empirical_v1` immutable, retain this source as a separately weighted observation batch, and keep the current v3 quality-shift prior near seven until more independent 30-roll runs are added.", ""]
    Path(args.output).write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"output": str(Path(args.output).resolve()), "sample_offers": sample_total, "special_count": special_count, "strong_deviations": [row["token_id"] for row in strong]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
