import asyncio
from types import SimpleNamespace

import pytest

from backend.voice.stt import OpenAITranscriber, TranscriptionError
from backend.voice.tts import OpenAISynthesizer, SpeechError


class FakeTranscriptions:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


class FakeSpeechStream:
    def __init__(self, chunks):
        self.chunks = chunks

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def iter_bytes(self):
        for chunk in self.chunks:
            yield chunk


class FakeSpeech:
    def __init__(self, chunks):
        self.chunks = chunks
        self.calls = []
        self.with_streaming_response = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeSpeechStream(self.chunks)


def test_transcription_preserves_detected_multilingual_text_and_usage():
    usage = {"input_tokens": 17}
    endpoint = FakeTranscriptions({
        "text": "Сәлем, нужно проверить policy.",
        "languages": [{"code": "kk"}, {"code": "ru"}, {"code": "en"}],
        "usage": usage,
    })
    seen = []
    adapter = OpenAITranscriber(
        model="gpt-transcribe",
        client=SimpleNamespace(audio=SimpleNamespace(transcriptions=endpoint)),
        usage_callback=seen.append,
    )
    result = asyncio.run(adapter.transcribe(b"audio", filename="utterance.webm", language_hint="mixed"))
    assert result.text == "Сәлем, нужно проверить policy."
    assert result.language == "mixed"
    assert result.detected_languages == ("kk", "ru", "en")
    assert result.stt_ms >= 0
    assert seen == [usage]
    assert endpoint.calls[0]["file"] == ("utterance.webm", b"audio")
    assert "language" not in endpoint.calls[0]
    assert endpoint.calls[0]["languages"] == ["kk", "ru", "en"]


def test_single_language_hint_is_passed_and_missing_detection_is_not_fabricated():
    endpoint = FakeTranscriptions(SimpleNamespace(text="Привет", usage=None))
    adapter = OpenAITranscriber(
        model="gpt-4o-mini-transcribe",
        client=SimpleNamespace(audio=SimpleNamespace(transcriptions=endpoint)),
    )
    result = asyncio.run(adapter.transcribe(b"audio", filename="voice.wav", language_hint="ru"))
    assert result.language == "ru"
    assert result.detected_languages == ()
    assert endpoint.calls[0]["language"] == "ru"


def test_mini_transcribe_does_not_receive_unsupported_multilanguage_parameter():
    endpoint = FakeTranscriptions({"text": "Сәлем, hello"})
    adapter = OpenAITranscriber(
        model="gpt-4o-mini-transcribe",
        client=SimpleNamespace(audio=SimpleNamespace(transcriptions=endpoint)),
    )
    result = asyncio.run(adapter.transcribe(b"audio", filename="voice.webm", language_hint="mixed"))
    assert result.text == "Сәлем, hello"
    assert result.language == "auto"
    assert "languages" not in endpoint.calls[0]
    assert "language" not in endpoint.calls[0]


def test_transcription_rejects_invalid_audio_and_keeps_provider_error_generic():
    endpoint = FakeTranscriptions(error=TimeoutError("secret transport detail"))
    adapter = OpenAITranscriber(
        model="gpt-transcribe",
        client=SimpleNamespace(audio=SimpleNamespace(transcriptions=endpoint)),
    )
    with pytest.raises(TranscriptionError, match="nonempty"):
        asyncio.run(adapter.transcribe(b"", filename="voice.wav"))
    with pytest.raises(TranscriptionError, match="extension"):
        asyncio.run(adapter.transcribe(b"audio", filename="voice.exe"))
    with pytest.raises(TranscriptionError, match="request failed") as exc:
        asyncio.run(adapter.transcribe(b"audio", filename="voice.wav"))
    assert "secret transport detail" not in str(exc.value)


def test_speech_stream_returns_mp3_with_first_byte_and_total_latency():
    endpoint = FakeSpeech([b"", b"first", b"last"])
    adapter = OpenAISynthesizer(
        model="gpt-4o-mini-tts", voice="marin",
        client=SimpleNamespace(audio=SimpleNamespace(speech=endpoint)),
    )
    result = asyncio.run(adapter.synthesize("Сәлем!", language="kk"))
    assert result.audio == b"firstlast"
    assert result.content_type == "audio/mpeg"
    assert 0 <= result.tts_first_byte_ms <= result.tts_total_ms
    assert result.usage is None
    assert "Kazakh" in endpoint.calls[0]["instructions"]


def test_speech_rejects_blank_and_empty_audio():
    endpoint = FakeSpeech([])
    adapter = OpenAISynthesizer(
        model="tts-1", client=SimpleNamespace(audio=SimpleNamespace(speech=endpoint)),
    )
    with pytest.raises(SpeechError, match="1..2000"):
        asyncio.run(adapter.synthesize("  "))
    with pytest.raises(SpeechError, match="no audio"):
        asyncio.run(adapter.synthesize("Hello"))
    assert "instructions" not in endpoint.calls[0]
