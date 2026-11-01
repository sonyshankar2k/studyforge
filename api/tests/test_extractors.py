"""Extractor and text tests. The Claude extractor is tested with a fake client: no API calls."""

from types import SimpleNamespace

import anthropic
import httpx
import pytest

from app.config import settings
from app.digitize.errors import PermanentJobError, TransientJobError
from app.digitize.extractors import ClaudeExtractor, RulesExtractor, get_extractor
from app.digitize.text import extract_text

PROTOCOL_TEXT = """
Treatment Arms
Arm A: SF-202 20 mg once daily (N=200)
Arm B: Active comparator fluticasone 250 mcg twice daily (N=200)
Arm C: Matching placebo once daily (N=100)
Primary objective: Evaluate efficacy versus placebo
Endpoint: Change from baseline in FEV1 at Week 24
"""


def _http_error(cls, status: int):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("error", response=httpx.Response(status, request=request), body=None)


class FakeMessages:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


def fake_client(result=None, error=None):
    return SimpleNamespace(messages=FakeMessages(result, error))


def tool_response(payload: dict):
    return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input=payload)])


# ------------------------------------------------------------------ rules


async def test_rules_extractor_reads_arms_doses_and_sizes():
    result = await RulesExtractor().extract(PROTOCOL_TEXT)
    assert [(a.arm_type, a.dose, a.planned_size) for a in result.arms] == [
        ("experimental", "20 mg once daily", 200),
        ("active_comparator", "250 mcg twice daily", 200),
        ("placebo", None, 100),
    ]
    assert result.objectives[0].endpoint == "Change from baseline in FEV1 at Week 24"


async def test_rules_extractor_explains_when_it_finds_nothing():
    result = await RulesExtractor().extract("An unstructured protocol with no recognizable lines.")
    assert result.arms == [] and result.objectives == []
    assert "ANTHROPIC_API_KEY" in result.notes


# ------------------------------------------------------------------ Claude


async def test_claude_extractor_forces_a_structured_tool_call():
    payload = {
        "arms": [{"name": "SF-202 20 mg", "arm_type": "experimental", "dose": "20 mg once daily"}],
        "objectives": [
            {"level": "primary", "description": "Efficacy", "endpoint": "FEV1 at Week 24"}
        ],
    }
    client = fake_client(result=tool_response(payload))
    result = await ClaudeExtractor(client).extract(PROTOCOL_TEXT)

    assert result.arms[0].dose == "20 mg once daily"
    call = client.messages.calls[0]
    assert call["tool_choice"] == {"type": "tool", "name": "record_protocol"}
    assert call["tools"][0]["input_schema"]["properties"].keys() >= {"arms", "objectives"}
    assert PROTOCOL_TEXT in call["messages"][0]["content"]


@pytest.mark.parametrize(
    "error",
    [
        _http_error(anthropic.RateLimitError, 429),
        _http_error(anthropic.InternalServerError, 500),
        anthropic.APITimeoutError(request=httpx.Request("POST", "https://api.anthropic.com")),
    ],
)
async def test_claude_temporary_errors_are_transient(error):
    with pytest.raises(TransientJobError):
        await ClaudeExtractor(fake_client(error=error)).extract("text")


async def test_claude_bad_request_is_permanent():
    error = _http_error(anthropic.AuthenticationError, 401)
    with pytest.raises(PermanentJobError):
        await ClaudeExtractor(fake_client(error=error)).extract("text")


async def test_claude_output_that_breaks_the_schema_is_retried():
    bad = tool_response({"arms": [{"name": "X", "arm_type": "not-a-type"}]})
    with pytest.raises(TransientJobError):
        await ClaudeExtractor(fake_client(result=bad)).extract("text")


# ------------------------------------------------------------------ selection + text


def test_extractor_selection(monkeypatch):
    monkeypatch.setattr(settings, "extractor", "auto")
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    assert get_extractor().name == "rules"

    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test")
    assert get_extractor().name == "claude"

    monkeypatch.setattr(settings, "extractor", "claude")
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    with pytest.raises(PermanentJobError):
        get_extractor()


def test_text_extraction_rejects_empty_and_broken_files():
    with pytest.raises(PermanentJobError):
        extract_text(b"   ", "text/plain", "blank.txt")
    with pytest.raises(PermanentJobError):
        extract_text(b"%PDF-1.4 not really", "application/pdf", "broken.pdf")
