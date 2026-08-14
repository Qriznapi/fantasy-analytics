from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from export_replay_manifest_from_db import export_manifest_rows  # noqa: E402
from tournament_config import load_tournament_config, resolve_event_db_path  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the replay-derived fantasy stat backfill for an event using cached "
            "OpenDota payloads, source2_demo_spike, and the current compact SQLite DB."
        )
    )
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--db-path", default="")
    parser.add_argument("--binary-path", required=True)
    parser.add_argument("--python-exe", default=sys.executable)
    parser.add_argument("--match-limit", type=int, default=0)
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--skip-parse", action="store_true")
    parser.add_argument("--skip-merge", action="store_true")
    parser.add_argument("--skip-reconcile", action="store_true")
    parser.add_argument("--skip-summary-sync", action="store_true")
    parser.add_argument("--skip-cleanup", action="store_true")
    parser.add_argument("--skip-unified", action="store_true")
    parser.add_argument("--sleep-sec", type=float, default=0.25)
    parser.add_argument("--timeout-sec", type=int, default=120)
    parser.add_argument("--end-tick", type=int, default=0)
    return parser.parse_args()


def _run(command: list[str], *, cwd: Path) -> dict[str, object]:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    stdout = completed.stdout.strip()
    parsed: object
    try:
        parsed = json.loads(stdout) if stdout else {}
    except json.JSONDecodeError:
        parsed = {"raw_stdout": stdout}
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": parsed,
        "stderr": completed.stderr.strip(),
    }


def main() -> int:
    args = parse_args()
    config = load_tournament_config(args.event_id)
    db_path = Path(args.db_path) if args.db_path else resolve_event_db_path(args.event_id)
    db_path = db_path.resolve()

    replay_dir = config.cache_dir / "replays"
    probe_dir = config.cache_dir / "replay_probe"
    replay_dir.mkdir(parents=True, exist_ok=True)
    probe_dir.mkdir(parents=True, exist_ok=True)
    config.cache_dir.mkdir(parents=True, exist_ok=True)

    manifest_rows = export_manifest_rows(
        db_path,
        replay_dir=replay_dir,
        only_missing_local=False,
        match_limit=args.match_limit,
    )
    config.replay_manifest_path.write_text(json.dumps(manifest_rows, ensure_ascii=False, indent=2), encoding="utf-8")

    results: dict[str, object] = {
        "event_id": args.event_id,
        "db_path": str(db_path),
        "manifest_path": str(config.replay_manifest_path),
        "replay_dir": str(replay_dir),
        "probe_dir": str(probe_dir),
        "manifest_rows": len(manifest_rows),
    }

    if not args.skip_download:
        results["download"] = _run(
            [
                args.python_exe,
                str(PROJECT_ROOT / "scripts" / "download_replays_from_manifest.py"),
                "--manifest-json",
                str(config.replay_manifest_path),
                "--output-dir",
                str(replay_dir),
                "--sleep-sec",
                str(args.sleep_sec),
                "--timeout-sec",
                str(args.timeout_sec),
                "--match-limit",
                str(args.match_limit),
            ],
            cwd=PROJECT_ROOT,
        )

    if args.download_only:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    if not args.skip_parse:
        results["parse_and_import"] = _run(
            [
                args.python_exe,
                str(PROJECT_ROOT / "scripts" / "run_replay_team_metric_batch.py"),
                "--manifest-json",
                str(config.replay_manifest_path),
                "--replay-dir",
                str(replay_dir),
                "--binary-path",
                str(Path(args.binary_path).resolve()),
                "--output-dir",
                str(probe_dir),
                "--sqlite-path",
                str(config.replay_sidecar_path),
                "--python-exe",
                args.python_exe,
                "--match-limit",
                str(args.match_limit),
                "--end-tick",
                str(args.end_tick),
            ],
            cwd=PROJECT_ROOT,
        )

    if not args.skip_merge:
        results["merge"] = _run(
            [
                args.python_exe,
                str(PROJECT_ROOT / "scripts" / "merge_replay_metrics_into_compact_db.py"),
                "--target-db",
                str(db_path),
                "--replay-db",
                str(config.replay_sidecar_path),
            ],
            cwd=PROJECT_ROOT,
        )

    if not args.skip_reconcile:
        results["reconcile"] = _run(
            [
                args.python_exe,
                str(PROJECT_ROOT / "scripts" / "reconcile_replay_player_metrics.py"),
                "--db-path",
                str(db_path),
            ],
            cwd=PROJECT_ROOT,
        )

    if not args.skip_summary_sync:
        results["summary_sync"] = _run(
            [
                args.python_exe,
                str(PROJECT_ROOT / "scripts" / "sync_summary_backfill_columns.py"),
                "--db-path",
                str(db_path),
            ],
            cwd=PROJECT_ROOT,
        )

    if not args.skip_cleanup:
        results["cleanup"] = _run(
            [
                args.python_exe,
                str(PROJECT_ROOT / "scripts" / "run_cleanup_consistency_pass.py"),
                "--db-path",
                str(db_path),
            ],
            cwd=PROJECT_ROOT,
        )

    if not args.skip_unified:
        results["unified"] = _run(
            [
                args.python_exe,
                str(PROJECT_ROOT / "scripts" / "build_unified_fantasy_metrics_table.py"),
                "--db-path",
                str(db_path),
            ],
            cwd=PROJECT_ROOT,
        )

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
