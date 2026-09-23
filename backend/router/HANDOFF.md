# Handoff — роль 1

Ветка: feat/voice
Статус: этап 2 запушен (`2f03b2a`); этап 3 завершён локально и ещё не закоммичен.

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

## Проверки

`python -m pytest -q`: 45 passed. Этап 2: 5 платных Router-вызовов.
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

## Что осталось

См. ROADMAP.md. В начале этапа 4 закоммитить и запушить этап 3. Затем реализовать
conversation state: active/parked/resume, slots и urgent interruption. Router latency
ещё не соответствует ориентиру 500 ms; не выдавать backend latency за end-to-audio.

## Запросы к другим ролям

Роли backend: перед live-app integration нужен usage/spend callback contract и
добавление `en` в общий Language contract. `mixed` должен поддерживать 2–3 языка.
