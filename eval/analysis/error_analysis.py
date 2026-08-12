#!/usr/bin/env python
# eval/analysis/error_analysis.py
"""
Error taxonomy analysis for eval result JSONL files.

Maps failed cases to error codes from the plan's E01-E24 taxonomy and
produces an error distribution table per model.

CLI:
  python eval/analysis/error_analysis.py eval/results/
  python eval/analysis/error_analysis.py eval/results/run_nemotron*.jsonl
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path


# ── Error taxonomy (plan Section 20) ─────────────────────────────────────────
ERROR_TAXONOMY: dict[str, str] = {
    "E01": "Schema misunderstanding",
    "E02": "Hallucinated table/field/counter",
    "E03": "Wrong KPI formula",
    "E04": "Incorrect arithmetic",
    "E05": "SQL syntax failure",
    "E06": "SQL semantic/result failure",
    "E07": "Wrong tool selected",
    "E08": "Required tool omitted",
    "E09": "Wrong tool argument",
    "E10": "Wrong cell/site/time window",
    "E11": "Relevant evidence missed",
    "E12": "Distractor evidence followed",
    "E13": "Correlation treated as causation",
    "E14": "Contradictory evidence ignored",
    "E15": "Premature conclusion",
    "E16": "Failed to revise hypothesis",
    "E17": "Incorrect RCA despite correct evidence",
    "E18": "Correct RCA with unsupported reasoning",
    "E19": "Overconfidence",
    "E20": "Unnecessary abstention",
    "E21": "Failed to abstain when evidence insufficient",
    "E22": "Agent loop / excessive calls",
    "E23": "Output schema violation",
    "E24": "Timeout/provider failure",
}


def assign_error_codes(row: dict) -> list[str]:
    """
    Assign one or more error codes to a result row based on the scoring fields.

    Priority mapping (plan Section 20 / eval plan mapping spec):
      hallucinated_count > 0             → E02
      required_tool_recall < 1.0         → E08
      tool_precision < 0.7               → E07
      missed_abstention == True          → E21
      false_abstention == True           → E20
      confidence >= 0.8 and not correct  → E19
      evidence_recall < 0.5              → E11
      Default (wrong RCA, no other code) → E17
    """
    codes: list[str] = []

    # E02 – hallucination
    if (row.get("hallucinated_count") or 0) > 0:
        codes.append("E02")

    # E08 – required tool omitted
    req_recall = row.get("required_tool_recall")
    if req_recall is not None and req_recall < 1.0:
        codes.append("E08")

    # E07 – wrong tool selected
    tool_prec = row.get("tool_precision")
    if tool_prec is not None and tool_prec < 0.7:
        codes.append("E07")

    # E21 – failed to abstain
    if row.get("missed_abstention", False):
        codes.append("E21")

    # E20 – unnecessary abstention
    if row.get("false_abstention", False):
        codes.append("E20")

    # E19 – overconfidence (high confidence, wrong RCA)
    conf = row.get("confidence")
    rca_correct = row.get("rca_correct", False)
    if conf is not None and not rca_correct:
        conf_float = float(conf) if isinstance(conf, (int, float)) else 0.0
        if conf_float >= 0.8:
            codes.append("E19")

    # E11 – relevant evidence missed
    ev_recall = row.get("evidence_recall")
    if ev_recall is not None and ev_recall < 0.5:
        codes.append("E11")

    # E24 – provider / timeout failure
    if "error" in row:
        codes.append("E24")
        return codes

    # Default fallback for wrong RCA with no other specific code
    if not rca_correct and not codes:
        codes.append("E17")

    return codes if codes else []


def _load_rows(paths: list[Path]) -> list[dict]:
    rows = []
    for p in paths:
        with open(p) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    return rows


def analyse(rows: list[dict]) -> dict[str, dict]:
    """
    Returns {model_id: {error_code: count, ...}}.
    Only failed or error rows are included; correct rows produce no error codes.
    """
    by_model: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for row in rows:
        model = row.get("model_id", "unknown")
        codes = assign_error_codes(row)
        for code in codes:
            by_model[model][code] += 1

    return {model: dict(counts) for model, counts in by_model.items()}


def _format_table(analysis: dict[str, dict]) -> str:
    models = sorted(analysis.keys())
    all_codes = sorted(
        {code for m_counts in analysis.values() for code in m_counts.keys()}
    )

    if not all_codes:
        return "  No errors found in result files."

    col_w = 14
    hdr = f"  {'Code':<6} {'Description':<40}" + "".join(
        f" {m[:col_w]:>{col_w}}" for m in models
    )
    sep = "  " + "─" * (len(hdr) - 2)
    lines = [sep, hdr, sep]

    for code in all_codes:
        desc = ERROR_TAXONOMY.get(code, "Unknown")[:38]
        counts_str = "".join(
            f" {analysis[m].get(code, 0):>{col_w}}" for m in models
        )
        lines.append(f"  {code:<6} {desc:<40}{counts_str}")

    lines.append(sep)
    # Totals
    totals_str = "".join(
        f" {sum(analysis[m].values()):>{col_w}}" for m in models
    )
    lines.append(f"  {'TOTAL':<6} {'':<40}{totals_str}")
    lines.append(sep)
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python eval/analysis/error_analysis.py eval/results/")
        sys.exit(1)

    arg = sys.argv[1]
    target = Path(arg)

    if target.is_dir():
        paths = sorted(target.glob("*.jsonl"))
    else:
        paths = []
        for a in sys.argv[1:]:
            p = Path(a)
            if p.is_file():
                paths.append(p)
            else:
                parent = p.parent
                paths.extend(sorted(parent.glob(p.name)))

    if not paths:
        print(f"No JSONL files found in: {arg}")
        sys.exit(1)

    print(f"\nLoading {len(paths)} result file(s)…")
    rows = _load_rows(paths)
    print(f"Loaded {len(rows)} result rows.")

    if not rows:
        print("No rows found.")
        sys.exit(1)

    analysis = analyse(rows)

    print("\nError Distribution by Model (E01–E24 taxonomy):\n")
    print(_format_table(analysis))

    # Per-model percentage breakdown
    print("\nPercentage breakdown per model (fraction of all error assignments):")
    for model, counts in sorted(analysis.items()):
        total = sum(counts.values())
        if total == 0:
            print(f"  {model}: no errors")
            continue
        print(f"\n  {model} ({total} error assignments):")
        for code, count in sorted(counts.items(), key=lambda x: -x[1]):
            desc = ERROR_TAXONOMY.get(code, "Unknown")
            pct = count / total * 100
            print(f"    {code}  {desc:<40}  {count:>4}  ({pct:.1f}%)")
    print()


if __name__ == "__main__":
    main()
