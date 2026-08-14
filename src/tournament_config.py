from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from project_db import PROJECT_ROOT, canonical_db_path


CONFIGS_DIR = PROJECT_ROOT / "configs" / "tournaments"


@dataclass(frozen=True)
class TournamentConfig:
    event_id: str
    display_name: str
    db_filename: str
    cache_dirname: str
    replay_manifest_filename: str
    replay_sidecar_filename: str
    opendota_league_id: int | None = None
    schema_template_event_id: str | None = None
    dotabuff_league_ids: list[int] = field(default_factory=list)
    liquipedia_urls: list[str] = field(default_factory=list)
    official_urls: list[str] = field(default_factory=list)
    stage_rules: dict[str, Any] = field(default_factory=dict)
    roster_source_priority: list[str] = field(default_factory=list)
    reference_seed_tables: list[str] = field(default_factory=list)
    sync_policy: dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    config_path: Path | None = None

    @property
    def canonical_db_path(self) -> Path:
        return PROJECT_ROOT / "data" / self.db_filename

    @property
    def cache_dir(self) -> Path:
        return PROJECT_ROOT / "data" / self.cache_dirname

    @property
    def replay_manifest_path(self) -> Path:
        return PROJECT_ROOT / "data" / self.replay_manifest_filename

    @property
    def replay_sidecar_path(self) -> Path:
        return PROJECT_ROOT / "data" / self.replay_sidecar_filename


def config_path_for_event(event_id: str, configs_dir: Path = CONFIGS_DIR) -> Path:
    return configs_dir / f"{event_id}.yaml"


def load_tournament_config(event_id: str, configs_dir: Path = CONFIGS_DIR) -> TournamentConfig:
    path = config_path_for_event(event_id, configs_dir=configs_dir)
    if not path.exists():
        raise FileNotFoundError(f"Tournament config not found: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    required = [
        "event_id",
        "display_name",
        "db_filename",
        "cache_dirname",
        "replay_manifest_filename",
        "replay_sidecar_filename",
    ]
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"Config {path} is missing required keys: {missing}")
    if payload["event_id"] != event_id:
        raise ValueError(f"Config {path} has mismatched event_id={payload['event_id']!r}")

    return TournamentConfig(
        event_id=payload["event_id"],
        display_name=payload["display_name"],
        db_filename=payload["db_filename"],
        cache_dirname=payload["cache_dirname"],
        replay_manifest_filename=payload["replay_manifest_filename"],
        replay_sidecar_filename=payload["replay_sidecar_filename"],
        opendota_league_id=int(payload["opendota_league_id"]) if payload.get("opendota_league_id") is not None else None,
        schema_template_event_id=payload.get("schema_template_event_id"),
        dotabuff_league_ids=[int(value) for value in payload.get("dotabuff_league_ids", [])],
        liquipedia_urls=[str(value) for value in payload.get("liquipedia_urls", [])],
        official_urls=[str(value) for value in payload.get("official_urls", [])],
        stage_rules=dict(payload.get("stage_rules", {})),
        roster_source_priority=[str(value) for value in payload.get("roster_source_priority", [])],
        reference_seed_tables=[str(value) for value in payload.get("reference_seed_tables", [])],
        sync_policy=dict(payload.get("sync_policy", {})),
        notes=str(payload.get("notes", "")),
        config_path=path,
    )


def known_event_ids(configs_dir: Path = CONFIGS_DIR) -> list[str]:
    if not configs_dir.exists():
        return []
    return sorted(path.stem for path in configs_dir.glob("*.yaml"))


def resolve_event_db_path(event_id: str, explicit: str | Path | None = None) -> Path:
    if explicit is not None:
        return Path(explicit)
    config = load_tournament_config(event_id)
    expected = canonical_db_path(PROJECT_ROOT, event_id=event_id)
    if expected.name != config.db_filename:
        return config.canonical_db_path
    return expected
