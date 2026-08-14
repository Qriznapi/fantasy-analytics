from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fantasy_model_evaluator import build_unified_evaluation  # noqa: E402


def main() -> None:
    result = build_unified_evaluation()
    print(f"runs_written={result['runs_written']}")
    print(f"metrics_written={result['metrics_written']}")
    print(result["summary"].head(20).to_string(index=False))


if __name__ == "__main__":
    main()
