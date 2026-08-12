# eval/scorers/root_cause.py
"""
Root Cause Accuracy Evaluator.

Deterministic scorer: compare predicted root_cause_code against ground truth.
Scoring:
  - 1.0  if predicted == ground_truth.root_cause_code  (exact match)
  - 0.5  if predicted in ground_truth.acceptable_root_cause_codes (partial credit)
  - 0.0  otherwise
"""
from __future__ import annotations


class RootCauseAccuracyEvaluator:
    """Evaluates RCA root-cause code accuracy against structured ground truth."""

    def evaluate(self, predicted_code: str, ground_truth: dict) -> dict:
        """
        Compare predicted_code against the ground truth.

        Parameters
        ----------
        predicted_code : str
            The root_cause_code returned by the agent.
        ground_truth : dict
            The ground_truth block from the test case. Must contain:
            - root_cause_code (str)
            - acceptable_root_cause_codes (list[str])

        Returns
        -------
        dict with keys:
            correct        (bool)  – exact match with primary root_cause_code
            in_acceptable  (bool)  – predicted is in acceptable_root_cause_codes
            score          (float) – 1.0 / 0.5 / 0.0
        """
        primary = ground_truth.get("root_cause_code", "")
        acceptable = set(ground_truth.get("acceptable_root_cause_codes", []))

        # Normalise
        pred = (predicted_code or "").strip().upper()
        primary = primary.strip().upper()
        acceptable = {a.strip().upper() for a in acceptable}

        correct = pred == primary
        in_acceptable = pred in acceptable

        # Also try free-text match for models that return natural language
        # instead of canonical codes (e.g. "CELLBARRED change" → CELL_BARRED_CHANGE)
        TEXT_MAP = {
            "CELL_BARRED_CHANGE":      ["cellbarred", "cell barred", "barring", "cell_barred"],
            "ADMIN_STATE_CHANGE":      ["adminstate", "admin_state", "administrativestate", "admin state", "locked", "unlock"],
            "BANDWIDTH_CHANGE":        ["bandwidth", "dlchannelbandwidth", "bw change"],
            "POWER_CONFIG_CHANGE":     ["power config", "transmission power", "maximumtransmissionpower"],
            "BACKHAUL_LINK_DOWN":      ["backhaul", "link down", "fibre", "fiber", "backhaul link"],
            "POWER_FAILURE":           ["power failure", "power outage", "rectifier"],
            "NEIGHBOUR_INTERFERENCE":  ["interference", "neighbour", "neighbor", "co-site"],
            "NR_RANDOM_ACCESS_FAILURE":["random access", "nr ra", "endc", "en-dc", "5g", "nr failure"],
            "UNDETERMINED":            ["undetermined", "insufficient", "ambiguous", "unclear", "unknown"],
        }

        if not correct and not in_acceptable:
            pred_lower = (predicted_code or "").lower()
            for code, keywords in TEXT_MAP.items():
                if any(kw in pred_lower for kw in keywords):
                    if code == primary:
                        correct = True
                        in_acceptable = True
                    elif code in acceptable:
                        in_acceptable = True
                    break

        if correct:
            score = 1.0
        elif in_acceptable:
            score = 0.5
        else:
            score = 0.0

        return {
            "correct": correct,
            "in_acceptable": in_acceptable,
            "score": score,
            "predicted": pred,
            "expected": primary,
        }
