# Разделение работы и Git

| Роль | Ветка | Рабочие папки |
|---|---|---|
| 1 — Мы: LLM + Voice | feat/voice | backend/router/** + backend/voice/** |
| 2 — Backend / Integration | feat/backend | backend/platform/** |
| 3 — Frontend / UX | feat/frontend | frontend/** |

Все три рабочие ветки получают общее обновление распределения из main.
Роль 1 — Александр и Codex в текущей задаче; двум товарищам — роли 2 и 3.
Старая feat/router сохранена для истории, но больше не используется для разработки.
Если уже выбрали её: сохраните работу в своей ветке перед переключением; не сбрасывайте изменения.
Роль 2 — интегратор, поэтому у неё дополнительная ответственность за общие файлы.

## Общие файлы
contracts/**, docs/**, корневые README/AGENTS/GEMINI, backend/__init__.py,
run.py, requirements*.txt, pyproject.toml, .env.example, .gitignore, .gitattributes,
Dockerfile, compose.yaml, .dockerignore, .github/** — редактирует интегратор.
Изменения API обсуждаются с владельцами 1 и 3; желательно только совместимые добавления.
Роли 1 и 3 записывают запрос на изменение в своём HANDOFF.md.
case_2/** — исходный набор, никто не изменяет; дополнительные тесты — backend/router/data/.
Собственные зависимости: backend/router/requirements.txt, backend/platform/requirements.txt.
Frontend может добавить package.json/lockfile внутри frontend, но изменение сборки/запуска
согласовать с интегратором. Не запускать общий formatter по чужим папкам.

## Начало работы (у каждого собственный clone)
git clone https://github.com/BAITC-Hacks/hack-22e0bf81-scoundrels.git
cd hack-22e0bf81-scoundrels
git fetch origin
git switch --track origin/feat/voice

Заменить последнюю ветку на feat/backend или feat/frontend для своей роли.
Если локальная ветка уже существует: git switch feat/voice.
Открывать корень репозитория в IDE, затем передать агенту START_PROMPT.md своей папки.
Python-установка и запуск — README.md.

## Рабочий цикл примерно раз в 30 минут
1. Проверить git status и выполнить проверки своей зоны.
2. git add backend/router backend/voice (или папку своей роли).
3. git diff --cached — убедиться, что нет ключей/чужих файлов.
4. git commit -m "feat(ai-voice): describe actual completed work"
5. git push -u origin feat/voice
6. Обновить собственный HANDOFF.md перед следующим передачей результата.

Коммиты осмысленные, push нужен для видимого прогресса организаторам.
Таймер/автоматизация коммитов не установлены. Историю не переписывать.

## Интеграция (роль 2)
После первого работающего текстового пути интегрировать небольшими порциями,
затем регулярно по готовности, не ждать окончания хакатона.
При чистом рабочем дереве:
git fetch origin
git switch main
git pull --ff-only origin main
git merge --no-ff origin/feat/voice
python -m pytest -q
git push origin main

Аналогично feat/backend и feat/frontend. При конфликте согласовать его с владельцем,
не выбирать blindly ours/theirs. Если тесты не проходят, не пушить main до исправления.
На собственной рабочей ветке получить интеграцию: git fetch origin; git merge origin/main.
Не rebase опубликованных веток и не force push. После интеграции снова своя ветка.

## Почему конфликтов будет мало
Файлы реализации, тесты и заметки физически разделены. Все зависят от одного контракта.
Это уменьшает пересечения, но не гарантирует отсутствие логических несовместимостей;
их ловят общие тесты и ранняя интеграция.

## Граница голоса и базового backend

Роль 1 пишет backend/voice: вызовы OpenAI STT/TTS, обработку языка, провайдерные
ошибки и метрики. Роль 2 пишет HTTP endpoints /api/voice/*, ограничения upload,
сессии, общий бюджет и подключение адаптеров. Роль 3 пишет запись микрофона и
воспроизведение в браузере. Никто не реализует чужую часть параллельно.
Одна ветка feat/voice содержит и router, и voice; две папки принадлежат одному человеку.
