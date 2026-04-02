import os

from openai import OpenAI, APIError, APIConnectionError, RateLimitError


_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set — add it to your .env file")
        _client = OpenAI(api_key=api_key)
    return _client


def chat(messages: list[dict]) -> str:
    """Send conversation history to OpenAI and return the assistant's response."""
    model = os.getenv("MODEL_NAME", "gpt-4o-mini")

    try:
        response = _get_client().chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.8,
        )
        return response.choices[0].message.content or ""
    except RateLimitError:
        return "meow... I'm being rate-limited. Give me a sec and try again 🐱"
    except APIConnectionError:
        return "Can't reach OpenAI right now. Internet might be napping like a cat 😿"
    except APIError as e:
        return f"meow meow... something went wrong with the API: {e.message}"
