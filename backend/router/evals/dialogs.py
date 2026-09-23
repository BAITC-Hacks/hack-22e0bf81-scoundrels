"""Bounded live replay of the ten labeled multi-turn sample dialogs."""
import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter

from backend.router.catalog import load_catalog
from backend.router.evals.official import _bounded_int, _percentile, _usage_detail_value
from backend.router.evals.run import LiveSettings, _usage_value, estimate_cost
from backend.router.providers.openai_provider import OpenAIRouterProvider
from backend.router.service import ScenarioRouter
from contracts.models import RouterContext, TurnRecord


ROOT = Path(__file__).resolve().parents[3]
DIALOGS_PATH = ROOT / "case_2/voice_router_dataset/dialogs_sample.json"
CATALOG_PATH = ROOT / "case_2/voice_router_dataset/scenarios.json"


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Replay bounded paid multi-turn dialog evals")
    parser.add_argument("--live", action="store_true", help="required to allow API calls")
    parser.add_argument(
        "--max-dialogs", type=_bounded_int(10), default=3,
        help="number of dialogs (1..10); full replay must explicitly pass 10",
    )
    parser.add_argument(
        "--dialog-id", action="append",
        choices=tuple(f"D{number:02}" for number in range(1, 11)),
        help="run one or more exact dialogs; may be repeated",
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "artifacts/router-dialogs-report.json",
    )
    return parser.parse_args(argv)


def score_records(records: list[dict]) -> dict:
    count = len(records)
    expected_slots = sum(len(record.get("expected_slot_names", [])) for record in records)
    slot_hits = sum(
        len(set(record.get("expected_slot_names", [])) & set(record.get("predicted_slot_names", [])))
        for record in records
    )
    latencies = [float(record["latency_ms"]) for record in records]
    return {
        "turns": count,
        "route_exact_match": round(
            sum(record.get("predicted") == record.get("expected") for record in records) / count,
            4,
        ) if count else None,
        "primary_accuracy": round(
            sum(
                bool(record.get("predicted"))
                and record["predicted"][0] == record["expected"][0]
                for record in records
            ) / count,
            4,
        ) if count else None,
        "slot_name_recall": round(slot_hits / expected_slots, 4) if expected_slots else None,
        "expected_slots": expected_slots,
        "slot_name_hits": slot_hits,
        "language_detection_accuracy": round(
            sum(record.get("detected_language") == record.get("lang") for record in records) / count,
            4,
        ) if count else None,
        "latency_ms": {
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "max": round(max(latencies), 1) if latencies else None,
        },
    }


def build_report(records: list[dict], dialogs: list[dict], model: str) -> dict:
    input_tokens = sum(record.get("input_tokens", 0) for record in records)
    output_tokens = sum(record.get("output_tokens", 0) for record in records)
    cached_tokens = sum(record.get("cached_tokens", 0) for record in records)
    return {
        "suite": "sample-dialogs-v1",
        "model": model,
        "dialogs": len(dialogs),
        "expected_client_turns": sum(
            sum(turn["role"] == "client" for turn in dialog["turns"]) for dialog in dialogs
        ),
        "api_errors": sum("error_type" in record for record in records),
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_tokens": cached_tokens,
            "cache_hit_ratio": round(cached_tokens / input_tokens, 4) if input_tokens else 0.0,
            "estimated_uncached_cost_upper_bound": estimate_cost(
                model, input_tokens, output_tokens
            ),
        },
        "metrics": score_records(records),
        "errors": [
            record for record in records
            if record.get("predicted") != record.get("expected") or "error_type" in record
        ],
        "records": records,
    }


def _write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


class RecordingProvider:
    """Expose internal language/usage data while ScenarioRouter applies topic state."""

    def __init__(self, provider: OpenAIRouterProvider):
        self.provider = provider
        self.last = None

    async def route(self, context, catalog):
        self.last = await self.provider.route_detailed(context, catalog)
        return self.last.result


