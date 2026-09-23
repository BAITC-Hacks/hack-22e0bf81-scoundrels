# Мы: голосовая часть общей роли 1

Ветка feat/voice; LLM-задачи — соседний backend/router/TASKS.md.

1. Согласовать Python-интерфейс адаптеров с ролью 2 до интеграции.
   Transcriber получает bytes + filename + языковой hint, возвращает Transcript
   и usage-данные. Synthesizer получает SpeechRequest, возвращает audio bytes,
   content_type, первую задержку и usage. HTTP не должен проникать в адаптеры.
2. stt.py: асинхронный OpenAI STT, injectable client, таймаут и ограниченные retries.
   Сохранять исходную RU/KK/смешанную речь; не навязывать перевод на русский.
3. tts.py: асинхронный OpenAI TTS, короткий ответ, audio/mpeg, ошибки провайдера.
   Проверить произношение на русском и казахском. Не обещать качество по названию модели.
4. Не включать голосовые вызовы на каждую текстовую eval-реплику.
   Тесты провайдеров используют mock-клиент; live smoke ограничен отдельным бюджетом.
5. Измерять STT и TTS time-to-first-byte честно; учитывать timeout/retry в usage.
   Токены/длительность/стоимость передавать общему budget guard роли 2.
6. Проверить без перевода/потери смысла mixed-реплику, которая влияет на выбор сценария.
   Разделять ошибки STT и ошибки LLM в отчётах.
7. Streaming/caching — после рабочего базового пути. Не выдавать полный TTS latency
   за first-byte latency; client playback latency измеряет frontend.
8. Передать интегратору пример вызова, поддерживаемые форматы и проверенные ограничения.

## Границы

- Мы: обращения к OpenAI и аудиоадаптеры.
- Товарищ backend: /api/voice/*, upload validation, configuration, budget, HTTP errors.
- Товарищ frontend: MediaRecorder, кнопка микрофона, звук в браузере и permissions.

## Готовность

- [x] Интерфейс записан в HANDOFF.md для согласования с ролью 2
- [x] STT/TTS реализованы, offline provider tests проходят
- [x] Ограниченный live smoke на RU/KK/mixed выполнен и задокументирован
- [x] HTTP-интеграция проверена; streaming доступен в feat/try_upgr_perf
- [x] Микрофон проверен при интеграции; раннее streaming-воспроизведение проверено отдельно
