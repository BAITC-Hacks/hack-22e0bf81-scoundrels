from argparse import Namespace
from types import SimpleNamespace

import pytest

from backend.router.evals.run import LiveSettings, estimate_cost, parse_args, run_live


def test_live_flag_is_required_before_configuration_or_api_access():
    with pytest.raises(SystemExit, match="--live"):
        import asyncio
        asyncio.run(run_live(
            Namespace(live=False, max_items=1, output=None),
            LiveSettings(openai_api_key=None, openai_router_model=None),
        ))


def test_smoke_run_is_hard_limited_to_five_items():
    with pytest.raises(SystemExit):
        parse_args(["--live", "--max-items", "6"])


def test_current_known_price_estimate_is_transparent():
    estimate = estimate_cost("gpt-6-luna", 1_000_000, 1_000_000)
    assert estimate["usd"] == 1.2
    assert estimate["rate_checked_on"] == "2026-09-23"
    assert estimate_cost("unknown-model", 100, 100) is None
