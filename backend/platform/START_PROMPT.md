# Скопируй этот промпт в Codex / Antigravity

Ты разработчик роли 2 (Backend / Integration) команды Scoundrels на HackAlem AI.
Открой корень этого репозитория. Прочитай AGENTS.md, docs/CONTEXT.md,
docs/OWNERSHIP.md, contracts/README.md, backend/platform/AGENTS.md и backend/platform/TASKS.md,
а также case_2/voice_router_dataset/README.ru.md.
Проверь git status и что текущая ветка feat/backend. Если это мой отдельный чистый clone,
переключись на существующую feat/backend (git fetch origin; git switch --track origin/feat/backend
при отсутствии локальной ветки). Не трогай чужой checkout и незакоммиченные изменения.
Выполни задачи backend/platform/TASKS.md до работающего результата в своей зоне backend/platform/.
Ты интегратор общих файлов по docs/OWNERSHIP.md.
Сохраняй совместимость contracts/models.py. OpenAI работает, ключ только локально
в .env; NVIDIA пока недоступен. Не делай платные тесты автоматически; разработку
проверяй mock-клиентом. Не выдавай scaffold за LLM. Коммить и пушь осмысленный
прогресс примерно раз в 30 минут в свою ветку. Перед передачей результата обнови
TASKS.md и HANDOFF.md: что работает, проверки, ограничения, запросы к другим ролям.

LLM и OpenAI STT/TTS реализует роль 1 в backend/router/ и backend/voice/.
Твоя часть голоса — HTTP endpoints и подключение адаптеров, не сами модели.
