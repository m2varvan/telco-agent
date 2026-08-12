# eval/scorers.py
"""
T1–T5 scoring functions for the evaluation harness.
Requirements: 9.1, 9.3
"""


def score_t1(response: str, expected: str) -> int:
    """
    T1 Schema understanding — exact-match scoring (0 or 1).
    Returns 1 if expected string is found (case-insensitive) in response, else 0.
    """
    return 1 if expected.strip().lower() in response.strip().lower() else 0


def score_t2(computed: float | None, expected: float, tolerance: float = 0.01) -> int:
    """
    T2 KPI calculation — numeric tolerance ±0.01 percentage points or ±0.01 kbps/ms.
    Returns 1 if abs(computed - expected) <= tolerance, else 0.
    """
    if computed is None:
        return 0
    return 1 if abs(computed - expected) <= tolerance else 0


def score_t3(result_rows: list[dict], expected_rows: list[dict], key: str) -> int:
    """
    T3 Multi-table join — row/set match scoring (0 or 1).
    Returns 1 if the set of key values in result_rows equals that of expected_rows.
    """
    result_keys = {r[key] for r in result_rows}
    expected_keys = {r[key] for r in expected_rows}
    return 1 if result_keys == expected_keys else 0


def score_t4(rca_output: dict, ground_truth_category: str, evidence_keywords: list[str]) -> int:
    """
    T4 RCA reasoning — rubric scoring 0–3:
      3: root_cause matches category AND >=1 evidence keyword found in evidence array
      2: root_cause matches category only (no keyword found)
      1: root_cause does not match BUT evidence keyword(s) found
      0: neither matches
    """
    root_cause = rca_output.get("root_cause", "") or ""
    rc_match = ground_truth_category.lower() in root_cause.lower()
    evidence_str = " ".join(rca_output.get("evidence", []) or [])
    ev_match = any(kw in evidence_str for kw in evidence_keywords)

    if rc_match and ev_match:
        return 3
    if rc_match:
        return 2
    if ev_match:
        return 1
    return 0


def score_t5(generated_sql: str, required_tables: list[str], required_joins: list[str]) -> int:
    """
    T5 SQL generation — valid SQL scoring.
    Returns 1 if all required_tables and required_joins appear in generated_sql, else 0.
    """
    sql_lower = generated_sql.lower()
    tables_ok = all(t.lower() in sql_lower for t in required_tables)
    joins_ok  = all(j.lower() in sql_lower for j in required_joins)
    return 1 if (tables_ok and joins_ok) else 0
