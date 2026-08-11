from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download replay .dem.bz2 files from an OpenDota replay manifest.")
    parser.add_argument("--manifest-json", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--sleep-sec", type=float, default=0.25)
    parser.add_argument("--timeout-sec", type=int, default=120)
    parser.add_argument("--match-limit", type=int, default=0)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [row for row in rows if row.get("status") == "ok" and row.get("replay_url")]


def _download_file(url: str, destination: Path, *, timeout_sec: int) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "fantasy-analytics-replay-downloader/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            destination.write_bytes(response.read())
            return {
                "status": "ok",
                "http_status": getattr(response, "status", 200),
                "bytes_written": destination.stat().st_size,
            }
    except urllib.error.HTTPError as exc:
        return {"status": "error", "http_status": exc.code, "error": f"HTTP {exc.code}: {exc.reason}"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "http_status": None, "error": str(exc)}


def main() -> int:
    args = parse_args()
    manifest_rows = _load_manifest(Path(args.manifest_json))
    if args.match_limit > 0:
        manifest_rows = manifest_rows[: args.match_limit]

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for index, row in enumerate(manifest_rows):
        match_id = int(row["match_id"])
        destination = output_dir / f"{match_id}.dem.bz2"
        if destination.exists() and not args.overwrite:
            results.append(
                {
                    "match_id": match_id,
                    "status": "skipped_existing",
                    "path": str(destination),
                    "bytes_written": destination.stat().st_size,
                }
            )
        else:
            result = _download_file(str(row["replay_url"]), destination, timeout_sec=args.timeout_sec)
            result["match_id"] = match_id
            result["path"] = str(destination)
            results.append(result)
        if index + 1 < len(manifest_rows):
            time.sleep(max(args.sleep_sec, 0.0))

    summary = {
        "requested": len(manifest_rows),
        "downloaded": sum(1 for row in results if row["status"] == "ok"),
        "skipped_existing": sum(1 for row in results if row["status"] == "skipped_existing"),
        "errors": [row for row in results if row["status"] == "error"],
        "output_dir": str(output_dir),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
