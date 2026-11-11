"""The /ws/voice route with STT, the LLM and TTS replaced by fakes."""

import base64
import json

import pytest
from fastapi.testclient import TestClient

from core import stt, tts
from core.memory import SessionStore
from web import app as app_module
from web import audio_router


class Fakes:
    def __init__(self):
        self.transcript: str | None = "what are you working on"
        self.reply = "mostly this repo"
        self.tts_audio: bytes | None = b"fake-mp3"
        self.heard: list[bytes] = []
        self.llm_calls: list[list[dict]] = []


@pytest.fixture
def fakes(monkeypatch):
    f = Fakes()

    async def fake_stt(audio):
        f.heard.append(audio)
        return f.transcript

    async def fake_chat(messages):
        f.llm_calls.append(messages)
        return f.reply

    async def fake_tts(text):
        return base64.b64encode(f.tts_audio).decode() if f.tts_audio is not None else None

    monkeypatch.setattr(stt, "transcribe_once", fake_stt)
    monkeypatch.setattr(audio_router, "chat", fake_chat)
    monkeypatch.setattr(tts, "synthesize", fake_tts)
    monkeypatch.setenv("TTS_ENABLED", "true")
    monkeypatch.setattr(audio_router, "_sessions", SessionStore())
    return f


@pytest.fixture
def client():
    with TestClient(app_module.app) as c:
        yield c


def speak(ws, *frames, session_id="s1"):
    ws.send_json({"type": "start", "session_id": session_id})
    for frame in frames:
        ws.send_bytes(frame)
    ws.send_json({"type": "stop"})


def read_turn(ws):
    """Collect one turn: JSON events in order, plus the audio bytes sent in between."""
    events, audio = [], bytearray()
    while True:
        msg = ws.receive()
        if msg.get("bytes") is not None:
            audio.extend(msg["bytes"])
            continue
        event = json.loads(msg["text"])
        events.append(event)
        if event["type"] in ("audio_end", "error"):
            return events, bytes(audio)


def test_full_voice_turn(client, fakes):
    with client.websocket_connect("/ws/voice") as ws:
        speak(ws, b"chunk-1", b"chunk-2")
        events, audio = read_turn(ws)

    assert events == [
        {"type": "transcript", "text": "what are you working on", "final": True},
        {"type": "response", "text": "mostly this repo"},
        {"type": "audio_end"},
    ]
    assert audio == b"fake-mp3"
    assert fakes.heard == [b"chunk-1chunk-2"]


def test_transcript_becomes_the_user_turn_in_the_llm_call(client, fakes):
    with client.websocket_connect("/ws/voice") as ws:
        speak(ws, b"audio")
        read_turn(ws)
    [call] = fakes.llm_calls
    assert call[0]["role"] == "system"
    assert call[-1] == {"role": "user", "content": "what are you working on"}


def test_same_session_remembers_the_last_turn(client, fakes):
    with client.websocket_connect("/ws/voice") as ws:
        speak(ws, b"one", session_id="abc")
        read_turn(ws)
        speak(ws, b"two", session_id="abc")
        read_turn(ws)
    assert [m["role"] for m in fakes.llm_calls[1]] == ["system", "user", "assistant", "user"]


def test_voice_and_text_chat_share_a_session_store(client, fakes, monkeypatch):
    store = SessionStore()
    monkeypatch.setattr(audio_router, "_sessions", store)
    store.get("shared").add_message("user", "typed earlier")
    with client.websocket_connect("/ws/voice") as ws:
        speak(ws, b"audio", session_id="shared")
        read_turn(ws)
    contents = [m["content"] for m in fakes.llm_calls[0]]
    assert "typed earlier" in contents


def test_tts_audio_is_sent_in_16k_chunks(client, fakes):
    fakes.tts_audio = bytes(range(256)) * 160  # 40,960 bytes
    with client.websocket_connect("/ws/voice") as ws:
        speak(ws, b"audio")
        sizes = []
        while True:
            msg = ws.receive()
            if msg.get("bytes") is not None:
                sizes.append(len(msg["bytes"]))
            elif json.loads(msg["text"])["type"] == "audio_end":
                break
    assert sizes == [16384, 16384, 8192]


