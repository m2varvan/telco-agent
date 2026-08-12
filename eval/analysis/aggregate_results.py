#!/usr/bin/env python
# eval/analysis/aggregate_results.py
"""
Aggregate multiple eval result JSONL files and produce a comparison table.

CLI:
  python eval/analysis/aggregate_results.py eval/results/
  python eval/analysis/aggregate_results.py eval/results/run_nemotron*.jsonl eval/results/run_azure*.jsonl

Output:
  Model               RCA_Acc  Evidence_F1  Hall_Rate  Abstention_Acc  p50_lat  p95_lat  Cost_Est
  nemotron_nim         XX.X%     X.XX         X.X%       XX.X%          XXXXms   XXXXms   $X.XX
  azure_frontier       XX.X%     X.XX         X.X%       XX.X%          XXXXms   XXXXms   $X.XX
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path


# ── Cost estimation constants ─────────────────────────────────────────────────
# Rough estimates; override by setting env vars COST_PER_1K_INPUT and COST_PER_1K_OUTPUT
# for the model under test.
DEFAULT_COST_INPUT_PER_1K  = float(os.getenv("COST_PER_1K_INPUT", "0.005"))   # $ per 1k input tokens
DEFAULT_COST_OUTPUT_PER_1K = float(os.getenv("COST_PER_1K_OUTPUT", "0.015"))  # $ per 1k output tokens


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


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = int(len(sorted_vals) * pct / 100)
    idx = min(idx, len(sorted_vals) - 1)
    return sorted_vals[idx]


def _estimate_cost(input_tokens: int | None, output_tokens: int | None) -> float:
    inp = (input_tokens or 0) / 1000.0 * DEFAULT_COST_INPUT_PER_1K
    out = (output_tokens or 0) / 1000.0 * DEFAULT_COST_OUTPUT_PER_1K
    return inp + out


def aggregate(rows: list[dict]) -> dict[str, dict]:
    """
    Group rows by model_id and compute per-model aggregate metrics.
    Returns {model_id: metrics_dict}.
    """
    by_model: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        model = row.get("model_id", "unknown")
        by_model[model].append(row)

    result: dict[str, dict] = {}
    for model, model_rows in by_model.items():
        valid = [r for r in model_rows if "error" not in r]
        n = len(valid)
        if n == 0:
            continue

        rca_correct = [r.get("rca_correct", False) for r in valid]
        ev_f1_vals  = [r.get("evidence_f1", 0.0) for r in valid]
        hall_flags  = [r.get("hallucinated_count", 0) > 0 for r in valid]
        abst_flags  = [r.get("abstention_correct", False) for r in valid]
        latencies   = [r.get("latency_ms", 0) for r in valid]
        costs       = [
            _estimate_cost(r.get("input_tokens"), r.get("output_tokens"))
            for r in valid
        ]

        rca_acc = sum(rca_correct) / n * 100
        ev_f1   = sum(ev_f1_vals) / n
        hall_rate = sum(hall_flags) / n * 100
        abst_acc  = sum(abst_flags) / n * 100
        p50_lat   = _percentile(latencies, 50)
        p95_lat   = _percentile(latencies, 95)
        total_cost = sum(costs)
        correct_count = sum(rca_correct)
        cost_per_correct = (
            total_cost / correct_count if correct_count > 0 else float("inf")
        )

        # Per-family breakdown
        family_acc: dict[str, dict] = {}
        by_family: dict[str, list[dict]] = defaultdict(list)
        for r in valid:
            by_family[r.get("family", "unknown")].append(r)
        for fam, fam_rows in by_family.items():
            fam_n = len(fam_rows)
            fam_correct = sum(r.get("rca_correct", False) for r in fam_rows)
            family_acc[fam] = {
                "n": fam_n,
                "correct": fam_correct,
                "accuracy_pct": round(fam_correct / fam_n * 100, 1),
            }

        result[model] = {
            "n": n,
            "rca_accuracy_pct": round(rca_acc, 1),
            "evidence_f1": round(ev_f1, 3),
            "hallucination_rate_pct": round(hall_rate, 1),
            "abstention_accuracy_pct": round(abst_acc, 1),
            "p50_latency_ms": int(p50_lat),
            "p95_latency_ms": int(p95_lat),
            "total_cost_usd": round(total_cost, 4),
            "cost_per_correct_rca_usd": round(cost_per_correct, 4),
            "family_accuracy": family_acc,
        }

    return result


def _format_table(aggregated: dict[str, dict]) -> str:
    hdr = (
        f"{'Model':<22} {'RCA_Acc':>8} {'Evidence_F1':>12} "
        f"{'Hall_Rate':>10} {'Abstention_Acc':>15} "
        f"{'p50_lat':>9} {'p95_lat':>9} {'Cost_Est':>9}"
    )
    sep = "─" * len(hdr)
    lines = [sep, hdr, sep]
    for model, m in aggregated.items():
        lines.append(
            f"{model:<22} "
            f"{m['rca_accuracy_pct']:>7.1f}% "
            f"{m['evidence_f1']:>12.3f} "
            f"{m['hallucination_rate_pct']:>9.1f}% "
            f"{m['abstention_accuracy_pct']:>14.1f}% "
            f"{m['p50_latency_ms']:>8}ms "
            f"{m['p95_latency_ms']:>8}ms "
            f"${m['total_cost_usd']:>7.4f}"
        )
    lines.append(sep)
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python eval/analysis/aggregate_results.py eval/results/")
        sys.exit(1)

    arg = sys.argv[1]
    target = Path(arg)

    if target.is_dir():
        paths = sorted(target.glob("*.jsonl"))
    else:
        # Multiple glob patterns or explicit files
        paths = []
        for a in sys.argv[1:]:
            p = Path(a)
            if p.is_file():
                paths.append(p)
            else:
                # Try glob
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

    aggregated = aggregate(rows)
    print("\n" + _format_table(aggregated))

    # Per-family breakdown
    print("\nPer-Family RCA Accuracy:")
    fam_hdr = f"  {'Model':<22} {'Family':<18} {'N':>4} {'Correct':>8} {'Acc%':>8}"
    print(fam_hdr)
    print("  " + "─" * (len(fam_hdr) - 2))
    for model, m in aggregated.items():
        for fam, fm in sorted(m["family_accuracy"].items()):
            print(
                f"  {model:<22} {fam:<18} {fm['n']:>4} "
                f"{fm['correct']:>8} {fm['accuracy_pct']:>7.1f}%"
            )

    print(f"\nCost per correct RCA:")
    for model, m in aggregated.items():
        cpr = m["cost_per_correct_rca_usd"]
        cpr_s = f"${cpr:.4f}" if cpr != float("inf") else "N/A (no correct)"
        print(f"  {model:<22} {cpr_s}")
    print()


if __name__ == "__main__":
    main()
