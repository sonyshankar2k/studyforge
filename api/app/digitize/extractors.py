"""Extractors turn protocol text into an ExtractedProtocol.

ClaudeExtractor   asks Claude, forcing a tool call whose input schema IS our Pydantic
                  model, so the answer comes back as validated structured data.
RulesExtractor    a free, offline, heuristic parser. Good enough for the sample
                  protocol and for tests; real protocols should use Claude.
"""

import re
from typing import Protocol

import anthropic
from pydantic import ValidationError

from app.config import settings
from app.digitize.errors import PermanentJobError, TransientJobError
from app.digitize.schema import ExtractedArm, ExtractedObjective, ExtractedProtocol
from app.models import ArmType, ObjectiveLevel


class Extractor(Protocol):
    name: str

    async def extract(self, text: str) -> ExtractedProtocol: ...


# ----------------------------------------------------------------------------- Claude

SYSTEM_PROMPT = """You extract study design elements from clinical trial protocols.

Rules:
- Report only what the protocol states. Never invent arms, doses, sizes or endpoints.
- arm_type: "placebo" for placebo/sham arms, "active_comparator" for an approved
  comparator or standard of care, otherwise "experimental".
- Copy doses with their units and frequency, e.g. "20 mg once daily".
- planned_size is the number of participants planned for that arm, if stated.
- Each objective needs the endpoint used to measure it.
- Put anything ambiguous in notes so a human reviewer can check it.
Call the record_protocol tool exactly once."""

TOOL_NAME = "record_protocol"


class ClaudeExtractor:
    name = "claude"

    def __init__(self, client: anthropic.AsyncAnthropic | None = None) -> None:
        self.client = client or anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.claude_timeout_seconds,
            max_retries=0,  # our worker owns retries, with backoff and visible progress
        )

    async def extract(self, text: str) -> ExtractedProtocol:
        try:
            response = await self.client.messages.create(
                model=settings.claude_model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=[
                    {
                        "name": TOOL_NAME,
                        "description": "Record the arms and objectives found in the protocol.",
                        "input_schema": ExtractedProtocol.model_json_schema(),
                    }
                ],
                tool_choice={"type": "tool", "name": TOOL_NAME},
                messages=[
                    {
                        "role": "user",
                        "content": f"<protocol>\n{text}\n</protocol>\n\n"
                        "Extract the study arms and objectives.",
                    }
                ],
            )
        except (
            anthropic.RateLimitError,
            anthropic.APITimeoutError,
            anthropic.APIConnectionError,
            anthropic.InternalServerError,
        ) as exc:
            raise TransientJobError(
                f"Claude is temporarily unavailable ({exc.__class__.__name__})"
            ) from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500 or exc.status_code == 529:
                raise TransientJobError(f"Claude returned {exc.status_code}") from exc
            raise PermanentJobError(f"Claude rejected the request ({exc.status_code})") from exc

        tool_input = next(
            (block.input for block in response.content if block.type == "tool_use"), None
        )
        if tool_input is None:
            raise TransientJobError("Claude did not return structured data")
        try:
            return ExtractedProtocol.model_validate(tool_input)
        except ValidationError as exc:
            # Occasionally a model output doesn't fit the schema; a fresh try usually does.
            raise TransientJobError("Claude's answer did not match the expected format") from exc


# ----------------------------------------------------------------------------- Rules

ARM_LINE = re.compile(r"^\s*(?:Arm|Treatment group|Group)\s*[A-Z0-9]{0,3}\s*[:\-–]\s*(.+)$", re.I)
OBJECTIVE_LINE = re.compile(
    r"^\s*(Primary|Secondary|Exploratory)\s+objective\s*\d*\s*[:\-–]\s*(.+)$", re.I
)
ENDPOINT_LINE = re.compile(r"^\s*(?:Endpoint|Outcome measure)\s*[:\-–]\s*(.+)$", re.I)
DOSE = re.compile(r"(\d+(?:\.\d+)?\s*(?:mg/kg|mg|mcg|µg|g|mL|IU|units)\b[^;,()\n]*)", re.I)
SIZE = re.compile(r"(?:\bN\s*=\s*(\d+))|(?:(\d+)\s+(?:participants|subjects|patients))", re.I)


class RulesExtractor:
    """Reads lines like 'Arm A: SF-202 20 mg once daily (N=150)' and
    'Primary objective: ...' followed by 'Endpoint: ...'."""

    name = "rules"

    async def extract(self, text: str) -> ExtractedProtocol:
        arms: list[ExtractedArm] = []
        objectives: list[ExtractedObjective] = []
        pending: tuple[ObjectiveLevel, str] | None = None

        for raw in text.splitlines():
            line = " ".join(raw.split())
            if not line:
                continue

            if m := ARM_LINE.match(line):
                arms.append(_parse_arm(m.group(1)))
            elif m := OBJECTIVE_LINE.match(line):
                pending = (ObjectiveLevel(m.group(1).lower()), m.group(2).strip())
            elif (m := ENDPOINT_LINE.match(line)) and pending:
                level, description = pending
                objectives.append(
                    ExtractedObjective(
                        level=level, description=description, endpoint=m.group(1).strip()
                    )
                )
                pending = None

        notes = None
        if not arms and not objectives:
            notes = (
                "The rule-based parser found nothing. It only understands simple "
                "'Arm A: ...' / 'Primary objective: ...' layouts; set ANTHROPIC_API_KEY "
                "to use Claude for real protocols."
            )
        return ExtractedProtocol(arms=arms, objectives=objectives, notes=notes)


def _parse_arm(text: str) -> ExtractedArm:
    lowered = text.lower()
    if "placebo" in lowered or "sham" in lowered:
        arm_type = ArmType.PLACEBO
    elif "comparator" in lowered or "standard of care" in lowered:
        arm_type = ArmType.ACTIVE_COMPARATOR
    else:
        arm_type = ArmType.EXPERIMENTAL

    dose_match = DOSE.search(text)
    size_match = SIZE.search(text)
    planned = next((int(g) for g in size_match.groups() if g), None) if size_match else None

    # Name = text before the first "(" or ",", without the size note.
    name = re.split(r"[(,;]", text, maxsplit=1)[0].strip()
    name = SIZE.sub("", name).strip(" -–") or text.strip()

    return ExtractedArm(
        name=name[:200],
        arm_type=arm_type,
        dose=dose_match.group(1).strip()[:100]
        if dose_match and arm_type != ArmType.PLACEBO
        else None,
        planned_size=planned,
        description=text.strip(),
    )


def get_extractor() -> Extractor:
    choice = settings.extractor
    if choice == "claude" or (choice == "auto" and settings.anthropic_api_key):
        if not settings.anthropic_api_key:
            raise PermanentJobError("EXTRACTOR=claude but ANTHROPIC_API_KEY is not set")
        return ClaudeExtractor()
    return RulesExtractor()
