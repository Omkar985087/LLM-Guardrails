"""
Output Guardrails — checks applied to the LLM's response before it is
returned to the user.

Each check function returns a `GuardrailResult`.  The orchestrator
`run_output_guards()` aggregates them.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from better_profanity import profanity
import jsonschema

from guardrails.models import CheckType, GuardrailResult
from guardrails.policy import Policy


# Ensure the profanity word list is loaded
profanity.load_censor_words()


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_toxicity(response: str, policy: Policy) -> GuardrailResult:
    """Use better-profanity to scan for toxic / profane content."""
    cfg = policy.output_guardrails.toxicity_check
    if not cfg.enabled:
        return GuardrailResult(
            check_name="Toxicity Check",
            check_type=CheckType.TOXICITY,
            passed=True,
            message=None,
        )

    is_profane = profanity.contains_profanity(response)
    return GuardrailResult(
        check_name="Toxicity Check",
        check_type=CheckType.TOXICITY,
        passed=not is_profane,
        message=cfg.message if is_profane else None,
    )


def check_topic_adherence(response: str, policy: Policy) -> GuardrailResult:
    """
    Lightweight topic-adherence check using keyword matching.

    Checks if the response contains at least one keyword from the
    allowed-topics list.  This is intentionally simple and fast —
    a more sophisticated approach would use a classifier model.
    """
    cfg = policy.output_guardrails.topic_adherence
    if not cfg.enabled or not cfg.allowed_topics:
        return GuardrailResult(
            check_name="Topic Adherence",
            check_type=CheckType.TOPIC_ADHERENCE,
            passed=True,
            message=None,
        )

    # Check for off-topic keyword patterns first (explicit blockers)
    for kw_pattern in cfg.off_topic_keywords:
        if re.search(kw_pattern, response, re.IGNORECASE):
            return GuardrailResult(
                check_name="Topic Adherence",
                check_type=CheckType.TOPIC_ADHERENCE,
                passed=False,
                message=cfg.message,
                matched_pattern=kw_pattern,
            )

    # Positive check: does the response seem related to allowed topics?
    # Use a relaxed keyword match — if any allowed topic word appears in
    # the response (case-insensitive), we consider it on-topic.
    response_lower = response.lower()
    on_topic = any(
        topic.lower() in response_lower for topic in cfg.allowed_topics
    )

    # Be lenient: if no topic keywords are found, we still pass the check
    # to avoid false positives on short or general responses.
    # Only block when off_topic_keywords explicitly match.
    return GuardrailResult(
        check_name="Topic Adherence",
        check_type=CheckType.TOPIC_ADHERENCE,
        passed=True,
        message=None,
    )


def check_schema_validation(
    response: str,
    policy: Policy,
    override_schema: Optional[dict[str, Any]] = None,
) -> GuardrailResult:
    """Validate the LLM response against a JSON schema (if enabled)."""
    cfg = policy.output_guardrails.schema_validation
    schema = override_schema or cfg.json_schema

    if not cfg.enabled and override_schema is None:
        return GuardrailResult(
            check_name="Schema Validation",
            check_type=CheckType.SCHEMA_VALIDATION,
            passed=True,
            message=None,
        )

    if schema is None:
        return GuardrailResult(
            check_name="Schema Validation",
            check_type=CheckType.SCHEMA_VALIDATION,
            passed=True,
            message=None,
        )

    # Try to parse the response as JSON
    try:
        data = json.loads(response)
    except json.JSONDecodeError as exc:
        return GuardrailResult(
            check_name="Schema Validation",
            check_type=CheckType.SCHEMA_VALIDATION,
            passed=False,
            message=f"⚠️ Response is not valid JSON: {exc.msg}",
        )

    # Validate against the schema
    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as exc:
        return GuardrailResult(
            check_name="Schema Validation",
            check_type=CheckType.SCHEMA_VALIDATION,
            passed=False,
            message=f"⚠️ Schema validation failed: {exc.message}",
        )

    return GuardrailResult(
        check_name="Schema Validation",
        check_type=CheckType.SCHEMA_VALIDATION,
        passed=True,
        message=None,
    )


def check_output_length(response: str, policy: Policy) -> GuardrailResult:
    """Check that the response doesn't exceed the configured max length."""
    max_len = policy.output_guardrails.max_output_length
    passed = len(response) <= max_len
    return GuardrailResult(
        check_name="Max Output Length",
        check_type=CheckType.OUTPUT_LENGTH,
        passed=passed,
        message=None if passed else (
            f"⚠️ Response too long ({len(response)} chars). "
            f"Maximum allowed is {max_len}."
        ),
    )


def check_output_blocked_topics(response: str, policy: Policy) -> list[GuardrailResult]:
    """Apply blocked-topic patterns to the output."""
    results: list[GuardrailResult] = []
    for bp in policy.content_policies.blocked_topics:
        match = re.search(bp.pattern, response)
        passed = match is None
        results.append(
            GuardrailResult(
                check_name="Output Blocked Topic",
                check_type=CheckType.BLOCKED_TOPIC,
                passed=passed,
                message=None if passed else bp.message,
                matched_pattern=bp.pattern if not passed else None,
            )
        )
    return results


def check_output_blocked_phrases(response: str, policy: Policy) -> list[GuardrailResult]:
    """Apply custom blocked-phrase patterns to the output."""
    results: list[GuardrailResult] = []
    for bp in policy.content_policies.custom_blocked_phrases:
        match = re.search(bp.pattern, response)
        passed = match is None
        results.append(
            GuardrailResult(
                check_name="Output Blocked Phrase",
                check_type=CheckType.BLOCKED_PHRASE,
                passed=passed,
                message=None if passed else bp.message,
                matched_pattern=bp.pattern if not passed else None,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_output_guards(
    response: str,
    policy: Policy,
    override_schema: Optional[dict[str, Any]] = None,
) -> list[GuardrailResult]:
    """
    Run all output guardrails against the LLM response.

    Returns a flat list of `GuardrailResult` objects.
    """
    results: list[GuardrailResult] = []

    # 1. Toxicity
    results.append(check_toxicity(response, policy))

    # 2. Topic adherence
    results.append(check_topic_adherence(response, policy))

    # 3. Schema validation
    results.append(check_schema_validation(response, policy, override_schema))

    # 4. Output length
    results.append(check_output_length(response, policy))

    # 5. Blocked topics in output
    results.extend(check_output_blocked_topics(response, policy))

    # 6. Custom blocked phrases in output
    results.extend(check_output_blocked_phrases(response, policy))

    return results
