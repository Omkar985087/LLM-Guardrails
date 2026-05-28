"""
Input Guardrails — checks applied to the user's prompt before it reaches the LLM.

Each check function returns a list of `GuardrailResult` objects.  The
orchestrator in main.py calls `run_input_guards(prompt, policy)` which
aggregates all results and short-circuits on the first failure.
"""

from __future__ import annotations

import re

from guardrails.models import CheckType, GuardrailResult
from guardrails.policy import Policy


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_max_length(prompt: str, policy: Policy) -> GuardrailResult:
    """Reject prompts that exceed the configured maximum length."""
    max_len = policy.input_guardrails.max_input_length
    passed = len(prompt) <= max_len
    return GuardrailResult(
        check_name="Max Input Length",
        check_type=CheckType.MAX_LENGTH,
        passed=passed,
        message=None if passed else (
            f"🚫 Input too long ({len(prompt)} chars). "
            f"Maximum allowed is {max_len}."
        ),
    )


def check_pii(prompt: str, policy: Policy) -> list[GuardrailResult]:
    """Scan for PII patterns (credit cards, SSNs, emails, phones)."""
    cfg = policy.input_guardrails.pii_detection
    if not cfg.enabled:
        return []

    results: list[GuardrailResult] = []
    for bp in cfg.block_patterns:
        match = re.search(bp.pattern, prompt)
        passed = match is None
        results.append(
            GuardrailResult(
                check_name=f"PII — {bp.name or 'pattern'}",
                check_type=CheckType.PII_DETECTION,
                passed=passed,
                message=None if passed else bp.message,
                matched_pattern=bp.pattern if not passed else None,
            )
        )
    return results


def check_prompt_injection(prompt: str, policy: Policy) -> list[GuardrailResult]:
    """Detect prompt injection and jailbreak attempts."""
    cfg = policy.input_guardrails.prompt_injection
    if not cfg.enabled:
        return []

    results: list[GuardrailResult] = []
    for bp in cfg.block_patterns:
        match = re.search(bp.pattern, prompt)
        passed = match is None
        results.append(
            GuardrailResult(
                check_name="Prompt Injection",
                check_type=CheckType.PROMPT_INJECTION,
                passed=passed,
                message=None if passed else bp.message,
                matched_pattern=bp.pattern if not passed else None,
            )
        )
    return results


def check_blocked_topics(prompt: str, policy: Policy) -> list[GuardrailResult]:
    """Check the prompt against blocked-topic patterns."""
    results: list[GuardrailResult] = []
    for bp in policy.content_policies.blocked_topics:
        match = re.search(bp.pattern, prompt)
        passed = match is None
        results.append(
            GuardrailResult(
                check_name=f"Blocked Topic",
                check_type=CheckType.BLOCKED_TOPIC,
                passed=passed,
                message=None if passed else bp.message,
                matched_pattern=bp.pattern if not passed else None,
            )
        )
    return results


def check_blocked_phrases(prompt: str, policy: Policy) -> list[GuardrailResult]:
    """Check the prompt against custom blocked phrases."""
    results: list[GuardrailResult] = []
    for bp in policy.content_policies.custom_blocked_phrases:
        match = re.search(bp.pattern, prompt)
        passed = match is None
        results.append(
            GuardrailResult(
                check_name="Blocked Phrase",
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

def run_input_guards(prompt: str, policy: Policy) -> list[GuardrailResult]:
    """
    Run all input guardrails against the user's prompt.

    Returns a flat list of `GuardrailResult` objects.  If any result has
    ``passed=False``, the request should be blocked.
    """
    results: list[GuardrailResult] = []

    # 1. Length check
    results.append(check_max_length(prompt, policy))

    # 2. PII detection
    results.extend(check_pii(prompt, policy))

    # 3. Prompt injection / jailbreak
    results.extend(check_prompt_injection(prompt, policy))

    # 4. Blocked topics
    results.extend(check_blocked_topics(prompt, policy))

    # 5. Custom blocked phrases
    results.extend(check_blocked_phrases(prompt, policy))

    return results
