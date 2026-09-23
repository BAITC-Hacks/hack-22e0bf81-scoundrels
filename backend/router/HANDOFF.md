# Handoff — роль 1

Ветка: feat/voice
Статус: этап 2 завершён и готов к передаче; этап 3 начинается с его commit + push.

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

## Проверки

`python -m pytest -q`: 38 passed. Этап 2: 5 платных Router-вызовов.
Каталог промпта: 43 карточки, 15 524 символа / 18 042 UTF-8 байта.

Live gpt-6-luna: 5/5; 22 085 input tokens, 731 output tokens; оценка $0.005148.
Latency: 2413.8..5561.7 ms, median 3766.2 ms. Это только router, не end-to-audio.

## Что осталось

См. ROADMAP.md. В начале этапа 3 закоммитить и запушить текущий этап 2,
затем начать официальную оценку и оптимизацию качества/задержки.

## Запросы к другим ролям

Роли backend: перед live-app integration нужен usage/spend callback contract и
добавление `en` в общий Language contract. `mixed` должен поддерживать 2–3 языка.
