from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


OPENDOTA_MATCH_URL = "https://api.opendota.com/api/matches/{match_id}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch replay metadata manifest from OpenDota.")
    parser.add_argument("--match-ids", default="")
    parser.add_argument("--match-ids-file", default="")
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--sleep-sec", type=float, default=0.5)
    parser.add_argument("--timeout-sec", type=int, default=60)
    parser.add_argument("--download-probe-limit", type=int, default=0)
    parser.add_argument("--download-probe-bytes", type=int, default=64)
    return parser.parse_args()


def load_match_ids(args: argparse.Namespace) -> list[int]:
    match_ids: list[int] = []
    if args.match_ids.strip():
        match_ids.extend(int(part.strip()) for part in args.match_ids.split(",") if part.strip())
    if args.match_ids_file:
        for raw_line in Path(args.match_ids_file).read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line:
                match_ids.append(int(line))
    deduped: list[int] = []
    seen: set[int] = set()
    for match_id in match_ids:
        if match_id not in seen:
            seen.add(match_id)
            deduped.append(match_id)
    return deduped


def fetch_json(url: str, *, timeout_sec: int) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    request = urllib.request.Request(url, headers={"User-Agent": "fantasy-analytics-replay-manifest/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload, {
                "http_status": getattr(response, "status", 200),
                "content_type": response.headers.get("Content-Type"),
            }
    except urllib.error.HTTPError as exc:
        return None, {
            "http_status": exc.code,
            "error": f"HTTP {exc.code}: {exc.reason}",
        }
    except Exception as exc:  # noqa: BLE001
        return None, {
            "http_status": None,
            "error": str(exc),
        }


def probe_replay_url(url: str, *, timeout_sec: int, probe_bytes: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "fantasy-analytics-replay-manifest/0.1",
            "Range": f"bytes=0-{max(probe_bytes - 1, 0)}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            payload = response.read()
            return {
                "http_status": getattr(response, "status", 200),
                "content_length": len(payload),
                "content_type": response.headers.get("Content-Type"),
                "prefix_ascii": "".join(chr(b) if 32 <= b <= 126 else "." for b in payload[:12]),
                "prefix_hex": payload[:12].hex(),
            }
    except urllib.error.HTTPError as exc:
        return {
            "http_status": exc.code,
            "error": f"HTTP {exc.code}: {exc.reason}",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "http_status": None,
            "error": str(exc),
        }


def project_record(match_id: int, payload: dict[str, Any] | None, meta: dict[str, Any]) -> dict[str, Any]:
    record: dict[str, Any] = {
        "match_id": match_id,
        "source_name": "opendota",
        "fetched_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **meta,
    }
    if not payload:
        record["status"] = "error"
        return record

    record.update(
        {
            "status": "ok",
            "cluster": payload.get("cluster"),
            "league_id": payload.get("leagueid"),
            "series_id": payload.get("series_id"),
            "start_time": payload.get("start_time"),
            "radiant_name": payload.get("radiant_name"),
            "dire_name": payload.get("dire_name"),
            "replay_salt": payload.get("replay_salt"),
            "replay_url": payload.get("replay_url"),
            "has_players": bool(payload.get("players")),
            "players_count": len(payload.get("players") or []),
        }
    )
    return record


def main() -> int:
    args = parse_args()
    match_ids = load_match_ids(args)
    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    for index, match_id in enumerate(match_ids):
        payload, meta = fetch_json(OPENDOTA_MATCH_URL.format(match_id=match_id), timeout_sec=args.timeout_sec)
        record = project_record(match_id, payload, meta)
        if record.get("replay_url") and index < args.download_probe_limit:
            record["download_probe"] = probe_replay_url(
                str(record["replay_url"]),
                timeout_sec=args.timeout_sec,
                probe_bytes=args.download_probe_bytes,
            )
        records.append(record)
        if index + 1 < len(match_ids):
            time.sleep(max(args.sleep_sec, 0.0))

    output_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "matches_requested": len(match_ids),
        "matches_ok": sum(1 for row in records if row.get("status") == "ok"),
        "matches_with_replay_url": sum(1 for row in records if row.get("replay_url")),
        "matches_with_replay_salt": sum(1 for row in records if row.get("replay_salt") is not None),
        "output_json": str(output_path),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
