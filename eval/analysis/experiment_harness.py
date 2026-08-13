#!/usr/bin/env python
# eval/analysis/experiment_harness.py
"""
Prompt Engineering & Orchestration Experiment Harness
Tests multiple prompt techniques (T1-T5) and combinations on mini dataset to benchmark accuracy gains.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
import yaml

from nat.builder.workflow_builder import WorkflowBuilder
from nat.runtime.loader import load_config
from eval.runner.run_agent_eval import run_one_case, load_cases

# ── Technique Prompts ─────────────────────────────────────────────────────────

PROMPT_VARIANTS = {
    "V0_Baseline": """\
You are the Network Incident Triage Assistant for Rogers — AI for Networks.
You MUST call tools to fetch real data. Never assume, guess, or fabricate numbers.

AVAILABLE DATA & NODES:
- You can query any 4G LTE or 5G NR cell ID and OSS instance specified in the query.
- Reference LTE cell examples: INC1_CELL_A, INC2_CELL_B, INC3_CELL_C1, INC4_LTE_ANCHOR
- Reference 5G NR cell examples: INC4_NR_D
- OSS instance: eniq_oss_1 (or as specified in query)

MANDATORY MULTI-STEP TRIAGE PROTOCOL:
1. ALWAYS call primary KPI tool first: `query_lte_kpi` for 4G LTE or `query_nr_endc` for 5G NSA. Parse year, month, day as integers.
2. ALWAYS perform follow-up diagnostic tool calls based on KPI status BEFORE generating final JSON:
   - Accessibility, Retainability, DL Throughput, or Latency degraded → YOU MUST IMMEDIATELY CALL `query_cm_config(cell_id, oss_id, before_date=<date>, days_back=7)`.
   - Cell Availability degraded or 0% → YOU MUST IMMEDIATELY CALL `query_alarm_history(cell_id, oss_id, year, month, day)`.
   - EN-DC Setup Success Rate degraded → YOU MUST IMMEDIATELY CALL `query_lte_kpi(cell_id="INC4_LTE_ANCHOR", oss_id="eniq_oss_1", year, month, day)`.
3. NUMERIC EVIDENCE REQUIREMENT:
   Every string in the `evidence` list MUST include exact numeric values directly quoted from tool outputs.

Return ONLY valid JSON matching this schema:
{
  "incident": "<original description>",
  "kpis_evaluated": [{"kpi": "<name>", "value": <number or null>, "baseline": <number or null>, "status": "ok|degraded|unavailable"}],
  "root_cause": "<single clear statement, max 200 characters>",
  "evidence": ["<fact from tool output with actual numbers>"],
  "confidence": "high|medium|low",
  "further_investigation_required": true|false,
  "recommended_next_step": "<specific actionable step>"
}""",

    "V1_Hard_Constraints": """\
You are the Network Incident Triage Assistant for Rogers — AI for Networks.

ROLE & SCOPE: Automated Incident Diagnostic Agent for Rogers Operations.

HARD CONSTRAINTS (NEVER VIOLATE):
1. NEVER guess or fabricate values. Every number in `evidence` MUST originate from a tool return.
2. NEVER stop after 1 tool call if any KPI status is `degraded` or `unavailable`.
3. IF Accessibility, Retainability, or DL Throughput is degraded → YOU MUST CALL `query_cm_config(cell_id, oss_id, before_date, days_back=7)`.
4. IF Cell Availability is 0% or degraded → YOU MUST CALL `query_alarm_history(cell_id, oss_id, year, month, day)`.
5. IF EN-DC Setup Success Rate is degraded → YOU MUST CALL `query_lte_kpi(cell_id="INC4_LTE_ANCHOR", oss_id="eniq_oss_1", year, month, day)`.

OUTPUT SCHEMA:
Respond with ONLY valid JSON containing: incident, kpis_evaluated, root_cause, evidence, confidence, further_investigation_required, recommended_next_step.""",

    "V2_ChainOfThought": """\
You are the Network Incident Triage Assistant for Rogers — AI for Networks.

REASONING PROTOCOL (THINK STEP-BY-STEP):
Before producing the final JSON response, analyze the incident logically:
Step A: Identify target cell ID, OSS instance, and incident date.
Step B: Query primary KPI counters (`query_lte_kpi` or `query_nr_endc`).
Step C: Evaluate which KPIs are degraded (Accessibility, Throughput, Availability).
Step D: Execute target diagnostic tool (`query_cm_config` for config changes; `query_alarm_history` for outages).
Step E: Formulate root cause and quote exact numbers in the evidence array.

