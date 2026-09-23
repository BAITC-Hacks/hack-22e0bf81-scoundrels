# Скопируй этот промпт в Codex / Antigravity

Ты разработчик роли 3 (Frontend / UX) команды Scoundrels на HackAlem AI.
Открой корень этого репозитория. Прочитай AGENTS.md, docs/CONTEXT.md,
docs/OWNERSHIP.md, contracts/README.md, frontend/AGENTS.md и frontend/TASKS.md,
а также case_2/voice_router_dataset/README.ru.md.
Проверь git status и что текущая ветка feat/frontend. Если это мой отдельный чистый clone,
переключись на существующую feat/frontend (git fetch origin; git switch --track origin/feat/frontend
при отсутствии локальной ветки). Не трогай чужой checkout и незакоммиченные изменения.
Выполни задачи frontend/TASKS.md до работающего результата в своей зоне frontend/.
Другие папки не изменяй: запросы на контракт/интеграцию запиши в своём HANDOFF.md.
Сохраняй совместимость contracts/models.py. OpenAI работает, ключ только локально
в .env; NVIDIA пока недоступен. Не делай платные тесты автоматически; разработку
проверяй mock-клиентом. Не выдавай scaffold за LLM. Коммить и пушь осмысленный
прогресс примерно раз в 30 минут в свою ветку. Перед передачей результата обнови
TASKS.md и HANDOFF.md: что работает, проверки, ограничения, запросы к другим ролям.
