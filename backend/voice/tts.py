"""Speech generation adapter with measured first audio byte and complete MP3 output."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from openai import AsyncOpenAI


MAX_SPEECH_CHARACTERS = 2000
MAX_OUTPUT_BYTES = 10 * 1024 * 1024
VOICE_INSTRUCTIONS = {
    "ru": "Speak naturally in Russian, at a calm customer-support pace.",
    "kk": "Speak naturally in Kazakh, with clear Kazakh pronunciation and a calm pace.",
    "en": "Speak naturally in English, at a calm customer-support pace.",
    "mixed": "Preserve each language in the text. Pronounce Russian, Kazakh and English naturally.",
    "auto": "Speak naturally in the language of the text at a calm pace.",
}


class SpeechError(RuntimeError):
    """Speech generation did not produce usable audio."""


class SpeechConfigurationError(SpeechError):
    """The speech adapter is not ready for live calls."""


@dataclass(frozen=True)
class SpeechResult:
    audio: bytes
    content_type: str
    tts_first_byte_ms: float
    tts_total_ms: float
    model: str
    voice: str
    input_characters: int
    usage: Any | None  # The speech endpoint may not return usage; budget guard must reserve.


@dataclass(frozen=True)
class SpeechStream:
    chunks: AsyncIterator[bytes]
    tts_first_byte_ms: float
    started_at: float
    content_type: str = "audio/mpeg"


class OpenAISynthesizer:
    def __init__(
        self,
        *,
        model: str | None,
        api_key: str | None = None,
        client: Any | None = None,
        voice: str = "marin",
        timeout_seconds: float = 20.0,
    ) -> None:
        if not model or not model.strip():
            raise SpeechConfigurationError("OPENAI_TTS_MODEL must be configured")
        if client is None and not api_key:
            raise SpeechConfigurationError("OPENAI_API_KEY is required")
        if not voice or timeout_seconds <= 0:
            raise SpeechConfigurationError("voice and positive timeout are required")
        self.model = model.strip()
        self.voice = voice
        self.timeout_seconds = timeout_seconds
        self.client = client or AsyncOpenAI(api_key=api_key, max_retries=0)

    async def synthesize(self, text: str, *, language: str = "auto") -> SpeechResult:
        async with self.stream(text, language=language) as stream:
            chunks = [chunk async for chunk in stream.chunks]
            return SpeechResult(
                audio=b"".join(chunks), content_type=stream.content_type,
                tts_first_byte_ms=stream.tts_first_byte_ms,
                tts_total_ms=round((perf_counter() - stream.started_at) * 1000, 1),
                model=self.model, voice=self.voice, input_characters=len(text.strip()), usage=None,
            )

    @asynccontextmanager
    async def stream(self, text: str, *, language: str = "auto") -> AsyncIterator[SpeechStream]:
        """Keep provider open while the consumer plays chunks; close on cancellation too."""
        spoken = text.strip()
        if not spoken or len(spoken) > MAX_SPEECH_CHARACTERS:
            raise SpeechError("speech text must be 1..2000 characters")
        if language not in VOICE_INSTRUCTIONS:
            raise SpeechError("unsupported speech language")
        request = {
            "model": self.model,
            "voice": self.voice,
            "input": spoken,
            "response_format": "mp3",
            "timeout": self.timeout_seconds,
        }
        if self.model not in {"tts-1", "tts-1-hd"}:
            request["instructions"] = VOICE_INSTRUCTIONS[language]

        started = perf_counter()
        try:
            async with self.client.audio.speech.with_streaming_response.create(**request) as response:
                iterator = response.iter_bytes().__aiter__()
                first = b""
                async for chunk in iterator:
                    if not chunk:
                        continue
                    first = chunk
                    break
                if not first:
                    raise SpeechError("OpenAI speech returned no audio")
                if len(first) > MAX_OUTPUT_BYTES:
                    raise SpeechError("generated audio exceeds 10 MiB")

                async def chunks():
                    total_size = len(first)
                    yield first
                    try:
                        async for part in iterator:
                            if not part:
                                continue
                            total_size += len(part)
                            if total_size > MAX_OUTPUT_BYTES:
                                raise SpeechError("generated audio exceeds 10 MiB")
                            yield part
                    except SpeechError:
                        raise
                    except Exception as exc:
                        raise SpeechError("OpenAI speech stream failed") from exc

                yield SpeechStream(
                    chunks=chunks(), tts_first_byte_ms=round((perf_counter() - started) * 1000, 1),
                    started_at=started,
                )
        except SpeechError:
            raise
        except Exception as exc:
            raise SpeechError("OpenAI speech request failed") from exc
