"""Speech generation adapter with measured first audio byte and complete MP3 output."""

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
        chunks: list[bytes] = []
        total_size = 0
        first_byte_ms: float | None = None
        try:
            async with self.client.audio.speech.with_streaming_response.create(**request) as response:
                async for chunk in response.iter_bytes():
                    if not chunk:
                        continue
                    if first_byte_ms is None:
                        first_byte_ms = round((perf_counter() - started) * 1000, 1)
                    total_size += len(chunk)
                    if total_size > MAX_OUTPUT_BYTES:
                        raise SpeechError("generated audio exceeds 10 MiB")
                    chunks.append(chunk)
        except SpeechError:
            raise
        except Exception as exc:
            raise SpeechError("OpenAI speech request failed") from exc
        if first_byte_ms is None:
            raise SpeechError("OpenAI speech returned no audio")
        return SpeechResult(
            audio=b"".join(chunks),
            content_type="audio/mpeg",
            tts_first_byte_ms=first_byte_ms,
            tts_total_ms=round((perf_counter() - started) * 1000, 1),
            model=self.model,
            voice=self.voice,
            input_characters=len(spoken),
            usage=None,
        )
