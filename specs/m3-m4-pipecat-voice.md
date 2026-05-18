# M3+M4: Pipecat Voice Pipeline

Card: N/A (personal project)
Status: draft
Date: 2026-05-18

---

## Goal

Add real-time voice conversation to neuro-ming using Pipecat framework. User speaks → AI responds with voice, in a natural conversational loop with <500ms latency.

## Motivation

- M1+M2 are text-chat + TTS (play audio after response). Not a real conversation.
- M3+M4 = actual voice loop: listen → understand → respond → handle interruptions.
- Pipecat is the proven framework (12.3K⭐, tend repo validates it).
- Same pipeline later extends to phone calls (Pharness) and streaming (M18+).

## Requirements

1. User speaks into mic → Pipecat STT transcribes in real-time
2. LLM generates response using neuro-ming personality
3. TTS speaks the response through speakers
4. VAD detects when user stops speaking (no manual button needed)
5. User can interrupt mid-response (TTS cancels immediately)
6. Web chat UI continues to work (text mode unaffected)
7. Desktop CLI mode: `python -m core.voice_pipeline` for local mic/speaker
8. WebSocket mode: browser connects for voice-in-browser (stretch goal)

## Non-Goals

- No phone calling in this milestone (that's Pharness's job)
- No wake word (M14+ territory)
- No avatar or lip sync (M8)
- No pipecat-subagents workers yet (implement the pipeline first, add workers after)
- Don't rewrite M1/M2 — additive only

## Edge Cases

- User is silent for 30+ seconds → pipeline stays listening, no timeout crash
- Background noise → Silero VAD should filter (test with music playing)
- Very long LLM response → TTS should stream (not wait for full response)
- Network drop during STT → graceful fallback, not crash
- Multiple browser tabs → each gets its own session

## Acceptance Criteria

- [ ] `python -m core.voice_pipeline` starts, listens to mic, responds via speaker
- [ ] Latency from end-of-speech to first audio response < 1 second
- [ ] Interruption works: speaking while TTS is playing cancels TTS
- [ ] neuro-ming personality preserved (same system prompt, same voice)
- [ ] Web chat `/chat` endpoint still works (no regression)
- [ ] No hardcoded API keys (all from .env)

---

## Technical Plan

### Architecture

```
core/voice_pipeline.py (new — entry point)
    │
    ├── Pipecat Pipeline:
    │   ├── Transport: LocalTransport (mic/speaker) or WebSocketTransport
    │   ├── VAD: Silero VAD
    │   ├── STT: Deepgram Nova-3
    │   ├── LLM: Azure OpenAI GPT-4o-mini (fast shell)
    │   │        └── system_prompt from core/personality.py
    │   └── TTS: Azure OpenAI TTS (existing) or ElevenLabs or Cartesia
    │
    └── Future: pipecat-subagents for workers (M4 phase 2)
```

### Dependencies to Add

```
pipecat-ai[silero,deepgram,openai]  # core pipeline
# Optional extras to evaluate:
# pipecat-ai[elevenlabs]  # better TTS
# pipecat-ai[cartesia]    # lowest latency TTS
```

### File Changes

| File | Action | Description |
|------|--------|-------------|
| `requirements.txt` | Edit | Add pipecat-ai with extras |
| `core/voice_pipeline.py` | Create | Pipecat pipeline definition + CLI entry |
| `core/voice_config.py` | Create | Voice-specific config (STT/TTS provider selection) |
| `.env.example` | Edit | Add DEEPGRAM_API_KEY, voice config vars |
| `web/app.py` | Edit (later) | Add `/voice` WebSocket endpoint (stretch) |

### Key Config (.env additions)

```
# Voice Pipeline (M3-M4)
DEEPGRAM_API_KEY=
VOICE_STT_PROVIDER=deepgram        # deepgram | whisper
VOICE_TTS_PROVIDER=azure-openai    # azure-openai | elevenlabs | cartesia
VOICE_LLM_MODEL=gpt-4o-mini       # fast shell model
ELEVENLABS_API_KEY=                # optional
CARTESIA_API_KEY=                  # optional
```

### Implementation Order

1. **Spike**: Install pipecat-ai, run their quickstart example locally to validate audio works
2. **M3 core**: Create `core/voice_pipeline.py` with Local Transport + Deepgram STT + Azure TTS
3. **Personality**: Wire `core/personality.py` system prompt into Pipecat LLM processor
4. **VAD + interruption**: Add Silero VAD, verify interruption handling
5. **TTS evaluation**: Compare Azure OpenAI vs ElevenLabs vs Cartesia (same sentence, pick by ear)
6. **Polish**: Error handling, graceful shutdown, .env validation
7. **WebSocket** (stretch): Add `/voice` endpoint for browser-based voice

### Reference: tend's Pipeline Setup

tend uses Pipecat like this (simplified):
```python
from pipecat.pipeline.pipeline import Pipeline
from pipecat.services.deepgram import DeepgramSTTService
from pipecat.services.openai import OpenAILLMService
from pipecat.services.elevenlabs import ElevenLabsTTSService
from pipecat.transports.local import LocalTransport
from pipecat.vad.silero import SileroVAD

transport = LocalTransport(mic_enabled=True, speaker_enabled=True)
pipeline = Pipeline([
    transport.input(),
    SileroVAD(),
    DeepgramSTTService(api_key=...),
    OpenAILLMService(model="gpt-4o-mini", system_prompt=PERSONALITY),
    ElevenLabsTTSService(voice_id=...),
    transport.output(),
])
```

This is ~20 lines to get a working voice loop. The complexity is in the config, not the code.

---

## Tasks

- [ ] Spike: install pipecat-ai, run quickstart example on local mic
- [ ] Create `core/voice_pipeline.py` with Local Transport
- [ ] Wire Deepgram STT (streaming, Nova-3)
- [ ] Wire LLM processor with personality.py system prompt
- [ ] Wire TTS (start with Azure OpenAI, evaluate alternatives)
- [ ] Add Silero VAD for turn detection
- [ ] Test interruption handling
- [ ] Update .env.example with new vars
- [ ] Verify web chat still works (no regression)
- [ ] (Stretch) Add WebSocket transport for browser voice

---

## Risks

- **Deepgram free tier limit**: 12,000 minutes/year. Enough for dev but watch usage.
- **Audio device permissions**: macOS may block mic access. Need to test with pyaudio/sounddevice.
- **Pipecat version churn**: Framework is actively developed (v1.2.1 as of May 2026). Pin version.
- **Latency budget**: Deepgram ~200ms + LLM ~300ms + TTS ~200ms = ~700ms. Acceptable. S2S model would cut to ~300ms total (future upgrade path).
