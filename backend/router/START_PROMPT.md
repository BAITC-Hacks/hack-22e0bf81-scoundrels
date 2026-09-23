# Скопируй этот промпт в Codex / Antigravity

Ты разработчик роли 1 (LLM + Voice) команды Scoundrels на HackAlem AI.
Открой корень этого репозитория. Прочитай AGENTS.md, docs/CONTEXT.md,
docs/OWNERSHIP.md, contracts/README.md, backend/router/AGENTS.md и backend/router/TASKS.md,
а также case_2/voice_router_dataset/README.ru.md.
Проверь git status и что текущая ветка feat/voice. Если это мой отдельный чистый clone,
переключись на существующую feat/voice (git fetch origin; git switch --track origin/feat/voice
при отсутствии локальной ветки). Не трогай чужой checkout и незакоммиченные изменения.
Выполни задачи backend/router/TASKS.md до работающего результата в своих зонах backend/router/ и backend/voice/.
Остальные папки не изменяй: запросы на контракт/интеграцию запиши в своём HANDOFF.md.
Сохраняй совместимость contracts/models.py. OpenAI работает, ключ только локально
в .env; NVIDIA пока недоступен. Не делай платные тесты автоматически; разработку
проверяй mock-клиентом. Не выдавай scaffold за LLM. Коммить и пушь осмысленный
прогресс примерно раз в 30 минут в свою ветку. Перед передачей результата обнови
TASKS.md и HANDOFF.md: что работает, проверки, ограничения, запросы к другим ролям.

Это наша объединённая LLM + Voice роль. Прочитай и выполни также
backend/voice/AGENTS.md и backend/voice/TASKS.md. STT/TTS принадлежат нам;
HTTP endpoints и бизнес-исполнитель — товарищу в feat/backend.