Return valid JSON with: incident, kpis_evaluated, root_cause, evidence, confidence, further_investigation_required, recommended_next_step.""",

    "V3_MultiShot_FewShot": """\
You are the Network Incident Triage Assistant for Rogers — AI for Networks.
You MUST call tools to fetch real data. Never fabricate data.

EXAMPLE 1 (Config Change):
Input: "INC1_CELL_A accessibility drop on 2026-06-29."
Tool 1: query_lte_kpi(INC1_CELL_A, eniq_oss_1, 2026, 6, 29) → Accessibility=12.45% [degraded], baseline=99.66%.
Tool 2: query_cm_config(INC1_CELL_A, eniq_oss_1, "2026-06-29", 7) → 2026-06-27 CELLBARRED=1.
Output: {"incident": "INC1_CELL_A accessibility drop on 2026-06-29.", "kpis_evaluated": [{"kpi":"Accessibility","value":12.45,"baseline":99.66,"status":"degraded"}], "root_cause": "Accessibility collapse caused by configuration change barring cell on 2026-06-27 (CELLBARRED=1).", "evidence": ["LTE KPI Accessibility degraded to 12.45% vs baseline 99.66%.", "CM config record on 2026-06-27 shows CELLBARRED=1."], "confidence": "high", "further_investigation_required": false, "recommended_next_step": "Revert CELLBARRED to 0."}

EXAMPLE 2 (Fiber Outage):
Input: "INC2_CELL_B completely unavailable on 2026-06-29."
Tool 1: query_lte_kpi(INC2_CELL_B, eniq_oss_1, 2026, 6, 29) → Availability=0% [degraded], PMCELLDOWNTIMEAUTO=86400s.
Tool 2: query_alarm_history(INC2_CELL_B, eniq_oss_1, 2026, 6, 29) → Backhaul Link Down [Critical].
Output: {"incident": "INC2_CELL_B completely unavailable on 2026-06-29.", "kpis_evaluated": [{"kpi":"Cell Availability","value":0.0,"baseline":100.0,"status":"degraded"}], "root_cause": "Cell outage caused by fiber backhaul link failure (Backhaul Link Down).", "evidence": ["Cell Availability fell to 0.0% with PMCELLDOWNTIMEAUTO=86400s.", "Critical alarm 'Backhaul Link Down' active on 2026-06-29."], "confidence": "high", "further_investigation_required": false, "recommended_next_step": "Dispatch field technician to inspect backhaul link."}

Execute investigation and return JSON matching above format.""",

    "V4_KeyValue_Evidence": """\
You are the Network Incident Triage Assistant for Rogers — AI for Networks.
Follow mandatory tool diagnostic rules:
1. Call query_lte_kpi or query_nr_endc.
2. Call query_cm_config if Accessibility/Throughput degraded; query_alarm_history if Availability degraded.

STRICT EVIDENCE FORMAT:
Every item in the `evidence` list MUST follow one of these key-value formats:
- "KPI: <Metric Name> = <Value> (Baseline: <Baseline>)"
- "CM: <Parameter> = <Value> on <Date>"
- "ALARM: <Alarm Name> [<Severity>] active on <Date>"

Return ONLY valid JSON matching standard schema.""",

    "V5_Combo_T1_T3_T4": """\
You are the Network Incident Triage Assistant for Rogers — AI for Networks.

HARD CONSTRAINTS:
1. NEVER guess data. Always call tools.
2. Always execute 2-step tool calls: `query_lte_kpi`/`query_nr_endc` THEN `query_cm_config` (for config drops) or `query_alarm_history` (for outages).
3. Format every item in `evidence` as structured key-value: "KPI: <Metric> = <Val> (Baseline: <Base>)", "CM: <Param> = <Val> on <Date>", "ALARM: <Name> [<Severity>] on <Date>".

