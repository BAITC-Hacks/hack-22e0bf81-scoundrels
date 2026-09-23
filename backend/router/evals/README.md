# Routing evaluation — owner 1

## Выполнено offline

Генератор `python -m backend.router.evals.run` по умолчанию использует scaffold.
Он обработал все 104 строки и вызвал неизменённый официальный evaluate.py.
Пустые predictions дали нулевые метрики — это НЕ результат качества LLM.
Настоящий LLM на dev/holdout ещё не запускался. Платных запросов: 0.

Бесплатное demo состояния: `python -m backend.router.evals.demo`.
Инструкции провайдера и интеграции: [../README.md](../README.md).

## Явный live-прогон (не запускать без разрешения)

После согласования model ID, актуальных цен и суммы с владельцем бюджета:

```text
python -m backend.router.evals.run --mode live --allow-paid --max-requests 104 --limit 104 --max-usd <согласованная-сумма> --input-usd-per-million <цена-входа> --output-usd-per-million <цена-выхода> --output-dir backend/router/artifacts/live-dev
```

Параметры в угловых скобках нужно заменить; фиксированных цен/модели в коде нет.
Предварительно OPENAI_API_KEY и OPENAI_ROUTER_MODEL задаются в локальном .env или env.
CLI ограничивает и число попыток, и резервируемую сумму; retries тоже расходуют лимит.
Неизвестный расход после сбоя остаётся зарезервирован. На первой ошибке сбор останавливается,
частичные результаты сохраняются; код возврата 2. Нет продолжения на 103 дорогих ошибках.
Для holdout добавить `--dataset backend/router/data/holdout_utterances.json --limit 12`
и отдельную директорию результата/лимит 12. Это авторский набор, не скрытый тест жюри.

Выходы: predictions.json, report.json, timings.json, evaluated_dataset.json,
official_metrics.txt. Артефакты сохраняются только внутри backend/router.
Отчёт содержит режим, модель, размер выборки, ошибки, hashes источников, число API calls,
консервативный расход, primary/full-match/intent-recall по языкам и типам,
дополнительное ordered_exact_match, abstention rate и p50/p95 router latency.
Полный full_match официального скрипта сравнивает множества, не весь порядок.
Замеры кэшированных и некэшированных запросов разделены, mouth-to-ear не заявляется.

## Правила оценки

1. Official interface: python case_2/voice_router_dataset/evaluate.py artifacts/predictions.json case_2/voice_router_dataset/dev_utterances.json
2. Keep SC01..SC40 and SYS_OUT_OF_SCOPE / SYS_UNCLEAR / SYS_GOODBYE unchanged.
3. Report top-1 accuracy on dev_utterances plus RU / KK / mixed / topic-switch slices.
4. Separate abstention rate (clarify/transfer) from correct scenario selection.
5. Use a distinct synthetic holdout; never hardcode judge or dev phrases.
6. Measure router wall time (complete validated decision, not first token), p50/p95.
7. Keep fresh and cached measurements separate. Publish sample size and model.
8. Offline tests are free; live eval is explicit, bounded and counts API usage.
9. Store generated reports in ignored artifacts/. Commit a concise verified summary.

Predictions format: {"U001": ["SC01"], "U085": ["SC27", "SC04"]}.
Export ordered Decision.scenario_ids; primary is first. Empty lists count as errors.
Use urgent-first, then mention order. The reference evaluator checks primary accuracy,
full match and multi-intent recall, with language/type breakdowns.
