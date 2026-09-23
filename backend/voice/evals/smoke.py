"""Explicitly bounded, paid audio loopback: TTS -> STT -> LLM router."""

import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.router.catalog import load_catalog
from backend.router.providers.openai_provider import OpenAIRouterProvider
from backend.voice.stt import OpenAITranscriber
from backend.voice.tts import OpenAISynthesizer
from contracts.models import RouterContext


ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "case_2/voice_router_dataset/scenarios.json"
CASES = (
    {"id": "ru", "text": "Хочу узнать, действует ли мой полис.", "expected": ["SC25"]},
    {"id": "kk", "text": "Менің сақтандыру полисім әлі жарамды ма?", "expected": ["SC25"]},
    {
        "id": "mixed",
        "text": "Сәлем, полисімді тексеріңізші, and I need to change my phone number.",
        "expected": ["SC25", "SC29"],
    },
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    openai_api_key: SecretStr | None = None
    openai_router_model: str | None = None
    openai_router_reasoning_effort: str | None = "low"
    openai_stt_model: str = "gpt-4o-mini-transcribe"
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "marin"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run at most three paid audio loopbacks")
    parser.add_argument("--live", action="store_true", help="required for API calls")
    parser.add_argument("--max-items", type=int, default=1, choices=range(1, 4))
    parser.add_argument("--case", choices=("ru", "kk", "mixed"),
                        help="run exactly one language case")
    parser.add_argument("--reuse-audio", action="store_true",
                        help="transcribe an existing generated MP3 without a new TTS call")
    parser.add_argument("--stt-model", type=str, default=None,
                        help="explicit model override for a bounded comparison")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/voice-smoke.json")
    return parser.parse_args(argv)


def _usage_json(usage):
    if usage is None:
        return None
    if isinstance(usage, dict):
        return usage
    if hasattr(usage, "model_dump"):
        return usage.model_dump(mode="json")
    return None


async def run(args, settings: Settings) -> dict:
    if not args.live:
        raise SystemExit("Refusing paid calls: pass --live explicitly")
    if not settings.openai_api_key:
        raise SystemExit("OPENAI_API_KEY is missing from .env")
    if not settings.openai_router_model:
        raise SystemExit("OPENAI_ROUTER_MODEL is missing from .env")

    key = settings.openai_api_key.get_secret_value()
    tts = OpenAISynthesizer(model=settings.openai_tts_model, api_key=key,
                            voice=settings.openai_tts_voice)
    stt_model = args.stt_model or settings.openai_stt_model
    stt = OpenAITranscriber(model=stt_model, api_key=key)
    router = OpenAIRouterProvider(model=settings.openai_router_model, api_key=key,
                                  reasoning_effort=settings.openai_router_reasoning_effort,
                                  prompt_cache_key="saqta-router-v1", max_output_tokens=600)
    catalog = load_catalog(CATALOG_PATH)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    records = []
    cases = [case for case in CASES if case["id"] == args.case] if args.case else CASES[:args.max_items]
    for case in cases:
        record = {"id": case["id"], "source_text": case["text"],
                  "expected": case["expected"]}
        try:
            audio_path = args.output.parent / f"voice-smoke-{case['id']}.mp3"
            if args.reuse_audio:
                audio = audio_path.read_bytes()
                record["reused_audio"] = True
            else:
                speech = await tts.synthesize(case["text"], language=case["id"])
                audio = speech.audio
                audio_path.write_bytes(audio)
                record.update({"tts_first_byte_ms": speech.tts_first_byte_ms,
                               "tts_total_ms": speech.tts_total_ms})
            record.update({"audio_file": str(audio_path.resolve()),
                           "audio_bytes": len(audio)})

            transcript = await stt.transcribe(
                audio, filename=audio_path.name, language_hint=case["id"]
            )
            record.update({"transcript": transcript.text,
                           "stt_language": transcript.language,
                           "stt_detected_languages": list(transcript.detected_languages),
                           "stt_ms": transcript.stt_ms,
                           "stt_usage": _usage_json(transcript.usage)})

            route_started = perf_counter()
            detailed = await router.route_detailed(
                RouterContext(text=transcript.text, language="auto"), catalog
            )
            record.update({"predicted": detailed.result.decision.scenario_ids,
                           "route_passed": detailed.result.decision.scenario_ids == case["expected"],
                           "router_ms": round((perf_counter() - route_started) * 1000, 1),
                           "router_language": detailed.detected_language,
                           "router_language_components": list(detailed.language_components),
                           "router_usage": _usage_json(detailed.usage)})
        except Exception as exc:
            record.update({"route_passed": False, "error_type": type(exc).__name__,
                           "error": str(exc)})
        records.append(record)
        args.output.write_text(json.dumps({"records": records}, ensure_ascii=False, indent=2),
                               encoding="utf-8")
    return {
        "suite": "voice-loopback-v1", "count": len(records),
        "passed": sum(bool(record["route_passed"]) for record in records),
        "tts_model": settings.openai_tts_model,
        "stt_model": stt_model,
        "router_model": settings.openai_router_model,
        "records": records,
    }


def main(argv=None) -> int:
    args = parse_args(argv)
    report = asyncio.run(run(args, Settings()))
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"suite": report["suite"], "count": report["count"],
                      "passed": report["passed"], "report": str(args.output.resolve())},
                     ensure_ascii=False, indent=2))
    return 0 if report["passed"] == report["count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
