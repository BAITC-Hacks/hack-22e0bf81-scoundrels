"""One explicitly paid, bounded HTTP round trip using a local recording."""

import argparse
import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.platform.app import create_app
from backend.platform.config import ROOT, Settings


MIME = {".mp3": "audio/mpeg", ".webm": "audio/webm", ".wav": "audio/wav",
        ".ogg": "audio/ogg", ".m4a": "audio/mp4"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run exactly one paid STT→LLM→TTS HTTP smoke")
    parser.add_argument("--live", action="store_true", help="required to permit API calls")
    parser.add_argument("--audio", type=Path, required=True, help="existing recording, max 1 MiB")
    parser.add_argument("--stt-model", choices=("gpt-transcribe", "gpt-4o-mini-transcribe"),
                        help="override local STT setting for this one bounded run")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/live-http-smoke.json")
    args = parser.parse_args(argv)
    if not args.live:
        parser.error("refusing paid calls without --live")
    mime = MIME.get(args.audio.suffix.lower())
    if not mime:
        parser.error("audio must be .mp3, .webm, .wav, .ogg or .m4a")
    data = args.audio.read_bytes()
    if not 0 < len(data) <= 1024 * 1024:
        parser.error("audio must be 1 byte to 1 MiB")
    overrides = {"openai_stt_model": args.stt_model} if args.stt_model else {}
    app = create_app(Settings(app_mode="live", **overrides))
    with TestClient(app) as client:
        sid = client.post("/api/sessions").json()["session_id"]
        transcript = client.post("/api/voice/transcribe", files={
            "file": (args.audio.name, data, mime),
        })
        transcript.raise_for_status()
        turn = client.post(f"/api/sessions/{sid}/turns", json={
            "text": transcript.json()["text"], "language": transcript.json()["language"],
        })
        turn.raise_for_status()
        reply = turn.json()
        speech = client.post("/api/voice/synthesize", json={
            "text": reply["assistant_text"], "language": reply["language"],
        })
        speech.raise_for_status()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    audio_output = args.output.with_suffix(".mp3")
    audio_output.write_bytes(speech.content)
    report = {
        "transcript": transcript.json(),
        "decision": reply["decision"],
        "assistant_text": reply["assistant_text"],
        "language": reply["language"],
        "router_ms": reply["timings"]["router_ms"],
        "tts_first_byte_ms": float(speech.headers["x-tts-first-byte-ms"]),
        "tts_total_ms": float(speech.headers["x-tts-total-ms"]),
        "reply_audio": str(audio_output.resolve()),
        "reply_audio_bytes": len(speech.content),
        "note": "This is server HTTP timing, not microphone-to-speaker latency.",
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"scenario_ids": reply["decision"]["scenario_ids"],
                      "report": str(args.output.resolve())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
