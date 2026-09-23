"""Bounded, interleaved A/B latency and quality comparison; paid calls require --live."""

import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter

from backend.router.catalog import load_catalog
from backend.router.evals.official import _percentile, _usage_detail_value
from backend.router.evals.run import LiveSettings, ROOT, _usage_value, estimate_cost
from backend.router.providers.openai_provider import OpenAIRouterProvider
from contracts.models import RouterContext


PROFILES = {"baseline": ("low", False), "none": ("none", False),
            "compact": ("none", True), "compact_low": ("low", True),
            "terse": ("low", False)}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--profiles", nargs="+", choices=tuple(PROFILES),
                        default=["baseline", "none", "compact"])
    parser.add_argument("--repeats", type=int, choices=range(1, 4), default=1)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/router-performance.json")
    return parser.parse_args(argv)


def summarize(records):
    summary = {}
    for profile in dict.fromkeys(row["profile"] for row in records):
        rows = [row for row in records if row["profile"] == profile and not row["warmup"]]
        successes = [row for row in rows if "error" not in row]
        values = [row["latency_ms"] for row in successes]
        summary[profile] = {
            "count": len(rows), "api_errors": len(rows) - len(successes),
            "ordered_correct": sum(row.get("predicted") == row["expected"] for row in rows),
            "language_correct": sum(row.get("language") == row["expected_language"] for row in rows),
            "p50_ms": _percentile(values, .5), "p95_ms": _percentile(values, .95),
            "mean_output_tokens": round(sum(row.get("output_tokens", 0) for row in successes)
                                        / len(successes), 1) if successes else None,
        }
    return summary


def quality_exit_code(records):
    """An HTTP-successful but wrong route/language must not pass the evaluation."""
    if any("error" in row for row in records):
        return 2
    measured = [row for row in records if not row["warmup"]]
    if not measured or any(
        row.get("predicted") != row["expected"]
        or row.get("language") != row["expected_language"] for row in measured
    ):
        return 1
    return 0


async def run(args):
    if not args.live:
        raise SystemExit("Refusing paid calls without --live")
    settings = LiveSettings()
    if not settings.openai_api_key:
        raise SystemExit("OPENAI_API_KEY is required")
    catalog = load_catalog(ROOT / "case_2/voice_router_dataset/scenarios.json")
    cases = []
    for name in ("smoke_utterances.json", "holdout_utterances.json"):
        cases.extend(json.loads(Path(__file__).with_name(name).read_text(encoding="utf-8"))["utterances"])
    profiles = list(dict.fromkeys(args.profiles))
    providers = {name: OpenAIRouterProvider(
        model=settings.openai_router_model, api_key=settings.openai_api_key.get_secret_value(),
        reasoning_effort=PROFILES[name][0], compact_output=PROFILES[name][1],
        text_verbosity="low" if name == "terse" else None,
        max_output_tokens=600, timeout_seconds=12, prompt_cache_key="saqta-router-v1",
    ) for name in profiles}
    records = []
    max_calls = len(profiles) * (1 + args.repeats * len(cases))
    print(f"Bounded run: at most {max_calls} router calls, serial, no retries", flush=True)

    async def one(name, item, warmup=False):
        started = perf_counter()
        row = {"profile": name, "id": item["id"], "warmup": warmup,
               "expected": item["expected"], "expected_language": item["lang"]}
        try:
            result = await providers[name].route_detailed(
                RouterContext(text=item["text"], language="auto"), catalog)
            row.update(predicted=result.result.decision.scenario_ids,
                       language=result.detected_language,
                       input_tokens=_usage_value(result.usage, "input_tokens"),
                       output_tokens=_usage_value(result.usage, "output_tokens"),
                       cached_tokens=_usage_detail_value(result.usage, "cached_tokens"))
        except Exception as exc:
            row["error"] = type(exc).__name__
            row["error_message"] = str(exc)
            row["cause_type"] = type(exc.__cause__).__name__ if exc.__cause__ else None
        row["latency_ms"] = round((perf_counter() - started) * 1000, 1)
        records.append(row)
        report = {"model": settings.openai_router_model, "max_calls": max_calls,
                  "summary": summarize(records), "records": records,
                  "note": "One excluded warmup per profile; interleaved serial calls; language hint auto (no ground-truth hint); not a load test.",
                  "estimated_cost": estimate_cost(settings.openai_router_model,
                      sum(r.get("input_tokens", 0) for r in records),
                      sum(r.get("output_tokens", 0) for r in records))}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{name} {item['id']}: {row['latency_ms']} ms "
              f"{'warmup' if warmup else row.get('predicted', row.get('error'))}", flush=True)

    try:
        for name in profiles:
            await one(name, cases[0], warmup=True)
        for repeat in range(args.repeats):
            for index, item in enumerate(cases):
                shift = (index + repeat) % len(profiles)
                for name in profiles[shift:] + profiles[:shift]:
                    await one(name, item)
    finally:
        for provider in providers.values():
            await provider.client.close()
    print(json.dumps(summarize(records), indent=2))
    return quality_exit_code(records)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
