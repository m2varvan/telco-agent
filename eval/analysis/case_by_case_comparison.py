#!/usr/bin/env python
# eval/analysis/case_by_case_comparison.py
"""
Case-by-Case Side-by-Side Comparison Script
Compares gpt_5_4 vs. nemotron_nim for every incident case in eval/results/.
"""
import json
import glob
from pathlib import Path

def load_latest_run(model_name: str) -> dict[str, dict]:
    files = sorted(glob.glob(f"eval/results/run_{model_name}_*.jsonl"))
    if not files:
        return {}
    latest = files[-1]
    rows = {}
    with open(latest, "r") as f:
        for line in f:
            if not line.strip(): continue
            d = json.loads(line)
            rows[d["case_id"]] = d
    return rows

def main():
    gpt_rows = load_latest_run("gpt_5_4")
    nemo_rows = load_latest_run("nemotron_nim")

    all_case_ids = sorted(list(set(gpt_rows.keys()) | set(nemo_rows.keys())))

    print("=" * 110)
    print(f"{'CASE ID':<16} | {'METRIC':<18} | {'GPT-5.4 (Frontier)':<34} | {'Nemotron NIM (Open-Source)':<34}")
    print("=" * 110)

    same_rca_count = 0
    total_cases = 0

    for case_id in all_case_ids:
        g = gpt_rows.get(case_id, {})
        n = nemo_rows.get(case_id, {})
        total_cases += 1

        g_rca_ok = "✅ CORRECT" if g.get("rca_correct") else "❌ WRONG"
        n_rca_ok = "✅ CORRECT" if n.get("rca_correct") else "❌ WRONG"

        if g.get("rca_correct") == n.get("rca_correct"):
            same_rca_count += 1

        g_lat = f"{g.get('latency_ms', 0)} ms ({g.get('latency_ms', 0)/1000:.1f}s)"
        n_lat = f"{n.get('latency_ms', 0)} ms ({n.get('latency_ms', 0)/1000:.1f}s)"

        g_f1 = f"{g.get('evidence_f1', 0.0):.3f}"
        n_f1 = f"{n.get('evidence_f1', 0.0):.3f}"

        g_hall = f"{g.get('hallucinated_count', 0)} items"
        n_hall = f"{n.get('hallucinated_count', 0)} items"

        g_tools = ", ".join(g.get("actual_tools", [])) or "None"
        n_tools = ", ".join(n.get("actual_tools", [])) or "None"

        g_rca = (g.get("rca_output", {}).get("root_cause") or "")[:32]
        n_rca = (n.get("rca_output", {}).get("root_cause") or "")[:32]

        print(f"{case_id:<16} | {'RCA Status':<18} | {g_rca_ok:<34} | {n_rca_ok:<34}")
        print(f"{'':<16} | {'Latency':<18} | {g_lat:<34} | {n_lat:<34}")
        print(f"{'':<16} | {'Evidence F1':<18} | {g_f1:<34} | {n_f1:<34}")
        print(f"{'':<16} | {'Hallucinations':<18} | {g_hall:<34} | {n_hall:<34}")
        print(f"{'':<16} | {'Tools Called':<18} | {g_tools[:34]:<34} | {n_tools[:34]:<34}")
        print(f"{'':<16} | {'RCA Output Text':<18} | {g_rca:<34} | {n_rca:<34}")
        print("-" * 110)

    print(f"\nSummary: {same_rca_count}/{total_cases} cases returned identical correctness status between GPT-5.4 and Nemotron Telco NIM.")

if __name__ == "__main__":
    main()
