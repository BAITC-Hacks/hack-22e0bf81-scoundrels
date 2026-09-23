"""File transcription adapter. HTTP upload limits and spend guard belong to platform."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePath
from time import perf_counter
from typing import Any

from openai import AsyncOpenAI


SUPPORTED_EXTENSIONS = frozenset({
    ".flac", ".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".ogg", ".wav", ".webm"
})
MAX_AUDIO_BYTES = 25 * 1024 * 1024


class TranscriptionError(RuntimeError):
    """A recording could not be transcribed."""


class TranscriptionConfigurationError(TranscriptionError):
    """The transcription adapter is not ready for live calls."""


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    language: str  # ru, kk, en, mixed, or auto when the model did not identify it
    detected_languages: tuple[str, ...]
    stt_ms: float
    usage: Any | None
    model: str


def _field(value: Any, name: str, default: Any = None) -> Any:
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def _detected_languages(response: Any) -> tuple[str, ...]:
    raw = _field(response, "languages") or []
    codes = [str(_field(item, "code", "")).lower() for item in raw]
    return tuple(dict.fromkeys(code for code in codes if code in {"ru", "kk", "en"}))


class OpenAITranscriber:
    def __init__(
        self,
        *,
        model: str | None,
        api_key: str | None = None,
        client: Any | None = None,
        timeout_seconds: float = 20.0,
        usage_callback: Callable[[Any], None] | None = None,
    ) -> None:
        if not model or not model.strip():
            raise TranscriptionConfigurationError("OPENAI_STT_MODEL must be configured")
        if timeout_seconds <= 0:
            raise TranscriptionConfigurationError("STT timeout must be positive")
        if client is None and not api_key:
            raise TranscriptionConfigurationError("OPENAI_API_KEY is required")
        self.model = model.strip()
        self.timeout_seconds = timeout_seconds
        self.usage_callback = usage_callback
        # A failed request may already be billable. The caller decides if another try is safe.
        self.client = client or AsyncOpenAI(api_key=api_key, max_retries=0)

    async def transcribe(
        self, audio: bytes, *, filename: str, language_hint: str = "auto"
    ) -> TranscriptionResult:
        if not audio or len(audio) > MAX_AUDIO_BYTES:
            raise TranscriptionError("audio must be nonempty and at most 25 MiB")
        safe_name = PurePath(filename).name
        if PurePath(safe_name).suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise TranscriptionError("unsupported audio file extension")
        if language_hint not in {"auto", "ru", "kk", "en", "mixed"}:
            raise TranscriptionError("unsupported language hint")

        request: dict[str, Any] = {
            "model": self.model,
            "file": (safe_name, audio),
            "response_format": "json",
            "timeout": self.timeout_seconds,
        }
        # A single-language hint helps the API. Mixed speech must remain unconstrained.
        if language_hint in {"ru", "kk", "en"}:
            request["language"] = language_hint
        elif language_hint == "mixed" and self.model == "gpt-transcribe":
            request["languages"] = ["kk", "ru", "en"]
        started = perf_counter()
        try:
            response = await self.client.audio.transcriptions.create(**request)
        except Exception as exc:
            raise TranscriptionError("OpenAI transcription request failed") from exc

        text = str(_field(response, "text", "") or "").strip()
        if not text:
            raise TranscriptionError("OpenAI transcription returned empty text")
        languages = _detected_languages(response)
        detected = "mixed" if len(languages) > 1 else languages[0] if languages else (
            language_hint if language_hint in {"ru", "kk", "en"} else "auto"
        )
        usage = _field(response, "usage")
        if self.usage_callback:
            self.usage_callback(usage)
        return TranscriptionResult(
            text=text,
            language=detected,
            detected_languages=languages,
            stt_ms=round((perf_counter() - started) * 1000, 1),
            usage=usage,
            model=self.model,
        )
