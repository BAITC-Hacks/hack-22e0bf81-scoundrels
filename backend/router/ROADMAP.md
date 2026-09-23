# Наша дорожная карта: LLM + Voice

Каждый этап рассчитан примерно на один сфокусированный 30-минутный блок и заканчивается
осмысленным commit + push в feat/voice. Если этап объективно занимает дольше, внутри него
делаем промежуточный коммит только при наличии проверяемого результата, не пустой активности.

## Этап 1 — контракт LLM и offline-провайдер ✅

Structured Output schema, полный каталог 40+3, prompt safety, urgent-first policy,
явные ошибки, injectable OpenAI client, бесплатные unit-тесты. Приложение ещё scaffold.

## Этап 2 — ограниченный live smoke и eval-команда ✅

CLI с явными `--live`, `--max-items` и лимитом попыток; загрузка модели/ключа из env,
usage-отчёт, predictions.json. Сначала 3–5 реплик RU/KK/mixed, без STT/TTS.
Модель выбираем по фактической доступности и качеству, а не зашиваем в код.

Результат первого smoke на gpt-6-luna: 5/5 (RU, KK, RU/KK, EN, KK/EN/RU),
22 085 input + 731 output tokens, оценка $0.005148. Router latency:
min 2.414 s, median 3.766 s, max 5.562 s. Точность хорошая, скорость требует работы.

## Этап 3 — оценка 104 реплик и настройка маршрутизации ✅

Этап 2 закоммичен и отправлен (`2f03b2a`). Добавлены официальный bounded evaluator,
checkpoint/resume, predictions.json, usage/cache/latency/error отчёт и synthetic holdout.
Стабильный каталог вынесен перед динамическим turn для prompt cache.

Финальный gpt-6-luna dev-run: 103/104 (primary/full 0.9904), multi-intent recall 1.0,
RU 52/52, KK 45/45, mixed 6/7; holdout 5/5. Prompt cache hit 99.09%.
Router p50 3.043 s, p95 4.709 s: качество высокое, latency всё ещё существенно выше цели.
Этап 3 закоммичен и отправлен (`9ba345a`).

## Этап 4 — состояние разговора ✅ (локально)

Active/parked/resolved topics, slots, continuation/switch/resume, urgent interruption,
SYS_UNCLEAR и повторный отказ → handoff. Прогон dialogs_sample.json.

Добавлен чистый session-local reducer без globals: один active topic, очередь parked,
merge слотов, related/exact resume, resolve, urgent interruption и transferred handoff.
ScenarioRouter применяет reducer после провайдера; платформа по-прежнему владеет хранением.

Финальный live replay gpt-6-luna: 10/10 диалогов, 40/40 routes, 30/30 ожидаемых
slot names, 40/40 language detection, 0 API/state errors. Cache hit 96.88%; router
p50 3.317 s, p95 5.106 s. Финальная single-turn regression текущего prompt:
104/104 по неизменённому official evaluate.py. Этап 4 коммитится и пушится в начале этапа 5.

## Этап 5 — STT адаптер

В начале этапа сначала commit + push этапа 4. Затем:
Injectable OpenAI client, форматы/таймауты/usage, offline tests; затем ограниченный
live smoke на русском, казахском и смешанной речи. Ошибки STT отдельно от routing.

## Этап 6 — TTS адаптер

Audio bytes/content type, latency/usage, offline tests; live проверка произношения RU/KK.
Короткие ответы, без генерации речи во время массовой текстовой оценки.

## Этап 7 — интеграция и производительность

Передача интерфейсов роли backend, сквозной микрофон→STT→router→TTS с frontend,
реальные stage timings и end-to-audio, p50/p95, устойчивые ошибки и лимиты расходов.

## Этап 8 — финальная приёмка

Скрытоподобные новые реплики, demo-сценарии, README с честными цифрами,
clean-clone репетиция и фиксация известных ограничений.
