"""
LLM Client — wraps Google Gemini (google-genai) for the guardrails gateway.

Handles:
- Loading environment variables reliably from the project root
- Managing the Google Gemini client singleton
- Building the system prompt with mandatory policy rules
- Normalizing and resolving Gemini model names (default: gemini-3.8-flash)
- Calling the Gemini API and handling retries/errors cleanly
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

from guardrails.policy import Policy

# ---------------------------------------------------------------------------
# Environment setup
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

# Load environment variables reliably from the project root
def load_env_from_root() -> None:
    """Load .env from the project root if it exists."""
    if ENV_FILE.exists():
        load_dotenv(dotenv_path=ENV_FILE)
    else:
        load_dotenv()


load_env_from_root()


# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------

class LLMConfigurationError(RuntimeError):
    """Raised when the LLM provider configuration (e.g. API key) is missing or invalid."""
    pass


# ---------------------------------------------------------------------------
# API Key & Model Configuration
# ---------------------------------------------------------------------------

PLACEHOLDER_KEYS = {
    "your_google_gemini_api_key_here",
    "your-api-key-here",
    "your api key here",
    "<your-api-key-here>",
    "your_api_key_here",
}


def get_api_key() -> str:
    """
    Retrieve the Google Gemini API key from the environment.
    Ensures .env is loaded from the project root.
    Raises LLMConfigurationError if missing, empty, or set to a placeholder.
    """
    load_env_from_root()

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key or not api_key.strip():
        raise LLMConfigurationError(
            "LLM provider is not configured. Please configure GOOGLE_API_KEY on the server."
        )

    cleaned = api_key.strip().strip('"').strip("'")
    if not cleaned or cleaned.lower() in PLACEHOLDER_KEYS:
        raise LLMConfigurationError(
            "LLM provider is not configured. Please configure GOOGLE_API_KEY on the server."
        )

    return cleaned


def normalize_model_name(model: str) -> str:
    """Normalize model string to standard Gemini format without duplicate models/ prefixes."""
    m = model.strip()
    while m.startswith("models/"):
        m = m[len("models/"):]
    return m


def get_model_name(policy: Optional[Policy] = None) -> str:
    """
    Resolve the Gemini model name to use.

    Priority:
    1. GEMINI_MODEL environment variable
    2. Model configured in Policy
    3. Default: 'gemini-3.8-flash'
    """
    env_model = os.getenv("GEMINI_MODEL")
    if env_model and env_model.strip():
        return normalize_model_name(env_model.strip())
    if policy and policy.llm and policy.llm.model:
        return normalize_model_name(policy.llm.model)
    return "gemini-3.8-flash"


def format_llm_error(exc: Exception, model_name: str = "") -> str:
    """
    Format LLM exceptions into clear, helpful, safe messages without exposing keys or secrets.
    Distinguishes configuration errors, authentication failures, missing models,
    rate limits, and provider outages.
    """
    if isinstance(exc, LLMConfigurationError):
        return str(exc)

    if isinstance(exc, errors.APIError):
        code = getattr(exc, "code", None)
        status = (getattr(exc, "status", None) or "").upper()
        msg = (getattr(exc, "message", None) or str(exc)).lower()

        if code in (401, 403) or "unauthenticated" in status or "permission_denied" in status or "api_key" in msg:
            return "LLM authentication failed. Please verify that your GOOGLE_API_KEY is valid."

        if code == 404 or "not_found" in status:
            target = model_name or "configured model"
            return (
                f"LLM model '{target}' is no longer available or was not found. "
                f"Please update GEMINI_MODEL (recommended: gemini-3.8-flash)."
            )

        if code == 429 or "resource_exhausted" in status or "quota" in msg:
            return "LLM rate limit or quota exceeded. Please try again later."

        if code in (500, 502, 503, 504) or "unavailable" in status:
            return "LLM service is currently unavailable. Please try again later."

        return f"LLM provider error ({code or 'API'}): request could not be completed."

    exc_str = str(exc)
    exc_lower = exc_str.lower()

    if "api_key not set" in exc_lower or "google_api_key" in exc_lower or "not configured" in exc_lower:
        return "LLM provider is not configured. Please configure GOOGLE_API_KEY on the server."

    if "connect" in exc_lower or "timeout" in exc_lower or "network" in exc_lower:
        return "Unable to connect to LLM provider. Please check network connectivity."

    return f"LLM provider call failed: {exc_str}"


# ---------------------------------------------------------------------------
# Client singleton
# ---------------------------------------------------------------------------

_client: Optional[genai.Client] = None
_cached_api_key: Optional[str] = None


def reset_client() -> None:
    """Reset the cached client singleton (useful for testing or config reload)."""
    global _client, _cached_api_key
    _client = None
    _cached_api_key = None


def get_client() -> genai.Client:
    """Return a cached Gemini client, creating it on first call or when key changes."""
    global _client, _cached_api_key
    api_key = get_api_key()
    if _client is None or _cached_api_key != api_key:
        _client = genai.Client(api_key=api_key)
        _cached_api_key = api_key
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
    model_name = normalize_model_name(get_model_name(policy))

    # If we're retrying, append the correction hint
    full_prompt = prompt
    if correction_hint:
        full_prompt = (
            f"{prompt}\n\n"
            f"[IMPORTANT — previous response was rejected. "
            f"Please correct: {correction_hint}]"
        )

    response = client.models.generate_content(
        model=model_name,
        contents=full_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=policy.llm.temperature,
            max_output_tokens=policy.llm.max_output_tokens,
        ),
    )

    return response.text or ""
