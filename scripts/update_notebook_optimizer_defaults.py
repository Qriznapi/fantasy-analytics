from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = [
    PROJECT_ROOT / "notebooks" / "02_fact_agent.ipynb",
    PROJECT_ROOT / "notebooks" / "ewc2026_fact_agent_demo.ipynb",
]

REPLACEMENTS = [
    (
        "    banner_optimizer_players_foundation,\n",
        "    banner_optimizer_players,\n    banner_optimizer_players_foundation,\n",
    ),
    (
        "    banner_optimizer_role_slots_foundation,\n",
        "    banner_optimizer_role_slots,\n    banner_optimizer_role_slots_foundation,\n",
    ),
    (
        "display(banner_optimizer_players_foundation(position=1, ti2026_only=True, limit=15))\n",
        "display(banner_optimizer_players(position=1, ti2026_only=True, limit=15))\n",
    ),
    (
        "display(banner_optimizer_role_slots_foundation(role_slot=\"core_pair\", ti2026_only=True, limit=10))\n",
        "display(banner_optimizer_role_slots(role_slot=\"core_pair\", ti2026_only=True, limit=10))\n",
    ),
]


def update_notebook(path: Path) -> bool:
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = False
    for cell in data.get("cells", []):
        if "source" not in cell:
            continue
        source = "".join(cell["source"])
        updated = source
        for old, new in REPLACEMENTS:
            updated = updated.replace(old, new)
        if updated != source:
            cell["source"] = updated.splitlines(keepends=True)
            changed = True
    if changed:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return changed


def main() -> None:
    for path in NOTEBOOKS:
        changed = update_notebook(path)
        print(f"{path.name}: {'updated' if changed else 'unchanged'}")


if __name__ == "__main__":
    main()
