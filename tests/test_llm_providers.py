"""Tests for LLM provider layer."""

import json

# pyrefly: ignore [missing-import]
import pytest

from app.llm.base import BaseLLMProvider
from app.schemas.planner import PlannerResponseSchema


def test_parse_response_valid_json():
    """Valid JSON should parse into PlannerResponseSchema."""
    raw = json.dumps({
        "mode": "task_input",
        "status": "ok",
        "timezone": "Europe/Kyiv",
        "tasks": [
            {
                "title": "Test task",
                "details": "",
                "type": "other",
                "priority": 3,
                "estimated_minutes": 30,
                "deadline": {"date": None, "time": None, "kind": None},
                "fixed_time": {"date": None, "time": None},
                "weather_sensitive": False,
                "tags": [],
            }
        ],
        "schedule_suggestions": [],
        "warnings": [],
        "clarification_questions": [],
        "summary": "1 задача добавлена.",
    })
    result = BaseLLMProvider._parse_response(raw)
    assert isinstance(result, PlannerResponseSchema)
    assert len(result.tasks) == 1
    assert result.tasks[0].title == "Test task"


def test_parse_response_with_markdown_fences():
    """JSON wrapped in markdown fences should still parse."""
    raw = '```json\n{"mode":"task_input","status":"ok","tasks":[],"summary":"OK","timezone":"Europe/Kyiv","schedule_suggestions":[],"warnings":[],"clarification_questions":[]}\n```'
    result = BaseLLMProvider._parse_response(raw)
    assert isinstance(result, PlannerResponseSchema)
    assert result.summary == "OK"


def test_parse_response_invalid_json():
    """Invalid JSON should return error response, not crash."""
    raw = "this is not json at all"
    result = BaseLLMProvider._parse_response(raw)
    assert isinstance(result, PlannerResponseSchema)
    assert len(result.warnings) > 0


def test_parse_response_partial_schema():
    """Partial but valid JSON should still parse (Pydantic defaults)."""
    raw = json.dumps({"mode": "task_input", "status": "ok", "summary": "Test"})
    result = BaseLLMProvider._parse_response(raw)
    assert result.summary == "Test"
    assert result.tasks == []


def test_factory_invalid_provider():
    """Unknown provider should raise ValueError."""
    from unittest.mock import MagicMock
    from app.llm.factory import get_llm_provider

    mock_settings = MagicMock()
    mock_settings.llm_provider = "unknown_provider"

    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_llm_provider(mock_settings)
