"""Bounded live smoke runner. It never runs from pytest or CI by itself."""
import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter
from typing import Any

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.router.catalog import load_catalog
from backend.router.providers.openai_provider import OpenAIRouterProvider
from contracts.models import RouterContext


ROOT = Path(__file__).resolve().parents[3]
SMOKE_PATH = Path(__file__).with_name("smoke_utterances.json")
HOLDOUT_PATH = Path(__file__).with_name("holdout_utterances.json")
CATALOG_PATH = ROOT / "case_2/voice_router_dataset/scenarios.json"


class LiveSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    openai_api_key: SecretStr | None = None
    openai_router_model: str | None = None
    openai_router_reasoning_effort: str | None = "low"


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Run a bounded paid router smoke test")
    parser.add_argument("--live", action="store_true", help="required to allow API calls")
    parser.add_argument("--suite", choices=("smoke", "holdout"), default="smoke")
    parser.add_argument("--max-items", type=int, default=5, choices=range(1, 6))
    parser.add_argument(
        "--output", type=Path, default=ROOT / "artifacts/router-smoke.json",
        help="result JSON; artifacts/ is gitignored",
    )
    return parser.parse_args(argv)


def _usage_value(usage: Any, name: str) -> int:
    if usage is None:
        return 0
    if isinstance(usage, dict):
        return int(usage.get(name, 0) or 0)
    return int(getattr(usage, name, 0) or 0)


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> dict | None:
    # Informational Standard rates checked 2026-09-23; billing dashboard is authoritative.
    rates = {
        "gpt-6-luna": (0.20, 1.00),
        "gpt-4o-mini": (0.15, 0.60),
    }
    if model not in rates:
        return None
    input_rate, output_rate = rates[model]
    return {
        "usd": round((input_tokens * input_rate + output_tokens * output_rate) / 1_000_000, 6),
        "input_usd_per_million": input_rate,
        "output_usd_per_million": output_rate,
        "rate_checked_on": "2026-09-23",
    }


async def run_live(args, settings: LiveSettings) -> tuple[dict, bool]:
    if not args.live:
        raise SystemExit("Refusing paid calls: pass --live explicitly")
    if not settings.openai_api_key:
        raise SystemExit("OPENAI_API_KEY is missing from .env")
    if not settings.openai_router_model:
        raise SystemExit("OPENAI_ROUTER_MODEL is missing from .env")

    suite_path = SMOKE_PATH if args.suite == "smoke" else HOLDOUT_PATH
    suite = json.loads(suite_path.read_text(encoding="utf-8"))["utterances"][:args.max_items]
    catalog = load_catalog(CATALOG_PATH)
    provider = OpenAIRouterProvider(
        model=settings.openai_router_model,
        api_key=settings.openai_api_key.get_secret_value(),
        reasoning_effort=settings.openai_router_reasoning_effort,
        prompt_cache_key="saqta-router-v1",
    )
    records = []
    predictions = {}
    input_tokens = output_tokens = 0
    all_passed = True

    for item in suite:
        started = perf_counter()
        try:
            # Public Language contract gets `en` in the backend integration change.
            # Until then, `auto` lets this internal smoke test exercise English safely.
            hint = item["lang"] if item["lang"] in {"ru", "kk", "mixed"} else "auto"
            detailed = await provider.route_detailed(
                RouterContext(text=item["text"], language=hint), catalog
            )
            predicted = detailed.result.decision.scenario_ids
            passed = predicted == item["expected"]
            all_passed = all_passed and passed
            predictions[item["id"]] = predicted
            input_tokens += _usage_value(detailed.usage, "input_tokens")
            output_tokens += _usage_value(detailed.usage, "output_tokens")
            records.append({
                "id": item["id"], "lang": item["lang"], "text": item["text"],
                "expected": item["expected"], "predicted": predicted, "passed": passed,
                "detected_language": detailed.detected_language,
                "language_components": list(detailed.language_components),
                "rationale": detailed.result.decision.rationale,
                "latency_ms": round((perf_counter() - started) * 1000, 1),
            })
        except Exception as exc:
            all_passed = False
            predictions[item["id"]] = []
            records.append({
                "id": item["id"], "lang": item["lang"], "text": item["text"],
                "expected": item["expected"], "predicted": [], "passed": False,
                "error_type": type(exc).__name__, "error": str(exc),
                "latency_ms": round((perf_counter() - started) * 1000, 1),
            })

    report = {
        "suite": f"router-{args.suite}-v1", "model": settings.openai_router_model,
        "reasoning_effort": settings.openai_router_reasoning_effort,
        "count": len(records), "passed": sum(record["passed"] for record in records),
        "all_passed": all_passed, "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost": estimate_cost(settings.openai_router_model, input_tokens, output_tokens),
        "predictions": predictions, "records": records,
    }
    return report, all_passed


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report, all_passed = asyncio.run(run_live(args, LiveSettings()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "suite", "model", "count", "passed", "all_passed", "input_tokens",
        "output_tokens", "estimated_cost",
    )}, ensure_ascii=False, indent=2))
    print(f"Detailed report: {args.output.resolve()}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
