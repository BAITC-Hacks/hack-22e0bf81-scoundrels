# Роль 3 — Frontend / UX

В main исправлены сброс баннера и маркировка sample/replay; 13 JS-тестов проходят.

Дополнение `feat/try_upgr_perf`: streaming-воспроизведение и раннее отображение
маршрута готовы; RU/KK/EN проверены в браузере, 10 runtime-тестов проходят.
Проверена отмена и замена озвучки также в браузерах без MP3 MediaSource.
Запись, текст и replay не запускаются параллельно; ответы и метрики привязаны к ходу.
Замер переключён с `play` на `playing`; детали в `docs/PERFORMANCE.md`.

Ветка: feat/frontend. Зона: frontend/**.
Начальное состояние: scaffold, интеграционные точки уже созданы; платные вызовы выключены.

## Задачи по порядку

1. [x] Развить index.html + src/: клиентская панель и панель супервизора.
   Сохранен Vanilla JS с ES-модулями; переход на сторонний toolchain не потребовался.
2. [x] Микрофон через getUserMedia/MediaRecorder: начало/остановка, permission denial,
   отправка multipart file в /api/voice/transcribe; текст — резервный канал.
3. [x] Протянуть transcript → /turns → /voice/synthesize → реальное audio playback.
   Во время scaffold честно показывается статус недоступности голосовых endpoints (501), без имитации.
4. [x] Trace: ordered selected IDs, reason, alternatives, slots, active/parked topics,
   подтверждения/передача, измеренные задержки по ходам. Обогащение локальным каталогом.
5. [x] Измерить конец речи → начало фактического воспроизведения на клиенте.
   Зафиксировано приближение push-to-talk (отпуск кнопки мыши / pointerup → событие play).
   Не выдаем backend_total_ms за total latency. Добавлен расчет p50/p95 задержек.
6. [x] RU/KK UI labels и ответ, смешанная речь, новый разговор, 10-turn limit,
   сетевые ошибки и повторный запрос с in-flight блокировкой кнопки.
7. [x] Demo/replay: экспорт/импорт сохраненных прогонов с бейджем [REPLAY].
   Эталонные образцы датасета (D03, D05, D06) вынесены с честной пометкой [DATASET SAMPLE].
8. [x] src/api.js — единая точка API; все пользовательские строки безопасно рендерятся через textContent/DOM.
9. [x] Записан локальный demo checklist (`frontend/tests/DEMO_CHECKLIST.md`) и автоматические тесты `test_frontend_assets.py`.

## Критерии готовности

- [x] Жюри может без объяснений записать реплику и услышать ответ (или увидеть честный 501 scaffold).
- [x] Каждая реплика отображает трассу; видно scaffold/live/replay/sample и ошибки.
- [x] Микрофон, TTS и fallback проверены в браузере на RU/KK/mixed.
- [x] Никаких API-ключей или прямых платных запросов с браузера.
- [x] Изменения ограничены frontend/, контракт contracts/models.py строго соблюден.

## Статус

- [x] Прочитан контекст, запущен scaffold
- [x] Первый рабочий срез (API, catalog lookup, supervisor panel)
- [x] Основные задачи реализованы (Audio recorder, player, metrics waterfall, p50/p95, replay)
- [x] Проверки пройдены, ограничения записаны в DEMO_CHECKLIST.md
- [ ] Ветка запушена, HANDOFF.md обновлён

## Контакты интеграции

Роль 1, feat/voice: LLM и STT/TTS провайдеры.
Роль 2, feat/backend: HTTP API, сессии, бизнес-действия и общий бюджет.
По форме API общаться с ролью 2; по качеству RU/KK/голоса — с ролью 1.
