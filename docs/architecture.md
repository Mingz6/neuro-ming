# Architecture

## Overview (M1-M2: Current)

```
Browser  →  FastAPI (web/app.py)  →  LLM wrapper (core/llm.py)  →  Azure OpenAI (GPT-5.4)
                  ↕                        ↕
            Jinja2 templates       Personality prompt (core/personality.py)
            Static files           Memory (core/memory.py)
                  ↕
            TTS wrapper (core/tts.py)  →  Azure OpenAI TTS (oai-mingz-tts)
                  ↕
            Audio response (base64 mp3 in JSON)
```

## Target Architecture (M3-M4: WebSocket Voice + Workers)

```
┌─────────────────────────────────────────────────────────┐
│             Browser (push-to-talk)                    │
│  MediaRecorder → WebSocket /ws/voice                  │
└──────────────────────────┬──────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  audio_router.py (WebSocket server)                   │
│  Binary audio in → STT → LLM → TTS → Binary audio out │
└───────┬────────────────┬───────────────┬───────────────┘
        │                │               │
        ▼                ▼               ▼
  core/stt.py      core/llm.py      core/tts.py
  (Deepgram /      (GPT-5.4)        (Azure TTS)
   Azure / Whisper)
```

**Key decisions (2026-05-21):**
- **No Pipecat for M3.** Browser audio via WebSocket + raw STT is simpler. Pipecat evaluated for future desktop build.
- **Tend patterns ported, not framework.** Hub/Worker architecture inspired by Tend, implemented with plain asyncio.
- **M4 workers** use Claude CLI subprocess (subscription billing, not API tokens).
- **Future: OpenAI Realtime API** — replace STT+LLM+TTS with single S2S model (~300ms latency).

## Current Components (M1-M2)

## Current Components (M1-M2)

| Module | Responsibility |
|--------|---------------|
| `core/personality.py` | Character definition — real Ming persona as system prompt |
| `core/llm.py` | Async multi-provider LLM wrapper — 6 providers, single `chat()` function |
| `core/tts.py` | Async TTS wrapper — Azure OpenAI, returns base64-encoded mp3 |
| `core/memory.py` | In-memory conversation history (sliding window, 20 msgs) |
| `core/stt.py` | Async STT wrapper — Deepgram (primary), Azure Speech (fallback), Whisper (offline) |
| `web/audio_router.py` | WebSocket `/ws/voice` endpoint — real-time voice conversation |
| `web/app.py` | FastAPI server, routes, input validation (4k char limit) |
| `web/templates/` | Jinja2 HTML templates |
| `web/static/` | CSS + JS for the chat UI |

## Planned Components (M4)

| Module | Responsibility |
|--------|---------------|
| `core/bus.py` | Minimal asyncio.Queue task bus (enqueue, on_complete, subscribe) |
| `workers/claude_cli.py` | Claude CLI subprocess worker (subscription billing) |
| `core/announcer.py` | Proactive TTS announcer (cooldown, defer-while-active) |
| `core/tools/` | Tool functions exposed to the LLM (email, calendar, etc.) |

## Migration Strategy

M3-M4 does NOT delete M1-M2 code. Instead:
1. The web chat UI (`/chat`) keeps working as-is (text + TTS via HTTP)
2. `/ws/voice` WebSocket endpoint handles real-time voice (STT → LLM → TTS)
3. `core/personality.py` is shared — same persona drives both text and voice
4. `core/llm.py` is shared — same chat function serves both HTTP and WS paths
5. M4 adds async workers that announce results via TTS even when user is idle

## Reference Implementation

- **tend** (`~/code/playground/tend`): Desktop voice assistant with Hub/Brain/Worker pattern
  - Architectural inspiration for M4 workers (ported patterns, not the Pipecat framework)
  - OpenWakeWordGate concept for future privacy boundary
  - ProactiveAnnouncer for unprompted updates
  - Claude CLI subprocess billing trick (subscription, not API tokens)
  - 47 source files, 61 test files, 8.5/10 quality score
