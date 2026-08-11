from __future__ import annotations

import argparse
import bz2
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from enrichment.replay_backfill import import_replay_metric_csvs, summarize_replay_metric_import


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run source2-demo replay team metric extraction in batch.")
    parser.add_argument("--manifest-json", required=True)
    parser.add_argument("--replay-dir", required=True)
    parser.add_argument("--binary-path", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--sqlite-path", required=True)
    parser.add_argument("--python-exe", default=sys.executable)
    parser.add_argument("--match-limit", type=int, default=0)
    parser.add_argument("--end-tick", type=int, default=0)
    parser.add_argument("--skip-existing-log", action="store_true")
    parser.add_argument("--skip-existing-import", action="store_true")
    return parser.parse_args()


def _load_manifest(path: Path) -> list[dict]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [row for row in rows if row.get("status") == "ok" and row.get("replay_url")]


def _ensure_dem_file(replay_dir: Path, match_id: int) -> tuple[Path, bool]:
    dem_path = replay_dir / f"{match_id}.dem"
    if dem_path.exists():
        if dem_path.stat().st_size == 0:
            dem_path.unlink()
        else:
            return dem_path, False

    bz2_path = replay_dir / f"{match_id}.dem.bz2"
    if not bz2_path.exists():
        raise FileNotFoundError(f"Replay archive missing for match {match_id}: {bz2_path}")

    temp_dir = Path(tempfile.gettempdir()) / "fantasy_analytics_dem_cache"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_dem_path = temp_dir / f"{match_id}.dem"
    temp_dem_path.write_bytes(bz2.decompress(bz2_path.read_bytes()))
    return temp_dem_path, True


def _run_binary(binary_path: Path, replay_path: Path, log_path: Path, end_tick: int) -> None:
    command = [str(binary_path), str(replay_path)]
    if end_tick > 0:
        command.append(str(end_tick))
    command.append("--team-metrics-only")

    completed = subprocess.run(command, check=True, capture_output=True)
    log_path.write_text(completed.stdout.decode("utf-8", errors="replace"), encoding="utf-8")


def _run_parser(python_exe: str, input_log: Path) -> dict:
    parser_script = PROJECT_ROOT / "scripts" / "parse_replay_team_metric_log.py"
    completed = subprocess.run(
        [python_exe, str(parser_script), "--input", str(input_log)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


def main() -> int:
    args = parse_args()
    manifest_rows = _load_manifest(Path(args.manifest_json))
    if args.match_limit > 0:
        manifest_rows = manifest_rows[: args.match_limit]

    replay_dir = Path(args.replay_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    binary_path = Path(args.binary_path)
    sqlite_path = Path(args.sqlite_path)

    con = sqlite3.connect(sqlite_path)
    batch_results: list[dict] = []

    for row in manifest_rows:
        match_id = int(row["match_id"])
        log_path = output_dir / f"source2_probe_{match_id}.txt"
        summary_json_path = output_dir / f"source2_probe_{match_id}.team_metric_summary.json"
        final_long_csv_path = output_dir / f"source2_probe_{match_id}.team_metric_final_long.csv"
        events_csv_path = output_dir / f"source2_probe_{match_id}.team_metric_events.csv"
        final_long_existed_before = final_long_csv_path.exists()

        temp_dem_created = False
        try:
            dem_path, temp_dem_created = _ensure_dem_file(replay_dir, match_id)
        except FileNotFoundError as exc:
            batch_results.append(
                {
                    "match_id": match_id,
                    "status": "missing_replay",
                    "error": str(exc),
                }
            )
            continue

        try:
            if not (args.skip_existing_log and log_path.exists()):
                _run_binary(binary_path, dem_path, log_path, args.end_tick)

            parser_result = _run_parser(args.python_exe, log_path)

            imported = None
            if not (args.skip_existing_import and final_long_existed_before):
                imported = import_replay_metric_csvs(
                    con,
                    events_csv_path=events_csv_path,
                    final_long_csv_path=final_long_csv_path,
                    source_name="source2_demo",
                    replace_match=True,
                )

            batch_results.append(
                {
                    "match_id": match_id,
                    "status": "ok",
                    "dem_path": str(dem_path),
                    "log_path": str(log_path),
                    "summary_json": str(summary_json_path),
                    "events_csv": str(events_csv_path),
                    "final_long_csv": str(final_long_csv_path),
                    "parser_summary": parser_result["summary"],
                    "import_result": imported,
                }
            )
        except Exception as exc:  # noqa: BLE001
            batch_results.append(
                {
                    "match_id": match_id,
                    "status": "error",
                    "dem_path": str(dem_path),
                    "error": str(exc),
                }
            )
        finally:
            if temp_dem_created and dem_path.exists():
                dem_path.unlink()

    con.commit()
    sqlite_summary = summarize_replay_metric_import(con, source_name="source2_demo")
    con.close()

    print(
        json.dumps(
            {
                "processed_matches": len(batch_results),
                "sqlite_path": str(sqlite_path),
                "matches": batch_results,
                "sqlite_summary": [
                    {
                        "stat_name": row[0],
                        "row_count": row[1],
                        "nonzero_rows": row[2],
                        "min_raw_value": row[3],
                        "max_raw_value": row[4],
                    }
                    for row in sqlite_summary
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
