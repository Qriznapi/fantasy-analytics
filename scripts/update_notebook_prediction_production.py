from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = [
    PROJECT_ROOT / "notebooks" / "02_fact_agent.ipynb",
    PROJECT_ROOT / "notebooks" / "ewc2026_fact_agent_demo.ipynb",
]

MARKER = "production_prediction_surface_demo_v1"

CODE_SOURCE = [
    f"# {MARKER}\n",
    "display(ask_foundation('production prediction for position 1 players from ti 2026 teams', max_rows=10).dataframes['prediction_production_players'])\n",
    "display(ask_foundation('production prediction for core_pair role slot from ti 2026 teams', max_rows=10).dataframes['prediction_production_role_slots'])\n",
    "display(ask_foundation('prediction production comparison', max_rows=20).dataframes['prediction_production_model_choices'])\n",
]


def update_notebook(path: Path) -> bool:
    data = json.loads(path.read_text(encoding="utf-8"))
    for cell in data.get("cells", []):
        src = "".join(cell.get("source", []))
        if MARKER in src:
            return False
    new_cell = {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": CODE_SOURCE,
    }
    data.setdefault("cells", []).append(new_cell)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return True


def main() -> None:
    for path in NOTEBOOKS:
        changed = update_notebook(path)
        print(f"{path.name}: {'updated' if changed else 'unchanged'}")


if __name__ == "__main__":
    main()
