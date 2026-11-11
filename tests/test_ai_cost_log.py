import json

import pytest

from core import ai_cost_log
from core.ai_cost_log import calculate_cost, log_call


def test_known_model_cost():
    usd, cad = calculate_cost("gpt-5.4", 1_000_000, 1_000_000)
    assert usd == pytest.approx(17.5)
    assert cad == pytest.approx(17.5 * ai_cost_log.CAD_RATE)


def test_deployment_alias_bills_at_the_gpt_5_4_rate():
    assert calculate_cost("neuro-ming-gpt", 1_000_000, 0)[0] == pytest.approx(2.5)


def test_longest_prefix_wins():
    # "gpt-5.4-mini-2026" must price as gpt-5.4-mini, not gpt-5.4.
    assert calculate_cost("gpt-5.4-mini-2026", 1_000_000, 0)[0] == pytest.approx(0.75)


def test_unknown_model_costs_zero():
    assert calculate_cost("mystery-model", 500, 500) == (0.0, 0.0)


def test_log_call_appends_one_json_line_per_call(tmp_path):
    log_call(deployment="gpt-5.4", prompt_tokens=100, completion_tokens=50, duration_ms=12)
    log_call(deployment="gpt-5.4", operation="tts", status="error")
    [log_file] = list((tmp_path / "logs").glob("ai-cost-*.jsonl"))
    rows = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert [r["operation"] for r in rows] == ["chat", "tts"]
    assert rows[0]["app"] == "neuro-ming"
    assert rows[0]["duration_ms"] == 12
    assert rows[1]["status"] == "error"


def test_log_call_survives_an_unwritable_directory(monkeypatch, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a directory")
    monkeypatch.setattr(ai_cost_log, "LOG_DIR", blocker / "logs")
    log_call(deployment="gpt-5.4")  # must not raise
