# Roadmap

The README lists the next three milestones. This is the whole list. Each milestone has to demo on its own.

```
Phase 1: FOUNDATION
├── M1: Chatbot with personality            done
├── M2: Voice output                        done
├── M3: Voice input (STT + WebSocket)       done
└── M4: Conversational loop (two-tier brain + workers)   next

Phase 2: AVATAR
├── M5: Persona eval harness
├── M6: Conversation simulator
├── M7: Safety guardrails
└── M8: Static VTuber avatar + lip sync

Phase 3: SKILLS
├── M9: Game playing (basic)
├── M10: Screen reading
├── M11: Tool use & web browsing
├── M12: Learning & memory
└── M13: Multi-agent collab

Phase 4: UTILITY
├── M14: Desktop assistant mode (Pipecat Local Transport)
├── M15: Scheduling & reminders
├── M16: Document analysis
└── M17: Code pair programming

Phase 5: PLATFORM
├── M18: Twitch/YouTube streaming (Pipecat WebRTC Transport)
├── M19: Chat interaction (live)
├── M20: Content generation
└── M21: Autonomous streaming
```

The task lists in [progress.md](progress.md) predate this numbering from M8 on, so
their milestone numbers differ. M5, M6 and M7 match in both files.

## Voice stack, M3 and M4

| Layer | Technology | Why |
|-------|-----------|-----|
| STT | Deepgram Nova-3 | Fast and accurate, about $0.01 per minute |
| STT alternatives | Azure Speech, Whisper | Redundancy and an offline option |
| Transport | WebSocket (`/ws/voice`) | Browser-native, no framework dependency |
| LLM (fast shell) | GPT-5.4-mini or Haiku | Low latency for the voice loop |
| LLM (workers) | Claude Opus through the CLI | Heavy tool use on subscription billing |
| TTS | Azure OpenAI (nova) | Already working since M2 |
| Possible later | OpenAI Realtime API | Skips STT and TTS, about 300 ms end to end |
