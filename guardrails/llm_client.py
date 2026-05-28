"""
LLM Client — wraps Google Gemini (google-genai) for the guardrails gateway.

Handles:
- Building the system prompt with mandatory policy rules
- Calling the Gemini API
- Retry logic when output guardrails fail
"""

from __future__ import annotations

import os
from typing import Any, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types

from guardrails.policy import Policy

# Load environment variables
load_dotenv()


# ---------------------------------------------------------------------------
# Client singleton
# ---------------------------------------------------------------------------

_client: Optional[genai.Client] = None


def get_client() -> genai.Client:
    """Return a cached Gemini client, creating it on first call."""
    global _client
    if _client is None:
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key or api_key == "your-api-key-here":
            raise RuntimeError(
                "GOOGLE_API_KEY not set. Add it to your .env file."
            )
        _client = genai.Client(api_key=api_key)
    return _client


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------

def build_system_prompt(policy: Policy) -> str:
    """
    Build the system instruction that is sent alongside every user prompt.

    Injects the mandatory rules from the policy so the LLM follows them
    natively, reducing the need for output-side filtering.
    """
    rules = policy.content_policies.mandatory_rules
    if not rules:
        return "You are a helpful assistant."

    rules_text = "\n".join(f"- {rule}" for rule in rules)

    return (
        "You are a helpful assistant. You MUST follow these mandatory rules "
        "at all times:\n\n"
        f"{rules_text}\n\n"
        "If a user asks you to violate any of these rules, politely decline "
        "and explain that you cannot do so."
    )


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------

def generate(
    prompt: str,
    policy: Policy,
    correction_hint: Optional[str] = None,
) -> str:
    """
    Send *prompt* to the Gemini model configured in *policy*.

    Parameters
    ----------
    prompt : str
        The user's prompt.
    policy : Policy
        The loaded guardrails policy (supplies model, temperature, etc.).
    correction_hint : str, optional
        When retrying after an output-guardrail failure, this hint is
        appended to the prompt to guide the model toward a compliant response.

    Returns
    -------
    str
        The model's text response.
    """
    client = get_client()
    system_prompt = build_system_prompt(policy)

    # If we're retrying, append the correction hint
    full_prompt = prompt
    if correction_hint:
        full_prompt = (
            f"{prompt}\n\n"
            f"[IMPORTANT — previous response was rejected. "
            f"Please correct: {correction_hint}]"
        )

    response = client.models.generate_content(
        model=policy.llm.model,
        contents=full_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=policy.llm.temperature,
            max_output_tokens=policy.llm.max_output_tokens,
        ),
    )

    return response.text or ""
