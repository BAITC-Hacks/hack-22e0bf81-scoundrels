"""One paid saved-audio → STT → router → streamed-TTS loop against local live server."""

import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter

import httpx

from backend.platform.evals.live_smoke import MIME, ROOT


async def run(args):
    if not args.live:
        raise SystemExit("Refusing paid calls without --live")
    data = args.audio.read_bytes()
    mime = MIME.get(args.audio.suffix.lower())
    if not mime or not 0 < len(data) <= 1024 * 1024:
        raise SystemExit("Audio must have a supported format and be at most 1 MiB")
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=30) as client:
        session = await client.post("/api/sessions")
        session.raise_for_status()
        sid = session.json()["session_id"]
        headers = {"X-Session-ID": sid}
        started = perf_counter()
        stt = await client.post("/api/voice/transcribe", headers=headers,
                                files={"file": (args.audio.name, data, mime)})
        stt.raise_for_status()
        transcript = stt.json()
        turn = await client.post(f"/api/sessions/{sid}/turns", json={
            "text": transcript["text"], "language": transcript["language"]})
        turn.raise_for_status()
        reply = turn.json()
        first_byte_ms = None
        received = 0
        async with client.stream("POST", "/api/voice/synthesize/stream", headers=headers,
                                 json={"text": reply["assistant_text"], "language": reply["language"]}) as speech:
            speech.raise_for_status()
            async for chunk in speech.aiter_bytes():
                if chunk and first_byte_ms is None:
                    first_byte_ms = round((perf_counter() - started) * 1000, 1)
                received += len(chunk)
            tts_ms = float(speech.headers["x-tts-first-byte-ms"])
    report = {"scenario_ids": reply["decision"]["scenario_ids"], "language": reply["language"],
              "stt_ms": transcript["stt_ms"], "router_ms": reply["timings"]["router_ms"],
              "tts_first_byte_ms": tts_ms, "client_chain_first_audio_byte_ms": first_byte_ms,
              "client_chain_complete_ms": round((perf_counter() - started) * 1000, 1),
              "audio_bytes": received,
              "note": "Saved recording to first audio byte; excludes microphone and browser playback."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/stream-http-smoke.json")
    asyncio.run(run(parser.parse_args()))
