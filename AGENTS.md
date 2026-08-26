# neuro-ming — Agent Instructions

AI VTuber assistant. Currently at M2: Voice Output (TTS). Web chatbot with Azure OpenAI GPT-5.2 + TTS.

See `.github/copilot-instructions.md` for full stack, structure, and conventions.

## Quick reference

- Runtime: Python 3.11+, FastAPI + Uvicorn
- Run: `source .venv/bin/activate && python web/app.py` → http://localhost:8000
- Keep `core/` framework-free (pure Python); web-specific code stays in `web/`
- Update `docs/progress.md` in the same PR when adding a new milestone
- Don't add a database before M12, don't add auth yet, don't switch web frameworks
