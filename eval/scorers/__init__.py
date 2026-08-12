# eval/scorers/__init__.py
"""
Full evaluation scorer package.
Exposes all evaluator classes for use by the runner.
Also exposes legacy T1–T5 scoring functions for backward compatibility with tests.
"""
from eval.scorers.root_cause import RootCauseAccuracyEvaluator
from eval.scorers.evidence import EvidenceGroundingEvaluator
from eval.scorers.schema_grounding import SchemaHallucinationEvaluator
from eval.scorers.tool_calls import ToolCallEvaluator
from eval.scorers.kpi_accuracy import evaluate_kpi_value, evaluate_degradation_detection
from eval.scorers.calibration import CalibrationCollector
from eval.scorers.abstention import AbstentionEvaluator

# ── Legacy T1–T5 functions (used by tests and basic eval harness) ─────────────

def score_t1(response: str, expected: str) -> int:
    """T1 Schema understanding — exact-match scoring (0 or 1)."""
    return 1 if expected.strip().lower() in response.strip().lower() else 0


def score_t2(computed, expected: float, tolerance: float = 0.01) -> int:
    """T2 KPI calculation — numeric tolerance."""
    if computed is None:
        return 0
    return 1 if abs(computed - expected) <= tolerance else 0


def score_t3(result_rows: list, expected_rows: list, key: str) -> int:
    """T3 Multi-table join — set match scoring."""
    return 1 if {r[key] for r in result_rows} == {r[key] for r in expected_rows} else 0


def score_t4(rca_output: dict, ground_truth_category: str, evidence_keywords: list) -> int:
    """
    T4 RCA reasoning — rubric 0–3:
    3 = category match AND evidence keyword found
    2 = category match only
    1 = evidence keyword only
    0 = neither
    """
    rc = (rca_output.get("root_cause", "") or "").lower()
    rc_match = ground_truth_category.lower() in rc
    ev_str = " ".join(rca_output.get("evidence", []) or [])
    ev_match = any(kw in ev_str for kw in evidence_keywords)
    if rc_match and ev_match:
        return 3
    if rc_match:
        return 2
    if ev_match:
        return 1
    return 0


def score_t5(generated_sql: str, required_tables: list, required_joins: list) -> int:
    """T5 SQL generation — tables + join keys present."""
    s = generated_sql.lower()
    return 1 if (all(t.lower() in s for t in required_tables) and
                 all(j.lower() in s for j in required_joins)) else 0


__all__ = [
    "RootCauseAccuracyEvaluator",
    "EvidenceGroundingEvaluator",
    "SchemaHallucinationEvaluator",
    "ToolCallEvaluator",
    "evaluate_kpi_value",
    "evaluate_degradation_detection",
    "CalibrationCollector",
    "AbstentionEvaluator",
    "score_t1", "score_t2", "score_t3", "score_t4", "score_t5",
]
