"""
Evaluation Runner — executes the guardrails pipeline against the labeled dataset.

Measures:
- Deterministic per-category guardrail predictions against ground-truth labels
- Request-level end-to-end blocking behavior
- Processing latency in milliseconds (mean, median, P95, max)
- Confusion matrices and classification metrics
- Macro-averaged F1 score
- Generates evaluation/results.json and evaluation/results.csv
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
import time
from typing import Any, Dict, List, Optional, Tuple

from guardrails.input_guards import run_input_guards
from guardrails.models import CheckType, GuardrailResult
from guardrails.output_guards import run_output_guards
from guardrails.policy import Policy, load_policy
from evaluation.metrics import (
    ConfusionMatrix,
    MetricScores,
    calculate_macro_f1,
    calculate_metrics,
)

EVALUATION_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET_PATH = EVALUATION_DIR / "dataset.json"
DEFAULT_RESULTS_JSON_PATH = EVALUATION_DIR / "results.json"
DEFAULT_RESULTS_CSV_PATH = EVALUATION_DIR / "results.csv"

# Category to CheckType mapping
CATEGORY_MAP: Dict[str, CheckType] = {
    "prompt_injection": CheckType.PROMPT_INJECTION,
    "pii_detection": CheckType.PII_DETECTION,
    "max_length": CheckType.MAX_LENGTH,
    "blocked_topic": CheckType.BLOCKED_TOPIC,
    "blocked_phrase": CheckType.BLOCKED_PHRASE,
    "toxicity": CheckType.TOXICITY,
    "topic_adherence": CheckType.TOPIC_ADHERENCE,
    "schema_validation": CheckType.SCHEMA_VALIDATION,
    "output_length": CheckType.OUTPUT_LENGTH,
}


def load_dataset(path: Optional[Path | str] = None) -> List[Dict[str, Any]]:
    """Load labeled evaluation test cases from JSON file."""
    dataset_file = Path(path) if path else DEFAULT_DATASET_PATH
    if not dataset_file.exists():
        raise FileNotFoundError(f"Evaluation dataset not found: {dataset_file}")

    with open(dataset_file, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    if not isinstance(data, list):
        raise ValueError(f"Dataset must be a JSON array of test cases, got {type(data).__name__}")

    return data


def expand_text_placeholders(text: str) -> str:
    """Expand dynamic length test placeholders."""
    if "__GENERATE_OVERSIZED_INPUT_4050__" in text:
        return "A" * 4050
    if "__GENERATE_OVERSIZED_OUTPUT_2050__" in text:
        return "B" * 2050
    return text


def is_category_enabled(category: str, policy: Policy) -> bool:
    """Determine whether the specified category is enabled in the active policy."""
    if category == "pii_detection":
        return policy.input_guardrails.pii_detection.enabled
    if category == "prompt_injection":
        return policy.input_guardrails.prompt_injection.enabled
    if category == "max_length":
        return policy.input_guardrails.max_input_length > 0
    if category == "blocked_topic":
        return len(policy.content_policies.blocked_topics) > 0
    if category == "blocked_phrase":
        return len(policy.content_policies.custom_blocked_phrases) > 0
    if category == "toxicity":
        return policy.output_guardrails.toxicity_check.enabled
    if category == "topic_adherence":
        return policy.output_guardrails.topic_adherence.enabled
    if category == "schema_validation":
        return policy.output_guardrails.schema_validation.enabled
    if category == "output_length":
        return policy.output_guardrails.max_output_length > 0
    return True


def evaluate_single_case(
    case: Dict[str, Any], policy: Policy
) -> Dict[str, Any]:
    """
    Execute appropriate guardrails against a single test case.
    Measures isolated guardrail latency without calling any LLM API.
    """
    case_id = case.get("id", "unknown")
    category = case.get("category", "")
    target_type = case.get("type", "input")
    raw_text = case.get("text", "")
    expected_violation = bool(case.get("expected_violation", False))
    override_schema = case.get("schema")

    text = expand_text_placeholders(raw_text)
    expected_check_type = CATEGORY_MAP.get(category)

    # Execute guardrails and measure latency
    t_start = time.perf_counter()
    if target_type == "output":
        guard_results = run_output_guards(
            text, policy, override_schema=override_schema
        )
    else:
        guard_results = run_input_guards(text, policy)
    t_end = time.perf_counter()

    latency_ms = (t_end - t_start) * 1000.0

    # Determine category prediction: did the designated check type detect a violation?
    relevant_checks = [
        r for r in guard_results if r.check_type == expected_check_type
    ] if expected_check_type else []

    # Category predicted violation is True if ANY check for that category failed (passed=False)
    category_violation_predicted = any(not r.passed for r in relevant_checks)

    # Request-level prediction: did ANY check fail?
    request_blocked_predicted = any(not r.passed for r in guard_results)

    # Check messages
    failed_messages = [r.message for r in relevant_checks if not r.passed and r.message]

    return {
        "id": case_id,
        "category": category,
        "type": target_type,
        "expected_violation": expected_violation,
        "category_violation_predicted": category_violation_predicted,
        "request_blocked_predicted": request_blocked_predicted,
        "category_correct": category_violation_predicted == expected_violation,
        "request_correct": request_blocked_predicted == expected_violation,
        "latency_ms": round(latency_ms, 4),
        "failed_messages": failed_messages,
        "description": case.get("description", ""),
    }


def run_benchmark(
    dataset_path: Optional[Path | str] = None,
    policy: Optional[Policy] = None,
    save_results: bool = True,
) -> Dict[str, Any]:
    """
    Execute the complete evaluation benchmark.

    Returns structured evaluation results with:
    - Metadata and policy configuration
    - Latency statistics (mean, median, P95, max)
    - Per-category confusion matrices and metrics
    - Overall macro F1-score
    - Request-level end-to-end confusion matrix and metrics
    - Safe vs blocked distribution counts and percentages
    """
    if policy is None:
        policy = load_policy()

    dataset = load_dataset(dataset_path)

    sample_results: List[Dict[str, Any]] = []
    latencies: List[float] = []

    # Confusion matrix buckets
    category_matrices: Dict[str, ConfusionMatrix] = {
        cat: ConfusionMatrix() for cat in CATEGORY_MAP.keys()
    }
    request_matrix = ConfusionMatrix()

    for case in dataset:
        evaluated = evaluate_single_case(case, policy)
        sample_results.append(evaluated)
        latencies.append(evaluated["latency_ms"])

        cat = evaluated["category"]
        exp = evaluated["expected_violation"]
        pred_cat = evaluated["category_violation_predicted"]
        pred_req = evaluated["request_blocked_predicted"]

        # Update per-category confusion matrix
        if cat in category_matrices:
            m = category_matrices[cat]
            if exp and pred_cat:
                m.tp += 1
            elif not exp and not pred_cat:
                m.tn += 1
            elif not exp and pred_cat:
                m.fp += 1
            elif exp and not pred_cat:
                m.fn += 1

        # Update request-level confusion matrix
        if exp and pred_req:
            request_matrix.tp += 1
        elif not exp and not pred_req:
            request_matrix.tn += 1
        elif not exp and pred_req:
            request_matrix.fp += 1
        elif exp and not pred_req:
            request_matrix.fn += 1

    # Latency calculations
    total_samples = len(latencies)
    if total_samples > 0:
        sorted_latencies = sorted(latencies)
        mean_lat = statistics.mean(latencies)
        median_lat = statistics.median(latencies)
        # P95 index
        p95_idx = max(0, min(total_samples - 1, math.ceil(0.95 * total_samples) - 1))
        p95_lat = sorted_latencies[p95_idx]
        max_lat = max(latencies)
    else:
        mean_lat = median_lat = p95_lat = max_lat = 0.0

    latency_stats = {
        "mean_ms": round(mean_lat, 3),
        "median_ms": round(median_lat, 3),
        "p95_ms": round(p95_lat, 3),
        "max_ms": round(max_lat, 3),
        "unit": "milliseconds",
    }

    # Per-category metrics
    category_metrics: Dict[str, Dict[str, Any]] = {}
    category_scores_map: Dict[str, MetricScores] = {}

    for cat, matrix in category_matrices.items():
        scores = calculate_metrics(matrix)
        category_scores_map[cat] = scores
        enabled = is_category_enabled(cat, policy)

        cat_type = "output" if cat in ("toxicity", "topic_adherence", "schema_validation", "output_length") else "input"

        category_metrics[cat] = {
            "category": cat,
            "type": cat_type,
            "enabled": enabled,
            "confusion_matrix": matrix.to_dict(),
            "metrics": scores.to_dict(),
        }

    # Overall macro F1 across categories with defined F1
    macro_f1 = calculate_macro_f1(category_scores_map)
    macro_f1_pct = round(macro_f1 * 100.0, 2) if macro_f1 is not None else None

    # Overall request-level metrics
    request_scores = calculate_metrics(request_matrix)

    # Request statistics
    blocked_count = request_matrix.tp + request_matrix.fp
    allowed_count = request_matrix.tn + request_matrix.fn
    safe_count = request_matrix.actual_negatives
    unsafe_count = request_matrix.actual_positives
    correct_count = request_matrix.tp + request_matrix.tn

    blocked_pct = round((blocked_count / total_samples) * 100.0, 2) if total_samples > 0 else 0.0
    allowed_pct = round((allowed_count / total_samples) * 100.0, 2) if total_samples > 0 else 0.0
    correct_pct = round((correct_count / total_samples) * 100.0, 2) if total_samples > 0 else 0.0

    # Policy configuration snapshot
    policy_snapshot = {
        "model": policy.llm.model,
        "max_input_length": policy.input_guardrails.max_input_length,
        "max_output_length": policy.output_guardrails.max_output_length,
        "pii_enabled": policy.input_guardrails.pii_detection.enabled,
        "injection_enabled": policy.input_guardrails.prompt_injection.enabled,
        "toxicity_enabled": policy.output_guardrails.toxicity_check.enabled,
        "topic_adherence_enabled": policy.output_guardrails.topic_adherence.enabled,
        "schema_validation_enabled": policy.output_guardrails.schema_validation.enabled,
        "blocked_topics_count": len(policy.content_policies.blocked_topics),
        "custom_blocked_phrases_count": len(policy.content_policies.custom_blocked_phrases),
    }

    # Limitations & notes
    limitations = [
        "Topic adherence: the active policy has empty off_topic_keywords ([]), and positive keywords are not configured to reject responses in check_topic_adherence(). Off-topic examples pass by design unless explicit off_topic_keywords patterns are specified, resulting in TP=0, FP=0, and F1=0.0 (included in the nine-category macro average).",
        "Schema validation: policy has schema_validation disabled by default (enabled=false); benchmark supplies explicit per-case schema overrides to validate detector logic.",
        "Isolated latency: measurements capture local guardrail regex, string, and profanity checks, completely excluding LLM network transit time."
    ]

    timestamp_str = datetime.now(timezone.utc).isoformat()

    results_data: Dict[str, Any] = {
        "metadata": {
            "dataset_version": "1.0.0",
            "timestamp": timestamp_str,
            "total_test_cases": total_samples,
            "policy": policy_snapshot,
            "limitations": limitations,
        },
        "summary": {
            "total_evaluated": total_samples,
            "total_safe": safe_count,
            "total_unsafe": unsafe_count,
            "total_correct": correct_count,
            "overall_accuracy_pct": request_scores.accuracy_pct,
            "overall_macro_f1": macro_f1,
            "overall_macro_f1_pct": macro_f1_pct,
            "macro_f1_aggregation_method": "Unweighted arithmetic mean of per-category F1 scores across all nine eligible guardrail categories (calculated directly as F1 = 2*TP / (2*TP + FP + FN), including topic_adherence with F1 = 0.0).",
        },
        "request_level": {
            "confusion_matrix": request_matrix.to_dict(),
            "metrics": request_scores.to_dict(),
            "requests_blocked": blocked_count,
            "requests_blocked_pct": blocked_pct,
            "requests_allowed": allowed_count,
            "requests_allowed_pct": allowed_pct,
        },
        "latency": latency_stats,
        "categories": category_metrics,
        "sample_evaluations": sample_results,
    }

    if save_results:
        save_results_files(results_data)

    return results_data


def save_results_files(
    results_data: Dict[str, Any],
    json_path: Optional[Path | str] = None,
    csv_path: Optional[Path | str] = None,
) -> None:
    """Save evaluation results to JSON and CSV formats."""
    target_json = Path(json_path) if json_path else DEFAULT_RESULTS_JSON_PATH
    target_csv = Path(csv_path) if csv_path else DEFAULT_RESULTS_CSV_PATH

    target_json.parent.mkdir(parents=True, exist_ok=True)
    target_csv.parent.mkdir(parents=True, exist_ok=True)

    # 1. Save JSON
    with open(target_json, "w", encoding="utf-8") as fh:
        json.dump(results_data, fh, indent=2)

    # 2. Save CSV summary
    categories = results_data.get("categories", {})
    req = results_data.get("request_level", {})
    req_m = req.get("confusion_matrix", {})
    req_s = req.get("metrics", {})

    with open(target_csv, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "Category",
            "Type",
            "Status",
            "Total",
            "TP",
            "TN",
            "FP",
            "FN",
            "Accuracy(%)",
            "Precision(%)",
            "Recall(%)",
            "F1-Score(%)",
            "Specificity(%)",
            "FPR(%)",
            "FNR(%)",
        ])

        for cat_name, cat_data in categories.items():
            cm = cat_data.get("confusion_matrix", {})
            met = cat_data.get("metrics", {})
            writer.writerow([
                cat_name,
                cat_data.get("type", "input"),
                "Enabled" if cat_data.get("enabled", True) else "Disabled",
                cm.get("total", 0),
                cm.get("tp", 0),
                cm.get("tn", 0),
                cm.get("fp", 0),
                cm.get("fn", 0),
                met.get("accuracy_pct", "N/A"),
                met.get("precision_pct", "N/A"),
                met.get("recall_pct", "N/A"),
                met.get("f1_score_pct", "N/A"),
                met.get("specificity_pct", "N/A"),
                met.get("fpr_pct", "N/A"),
                met.get("fnr_pct", "N/A"),
            ])

        # Overall request-level row
        writer.writerow([
            "OVERALL_REQUEST_LEVEL",
            "pipeline",
            "Active",
            req_m.get("total", 0),
            req_m.get("tp", 0),
            req_m.get("tn", 0),
            req_m.get("fp", 0),
            req_m.get("fn", 0),
            req_s.get("accuracy_pct", "N/A"),
            req_s.get("precision_pct", "N/A"),
            req_s.get("recall_pct", "N/A"),
            req_s.get("f1_score_pct", "N/A"),
            req_s.get("specificity_pct", "N/A"),
            req_s.get("fpr_pct", "N/A"),
            req_s.get("fnr_pct", "N/A"),
        ])


def load_cached_results(
    json_path: Optional[Path | str] = None,
) -> Optional[Dict[str, Any]]:
    """Load previously saved benchmark results from JSON, or return None if not present."""
    target_json = Path(json_path) if json_path else DEFAULT_RESULTS_JSON_PATH
    if not target_json.exists():
        return None
    try:
        with open(target_json, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None
