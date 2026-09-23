# Handoff — роль 1

Обновление `feat/try_upgr_perf`: есть opt-in компактная Structured Outputs схема
и interleaved A/B CLI `backend.router.evals.performance`. Reasoning `none`
ускоряет ответы, но показал регрессии; по умолчанию оставлен исходный `low`.
Данные эксперимента: `docs/PERFORMANCE.md`.

Ветка: feat/voice
Исторический handoff ветки `feat/voice`. Текущий интегрированный статус —
в корневом `README.md` и `backend/platform/HANDOFF.md`; live-путь в `main`
подключён и проверен.

## Что работает

Общий бесплатный scaffold запускается. Добавлены:

- Pydantic-схема Structured Outputs для LLM-маршрута;
- компактный промпт со всеми 40 сценариями и 3 системными намерениями;
- OpenAI Responses provider с явной моделью, таймаутом и bounded output;
- urgent-first policy, каталог как источник confirmation policy;
- явные ошибки для timeout/incomplete/refusal-like/unknown-id ответов;
- injectable client и offline-тесты без API-расходов.

Провайдер подключается через ScenarioRouter(provider=...), но приложение продолжает
явный scaffold. Live wiring выполняется после ограниченного smoke и budget integration.

Этап 2 добавил bounded CLI `python -m backend.router.evals.run`: без `--live`
он отказывается делать запросы, `--max-items` жёстко ограничен диапазоном 1..5.
Smoke включает RU, KK, RU/KK, EN и KK/EN/RU; подробный отчёт — ignored artifacts/.

Этап 3 добавил `python -m backend.router.evals.official`: explicit `--live`, лимит
1..104, concurrency 1..5, checkpoint/resume, официальный predictions.json, разрезы
качества, token/cache usage и p50/p95. Длинный каталог теперь находится в стабильной
части prompt, динамический разговор — после него; используется стабильный cache key.
Отдельный holdout содержит новые RU/KK/mixed пограничные формулировки.

Этап 4 добавил чистый topic reducer в conversation.py и подключил его через
ScenarioRouter. Он копирует входное состояние, не использует globals, держит не более
одной active темы, паркует switch/multi-intent, сливает slots, поднимает exact/related
resume, возвращает parked тему после resolve и переводит active тему в transferred для SC37.
SYS_UNCLEAR/OUT_OF_SCOPE сохраняют работу; SYS_GOODBYE закрывает active/parked темы.

`python -m backend.router.evals.dialogs` последовательно replay-ит размеченные диалоги,
не выполняя actions. CLI требует `--live`, ограничен 1..10 диалогами и поддерживает
повторяемый `--dialog-id` для bounded диагностики.

## Проверки

`python -m pytest -q`: 57 passed. Этап 2: 5 платных Router-вызовов.
Каталог промпта: 43 карточки, 15 524 символа / 18 042 UTF-8 байта.

Live gpt-6-luna: 5/5; 22 085 input tokens, 731 output tokens; оценка $0.005148.
Latency: 2413.8..5561.7 ms, median 3766.2 ms. Это только router, не end-to-audio.

Финальный official dev (gpt-6-luna, reasoning low): primary/full 103/104 = 0.9904,
multi-intent recall 1.0; RU 52/52, KK 45/45, mixed 6/7. Synthetic holdout: 5/5.
API errors: 0. Language detection: 104/104. Cache hit: 476 008 / 480 365 = 99.09%.
Latency: p50 3043.0 ms, p95 4708.9 ms, max 6344.9 ms.
Uncached-rate cost upper bound финального run: $0.114668; actual ниже из-за cache.
За все tuning/eval прогоны этапа 3 tracked upper bounds около $0.36 плюс один failed
request с неизвестным usage. Generated reports/predictions остаются в ignored artifacts/.

Финальный multi-turn replay: 10/10 диалогов, 40/40 exact routes, 30/30 ожидаемых
slot names, 40/40 language detection, 0 API errors, 0 topic invariant failures.
Operations: create 10, continue 21, switch 2, resume 1, resolve 5, none 1.
Cache hit 196 789 / 203 128 = 96.88%; latency p50 3317.2 ms, p95 5105.9 ms,
max 6249.6 ms. Uncached-rate upper bound финального replay: $0.050061.
Контрольный official dev на финальном prompt: 104/104 primary/full, multi-intent recall 1.0,
все language/type slices 1.0, 0 API errors. Cache hit 99.17%; p50 3145.9 ms,
p95 5311.2 ms; uncached-rate upper bound $0.121905.
Все tuning/replay прогоны этапа 4: tracked upper bounds около $0.305; actual ниже.

## Что осталось

См. ROADMAP.md. В начале этапа 5 закоммитить и запушить этап 4. Затем реализовать
OpenAI STT adapter в backend/voice с injectable client и bounded live audio smoke.
Router latency всё ещё не соответствует ориентиру 500 ms; не выдавать его за end-to-audio.

## Запросы к другим ролям

Роли backend: перед live-app integration нужен usage/spend callback contract и
добавление `en` в общий Language contract. `mixed` должен поддерживать 2–3 языка.
