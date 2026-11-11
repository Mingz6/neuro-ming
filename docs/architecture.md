# Architecture

The README has the diagrams. This page records how the pieces fit and what each module owns.

## Today (M1 to M3)

```
Text:   Browser  →  POST /chat  →  web/app.py  →  core/memory.py  →  core/llm.py  →  LLM provider
                                        ↓                                (persona from core/personality.py)
                                   core/tts.py  →  Azure OpenAI TTS  →  base64 mp3 in the JSON reply

Voice:  Browser mic (webm/opus)  →  WebSocket /ws/voice  →  web/audio_router.py
            buffer until "stop"  →  core/stt.py  →  core/memory.py + core/llm.py  →  core/tts.py
            →  transcript, reply text, mp3 in 16 KB frames, audio_end
```

Both routes share one `SessionStore`, so a typed question and a spoken follow-up land in the same conversation.

## Next (M4): workers

```
Browser (push-to-talk)  →  /ws/voice  →  STT  →  fast shell  →  TTS
                                                      │
                                              do_task() tool call
                                                      ↓
                                      asyncio.Queue  →  Claude CLI worker
                                                      ↓
                                      announcer  →  TTS, even if the user is silent
```

**Key decisions (2026-05-21):**
- **No Pipecat for M3.** Browser audio via WebSocket + raw STT is simpler. Pipecat evaluated for future desktop build.
- **Tend patterns ported, not framework.** Hub/Worker architecture inspired by Tend, implemented with plain asyncio.
- **M4 workers** use Claude CLI subprocess (subscription billing, not API tokens).
- **Future: OpenAI Realtime API** — replace STT+LLM+TTS with single S2S model (~300ms latency).

## Current Components (M1-M3)

| Module | Responsibility |
|--------|---------------|
| `core/personality.py` | Character definition — real Ming persona as system prompt |
| `core/llm.py` | Async multi-provider LLM wrapper — 6 providers, single `chat()` function |
| `core/tts.py` | Async TTS wrapper — Azure OpenAI, returns base64-encoded mp3 |
| `core/memory.py` | In-memory conversation history (sliding window, 20 msgs) |
| `core/stt.py` | Async STT wrapper. `STT_PROVIDER` picks Deepgram (default), Azure Speech or Whisper (offline). Azure and Whisper get WAV from `ffmpeg` |
| `web/audio_router.py` | WebSocket `/ws/voice` endpoint, one turn per start/stop pair |
| `web/app.py` | FastAPI server, routes, input validation (4k char limit) |
| `web/templates/` | Jinja2 HTML templates |
| `tests/` | pytest suite, no network, no API keys |
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

- **tend** (a local checkout, not in this repo): Desktop voice assistant with Hub/Brain/Worker pattern
  - Architectural inspiration for M4 workers (ported patterns, not the Pipecat framework)
  - OpenWakeWordGate concept for future privacy boundary
  - ProactiveAnnouncer for unprompted updates
  - Claude CLI subprocess billing trick (subscription, not API tokens)
  - 47 source files, 61 test files, 8.5/10 quality score
