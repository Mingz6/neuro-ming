from core.personality import get_system_prompt

MAX_MESSAGES = 20


class Memory:
    def __init__(self):
        self._messages: list[dict] = []

    def add_message(self, role: str, content: str) -> None:
        self._messages.append({"role": role, "content": content})
        # Sliding window — keep system prompt + last N messages
        if len(self._messages) > MAX_MESSAGES:
            self._messages = self._messages[-MAX_MESSAGES:]

    def get_messages(self) -> list[dict]:
        """Return full conversation with system prompt prepended."""
        system = {"role": "system", "content": get_system_prompt()}
        return [system] + self._messages

    def clear(self) -> None:
        self._messages = []
