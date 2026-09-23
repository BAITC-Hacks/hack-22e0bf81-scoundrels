"""Explicit, bounded live evaluation over the official Voice Router dev set."""
import argparse
import asyncio
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from time import perf_counter
from typing import Any

from backend.router.catalog import load_catalog
from backend.router.evals.run import LiveSettings, _usage_value, estimate_cost
from backend.router.models import RouterModelOutput
from backend.router.prompting import build_router_instructions
from backend.router.providers.openai_provider import OpenAIRouterProvider
from contracts.models import RouterContext


ROOT = Path(__file__).resolve().parents[3]
DEV_PATH = ROOT / "case_2/voice_router_dataset/dev_utterances.json"
CATALOG_PATH = ROOT / "case_2/voice_router_dataset/scenarios.json"
MAX_DEV_ITEMS = 104


def _bounded_int(maximum: int):
    def parse(value: str) -> int:
        parsed = int(value)
        if not 1 <= parsed <= maximum:
            raise argparse.ArgumentTypeError(f"must be between 1 and {maximum}")
        return parsed
    return parse


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Run a bounded paid official router evaluation")
    parser.add_argument("--live", action="store_true", help="required to allow API calls")
    parser.add_argument(
        "--max-items", type=_bounded_int(MAX_DEV_ITEMS), default=20,
        help="number of official utterances (1..104); full run must explicitly pass 104",
    )
    parser.add_argument("--concurrency", type=_bounded_int(5), default=4)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "artifacts/router-dev-report.json",
    )
    parser.add_argument(
        "--predictions", type=Path, default=ROOT / "artifacts/predictions.json",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="continue matching completed records from an existing report",
    )
    return parser.parse_args(argv)


def _usage_detail_value(usage: Any, name: str) -> int:
    if usage is None:
        return 0
    details = usage.get("input_tokens_details", {}) if isinstance(usage, dict) else (
        getattr(usage, "input_tokens_details", None)
    )
    if details is None:
        return 0
    if isinstance(details, dict):
        return int(details.get(name, 0) or 0)
    return int(getattr(details, name, 0) or 0)


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    value = ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
    return round(value, 1)


def evaluation_fingerprint(catalog, model: str, reasoning_effort: str | None) -> str:
    """Prevent resume from mixing predictions made with different routing behavior."""
    configuration = {
        "model": model,
        "reasoning_effort": reasoning_effort,
        "max_output_tokens": 600,
        "instructions": build_router_instructions(catalog),
        "output_schema": RouterModelOutput.model_json_schema(),
    }
    encoded = json.dumps(
        configuration, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def score_records(records: list[dict]) -> dict:
    groups = defaultdict(lambda: {"count": 0, "primary_correct": 0, "full_correct": 0})
    recall_hit = recall_total = ordered_correct = language_correct = 0
    detected_count = 0
    latencies = []

    for record in records:
        expected = record["expected"]
        predicted = record.get("predicted", [])
        primary = bool(predicted) and predicted[0] == expected[0]
        full = set(predicted) == set(expected)
        ordered_correct += predicted == expected
        if record["type"] == "multi_intent":
            recall_hit += len(set(expected) & set(predicted))
            recall_total += len(expected)
        for key in ("all", f"lang={record['lang']}", f"type={record['type']}"):
            group = groups[key]
            group["count"] += 1
            group["primary_correct"] += primary
            group["full_correct"] += full
        detected = record.get("detected_language")
        if detected:
            detected_count += 1
            language_correct += detected == record["lang"]
        latencies.append(float(record["latency_ms"]))

    rendered_groups = {}
    for key, group in sorted(groups.items()):
        count = group["count"]
        rendered_groups[key] = {
            "count": count,
            "primary_accuracy": round(group["primary_correct"] / count, 4),
            "full_match": round(group["full_correct"] / count, 4),
        }
    count = len(records)
    return {
        "groups": rendered_groups,
        "ordered_full_match": round(ordered_correct / count, 4) if count else None,
        "multi_intent_recall": round(recall_hit / recall_total, 4) if recall_total else None,
        "language_detection_accuracy": (
            round(language_correct / detected_count, 4) if detected_count else None
        ),
        "latency_ms": {
            "min": round(min(latencies), 1) if latencies else None,
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "max": round(max(latencies), 1) if latencies else None,
        },
    }


def build_report(
    records: list[dict], model: str, reasoning_effort: str | None, fingerprint: str
) -> dict:
    input_tokens = sum(record.get("input_tokens", 0) for record in records)
    output_tokens = sum(record.get("output_tokens", 0) for record in records)
    cached_tokens = sum(record.get("cached_tokens", 0) for record in records)
    cache_write_tokens = sum(record.get("cache_write_tokens", 0) for record in records)
    return {
        "suite": "official-dev-v1",
        "model": model,
        "reasoning_effort": reasoning_effort,
        "evaluation_fingerprint": fingerprint,
        "count": len(records),
        "api_errors": sum("error_type" in record for record in records),
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_tokens": cached_tokens,
            "cache_write_tokens": cache_write_tokens,
            "cache_hit_ratio": round(cached_tokens / input_tokens, 4) if input_tokens else 0.0,
            "estimated_uncached_cost_upper_bound": estimate_cost(
                model, input_tokens, output_tokens
            ),
        },
        "metrics": score_records(records),
        "errors": [
            {key: record.get(key) for key in (
                "id", "text", "lang", "type", "expected", "predicted", "error_type", "error"
            ) if record.get(key) is not None}
            for record in records
            if set(record.get("predicted", [])) != set(record["expected"])
        ],
        "records": records,
    }


