# Роль 1 — LLM + Voice

Эксперимент `feat/try_upgr_perf`: компактная схема и сравнительный CLI готовы;
reasoning `none` не включён по умолчанию из-за регрессий. См. `docs/PERFORMANCE.md`.

Ветка: feat/voice. Зоны роли 1: backend/router/** и backend/voice/**.
Начальное состояние: scaffold, интеграционные точки уже созданы; платные вызовы выключены.

## Задачи по порядку

1. Прочитать весь каталог, not_this_if, README набора и evaluate.py.
2. Реализовать providers/openai_provider.py: structured output, модель из env,
   таймаут, bounded output/retries, injectable client; настоящие LLM-решения.
3. В service.py выбирать ordered scenario_ids: urgent first, остальные в порядке речи.
   Учитывать все 43 ID. Не отрезать нужный сценарий жёстким lexical top-k.
4. ✅ conversation.py: продолжение, заполнение слотов, switch/park/resume, multi-intent.
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

- [x] Прочитан контекст, запущен scaffold
- [x] Первый offline-срез: schema + prompt + provider
- [x] 104 dev-реплики оценены official evaluate.py; отчёт и holdout добавлены
- [x] Topic reducer и 10 sample-dialogs / 40 client turns проверены
- [ ] Основные задачи реализованы
- [x] Текущие проверки пройдены, измеренные ограничения записаны
- [x] Этап 3 запушен, HANDOFF.md обновлён; этап 4 ожидает commit в начале этапа 5

## Голос — тоже наша зона

Выполнить также backend/voice/TASKS.md. Это одна роль и одна ветка feat/voice.
Начать с текстового LLM-router и точности, затем STT/TTS и смешанной речи.
HTTP endpoints, действия, бюджет и запуск интегрирует роль 2 в feat/backend.
