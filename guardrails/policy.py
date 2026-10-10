"""
Policy Engine — loads and caches the YAML guardrails policy.

Provides a singleton `get_policy()` that reads guardrails_policy.yaml,
parses it into typed Pydantic models, and caches the result.  Call
`reload_policy()` to force a re-read (e.g. after editing the YAML).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

<<<<<<< HEAD
from dotenv import load_dotenv
import yaml
from pydantic import BaseModel, Field

# Ensure environment variables are loaded from the project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
if ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE)

=======
import yaml
from pydantic import BaseModel, Field

>>>>>>> 41a27c22ffe0732f0ad03e20dc6fc7f63887f5ed

# ---------------------------------------------------------------------------
# Policy sub-models
# ---------------------------------------------------------------------------

class BlockPattern(BaseModel):
    """A single regex-based blocking pattern."""
    name: Optional[str] = None
    pattern: str
    message: str


class PIIDetectionConfig(BaseModel):
    enabled: bool = True
    block_patterns: list[BlockPattern] = Field(default_factory=list)


class PromptInjectionConfig(BaseModel):
    enabled: bool = True
    block_patterns: list[BlockPattern] = Field(default_factory=list)


class InputGuardrailsConfig(BaseModel):
    pii_detection: PIIDetectionConfig = Field(default_factory=PIIDetectionConfig)
    prompt_injection: PromptInjectionConfig = Field(default_factory=PromptInjectionConfig)
    max_input_length: int = 4000


class ToxicityCheckConfig(BaseModel):
    enabled: bool = True
    message: str = "Response contained inappropriate content."


class TopicAdherenceConfig(BaseModel):
    enabled: bool = True
    allowed_topics: list[str] = Field(default_factory=list)
    off_topic_keywords: list[str] = Field(default_factory=list)
    message: str = "Response went off-topic."


class SchemaValidationConfig(BaseModel):
    enabled: bool = False
    json_schema: Optional[dict[str, Any]] = None


class OutputGuardrailsConfig(BaseModel):
    toxicity_check: ToxicityCheckConfig = Field(default_factory=ToxicityCheckConfig)
    topic_adherence: TopicAdherenceConfig = Field(default_factory=TopicAdherenceConfig)
    schema_validation: SchemaValidationConfig = Field(default_factory=SchemaValidationConfig)
    max_output_length: int = 2000


class ContentPoliciesConfig(BaseModel):
    blocked_topics: list[BlockPattern] = Field(default_factory=list)
    mandatory_rules: list[str] = Field(default_factory=list)
    custom_blocked_phrases: list[BlockPattern] = Field(default_factory=list)


class LLMConfig(BaseModel):
<<<<<<< HEAD
    model: str = "gemini-3.8-flash"
=======
    model: str = "gemini-2.0-flash"
>>>>>>> 41a27c22ffe0732f0ad03e20dc6fc7f63887f5ed
    temperature: float = 0.7
    max_output_tokens: int = 1024
    retry_on_output_violation: bool = True
    max_retries: int = 2


# ---------------------------------------------------------------------------
# Top-level Policy model
# ---------------------------------------------------------------------------

class Policy(BaseModel):
    """Complete parsed guardrails policy."""
    input_guardrails: InputGuardrailsConfig = Field(
        default_factory=InputGuardrailsConfig
    )
    output_guardrails: OutputGuardrailsConfig = Field(
        default_factory=OutputGuardrailsConfig
    )
    content_policies: ContentPoliciesConfig = Field(
        default_factory=ContentPoliciesConfig
    )
    llm: LLMConfig = Field(default_factory=LLMConfig)


# ---------------------------------------------------------------------------
# Singleton loader
# ---------------------------------------------------------------------------

_policy_cache: Optional[Policy] = None
_policy_path: Optional[Path] = None


def load_policy(path: str | Path | None = None) -> Policy:
    """Load the policy from *path* (or the default location) and cache it."""
    global _policy_cache, _policy_path

    if path is None:
        # Default: guardrails_policy.yaml next to this file's project root
        path = Path(__file__).resolve().parent.parent / "guardrails_policy.yaml"
    else:
        path = Path(path)

    _policy_path = path

    if not path.exists():
        raise FileNotFoundError(f"Policy file not found: {path}")

    with open(path, "r", encoding="utf-8") as fh:
        raw: dict = yaml.safe_load(fh) or {}

<<<<<<< HEAD
    # Allow GEMINI_MODEL environment variable to override YAML setting
    env_model = os.getenv("GEMINI_MODEL")
    if env_model and env_model.strip():
        if "llm" in raw and isinstance(raw["llm"], dict):
            raw["llm"]["model"] = env_model.strip()
        elif "llm" not in raw:
            raw["llm"] = {"model": env_model.strip()}

=======
>>>>>>> 41a27c22ffe0732f0ad03e20dc6fc7f63887f5ed
    _policy_cache = Policy(**raw)
    return _policy_cache


def reload_policy() -> Policy:
    """Force re-read of the policy file."""
    if _policy_path is None:
        return load_policy()
    return load_policy(_policy_path)


def get_policy() -> Policy:
    """Return the cached policy, loading it on first call."""
    if _policy_cache is None:
        return load_policy()
    return _policy_cache
