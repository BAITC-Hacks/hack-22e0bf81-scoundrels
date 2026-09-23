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
