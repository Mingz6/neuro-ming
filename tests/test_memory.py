import pytest

from core import memory
from core.memory import MAX_MESSAGES, Memory, SessionStore
from core.personality import get_system_prompt


def test_get_messages_puts_system_prompt_first():
    mem = Memory()
    mem.add_message("user", "hi")
    msgs = mem.get_messages()
    assert msgs[0] == {"role": "system", "content": get_system_prompt()}
    assert msgs[1] == {"role": "user", "content": "hi"}


def test_window_keeps_only_the_latest_messages():
    mem = Memory()
    for i in range(MAX_MESSAGES + 5):
        mem.add_message("user", f"msg {i}")
    msgs = mem.get_messages()[1:]  # drop the system prompt
    assert len(msgs) == MAX_MESSAGES
    assert msgs[0]["content"] == "msg 5"
    assert msgs[-1]["content"] == f"msg {MAX_MESSAGES + 4}"


def test_clear_empties_history_but_keeps_system_prompt():
    mem = Memory()
    mem.add_message("user", "hi")
    mem.clear()
    assert len(mem.get_messages()) == 1


def test_session_store_returns_same_memory_per_id():
    store = SessionStore()
    assert store.get("a") is store.get("a")
    assert store.get("a") is not store.get("b")


def test_session_store_clear_forgets_the_session():
    store = SessionStore()
    first = store.get("a")
    first.add_message("user", "hi")
    store.clear("a")
    assert store.get("a") is not first
    store.clear("never-existed")  # no error


def test_session_expires_after_ttl(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(memory.time, "monotonic", lambda: now[0])
    store = SessionStore()
    first = store.get("a")
    now[0] += memory.SESSION_TTL + 1
    assert store.get("a") is not first


def test_session_touch_keeps_it_alive(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(memory.time, "monotonic", lambda: now[0])
    store = SessionStore()
    first = store.get("a")
    now[0] += memory.SESSION_TTL - 10
    store.get("a")
    now[0] += memory.SESSION_TTL - 10
    assert store.get("a") is first


def test_oldest_session_is_dropped_at_the_cap(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(memory.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(memory, "MAX_SESSIONS", 3)
    store = SessionStore()
    oldest = store.get("s0")
    for i in range(1, 3):
        now[0] += 1
        store.get(f"s{i}")
    now[0] += 1
    store.get("s3")  # over the cap, so s0 goes
    assert set(store._sessions) == {"s1", "s2", "s3"}
    assert store.get("s0") is not oldest
