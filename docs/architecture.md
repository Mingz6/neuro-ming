# Architecture

## Overview (M1-M2: Current)

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

## Target Architecture (M3-M4: Pipecat)

```
┌─────────────────────────────────────────────────────────┐
│                    Pipecat Pipeline                       │
│                                                          │
│  Mic → Silero VAD → Deepgram STT → LLM → TTS → Speaker │
│              │                        │                   │
│              │                   Tool calls               │
│              │                        │                   │
│              │                        ▼                   │
│              │              pipecat-subagents             │
│              │              ┌─────────────────┐          │
│              │              │  Worker 1 (Opus) │          │
│              │              │  Worker 2 (Opus) │          │
│              │              │  Worker N        │          │
│              │              └────────┬─────────┘          │
│              │                       │                    │
│              │               Shared Message Bus           │
│              │                       │                    │
│              │                       ▼                    │
│              │              Announce via TTS              │
│              └──── Interruption handling (auto)           │
└─────────────────────────────────────────────────────────┘
         │                                      │
    Local Transport                     WebSocket Transport
    (desktop mic/speaker)              (browser / web UI)
```

**Key decisions:**
- **Pipecat** as the pipeline framework (12.3K⭐, BSD, proven by tend repo)
- **pipecat-subagents** for the worker pattern (Hub → Brain → Workers)
- **Local Transport** for M3-M4 desktop mode
- **WebSocket Transport** to keep the web chat UI working
- **Future: OpenAI Realtime API** — replace STT+LLM+TTS with single S2S model (~300ms latency)
- **Future: Twilio Serializer** — same pipeline makes phone calls (Pharness use case)

## Current Components (M1-M2)

## Current Components (M1-M2)

| Module | Responsibility |
|--------|---------------|
| `core/personality.py` | Character definition — real Ming persona as system prompt |
| `core/llm.py` | Async multi-provider LLM wrapper — 6 providers, single `chat()` function |
| `core/tts.py` | Async TTS wrapper — Azure OpenAI, returns base64-encoded mp3 |
| `core/memory.py` | In-memory conversation history (sliding window, 20 msgs) |
| `web/app.py` | FastAPI server, routes, input validation (4k char limit) |
| `web/templates/` | Jinja2 HTML templates |
| `web/static/` | CSS + JS for the chat UI |

## Planned Components (M3-M4)

| Module | Responsibility |
|--------|---------------|
| `core/voice_pipeline.py` | Pipecat pipeline definition (STT → LLM → TTS + VAD) |
| `core/transports/local.py` | Local mic/speaker transport (desktop mode) |
| `core/transports/websocket.py` | WebSocket transport (browser mode) |
| `core/workers/` | pipecat-subagents worker definitions |
| `core/tools/` | Tool functions exposed to the LLM (email, calendar, etc.) |

## Migration Strategy

M3-M4 does NOT delete M1-M2 code. Instead:
1. The web chat UI (`/chat`) keeps working as-is (text + TTS via HTTP)
2. A new `/voice` endpoint starts a Pipecat WebSocket session for browser voice
3. A new CLI mode (`python -m core.voice_pipeline`) runs desktop voice locally
4. `core/personality.py` is shared — same persona drives both text and voice
5. `core/llm.py` stays for the web chat path; Pipecat uses its own LLM processor for voice

## Reference Implementation

- **tend** (`~/code/playground/tend`): Pipecat + pipecat-subagents desktop voice assistant
  - Hub (audio owner) → Brain (LLM routing) → Workers (tool execution)
  - OpenWakeWordGate for privacy boundary
  - ProactiveAnnouncer for unprompted updates
  - 47 source files, 61 test files, 8.5/10 quality score
