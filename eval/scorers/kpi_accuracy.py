# eval/scorers/kpi_accuracy.py
"""
KPI Accuracy Evaluator.

Provides two functions:
  evaluate_kpi_value        – numeric correctness within tolerance
  evaluate_degradation_detection – whether the status string was correctly flagged
"""
from __future__ import annotations


def evaluate_kpi_value(
    computed: float | None,
    expected: float,
    kpi_name: str,
    tolerance: float = 0.1,
) -> dict:
    """
    Evaluate whether a computed KPI value is within tolerance of the expected value.

    Parameters
    ----------
    computed  : float | None – Value returned by the agent/tool. None = unavailable.
    expected  : float        – Ground-truth expected value.
    kpi_name  : str          – Human-readable KPI name (used in result label).
    tolerance : float        – Absolute tolerance (default 0.1 percentage points).

    Returns
    -------
    dict with keys:
        correct    (bool)
        abs_error  (float | None)
        rel_error  (float | None)
        kpi_name   (str)
    """
    if computed is None:
        return {
            "correct": False,
            "abs_error": None,
            "rel_error": None,
            "kpi_name": kpi_name,
        }

    abs_error = abs(computed - expected)
    rel_error = abs_error / abs(expected) if expected != 0.0 else None
    correct = abs_error <= tolerance

    return {
        "correct": correct,
        "abs_error": round(abs_error, 6),
        "rel_error": round(rel_error, 6) if rel_error is not None else None,
        "kpi_name": kpi_name,
    }


def evaluate_degradation_detection(status: str, expected_degraded: bool) -> bool:
    """
    Check whether the degradation status string matches the expected state.

    Parameters
    ----------
    status           : str  – One of "ok", "degraded", "unavailable".
    expected_degraded: bool – True if the ground truth says KPI should be degraded.

    Returns
    -------
    bool – True if the prediction is correct.
    """
    predicted_degraded = status == "degraded"
    return predicted_degraded == expected_degraded
