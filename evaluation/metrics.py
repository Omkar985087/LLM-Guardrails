"""
Evaluation Metrics — calculations for guardrail performance.

Implements standard binary classification metrics:
- Confusion matrix counts (TP, TN, FP, FN)
- Accuracy, Precision, Recall, F1-score
- Specificity, False Positive Rate (FPR), False Negative Rate (FNR)
- Safe zero-denominator handling with explicit null representation
- Macro-averaged F1 aggregation across categories
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ConfusionMatrix:
    """Confusion matrix counts for binary classification."""
    tp: int = 0  # True Positive: actual violation correctly blocked
    tn: int = 0  # True Negative: actual safe correctly allowed
    fp: int = 0  # False Positive: actual safe incorrectly blocked
    fn: int = 0  # False Negative: actual violation incorrectly allowed

    @property
    def total(self) -> int:
        return self.tp + self.tn + self.fp + self.fn

    @property
    def actual_positives(self) -> int:
        """Total actual violations (TP + FN)."""
        return self.tp + self.fn

    @property
    def actual_negatives(self) -> int:
        """Total actual safe examples (TN + FP)."""
        return self.tn + self.fp

    @property
    def predicted_positives(self) -> int:
        """Total predicted blocks (TP + FP)."""
        return self.tp + self.fp

    @property
    def predicted_negatives(self) -> int:
        """Total predicted allowed (TN + FN)."""
        return self.tn + self.fn

    def to_dict(self) -> Dict[str, int]:
        return {
            "tp": self.tp,
            "tn": self.tn,
            "fp": self.fp,
            "fn": self.fn,
            "total": self.total,
            "actual_positives": self.actual_positives,
            "actual_negatives": self.actual_negatives,
            "predicted_positives": self.predicted_positives,
            "predicted_negatives": self.predicted_negatives,
        }


@dataclass
class MetricScores:
    """Calculated metric scores with safe handling for zero denominators."""
    accuracy: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1_score: Optional[float] = None
    specificity: Optional[float] = None
    fpr: Optional[float] = None  # False Positive Rate
    fnr: Optional[float] = None  # False Negative Rate

    # Percentage representations (0.0 to 100.0) rounded to 2 decimal places
    accuracy_pct: Optional[float] = None
    precision_pct: Optional[float] = None
    recall_pct: Optional[float] = None
    f1_score_pct: Optional[float] = None
    specificity_pct: Optional[float] = None
    fpr_pct: Optional[float] = None
    fnr_pct: Optional[float] = None

    undefined_reasons: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def calculate_f1_from_matrix(tp: int, fp: int, fn: int) -> Optional[float]:
    """
    Calculate F1 score directly from confusion matrix counts:
        F1 = 2 * TP / (2 * TP + FP + FN)

    If the denominator is zero (2*TP + FP + FN == 0), returns None.
    If the denominator is nonzero and TP == 0, returns 0.0.
    """
    f1_denom = (2 * tp) + fp + fn
    if f1_denom > 0:
        return round((2 * tp) / f1_denom, 4)
    return None


def calculate_metrics(matrix: ConfusionMatrix) -> MetricScores:
    """
    Calculate classification metrics from a confusion matrix.

    Formulas:
        Accuracy    = (TP + TN) / (TP + TN + FP + FN)
        Precision   = TP / (TP + FP)
        Recall      = TP / (TP + FN)
        F1          = 2 * TP / (2 * TP + FP + FN)
        Specificity = TN / (TN + FP)
        FPR         = FP / (FP + TN)
        FNR         = FN / (FN + TP)

    Returns MetricScores with None for undefined metrics and explicit reasons.
    """
    scores = MetricScores()
    reasons: Dict[str, str] = {}

    tp, tn, fp, fn = matrix.tp, matrix.tn, matrix.fp, matrix.fn
    total = matrix.total

    # Accuracy = (TP + TN) / Total
    if total > 0:
        acc = (tp + tn) / total
        scores.accuracy = round(acc, 4)
        scores.accuracy_pct = round(acc * 100.0, 2)
    else:
        reasons["accuracy"] = "Dataset is empty (TP + TN + FP + FN == 0)"

    # Precision = TP / (TP + FP)
    pred_pos = tp + fp
    if pred_pos > 0:
        prec = tp / pred_pos
        scores.precision = round(prec, 4)
        scores.precision_pct = round(prec * 100.0, 2)
    else:
        reasons["precision"] = "No positive predictions made (TP + FP == 0)"

    # Recall = TP / (TP + FN)
    actual_pos = tp + fn
    if actual_pos > 0:
        rec = tp / actual_pos
        scores.recall = round(rec, 4)
        scores.recall_pct = round(rec * 100.0, 2)
    else:
        reasons["recall"] = "No actual positive violations in dataset (TP + FN == 0)"

    # F1-score = 2 * TP / (2 * TP + FP + FN)
    f1_denom = (2 * tp) + fp + fn
    if f1_denom > 0:
        f1 = (2 * tp) / f1_denom
        scores.f1_score = round(f1, 4)
        scores.f1_score_pct = round(f1 * 100.0, 2)
    else:
        reasons["f1_score"] = "No positive cases or positive predictions (2*TP + FP + FN == 0)"

    # Specificity = TN / (TN + FP)
    actual_neg = tn + fp
    if actual_neg > 0:
        spec = tn / actual_neg
        scores.specificity = round(spec, 4)
        scores.specificity_pct = round(spec * 100.0, 2)
    else:
        reasons["specificity"] = "No actual negative safe examples in dataset (TN + FP == 0)"

    # False Positive Rate (FPR) = FP / (FP + TN)
    if actual_neg > 0:
        fpr_val = fp / actual_neg
        scores.fpr = round(fpr_val, 4)
        scores.fpr_pct = round(fpr_val * 100.0, 2)
    else:
        reasons["fpr"] = "No actual negative safe examples to compute FPR (FP + TN == 0)"

    # False Negative Rate (FNR) = FN / (FN + TP)
    if actual_pos > 0:
        fnr_val = fn / actual_pos
        scores.fnr = round(fnr_val, 4)
        scores.fnr_pct = round(fnr_val * 100.0, 2)
    else:
        reasons["fnr"] = "No actual positive violations to compute FNR (FN + TP == 0)"

    scores.undefined_reasons = reasons
    return scores


def calculate_macro_f1(category_data: Dict[str, Any]) -> Optional[float]:
    """
    Calculate the macro-average F1-score across all eligible categories.

    Each category's F1 is calculated directly from its confusion matrix:
        F1 = 2 * TP / (2 * TP + FP + FN)
    If the denominator is nonzero but TP = 0, F1 equals 0.0 (e.g. topic_adherence).
    If the denominator is zero (2*TP + FP + FN == 0), F1 is undefined (None) and excluded.

    For this benchmark, all eligible categories with defined F1 (including F1 = 0.0)
    are included in the macro average.
    """
    f1_values: List[float] = []
    for item in category_data.values():
        if isinstance(item, MetricScores):
            if item.f1_score is not None:
                f1_values.append(item.f1_score)
        elif isinstance(item, ConfusionMatrix):
            f1 = calculate_f1_from_matrix(item.tp, item.fp, item.fn)
            if f1 is not None:
                f1_values.append(f1)
        elif isinstance(item, dict):
            if "metrics" in item and "f1_score" in item["metrics"]:
                f1 = item["metrics"]["f1_score"]
                if f1 is not None:
                    f1_values.append(f1)
            elif "confusion_matrix" in item:
                cm = item["confusion_matrix"]
                f1 = calculate_f1_from_matrix(cm.get("tp", 0), cm.get("fp", 0), cm.get("fn", 0))
                if f1 is not None:
                    f1_values.append(f1)
            elif "tp" in item and "fp" in item and "fn" in item:
                f1 = calculate_f1_from_matrix(item["tp"], item["fp"], item["fn"])
                if f1 is not None:
                    f1_values.append(f1)
            elif "f1_score" in item and item["f1_score"] is not None:
                f1_values.append(item["f1_score"])

    if not f1_values:
        return None
    return round(sum(f1_values) / len(f1_values), 4)
