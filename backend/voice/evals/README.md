# Bounded voice smoke

Это отдельный платный тест адаптеров, не часть общего `pytest` и не тест
браузерного микрофона. Он синтезирует короткие RU, KK и KK/EN фразы, затем
распознаёт MP3 и проверяет LLM-маршрут. Максимум три фразы за запуск;
`--live` обязателен. Ключ берётся из локального `.env`, никогда не печатается.

```powershell
.\.venv\Scripts\python.exe -m backend.voice.evals.smoke --live --max-items 3 --stt-model gpt-transcribe
```

После первого запуска MP3 лежат в ignored `artifacts/`. Чтобы не платить
повторно за TTS при проверке иного STT/prompt:

```powershell
.\.venv\Scripts\python.exe -m backend.voice.evals.smoke --live --case mixed --reuse-audio --stt-model gpt-transcribe --output artifacts/voice-smoke-mixed.json
```

Нужны `OPENAI_API_KEY`, `OPENAI_ROUTER_MODEL`; необязательные
`OPENAI_STT_MODEL`, `OPENAI_TTS_MODEL`, `OPENAI_TTS_VOICE` читаются из `.env`.
По умолчанию STT = `gpt-4o-mini-transcribe`, но в нашем одном mixed-кейсе
он исказил казахскую фразу и пропустил второй сценарий. Для демо ставьте
`OPENAI_STT_MODEL=gpt-transcribe` после своей проверки доступности/расходов.

Отчёт содержит transcript, ожидаемые/полученные IDs, stage timings и usage.
`tts_first_byte_ms` — первый chunk на сервере, **не** начало воспроизведения
в браузере. `stt_ms + router_ms + tts_first_byte_ms` — лишь приблизительная
оценка последовательного пути; здесь TTS читает исходную фразу до STT и
не озвучивает реальный ответ исполнителя. Целевой `end_to_audio_ms` измеряется
только в интегрированном UI от конца речи до фактического playback.

Последний ограниченный прогон: RU 1/1, KK 1/1, mixed KK/EN 1/1; это
не статистическая гарантия на произвольной речи. Прежде чем заявлять о
качестве синтеза, человеку нужно прослушать сохранённые MP3.
