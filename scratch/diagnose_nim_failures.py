import json
from pathlib import Path

result_file = Path("eval/results/run_nemotron_nim_20260814T141205.jsonl")

cases = []
with open(result_file) as f:
    for line in f:
        cases.append(json.loads(line))

print(f"Total cases loaded: {len(cases)}")
print("=" * 80)

failures = [c for c in cases if not c.get("rca_correct", False)]
print(f"Total True Failures: {len(failures)} / {len(cases)}\n")

for idx, c in enumerate(failures, 1):
    case_id = c.get("case_id")
    predicted_rc = c.get("predicted_root_cause_code")
    gt_rc = c.get("ground_truth_root_cause_code")
    in_acceptable = c.get("in_acceptable", False)
    case_family = c.get("family", "unknown")
    latency = c.get("latency_ms", 0)
    raw_rca = c.get("raw_rca", {})
    root_cause_text = raw_rca.get("root_cause", "")
    
    print(f"{idx}. Case: {case_id} | Family: {case_family} | AcceptableMatch: {in_acceptable}")
    print(f"   Predicted Code:  '{predicted_rc}'")
    print(f"   GroundTruth Code: '{gt_rc}'")
    print(f"   Root Cause Text: '{root_cause_text[:120]}...'")
    print(f"   Latency: {latency}ms")
    print("-" * 80)
