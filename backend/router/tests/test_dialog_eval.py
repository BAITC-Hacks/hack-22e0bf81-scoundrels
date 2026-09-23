from argparse import Namespace

import pytest

from backend.router.evals.dialogs import parse_args, run_dialogs, score_records
from backend.router.evals.run import LiveSettings


def test_dialog_eval_requires_explicit_live_flag_before_configuration():
    import asyncio
    with pytest.raises(SystemExit, match="--live"):
        asyncio.run(run_dialogs(
            Namespace(live=False),
            LiveSettings(openai_api_key=None, openai_router_model=None),
        ))


def test_dialog_eval_is_hard_limited_to_ten_dialogs():
    with pytest.raises(SystemExit):
        parse_args(["--live", "--max-dialogs", "11"])
    parsed = parse_args(["--live", "--dialog-id", "D02", "--dialog-id", "D06"])
    assert parsed.dialog_id == ["D02", "D06"]


def test_dialog_metrics_count_routes_slots_languages_and_latency():
    records = [
        {
            "expected": ["SC17"], "predicted": ["SC17"], "lang": "ru",
            "detected_language": "ru", "expected_slot_names": ["phone"],
            "predicted_slot_names": ["phone"], "latency_ms": 100,
        },
        {
            "expected": ["SC27", "SC31"], "predicted": ["SC27"], "lang": "mixed",
            "detected_language": "mixed", "expected_slot_names": ["policy_number"],
            "predicted_slot_names": [], "latency_ms": 300,
        },
    ]
    metrics = score_records(records)
    assert metrics["route_exact_match"] == 0.5
    assert metrics["primary_accuracy"] == 1.0
    assert metrics["slot_name_recall"] == 0.5
    assert metrics["language_detection_accuracy"] == 1.0
    assert metrics["latency_ms"]["p50"] == 200.0
