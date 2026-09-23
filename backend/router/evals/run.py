"""Generate v1 ordered predictions and run the unmodified official evaluator."""
import argparse
import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys

from contracts.models import RouterContext
from backend.router.catalog import load_catalog
from backend.router.prompting import DATASET
from backend.router.providers.openai_provider import OpenAIProvider, RouterProviderError
from backend.router.service import ScenarioRouter
from .budget import EvalBudget

ROUTER_ROOT = Path(__file__).resolve().parents[1]


def metrics(rows: list[dict], predictions: dict) -> dict:
    groups = defaultdict(list)
    for row in rows:
        for key in ("all", "lang=" + row["lang"], "type=" + row["type"]):
            groups[key].append(row)
    report = {}
    for key, entries in groups.items():
        primary = full = ordered = hits = total = 0
        for row in entries:
            got, expected = predictions.get(row["id"], []), row["expected"]
            primary += bool(got) and got[0] == expected[0]
            full += set(got) == set(expected)  # Matches official full_match semantics.
            ordered += got == expected
            if row["type"] == "multi_intent":
                hits += len(set(got) & set(expected))
                total += len(expected)
        report[key] = {"n": len(entries), "primary_accuracy": primary/len(entries),
                       "full_match": full/len(entries), "ordered_exact_match": ordered/len(entries),
                       "intent_recall": hits/total if total else None}
    return report


async def collect(router, catalog, rows: list[dict]) -> tuple[dict, list[dict], list[dict]]:
    predictions, timings, failures = {}, [], []
    for row in rows:
        # Gold labels/type never enter the router or prompt. Dev rows are independent sessions.
        context = RouterContext(text=row["text"], language="auto")
        try:
            trace = await router.route_with_trace(context, catalog)
        except (RouterProviderError, RuntimeError, ValueError) as exc:
            failures.append({"id": row["id"], "code": exc.code if isinstance(exc, RouterProviderError) else "evaluation_stopped"})
            break  # Don't spend on the rest of a broken configuration/provider.
        predictions[row["id"]] = trace.result.decision.scenario_ids
        timings.append({"id": row["id"], "router_ms": trace.router_ms,
                        "provider_ms": trace.provider_ms, "language": trace.language,
                        "attempts": trace.attempts,
                        "action": trace.result.decision.action,
                        "input_tokens": trace.usage.input_tokens if trace.usage else None,
                        "output_tokens": trace.usage.output_tokens if trace.usage else None,
                        "cached_input_tokens": trace.usage.cached_input_tokens if trace.usage else None,
                        "certainty": trace.result.decision.certainty})
    return predictions, timings, failures


def latency_summary(timings: list[dict]) -> dict:
    result = {}
    for key, rows in (("all", timings),
                      ("cached", [t for t in timings if (t["cached_input_tokens"] or 0) > 0]),
                      ("uncached", [t for t in timings if t["cached_input_tokens"] == 0])):
        values = sorted(t["router_ms"] for t in rows)
        result[key] = {"n": len(values), "p50_ms": statistics.median(values) if values else None,
                       "p95_ms": values[math.ceil(len(values)*0.95)-1] if values else None}
    return result


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--mode", choices=["scaffold", "live"], default="scaffold")
    result.add_argument("--dataset", type=Path, default=DATASET / "dev_utterances.json")
    result.add_argument("--output-dir", type=Path, default=ROUTER_ROOT / "artifacts" / "eval")
    result.add_argument("--limit", type=int, default=104)
    result.add_argument("--allow-paid", action="store_true")
    result.add_argument("--max-requests", type=int)
    result.add_argument("--max-usd", type=Decimal)
    result.add_argument("--input-usd-per-million", type=Decimal)
    result.add_argument("--cached-input-usd-per-million", type=Decimal)
    result.add_argument("--cache-write-usd-per-million", type=Decimal)
    result.add_argument("--output-usd-per-million", type=Decimal)
    return result


