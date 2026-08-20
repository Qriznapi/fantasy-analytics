# Воспроизводимость и проверки

## Среда

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m compileall src scripts
```

Для OCR установите `pytesseract` и системный Tesseract через
`run_rng_ui_ocr_setup.cmd`. Если Tesseract расположен не в стандартном пути,
задайте переменную `TESSERACT_CMD` с путём к `tesseract.exe`.

## Минимальные проверки

После изменений в сборе данных:

```powershell
.\.venv\Scripts\python.exe scripts\validate_project.py
.\.venv\Scripts\python.exe scripts\report_backfill_coverage.py
```

После изменений RNG-кода:

```powershell
.\.venv\Scripts\python.exe -m compileall src scripts
```

Перед запуском длительного обучения убедитесь, что существуют:

- `data/ti_2026_fantasy_compact.sqlite`;
- `models/rng_neural_slot_selfplay_selected_v1.pt`;
- token preset и initial-state preset из CMD-файла.

## Порядок экспериментирования

1. Создавайте новые `dataset_id`, artifact и report names для каждого большого
   прогона.
2. Не перезаписывайте baseline checkpoint.
3. Разделяйте train corpus и final matched evaluation seeds.
4. Сравнивайте варианты на общих стартовых состояниях и одинаковом расписании
   трёх жетонов, включая возможность refresh.
5. Сохраняйте отчёт, конфигурацию и parent artifact рядом с результатом.

Никогда не продвигайте модель только по training loss, single run или UI-игре.
Решение принимается по независимой paired evaluation и поведению в safe,
balanced и ceiling режимах.
