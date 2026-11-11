import asyncio
import json
import os
import shutil
import stat
import subprocess
import textwrap

import httpx
import pytest

from core import stt

WEBM_BYTES = b"\x1a\x45\xdf\xa3 pretend webm/opus from MediaRecorder"
WAV_BYTES = b"RIFF\x24\x00\x00\x00WAVEfmt pretend pcm"


def use_mock_http(monkeypatch, handler):
    """Route every httpx.AsyncClient the module builds through a fake transport."""
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        return real(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(stt.httpx, "AsyncClient", factory)


def write_script(path, body):
    path.write_text("#!/bin/sh\n" + textwrap.dedent(body))
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


# --- provider selection ---

def test_default_provider_is_deepgram():
    assert stt._get_provider() == stt.STTProvider.DEEPGRAM


@pytest.mark.parametrize("raw, expected", [
    ("azure", stt.STTProvider.AZURE),
    ("WHISPER", stt.STTProvider.WHISPER),
    ("Deepgram", stt.STTProvider.DEEPGRAM),
])
def test_provider_is_read_from_env(monkeypatch, raw, expected):
    monkeypatch.setenv("STT_PROVIDER", raw)
    assert stt._get_provider() == expected


def test_unknown_provider_falls_back_to_deepgram(monkeypatch):
    monkeypatch.setenv("STT_PROVIDER", "carrier-pigeon")
    assert stt._get_provider() == stt.STTProvider.DEEPGRAM


@pytest.mark.parametrize("value, expected", [("true", True), ("1", True), ("false", False), ("", False)])
def test_is_enabled(monkeypatch, value, expected):
    monkeypatch.setenv("STT_ENABLED", value)
    assert stt.is_enabled() is expected


# --- transcribe_once routing ---

@pytest.fixture
def fake_providers(monkeypatch):
    """Replace the three backends with recorders so only the routing is under test."""
    seen: dict[str, bytes] = {}

    def make(name):
        async def fake(audio: bytes):
            seen[name] = audio
            return f"{name} heard you"
        return fake

    monkeypatch.setattr(stt, "_deepgram_transcribe", make("deepgram"))
    monkeypatch.setattr(stt, "_azure_transcribe", make("azure"))
    monkeypatch.setattr(stt, "_whisper_transcribe", make("whisper"))

    async def fake_wav(audio: bytes):
        return b"CONVERTED:" + audio

    monkeypatch.setattr(stt, "_to_wav16k", fake_wav)
    return seen


async def test_empty_audio_returns_none(fake_providers):
    assert await stt.transcribe_once(b"") is None
    assert fake_providers == {}


async def test_deepgram_gets_the_raw_browser_audio(fake_providers):
    assert await stt.transcribe_once(WEBM_BYTES) == "deepgram heard you"
    assert fake_providers == {"deepgram": WEBM_BYTES}


@pytest.mark.parametrize("provider", ["azure", "whisper"])
async def test_wav_only_providers_get_converted_audio(monkeypatch, fake_providers, provider):
    monkeypatch.setenv("STT_PROVIDER", provider)
    assert await stt.transcribe_once(WEBM_BYTES) == f"{provider} heard you"
    assert fake_providers == {provider: b"CONVERTED:" + WEBM_BYTES}


async def test_failed_conversion_means_no_transcript(monkeypatch, fake_providers):
    async def broken(_audio):
        return None

    monkeypatch.setattr(stt, "_to_wav16k", broken)
    monkeypatch.setenv("STT_PROVIDER", "whisper")
    assert await stt.transcribe_once(WEBM_BYTES) is None
    assert fake_providers == {}


# --- transcribe_stream ---

async def chunks(*parts):
    for part in parts:
        yield part


async def test_non_streaming_provider_buffers_then_transcribes_once(monkeypatch):
    received = []

    async def fake_once(audio):
        received.append(audio)
        return "whole buffer"

    monkeypatch.setattr(stt, "transcribe_once", fake_once)
    monkeypatch.setenv("STT_PROVIDER", "whisper")
    out = [text async for text in stt.transcribe_stream(chunks(b"ab", b"cd", b"ef"))]
    assert out == ["whole buffer"]
    assert received == [b"abcdef"]


async def test_non_streaming_provider_with_no_audio_yields_nothing(monkeypatch):
    monkeypatch.setenv("STT_PROVIDER", "azure")
    assert [text async for text in stt.transcribe_stream(chunks())] == []


async def test_deepgram_stream_is_used_for_deepgram(monkeypatch):
    async def fake_stream(audio_stream):
        async for _ in audio_stream:
            pass
        yield "live words"

    monkeypatch.setattr(stt, "_deepgram_stream", fake_stream)
    out = [text async for text in stt.transcribe_stream(chunks(b"x"))]
    assert out == ["live words"]


# --- Deepgram REST ---

def deepgram_body(transcript):
    return {"results": {"channels": [{"alternatives": [{"transcript": transcript}]}]}}


async def test_deepgram_sends_audio_with_the_token_and_parses_the_transcript(monkeypatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-test")
    seen = {}

    def handler(request: httpx.Request):
        seen["auth"] = request.headers["authorization"]
        seen["body"] = request.content
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=deepgram_body("  what are you working on  "))

    use_mock_http(monkeypatch, handler)
    assert await stt.transcribe_once(WEBM_BYTES) == "what are you working on"
    assert seen["auth"] == "Token dg-test"
    assert seen["body"] == WEBM_BYTES
    assert seen["params"]["model"] == "nova-3-general"


async def test_deepgram_without_a_key_returns_none(monkeypatch):
    use_mock_http(monkeypatch, lambda r: pytest.fail("no request should be made"))
    assert await stt.transcribe_once(WEBM_BYTES) is None


async def test_deepgram_blank_transcript_is_none(monkeypatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-test")
    use_mock_http(monkeypatch, lambda r: httpx.Response(200, json=deepgram_body("   ")))
    assert await stt.transcribe_once(WEBM_BYTES) is None


async def test_deepgram_http_error_is_none(monkeypatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-test")
    use_mock_http(monkeypatch, lambda r: httpx.Response(401, json={"err": "bad key"}))
    assert await stt.transcribe_once(WEBM_BYTES) is None


# --- Azure Speech REST ---

async def test_azure_posts_wav_to_the_regional_endpoint(monkeypatch):
    monkeypatch.setenv("STT_PROVIDER", "azure")
    monkeypatch.setenv("AZURE_SPEECH_KEY", "az-test")
    monkeypatch.setenv("AZURE_SPEECH_REGION", "westus")
    seen = {}

    def handler(request: httpx.Request):
        seen["host"] = request.url.host
        seen["key"] = request.headers["ocp-apim-subscription-key"]
        seen["body"] = request.content
        return httpx.Response(200, json={"RecognitionStatus": "Success", "DisplayText": "Hello there. "})

    use_mock_http(monkeypatch, handler)
    assert await stt.transcribe_once(WAV_BYTES) == "Hello there."
    assert seen == {"host": "westus.stt.speech.microsoft.com", "key": "az-test", "body": WAV_BYTES}


async def test_azure_no_match_is_none(monkeypatch):
    monkeypatch.setenv("STT_PROVIDER", "azure")
    monkeypatch.setenv("AZURE_SPEECH_KEY", "az-test")
    use_mock_http(monkeypatch, lambda r: httpx.Response(200, json={"RecognitionStatus": "NoMatch"}))
    assert await stt.transcribe_once(WAV_BYTES) is None


async def test_azure_without_a_key_returns_none(monkeypatch):
    monkeypatch.setenv("STT_PROVIDER", "azure")
    assert await stt.transcribe_once(WAV_BYTES) is None


# --- Whisper CLI (a shell script plays whisper.cpp) ---

async def test_whisper_returns_the_cli_stdout(monkeypatch, tmp_path):
    cmd = write_script(tmp_path / "whisper", """\
        echo "  hello from whisper  "
    """)
    monkeypatch.setenv("STT_PROVIDER", "whisper")
    monkeypatch.setenv("WHISPER_CMD", cmd)
    assert await stt.transcribe_once(WAV_BYTES) == "hello from whisper"


async def test_whisper_gets_the_wav_file_and_model_and_cleans_up(monkeypatch, tmp_path):
    record = tmp_path / "args.txt"
    cmd = write_script(tmp_path / "whisper", f"""\
        echo "$@" > {record}
        head -c 4 "$4" > {tmp_path}/head.txt
        echo ok
    """)
    monkeypatch.setenv("STT_PROVIDER", "whisper")
    monkeypatch.setenv("WHISPER_CMD", cmd)
    monkeypatch.setenv("WHISPER_MODEL", "/models/base.en.bin")
    await stt.transcribe_once(WAV_BYTES)
    args = record.read_text().split()
    assert args[:2] == ["-m", "/models/base.en.bin"]
    assert args[2] == "-f"
    assert (tmp_path / "head.txt").read_text() == "RIFF"
    assert not os.path.exists(args[3]), "temp wav should be deleted"


async def test_whisper_nonzero_exit_is_none(monkeypatch, tmp_path):
    cmd = write_script(tmp_path / "whisper", "echo broken >&2\nexit 3\n")
    monkeypatch.setenv("STT_PROVIDER", "whisper")
    monkeypatch.setenv("WHISPER_CMD", cmd)
    assert await stt.transcribe_once(WAV_BYTES) is None


async def test_whisper_blank_output_is_none(monkeypatch, tmp_path):
    cmd = write_script(tmp_path / "whisper", "echo '   '\n")
    monkeypatch.setenv("STT_PROVIDER", "whisper")
    monkeypatch.setenv("WHISPER_CMD", cmd)
    assert await stt.transcribe_once(WAV_BYTES) is None


async def test_whisper_missing_binary_is_none(monkeypatch, tmp_path):
    monkeypatch.setenv("STT_PROVIDER", "whisper")
    monkeypatch.setenv("WHISPER_CMD", str(tmp_path / "does-not-exist"))
    assert await stt.transcribe_once(WAV_BYTES) is None


# --- browser audio to WAV ---

async def test_wav_input_skips_ffmpeg(monkeypatch, tmp_path):
    monkeypatch.setenv("FFMPEG_CMD", str(tmp_path / "must-not-run"))
    assert await stt._to_wav16k(WAV_BYTES) == WAV_BYTES


async def test_non_wav_input_goes_through_ffmpeg_at_16k_mono(monkeypatch, tmp_path):
    args_file = tmp_path / "ffmpeg-args.txt"
    cmd = write_script(tmp_path / "ffmpeg", f"""\
        echo "$@" > {args_file}
        for last; do :; done
        printf 'RIFF....WAVEfake' > "$last"
    """)
    monkeypatch.setenv("FFMPEG_CMD", cmd)
    out = await stt._to_wav16k(WEBM_BYTES)
    assert out == b"RIFF....WAVEfake"
    args = args_file.read_text()
    assert "-ar 16000" in args and "-ac 1" in args


async def test_ffmpeg_failure_returns_none(monkeypatch, tmp_path):
    cmd = write_script(tmp_path / "ffmpeg", "echo 'bad input' >&2\nexit 1\n")
    monkeypatch.setenv("FFMPEG_CMD", cmd)
    assert await stt._to_wav16k(WEBM_BYTES) is None


async def test_missing_ffmpeg_returns_none(monkeypatch, tmp_path):
    monkeypatch.setenv("FFMPEG_CMD", str(tmp_path / "does-not-exist"))
    assert await stt._to_wav16k(WEBM_BYTES) is None


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
async def test_real_ffmpeg_turns_opus_into_16k_mono_wav(tmp_path):
    src = tmp_path / "tone.webm"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
         "-c:a", "libopus", str(src)],
        check=True,
    )
    wav = await stt._to_wav16k(src.read_bytes())
    assert wav is not None and stt._is_wav(wav)
    out = tmp_path / "out.wav"
    out.write_bytes(wav)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=sample_rate,channels", "-of", "json", str(out)],
        capture_output=True, text=True, check=True,
    )
    stream = json.loads(probe.stdout)["streams"][0]
    assert (stream["sample_rate"], stream["channels"]) == ("16000", 1)


# --- Deepgram streaming, against a local stand-in for the Deepgram socket ---

async def test_deepgram_stream_sends_audio_and_yields_final_transcripts(monkeypatch):
    from websockets.asyncio.server import serve

    received = []
    headers = {}

    async def fake_deepgram(ws):
        headers["auth"] = ws.request.headers["Authorization"]
        async for msg in ws:
            if isinstance(msg, bytes):
                received.append(msg)
                continue
            if json.loads(msg).get("type") == "CloseStream":
                break
        for text, final in (("hel", False), ("hello there", True)):
            await ws.send(json.dumps({
                "type": "Results", "is_final": final,
                "channel": {"alternatives": [{"transcript": text}]},
            }))
        await ws.close()

    async with serve(fake_deepgram, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        monkeypatch.setattr(stt, "DEEPGRAM_WS_URL", f"ws://127.0.0.1:{port}")
        monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-test")
        out = [text async for text in stt.transcribe_stream(chunks(b"aa", b"bb"))]

    assert out == ["hello there"]
    assert b"".join(received) == b"aabb"
    assert headers["auth"] == "Token dg-test"


async def test_deepgram_stream_without_a_key_yields_nothing():
    assert [text async for text in stt.transcribe_stream(chunks(b"aa"))] == []
