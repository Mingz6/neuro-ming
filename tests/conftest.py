"""Shared fixtures. No test here touches the network or a real API key."""

import pytest

ENV_VARS = [
    "LLM_PROVIDER", "MODEL_NAME", "LLM_FALLBACK_MODELS",
    "OPENAI_API_KEY", "GROQ_API_KEY", "TOGETHER_API_KEY", "OPENROUTER_API_KEY",
    "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT",
    "TTS_ENABLED", "TTS_API_KEY", "TTS_ENDPOINT", "TTS_DEPLOYMENT", "TTS_VOICE", "TTS_FORMAT",
    "STT_ENABLED", "STT_PROVIDER", "DEEPGRAM_API_KEY",
    "AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION",
    "WHISPER_CMD", "WHISPER_MODEL", "FFMPEG_CMD",
    "CORS_ORIGINS", "AI_COST_LOG_DIR",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    """Start every test with no provider config, and keep cost logs out of the repo."""
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    from core import ai_cost_log, llm, tts

    monkeypatch.setattr(ai_cost_log, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(llm, "_client", None)
    monkeypatch.setattr(tts, "_tts_client", None)
