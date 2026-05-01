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


def _fallback_models(primary: str) -> list[str]:
    raw = os.getenv("LLM_FALLBACK_MODELS", "gpt-5.4")
    fallbacks = [m.strip() for m in raw.split(",") if m.strip()]
    ordered = [primary, *fallbacks]

    deduped: list[str] = []
    seen: set[str] = set()
    for m in ordered:
        if m in seen:
            continue
        seen.add(m)
        deduped.append(m)
    return deduped


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
    primary_model = os.getenv("MODEL_NAME", "gpt-5.4")
    provider = os.getenv("LLM_PROVIDER", "ollama")
    models_to_try = _fallback_models(primary_model) if provider == "azure-openai" else [primary_model]

    try:
        last_api_error: APIError | None = None
        for model in models_to_try:
            kwargs: dict = {
                "model": model,
                "messages": messages,
            }
            # GPT-5.x models only support default temperature
            if not model.startswith("gpt-5"):
                kwargs["temperature"] = 0.8

            try:
                response = await _get_client().chat.completions.create(**kwargs)
                if not response.choices:
                    return "meow... the AI returned nothing. Try again? 🐱"
                return response.choices[0].message.content or ""
            except APIError as e:
                last_api_error = e
                msg = (e.message or "").lower()
                retryable_model_error = (
                    "could not find an existing deployment" in msg
                    or "deploymentnotfound" in msg
                    or "does not exist" in msg
                    or "unsupported" in msg
                )
                if provider == "azure-openai" and retryable_model_error and model != models_to_try[-1]:
                    logger.warning(
                        "LLM deployment/model '%s' failed, retrying fallback '%s'",
                        model,
                        models_to_try[models_to_try.index(model) + 1],
                    )
                    continue
                raise

        if last_api_error:
            raise last_api_error
        return "meow... no model could answer right now. Try again? 🐱"
    except RateLimitError:
        logger.warning("LLM rate-limited (provider=%s, model=%s)", provider, models_to_try[0])
        return "meow... I'm being rate-limited. Give me a sec and try again 🐱"
    except APIConnectionError:
        logger.warning("LLM connection failed (provider=%s)", provider)
        return f"Can't reach {provider} right now. Internet might be napping like a cat 😿"
    except APIError as e:
        logger.error("LLM API error (provider=%s, model=%s): %s", provider, models_to_try[0], e.message)
        return f"meow meow... something went wrong with the API: {e.message}"
    except Exception:
        logger.exception("LLM unexpected failure (provider=%s, model=%s)", provider, models_to_try[0])
        return "meow... something unexpected broke. Try again? 🐱"
