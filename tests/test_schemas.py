"""Contract model tests against the frozen JSON Schemas."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError as JSONSchemaValidationError
from pydantic import ValidationError as PydanticValidationError

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
    "handoff": {"performed": True},
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


@pytest.mark.parametrize(
    ("model", "schema_name", "sample", "path"),
    [
        (AgentConfig, "agent_config.schema.json", AGENT_CONFIG_SAMPLE, ("owner", "role")),
        (AgentConfig, "agent_config.schema.json", AGENT_CONFIG_SAMPLE, ("routing", 0, "when")),
        (AgentConfig, "agent_config.schema.json", AGENT_CONFIG_SAMPLE, ("working_hours",)),
        (CallResult, "call_result.schema.json", CALL_RESULT_SAMPLE, ("caller", "hash")),
        (CallResult, "call_result.schema.json", CALL_RESULT_SAMPLE, ("transcript", 0, "words")),
        (CallResult, "call_result.schema.json", CALL_RESULT_SAMPLE, ("handoff", "performed")),
        (CallResult, "call_result.schema.json", CALL_RESULT_SAMPLE, ("duration_s",)),
    ],
)
def test_optional_nonnullable_fields_reject_null(
    model: type[AgentConfig] | type[CallResult],
    schema_name: str,
    sample: dict[str, object],
    path: tuple[str | int, ...],
) -> None:
    invalid_sample = deepcopy(sample)
    target = invalid_sample
    for key in path[:-1]:
        target = target[key]  # type: ignore[index]
    target[path[-1]] = None  # type: ignore[index]

    with pytest.raises(PydanticValidationError):
        model.model_validate(invalid_sample)
    with pytest.raises(JSONSchemaValidationError):
        _validate_contract(schema_name, invalid_sample)