async def run(args) -> int:
    destination = args.output_dir.resolve()
    if not destination.is_relative_to(ROUTER_ROOT):
        raise ValueError("Evaluation outputs must stay inside backend/router")
    if args.limit < 1:
        raise ValueError("limit must be positive")
    rows = json.loads(args.dataset.read_text(encoding="utf-8"))["utterances"][:args.limit]
    if not rows or len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Dataset must contain unique nonempty rows")
    catalog = load_catalog(DATASET / "scenarios.json")
    provider, budget = None, None
    if args.mode == "live":
        rates = (args.input_usd_per_million, args.cached_input_usd_per_million,
                 args.cache_write_usd_per_million, args.output_usd_per_million)
        if not args.allow_paid or any(v is None for v in (args.max_requests, args.max_usd, *rates)):
            raise ValueError("Live requires paid opt-in, request/USD caps and all four token rates")
        budget = EvalBudget(max_usd=args.max_usd, input_rate=args.input_usd_per_million,
                            cached_input_rate=args.cached_input_usd_per_million,
                            cache_write_rate=args.cache_write_usd_per_million,
                            output_rate=args.output_usd_per_million, max_calls=args.max_requests)
        # Only the explicit live CLI loads local secrets. Never prints them.
        from dotenv import load_dotenv
        load_dotenv(ROUTER_ROOT.parents[1] / ".env", override=False)
        provider = OpenAIProvider.from_env(budget=budget)
    router = ScenarioRouter(provider, mode=args.mode)
    try:
        predictions, timings, failures = await collect(router, catalog, rows)
    finally:
        if provider is not None:
            await provider.aclose()
    destination.mkdir(parents=True, exist_ok=True)
    report = {
        "mode": args.mode, "is_real_llm_evaluation": args.mode == "live",
        "notice": "LIVE" if args.mode == "live" else "SCAFFOLD PIPELINE CHECK ONLY; NOT LLM QUALITY",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": provider.settings.model if provider else None,
        "planned": len(rows), "completed": len(predictions), "failures": failures,
        "api_calls": budget.calls if budget else 0,
        "charged_or_reserved_usd": str(budget.charged_or_reserved) if budget else "0",
        "metrics": metrics(rows, predictions),
        "abstention_rate": sum(t["action"] in {"clarify", "transfer"} for t in timings)/len(timings) if timings else None,
        "latency": latency_summary(timings),
        "median_router_ms": statistics.median(t["router_ms"] for t in timings) if timings else None,
        "median_provider_ms": statistics.median(t["provider_ms"] for t in timings if t["provider_ms"] is not None)
            if any(t["provider_ms"] is not None for t in timings) else None,
        "hashes": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in {
            "dataset": args.dataset, "catalog": DATASET / "scenarios.json",
            "prompt": ROUTER_ROOT / "prompts" / "router.md", "schema": ROUTER_ROOT / "schemas.py"}.items()},
        "errors": [{"id": r["id"], "expected": r["expected"], "got": predictions.get(r["id"], [])}
                   for r in rows if predictions.get(r["id"], []) != r["expected"]],
    }
    for name, value in (("predictions.json", predictions), ("report.json", report),
                        ("timings.json", timings), ("evaluated_dataset.json", {"utterances": rows})):
        (destination / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    official = subprocess.run([sys.executable, str(DATASET / "evaluate.py"), str(destination / "predictions.json"),
                               str(destination / "evaluated_dataset.json")], capture_output=True, encoding="utf-8",
                              env={**os.environ, "PYTHONIOENCODING": "utf-8"}, check=True)
    (destination / "official_metrics.txt").write_text(report["notice"] + "\n" + official.stdout, encoding="utf-8")
    print(json.dumps({"mode": args.mode, "completed": len(predictions), "planned": len(rows),
                      "failures": failures, "output_dir": str(destination)}, ensure_ascii=False))
    return 2 if failures else 0


def main():
    args = parser().parse_args()
    try:
        return asyncio.run(run(args))
    except (ValueError, RuntimeError) as exc:
        # Configuration errors contain no SDK response or key values.
        print(f"Evaluation configuration error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