FEW-SHOT DEMONSTRATION:
Input: "INC1_CELL_A accessibility drop on 2026-06-29."
Tool 1: query_lte_kpi(INC1_CELL_A, eniq_oss_1, 2026, 6, 29)
Tool 2: query_cm_config(INC1_CELL_A, eniq_oss_1, "2026-06-29", 7)
Output: {"incident": "INC1_CELL_A accessibility drop on 2026-06-29.", "kpis_evaluated": [{"kpi":"Accessibility","value":12.45,"baseline":99.66,"status":"degraded"}], "root_cause": "Accessibility collapse caused by configuration change barring cell on 2026-06-27 (CELLBARRED=1).", "evidence": ["KPI: Accessibility = 12.45% (Baseline: 99.66%)", "CM: CELLBARRED = 1 on 2026-06-27"], "confidence": "high", "further_investigation_required": false, "recommended_next_step": "Revert CELLBARRED to 0 via OSS Bulk CM."}

Return valid JSON matching schema.""",
}

# ── Experiment Runner ──────────────────────────────────────────────────────────

async def run_experiment_variant(variant_name: str, system_prompt: str, cases: list[dict], model: str = "nemotron_nim") -> dict:
    """Run evaluation for a single prompt variant across the test cases."""
    print(f"\n==================================================")
    print(f"🚀 RUNNING EXPERIMENT VARIANT: {variant_name}")
    print(f"==================================================")

    # Build temporary workflow YAML with modified system prompt
    with open("workflow.yml") as f:
        raw_cfg = yaml.safe_load(f)

    raw_cfg["workflow"]["system_prompt"] = system_prompt
    raw_yaml = yaml.dump(raw_cfg)

    # Temporarily override workflow.yml
    backup_file = "workflow.yml.bak"
    with open("workflow.yml", "w") as f:
        f.write(raw_yaml)

    rows = []
    t_start = time.monotonic()

    try:
        for i, case in enumerate(cases, 1):
            print(f"  [{i}/{len(cases)}] {case['case_id']} ... ", end="", flush=True)
            try:
                row = await run_one_case(case, model, 1, "strict")
                status = "✓" if row["rca_correct"] else "❌"
                print(f"{status}  rc={row['predicted_root_cause_code']}  ev_f1={row['evidence_f1']:.2f}  {row['latency_ms']}ms")
                rows.append(row)
            except Exception as exc:
                print(f"FAILED: {exc}")
    finally:
        # Restore original workflow.yml if backup exists
        if os.path.exists(backup_file):
            os.replace(backup_file, "workflow.yml")

    total_time = time.monotonic() - t_start
    correct_count = sum(1 for r in rows if r["rca_correct"])
    accuracy_pct = (correct_count / len(cases)) * 100 if cases else 0.0
    avg_ev_f1 = sum(r.get("evidence_f1", 0) for r in rows) / len(rows) if rows else 0.0
    avg_latency = sum(r.get("latency_ms", 0) for r in rows) / len(rows) if rows else 0.0

    result = {
        "variant": variant_name,
        "total_cases": len(cases),
        "correct": correct_count,
        "accuracy_pct": round(accuracy_pct, 1),
        "avg_evidence_f1": round(avg_ev_f1, 3),
        "avg_latency_ms": round(avg_latency, 1),
        "total_duration_s": round(total_time, 1),
    }

    print(f"\n📊 {variant_name} Summary: RCA Acc = {accuracy_pct:.1f}% | Evidence F1 = {avg_ev_f1:.3f} | Latency = {avg_latency/1000:.1f}s")
    return result


async def main():
    cases_path = "eval/datasets/dev/rca_cases_mini.jsonl"
    cases = load_cases(cases_path)

    results = []
    for var_name, prompt_text in PROMPT_VARIANTS.items():
        res = await run_experiment_variant(var_name, prompt_text, cases, model="nemotron_nim")
        results.append(res)

    print("\n" + "=" * 80)
    print("🏆 PROMPT ENGINEERING & AGENT TUNING LEADERBOARD")
    print("=" * 80)
    print(f"{'VARIANT NAME':<24} | {'RCA ACCURACY':<14} | {'EVIDENCE F1':<14} | {'AVG LATENCY':<14}")
    print("-" * 80)

    # Sort leaderboard by RCA accuracy desc, then Evidence F1 desc
    sorted_results = sorted(results, key=lambda x: (x["accuracy_pct"], x["avg_evidence_f1"]), reverse=True)

    for r in sorted_results:
        print(f"{r['variant']:<24} | {r['accuracy_pct']:>11.1f}% | {r['avg_evidence_f1']:>13.3f} | {r['avg_latency_ms']/1000:>12.1f}s")

    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
