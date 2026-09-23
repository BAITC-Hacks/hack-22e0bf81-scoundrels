# Handoff — роль 1

Ветка: feat/voice
Статус: этап 1 завершён; live-подключение намеренно ещё не включено.

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

## Проверки

`python -m pytest -q`: 34 passed. API-вызовов и расходов: 0.
Каталог промпта: 43 карточки, 15 524 символа / 18 042 UTF-8 байта.

## Что осталось

См. ROADMAP.md. Следующий этап: bounded live smoke + eval-команда.

## Запросы к другим ролям

Роли backend: перед live-app integration нужен usage/spend callback contract.
