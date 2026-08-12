# eval/scorers/abstention.py
"""
Abstention Evaluator.

Tests whether the agent correctly identifies when it should — or should not —
ask for further investigation.

Three outcomes:
  correct_abstention   – agent said True, ground truth says True  (good)
  false_abstention     – agent said True, ground truth says False (unnecessary uncertainty)
  missed_abstention    – agent said False, ground truth says True (dangerous overconfidence)
"""
from __future__ import annotations


class AbstentionEvaluator:
    """Evaluates agent abstention behaviour."""

    def evaluate(
        self,
        predicted_needs_investigation: bool,
        ground_truth_needs_investigation: bool,
    ) -> dict:
        """
        Parameters
        ----------
        predicted_needs_investigation   : bool
            Value of needs_further_investigation in agent output.
        ground_truth_needs_investigation: bool
            Expected value from ground_truth.needs_further_investigation.

        Returns
        -------
        dict with keys:
            correct_abstention  (bool) – True when both agree on True
            false_abstention    (bool) – Agent said needs-investigation but GT says no
            missed_abstention   (bool) – Agent said no-investigation but GT says yes
            correct             (bool) – Overall binary: prediction == ground truth
        """
        pred = bool(predicted_needs_investigation)
        gt = bool(ground_truth_needs_investigation)

        correct_abstention = pred and gt
        false_abstention = pred and not gt
        missed_abstention = not pred and gt
        correct = pred == gt

        return {
            "correct_abstention": correct_abstention,
            "false_abstention": false_abstention,
            "missed_abstention": missed_abstention,
            "correct": correct,
        }
