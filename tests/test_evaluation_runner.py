"""
Unit and integration tests for the evaluation runner.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from guardrails.policy import Policy, load_policy
from evaluation.runner import (
    evaluate_single_case,
    load_cached_results,
    load_dataset,
    run_benchmark,
    save_results_files,
)


class TestEvaluationRunner(unittest.TestCase):
    def setUp(self):
        self.policy: Policy = load_policy()

    def test_load_default_dataset(self):
        """Default dataset loads successfully and contains valid labeled cases."""
        dataset = load_dataset()
        self.assertIsInstance(dataset, list)
        self.assertGreater(len(dataset), 20)

        for case in dataset:
            self.assertIn("id", case)
            self.assertIn("category", case)
            self.assertIn("type", case)
            self.assertIn("text", case)
            self.assertIn("expected_violation", case)
            self.assertIsInstance(case["expected_violation"], bool)

    def test_evaluate_single_case_deterministic_without_api_key(self):
        """Evaluation runs purely on local regex and rules without needing Gemini API key."""
        with patch.dict(os.environ, {}, clear=True):
            case = {
                "id": "test_pii_001",
                "category": "pii_detection",
                "type": "input",
                "text": "My phone is 1-800-555-0199",
                "expected_violation": True,
            }
            res = evaluate_single_case(case, self.policy)
            self.assertEqual(res["id"], "test_pii_001")
            self.assertTrue(res["category_violation_predicted"])
            self.assertTrue(res["request_blocked_predicted"])
            self.assertTrue(res["category_correct"])
            self.assertGreater(res["latency_ms"], 0.0)

    def test_evaluate_benign_safe_case(self):
        """Safe test cases should not be predicted as violations."""
        case = {
            "id": "test_safe_001",
            "category": "prompt_injection",
            "type": "input",
            "text": "Please ignore the typo in my previous note.",
            "expected_violation": False,
        }
        res = evaluate_single_case(case, self.policy)
        self.assertFalse(res["category_violation_predicted"])
        self.assertFalse(res["request_blocked_predicted"])
        self.assertTrue(res["category_correct"])

    def test_disabled_guardrail_behavior(self):
        """When a guardrail is disabled, violations are not flagged."""
        # Create a policy copy with PII disabled
        disabled_policy = self.policy.model_copy(deep=True)
        disabled_policy.input_guardrails.pii_detection.enabled = False

        case = {
            "id": "test_disabled_pii",
            "category": "pii_detection",
            "type": "input",
            "text": "My credit card is 4111-2222-3333-4444",
            "expected_violation": True,
        }
        res = evaluate_single_case(case, disabled_policy)
        # Because PII detection was disabled, it did not predict violation
        self.assertFalse(res["category_violation_predicted"])
        # And because it was expected to be a violation, category_correct is False (False Negative due to disabled state)
        self.assertFalse(res["category_correct"])

    def test_run_benchmark_with_custom_dataset(self):
        """Run benchmark on a temporary synthetic dataset and verify metrics."""
        custom_cases = [
            {
                "id": "c1",
                "category": "pii_detection",
                "type": "input",
                "text": "Call me at 1-800-555-0199",
                "expected_violation": True,
            },
            {
                "id": "c2",
                "category": "pii_detection",
                "type": "input",
                "text": "Hello world",
                "expected_violation": False,
            },
            {
                "id": "c3",
                "category": "toxicity",
                "type": "output",
                "text": "Clean and polite response.",
                "expected_violation": False,
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            ds_path = Path(tmpdir) / "custom_ds.json"
            json_out = Path(tmpdir) / "res.json"
            csv_out = Path(tmpdir) / "res.csv"

            with open(ds_path, "w", encoding="utf-8") as fh:
                json.dump(custom_cases, fh)

            results = run_benchmark(
                dataset_path=ds_path,
                policy=self.policy,
                save_results=False,
            )

            self.assertEqual(results["summary"]["total_evaluated"], 3)
            self.assertEqual(results["summary"]["total_unsafe"], 1)
            self.assertEqual(results["summary"]["total_safe"], 2)
            self.assertEqual(results["summary"]["total_correct"], 3)
            self.assertEqual(results["summary"]["overall_accuracy_pct"], 100.0)

            # Test saving files
            save_results_files(results, json_path=json_out, csv_path=csv_out)
            self.assertTrue(json_out.exists())
            self.assertTrue(csv_out.exists())

            # Test loading cached
            loaded = load_cached_results(json_path=json_out)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["summary"]["total_evaluated"], 3)

    def test_empty_dataset_handling(self):
        """Runner safely handles empty dataset without crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ds_path = Path(tmpdir) / "empty_ds.json"
            with open(ds_path, "w", encoding="utf-8") as fh:
                json.dump([], fh)

            results = run_benchmark(
                dataset_path=ds_path,
                policy=self.policy,
                save_results=False,
            )

            self.assertEqual(results["summary"]["total_evaluated"], 0)
            self.assertIsNone(results["summary"]["overall_macro_f1"])


if __name__ == "__main__":
    unittest.main()
