# Network Incident Triage Agent — LLM Evaluation Harness

This directory contains the full evaluation framework for the Network Incident
Triage Agent. It is designed to compare open-source models (NVIDIA Nemotron Telco
via NIM) against frontier commercial models (Azure OpenAI) using identical
incidents, tools, data, and scoring — **the model is the only variable**.

---

## Directory Structure

```
eval/
├── README.md                    ← this file
├── schema/
│   ├── rca_output_schema.json   ← JSON Schema for agent structured output
│   ├── case_schema.json         ← JSON Schema for test case format
│   └── root_cause_codes.py      ← canonical RCA taxonomy constants
├── datasets/
│   ├── dev/
│   │   └── rca_cases.jsonl      ← 25 development cases (5 × 5 families)
│   └── test/
│       └── rca_cases.jsonl      ← 20 held-out test cases (4 × 5 families)
├── scorers/
│   ├── __init__.py
│   ├── root_cause.py            ← RootCauseAccuracyEvaluator
│   ├── evidence.py              ← EvidenceGroundingEvaluator
│   ├── schema_grounding.py      ← SchemaHallucinationEvaluator
│   ├── tool_calls.py            ← ToolCallEvaluator
│   ├── kpi_accuracy.py          ← KPIAccuracyEvaluator
│   ├── calibration.py           ← CalibrationCollector
│   └── abstention.py            ← AbstentionEvaluator
├── configs/
│   ├── models/
│   │   ├── nemotron_nim.yml     ← Nemotron Telco (self-hosted NIM)
│   │   └── azure_frontier.yml  ← Azure OpenAI frontier model
│   ├── eval_strict.yml          ← Strict apples-to-apples eval config
│   └── eval_optimized.yml       ← Best deployable config eval
├── runner/
│   ├── __init__.py
│   └── run_agent_eval.py        ← Full agent evaluation runner
├── analysis/
│   ├── __init__.py
│   ├── aggregate_results.py     ← Aggregate metrics + comparison table
│   └── error_analysis.py        ← E01–E24 error taxonomy analysis
└── results/
    └── .gitkeep                 ← Result JSONL files written here
```

The `eval/scenarios.py`, `eval/scorers.py`, and `eval/run_eval.py` files are the
original basic harness and are kept unchanged.

---

## What the Eval Harness Does

1. **Loads test cases** from a JSONL file (dev or held-out test set).
2. **Runs the agent** for each case using `main.py`'s `run_with_fallback()`.
3. **Captures** latency, token counts, tool trajectory, and structured RCA output.
4. **Scores** each run with deterministic evaluators:
   - Root cause accuracy (exact + acceptable partial credit)
   - Evidence grounding (precision, recall, F1)
   - Schema hallucination (valid field rate, hallucinated field names)
   - Tool call coverage (required recall, precision, F1)
   - Abstention accuracy (correct/missed/false abstention)
5. **Writes one row per run** to `eval/results/run_{model}_{timestamp}.jsonl`.
6. **Prints a summary** table at the end of each run.

---

## Running the Development Eval

Use the dev set for debugging and scorer validation. Results from dev cases must
not be used to draw final model conclusions.

```bash
# Nemotron NIM (default model)
.venv/bin/python eval/runner/run_agent_eval.py \
    --model nemotron_nim \
    --cases eval/datasets/dev/rca_cases.jsonl \
    --reps 1

# Azure OpenAI frontier model
.venv/bin/python eval/runner/run_agent_eval.py \
    --model azure_frontier \
    --cases eval/datasets/dev/rca_cases.jsonl \
    --reps 1
```

---

## Running the Strict Held-Out Eval

The held-out test set must only be run once all settings are frozen. Use 3
repetitions for stability analysis.

```bash
# Strict mode, 3 repetitions
.venv/bin/python eval/runner/run_agent_eval.py \
    --model nemotron_nim \
    --cases eval/datasets/test/rca_cases.jsonl \
    --reps 3 \
    --mode strict

.venv/bin/python eval/runner/run_agent_eval.py \
    --model azure_frontier \
    --cases eval/datasets/test/rca_cases.jsonl \
    --reps 3 \
    --mode strict
```

---

## Comparing Models

After both models have produced results, run the analysis scripts:

```bash
# Comparison table
.venv/bin/python eval/analysis/aggregate_results.py eval/results/

# Error taxonomy breakdown
.venv/bin/python eval/analysis/error_analysis.py eval/results/
```

Example output:

