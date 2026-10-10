"""
Tests for environment configuration and Gemini LLM client.
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from google.genai import errors

from guardrails.llm_client import (
    LLMConfigurationError,
    format_llm_error,
    get_api_key,
    get_model_name,
    normalize_model_name,
    reset_client,
    generate,
)
from guardrails.policy import Policy, load_policy


class TestEnvAndClient(unittest.TestCase):
    def setUp(self):
        reset_client()

    def tearDown(self):
        reset_client()

    def test_missing_api_key_raises_configuration_error(self):
        """When GOOGLE_API_KEY is not set or empty, LLMConfigurationError is raised."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("guardrails.llm_client.load_env_from_root"):
                with self.assertRaises(LLMConfigurationError) as ctx:
                    get_api_key()
                self.assertIn("LLM provider is not configured", str(ctx.exception))
                self.assertIn("GOOGLE_API_KEY", str(ctx.exception))

    def test_empty_or_whitespace_api_key_raises_configuration_error(self):
        """When GOOGLE_API_KEY is whitespace or empty string, error is raised."""
        for empty_val in ["", "   ", "\t\n"]:
            with patch.dict(os.environ, {"GOOGLE_API_KEY": empty_val}):
                with patch("guardrails.llm_client.load_env_from_root"):
                    with self.assertRaises(LLMConfigurationError):
                        get_api_key()

    def test_placeholder_api_key_raises_configuration_error(self):
        """Placeholder keys from .env.example are rejected."""
        placeholders = [
            "your_google_gemini_api_key_here",
            "your-api-key-here",
            "your api key here",
            "<your-api-key-here>",
            "YOUR_GOOGLE_GEMINI_API_KEY_HERE",
        ]
        for placeholder in placeholders:
            with patch.dict(os.environ, {"GOOGLE_API_KEY": placeholder}):
                with patch("guardrails.llm_client.load_env_from_root"):
                    with self.assertRaises(LLMConfigurationError) as ctx:
                        get_api_key()
                    self.assertIn("LLM provider is not configured", str(ctx.exception))

    def test_valid_api_key_is_returned(self):
        """Valid non-placeholder API key is returned properly."""
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "AIzaSyTestValidKey123"}):
            with patch("guardrails.llm_client.load_env_from_root"):
                key = get_api_key()
                self.assertEqual(key, "AIzaSyTestValidKey123")

    def test_get_model_name_precedence(self):
        """GEMINI_MODEL env var takes precedence over policy, which defaults to gemini-3.8-flash."""
        # 1. Default fallback when no env var and no policy
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_model_name(None), "gemini-3.8-flash")

        # 2. Env var override takes highest priority
        with patch.dict(os.environ, {"GEMINI_MODEL": "custom-gemini-model"}):
            self.assertEqual(get_model_name(None), "custom-gemini-model")

        # 3. Policy model when no env var
        with patch.dict(os.environ, {}, clear=True):
            policy = Policy()
            policy.llm.model = "gemini-3.8-flash"
            self.assertEqual(get_model_name(policy), "gemini-3.8-flash")

    def test_normalize_model_name(self):
        """Ensure models/ prefixes are normalized and duplicate prefixes stripped."""
        self.assertEqual(normalize_model_name("gemini-3.8-flash"), "gemini-3.8-flash")
        self.assertEqual(normalize_model_name("models/models/gemini-3.8-flash"), "gemini-3.8-flash")

    def test_format_llm_error_distinguishes_error_types(self):
        """Test formatting of configuration, auth, not found, rate limit, and outage errors."""
        # Configuration error
        config_err = LLMConfigurationError("LLM provider is not configured. Please configure GOOGLE_API_KEY on the server.")
        msg = format_llm_error(config_err)
        self.assertIn("LLM provider is not configured", msg)

        # 404 Model Not Found
        api_404 = errors.APIError(code=404, response_json={"error": {"code": 404, "message": "models/gemini-2.0-flash is no longer available", "status": "NOT_FOUND"}})
        msg_404 = format_llm_error(api_404, model_name="gemini-2.0-flash")
        self.assertIn("no longer available", msg_404)
        self.assertIn("gemini-3.8-flash", msg_404)

        # 401/403 Authentication Error
        api_401 = errors.APIError(code=401, response_json={"error": {"code": 401, "message": "API key not valid", "status": "UNAUTHENTICATED"}})
        msg_401 = format_llm_error(api_401)
        self.assertIn("authentication failed", msg_401.lower())

        # 429 Rate Limit
        api_429 = errors.APIError(code=429, response_json={"error": {"code": 429, "message": "Resource exhausted", "status": "RESOURCE_EXHAUSTED"}})
        msg_429 = format_llm_error(api_429)
        self.assertIn("rate limit or quota", msg_429.lower())

        # 503 Unavailable
        api_503 = errors.APIError(code=503, response_json={"error": {"code": 503, "message": "Service unavailable", "status": "UNAVAILABLE"}})
        msg_503 = format_llm_error(api_503)
        self.assertIn("service is currently unavailable", msg_503.lower())

    @patch("guardrails.llm_client.get_client")
    def test_mocked_generate_success(self, mock_get_client):
        """Test generate() calls mocked Gemini client with proper model and configuration."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Hello! Guardrails are functioning."
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        policy = load_policy()
        result = generate("Test prompt", policy)

        self.assertEqual(result, "Hello! Guardrails are functioning.")
        mock_client.models.generate_content.assert_called_once()
        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "gemini-3.8-flash")
        self.assertEqual(call_kwargs["contents"], "Test prompt")


if __name__ == "__main__":
    unittest.main()
