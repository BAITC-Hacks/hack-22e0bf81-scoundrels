# Routing evaluation — owner 1

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

## Commands

```powershell
# Five new phrases, independent from official dev data:
.\.venv\Scripts\python.exe -m backend.router.evals.run --live --suite holdout --max-items 5 --output artifacts\router-holdout.json

# Full paid dev run (default is only 20; 104 must be explicit):
.\.venv\Scripts\python.exe -m backend.router.evals.official --live --max-items 104 --concurrency 4

# Unchanged organizer evaluator. -X utf8 avoids a Windows cp1251 print failure on Kazakh text:
.\.venv\Scripts\python.exe -X utf8 case_2\voice_router_dataset\evaluate.py artifacts\predictions.json case_2\voice_router_dataset\dev_utterances.json
```

The live runner checkpoints after every completed call. Re-run with the same arguments and
`--resume` to retry provider failures without paying for completed records again. A stored
fingerprint rejects resume after changing model, schema, catalog or prompt.

Verified 2026-09-23 with gpt-6-luna / reasoning low: 103/104 primary and full match,
1.0 multi-intent recall, 5/5 synthetic holdout, no API errors. Router p50 3043.0 ms,
p95 4708.9 ms. Cache hit was 99.09%; the final run's uncached-rate cost upper bound was
$0.114668. Detailed records and generated predictions are ignored under artifacts/.
