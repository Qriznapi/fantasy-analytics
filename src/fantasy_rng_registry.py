from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_registry_schema(con: sqlite3.Connection) -> None:
    con.executescript("""
        CREATE TABLE IF NOT EXISTS fantasy_rng_policy_registry (
          policy_version TEXT PRIMARY KEY, status TEXT NOT NULL,
          actor_artifact_path TEXT NOT NULL, critic_artifact_path TEXT,
          actor_sha256 TEXT NOT NULL, critic_sha256 TEXT,
          parent_policy_version TEXT, train_run_id TEXT, dataset_id TEXT NOT NULL,
          validation_metrics_json TEXT NOT NULL, promotion_rationale TEXT NOT NULL,
          created_at_utc TEXT NOT NULL, promoted_at_utc TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_rng_registry_one_champion
          ON fantasy_rng_policy_registry(status) WHERE status = 'champion';
        CREATE TABLE IF NOT EXISTS fantasy_rng_inference_log (
          inference_id TEXT PRIMARY KEY, policy_version TEXT NOT NULL, profile_id TEXT NOT NULL,
          seed INTEGER NOT NULL, recommendation_json TEXT NOT NULL, created_at_utc TEXT NOT NULL
        );
    """)
    con.commit()


def register_policy(
    con: sqlite3.Connection,
    *,
    actor_artifact: Path,
    critic_artifact: Path | None,
    artifact_dir: Path,
    dataset_id: str,
    train_run_id: str | None,
    parent_policy_version: str | None,
    validation_metrics: dict[str, Any],
    promotion_rationale: str,
    promote: bool,
) -> dict[str, str]:
    create_registry_schema(con)
    if not actor_artifact.exists():
        raise FileNotFoundError(actor_artifact)
    version = f"rng_policy_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{_digest(actor_artifact)[:8]}"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    actor_copy = artifact_dir / f"{version}_actor.json"
    shutil.copy2(actor_artifact, actor_copy)
    critic_copy: Path | None = None
    if critic_artifact:
        if not critic_artifact.exists():
            raise FileNotFoundError(critic_artifact)
        critic_copy = artifact_dir / f"{version}_critic.json"
        shutil.copy2(critic_artifact, critic_copy)
    if promote:
        con.execute("UPDATE fantasy_rng_policy_registry SET status = 'superseded' WHERE status = 'champion'")
    con.execute(
        "INSERT INTO fantasy_rng_policy_registry VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            version, "champion" if promote else "candidate", str(actor_copy), str(critic_copy) if critic_copy else None,
            _digest(actor_copy), _digest(critic_copy) if critic_copy else None, parent_policy_version, train_run_id,
            dataset_id, json.dumps(validation_metrics, ensure_ascii=False), promotion_rationale, _now(), _now() if promote else None,
        ),
    )
    con.commit()
    return {"policy_version": version, "status": "champion" if promote else "candidate", "actor_artifact_path": str(actor_copy), "critic_artifact_path": str(critic_copy) if critic_copy else ""}


def load_champion(con: sqlite3.Connection) -> dict[str, Any]:
    create_registry_schema(con)
    row = con.execute("SELECT * FROM fantasy_rng_policy_registry WHERE status = 'champion'").fetchone()
    if row is None:
        raise RuntimeError("No RNG champion is registered")
    columns = [item[0] for item in con.execute("SELECT * FROM fantasy_rng_policy_registry LIMIT 0").description]
    return dict(zip(columns, row))


def persist_inference(con: sqlite3.Connection, *, policy_version: str, profile_id: str, seed: int, payload: dict[str, Any]) -> str:
    create_registry_schema(con)
    inference_id = f"rng_inference::{datetime.now(timezone.utc).isoformat(timespec='seconds')}"
    con.execute(
        "INSERT INTO fantasy_rng_inference_log VALUES (?, ?, ?, ?, ?, ?)",
        (inference_id, policy_version, profile_id, int(seed), json.dumps(payload, ensure_ascii=False), _now()),
    )
    con.commit()
    return inference_id
