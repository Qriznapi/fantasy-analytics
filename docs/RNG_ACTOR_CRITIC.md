# RNG actor-critic и planner

Подробная исследовательская архитектура, тензорные представления, objective и
валидация: [RESEARCH_ARCHITECTURE.md](RESEARCH_ARCHITECTURE.md). Этот документ
сохраняет практический контракт симулятора и UI.

## Цель

Система выбирает применение жетонов замены, чтобы максимизировать ожидаемую
ценность итогового баннера после 30 операций. Значение баннера вычисляется
точным локальным симулятором и фэнтези-профилем, а не произвольной наградой.

Текущая рабочая система: **actor + bounded critic + Monte Carlo planner**.
Ни actor, ни critic не заменяют planner без независимой оценки.

## Точные правила среды

1. На ходе появляются три разных жетона.
2. Пользователь или модель выбирает жетон и одну роль: `core`, `mid` или
   `support`; также доступен `refresh`.
3. После выбора формируется полностью новый набор из трёх жетонов.
4. В пределах роли не может быть двух одинаковых показателей.
5. Reroll показателя не возвращает текущий показатель и не создаёт дубликат.
6. Reroll качества не возвращает текущий tier и соблюдает границы I–V.
7. `quality_shift_plus1` повышает один случайный допустимый tier.
8. `quality_shift_plus2_minus1` повышает два разных допустимых tier и понижает
   третий, отличный от них, при соблюдении границ.

`refresh` также расходует ход и создаёт новый набор из трёх жетонов. Жетон
сначала выбирается как token ID, а затем применяется к выбранной роли: роль не
является случайной частью выпавшего жетона.

Свойства эмблем реализуются в simulator: `Unique` активен только при отсутствии
других Unique в данной роли; `Vampiric` усиливает себя и ослабляет соседние;
`Benevolent`, `Fractal` и `Friendly` применяются по условиям баннера.

## Компоненты

| Компонент | Файл | Роль |
|---|---|---|
| Exact environment | `src/fantasy_rng_env.py` | Состояние баннеров, жетоны и легальные переходы. |
| Strategy prior | `src/fantasy_rng_strategy_prior.py` | Прозрачный tie-break: tier, руны mid, teamfight, farm, Friendly и слабые traits. |
| Slot-aware model | `src/fantasy_rng_slot_neural.py` | Transformer по 15 слотам, actor, Q и V heads. |
| Planner | `src/fantasy_rng_slot_planner.py` | Top-k actor кандидаты, rollout и риск-агрегация. |
| Offline actor-critic train | `src/fantasy_rng_offline_policy.py` | KL-консервативная дистилляция planner-а и terminal Q. |

Actor предлагает кандидаты, planner проверяет их в симуляции. Terminal critic
предсказывает итоговую ценность только для распределения состояний planner-а и
используется как ограниченный bootstrap хвоста rollout. Его вклад включается
параметром `critic_leaf_weight`; дефолт `0.0` сохраняет чистый planner.

## Данные обучения

Teacher corpus состоит из полных 30-шаговых planner-траекторий в SQLite-таблицах
`fantasy_rng_offline_trajectory_*`. Каждая строка содержит состояние, набор
офферов, выбранное действие, logits/probabilities actor-а, кандидаты planner-а
и фактическую итоговую ценность баннера.

Это синтетические, но rule-faithful данные: стартовые баннеры и жетоны
семплируются по сохранённым эмпирическим пресетам. Они не являются реальными
матчами TI и не используются для оценки игроков.

### Состав decision dataset

| Группа | Содержимое |
|---|---|
| State | 15 slot records, banner value, rolls left, progress, objective mode |
| Candidate | token, target role, scope, colour, slot и current multiplier |
| Local estimates | `expected_delta`, `p75_delta`, `p90_delta` |
| Teacher outcome | planner choice, behavior probabilities, return-to-go, final utility |

Среда генерирует новый набор офферов на каждом следующем ходу; невыбранные
жетоны не переносятся в будущий шаг.

## Отклонённые эксперименты

Stage 2 conservative actor-critic прошёл teacher corpus, обучение и matched
evaluation, но **не был продвинут**. На independent safe-router test он показал
регрессию `-2,922` очка, 95% CI `[-4,928; -1,288]`. Поэтому текущая
практическая система остаётся
`models/rng_neural_slot_selfplay_selected_v1.pt + planner`.

Его CMD, checkpoint и generated reports удалены из чистого проекта: они не
должны случайно использоваться как production baseline. Архитектурный вывод
сохранён, поскольку он важнее конкретного исторического артефакта: Q видел
итог только выбранного behavior action и не мог надёжно ранжировать
альтернативы.

## Консервативный fine-tune

Новые fine-tune эксперименты должны стартовать отдельно от active baseline,
с низким learning rate, KL-якорем к исходному actor и слабой
behaviour-cloning регуляризацией. Checkpoint выбирается на fresh selection
seeds и проверяется как полный `actor + planner` на новых matched seeds.

Результат не продвигается автоматически: положительный средний margin без
неотрицательной нижней границы CI недостаточен для замены baseline.

<!-- Historical evidence retained above; generated artifacts are intentionally ignored. -->

## Практический UI

Запуск: `run_rng_human_vs_model_ui.cmd`.

UI поддерживает ручное заполнение баннеров, число оставшихся жетонов, офферы,
OCR скриншота и сравнение с моделью. OCR читает 15 эмблем и три нижние кнопки жетонов в
двух распространённых client layouts и автоматически переносит три token ID в
редактируемое поле. Роль применяется автоматически только при coverage `5/5`:
частично прочитанный баннер нельзя безопасно дополнить неизвестными слотами.
При неуверенности в scope он выводит пометку для проверки. UI -- помощник;
перед применением действия в клиенте проверяйте распознанные поля и роль.
