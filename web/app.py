import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from pydantic import BaseModel, Field

# Load .env from project root
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Add project root to path so `core` package resolves
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.llm import chat
from core.memory import SessionStore
from core import tts

app = FastAPI(title="Neuro-Ming")

cors_origins = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:4321").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)

web_dir = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=web_dir / "static"), name="static")
templates = Jinja2Templates(directory=web_dir / "templates")

sessions = SessionStore()


class ChatRequest(BaseModel):
    message: str = Field(..., max_length=4000)
    session_id: str = Field(..., min_length=1, max_length=64)
    tts_enabled: bool = Field(default=True)


class ClearRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=64)


@app.get("/")
async def landing(request: Request):
    return templates.TemplateResponse(request, "landing.html")


@app.get("/chat")
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    user_msg = req.message.strip()
    if not user_msg:
        return {"response": "meow? You didn't say anything 🐱"}

    memory = sessions.get(req.session_id)
    memory.add_message("user", user_msg)
    response = await chat(memory.get_messages())
    memory.add_message("assistant", response)

    audio = None
    if req.tts_enabled and tts.is_enabled():
        audio = await tts.synthesize(response)

    result: dict = {"response": response}
    if audio:
        result["audio"] = audio
    return result


@app.post("/clear")
async def clear_endpoint(req: ClearRequest):
    sessions.clear(req.session_id)
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("web.app:app", host="127.0.0.1", port=8000, reload=True)
