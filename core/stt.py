"""Speech-to-text module — Deepgram primary, Azure fallback, Whisper offline."""

import asyncio
import base64
import json
import logging
import os
from collections.abc import AsyncIterator
from enum import StrEnum

import httpx

logger = logging.getLogger(__name__)


class STTProvider(StrEnum):
    DEEPGRAM = "deepgram"
    AZURE = "azure"
    WHISPER = "whisper"


def _get_provider() -> STTProvider:
    raw = os.getenv("STT_PROVIDER", "deepgram").lower()
    try:
        return STTProvider(raw)
    except ValueError:
        logger.warning("Unknown STT_PROVIDER '%s', defaulting to deepgram", raw)
        return STTProvider.DEEPGRAM


def is_enabled() -> bool:
    return os.getenv("STT_ENABLED", "false").lower() in ("true", "1", "yes")


async def transcribe_once(audio_bytes: bytes) -> str | None:
    """Transcribe a complete audio buffer. Returns transcript text or None on failure."""
    if not audio_bytes:
        return None

    provider = _get_provider()
    if provider == STTProvider.DEEPGRAM:
        return await _deepgram_transcribe(audio_bytes)
    elif provider == STTProvider.AZURE:
        return await _azure_transcribe(audio_bytes)
    elif provider == STTProvider.WHISPER:
        return await _whisper_transcribe(audio_bytes)
    return None


async def transcribe_stream(audio_stream: AsyncIterator[bytes]) -> AsyncIterator[str]:
    """Stream audio chunks, yield interim/final transcripts. Deepgram only."""
    provider = _get_provider()
    if provider == STTProvider.DEEPGRAM:
        async for text in _deepgram_stream(audio_stream):
            yield text
    else:
        # Non-streaming fallback: buffer all audio, transcribe once
        buffer = bytearray()
        async for chunk in audio_stream:
            buffer.extend(chunk)
        if buffer:
            result = await transcribe_once(bytes(buffer))
            if result:
                yield result


# --- Deepgram ---

DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"
DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"


async def _deepgram_transcribe(audio_bytes: bytes) -> str | None:
    """Deepgram REST API for single-shot transcription."""
    api_key = os.getenv("DEEPGRAM_API_KEY", "")
    if not api_key:
        logger.error("DEEPGRAM_API_KEY not set")
        return None

    params = {
        "model": "nova-3-general",
        "language": "en",
        "punctuate": "true",
        "smart_format": "true",
    }
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": "audio/webm",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                DEEPGRAM_URL,
                params=params,
                headers=headers,
                content=audio_bytes,
            )
            resp.raise_for_status()
            data = resp.json()
            transcript = (
                data.get("results", {})
                .get("channels", [{}])[0]
                .get("alternatives", [{}])[0]
                .get("transcript", "")
            )
            return transcript.strip() or None
    except (httpx.HTTPError, KeyError, IndexError) as e:
        logger.warning("Deepgram transcription failed: %s", e)
        return None


async def _deepgram_stream(audio_stream: AsyncIterator[bytes]) -> AsyncIterator[str]:
    """Deepgram WebSocket streaming STT with interim results."""
    import websockets

    api_key = os.getenv("DEEPGRAM_API_KEY", "")
    if not api_key:
        logger.error("DEEPGRAM_API_KEY not set for streaming")
        return

    params = (
        "?model=nova-3-general"
        "&language=en"
        "&punctuate=true"
        "&interim_results=true"
        "&endpointing=300"
        "&smart_format=true"
        "&encoding=linear16"
        "&sample_rate=16000"
        "&channels=1"
    )
    url = DEEPGRAM_WS_URL + params
    headers = {"Authorization": f"Token {api_key}"}

    try:
        async with websockets.connect(url, additional_headers=headers) as ws:
            # Send audio in a background task
            async def send_audio():
                async for chunk in audio_stream:
                    await ws.send(chunk)
                # Signal end of audio
                await ws.send(json.dumps({"type": "CloseStream"}))

            send_task = asyncio.create_task(send_audio())

            try:
                async for msg in ws:
                    data = json.loads(msg)
                    if data.get("type") == "Results":
                        transcript = (
                            data.get("channel", {})
                            .get("alternatives", [{}])[0]
                            .get("transcript", "")
                        )
                        is_final = data.get("is_final", False)
                        if transcript.strip() and is_final:
                            yield transcript.strip()
            finally:
                send_task.cancel()
                try:
                    await send_task
                except asyncio.CancelledError:
                    pass
    except Exception as e:
        logger.warning("Deepgram streaming failed: %s", e)


# --- Azure Speech ---

async def _azure_transcribe(audio_bytes: bytes) -> str | None:
    """Azure Speech-to-Text REST API (single-shot)."""
    speech_key = os.getenv("AZURE_SPEECH_KEY", "")
    speech_region = os.getenv("AZURE_SPEECH_REGION", "canadacentral")
    if not speech_key:
        logger.error("AZURE_SPEECH_KEY not set")
        return None

    url = (
        f"https://{speech_region}.stt.speech.microsoft.com"
        f"/speech/recognition/conversation/cognitiveservices/v1"
        f"?language=en-US"
    )
    headers = {
        "Ocp-Apim-Subscription-Key": speech_key,
        "Content-Type": "audio/wav; codecs=audio/pcm; samplerate=16000",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, content=audio_bytes)
            resp.raise_for_status()
            data = resp.json()
            if data.get("RecognitionStatus") == "Success":
                return data.get("DisplayText", "").strip() or None
            return None
    except (httpx.HTTPError, KeyError) as e:
        logger.warning("Azure STT failed: %s", e)
        return None


# --- Whisper (local via whisper.cpp or openai-whisper) ---

async def _whisper_transcribe(audio_bytes: bytes) -> str | None:
    """Local Whisper transcription via whisper.cpp CLI."""
    import tempfile

    whisper_cmd = os.getenv("WHISPER_CMD", "whisper-cpp")
    model_path = os.getenv("WHISPER_MODEL", "")

    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name

        cmd = [whisper_cmd, "-m", model_path, "-f", tmp_path, "--no-timestamps", "-l", "en"]
        if not model_path:
            cmd = [whisper_cmd, "-f", tmp_path, "--no-timestamps", "-l", "en"]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60.0)

        if proc.returncode != 0:
            logger.warning("Whisper failed (rc=%d): %s", proc.returncode, stderr.decode()[:200])
            return None

        transcript = stdout.decode().strip()
        return transcript or None
    except (FileNotFoundError, asyncio.TimeoutError) as e:
        logger.warning("Whisper transcription failed: %s", e)
        return None
    finally:
        import os as _os
        try:
            _os.unlink(tmp_path)
        except (OSError, UnboundLocalError):
            pass