def test_tts_off_still_answers_in_text(client, fakes, monkeypatch):
    monkeypatch.setenv("TTS_ENABLED", "false")
    with client.websocket_connect("/ws/voice") as ws:
        speak(ws, b"audio")
        events, audio = read_turn(ws)
    assert [e["type"] for e in events] == ["transcript", "response", "audio_end"]
    assert audio == b""


def test_tts_failure_still_ends_the_turn(client, fakes):
    fakes.tts_audio = None
    with client.websocket_connect("/ws/voice") as ws:
        speak(ws, b"audio")
        events, audio = read_turn(ws)
    assert events[-1] == {"type": "audio_end"}
    assert audio == b""


def test_unintelligible_audio_returns_an_error_and_skips_the_llm(client, fakes):
    fakes.transcript = None
    with client.websocket_connect("/ws/voice") as ws:
        speak(ws, b"mumble")
        events, _ = read_turn(ws)
    assert events == [{"type": "error", "message": "Could not understand audio"}]
    assert fakes.llm_calls == []


def test_stop_with_no_audio_is_an_error(client, fakes):
    with client.websocket_connect("/ws/voice") as ws:
        ws.send_json({"type": "start", "session_id": "s1"})
        ws.send_json({"type": "stop"})
        events, _ = read_turn(ws)
    assert events == [{"type": "error", "message": "No audio received"}]
    assert fakes.heard == []


def test_audio_before_start_is_ignored(client, fakes):
    with client.websocket_connect("/ws/voice") as ws:
        ws.send_bytes(b"stray frame")
        speak(ws, b"real")
        read_turn(ws)
    assert fakes.heard == [b"real"]


def test_oversized_recording_is_cut_off(client, fakes, monkeypatch):
    monkeypatch.setattr(audio_router, "MAX_AUDIO_BYTES", 10)
    with client.websocket_connect("/ws/voice") as ws:
        ws.send_json({"type": "start", "session_id": "s1"})
        ws.send_bytes(b"12345678")
        ws.send_bytes(b"12345678")
        first = ws.receive_json()
        ws.send_json({"type": "stop"})
        second = ws.receive_json()
    assert first == {"type": "error", "message": "Audio buffer exceeded 10 MB limit"}
    assert second == {"type": "error", "message": "No audio received"}
    assert fakes.heard == []


def test_start_clears_a_half_finished_recording(client, fakes):
    with client.websocket_connect("/ws/voice") as ws:
        ws.send_json({"type": "start", "session_id": "s1"})
        ws.send_bytes(b"abandoned")
        speak(ws, b"fresh")
        read_turn(ws)
    assert fakes.heard == [b"fresh"]


def test_junk_text_frames_do_not_break_the_socket(client, fakes):
    with client.websocket_connect("/ws/voice") as ws:
        ws.send_text("not json")
        ws.send_text("[1, 2]")  # valid JSON, wrong shape
        ws.send_json({"type": "ping"})
        speak(ws, b"audio")
        events, _ = read_turn(ws)
    assert events[-1] == {"type": "audio_end"}


def test_config_frame_sets_the_session(client, fakes, monkeypatch):
    store = SessionStore()
    monkeypatch.setattr(audio_router, "_sessions", store)
    with client.websocket_connect("/ws/voice") as ws:
        ws.send_json({"type": "config", "session_id": "from-config"})
        ws.send_json({"type": "start"})
        ws.send_bytes(b"audio")
        ws.send_json({"type": "stop"})
        read_turn(ws)
    assert "from-config" in store._sessions


def test_missing_session_id_falls_back_to_voice_default(client, fakes, monkeypatch):
    store = SessionStore()
    monkeypatch.setattr(audio_router, "_sessions", store)
    with client.websocket_connect("/ws/voice") as ws:
        ws.send_json({"type": "start"})
        ws.send_bytes(b"audio")
        ws.send_json({"type": "stop"})
        read_turn(ws)
    assert "voice-default" in store._sessions
