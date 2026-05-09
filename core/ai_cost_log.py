"""AI cost logger for neuro-ming.

Writes per-call JSONL records to logs/ai-cost-YYYY-MM.jsonl.
Same schema as worker-center's ai_cost_log.py — the collector reads both.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

PRICING: dict[str, dict[str, float]] = {
    "gpt-5.4-pro": {"input": 30.0, "output": 180.0},
    "gpt-5.4": {"input": 2.50, "output": 15.0},
    "gpt-5.4-mini": {"input": 0.75, "output": 4.50},
    "gpt-5.3-chat": {"input": 1.75, "output": 14.0},
}

DEPLOYMENT_TO_MODEL: dict[str, str] = {
    "neuro-ming-gpt": "gpt-5.4-pro",
}

CAD_RATE = 1.38
LOG_DIR = Path(os.environ.get("AI_COST_LOG_DIR", "logs"))


def _resolve_model(deployment: str) -> str:
    return DEPLOYMENT_TO_MODEL.get(deployment.lower(), deployment.lower())


def _find_pricing(model: str) -> dict[str, float] | None:
    if model in PRICING:
        return PRICING[model]
    candidates = [k for k in PRICING if model.startswith(k) or k.startswith(model)]
    if candidates:
        return PRICING[max(candidates, key=len)]
    return None


def calculate_cost(deployment: str, prompt_tokens: int, completion_tokens: int) -> tuple[float, float]:
    model = _resolve_model(deployment)
    pricing = _find_pricing(model)
    if not pricing:
        return 0.0, 0.0
    usd = (prompt_tokens / 1e6) * pricing["input"] + (completion_tokens / 1e6) * pricing["output"]
    return round(usd, 6), round(usd * CAD_RATE, 6)


def log_call(
    *,
    deployment: str,
    operation: str = "chat",
    ref: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    duration_ms: int = 0,
    status: str = "ok",
) -> None:
    cost_usd, cost_cad = calculate_cost(deployment, prompt_tokens, completion_tokens)
    model = _resolve_model(deployment)
    now = datetime.now(timezone.utc)

    record = {
        "ts": now.isoformat(timespec="milliseconds"),
        "app": "neuro-ming",
        "deployment": deployment,
        "model": model,
        "operation": operation,
        "ref": ref,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cost_usd": cost_usd,
        "cost_cad": cost_cad,
        "duration_ms": duration_ms,
        "status": status,
    }

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = LOG_DIR / f"ai-cost-{now.strftime('%Y-%m')}.jsonl"
        with open(log_file, "a") as f:
            f.write(json.dumps(record) + "\n")
    except OSError as e:
        log.warning("Failed to write ai-cost log: %s", e)
