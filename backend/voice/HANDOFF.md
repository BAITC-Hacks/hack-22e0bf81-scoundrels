# Голос: контракт для интеграции (роль 1 → роли 2 и 3)

Обновление `feat/try_upgr_perf`: добавлен `OpenAISynthesizer.stream()` с
контекстным управлением соединением и проверкой размера. Buffered `synthesize()`
сохранён. HTTP streaming и MediaSource проверены в браузере на RU/KK/EN.
Замеры и ограничения — `docs/PERFORMANCE.md`.

Ветка `feat/voice`. Адаптеры реализованы и проверены отдельно от HTTP.
Роль 2 владеет `backend/platform/**`, общими контрактами, бюджетом и endpoints;
роль 3 — `frontend/**`. После интеграции в `main` сайт работает при
`APP_MODE=live`; в бесплатном `APP_MODE=scaffold` `/api/voice/*` возвращает 501.

## Python API

```python
from backend.voice.stt import OpenAITranscriber, TranscriptionError
from backend.voice.tts import OpenAISynthesizer, SpeechError

stt = OpenAITranscriber(model="gpt-transcribe", api_key=key)
transcript = await stt.transcribe(audio_bytes, filename="recording.webm", language_hint="mixed")
# transcript.text, .language, .detected_languages, .stt_ms, .usage, .model

tts = OpenAISynthesizer(model="gpt-4o-mini-tts", api_key=key, voice="marin")
speech = await tts.synthesize(reply_text, language="kk")
# speech.audio (MP3), .content_type, .tts_first_byte_ms, .tts_total_ms
```

`language_hint`: `auto`, `ru`, `kk`, `en`, `mixed`. Для `gpt-transcribe`
и `mixed` передаются `languages=["kk", "ru", "en"]`; для mini-модели этот
параметр не передаётся. `TranscriptionResult.language` — подсказка от STT,
не надёжная детекция каждого слова: в смешанном примере API вернул `en`,
хотя transcript содержит казахский и английский. Для маршрутизации передавайте
`transcript.text` и `RouterContext(language="auto")`, чтобы LLM видел весь текст.

STT принимает непустые bytes до 25 MiB и имя с расширением flac/mp3/mp4/mpeg/
mpga/m4a/ogg/wav/webm. Это не заменяет MIME-проверку и ограничение upload
в HTTP. TTS принимает 1–2000 символов и отдаёт `audio/mpeg`, максимум 10 MiB.
Оба адаптера имеют timeout 20 с и ноль автоматических retries: не повторять
платный запрос вслепую после неизвестного исхода. Ошибки провайдера снаружи
обобщены; детали доступны только через `__cause__` на сервере, не в HTTP ответе.

## Интеграционные задачи роли 2

1. Добавить `en` в `contracts.models.Language` либо преобразовывать его в
   `mixed`/`auto` без потери текста; сейчас общий контракт отклоняет `en`.
2. Создавать адаптеры один раз на app lifespan, брать конфигурацию из env,
   хранить ключ только на сервере. `OPENAI_STT_MODEL=gpt-transcribe` рекомендован
   для mixed по нашему ограниченному тесту; mini испортил казахский фрагмент.
3. `/api/voice/transcribe`: читать upload с hard limit, передавать filename;
   вернуть `Transcript(text, language, stt_ms)`, нормализовав `en` для текущего
   wire contract, если контракт ещё не расширен. 413/415/422/502/504 —
   различать размер, формат, пустой ввод, провайдера и timeout.
4. `/api/voice/synthesize`: `SpeechRequest` → `speech.audio` с
   `Content-Type: audio/mpeg`; добавить `X-TTS-First-Byte-Ms` и
   `X-TTS-Total-Ms` либо отдельную telemetry. Сейчас `synthesize()`
   буферизует весь MP3; для latency-бонуса нужен streaming endpoint.
5. Перед каждым платным вызовом зарезервировать бюджет. STT возвращает
   provider usage (в live-пробе — seconds); TTS endpoint usage не вернул,
   резервировать по длине текста/консервативной оценке. SDK retries отключены.
6. Связать транскрипт → существующий turn/router → исполнитель сценария →
   короткий безопасный ответ → TTS. Не озвучивать вымышленные бизнес-результаты.

## Интеграционные задачи роли 3

MediaRecorder должен отправить файл с именем/расширением, которое реально
соответствует контейнеру браузера; для webm — `recording.webm`. После TTS
проигрывать MP3; измерить end-of-speech → **фактическое начало playback**,
включая upload, backend, download и browser decode. Показывать текст транскрипта
и error state. В интерфейсе явно обозначить, что голос сгенерирован AI.

## Проверки и честные ограничения

`python -m pytest -q`: 63 passed локально. В bounded live loopback
на сохранённом MP3 `gpt-transcribe` + `gpt-6-luna` дал 3/3 ожидаемых routes
для RU, KK и KK/EN. Это три синтетически озвученные фразы, **не** проверка
реального микрофона, акцентов, шума или произношения человеком. Локальные
MP3/отчёты — ignored `artifacts/`, в Git не попадают.

Последний STT→router run (три фразы): RU 1355.7+3088.6 ms,
KK 652.9+2307.1 ms, mixed 678.5+3140.3 ms. Даже без TTS/сети браузера
это выше бонусного порога 1.5 s. Файловый TTS первого байта в отдельном run:
RU 752.1, KK 708.0, mixed 608.8 ms. Эти числа **нельзя** выдавать за
`end_to_audio_ms`; его пока нет. Для ускорения сначала нужна рабочая
интеграция и измерение breakdown на реальном UI, затем streaming/fast path.
