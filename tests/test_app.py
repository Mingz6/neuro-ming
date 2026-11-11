import pytest
from fastapi.testclient import TestClient

from core.memory import SessionStore
from web import app as app_module


@pytest.fixture
def client(monkeypatch):
    """The real app with a fresh session store and the LLM and TTS replaced."""
    monkeypatch.setattr(app_module, "sessions", SessionStore())
    seen: list[list[dict]] = []

    async def fake_chat(messages):
        seen.append(messages)
        return f"echo: {messages[-1]['content']}"

    monkeypatch.setattr(app_module, "chat", fake_chat)
    with TestClient(app_module.app) as c:
        c.llm_calls = seen
        yield c


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["uptime_seconds"] >= 0


def test_pages_render(client):
    for path in ("/", "/chat"):
        res = client.get(path)
        assert res.status_code == 200
        assert "Neuro-Ming" in res.text


def test_static_assets_are_served(client):
    assert client.get("/static/chat.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200


def test_chat_returns_the_reply(client):
    res = client.post("/chat", json={"message": "hello", "session_id": "s1"})
    assert res.status_code == 200
    assert res.json() == {"response": "echo: hello"}


def test_chat_sends_system_prompt_then_history(client):
    client.post("/chat", json={"message": "first", "session_id": "s1"})
    client.post("/chat", json={"message": "second", "session_id": "s1"})
    second_call = client.llm_calls[1]
    assert [m["role"] for m in second_call] == ["system", "user", "assistant", "user"]
    assert second_call[2]["content"] == "echo: first"


def test_sessions_do_not_share_history(client):
    client.post("/chat", json={"message": "from a", "session_id": "a"})
    client.post("/chat", json={"message": "from b", "session_id": "b"})
    assert len(client.llm_calls[1]) == 2  # system + this user turn only


def test_clear_forgets_the_conversation(client):
    client.post("/chat", json={"message": "one", "session_id": "s1"})
    assert client.post("/clear", json={"session_id": "s1"}).json() == {"status": "ok"}
    client.post("/chat", json={"message": "two", "session_id": "s1"})
    assert len(client.llm_calls[1]) == 2


def test_blank_message_never_reaches_the_llm(client):
    res = client.post("/chat", json={"message": "   ", "session_id": "s1"})
    assert "You didn't say anything" in res.json()["response"]
    assert client.llm_calls == []


@pytest.mark.parametrize("body", [
    {"message": "x" * 4001, "session_id": "s1"},
    {"message": "hi", "session_id": ""},
    {"message": "hi", "session_id": "s" * 65},
    {"message": "hi"},
    {"session_id": "s1"},
])
def test_bad_chat_requests_are_rejected(client, body):
    assert client.post("/chat", json=body).status_code == 422
    assert client.llm_calls == []


def test_chat_adds_audio_when_tts_is_on(client, monkeypatch):
    spoken = []

    async def fake_synthesize(text):
        spoken.append(text)
        return "QVVESU8="

    monkeypatch.setenv("TTS_ENABLED", "true")
    monkeypatch.setattr(app_module.tts, "synthesize", fake_synthesize)
    res = client.post("/chat", json={"message": "hi", "session_id": "s1"}).json()
    assert res == {"response": "echo: hi", "audio": "QVVESU8="}
    assert spoken == ["echo: hi"]


def test_chat_skips_tts_when_the_client_mutes(client, monkeypatch):
    async def explode(_text):
        raise AssertionError("TTS should not run")

    monkeypatch.setenv("TTS_ENABLED", "true")
    monkeypatch.setattr(app_module.tts, "synthesize", explode)
    res = client.post("/chat", json={"message": "hi", "session_id": "s1", "tts_enabled": False})
    assert "audio" not in res.json()


def test_chat_skips_tts_when_the_server_has_it_off(client, monkeypatch):
    async def explode(_text):
        raise AssertionError("TTS should not run")

    monkeypatch.setattr(app_module.tts, "synthesize", explode)
    assert "audio" not in client.post("/chat", json={"message": "hi", "session_id": "s1"}).json()


def test_chat_leaves_audio_out_when_tts_fails(client, monkeypatch):
    async def failing(_text):
        return None

    monkeypatch.setenv("TTS_ENABLED", "true")
    monkeypatch.setattr(app_module.tts, "synthesize", failing)
    assert client.post("/chat", json={"message": "hi", "session_id": "s1"}).json() == {"response": "echo: hi"}
