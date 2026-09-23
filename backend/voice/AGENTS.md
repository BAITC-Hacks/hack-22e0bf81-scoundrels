# Роль 1 — мы: LLM + Voice

Ветка feat/voice. Наша роль владеет backend/router/** и backend/voice/**.
Прочитай корневой AGENTS.md, docs/CONTEXT.md, docs/OWNERSHIP.md,
contracts/README.md и TASKS.md этой папки.
Backend/platform и общие файлы ведёт товарищ в feat/backend.
OpenAI работает. NVIDIA не требуется. Ключи только на сервере.
В этой папке: STT/TTS адаптеры и их тесты; HTTP endpoints — у backend.
Согласуй usage accounting с интегратором перед live-подключением.
