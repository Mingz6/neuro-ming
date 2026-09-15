# neuro-ming — Agent Instructions

AI VTuber assistant. Web chatbot with pluggable LLM, TTS, and real-time voice over WebSocket.

See `.github/copilot-instructions.md` for full stack, structure, and conventions.
The roadmap in `README.md` is the canonical answer to which milestone is current —
this file deliberately does not restate it.

## Quick reference

- Runtime: Python 3.11+, FastAPI + Uvicorn
- Run: `source .venv/bin/activate && python web/app.py` → http://localhost:8000
- Keep `core/` framework-free (pure Python); web-specific code stays in `web/`
- Update `docs/progress.md` in the same PR when adding a new milestone
- Don't add a database before M12, don't add auth yet, don't switch web frameworks
