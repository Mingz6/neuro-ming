import logging
import os

from openai import AsyncAzureOpenAI, AsyncOpenAI, APIError, APIConnectionError, RateLimitError

logger = logging.getLogger(__name__)

PROVIDERS = {
    "openai":       {"env_key": "OPENAI_API_KEY",     "base_url": None},
    "groq":         {"env_key": "GROQ_API_KEY",       "base_url": "https://api.groq.com/openai/v1"},
    "together":     {"env_key": "TOGETHER_API_KEY",    "base_url": "https://api.together.xyz/v1"},
    "openrouter":   {"env_key": "OPENROUTER_API_KEY",  "base_url": "https://openrouter.ai/api/v1"},
    "ollama":       {"env_key": None,                  "base_url": "http://localhost:11434/v1"},
    "azure-openai": {"env_key": "AZURE_OPENAI_API_KEY", "base_url": None},
}

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        provider = os.getenv("LLM_PROVIDER", "ollama").lower()
        cfg = PROVIDERS.get(provider)
        if not cfg:
            raise RuntimeError(f"Unknown LLM_PROVIDER: {provider}. Options: {', '.join(PROVIDERS)}")

        if provider == "azure-openai":
            api_key = os.getenv("AZURE_OPENAI_API_KEY", "")
            endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
            if not api_key or not endpoint:
                raise RuntimeError("AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT must be set")
            _client = AsyncAzureOpenAI(
                api_key=api_key,
                azure_endpoint=endpoint,
                api_version="2025-01-01-preview",
            )
        else:
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
        kwargs: dict = {
            "model": model,
            "messages": messages,
        }
        # GPT-5.x models only support default temperature
        if not model.startswith("gpt-5"):
            kwargs["temperature"] = 0.8

        response = await _get_client().chat.completions.create(**kwargs)
        if not response.choices:
            return "meow... the AI returned nothing. Try again? 🐱"
        return response.choices[0].message.content or ""
    except RateLimitError:
        logger.warning("LLM rate-limited (provider=%s, model=%s)", os.getenv("LLM_PROVIDER", "ollama"), model)
        return "meow... I'm being rate-limited. Give me a sec and try again 🐱"
    except APIConnectionError:
        provider = os.getenv("LLM_PROVIDER", "ollama")
        logger.warning("LLM connection failed (provider=%s)", provider)
        return f"Can't reach {provider} right now. Internet might be napping like a cat 😿"
    except APIError as e:
        logger.error("LLM API error (provider=%s, model=%s): %s", os.getenv("LLM_PROVIDER", "ollama"), model, e.message)
        return f"meow meow... something went wrong with the API: {e.message}"
    except Exception:
        logger.exception("LLM unexpected failure (provider=%s, model=%s)", os.getenv("LLM_PROVIDER", "ollama"), model)
        return "meow... something unexpected broke. Try again? 🐱"
