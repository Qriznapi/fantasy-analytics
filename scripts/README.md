# Scripts

Каталог содержит только поддерживаемые CLI-скрипты. Исторические `smoke`,
`v5-v8`, одноразовые scorecard и отклонённые actor-critic pipelines удалены:
их результаты зафиксированы в документации, а не должны случайно запускаться.

## Поддерживаемые группы

| Группа | Скрипты |
|---|---|
| Турнирные данные | `build_*database.py`, `sync_ti2026_matches.py`, `backfill_*.py`, `rebuild_backfilled_fantasy_points.py` |
| Replay и coverage | `*replay*.py`, `report_backfill_coverage.py`, `validate_*database.py` |
| RNG data/model | `generate_rng_offline_trajectories.py`, `train_rng_slot_bootstrap.py`, `train_rng_slot_ppo.py`, `evaluate_rng_planner_actors.py` |
| Проверки и notebooks | `validate_project.py`, `check_text_integrity.py`, `sync_notebooks.py` |

Запускайте скрипты только после подготовки локальных SQLite-файлов. Для
практического советника используйте `run_rng_human_vs_model_ui.cmd` в корне.
