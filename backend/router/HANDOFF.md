# Handoff — роль 1

Ветка: feat/router
Статус: AI Router готов к интеграции; малый live smoke пройден, полный dev eval не запускался.
Автор коммитов: Frostynncht <mihonartem@gmail.com>.

В origin/main/7aaee49 изменено распределение ролей на LLM+Voice/feat/voice.
Пользователь явно подтвердил, что его роль остаётся AI Router/feat/router.
Код и тесты менялись только в backend/router; голос и platform не затронуты.

## Что работает

`ScenarioRouter()` сохраняет бесплатный scaffold.
`ScenarioRouter(provider, mode="live")` делает один содержательный LLM-вызов на ход.
Полный каталог, structured output, проверка ID/слотов, stable urgent-first,
create/continue/switch/park/resume/resolve, multi-intent, clarify/transfer.
Темы возвращаются копией; состояние хранится у platform.
Structured output возвращает отдельные слоты для каждого намерения и обнаруженный язык.
route_with_trace передаёт language и реальные router/provider timings без изменения v1.
Provider: явная модель из env, 20 s timeout, 1800 output tokens, 0 retries по умолчанию,
обязательные authorize/settle hooks, store=false, безопасные коды ошибок без payload/ключа.
Eval экспортирует Decision.scenario_ids и вызывает официальный evaluate.py; есть
RU/KK/mixed/type slices, ordered-exact, abstention, p50/p95, cached/uncached.

## Проверки

`backend/router/.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider`:
112 passed (Python 3.12, Windows) после live smoke и уточнения учёта cache-write.
В том числе настоящий SDK через MockTransport,
HTTP 429/retry, timeout/cancellation, отказ бюджета до сети, invalid/refusal/incomplete,
все 43 ID, переходы тем, изоляция сессий и интеграция v1 в исходный FastAPI.

`python -m backend.router.evals.demo`: шесть mock-ходов прошли:
SC27 create → SC33 switch (KK) → SC27 resume с прежним полисом →
[SC11, SC27] urgent-first (mixed) → SYS_UNCLEAR clarify → SYS_UNCLEAR transfer.

`python -m backend.router.evals.run --mode scaffold --output-dir backend/router/artifacts/scaffold-check`:
104/104, официальный evaluator выполнен. Primary/full-match/recall = 0 из-за пустых
scaffold predictions; это проверка pipeline, НЕ измерение LLM.

### Live smoke 2026-09-23

Модель: `gpt-6-sol`, Standard Responses API, structured output, retries=0.
Актуальные официальные ставки: input $2.00, cached input $0.20,
cache write $2.50, output $10.00 за 1M токенов.
Источник: https://developers.openai.com/api/docs/models/gpt-6-sol

Команда использовала отдельный `data/smoke_utterances.json`, 5 авторских реплик,
`--max-requests 5 --max-usd 2`. Ни dev labels, ни ожидаемый ответ не входили в prompt.

- 5/5 API-запросов завершены, failures=0, attempts=1 для каждого.
- Primary accuracy / full match / ordered exact match: 1.000 (5 реплик).
- RU: 2/2, KK: 2/2, mixed: 1/1.
- Multi-intent recall: 1.000 на одном примере `[SC11, SC27]` с urgent-first.
- Out-of-scope и unclear распознаны; unclear вернул action=clarify.
- Токены: input 42,389; cached input 33,720; output 787.
- Ledger прогона зарезервировал/учёл $0.092648 из разрешённых $2.
- Пересчитанная верхняя оценка по observed usage с тарификацией всего uncached
  input по более дорогой cache-write ставке: $0.0362865. Финальный счёт определяет OpenAI.
- Router latency: p50 3,699 ms; p95 5,169 ms. Cached p50 3,360 ms.

Проблем маршрутизации на малой выборке не найдено, поэтому prompt/policy не подгонялись.
Обнаружена неточность preflight budget: cache write дороже обычного input, а usage
не выделяет число cache-write tokens. EvalBudget исправлен: теперь резерв и settlement
оценивают весь uncached input по большей из input/cache-write ставок и требуют все 4 тарифа.

Это smoke из 5 авторских реплик, а не доказательство общей точности. Полный dev/holdout
eval и mouth-to-ear latency не измерены. Артефакты отчёта локальные и игнорируются Git.
Артефакты demo/report генерируются в игнорируемой backend/router/artifacts/.
Набор 12 новых holdout-реплик добавлен отдельно, без обучения/настройки на dev.

## Что осталось

1. Интегратор подключает provider, budget, исключения, язык и ответ/исполнитель.
2. Перед полным прогоном 104 dev-реплик согласовать отдельный лимит по результатам smoke.
   Команды и обязательные лимиты: evals/README.md; теперь нужны все 4 token rates.
3. Проверить язык и содержание живых ответов; offline-тесты проверяют механизмы,
   но не доказывают, что модель правильно извлекает слоты или понимает речь.
4. Неверно нормализованный слот сейчас отклоняет решение целиком (safe error),
   автоматический платный repair-call отсутствует.
5. Достоверный end-to-audio замер и голосовое демо выполняются после интеграции.

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

## Конкретные вопросы интегратору

- Какой adapter реализует BudgetGuard для одновременных session/run reservations?
  Сигнатуры находятся в providers/openai_provider.py и README.md; shared contract менять не нужно.
- Подключите trace.language при language=auto: в RouteResult v1 поля language нет.
- Согласуйте точный OPENAI_ROUTER_MODEL, цены и денежный/запросный лимит первого live eval.
- Подтвердите, что executor пропускает бизнес-действия при clarify, transfer и
  topic_operation=resolve, а реальное подтверждение привязано к действию и слотам.
- При слиянии учтите подтверждённую пользователем отдельную ветку feat/router,
  несмотря на смену владельца в новом main. Не перезаписывать работу других участников.

## Коммиты и воспроизведение

Первый срез: 1a1bd41 (`feat(router): implement structured LLM routing and topic state`).
Следующий срез включает eval/demo/holdout, дополнительные проверки и эту передачу.
Ветка публикуется обычным push; main не менялся, force push/rebase не выполнялись.
План девяти этапов: PLAN.md. Инструкция запуска/интеграции: README.md.
