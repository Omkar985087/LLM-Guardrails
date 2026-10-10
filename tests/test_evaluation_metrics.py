"""
Unit tests for evaluation metrics calculations and edge cases.
"""

from __future__ import annotations

import unittest

from evaluation.metrics import (
    ConfusionMatrix,
    MetricScores,
    calculate_macro_f1,
    calculate_metrics,
)


class TestEvaluationMetrics(unittest.TestCase):
    def test_hand_calculated_standard_metrics(self):
        """
        Verify every metric formula against manual hand-calculated values:
        TP = 40, TN = 50, FP = 5, FN = 5, Total = 100
        Accuracy = (40 + 50) / 100 = 0.90 (90.0%)
        Precision = 40 / (40 + 5) = 40 / 45 = 0.8889 (88.89%)
        Recall = 40 / (40 + 5) = 40 / 45 = 0.8889 (88.89%)
        F1 = 2 * (40/45) * (40/45) / (80/45) = 40/45 = 0.8889 (88.89%)
        Specificity = 50 / (50 + 5) = 50 / 55 = 0.9091 (90.91%)
        FPR = 5 / (5 + 50) = 5 / 55 = 0.0909 (9.09%)
        FNR = 5 / (5 + 40) = 5 / 45 = 0.1111 (11.11%)
        """
        matrix = ConfusionMatrix(tp=40, tn=50, fp=5, fn=5)
        scores = calculate_metrics(matrix)

        self.assertEqual(scores.accuracy, 0.9)
        self.assertEqual(scores.accuracy_pct, 90.0)

        self.assertEqual(scores.precision, 0.8889)
        self.assertEqual(scores.precision_pct, 88.89)

        self.assertEqual(scores.recall, 0.8889)
        self.assertEqual(scores.recall_pct, 88.89)

        self.assertEqual(scores.f1_score, 0.8889)
        self.assertEqual(scores.f1_score_pct, 88.89)

        self.assertEqual(scores.specificity, 0.9091)
        self.assertEqual(scores.specificity_pct, 90.91)

        self.assertEqual(scores.fpr, 0.0909)
        self.assertEqual(scores.fpr_pct, 9.09)

        self.assertEqual(scores.fnr, 0.1111)
        self.assertEqual(scores.fnr_pct, 11.11)

        self.assertEqual(len(scores.undefined_reasons), 0)

    def test_perfect_classification(self):
        """All cases correctly classified: TP=20, TN=30, FP=0, FN=0."""
        matrix = ConfusionMatrix(tp=20, tn=30, fp=0, fn=0)
        scores = calculate_metrics(matrix)

        self.assertEqual(scores.accuracy_pct, 100.0)
        self.assertEqual(scores.precision_pct, 100.0)
        self.assertEqual(scores.recall_pct, 100.0)
        self.assertEqual(scores.f1_score_pct, 100.0)
        self.assertEqual(scores.specificity_pct, 100.0)
        self.assertEqual(scores.fpr_pct, 0.0)
        self.assertEqual(scores.fnr_pct, 0.0)

    def test_zero_denominator_empty_dataset(self):
        """Empty confusion matrix (0, 0, 0, 0). All metrics should safely be None with reasons."""
        matrix = ConfusionMatrix(tp=0, tn=0, fp=0, fn=0)
        scores = calculate_metrics(matrix)

        self.assertIsNone(scores.accuracy)
        self.assertIsNone(scores.precision)
        self.assertIsNone(scores.recall)
        self.assertIsNone(scores.f1_score)
        self.assertIsNone(scores.specificity)
        self.assertIsNone(scores.fpr)
        self.assertIsNone(scores.fnr)

        self.assertIn("accuracy", scores.undefined_reasons)
        self.assertIn("precision", scores.undefined_reasons)
        self.assertIn("recall", scores.undefined_reasons)

    def test_zero_denominator_no_positive_predictions(self):
        """
        When TP=0 and FP=0 but FN > 0 (e.g. TP=0, TN=10, FP=0, FN=5):
        Denominator (2*TP + FP + FN) = 5 > 0.
        Precision is undefined (0/0) -> None
        Recall is 0 / 5 = 0.0
        F1 is 2 * 0 / 5 = 0.0
        """
        matrix = ConfusionMatrix(tp=0, tn=10, fp=0, fn=5)
        scores = calculate_metrics(matrix)

        self.assertIsNone(scores.precision)
        self.assertEqual(scores.f1_score, 0.0)
        self.assertEqual(scores.f1_score_pct, 0.0)
        self.assertEqual(scores.recall, 0.0)
        self.assertEqual(scores.specificity, 1.0)
        self.assertIn("precision", scores.undefined_reasons)

    def test_tp_0_fp_0_fn_2_yields_f1_zero(self):
        """
        Test case specifically required: TP=0, FP=0, FN=2 (like topic_adherence):
        Denominator = 2 * 0 + 0 + 2 = 2.
        Precision = undefined (None) because TP + FP == 0.
        Recall = 0 / 2 = 0.0.
        F1 = 2 * 0 / (2 * 0 + 0 + 2) = 0.0 (must equal 0, even though precision is undefined).
        """
        matrix = ConfusionMatrix(tp=0, tn=3, fp=0, fn=2)
        scores = calculate_metrics(matrix)

        self.assertIsNone(scores.precision)
        self.assertIn("precision", scores.undefined_reasons)
        self.assertEqual(scores.recall, 0.0)
        self.assertEqual(scores.recall_pct, 0.0)
        self.assertEqual(scores.f1_score, 0.0)
        self.assertEqual(scores.f1_score_pct, 0.0)
        self.assertNotIn("f1_score", scores.undefined_reasons)

    def test_zero_denominator_no_actual_positives(self):
        """
        When all samples are negative (TP=0, FN=0, TN=10, FP=2):
        Denominator = 2 * 0 + 2 + 0 = 2 > 0.
        Recall is undefined (0/0) -> None
        Precision is 0 / 2 = 0.0
        F1 is 0.0
        """
        matrix = ConfusionMatrix(tp=0, tn=10, fp=2, fn=0)
        scores = calculate_metrics(matrix)

        self.assertEqual(scores.precision, 0.0)
        self.assertIsNone(scores.recall)
        self.assertEqual(scores.f1_score, 0.0)
        self.assertEqual(scores.f1_score_pct, 0.0)
        self.assertIsNone(scores.fnr)
        self.assertIn("recall", scores.undefined_reasons)
        self.assertIn("fnr", scores.undefined_reasons)

    def test_zero_denominator_f1_strictly_undefined(self):
        """
        When 2*TP + FP + FN == 0 (TP=0, FP=0, FN=0, TN=10):
        Denominator is 0, so F1 is undefined (None) with reason recorded.
        """
        matrix = ConfusionMatrix(tp=0, tn=10, fp=0, fn=0)
        scores = calculate_metrics(matrix)

        self.assertIsNone(scores.precision)
        self.assertIsNone(scores.recall)
        self.assertIsNone(scores.f1_score)
        self.assertIn("f1_score", scores.undefined_reasons)

    def test_zero_denominator_no_actual_negatives(self):
        """
        When all samples are positive (TN=0, FP=0, TP=8, FN=2):
        Specificity is undefined (0/0) -> None
        FPR is undefined -> None
        """
        matrix = ConfusionMatrix(tp=8, tn=0, fp=0, fn=2)
        scores = calculate_metrics(matrix)

        self.assertIsNone(scores.specificity)
        self.assertIsNone(scores.fpr)
        self.assertEqual(scores.recall, 0.8)
        self.assertEqual(scores.f1_score, 0.8889)
        self.assertIn("specificity", scores.undefined_reasons)
        self.assertIn("fpr", scores.undefined_reasons)

    def test_macro_f1_calculation(self):
        """
        Macro F1 averages all defined category F1 scores, including categories with F1=0.0:
        Cat A: F1 = 1.0
        Cat B: F1 = 0.8
        Cat C: F1 = 0.0 (e.g. topic_adherence)
        Cat D: F1 = None (strictly zero denominator, excluded)
        Expected Macro F1 = (1.0 + 0.8 + 0.0) / 3 = 0.6
        """
        cat_scores = {
            "cat_a": MetricScores(f1_score=1.0),
            "cat_b": MetricScores(f1_score=0.8),
            "cat_c": MetricScores(f1_score=0.0),
            "cat_d": MetricScores(f1_score=None),
        }
        macro_f1 = calculate_macro_f1(cat_scores)
        self.assertEqual(macro_f1, 0.6)

    def test_macro_f1_all_undefined(self):
        """When all categories have undefined F1, macro F1 returns None."""
        cat_scores = {
            "cat_a": MetricScores(f1_score=None),
            "cat_b": MetricScores(f1_score=None),
        }
        self.assertIsNone(calculate_macro_f1(cat_scores))


if __name__ == "__main__":
    unittest.main()
