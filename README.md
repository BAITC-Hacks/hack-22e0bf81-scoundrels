# RouteMap · Voice Router

HackAlem AI · Scoundrels · кейс Halyk Bank / Voice Router.
Веб-симулятор контакт-центра Saqta Insurance: LLM выбирает сценарии,
сохраняет несколько тем разговора и объясняет решение супервизору.

**Сейчас это командный scaffold, не готовая конкурсная работа.**
Работают запуск, загрузка исходного каталога, сессии, текстовый API, UI и трасса.
LLM, STT/TTS, бизнес-действия и контроль расходов — задания участников.
Scaffold не делает платных API-вызовов; голосовые endpoints честно возвращают 501.

## Команда: выберите свою роль

| Участник | Ветка | Рабочая папка | С чего начать |
|---|---|---|---|
| 1 — Мы: LLM + голос | feat/voice | backend/router/ + backend/voice/ | [Задачи](backend/router/TASKS.md) · [Промпт агенту](backend/router/START_PROMPT.md) |
| 2 — Backend / интеграция | feat/backend | backend/platform/ | [Задачи](backend/platform/TASKS.md) · [Промпт агенту](backend/platform/START_PROMPT.md) |
| 3 — Frontend / UX | feat/frontend | frontend/ | [Задачи](frontend/TASKS.md) · [Промпт агенту](frontend/START_PROMPT.md) |

У каждого отдельный clone и одна рабочая ветка. Прочитайте [правила совместной работы](docs/OWNERSHIP.md).
Общие контракты и корневые файлы ведёт участник 2; остальные меняют только свои зоны.
Ветка feat/router устарела: наша общая LLM + Voice ветка теперь feat/voice.
Голосовые задачи роли 1: [backend/voice/TASKS.md](backend/voice/TASKS.md).
Коммит **и push** осмысленного прогресса примерно каждые 30 минут.

## Быстрый старт

Требуется Python 3.11 или 3.12. Node/Docker для обычного запуска не нужны.

```sh
git clone https://github.com/BAITC-Hacks/hack-22e0bf81-scoundrels.git
cd hack-22e0bf81-scoundrels
git fetch origin
git switch --track origin/feat/voice
python -m venv .venv
```

В последней git-команде выберите свою ветку: feat/voice, feat/backend или feat/frontend.

Windows PowerShell (активация окружения не требуется):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe run.py
```

Linux/macOS:

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python run.py
```

При активированном окружении запуск одной командой: `python run.py`.
Открыть http://127.0.0.1:8000 — текстовая проверка API и JSON-трасса;
http://127.0.0.1:8000/docs — интерактивный контракт API.
Ctrl+C останавливает сервер. Сессии пока в памяти; перезапуск их очищает.
Демо ограничено 10 пользовательскими ходами и 100 сессиями на процесс.

Опционально: `docker compose up --build` (Docker-вариант в этой среде не проверялся).

## Ключи и расходы

Для scaffold .env не нужен. Для будущей live-интеграции скопируйте .env.example в .env
и укажите свой OPENAI_API_KEY локально. OpenAI работает, NVIDIA пока недоступен
из-за верификации аккаунта. Не отправляйте ключи в чат, Git или frontend.
На участника выделено USD 50 OpenAI; автоматического объединения кредитов нет.

Даже с ключом scaffold не вызывает API. APP_MODE=live пока не поддерживается:
участник 2 включает его только после интеграции провайдеров и лимитов.
SESSION_BUDGET_USD/RUN_BUDGET_USD в .env.example пока являются настройками проекта
для реализации, **не действующим ограничителем расходов**.

## Структура

```text
backend/router/       # роль 1 (мы): LLM, темы, каталог, промпты, evals, tests
backend/voice/        # роль 1 (мы): OpenAI STT/TTS, языки, аудиоадаптеры
backend/platform/     # роль 2: FastAPI, сессии, HTTP endpoints, mock actions, бюджет
frontend/             # роль 3: микрофон, клиент, супервизор, replay
contracts/            # общие Pydantic-модели и описание API v1
case_2/voice_router_dataset/  # неизменённый официальный стартовый набор
docs/                 # общий контекст, ТЗ, владение файлами, приёмка
.github/workflows/    # бесплатный CI на Python 3.11/3.12
run.py                # локальный запуск
```

В каждой рабочей папке есть AGENTS.md, GEMINI.md, TASKS.md,
START_PROMPT.md и HANDOFF.md. Передайте агенту START_PROMPT.md явно:
не все инструменты автоматически читают одинаковые файлы контекста.

## Данные и оценка

Прочитайте [README набора](case_2/voice_router_dataset/README.ru.md).
Каталог: 40 бизнес-сценариев и 3 системных намерения. Dev: 104 реплики.
Данные синтетические; дата «сегодня» внутри набора — 2026-10-01.
Оригинальные файлы не изменять. Дополнительные проверки — backend/router/data/.

Оценка реального маршрутизатора после реализации генерации predictions.json:

```sh
python case_2/voice_router_dataset/evaluate.py artifacts/predictions.json case_2/voice_router_dataset/dev_utterances.json
```

Формат predictions: `{"U001": ["SC01"], "U085": ["SC27", "SC04"]}`.
Не считайте scaffold-ответы результатом LLM. Достигнутую точность пока не заявляем.

## Проверки

```sh
python -m pytest -q
```

Или используйте путь к python из .venv, как при запуске выше.
Все тесты offline: контракты, каталог, сессии, граница 10 ходов, ошибочные ID,
статические ресурсы и честные заглушки голоса. CI не использует ключи.
Живой голос, точность маршрутизации, end-to-audio и цены проверяются отдельно.

## Архитектура и обязательные ограничения

Микрофон → STT → LLM Router + контекст → исполнитель на данных Saqta → TTS.
Супервизор получает трассу каждого хода. Многотемность: active + parked + resume.
До реализации streaming используем простую последовательность HTTP endpoints.
Содержательное решение принимает LLM; intent-классификатор и хардкод фраз запрещены.
Необратимые мок-действия требуют явного подтверждения. При затруднении — оператор.
Время backend не равно времени от конца речи до слышимого ответа.
Поддержку KK у выбранных STT/TTS нужно проверить, браузерные голоса её не гарантируют.

- [Контекст и требования](docs/CONTEXT.md)
- [Полное предоставленное ТЗ](docs/SPEC.md)
- [Контракты](contracts/README.md)
- [Распределение файлов и веток](docs/OWNERSHIP.md)
- [Приёмка и demo](docs/ACCEPTANCE.md)
