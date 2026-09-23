# Роль 1 — AI Router

Ветка: feat/router. Зона: backend/router/**.
План работы из 9 этапов: [PLAN.md](PLAN.md). Платные вызовы автоматически не запускаются.

## Задачи по порядку

1. Прочитать весь каталог, not_this_if, README набора и evaluate.py.
2. Реализовать providers/openai_provider.py: structured output, модель из env,
   таймаут, bounded output/retries, injectable client; настоящие LLM-решения.
3. В service.py выбирать ordered scenario_ids: urgent first, остальные в порядке речи.
   Учитывать все 43 ID. Не отрезать нужный сценарий жёстким lexical top-k.
4. conversation.py: продолжение, заполнение слотов, switch/park/resume, multi-intent.
   Платформа хранит state; router возвращает новый state. Не разделять сессии через globals.
5. SYS_UNCLEAR/OUT_OF_SCOPE/GOODBYE; короткое основание по границам сценариев,
   альтернативы, честная уверенность; никакого отображения hidden chain of thought.
6. evals/: генерация predictions.json из Decision.scenario_ids, затем официальный
   evaluate.py. Primary/full-match/multi-intent recall и RU/KK/mixed slices.
7. Начать с одного компактного LLM-вызова на ход. Второй дорогой вызов только
   после измеримого выигрыша и согласования бюджета с ролью 2.
8. Подключить в service.py реальный провайдер совместно с интегратором;
   поддержать явный scaffold для бесплатных тестов.

## Критерии готовности

- Любая новая реплика проходит реальный LLM в live; ID валидируются по каталогу.
- 104 dev-реплики оценены без обучения/хардкода по ним; ошибки честно записаны.
- Многотемный разговор сохраняет слоты и возвращается к parked теме.
- Тесты offline с подставным клиентом не тратят API; live eval запускается явно.
- Интерфейс ScenarioRouter.route и v1 wire contract совместимы с platform.

## Статус

- [x] Прочитан контекст, исходные 22 теста scaffold прошли
- [x] Первый рабочий срез: полный каталог, OpenAI provider, policy, темы
- [x] Основная маршрутизация реализована; 112 offline-тестов всего проекта проходят
- [x] Eval harness и воспроизводимый mock demo, отдельный holdout 12 реплик
- [ ] Реальный live eval 104 реплик — требует отдельного разрешения на расход
- [ ] Интеграция live в platform — владелец 2, после budget adapter
- [x] Offline-проверки пройдены, ограничения записаны
- [x] Первый срез запушен (1a1bd41), HANDOFF.md обновлён; финальный срез отправляется отдельно

## Договорённость о роли

Пользователь явно назначил AI Router / feat/router / backend/router.
В origin/main найден более новый 7aaee49: LLM+Voice / feat/voice, владелец Alexandr.
Пользователь подтвердил: «Оставляем мою роль AI Router в feat/router».
Работа остаётся в этой ветке и зоне; чужую ветку/voice не меняли.
Интегратору нужно учесть расхождение при слиянии документации. Контракт моделей не изменился.
