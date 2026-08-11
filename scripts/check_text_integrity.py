from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_DIR = PROJECT_ROOT / "notebooks"
SRC_DIR = PROJECT_ROOT / "src"
DOCS_DIR = PROJECT_ROOT / "docs"

SUSPICIOUS_TOKENS = [
    "????",
    "вЂ",
]


def _iter_notebook_strings(path: Path):
    nb = json.loads(path.read_text(encoding="utf-8"))
    for cell_idx, cell in enumerate(nb.get("cells", [])):
        yield f"cell[{cell_idx}].source", "".join(cell.get("source", []))
        for out_idx, output in enumerate(cell.get("outputs", [])):
            if "text" in output:
                text = output["text"]
                yield f"cell[{cell_idx}].outputs[{out_idx}].text", "".join(text) if isinstance(text, list) else str(text)
            if "data" in output:
                for key, value in output["data"].items():
                    if key.startswith("text/"):
                        yield (
                            f"cell[{cell_idx}].outputs[{out_idx}].data[{key}]",
                            "".join(value) if isinstance(value, list) else str(value),
                        )


def _iter_text_files():
    for path in NOTEBOOK_DIR.glob("*.ipynb"):
        yield path, "notebook"
    for path in SRC_DIR.rglob("*.py"):
        yield path, "text"
    for path in DOCS_DIR.glob("*.md"):
        yield path, "text"


def _check_text_block(text: str) -> list[str]:
    issues: list[str] = []
    for token in SUSPICIOUS_TOKENS:
        if token in text:
            issues.append(f"contains suspicious token {token!r}")
    return issues


def main() -> None:
    failures: list[str] = []

    for path, kind in _iter_text_files():
        if kind == "notebook":
            try:
                for location, text in _iter_notebook_strings(path):
                    for issue in _check_text_block(text):
                        failures.append(f"{path}: {location}: {issue}")
            except Exception as exc:
                failures.append(f"{path}: failed to parse notebook as UTF-8 JSON: {exc}")
        else:
            try:
                text = path.read_text(encoding="utf-8")
            except Exception as exc:
                failures.append(f"{path}: failed to read as UTF-8 text: {exc}")
                continue
            for issue in _check_text_block(text):
                failures.append(f"{path}: {issue}")

    if failures:
        print("[text-integrity] failures detected:")
        for item in failures:
            print("-", item)
        raise SystemExit(1)

    print("[text-integrity] ok")


if __name__ == "__main__":
    main()
