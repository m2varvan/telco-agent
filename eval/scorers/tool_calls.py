# eval/scorers/tool_calls.py
"""
Tool Call Evaluator.

Scores the agent's tool trajectory against the ground-truth required and
optional tools.

Metrics:
  required_tool_recall    = required tools called / all required tools
  tool_precision          = relevant calls / all calls
  tool_f1                 = harmonic mean
  unnecessary_call_rate   = irrelevant calls / all calls
"""
from __future__ import annotations


class ToolCallEvaluator:
    """Evaluates the agent's tool-call trajectory."""

    def evaluate(self, tool_trajectory: list[str], ground_truth: dict) -> dict:
        """
        Parameters
        ----------
        tool_trajectory : list[str]
            Ordered list of tool names called by the agent during one run.
        ground_truth : dict
            Ground-truth block. Used keys:
            - required_tools (list[str])
            - optional_tools (list[str])

        Returns
        -------
        dict with keys:
            required_tool_recall  (float)
            tool_precision        (float)
            tool_f1               (float)
            unnecessary_call_rate (float)
            required_called       (list[str])  – required tools that were called
            required_missing      (list[str])  – required tools that were NOT called
            unnecessary_calls     (list[str])  – calls not in required or optional
        """
        required: set[str] = {
            t.strip() for t in ground_truth.get("required_tools", [])
        }
        optional: set[str] = {
            t.strip() for t in ground_truth.get("optional_tools", [])
        }
        relevant: set[str] = required | optional

        # Normalise trajectory
        called: list[str] = [t.strip() for t in tool_trajectory if t]
        called_set: set[str] = set(called)

        n_called = len(called)
        n_required = len(required)

        required_called = sorted(required & called_set)
        required_missing = sorted(required - called_set)
        unnecessary = [t for t in called if t not in relevant]

        required_tool_recall = (
            len(required_called) / n_required if n_required > 0 else 1.0
        )
        # Precision: fraction of all calls that are relevant (required or optional)
        relevant_calls = [t for t in called if t in relevant]
        tool_precision = len(relevant_calls) / n_called if n_called > 0 else 1.0

        tool_f1 = (
            (2 * tool_precision * required_tool_recall)
            / (tool_precision + required_tool_recall)
            if (tool_precision + required_tool_recall) > 0
            else 0.0
        )
        unnecessary_call_rate = len(unnecessary) / n_called if n_called > 0 else 0.0

        return {
            "required_tool_recall": round(required_tool_recall, 4),
            "tool_precision": round(tool_precision, 4),
            "tool_f1": round(tool_f1, 4),
            "unnecessary_call_rate": round(unnecessary_call_rate, 4),
            "required_called": required_called,
            "required_missing": required_missing,
            "unnecessary_calls": unnecessary,
        }
