import json
from types import SimpleNamespace

import httpx
import pytest
from openai import APIConnectionError, APIError, AsyncAzureOpenAI, AsyncOpenAI, RateLimitError

from core import llm


# --- provider selection ---

def test_default_provider_is_local_ollama():
    client = llm._get_client()
    assert isinstance(client, AsyncOpenAI)
    assert str(client.base_url).startswith("http://localhost:11434/v1")


@pytest.mark.parametrize(
    "provider, key_var, host",
    [
        ("openai", "OPENAI_API_KEY", "api.openai.com"),
        ("groq", "GROQ_API_KEY", "api.groq.com"),
        ("together", "TOGETHER_API_KEY", "api.together.xyz"),
        ("openrouter", "OPENROUTER_API_KEY", "openrouter.ai"),
    ],
)
def test_keyed_providers_use_their_own_base_url(monkeypatch, provider, key_var, host):
    monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.setenv(key_var, "test-key")
    client = llm._get_client()
    assert host in str(client.base_url)
    assert client.api_key == "test-key"


def test_provider_name_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "GROQ")
    monkeypatch.setenv("GROQ_API_KEY", "k")
    assert "groq" in str(llm._get_client().base_url)


def test_keyed_provider_without_key_fails_loudly(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        llm._get_client()


def test_unknown_provider_lists_the_options(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "skynet")
    with pytest.raises(RuntimeError, match="Unknown LLM_PROVIDER: skynet") as exc:
        llm._get_client()
    for name in llm.PROVIDERS:
        assert name in str(exc.value)


def test_azure_needs_key_and_endpoint(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "azure-openai")
    with pytest.raises(RuntimeError, match="AZURE_OPENAI_API_KEY"):
        llm._get_client()


def test_azure_builds_the_azure_client(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "azure-openai")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "k")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.invalid")
    assert isinstance(llm._get_client(), AsyncAzureOpenAI)


def test_client_is_built_once(monkeypatch):
    first = llm._get_client()
    monkeypatch.setenv("LLM_PROVIDER", "skynet")  # ignored: the client is cached
    assert llm._get_client() is first


def test_six_providers():
    assert sorted(llm.PROVIDERS) == [
        "azure-openai", "groq", "ollama", "openai", "openrouter", "together",
    ]


# --- fallback model order ---

def test_fallback_default_is_the_neuro_ming_deployment():
    assert llm._fallback_models("gpt-5.4") == ["gpt-5.4", "neuro-ming-gpt"]


def test_fallback_list_is_deduped_and_primary_stays_first(monkeypatch):
    monkeypatch.setenv("LLM_FALLBACK_MODELS", "gpt-4.1, gpt-5.4 ,, gpt-4.1")
    assert llm._fallback_models("gpt-5.4") == ["gpt-5.4", "gpt-4.1"]


# --- chat() with a fake client ---

class FakeCompletions:
    """Stands in for client.chat.completions. Each script entry is a reply or an exception."""

    def __init__(self, script):
        self.script = list(script)
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def install_fake(monkeypatch, *script):
    completions = FakeCompletions(script)
    fake = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    monkeypatch.setattr(llm, "_client", fake)
    return completions


def reply(text, prompt_tokens=10, completion_tokens=5):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


def api_error(message):
    request = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
    return APIError(message, request=request, body=None)


MESSAGES = [{"role": "user", "content": "hi"}]


async def test_chat_returns_the_reply_text(monkeypatch):
    calls = install_fake(monkeypatch, reply("hey"))
    monkeypatch.setenv("MODEL_NAME", "llama3.1")
    assert await llm.chat(MESSAGES) == "hey"
    assert calls.calls[0]["model"] == "llama3.1"
    assert calls.calls[0]["messages"] == MESSAGES


async def test_chat_sets_temperature_except_for_gpt5(monkeypatch):
    calls = install_fake(monkeypatch, reply("a"), reply("b"))
    monkeypatch.setenv("MODEL_NAME", "llama3.1")
    await llm.chat(MESSAGES)
    monkeypatch.setenv("MODEL_NAME", "gpt-5.4")
    await llm.chat(MESSAGES)
    assert calls.calls[0]["temperature"] == 0.8
    assert "temperature" not in calls.calls[1]


async def test_chat_handles_empty_choices(monkeypatch):
    install_fake(monkeypatch, SimpleNamespace(choices=[], usage=None))
    assert "returned nothing" in await llm.chat(MESSAGES)


async def test_chat_turns_none_content_into_empty_string(monkeypatch):
    install_fake(monkeypatch, reply(None))
    assert await llm.chat(MESSAGES) == ""


async def test_azure_falls_back_when_the_deployment_is_missing(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "azure-openai")
    monkeypatch.setenv("MODEL_NAME", "gpt-5.4")
    calls = install_fake(
        monkeypatch,
        api_error("The API deployment for this resource does not exist"),
        reply("from the fallback"),
    )
    assert await llm.chat(MESSAGES) == "from the fallback"
    assert [c["model"] for c in calls.calls] == ["gpt-5.4", "neuro-ming-gpt"]


async def test_azure_does_not_retry_other_api_errors(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "azure-openai")
    monkeypatch.setenv("MODEL_NAME", "gpt-5.4")
    calls = install_fake(monkeypatch, api_error("content filter tripped"), reply("never used"))
    out = await llm.chat(MESSAGES)
    assert "content filter tripped" in out
    assert len(calls.calls) == 1


async def test_azure_call_writes_a_cost_record(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_PROVIDER", "azure-openai")
    monkeypatch.setenv("MODEL_NAME", "neuro-ming-gpt")
    install_fake(monkeypatch, reply("hey", prompt_tokens=1000, completion_tokens=200))
    await llm.chat(MESSAGES)
    [log_file] = list((tmp_path / "logs").glob("ai-cost-*.jsonl"))
    record = json.loads(log_file.read_text().strip())
    assert record["model"] == "gpt-5.4"
    assert record["prompt_tokens"] == 1000
    assert record["cost_usd"] == pytest.approx(0.0055)


async def test_other_providers_write_no_cost_record(monkeypatch, tmp_path):
    install_fake(monkeypatch, reply("hey"))
    await llm.chat(MESSAGES)
    assert not (tmp_path / "logs").exists()


async def test_rate_limit_becomes_a_friendly_message(monkeypatch):
    request = httpx.Request("POST", "https://example.invalid")
    response = httpx.Response(429, request=request)
    install_fake(monkeypatch, RateLimitError("slow down", response=response, body=None))
    assert "rate-limited" in await llm.chat(MESSAGES)


async def test_connection_failure_names_the_provider(monkeypatch):
    request = httpx.Request("POST", "https://example.invalid")
    install_fake(monkeypatch, APIConnectionError(request=request))
    assert "Can't reach ollama" in await llm.chat(MESSAGES)


async def test_unexpected_exception_never_escapes(monkeypatch):
    install_fake(monkeypatch, ValueError("boom"))
    assert "something unexpected broke" in await llm.chat(MESSAGES)
