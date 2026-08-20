# Dota 2 Fantasy Analytics

Проект объединяет два связанных направления:

1. Анализ фэнтези-статистики EWC 2026 и TI 2026 в локальных SQLite-базах.
2. Симулятор и обучаемый советник по заменам эмблем Dota Fantasy.

Большие базы данных, реплеи, модели и generated reports не предназначены для
GitHub. Они создаются и хранятся локально в `data/`, `models/` и `reports/`.

## Актуальные точки входа

| Задача | Точка входа |
|---|---|
| Собрать/обновить базу турнира | `notebooks/01_collect_to_sqlite.ipynb` |
| Исследовать базу и задавать фактологические вопросы | `notebooks/02_fact_agent.ipynb` |
| Запустить Colab-совместимый agent | `notebooks/ewc2026_fact_agent_colab.ipynb` |
| Посмотреть dashboard | `streamlit run dashboard/app.py` |
| Запустить UI «человек против модели» | `run_rng_human_vs_model_ui.cmd` |
| Установить OCR-зависимости для UI | `run_rng_ui_ocr_setup.cmd` |

## Локальные артефакты

Канонические пути:

```text
data/ewc_2026_fantasy_compact.sqlite
data/ti_2026_fantasy_compact.sqlite
models/rng_neural_slot_selfplay_selected_v1.pt
```

EWC является историческим, более полным аналитическим набором. TI 2026
обновляется по мере появления карт и используется для live-проверок, но не
является источником обучения текущего RNG planner-а.

## Установка

Требуется Python 3.10+.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Для распознавания скриншотов в RNG UI дополнительно:

```powershell
run_rng_ui_ocr_setup.cmd
```

## Документация

- [Навигация по документации](docs/README.md)
- [Данные и SQLite](docs/DATA_AND_DATABASE.md)
- [Аналитика и fact-agent](docs/ANALYTICS_AND_AGENT.md)
- [Исследовательская архитектура](docs/RESEARCH_ARCHITECTURE.md)
- [RNG actor-critic и planner](docs/RNG_ACTOR_CRITIC.md)
- [Воспроизводимость и проверки](docs/REPRODUCIBILITY.md)

## Принципы проекта

- Числовые ответы агента должны опираться на SQLite или явно указанный источник.
- Нулевое значение не равно отсутствию покрытия: проверяйте provenance и coverage.
- Новая модель не заменяет текущую по умолчанию. Продвижение возможно только
  после независимой matched evaluation на одинаковых стартовых состояниях и
  расписаниях жетонов.
