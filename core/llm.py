import os

from openai import AsyncOpenAI, APIError, APIConnectionError, RateLimitError

PROVIDERS = {
    "openai":     {"env_key": "OPENAI_API_KEY",     "base_url": None},
    "groq":       {"env_key": "GROQ_API_KEY",       "base_url": "https://api.groq.com/openai/v1"},
    "together":   {"env_key": "TOGETHER_API_KEY",    "base_url": "https://api.together.xyz/v1"},
    "openrouter": {"env_key": "OPENROUTER_API_KEY",  "base_url": "https://openrouter.ai/api/v1"},
    "ollama":     {"env_key": None,                  "base_url": "http://localhost:11434/v1"},
}

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        provider = os.getenv("LLM_PROVIDER", "ollama").lower()
        cfg = PROVIDERS.get(provider)
        if not cfg:
            raise RuntimeError(f"Unknown LLM_PROVIDER: {provider}. Options: {', '.join(PROVIDERS)}")

        api_key = "ollama"  # default dummy key
        if cfg["env_key"]:
            api_key = os.getenv(cfg["env_key"], "")
            if not api_key:
                raise RuntimeError(f"{cfg['env_key']} not set — add it to secrets.zsh")

        _client = AsyncOpenAI(api_key=api_key, base_url=cfg["base_url"])
    return _client


async def chat(messages: list[dict]) -> str:
    """Send conversation history and return the assistant's response."""
    model = os.getenv("MODEL_NAME", "gpt-4o-mini")

    try:
        response = await _get_client().chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.8,
        )
        if not response.choices:
            return "meow... the AI returned nothing. Try again? 🐱"
        return response.choices[0].message.content or ""
    except RateLimitError:
        return "meow... I'm being rate-limited. Give me a sec and try again 🐱"
    except APIConnectionError:
        provider = os.getenv("LLM_PROVIDER", "ollama")
        return f"Can't reach {provider} right now. Internet might be napping like a cat 😿"
    except APIError as e:
        return f"meow meow... something went wrong with the API: {e.message}"
