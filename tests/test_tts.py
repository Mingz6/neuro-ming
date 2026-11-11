import base64
from types import SimpleNamespace

import httpx
import pytest
from openai import APIConnectionError, AsyncAzureOpenAI

from core import tts


class FakeSpeech:
    def __init__(self, result=b"ID3-fake-mp3"):
        self.result = result
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return SimpleNamespace(content=self.result)


def install_fake(monkeypatch, result=b"ID3-fake-mp3"):
    speech = FakeSpeech(result)
    monkeypatch.setattr(tts, "_tts_client", SimpleNamespace(audio=SimpleNamespace(speech=speech)))
    return speech


@pytest.mark.parametrize("value, expected", [("true", True), ("1", True), ("YES", True), ("false", False), ("", False)])
def test_is_enabled(monkeypatch, value, expected):
    monkeypatch.setenv("TTS_ENABLED", value)
    assert tts.is_enabled() is expected


def test_disabled_by_default():
    assert tts.is_enabled() is False


def test_client_needs_key_and_endpoint():
    with pytest.raises(RuntimeError, match="TTS_API_KEY and TTS_ENDPOINT"):
        tts._get_tts_client()


def test_client_is_azure_and_cached(monkeypatch):
    monkeypatch.setenv("TTS_API_KEY", "k")
    monkeypatch.setenv("TTS_ENDPOINT", "https://example.invalid")
    client = tts._get_tts_client()
    assert isinstance(client, AsyncAzureOpenAI)
    assert tts._get_tts_client() is client


async def test_synthesize_returns_base64_audio(monkeypatch):
    speech = install_fake(monkeypatch, b"mp3-bytes")
    out = await tts.synthesize("hello")
    assert base64.b64decode(out) == b"mp3-bytes"
    assert speech.calls == [
        {"model": "tts", "voice": "nova", "input": "hello", "response_format": "mp3"}
    ]


async def test_synthesize_reads_voice_settings_from_env(monkeypatch):
    speech = install_fake(monkeypatch)
    monkeypatch.setenv("TTS_DEPLOYMENT", "my-tts")
    monkeypatch.setenv("TTS_VOICE", "alloy")
    monkeypatch.setenv("TTS_FORMAT", "wav")
    await tts.synthesize("hi")
    assert speech.calls[0]["model"] == "my-tts"
    assert speech.calls[0]["voice"] == "alloy"
    assert speech.calls[0]["response_format"] == "wav"


async def test_empty_text_skips_the_api(monkeypatch):
    speech = install_fake(monkeypatch)
    assert await tts.synthesize("") is None
    assert speech.calls == []


async def test_long_text_is_cut_to_the_api_limit(monkeypatch):
    speech = install_fake(monkeypatch)
    await tts.synthesize("x" * (tts.MAX_TTS_CHARS + 100))
    assert len(speech.calls[0]["input"]) == tts.MAX_TTS_CHARS


async def test_api_failure_returns_none(monkeypatch):
    request = httpx.Request("POST", "https://example.invalid")
    install_fake(monkeypatch, APIConnectionError(request=request))
    assert await tts.synthesize("hello") is None


async def test_missing_config_returns_none():
    assert await tts.synthesize("hello") is None
