from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path


TEAM_CLASSES = {
    "CDOTA_DataRadiant": "radiant",
    "CDOTA_DataDire": "dire",
}

METRIC_FIELD_MAP = {
    "m_iWatchersTaken": "watchers_taken",
    "m_iLotusesTaken": "lotuses_taken",
    "m_iTormentorKills": "tormentor_kills",
    "m_nAcquiredMadstone": "acquired_madstone",
    "m_nCurrentMadstone": "current_madstone",
}

TEAM_FIELD_RE = re.compile(
    r"^m_vecDataTeam\.(?P<slot>\d{4})\.(?P<field>"
    r"m_iWatchersTaken|m_iLotusesTaken|m_iTormentorKills|m_nAcquiredMadstone|m_nCurrentMadstone"
    r")=(?P<value>-?\d+)$"
)
MATCH_ID_RE = re.compile(r"(\d{8,})")


@dataclass(slots=True)
class ReplayMetricEvent:
    match_id: int
    tick: int
    event_type: str
    team_side: str
    entity_handle: int
    team_slot: int
    metric_name: str
    metric_value: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse source2-demo team metric logs into tabular replay-derived fantasy metrics."
    )
    parser.add_argument("--input", required=True, help="Path to a source2_probe_*_tick*.txt file.")
    parser.add_argument("--output-dir", default="", help="Directory for CSV/JSON outputs. Defaults near the input file.")
    parser.add_argument("--match-id", type=int, default=0, help="Override inferred match id.")
    return parser.parse_args()


def infer_match_id(path: Path, explicit_match_id: int) -> int:
    if explicit_match_id:
        return explicit_match_id
    match = MATCH_ID_RE.search(path.name)
    if not match:
        raise ValueError(f"Could not infer match_id from filename: {path.name}")
    return int(match.group(1))


def parse_team_metric_line(line: str, match_id: int) -> list[ReplayMetricEvent]:
    line = line.rstrip("\n")
    if not line.startswith("team_metric\t"):
        return []

    parts = line.split("\t")
    header: dict[str, str] = {}
    events: list[ReplayMetricEvent] = []

    for part in parts[1:]:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        header[key] = value

    team_class = header.get("class", "")
    team_side = TEAM_CLASSES.get(team_class)
    if not team_side:
        return []

    tick = int(header["tick"])
    event_type = header["event"]
    entity_handle = int(header["handle"])

    for part in parts[1:]:
        field_match = TEAM_FIELD_RE.match(part)
        if not field_match:
            continue
        team_slot = int(field_match.group("slot"))
        metric_name = METRIC_FIELD_MAP[field_match.group("field")]
        metric_value = int(field_match.group("value"))
        events.append(
            ReplayMetricEvent(
                match_id=match_id,
                tick=tick,
                event_type=event_type,
                team_side=team_side,
                entity_handle=entity_handle,
                team_slot=team_slot,
                metric_name=metric_name,
                metric_value=metric_value,
            )
        )
    return events


def parse_replay_metric_log(path: Path, match_id: int) -> list[ReplayMetricEvent]:
    events: list[ReplayMetricEvent] = []
    raw_prefix = path.read_bytes()[:4]
    encoding = "utf-16" if raw_prefix.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8"
    with path.open("r", encoding=encoding) as handle:
        for line in handle:
            events.extend(parse_team_metric_line(line, match_id))
    return events


def build_final_snapshot(events: list[ReplayMetricEvent]) -> list[dict[str, int | str]]:
    latest_by_key: dict[tuple[str, int, str], ReplayMetricEvent] = {}
    for event in events:
        key = (event.team_side, event.team_slot, event.metric_name)
        prev = latest_by_key.get(key)
        if prev is None or (event.tick, event.event_type) >= (prev.tick, prev.event_type):
            latest_by_key[key] = event

    final_rows: list[dict[str, int | str]] = []
    grouped: dict[tuple[str, int], dict[str, int | str]] = {}
    for (team_side, team_slot, metric_name), event in sorted(latest_by_key.items()):
        row = grouped.setdefault(
            (team_side, team_slot),
            {
                "team_side": team_side,
                "team_slot": team_slot,
                "last_tick": event.tick,
            },
        )
        row["last_tick"] = max(int(row["last_tick"]), event.tick)
        row[metric_name] = event.metric_value

    for row in grouped.values():
        for metric_name in METRIC_FIELD_MAP.values():
            row.setdefault(metric_name, 0)
        final_rows.append(row)

    final_rows.sort(key=lambda row: (str(row["team_side"]), int(row["team_slot"])))
    return final_rows


