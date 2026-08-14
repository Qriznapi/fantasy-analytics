from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVENT_ID = "ewc2026"
EVENT_DB_FILENAMES = {
    "ewc2026": "ewc_2026_fantasy_compact.sqlite",
    "ti2026": "ti_2026_fantasy_compact.sqlite",
}


def canonical_db_rel(event_id: str = DEFAULT_EVENT_ID) -> Path:
    filename = EVENT_DB_FILENAMES.get(event_id)
    if not filename:
        raise KeyError(f"Unknown event_id={event_id!r}")
    return Path("data") / filename


def legacy_db_rel(event_id: str = DEFAULT_EVENT_ID) -> Path:
    return Path("data") / "db" / canonical_db_rel(event_id).name


def canonical_db_path(project_root: Path = PROJECT_ROOT, event_id: str = DEFAULT_EVENT_ID) -> Path:
    return project_root / canonical_db_rel(event_id)


def legacy_db_path(project_root: Path = PROJECT_ROOT, event_id: str = DEFAULT_EVENT_ID) -> Path:
    return project_root / legacy_db_rel(event_id)


def resolve_db_path(
    project_root: Path = PROJECT_ROOT,
    explicit: str | Path | None = None,
    *,
    event_id: str = DEFAULT_EVENT_ID,
) -> Path:
    if explicit is not None:
        return Path(explicit)
    canonical = canonical_db_path(project_root, event_id=event_id)
    legacy = legacy_db_path(project_root, event_id=event_id)
    if canonical.exists():
        return canonical
    if legacy.exists():
        return legacy
    return canonical


def shadow_db_status(
    project_root: Path = PROJECT_ROOT,
    *,
    event_id: str = DEFAULT_EVENT_ID,
) -> dict[str, object]:
    canonical = canonical_db_path(project_root, event_id=event_id)
    legacy = legacy_db_path(project_root, event_id=event_id)
    return {
        "event_id": event_id,
        "canonical_path": canonical,
        "legacy_path": legacy,
        "canonical_exists": canonical.exists(),
        "legacy_exists": legacy.exists(),
        "resolved_path": resolve_db_path(project_root, event_id=event_id),
        "shadow_copy_present": canonical.exists() and legacy.exists(),
    }
