import base64
import logging
import os

from openai import AsyncAzureOpenAI, APIError, APIConnectionError

logger = logging.getLogger(__name__)

MAX_TTS_CHARS = 4096

_tts_client: AsyncAzureOpenAI | None = None


def _get_tts_client() -> AsyncAzureOpenAI:
    """TTS uses its own Azure OpenAI resource (separate from the chat LLM)."""
    global _tts_client
    if _tts_client is None:
        api_key = os.getenv("TTS_API_KEY", "")
        endpoint = os.getenv("TTS_ENDPOINT", "")
        if not api_key or not endpoint:
            raise RuntimeError("TTS_API_KEY and TTS_ENDPOINT must be set for TTS")
        _tts_client = AsyncAzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version="2025-01-01-preview",
        )
    return _tts_client


def is_enabled() -> bool:
    return os.getenv("TTS_ENABLED", "false").lower() in ("true", "1", "yes")


async def synthesize(text: str) -> str | None:
    """Convert text to speech, return base64-encoded audio or None on failure."""
    if not text:
        return None

    model = os.getenv("TTS_DEPLOYMENT", "tts")
    voice = os.getenv("TTS_VOICE", "nova")
    fmt = os.getenv("TTS_FORMAT", "mp3")

    # OpenAI TTS caps at 4096 chars
    if len(text) > MAX_TTS_CHARS:
        logger.warning("TTS text truncated from %d to %d chars", len(text), MAX_TTS_CHARS)
        text = text[:MAX_TTS_CHARS]

    try:
        client = _get_tts_client()
        response = await client.audio.speech.create(
            model=model,
            voice=voice,
            input=text,
            response_format=fmt,
        )
        audio_bytes = response.content
        return base64.b64encode(audio_bytes).decode("ascii")
    except (APIError, APIConnectionError):
        return None
    except Exception:
        return None
