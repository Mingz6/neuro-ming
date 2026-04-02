import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from pydantic import BaseModel

# Load .env from project root
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Add project root to path so `core` package resolves
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.llm import chat
from core.memory import Memory

app = FastAPI(title="Neuro-Ming")

web_dir = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=web_dir / "static"), name="static")
templates = Jinja2Templates(directory=web_dir / "templates")

memory = Memory()


class ChatRequest(BaseModel):
    message: str


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    user_msg = req.message.strip()
    if not user_msg:
        return {"response": "meow? You didn't say anything 🐱"}

    memory.add_message("user", user_msg)
    response = chat(memory.get_messages())
    memory.add_message("assistant", response)
    return {"response": response}


@app.post("/clear")
async def clear_endpoint():
    memory.clear()
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("web.app:app", host="0.0.0.0", port=8000, reload=True)
