# Разделение работы и Git

| Роль | Ветка | Единственная основная зона |
|---|---|---|
| 1 — AI Router | feat/router | backend/router/** |
| 2 — Voice / Backend / Integration | feat/voice | backend/platform/** |
| 3 — Frontend / UX | feat/frontend | frontend/** |

Все три ветки начинаются от одного scaffold-коммита main.
Имена участников пока не назначены; команда выбирает человека для каждой роли.
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
git switch --track origin/feat/router

Заменить последнюю ветку на feat/voice или feat/frontend для своей роли.
Если локальная ветка уже существует: git switch feat/router.
Открывать корень репозитория в IDE, затем передать агенту START_PROMPT.md своей папки.
Python-установка и запуск — README.md.

## Рабочий цикл примерно раз в 30 минут
1. Проверить git status и выполнить проверки своей зоны.
2. git add backend/router (или свою папку).
3. git diff --cached — убедиться, что нет ключей/чужих файлов.
4. git commit -m "feat(router): describe actual completed work"
5. git push -u origin feat/router
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
git merge --no-ff origin/feat/router
python -m pytest -q
git push origin main

Аналогично feat/voice и feat/frontend. При конфликте согласовать его с владельцем,
не выбирать blindly ours/theirs. Если тесты не проходят, не пушить main до исправления.
На собственной рабочей ветке получить интеграцию: git fetch origin; git merge origin/main.
Не rebase опубликованных веток и не force push. После интеграции снова своя ветка.

## Почему конфликтов будет мало
Файлы реализации, тесты и заметки физически разделены. Все зависят от одного контракта.
Это уменьшает пересечения, но не гарантирует отсутствие логических несовместимостей;
их ловят общие тесты и ранняя интеграция.
