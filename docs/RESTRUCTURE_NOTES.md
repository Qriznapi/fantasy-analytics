# Restructure notes

This repository was prepared from the uploaded `Project F` archive as a portfolio-oriented standalone project.

## Changes made

- moved the SQLite database to `data/`;
- moved analytical modules to `src/`;
- moved the Streamlit UI to `dashboard/app.py`;
- renamed/moved the demo notebook to `notebooks/ewc2026_fact_agent_demo.ipynb`;
- moved validation and regression checks to `scripts/` and `tests/`;
- replaced machine-specific default paths with repository-relative paths;
- updated the notebook paths accordingly;
- updated the test/validation file manifest to match the files actually present in the uploaded archive;
- added README, requirements, `.gitignore`, optional LLM environment template, and project documentation.

## What was intentionally not changed

- the bundled SQLite database contents;
- fantasy scoring formulas;
- profile-construction logic;
- reliability/optimizer formulas and stored outputs;
- deterministic query-routing behavior;
- analytical conclusions in the source project.

The SQLite file is byte-for-byte identical to the database in the uploaded archive (SHA-256: `78b70b08096956416774f5bc11b87b2adaf7268bec2850265adc8175d93fb8ad`).

## Validation performed

The cleaned repository was checked with:

```bash
python -m compileall -q src dashboard tests scripts
python tests/regression_tests.py
python scripts/validate_project.py
```

Both the regression suite and the full validation completed successfully in the preparation environment.
