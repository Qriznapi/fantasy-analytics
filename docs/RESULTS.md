# Results and Evaluation Protocol

## Current public result status

Historical generated reports and experimental checkpoints are intentionally not
committed. Consequently, this repository does **not** publish an unverifiable
number for candidate improvement, win rate, or confidence interval.

The operational system is the validated baseline actor plus exact Monte Carlo
planner. A previous conservative actor-critic candidate was rejected after a
negative independent safe-scenario result; see `RNG_ACTOR_CRITIC.md`.

## Portfolio metrics contract

Every promoted candidate must report the following values on fresh matched
seeds. Baseline and candidate receive the same initial banners, three-token
offers, stochastic transitions, and objective mode.

| Metric | Meaning | Promotion interpretation |
|---|---|---|
| Evaluation episodes | Number of paired trajectories | report sample size |
| Mean paired delta | candidate final utility minus baseline | positive is desirable |
| Median paired delta | robust central improvement | guards against rare outliers |
| Win rate | fraction of episodes won by candidate | descriptive, not sufficient alone |
| Bootstrap 95% CI | uncertainty of mean paired delta | lower bound should be non-negative |
| Safe-mode delta | downside-sensitive paired delta | must not materially regress |

## Generate a fresh result

With local TI database, baseline checkpoint, and a new candidate checkpoint:

```powershell
.\.venv\Scripts\python.exe scripts\run_portfolio_evaluation.py `
  --candidate models\candidate.pt `
  --episodes 100
```

The command writes ignored JSON into `reports/portfolio_evaluation.json` and
prints a Markdown-ready results block. Copy the resulting values into the
`Key Results` table in the root README only after the run is retained with its
seed, presets, and candidate parent artifact.
