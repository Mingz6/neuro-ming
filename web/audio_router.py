"""WebSocket audio router — /ws/voice endpoint for real-time voice conversation."""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core import stt, tts
from core.llm import chat
from core.memory import SessionStore

logger = logging.getLogger(__name__)

router = APIRouter()

# Shared session store (imported from app at mount time, or standalone)
_sessions: SessionStore | None = None


def init(sessions: SessionStore) -> None:
    """Inject the shared session store."""
    global _sessions
    _sessions = sessions


def _get_sessions() -> SessionStore:
    global _sessions
    if _sessions is None:
        _sessions = SessionStore()
    return _sessions


@router.websocket("/ws/voice")
async def voice_ws(ws: WebSocket):
    """Real-time voice conversation over WebSocket.

    Protocol:
    - Client sends: binary audio frames (webm/opus from MediaRecorder)
    - Client sends: JSON text messages for control:
        {"type": "start", "session_id": "..."}  — begin recording
        {"type": "stop"}                         — end recording, trigger STT→LLM→TTS
        {"type": "config", "session_id": "..."}  — set session
    - Server sends: binary audio frames (mp3 TTS response)
    - Server sends: JSON text messages:
        {"type": "transcript", "text": "...", "final": true/false}
        {"type": "response", "text": "..."}
        {"type": "audio_end"}
        {"type": "error", "message": "..."}
    """
    await ws.accept()

    session_id: str = ""
    audio_buffer = bytearray()
    recording = False

    try:
        while True:
            msg = await ws.receive()

            if msg.get("type") == "websocket.disconnect":
                break

            # Text message = control frame
            if "text" in msg:
                try:
                    import json
                    data = json.loads(msg["text"])
                except (json.JSONDecodeError, TypeError):
                    continue

                msg_type = data.get("type", "")

                if msg_type == "config":
                    session_id = data.get("session_id", session_id)

                elif msg_type == "start":
                    session_id = data.get("session_id", session_id)
                    audio_buffer = bytearray()
                    recording = True

                elif msg_type == "stop":
                    recording = False
                    if not audio_buffer:
                        await ws.send_json({"type": "error", "message": "No audio received"})
                        continue

                    await _process_voice_turn(ws, bytes(audio_buffer), session_id)
                    audio_buffer = bytearray()

            # Binary message = audio data
            elif "bytes" in msg:
                if recording:
                    audio_buffer.extend(msg["bytes"])

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("Voice WebSocket error: %s", e, exc_info=True)
        try:
            await ws.send_json({"type": "error", "message": "Internal error"})
        except Exception:
            pass


async def _process_voice_turn(ws: WebSocket, audio_bytes: bytes, session_id: str) -> None:
    """Process one voice turn: STT → LLM → TTS → send back."""

    # 1. Transcribe
    transcript = await stt.transcribe_once(audio_bytes)
    if not transcript:
        await ws.send_json({"type": "error", "message": "Could not understand audio"})
        return

    await ws.send_json({"type": "transcript", "text": transcript, "final": True})

    # 2. LLM response
    sessions = _get_sessions()
    memory = sessions.get(session_id or "voice-default")
    memory.add_message("user", transcript)
    response = await chat(memory.get_messages())
    memory.add_message("assistant", response)

    await ws.send_json({"type": "response", "text": response})

    # 3. TTS — synthesize and send audio back
    if tts.is_enabled():
        audio_b64 = await tts.synthesize(response)
        if audio_b64:
            import base64
            audio_data = base64.b64decode(audio_b64)
            # Send in chunks for smoother playback
            chunk_size = 16384
            for i in range(0, len(audio_data), chunk_size):
                await ws.send_bytes(audio_data[i:i + chunk_size])

    await ws.send_json({"type": "audio_end"})
