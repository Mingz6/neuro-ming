import time
from core.personality import get_system_prompt

MAX_MESSAGES = 20
SESSION_TTL = 1800  # 30 minutes
MAX_SESSIONS = 200


class Memory:
    def __init__(self):
        self._messages: list[dict] = []

    def add_message(self, role: str, content: str) -> None:
        self._messages.append({"role": role, "content": content})
        if len(self._messages) > MAX_MESSAGES:
            self._messages = self._messages[-MAX_MESSAGES:]

    def get_messages(self) -> list[dict]:
        """Return full conversation with system prompt prepended."""
        system = {"role": "system", "content": get_system_prompt()}
        return [system] + self._messages

    def clear(self) -> None:
        self._messages = []


class SessionStore:
    """In-memory session store with TTL-based expiry."""

    def __init__(self):
        self._sessions: dict[str, tuple[Memory, float]] = {}

    def get(self, session_id: str) -> Memory:
        self._evict()
        if session_id in self._sessions:
            mem, _ = self._sessions[session_id]
            self._sessions[session_id] = (mem, time.monotonic())
            return mem
        if len(self._sessions) >= MAX_SESSIONS:
            self._evict_oldest()
        mem = Memory()
        self._sessions[session_id] = (mem, time.monotonic())
        return mem

    def clear(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def _evict(self) -> None:
        cutoff = time.monotonic() - SESSION_TTL
        expired = [k for k, (_, ts) in self._sessions.items() if ts < cutoff]
        for k in expired:
            del self._sessions[k]

    def _evict_oldest(self) -> None:
        if not self._sessions:
            return
        oldest = min(self._sessions, key=lambda k: self._sessions[k][1])
        del self._sessions[oldest]