def build_summary(events: list[ReplayMetricEvent], final_rows: list[dict[str, int | str]], match_id: int) -> dict[str, object]:
    nonzero_event_counts: dict[str, int] = {}
    max_values: dict[str, int] = {}
    for metric_name in METRIC_FIELD_MAP.values():
        metric_events = [event for event in events if event.metric_name == metric_name]
        nonzero_event_counts[metric_name] = sum(1 for event in metric_events if event.metric_value > 0)
        max_values[metric_name] = max((event.metric_value for event in metric_events), default=0)

    return {
        "match_id": match_id,
        "team_metric_event_rows": len(events),
        "team_metric_final_rows": len(final_rows),
        "nonzero_event_counts": nonzero_event_counts,
        "max_values": max_values,
        "team_sides": sorted({event.team_side for event in events}),
        "team_slots_seen": sorted({event.team_slot for event in events}),
    }


def write_events_csv(path: Path, events: list[ReplayMetricEvent]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "match_id",
                "tick",
                "event_type",
                "team_side",
                "entity_handle",
                "team_slot",
                "metric_name",
                "metric_value",
            ],
        )
        writer.writeheader()
        for event in events:
            writer.writerow(
                {
                    "match_id": event.match_id,
                    "tick": event.tick,
                    "event_type": event.event_type,
                    "team_side": event.team_side,
                    "entity_handle": event.entity_handle,
                    "team_slot": event.team_slot,
                    "metric_name": event.metric_name,
                    "metric_value": event.metric_value,
                }
            )


def write_final_csv(path: Path, final_rows: list[dict[str, int | str]]) -> None:
    fieldnames = [
        "team_side",
        "team_slot",
        "last_tick",
        "watchers_taken",
        "lotuses_taken",
        "tormentor_kills",
        "acquired_madstone",
        "current_madstone",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in final_rows:
            writer.writerow(row)


def build_final_long_rows(match_id: int, final_rows: list[dict[str, int | str]]) -> list[dict[str, int | str]]:
    long_rows: list[dict[str, int | str]] = []
    for row in final_rows:
        for metric_name in METRIC_FIELD_MAP.values():
            long_rows.append(
                {
                    "match_id": match_id,
                    "team_side": row["team_side"],
                    "team_slot": row["team_slot"],
                    "last_tick": row["last_tick"],
                    "stat_name": metric_name,
                    "raw_value": row[metric_name],
                }
            )
    return long_rows


def write_final_long_csv(path: Path, rows: list[dict[str, int | str]]) -> None:
    fieldnames = ["match_id", "team_side", "team_slot", "last_tick", "stat_name", "raw_value"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    args = parse_args()
    input_path = Path(args.input).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else input_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    match_id = infer_match_id(input_path, args.match_id)
    events = parse_replay_metric_log(input_path, match_id)
    final_rows = build_final_snapshot(events)
    final_long_rows = build_final_long_rows(match_id, final_rows)
    summary = build_summary(events, final_rows, match_id)

    stem = input_path.stem
    events_csv = output_dir / f"{stem}.team_metric_events.csv"
    final_csv = output_dir / f"{stem}.team_metric_final.csv"
    final_long_csv = output_dir / f"{stem}.team_metric_final_long.csv"
    summary_json = output_dir / f"{stem}.team_metric_summary.json"

    write_events_csv(events_csv, events)
    write_final_csv(final_csv, final_rows)
    write_final_long_csv(final_long_csv, final_long_rows)
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(
        {
            "match_id": match_id,
            "events_csv": str(events_csv),
            "final_csv": str(final_csv),
            "final_long_csv": str(final_long_csv),
            "summary_json": str(summary_json),
            "summary": summary,
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
