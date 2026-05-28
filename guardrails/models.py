"""
Pydantic models for the LLM Guardrails Gateway.

Defines request/response schemas and guardrail result structures.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class GuardrailStatus(str, Enum):
    """Overall status after guardrail evaluation."""
    PASSED = "passed"
    BLOCKED = "blocked"
    FILTERED = "filtered"


class CheckType(str, Enum):
    """Categories of guardrail checks."""
    PII_DETECTION = "pii_detection"
    PROMPT_INJECTION = "prompt_injection"
    MAX_LENGTH = "max_length"
    BLOCKED_TOPIC = "blocked_topic"
    BLOCKED_PHRASE = "blocked_phrase"
    TOXICITY = "toxicity"
    TOPIC_ADHERENCE = "topic_adherence"
    SCHEMA_VALIDATION = "schema_validation"
    OUTPUT_LENGTH = "output_length"


# ---------------------------------------------------------------------------
# Guardrail Result
# ---------------------------------------------------------------------------

class GuardrailResult(BaseModel):
    """Result of a single guardrail check."""
    check_name: str = Field(..., description="Human-readable name of the check")
    check_type: CheckType = Field(..., description="Category of the check")
    passed: bool = Field(..., description="Whether the check passed")
    message: Optional[str] = Field(None, description="Detail message (set on failure)")
    matched_pattern: Optional[str] = Field(
        None, description="The pattern that triggered the block, if any"
    )


# ---------------------------------------------------------------------------
# API Request / Response
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    """Incoming chat request from the user."""
    prompt: str = Field(
        ...,
        description="The user's prompt to send to the LLM",
        min_length=1,
    )
    session_id: Optional[str] = Field(
        None, description="Optional session identifier for context"
    )
    output_schema: Optional[dict[str, Any]] = Field(
        None,
        description="Optional JSON schema to validate the LLM output against "
                    "(overrides the policy-level schema)",
    )


class ChatResponse(BaseModel):
    """Response returned to the user after guardrail evaluation."""
    status: GuardrailStatus = Field(..., description="Overall guardrail status")
    response: Optional[str] = Field(
        None, description="LLM response text (None if blocked at input)"
    )
    input_guardrails: list[GuardrailResult] = Field(
        default_factory=list, description="Results of input guardrail checks"
    )
    output_guardrails: list[GuardrailResult] = Field(
        default_factory=list, description="Results of output guardrail checks"
    )
    retries_used: int = Field(
        0, description="Number of LLM retries due to output violations"
    )
    message: Optional[str] = Field(
        None, description="User-facing summary message"
    )
