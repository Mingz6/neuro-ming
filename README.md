# Neuro-Ming — AI VTuber Assistant 🐱

An AI assistant that starts as a chatbot and grows into a full AI VTuber with voice, avatar, game playing, and streaming. Each milestone is independently demoable — right now we're at M1: a chatbot with personality.

## Current Status: M1 — Chatbot with Personality ✅

A web-based chatbot powered by Azure OpenAI GPT-5.2, with a personality modeled on the real Ming (dev voice, cat energy, smart home nerd). Dark-themed UI, multi-turn conversation, in-memory history.

## Run Locally

```bash
cd ~/code/personal/neuro-ming
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # add your OpenAI API key
python web/app.py
# Open http://localhost:8000
```

## Milestone Roadmap

```
Phase 1: FOUNDATION
├── M1: Chatbot with personality  ← you are here
├── M2: Voice output (TTS)
├── M3: Voice input (STT)
└── M4: Conversational loop (M1-M3 combined)

Phase 2: AVATAR
├── M5: Static VTuber avatar
├── M6: Lip sync
├── M7: Expressions & gestures
└── M8: Full avatar pipeline

Phase 3: SKILLS
├── M9: Game playing (basic)
├── M10: Screen reading
├── M11: Tool use & web browsing
├── M12: Learning & memory
└── M13: Multi-agent collab

Phase 4: UTILITY
├── M14: Desktop assistant mode
├── M15: Scheduling & reminders
├── M16: Document analysis
└── M17: Code pair programming

Phase 5: PLATFORM
├── M18: Twitch/YouTube streaming
├── M19: Chat interaction (live)
├── M20: Content generation
└── M21: Autonomous streaming
```

## Tech Stack

- **Python** — FastAPI (async), OpenAI SDK
- **Frontend** — Vanilla HTML/CSS/JS (no framework needed for M1)
- **LLM** — 6 providers: Azure OpenAI, OpenAI, Groq, Together AI, OpenRouter, Ollama
- **Default model** — Azure OpenAI GPT-5.2 (`gpt-5-2-chat` deployment)

## Screenshot

![M1 Chat UI](docs/images/m1-chat-ui.png)
