# Neuro-Ming M3/M4 — Voice Architecture Spec

**Status:** Active  
**Source:** Tend/Jarvis repo study (Vancouver AI Meetup May 15 2026 — OpenClaw hackathon winner)  
**Reference repo:** `/Users/mingz/code/playground/tend`  
**Updated:** 2026-05-21 (replaced draft with concrete findings from code study)

---

## What Tend Taught Us

Tend is a production ambient voice assistant built on [Pipecat](https://github.com/pipecat-ai/pipecat) + [pipecat-subagents](https://github.com/pipecat-ai/pipecat-subagents). Its architecture is a near-perfect blueprint for neuro-ming M3/M4. Key patterns extracted:

| Tend concept | Tend implementation | Neuro-ming equivalent |
|---|---|---|
| Hub | `audio/hub.py` — always-running audio agent with STT/TTS/context | `web/app.py` + new voice loop |
| Brain | `brain.py` — thin `LLMAgent` (no context ownership) | Fast conversational shell |
| Wake/sleep gates | `audio/gates.py` — OpenWakeWord + sleep phrase | Push-to-talk (M3), "hey neuro" (M5+) |
| GeneralWorker | `workers/general.py` + Claude CLI subprocess | Claude Opus async worker |
| Shared bus | `pipecat_subagents.AgentBus` | `asyncio.Queue` to start |
| ProactiveAnnouncer | `announcer.py` — cooldown, defer-while-brain-active, LLM context log | Worker → TTS notify |
| Skills as markdown | `~/.tend/skills/<name>/SKILL.md` | Neuro-ming skills (M5) |
| soul.md | `_defaults/soul.md` — persona prompt reloaded daily | `core/personality.py` |
| SessionManager | `session.py` — daily reset at 04:00, deferred when brain active | New `core/session.py` |

---

## The Core Pattern (Tend's Canonical Pipeline)

```
Mic → OpenWakeWordGate → STT (Deepgram / Whisper fallback)
    → user_aggregator
    → BusBridgeProcessor → AgentBus → Brain.LLM
    → BusBridgeProcessor → TTS (ElevenLabs / AVSpeech fallback)
    → assistant_aggregator (captures context)
    → Speaker

Brain.LLM tool call → GeneralWorker (Claude CLI subprocess, subscription billing)
    → worker runs independently (can take minutes)
    → worker.announce() → ProactiveAnnouncer → TTS → Speaker
    → brain._append_to_context() (so next turn knows what was said)
```

**Critical insight:** Brain does NOT own the LLMContext. Hub owns it. Brain is just an LLMAgent plugged into the bus. This is why the brain can go "inactive" (sleep) while Hub keeps audio running — wake word detection happens at the Gate, not inside Brain. When users speak to a sleeping Tend, only the Gate is awake; the LLM never fires until wake word detected.

---

## Dependency Decision: Do NOT add Pipecat to neuro-ming yet

Tend's value is architectural — the patterns, not the framework. Pipecat's local audio pipeline (`LocalAudioTransport`, `VADProcessor`, etc.) assumes a Raspberry Pi or desktop app, not a browser client. Adding `pipecat-ai` for M3 would force a major refactor of `web/app.py` and block M3 delivery.

**Plan:**
- M3: raw WebSocket audio, custom STT wrapper (no Pipecat dep)
- M4: `asyncio.Queue` as bus, port `claude_cli.py` and `announcer.py` from Tend (no Pipecat dep)
- M5+: Evaluate Pipecat for a standalone desktop/Pi build of neuro-ming (separate entrypoint, separate requirements)

---

## M3: STT + Basic Voice Loop

**Goal:** Close the audio loop. User speaks → STT → existing chat LLM → TTS response. Push-to-talk, no wake word. No workers, no bus.

### Architecture

```
Browser mic (MediaRecorder)
    → WebSocket /ws/voice (PCM 16kHz mono)
    → core/stt.py (Deepgram or Azure STT or Whisper)
    → existing /chat LLM logic (core/llm.py)
    → core/tts.py (existing Azure TTS)
    → WebSocket stream back
    → browser AudioContext plays chunks
```

### New: `core/stt.py`

Same cloud-preferred / local-fallback pattern as Tend's `services.py`:

```python
from enum import StrEnum

class STTProvider(StrEnum):
    DEEPGRAM = "deepgram"
    AZURE = "azure"
    WHISPER = "whisper"

async def is_enabled() -> bool: ...
async def transcribe_stream(audio_stream: AsyncIterator[bytes]) -> AsyncIterator[str]: ...
async def transcribe_once(audio_bytes: bytes) -> str | None: ...
```

Provider selection: env var `STT_PROVIDER=deepgram`. Deepgram preferred (streaming, 100ms latency). Azure STT as zero-cost fallback (already have creds). Whisper for offline.

Deepgram setup:
```python
# deepgram nova-3-general, interim_results=True, endpointing=300ms
# Same params Tend uses
```

### New: `web/audio_router.py`

WebSocket endpoint for voice:
```python
@router.websocket("/ws/voice")
async def voice_ws(ws: WebSocket):
    await ws.accept()
    async for chunk in ws.iter_bytes():
        # buffer until endpointing threshold
        ...
    transcript = await stt.transcribe_once(pcm_buffer)
    async for text_chunk in llm.stream_chat(transcript):
        async for audio_chunk in tts.stream(text_chunk):
            await ws.send_bytes(audio_chunk)
```

### Update: Browser UI (push-to-talk)

`web/static/chat.js` additions:
```js
// Push-to-talk: hold space or click mic button
// MediaRecorder → WebSocket → stream PCM
// Receive audio chunks → AudioContext decode + play in order
```

### .env.example additions

```
STT_PROVIDER=deepgram       # deepgram | azure | whisper
DEEPGRAM_API_KEY=
STT_ENABLED=false
```

### M3 tasks

- [ ] `core/stt.py` — Deepgram primary, Azure fallback, Whisper offline
- [ ] `web/audio_router.py` — WebSocket `/ws/voice` endpoint, PCM buffering
- [ ] Push-to-talk in browser UI (chat.js + ChatWidget.tsx)
- [ ] Wire STT transcript → existing `core/llm.py` chat path
- [ ] Spike ElevenLabs TTS vs current Azure nova (same sentence, pick by ear)
- [ ] `.env.example` additions
- [ ] Verify `/chat` text endpoint still works (no regression)

---

## M4: Two-Tier Brain + Workers + Shared Bus

**Goal:** Fast shell stays conversational. Heavy tasks spawn async Claude CLI workers. ProactiveAnnouncer delivers results to voice.

### Architecture

```
Browser mic → WebSocket → STT → Fast Shell (Haiku, <300ms)
    ├── simple reply → TTS → browser speaker
    └── do_task tool call detected
                   │
            AsyncTaskBus (asyncio.Queue)
                   │
         ClaudeCliWorker (Opus, CLI subprocess, subscription billing)
                   │
            task_done → ProactiveAnnouncer
                   │
        TTS announce → browser speaker (even if user not talking)
        + append to LLM context (next turn knows what was said)
```

### New: `core/bus.py`

Minimal shared bus — no pipecat-subagents required:
```python
from asyncio import Queue
from typing import Callable, Awaitable

class TaskBus:
    def __init__(self): ...
    async def enqueue(self, task_id: str, request: str) -> None: ...
    async def on_complete(self, task_id: str, result: str, spoken: str) -> None: ...
    def subscribe(self, callback: Callable[[str, str], Awaitable[None]]) -> None: ...
```

### New: `workers/claude_cli.py` (ported from Tend)

Tend's `workers/claude_cli.py` is the key. Port directly:
- Scrub `ANTHROPIC_API_KEY` (+ 30 other vars) from subprocess env → bills subscription, not per-token
- `asyncio.create_subprocess_exec(["claude", "--output-format", "json", ...])` 
- `ClaudeRunSpec(prompt, system_prompt, model)` — model defaults to Opus for workers
- On complete: post result to `TaskBus.on_complete()`
- On error: post error with spoken fallback ("Sorry, that task failed")

```python
# CLAUDE_CLI_CLEAR_ENV list from tend (scrubs 30+ env vars to force subscription billing)
# ClaudeRunSpec dataclass
# async def run(spec: ClaudeRunSpec, cwd: Path, timeout: float) -> ClaudeResult
```

### New: `core/announcer.py` (ported from Tend)

Port Tend's `announcer.py` directly:
```python
class ProactiveAnnouncer:
    async def announce(self, text: str, *, category: str, urgent: bool = False) -> bool:
        # - Drop if on cooldown (default 300s per category, configurable per-category)
        # - Queue if fast shell is mid-turn (not urgent)
        # - Urgency bypasses both cooldown and queue
        # - Always log to LLM context so next turn knows what was said
```

Key behavior: if user is mid-conversation, worker result is queued and plays as soon as the turn ends. User never hears a worker interrupting their own reply.

### Update: `core/llm.py`

Add tool definitions:
```python
@tool
async def do_task(request: str) -> str:
    """Queue a background task. Returns immediately with an acknowledgement."""
    task_id = await bus.enqueue(task_id=uuid4(), request=request)
    return f"On it. I'll let you know when I have an answer."

@tool  
async def task_status() -> str:
    """Check status of running background tasks."""
```

Model split:
```python
# Fast shell
SHELL_MODEL = "claude-haiku-4-5"    # <300ms response

# Workers (in claude_cli.py)
WORKER_MODEL = "claude-opus-4-5"    # called via CLI, subscription billing
```

System prompt addition:
```
For tasks that need internet access, heavy research, or long computation,
call do_task with the user's verbatim request. Give a one-sentence
acknowledgement. I will announce the result when it's ready.
```

### M4 tasks

- [ ] `core/bus.py` — minimal `asyncio.Queue` task bus
- [ ] `workers/claude_cli.py` — ported from Tend, subscription billing, CLAUDE_CLI_CLEAR_ENV
- [ ] `core/announcer.py` — ported from Tend, cooldown + deferral + context append
- [ ] `core/llm.py` — add `do_task` tool, two-model config (Haiku shell + Opus workers)
- [ ] Wire announcer → TTS playback (even outside of active turns)
- [ ] Queue + announce UX in browser: show "working..." indicator, clear on announce
- [ ] Parallel workers: multiple `do_task` calls run concurrently, each posts to bus independently
- [ ] Worker timeout + retry (from Tend's `ClaudeRunSpec`)

---

## TTS Evaluation: ElevenLabs vs Azure TTS

| | Azure TTS (current, M2) | ElevenLabs |
|---|---|---|
| Voice | nova (good) | Rachel/Adam (best in class) |
| Latency | ~300ms | ~200ms (turbo model) |
| Cost | ~zero (Azure sub) | $20/mo creator plan |
| API stability | Very stable | Generally stable |
| Naturalness | Good | Best available |
| Tend's choice | Not used | Primary (AVSpeech as fallback) |

**Action (M3 spike):** Same sentence through both. Pick by ear. If ElevenLabs wins clearly, swap as default. Keep Azure as fallback.

Also worth testing: macOS AVSpeech (native, zero cost, `say` command + PyObjC). Fine for dev.

---

## STT Evaluation: Deepgram vs Azure vs Whisper

| | Deepgram (nova-3-general) | Azure STT | Whisper (local) |
|---|---|---|---|
| Accuracy | Best | Good | Good (large-v3-turbo) |
| Latency | Streaming, ~100ms | Streaming | Batch (high latency) |
| Cost | ~$0.0059/min (~$5-10 total dev) | Included in Azure sub | Free |
| Setup | DEEPGRAM_API_KEY | Already wired | whisper.cpp installed |
| Interim results | Yes | Yes | No |
| Tend's choice | Primary | Not used | Local fallback |

**Decision:** Deepgram primary, Azure STT as zero-cost fallback, Whisper for offline.

---

## What to Reuse Directly vs Rewrite

| Tend component | Neuro-ming action |
|---|---|
| `workers/claude_cli.py` | **Port directly** — CLAUDE_CLI_CLEAR_ENV list, ClaudeRunSpec, subprocess spawn pattern |
| `announcer.py` | **Port directly** — cooldown logic, deferral queue, drain_pending, context append |
| `services.py` STT factory | **Port logic** — preflight check + fallback pattern |
| `services.py` TTS factory | **Reference** — use for ElevenLabs spike |
| `brain.py` `on_task_update` | **Adapt** — append announced text to LLM context (same idea, no pipecat frames) |
| `session.py` SessionManager | **Adapt later** — daily reset at 04:00, soul reload (M5+) |
| `audio/hub.py` full pipeline | **Defer** — too coupled to Pipecat's local audio transport |
| `audio/gates.py` wake/sleep | **Defer to M5+** — needs always-running process, not browser tab |
| `dispatch.py` event fan-out | **Reference for M5** — skill-as-event pattern |
| Skills as markdown (`SKILL.md`) | **Adopt for M5** — brain skills live in `~/.neuro-ming/skills/` |

---

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Deepgram free tier (12,000 min/year) | Low | Enough for dev; watch usage |
| Browser mic permissions | Medium | Test on Chrome + Safari |
| Claude CLI subprocess not in PATH | Medium | `which claude` check at startup |
| WebSocket audio ordering/chunks | Medium | Use `AudioWorklet`, sequence numbers |
| Worker timeout (Opus is slow) | Low | Default 120s timeout, configurable |
| ElevenLabs voice quality not worth $20/mo | Low | Azure TTS fallback ready |

---

## References

- Tend source: `/Users/mingz/code/playground/tend`
- Tend brain: `tend/src/tend/brain.py` — LLMAgent pattern, on_task_update
- Tend announcer: `tend/src/tend/announcer.py` — port this directly
- Tend claude_cli: `tend/src/tend/workers/claude_cli.py` — port this directly
- Tend services: `tend/src/tend/services.py` — STT/TTS factory pattern
- Meetup notes: `~/code/playground/vam-ai/meetings/2026/2026-05-15-openclaw-demos/notes-live.md`
- Voice memo summary: `~/code/personal/neuro-ming/comms/2026-05-09-summary.md`
- PipeCat framework: https://github.com/pipecat-ai/pipecat
- pipecat-subagents: https://github.com/pipecat-ai/pipecat-subagents
