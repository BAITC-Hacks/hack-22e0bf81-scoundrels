# AI Router

Готовый к интеграции модуль маршрутизации; качество живой модели пока не измерено.
Изменения ограничены `backend/router/`. Wire-модели `contracts/models.py` не менялись.

## Быстрая бесплатная проверка

Из корня репозитория, после установки `requirements-dev.txt`:

```sh
python -m pytest -q
python -m backend.router.evals.demo
python -m backend.router.evals.run --mode scaffold --output-dir backend/router/artifacts/scaffold-check
```

В подготовленном Windows clone вместо `python` можно использовать
`backend/router/.venv/Scripts/python.exe`. Окружение и artifacts игнорируются Git.

Demo использует настоящий SDK с MockTransport и заранее заданными ответами из
`data/demo_dialog.json`. Проверяет state/контракт/приоритеты, НЕ интеллект модели.
Трасса: `backend/router/artifacts/demo.json`. Шесть ходов RU → KK → RU → mixed,
возврат к полису, срочное ДТП, повторная неясность и передача контекста оператору.

## Подключение платформой

```python
from backend.router.providers.openai_provider import OpenAIProvider
from backend.router.service import ScenarioRouter

# Platform заранее загрузила локальный .env и создала budget adapter для этой сессии.
provider = OpenAIProvider.from_env(budget=session_budget_adapter)
router = ScenarioRouter(provider, mode="live")
trace = await router.route_with_trace(context, catalog)
result = trace.result  # RouteResult v1
# trace.language -> TurnResponse.language, trace.router_ms -> timings.router_ms
# Исполнитель платформы формирует ответ по KB/actions и возвращает его клиенту.
await provider.aclose()  # При закрытии принадлежащего платформе клиента.
```

Этот пример — wiring, не самостоятельно запускаемый сервер. Бюджет привязывается
к сессии/запуску; нельзя использовать бюджет чужой сессии в общем router singleton.
Допустимо инжектировать общий AsyncOpenAI-клиент в отдельные session-bound providers;
жизненным циклом общего клиента тогда управляет платформа.

Совместимый `await router.route(context, catalog)` возвращает только RouteResult.
`route_with_trace` дополнительно возвращает язык, реальные provider/router milliseconds,
usage последней успешной попытки и число попыток. Расход ВСЕХ попыток идёт через guard.
Нет общего `last_response`, способного перепутать параллельные сессии.

`ScenarioRouter()` всегда scaffold, даже при наличии ключа или APP_MODE в окружении.
Live требует явных provider и mode. Ни один live-сбой не превращается в scaffold-успех.

## Настройки провайдера

| Переменная окружения | Значение |
|---|---|
| OPENAI_API_KEY | Только локальное окружение / .env; никогда не Git |
| OPENAI_ROUTER_MODEL | Обязательный model ID, без автоматического выбора |
| ROUTER_TIMEOUT_SECONDS | 20 по умолчанию, максимум 60 на попытку |
| ROUTER_MAX_OUTPUT_TOKENS | 1800 по умолчанию, 256–8192 |
| ROUTER_MAX_RETRIES | 0 по умолчанию, допустимо 1 |

Provider не загружает .env сам — это обязанность platform startup; eval CLI загружает
его только после явного разрешения live. SDK retries выключены. Повтор возможен
только для временной сетевой/HTTP ошибки, с отдельным резервом и учётом расхода.
Refusal, неверный JSON, усечённый ответ и неверные ID не повторяются автоматически.
Structured Outputs: https://developers.openai.com/api/docs/guides/structured-outputs

`BudgetGuard.authorize(RequestEstimate) -> reservation_id` должен атомарно
зарезервировать максимально возможный расход и бросить исключение при превышении
session/run budget. `settle(reservation_id, TokenUsage | None)` вызывается и при отказе,
и при ошибке. None означает неизвестный расход: полный резерв остаётся занятым.
Вход оценивается консервативно по UTF-8 bytes + framing allowance, без скидки кэша.
Production guard, цены и лимиты — ответственность интегратора; EvalBudget только для CLI.

## Правила состояния и исполнения

- Модель видит все 43 сценария, границы, по два RU/KK примера и описания слотов.
  Официальные dev-labels в промпт не попадают, lexical top-k отсутствует.
- Один содержательный вызов на ход, включая определение продолжения/языка/слотов.
- Приоритет `urgent` идёт первым, `high` не обгоняет обычные намерения.
- Слоты привязаны к намерению. Пустые значения не стирают ранее известные.
  Исправления заменяют соответствующий слот. Дубликаты и неверные форматы отклоняются.
- В v1 значения строковые: числа — decimal strings, boolean — `true`/`false`,
  списки — JSON-array строк. Enum/date/phone форматы берутся из официального slots.json.
- create/switch создают новую основную тему; continue/resume используют существующую.
  При нескольких темах одного сценария обязателен точный target_topic_id.
- resolve закрывает только указанную тему разговора; executor не должен выполнять
  бизнес-действия по решению с topic_operation=resolve. Очередь остаётся parked.
- Goodbye сохраняет незавершённые темы как parked. Transfer сохраняет все слоты
  и помечает открытые темы transferred; фактический перевод выполняет platform.
- Medium/low либо SYS_UNCLEAR → один вопрос. Повторный SYS_UNCLEAR → transfer.
  Certainty — самооценка модели, не откалиброванная вероятность.
- requires_confirmation описывает требование основного сценария, НЕ согласие клиента.
  Подтверждение действия должно быть связано с действием и слотами в platform.

## Ограничения

Нет утверждения о достигнутой точности, задержке живого API или качестве KK.
Scaffold-прогон 104 строк проверяет только оценщик. Отдельный набор из 12 новых
синтетических реплик подготовлен в data/holdout_utterances.json, live не выполнялся.
Неверный формат извлечённого слота отклоняет решение целиком; исправление/вопрос
при ошибке и дальнейшее исполнение должен обработать platform.
Текущий HTTP-сервер остаётся scaffold до интеграции владельцем общих файлов.
