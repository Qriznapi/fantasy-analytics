from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from tournament_config import load_tournament_config, resolve_event_db_path  # noqa: E402


DDL_ORDER = ("table", "index", "view", "trigger")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap an event database from the shared Project F schema.")
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--db-path", default="")
    parser.add_argument("--template-db-path", default="")
    parser.add_argument("--replace-existing", action="store_true")
    parser.add_argument("--skip-reference-seed", action="store_true")
    return parser.parse_args()


def fetch_schema_objects(con: sqlite3.Connection) -> list[tuple[str, str, str]]:
    rows = con.execute(
        """
        SELECT type, name, sql
        FROM sqlite_master
        WHERE sql IS NOT NULL
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    typed: dict[str, list[tuple[str, str, str]]] = {kind: [] for kind in DDL_ORDER}
    for row_type, row_name, row_sql in rows:
        if row_type in typed:
            typed[row_type].append((row_type, row_name, row_sql))
    ordered: list[tuple[str, str, str]] = []
    for kind in DDL_ORDER:
        ordered.extend(typed[kind])
    return ordered


def clone_schema(source_db: Path, target_db: Path) -> int:
    source = sqlite3.connect(str(source_db))
    target = sqlite3.connect(str(target_db))
    try:
        count = 0
        for _, _, sql in fetch_schema_objects(source):
            target.execute(sql)
            count += 1
        target.commit()
        return count
    finally:
        source.close()
        target.close()


def table_columns(con: sqlite3.Connection, table_name: str) -> list[str]:
    return [str(row[1]) for row in con.execute(f"PRAGMA table_info({table_name})").fetchall()]


def copy_reference_tables(source_db: Path, target_db: Path, table_names: list[str]) -> dict[str, int]:
    source = sqlite3.connect(str(source_db))
    target = sqlite3.connect(str(target_db))
    copied: dict[str, int] = {}
    try:
        for table_name in table_names:
            exists = source.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            ).fetchone()
            if not exists:
                continue
            source_cols = table_columns(source, table_name)
            target_cols = table_columns(target, table_name)
            shared_cols = [col for col in source_cols if col in target_cols]
            if not shared_cols:
                continue
            quoted_cols = ", ".join(shared_cols)
            rows = source.execute(f"SELECT {quoted_cols} FROM {table_name}").fetchall()
            target.execute(f"DELETE FROM {table_name}")
            if rows:
                placeholders = ", ".join("?" for _ in shared_cols)
                target.executemany(
                    f"INSERT INTO {table_name}({quoted_cols}) VALUES ({placeholders})",
                    rows,
                )
            copied[table_name] = len(rows)
        target.commit()
        return copied
    finally:
        source.close()
        target.close()


def ensure_bootstrap_tables(target_db: Path, event_id: str, display_name: str, config_path: Path | None) -> None:
    con = sqlite3.connect(str(target_db))
    try:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS event_registry (
                event_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                config_path TEXT,
                created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS event_build_runs (
                run_id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                action_name TEXT NOT NULL,
                status TEXT NOT NULL,
                template_event_id TEXT,
                template_db_path TEXT,
                target_db_path TEXT NOT NULL,
                notes TEXT,
                created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS event_sync_runs (
                run_id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                source_name TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at_utc TEXT NOT NULL,
                finished_at_utc TEXT,
                new_match_count INTEGER NOT NULL DEFAULT 0,
                updated_match_count INTEGER NOT NULL DEFAULT 0,
                failed_match_count INTEGER NOT NULL DEFAULT 0,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS event_sync_match_log (
                run_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                match_id INTEGER NOT NULL,
                action_name TEXT NOT NULL,
                status TEXT NOT NULL,
                source_name TEXT NOT NULL,
                notes TEXT,
                PRIMARY KEY (run_id, match_id, source_name)
            );
            """
        )
        con.execute(
            """
            INSERT INTO event_registry(event_id, display_name, config_path)
            VALUES (?, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
                display_name=excluded.display_name,
                config_path=excluded.config_path,
                updated_at_utc=CURRENT_TIMESTAMP
            """,
            (event_id, display_name, str(config_path) if config_path else None),
        )
        con.commit()
    finally:
        con.close()


def record_build_run(
    target_db: Path,
    *,
    event_id: str,
    action_name: str,
    status: str,
    template_event_id: str | None,
    template_db_path: Path | None,
    notes: str,
) -> str:
    run_id = f"build::{event_id}::{uuid4().hex[:12]}"
    con = sqlite3.connect(str(target_db))
    try:
        con.execute(
            """
            INSERT INTO event_build_runs(
                run_id, event_id, action_name, status,
                template_event_id, template_db_path, target_db_path, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                event_id,
                action_name,
                status,
                template_event_id,
                str(template_db_path) if template_db_path else None,
                str(target_db),
                notes,
            ),
        )
        con.commit()
        return run_id
    finally:
        con.close()


def bootstrap_event_database(
    event_id: str,
    *,
    db_path: Path | None = None,
    template_db_path: Path | None = None,
    replace_existing: bool = False,
    skip_reference_seed: bool = False,
) -> dict[str, object]:
    config = load_tournament_config(event_id)
    target_db = db_path or resolve_event_db_path(event_id)
    template_event_id = config.schema_template_event_id
    template_db = template_db_path
    if template_db is None and template_event_id:
        template_db = resolve_event_db_path(template_event_id)

    if target_db.exists():
        if not replace_existing:
            return {
                "event_id": event_id,
                "target_db": str(target_db),
                "status": "exists",
                "message": "Target database already exists; pass --replace-existing to rebuild it.",
            }
        target_db.unlink()

    if template_db is None or not template_db.exists():
        raise FileNotFoundError(
            f"Template database is required to bootstrap {event_id!r} and was not found: {template_db}"
        )

    target_db.parent.mkdir(parents=True, exist_ok=True)
    config.cache_dir.mkdir(parents=True, exist_ok=True)

    cloned_objects = clone_schema(template_db, target_db)
    ensure_bootstrap_tables(target_db, config.event_id, config.display_name, config.config_path)
    copied_reference_rows = {} if skip_reference_seed else copy_reference_tables(
        template_db,
        target_db,
        config.reference_seed_tables,
    )
    notes = (
        f"Bootstrapped {event_id} from template {template_event_id or 'explicit'}; "
        f"cloned {cloned_objects} schema objects."
    )
    run_id = record_build_run(
        target_db,
        event_id=event_id,
        action_name="bootstrap_from_template",
        status="ok",
        template_event_id=template_event_id,
        template_db_path=template_db,
        notes=notes,
    )
    return {
        "event_id": event_id,
        "display_name": config.display_name,
        "target_db": str(target_db),
        "template_db": str(template_db),
        "template_event_id": template_event_id,
        "cloned_schema_objects": cloned_objects,
        "copied_reference_rows": copied_reference_rows,
        "build_run_id": run_id,
        "status": "ok",
    }


def main() -> None:
    args = parse_args()
    result = bootstrap_event_database(
        args.event_id,
        db_path=Path(args.db_path) if args.db_path else None,
        template_db_path=Path(args.template_db_path) if args.template_db_path else None,
        replace_existing=args.replace_existing,
        skip_reference_seed=args.skip_reference_seed,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
