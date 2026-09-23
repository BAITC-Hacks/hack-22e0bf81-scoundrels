# Handoff — роль 1

Ветка: feat/router
Статус: первый рабочий срез AI Router, проверен offline. Live качество не измерено.

## Что работает

`ScenarioRouter()` сохраняет бесплатный scaffold.
`ScenarioRouter(provider, mode="live")` делает один содержательный LLM-вызов на ход.
Полный каталог, structured output, проверка ID/слотов, stable urgent-first,
create/continue/switch/park/resume/resolve, multi-intent, clarify/transfer.
Темы возвращаются копией; состояние хранится у platform.

## Проверки

`backend/router/.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider`:
93 passed. В том числе настоящий SDK через MockTransport. Платных вызовов: 0.

## Что осталось

См. TASKS.md.

## Запросы к другим ролям

1. Роль 2: подключить OpenAIProvider через BudgetGuard (authorize/settle).
   Каждый retry резервируется отдельно; usage=None означает неизвестный расход,
   резерв нельзя освобождать как нулевой. По умолчанию retries=0.
2. Использовать route_with_trace для detected language, provider_ms, router_ms, usage;
   route() остаётся совместим с v1. Не использовать общий last_response для сессий.
3. Обрабатывать RouterProviderError как 502 (timeout при желании 504), до записи истории.
   Сейчас app.py ловит только неверные ID ПОСЛЕ route, исключения provider ещё не подключены.
4. Формировать ответ по knowledge_base/mock_backend и выбранному сценарию. Сейчас
   platform для любого route без вопроса говорит «Передаю вопрос оператору» — это scaffold.
5. requires_confirmation — требование, НЕ разрешение выполнить действие.
   Даже resolve закрывает только тему разговора, не подтверждает действие.
6. До включения APP_MODE=live интегратор подключает budget, reply/executor, STT/TTS и health.
