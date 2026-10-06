"""Contract model tests against the frozen JSON Schemas."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from app.schemas import AgentConfig, CallResult

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"

AGENT_CONFIG_SAMPLE = {
    "version": 1,
    "owner": {"name": "Иван Петров", "company": "Пример"},
    "greeting": "Здравствуйте.",
    "disclosure": "Я AI-помощник, разговор обрабатывается.",
    "closing": "До свидания.",
    "routing": [{"id": "default", "priority": 10, "action": "take_message"}],
    "handoff_number": "+375000000000",
    "retention_days": 30,
    "store_audio": False,
    "notice_detail": "minimal",
}

CALL_RESULT_SAMPLE = {
    "call_id": "synthetic-call-1",
    "started_at": "2025-01-01T10:00:00Z",
    "ended_at": "2025-01-01T10:01:00Z",
    "caller": {"masked": "+375******123"},
    "transcript": [
        {
            "who": "caller",
            "text": "Синтетический запрос",
            "start_s": 0.1,
            "words": [{"w": "Синтетический", "p": 0.98}],
        }
    ],
    "intent": "client",
    "urgency": "normal",
    "slots": {"name": None, "company": None, "reason": "Синтетический запрос"},
    "summary_ru": "Синтетический звонок.",
    "action": "take_message",
}


def _validate_contract(schema_name: str, sample: dict[str, object]) -> None:
    schema = json.loads((CONTRACTS / schema_name).read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(sample)


def test_agent_config_model_matches_json_schema_sample() -> None:
    AgentConfig.model_validate(AGENT_CONFIG_SAMPLE)
    _validate_contract("agent_config.schema.json", AGENT_CONFIG_SAMPLE)


def test_call_result_model_matches_json_schema_sample() -> None:
    CallResult.model_validate(CALL_RESULT_SAMPLE)
    _validate_contract("call_result.schema.json", CALL_RESULT_SAMPLE)
