from argparse import Namespace
from types import SimpleNamespace

import pytest

from backend.router.evals.official import (
    _usage_detail_value,
    evaluation_fingerprint,
    parse_args,
    run_official,
    score_records,
)
from backend.router.evals.run import LiveSettings


def test_official_eval_requires_explicit_live_flag_before_configuration():
    import asyncio
    with pytest.raises(SystemExit, match="--live"):
        asyncio.run(run_official(
            Namespace(live=False),
            LiveSettings(openai_api_key=None, openai_router_model=None),
        ))


def test_official_eval_is_hard_limited_to_dataset_size_and_five_workers():
    with pytest.raises(SystemExit):
        parse_args(["--live", "--max-items", "105"])
    with pytest.raises(SystemExit):
        parse_args(["--live", "--concurrency", "6"])


def test_usage_detail_supports_sdk_objects_and_missing_details():
    usage = SimpleNamespace(input_tokens_details=SimpleNamespace(
        cached_tokens=1024, cache_write_tokens=2048
    ))
    assert _usage_detail_value(usage, "cached_tokens") == 1024
    assert _usage_detail_value(usage, "cache_write_tokens") == 2048
    assert _usage_detail_value(None, "cached_tokens") == 0


def test_evaluation_fingerprint_changes_with_model_configuration():
    first = evaluation_fingerprint([], "model-a", "low")
    second = evaluation_fingerprint([], "model-b", "low")
    assert first != second
    assert len(first) == 64


def test_metrics_match_official_set_semantics_and_preserve_order_metric():
    records = [
        {
            "id": "A", "text": "a", "lang": "ru", "type": "single",
            "expected": ["SC01"], "predicted": ["SC01"], "latency_ms": 100,
            "detected_language": "ru",
        },
        {
            "id": "B", "text": "b", "lang": "mixed", "type": "multi_intent",
            "expected": ["SC38", "SC29"], "predicted": ["SC29", "SC38"],
            "latency_ms": 300, "detected_language": "mixed",
        },
    ]
    metrics = score_records(records)
    assert metrics["groups"]["all"]["primary_accuracy"] == 0.5
    assert metrics["groups"]["all"]["full_match"] == 1.0
    assert metrics["ordered_full_match"] == 0.5
    assert metrics["multi_intent_recall"] == 1.0
    assert metrics["latency_ms"]["p50"] == 200.0