def _write_progress(args, report: dict, selected: list[dict]) -> None:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.predictions.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    by_id = {record["id"]: record.get("predicted", []) for record in report["records"]}
    predictions = {item["id"]: by_id[item["id"]] for item in selected if item["id"] in by_id}
    args.predictions.write_text(
        json.dumps(predictions, ensure_ascii=False, indent=2), encoding="utf-8"
    )


async def run_official(args, settings: LiveSettings) -> dict:
    if not args.live:
        raise SystemExit("Refusing paid calls: pass --live explicitly")
    if not settings.openai_api_key:
        raise SystemExit("OPENAI_API_KEY is missing from .env")
    if not settings.openai_router_model:
        raise SystemExit("OPENAI_ROUTER_MODEL is missing from .env")

    selected = json.loads(DEV_PATH.read_text(encoding="utf-8"))["utterances"][:args.max_items]
    catalog = load_catalog(CATALOG_PATH)
    provider = OpenAIRouterProvider(
        model=settings.openai_router_model,
        api_key=settings.openai_api_key.get_secret_value(),
        reasoning_effort=settings.openai_router_reasoning_effort,
        max_output_tokens=600,
        prompt_cache_key="saqta-router-v1",
    )
    fingerprint = evaluation_fingerprint(
        catalog, settings.openai_router_model, settings.openai_router_reasoning_effort
    )
    records_by_id = {}
    if args.resume and args.output.exists():
        previous = json.loads(args.output.read_text(encoding="utf-8"))
        if previous.get("evaluation_fingerprint") != fingerprint:
            raise SystemExit("Cannot resume: model, prompt, catalog or schema changed")
        allowed = {item["id"] for item in selected}
        records_by_id = {
            record["id"]: record for record in previous.get("records", [])
            if record.get("id") in allowed and "error_type" not in record
        }

    semaphore = asyncio.Semaphore(args.concurrency)

    async def route_one(item: dict) -> dict:
        async with semaphore:
            started = perf_counter()
            base = {key: item[key] for key in ("id", "text", "lang", "type", "expected")}
            try:
                detailed = await provider.route_detailed(
                    RouterContext(text=item["text"], language=item["lang"]), catalog
                )
                usage = detailed.usage
                return base | {
                    "predicted": detailed.result.decision.scenario_ids,
                    "detected_language": detailed.detected_language,
                    "language_components": list(detailed.language_components),
                    "certainty": detailed.result.decision.certainty,
                    "rationale": detailed.result.decision.rationale,
                    "latency_ms": round((perf_counter() - started) * 1000, 1),
                    "input_tokens": _usage_value(usage, "input_tokens"),
                    "output_tokens": _usage_value(usage, "output_tokens"),
                    "cached_tokens": _usage_detail_value(usage, "cached_tokens"),
                    "cache_write_tokens": _usage_detail_value(usage, "cache_write_tokens"),
                }
            except Exception as exc:
                return base | {
                    "predicted": [],
                    "latency_ms": round((perf_counter() - started) * 1000, 1),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }

    pending = [
        asyncio.create_task(route_one(item)) for item in selected
        if item["id"] not in records_by_id
    ]
    for completed in asyncio.as_completed(pending):
        record = await completed
        records_by_id[record["id"]] = record
        ordered = [records_by_id[item["id"]] for item in selected if item["id"] in records_by_id]
        _write_progress(
            args,
            build_report(
                ordered,
                settings.openai_router_model,
                settings.openai_router_reasoning_effort,
                fingerprint,
            ),
            selected,
        )

    records = [records_by_id[item["id"]] for item in selected]
    report = build_report(
        records,
        settings.openai_router_model,
        settings.openai_router_reasoning_effort,
        fingerprint,
    )
    _write_progress(args, report, selected)
    return report


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = asyncio.run(run_official(args, LiveSettings()))
    summary = {
        "suite": report["suite"],
        "model": report["model"],
        "count": report["count"],
        "api_errors": report["api_errors"],
        "usage": report["usage"],
        "metrics": report["metrics"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Predictions: {args.predictions.resolve()}")
    print(f"Detailed report: {args.output.resolve()}")
    return 2 if report["api_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
