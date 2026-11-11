"""Speech-to-text. STT_PROVIDER picks one of Deepgram (default), Azure Speech or offline Whisper."""

import asyncio
import json
import logging
import os
import tempfile
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
    # Azure's REST endpoint and whisper.cpp only read WAV. The browser records
    # webm/opus, so convert first. Deepgram sniffs the container itself.
    wav = await _to_wav16k(audio_bytes)
    if wav is None:
        return None
    if provider == STTProvider.AZURE:
        return await _azure_transcribe(wav)
    return await _whisper_transcribe(wav)


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


# --- Audio conversion ---

def _is_wav(audio_bytes: bytes) -> bool:
    return audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE"


async def _to_wav16k(audio_bytes: bytes) -> bytes | None:
    """Return 16 kHz mono PCM WAV. WAV input passes through; anything else goes through ffmpeg."""
    if _is_wav(audio_bytes):
        return audio_bytes

    ffmpeg_cmd = os.getenv("FFMPEG_CMD", "ffmpeg")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in.bin")
            dst = os.path.join(tmp, "out.wav")
            with open(src, "wb") as f:
                f.write(audio_bytes)
            proc = await asyncio.create_subprocess_exec(
                ffmpeg_cmd, "-loglevel", "error", "-y", "-i", src,
                "-ar", "16000", "-ac", "1", "-f", "wav", dst,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            if proc.returncode != 0:
                logger.warning("ffmpeg failed (rc=%d): %s", proc.returncode, stderr.decode()[:200])
                return None
            with open(dst, "rb") as f:
                return f.read() or None
    except (FileNotFoundError, asyncio.TimeoutError, OSError) as e:
        logger.warning("Could not convert audio to WAV (is ffmpeg installed?): %s", e)
        return None


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
    from websockets.asyncio.client import connect

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
        async with connect(url, additional_headers=headers) as ws:
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

async def _whisper_transcribe(wav_bytes: bytes) -> str | None:
    """Local Whisper transcription via whisper.cpp CLI. Expects 16 kHz mono WAV."""
    whisper_cmd = os.getenv("WHISPER_CMD", "whisper-cpp")
    model_path = os.getenv("WHISPER_MODEL", "")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_bytes)
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
            logger.warning("Whisper failed (rc=%d): %s", proc.returncode, stderr.decode()[-200:])
            return None

        transcript = stdout.decode().strip()
        return transcript or None
    except (FileNotFoundError, asyncio.TimeoutError) as e:
        logger.warning("Whisper transcription failed: %s", e)
        return None
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
