# Architecture

## Overview

```
Browser  →  FastAPI (web/app.py)  →  LLM wrapper (core/llm.py)  →  Azure OpenAI (GPT-5.2)
                  ↕                        ↕
            Jinja2 templates       Personality prompt (core/personality.py)
            Static files           Memory (core/memory.py)
                  ↕
            TTS wrapper (core/tts.py)  →  Azure OpenAI TTS (oai-mingz-tts)
                  ↕
            Audio response (base64 mp3 in JSON)
```

All LLM and TTS calls are async so the event loop stays unblocked.

## Why FastAPI

- Async out of the box — ready for WebSocket support in M2+ (streaming TTS)
- Fast and lightweight, minimal boilerplate
- Built-in request validation via Pydantic

## Why OpenAI API First

- Fastest path to a working chatbot — no GPU setup, no model downloads
- Switch to local models (Ollama, vLLM) later without changing the interface
- `core/llm.py` is the only file that talks to OpenAI — easy to swap

## Components

| Module | Responsibility |
|--------|---------------|
| `core/personality.py` | Character definition — real Ming persona as system prompt |
| `core/llm.py` | Async multi-provider LLM wrapper — 6 providers, single `chat()` function |
| `core/tts.py` | Async TTS wrapper — Azure OpenAI, returns base64-encoded mp3 |
| `core/memory.py` | In-memory conversation history (sliding window, 20 msgs) |
| `web/app.py` | FastAPI server, routes, input validation (4k char limit) |
| `web/templates/` | Jinja2 HTML templates |
| `web/static/` | CSS + JS for the chat UI |
