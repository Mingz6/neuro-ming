# neuro-ming — Copilot Instructions

AI VTuber assistant. Currently at **M3: Voice Input (STT)**. Web chatbot with pluggable LLM, TTS, and real-time voice over WebSocket.

## Stack

- **Runtime:** Python 3.11+, FastAPI + Uvicorn
- **LLM:** six providers behind one interface — `LLM_PROVIDER` picks from ollama (default, local), azure, openai, groq, together, openrouter. Azure uses GPT-5.4 with a `gpt-4.1` fallback.
- **Voice:** Azure OpenAI TTS (nova); STT via Deepgram → Azure Speech → Whisper offline
- **Frontend:** plain HTML/JS in `web/` + SolidJS widget consumed by mingz-dev
- **No database** — conversation memory is in-process until M11

## Run

```bash
source .venv/bin/activate
python web/app.py    # http://localhost:8000
```

## Conventions

- The `README.md` roadmap (the block with the 🚧 marker) is the canonical current
  milestone. When one lands, update it and the line at the top of this file — those
  are the only two copies; four copies is how this drifted to M1/M2/M3 at once.
- Each milestone (M1, M2, ...) is independently demoable. Don't break an earlier milestone when adding the next.
- Secrets live in `.env` (never commit). `.env.example` stays in sync with every new variable.
- Keep `core/` framework-free (pure Python). Web-specific code stays in `web/`.
- TTS responses are mp3 returned from FastAPI; client decides whether to play.

## Architecture

```
core/          ← llm, memory, personality, tts — pure logic
web/           ← FastAPI app + static + templates (the shell)
docs/          ← architecture + progress notes (keep updated per milestone)
```

## Coding Rules

- FastAPI endpoints use async def. Never block the event loop — run CPU/sync work via `asyncio.to_thread` if unavoidable.
- Use Pydantic models for request/response schemas. Never return raw dicts.
- Log with `logging` module, not print. Include request IDs where useful.
- When adding a new milestone, update `docs/progress.md` in the same PR.

## What NOT to do

- Don't add a database before M12 (Learning & memory). In-process state is intentional.
- Don't add auth before we have users other than the owner.
- Don't switch web frameworks. FastAPI stays.