async def run_dialogs(args, settings: LiveSettings) -> dict:
    if not args.live:
        raise SystemExit("Refusing paid calls: pass --live explicitly")
    if not settings.openai_api_key:
        raise SystemExit("OPENAI_API_KEY is missing from .env")
    if not settings.openai_router_model:
        raise SystemExit("OPENAI_ROUTER_MODEL is missing from .env")

    all_dialogs = json.loads(DIALOGS_PATH.read_text(encoding="utf-8"))["dialogs"]
    if args.dialog_id:
        selected_ids = set(args.dialog_id)
        dialogs = [dialog for dialog in all_dialogs if dialog["dialog_id"] in selected_ids]
    else:
        dialogs = all_dialogs[:args.max_dialogs]
    catalog = load_catalog(CATALOG_PATH)
    recording = RecordingProvider(OpenAIRouterProvider(
        model=settings.openai_router_model,
        api_key=settings.openai_api_key.get_secret_value(),
        reasoning_effort=settings.openai_router_reasoning_effort,
        max_output_tokens=600,
        prompt_cache_key="saqta-router-v1",
    ))
    router = ScenarioRouter(provider=recording)
    records = []

    for dialog in dialogs:
        history = []
        topics = []
        turns = dialog["turns"]
        for index, turn in enumerate(turns):
            if turn["role"] != "client":
                continue
            started = perf_counter()
            base = {
                "dialog_id": dialog["dialog_id"],
                "title": dialog["title"],
                "turn_index": index,
                "text": turn["text"],
                "lang": turn["lang"],
                "expected": turn["scenarios"],
                "expected_slot_names": list(turn.get("slots", {})),
            }
            try:
                routed = await router.route(
                    RouterContext(
                        text=turn["text"], language=turn["lang"],
                        history=history, topics=topics,
                    ),
                    catalog,
                )
                detailed = recording.last
                usage = detailed.usage
                predicted_slots = {slot.name: slot.value for slot in routed.decision.slots}
                active_count = sum(topic.status == "active" for topic in routed.topics)
                record = base | {
                    "predicted": routed.decision.scenario_ids,
                    "predicted_slots": predicted_slots,
                    "predicted_slot_names": list(predicted_slots),
                    "detected_language": detailed.detected_language,
                    "language_components": list(detailed.language_components),
                    "raw_topic_operation": detailed.result.decision.topic_operation,
                    "applied_topic_operation": routed.decision.topic_operation,
                    "rationale": routed.decision.rationale,
                    "clarification_question": routed.decision.clarification_question,
                    "topics": [topic.model_dump(mode="json") for topic in routed.topics],
                    "topic_invariant_ok": active_count <= 1,
                    "latency_ms": round((perf_counter() - started) * 1000, 1),
                    "input_tokens": _usage_value(usage, "input_tokens"),
                    "output_tokens": _usage_value(usage, "output_tokens"),
                    "cached_tokens": _usage_detail_value(usage, "cached_tokens"),
                }
                topics = routed.topics
                bot_text = ""
                if index + 1 < len(turns) and turns[index + 1]["role"] == "bot":
                    bot_text = turns[index + 1]["text"]
                history.append(TurnRecord(
                    user_text=turn["text"], assistant_text=bot_text,
                    decision=routed.decision,
                ))
                records.append(record)
            except Exception as exc:
                records.append(base | {
                    "predicted": [],
                    "predicted_slot_names": [],
                    "latency_ms": round((perf_counter() - started) * 1000, 1),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                })
                # Later turns depend on the missing decision; continue with the next dialog.
                break
            _write_report(args.output, build_report(records, dialogs, settings.openai_router_model))

    report = build_report(records, dialogs, settings.openai_router_model)
    _write_report(args.output, report)
    return report


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = asyncio.run(run_dialogs(args, LiveSettings()))
    print(json.dumps({key: report[key] for key in (
        "suite", "model", "dialogs", "expected_client_turns", "api_errors", "usage", "metrics",
    )}, ensure_ascii=False, indent=2))
    print(f"Detailed report: {args.output.resolve()}")
    return 2 if report["api_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
