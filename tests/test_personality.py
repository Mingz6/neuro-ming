import hashlib
import re

from core.personality import SYSTEM_PROMPT, get_system_prompt

# The persona is public, so private names must never appear in it. The names are
# stored as SHA-256 hashes so this file does not spell them out either.
BANNED_WORD_HASHES = {
    "e010fd1ce1acc173e3b4835b7635f8d4600d774869102adb5cb7b5d7895649ba",
    "7ebf0e757e754ce6759aa1d048186379a7b0d6128696391441ade76b158ee7aa",
    "502913bfdd49eab564282dff101e6d167321237eeec66eedb2a438ed80fdeaa0",
    "10d6208a67b9f47ac1e641df47ec525fdf533b52a756504d96c248d1351c2d71",
}


def test_prompt_is_the_module_constant():
    assert get_system_prompt() == SYSTEM_PROMPT
    assert SYSTEM_PROMPT.startswith("You are Neuro-Ming")


def test_prompt_keeps_the_voice_rules():
    assert "The NEVER list" in SYSTEM_PROMPT
    assert "Never pretend to be human" in SYSTEM_PROMPT


def test_prompt_has_no_private_names():
    words = set(re.findall(r"[a-z]+", SYSTEM_PROMPT.lower()))
    hashes = {hashlib.sha256(w.encode()).hexdigest() for w in words}
    assert not hashes & BANNED_WORD_HASHES


def test_prompt_has_no_contact_details():
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", SYSTEM_PROMPT)
    assert not re.search(r"\b\d{3}[- .]\d{3}[- .]\d{4}\b", SYSTEM_PROMPT)
