#!/usr/bin/env python
# eval/runner/run_agent_eval.py
"""
Full Agent RCA Evaluation Runner.

For each test case × repetition:
  1. Run the agent via main.py's run_with_fallback()
  2. Capture latency, token counts, tool trajectory, and result JSON
  3. Score with all evaluators
  4. Write one row to eval/results/run_{model}_{timestamp}.jsonl

CLI:
  python eval/runner/run_agent_eval.py --model nemotron_nim \\
      --cases eval/datasets/test/rca_cases.jsonl --reps 1
  python eval/runner/run_agent_eval.py --model azure_frontier \\
      --cases eval/datasets/dev/rca_cases.jsonl --reps 1
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Add project root to path so imports work regardless of CWD ───────────────
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from main import run_with_fallback, _extract_json   # noqa: E402
from eval.scorers.root_cause import RootCauseAccuracyEvaluator
from eval.scorers.evidence import EvidenceGroundingEvaluator
from eval.scorers.schema_grounding import SchemaHallucinationEvaluator
from eval.scorers.tool_calls import ToolCallEvaluator
from eval.scorers.abstention import AbstentionEvaluator

RESULTS_DIR = _ROOT / "eval" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# ── Load test cases ────────────────────────────────────────────────────────────

def load_cases(path: str) -> list[dict]:
    cases = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


# ── Token counting (best-effort from environment) ─────────────────────────────

def _try_get_token_counts() -> tuple[int | None, int | None]:
    """
    NeMo Agent Toolkit may expose token counts via env vars after a run.
    Returns (input_tokens, output_tokens) or (None, None) if not available.
    """
    try:
        inp = int(os.environ.get("NAT_LAST_INPUT_TOKENS", ""))
        out = int(os.environ.get("NAT_LAST_OUTPUT_TOKENS", ""))
        return inp, out
    except (ValueError, TypeError):
        return None, None


# ── Tool-trajectory extraction ────────────────────────────────────────────────

def _extract_tool_trajectory(raw_output: str) -> list[str]:
    """
    Attempt to extract the list of tool calls made during the run.
    The agent logger emits "TOOL CALL → {TOOLNAME}" lines; capture them.
    This is best-effort — production integration would hook into the NAT runner.
    """
    tools: list[str] = []
    known = {
        "query_lte_kpi", "query_nr_endc", "query_cm_config", "query_alarm_history",
        "query_neighbour_topology", "query_kpi_trend", "query_similar_incidents", "query_telecom_knowledge"
    }
    # Scan raw text for tool name mentions (case-insensitive)
    lower = raw_output.lower()
    for tool in known:
        if tool in lower:
            # Count rough occurrences to approximate trajectory
            count = lower.count(tool)
            tools.extend([tool] * count)
    # Deduplicate while preserving approximate order
    seen: set[str] = set()
    unique: list[str] = []
    for t in tools:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique


# ── Single-case runner ────────────────────────────────────────────────────────

async def run_one_case(
    case: dict,
    model: str,
    rep: int,
    eval_mode: str = "strict",
) -> dict:
    """Run a single test case and return the scored result row."""
    case_id = case["case_id"]
    incident_desc = case["incident"]["description"]
    gt = case["ground_truth"]

    # Inject case_id into the description so the agent can reference it
    prompt = incident_desc

    t0 = time.monotonic()
    raw_output = await run_with_fallback(prompt, model)
    latency_ms = int((time.monotonic() - t0) * 1000)

    rca = _extract_json(raw_output) or {}

    # Inject incident_id into agent output if missing
    if not rca.get("incident_id"):
        rca["incident_id"] = case_id

    # ── Extract fields ────────────────────────────────────────────────────────
    predicted_rc_code = rca.get("root_cause_code", "") or ""
    # If no structured code, try to infer from free-text root_cause
    if not predicted_rc_code:
        rc_text = (rca.get("root_cause", "") or "").lower()
        TEXT_TO_CODE = {
            "cellbarred": "CELL_BARRED_CHANGE", "cell barred": "CELL_BARRED_CHANGE",
            "administrativestate": "ADMIN_STATE_CHANGE", "admin state": "ADMIN_STATE_CHANGE",
            "bandwidth": "BANDWIDTH_CHANGE",
            "backhaul": "BACKHAUL_LINK_DOWN", "link down": "BACKHAUL_LINK_DOWN",
            "power failure": "POWER_FAILURE",
            "interference": "NEIGHBOUR_INTERFERENCE", "co-site": "NEIGHBOUR_INTERFERENCE",
            "en-dc": "NR_RANDOM_ACCESS_FAILURE", "endc": "NR_RANDOM_ACCESS_FAILURE",
            "5g nsa": "NR_RANDOM_ACCESS_FAILURE", "nr random": "NR_RANDOM_ACCESS_FAILURE",
            "undetermined": "UNDETERMINED", "insufficient": "UNDETERMINED",
        }
        for kw, code in TEXT_TO_CODE.items():
            if kw in rc_text:
                predicted_rc_code = code
                break
    predicted_evidence = rca.get("evidence", []) or []
    # Normalise evidence: accept both string and dict forms
    from eval.scorers.evidence import _normalise_evidence_item
    norm_evidence: list[dict] = [_normalise_evidence_item(ev) for ev in predicted_evidence]

    predicted_confidence = rca.get("confidence")
    # Confidence may be a string ("high"/"medium"/"low") in old-format output
    if isinstance(predicted_confidence, str):
        conf_map = {"high": 0.9, "medium": 0.6, "low": 0.3}
        predicted_confidence = conf_map.get(predicted_confidence.lower(), 0.3)

    predicted_needs_investigation = bool(
        rca.get("needs_further_investigation", False)
    )

    tool_trajectory = _extract_tool_trajectory(raw_output)
    input_tokens, output_tokens = _try_get_token_counts()

    # ── Score ─────────────────────────────────────────────────────────────────
    rc_result = RootCauseAccuracyEvaluator().evaluate(predicted_rc_code, gt)
    ev_result = EvidenceGroundingEvaluator().evaluate(norm_evidence, gt.get("required_evidence", []))
    hall_result = SchemaHallucinationEvaluator().evaluate(rca)
    tool_result = ToolCallEvaluator().evaluate(tool_trajectory, gt)
    abst_result = AbstentionEvaluator().evaluate(
        predicted_needs_investigation, gt.get("needs_further_investigation", False)
    )

    rca_correct = rc_result["correct"]

    row = {
        "run_id": str(uuid.uuid4()),
        "case_id": case_id,
        "model_id": model,
        "eval_mode": eval_mode,
        "repetition": rep,
        "family": case.get("family", ""),
        "difficulty": case.get("difficulty", ""),

        # Prediction
        "predicted_root_cause_code": predicted_rc_code,
        "ground_truth_root_cause_code": gt.get("root_cause_code", ""),
        "rca_correct": rca_correct,
        "in_acceptable": rc_result["in_acceptable"],
        "rc_score": rc_result["score"],

        # Evidence
        "evidence_precision": ev_result["precision"],
        "evidence_recall": ev_result["recall"],
        "evidence_f1": ev_result["f1"],
        "unsupported_evidence_rate": ev_result["unsupported_rate"],

        # Schema
        "schema_valid_rate": hall_result["valid_rate"],
        "hallucinated_fields": hall_result["hallucinated_fields"],
        "hallucinated_count": hall_result["hallucinated_count"],

        # Tools
        "required_tool_recall": tool_result["required_tool_recall"],
        "tool_precision": tool_result["tool_precision"],
        "tool_f1": tool_result["tool_f1"],
        "unnecessary_call_rate": tool_result["unnecessary_call_rate"],
        "tool_trajectory": tool_trajectory,
        "required_tools_missing": tool_result["required_missing"],

        # Abstention
        "predicted_needs_investigation": predicted_needs_investigation,
        "ground_truth_needs_investigation": gt.get("needs_further_investigation", False),
        "correct_abstention": abst_result["correct_abstention"],
        "false_abstention": abst_result["false_abstention"],
        "missed_abstention": abst_result["missed_abstention"],
        "abstention_correct": abst_result["correct"],

        # Confidence
        "confidence": predicted_confidence,

        # Performance
        "latency_ms": latency_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,

        # Raw
        "raw_rca": rca,
    }

    return row


# ── Batch runner ──────────────────────────────────────────────────────────────

async def run_eval(model: str, cases_path: str, reps: int, eval_mode: str) -> None:
    cases = load_cases(cases_path)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out_file = RESULTS_DIR / f"run_{model}_{timestamp}.jsonl"

    all_rows: list[dict] = []
    total = len(cases) * reps
    done = 0

    print(f"\n{'─'*60}")
    print(f"  Eval: {eval_mode}  |  Model: {model}")
    print(f"  Cases: {len(cases)}  |  Reps: {reps}  |  Total runs: {total}")
    print(f"  Output: {out_file}")
    print(f"{'─'*60}\n")

    with open(out_file, "w") as out_f:
        for rep in range(1, reps + 1):
            for case in cases:
                case_id = case["case_id"]
                print(f"  [{done+1}/{total}] {case_id} rep={rep} ... ", end="", flush=True)
                try:
                    row = await run_one_case(case, model, rep, eval_mode)
                    status = "✓" if row["rca_correct"] else "✗"
                    print(
                        f"{status}  rc={row['predicted_root_cause_code']}"
                        f"  ev_f1={row['evidence_f1']:.2f}"
                        f"  hall={row['hallucinated_count']}"
                        f"  {row['latency_ms']}ms"
                    )
                except Exception as exc:
                    print(f"ERROR: {exc}")
                    row = {
                        "run_id": str(uuid.uuid4()),
                        "case_id": case_id,
                        "model_id": model,
                        "eval_mode": eval_mode,
                        "repetition": rep,
                        "family": case.get("family", ""),
                        "difficulty": case.get("difficulty", ""),
                        "error": str(exc),
                        "rca_correct": False,
                    }

                out_f.write(json.dumps(row) + "\n")
                out_f.flush()
                all_rows.append(row)
                done += 1

    # ── Summary ───────────────────────────────────────────────────────────────
    valid = [r for r in all_rows if "error" not in r]
    if not valid:
        print("\nNo valid results to summarise.")
        return

    rca_acc = sum(r["rca_correct"] for r in valid) / len(valid) * 100
    ev_f1 = sum(r.get("evidence_f1", 0) for r in valid) / len(valid)
    hall_rate = sum(r.get("hallucinated_count", 0) > 0 for r in valid) / len(valid) * 100
    abst_acc = sum(r.get("abstention_correct", False) for r in valid) / len(valid) * 100
    avg_lat = sum(r.get("latency_ms", 0) for r in valid) / len(valid)

    print(f"\n{'─'*60}")
    print(f"  SUMMARY — {model}")
    print(f"{'─'*60}")
    print(f"  RCA Accuracy:       {rca_acc:.1f}%")
    print(f"  Evidence F1 (avg):  {ev_f1:.3f}")
    print(f"  Hallucination rate: {hall_rate:.1f}%")
    print(f"  Abstention acc:     {abst_acc:.1f}%")
    print(f"  Avg latency:        {avg_lat:.0f}ms")
    print(f"  Results written to: {out_file}")
    print(f"{'─'*60}\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run agent-level RCA evaluation for a given model and case set."
    )
    parser.add_argument(
        "--model",
        default="nemotron_nim",
        help="Model ID matching workflow.yml llms key (default: nemotron_nim)",
    )
    parser.add_argument(
        "--cases",
        default="eval/datasets/test/rca_cases.jsonl",
        help="Path to the JSONL case file (default: eval/datasets/test/rca_cases.jsonl)",
    )
    parser.add_argument(
        "--reps",
        type=int,
        default=1,
        help="Number of repetitions per case (default: 1)",
    )
    parser.add_argument(
        "--mode",
        default="strict",
        choices=["strict", "optimized"],
        help="Eval mode label written to results (default: strict)",
    )
    args = parser.parse_args()

    asyncio.run(run_eval(args.model, args.cases, args.reps, args.mode))


if __name__ == "__main__":
    main()