```
─────────────────────────────────────────────────────────────────────────────
Model                  RCA_Acc  Evidence_F1   Hall_Rate  Abstention_Acc   p50_lat   p95_lat  Cost_Est
─────────────────────────────────────────────────────────────────────────────
nemotron_nim            XX.X%        X.XXX        X.X%          XX.X%     XXXXms    XXXXms   $X.XXXX
azure_frontier          XX.X%        X.XXX        X.X%          XX.X%     XXXXms    XXXXms   $X.XXXX
```

---

## Adding New Models

1. Add a new config file `eval/configs/models/{model_id}.yml`:
   ```yaml
   model_id: my_new_model
   category: open_source
   display_name: "My New Model"
   llm_name: my_new_model       # must match a key in workflow.yml llms section
   temperature: 0.0
   max_tokens: 4096
   max_agent_steps: 12
   ```

2. Add the model to `workflow.yml` under the `llms:` key with the correct
   provider config (`_type: openai` or `_type: azure_openai`).

3. Set the required environment variables in `.env`.

4. Run the eval:
   ```bash
   .venv/bin/python eval/runner/run_agent_eval.py \
       --model my_new_model \
       --cases eval/datasets/dev/rca_cases.jsonl \
       --reps 1
   ```

The model is the only variable — no other changes are needed.

---

## Dataset Format

Each case is a JSON object on a single line (JSONL). Fields:

```json
{
  "case_id": "F1_DEV_001",
  "family": "config_change",
  "difficulty": "easy",
  "incident": {
    "target_cell": "INC1_CELL_A",
    "incident_time": "2026-06-29T08:00:00",
    "description": "..."
  },
  "ground_truth": {
    "root_cause_code": "CELL_BARRED_CHANGE",
    "acceptable_root_cause_codes": ["CELL_BARRED_CHANGE", "ADMIN_STATE_CHANGE"],
    "required_tools": ["query_lte_kpi", "query_cm_config"],
    "optional_tools": ["query_alarm_history", "query_neighbour_topology", "query_kpi_trend", "query_similar_incidents", "query_telecom_knowledge"],
    "required_evidence": [
      {"source": "CM", "table": "cm_config_sample", "field": "CELLBARRED"},
      {"source": "KPI", "metric": "accessibility"}
    ],
    "needs_further_investigation": false
  }
}
```

Families: `config_change`, `outage`, `interference`, `endc`, `ambiguous`  
Difficulty: `easy`, `medium`, `hard`, `ambiguous`  
Case ID format: `F{1-5}_{DEV|TEST}_{001-NNN}`

---

## Scoring Methodology

### Root Cause Accuracy
- **1.0** — predicted code exactly matches `root_cause_code`
- **0.5** — predicted code is in `acceptable_root_cause_codes`
- **0.0** — neither

### Evidence Grounding
- **Precision** = evidence items matching required source/field / all predicted items
- **Recall** = required evidence items found / all required items
- **F1** = harmonic mean
- **Unsupported rate** = predicted items with no match / all predicted

Matching: source domain match (KPI/CM/Alarm/NR) AND field/counter name appears
in observation text.

### Schema Hallucination
Extracts capitalised counter names (PM\*, cm\*) from evidence observations and
root_cause text, then checks against the known column sets from the actual CSVs.
Reports valid rate and a list of hallucinated field names.

### Tool Calls
- **Required tool recall** = required tools called / all required tools
- **Tool precision** = relevant calls / all calls (required + optional)
- **Tool F1** = harmonic mean
- **Unnecessary call rate** = calls not in required or optional / all calls

### Abstention
- `correct_abstention` — both predicted and GT say investigation needed
- `false_abstention`   — agent said needed, GT says not
- `missed_abstention`  — agent said not needed, GT says needed (most dangerous)

### Calibration (for aggregate analysis)
- **Brier Score** — mean squared error between confidence and outcome
- **ECE** — expected calibration error across confidence buckets
- **High-confidence error rate** — wrong RCAs with confidence ≥ 0.8

---

## Eval Plan Reference

The full evaluation plan is at:
`instructions/network_rca_llm_evaluation_plan.md`

Key sections:
- Section 4: Experimental Principles
- Section 8-10: Dataset Design and Difficulty Levels
- Section 11: Case Format
- Section 13: Output Schema
- Section 14: Metrics
- Section 17: Strict vs Optimized Modes
- Section 20: Error Taxonomy
- Section 35: RCA Taxonomy

---

## Notes

- All scoring is **deterministic** — no LLM judge required for the core metrics.
- The `eval/results/` directory is in `.gitignore` to avoid committing large result
  files. Add them to your artifact storage separately.
- Token cost estimates use defaults of $0.005/1k input and $0.015/1k output. Set
  `COST_PER_1K_INPUT` and `COST_PER_1K_OUTPUT` env vars to override.
- The `.venv/bin/python` interpreter is used throughout to ensure the correct
  virtual environment.
