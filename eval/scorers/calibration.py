# eval/scorers/calibration.py
"""
Calibration metrics for confidence scores.

A model is well-calibrated when its stated confidence matches its empirical
accuracy: a model that says 0.9 confidence should be correct ~90% of the time.

Three metrics:
  compute_brier_score            – mean squared error of confidence vs outcome
  compute_ece                    – Expected Calibration Error over N bins
  compute_high_confidence_error_rate – fraction of high-confidence runs that were wrong
"""
from __future__ import annotations
import math


class CalibrationCollector:
    """Calibration metrics for a list of (confidence, was_correct) predictions."""

    def compute_brier_score(
        self,
        predictions: list[tuple[float, bool]],
    ) -> float:
        """
        Brier Score = mean((confidence - correctness)^2).
        Lower is better. Perfect = 0.0. Worst = 1.0.

        Parameters
        ----------
        predictions : list of (confidence: float, was_correct: bool)

        Returns
        -------
        float – Brier score in [0, 1]
        """
        if not predictions:
            return 0.0
        total = sum((conf - float(correct)) ** 2 for conf, correct in predictions)
        return round(total / len(predictions), 6)

    def compute_ece(
        self,
        predictions: list[tuple[float, bool]],
        n_bins: int = 5,
    ) -> float:
        """
        Expected Calibration Error.

        Divide predictions into n_bins equal-width confidence buckets.
        For each bin compute |avg_confidence - accuracy|.
        ECE = weighted average across bins (weight = fraction of samples in bin).

        Parameters
        ----------
        predictions : list of (confidence: float, was_correct: bool)
        n_bins      : int – number of equal-width bins (default 5)

        Returns
        -------
        float – ECE in [0, 1], lower is better
        """
        if not predictions:
            return 0.0

        bins: list[list[tuple[float, bool]]] = [[] for _ in range(n_bins)]
        for conf, correct in predictions:
            # Clamp to [0, 1]
            conf = max(0.0, min(1.0, conf))
            idx = min(int(conf * n_bins), n_bins - 1)
            bins[idx].append((conf, correct))

        n = len(predictions)
        ece = 0.0
        for bucket in bins:
            if not bucket:
                continue
            avg_conf = sum(c for c, _ in bucket) / len(bucket)
            avg_acc = sum(float(ok) for _, ok in bucket) / len(bucket)
            ece += (len(bucket) / n) * abs(avg_conf - avg_acc)

        return round(ece, 6)

    def compute_high_confidence_error_rate(
        self,
        predictions: list[tuple[float, bool]],
        threshold: float = 0.8,
    ) -> float:
        """
        Fraction of predictions where confidence >= threshold but was_correct is False.

        Parameters
        ----------
        predictions : list of (confidence: float, was_correct: bool)
        threshold   : float – confidence cutoff (default 0.8)

        Returns
        -------
        float – error rate in [0, 1] among high-confidence predictions
        """
        high_conf = [(c, ok) for c, ok in predictions if c >= threshold]
        if not high_conf:
            return 0.0
        wrong = sum(1 for _, ok in high_conf if not ok)
        return round(wrong / len(high_conf), 6)
