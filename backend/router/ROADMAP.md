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

## Этап 3 — оценка 104 реплик и настройка маршрутизации ✅ (локально)

Этап 2 закоммичен и отправлен (`2f03b2a`). Добавлены официальный bounded evaluator,
checkpoint/resume, predictions.json, usage/cache/latency/error отчёт и synthetic holdout.
Стабильный каталог вынесен перед динамическим turn для prompt cache.

Финальный gpt-6-luna dev-run: 103/104 (primary/full 0.9904), multi-intent recall 1.0,
RU 52/52, KK 45/45, mixed 6/7; holdout 5/5. Prompt cache hit 99.09%.
Router p50 3.043 s, p95 4.709 s: качество высокое, latency всё ещё существенно выше цели.
Этап 3 по договорённости коммитится и пушится в начале этапа 4.

## Этап 4 — состояние разговора

Active/parked/resolved topics, slots, continuation/switch/resume, urgent interruption,
SYS_UNCLEAR и повторный отказ → handoff. Прогон dialogs_sample.json.

## Этап 5 — STT адаптер

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
