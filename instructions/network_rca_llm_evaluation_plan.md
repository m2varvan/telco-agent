# Network Incident Triage Assistant
## Frontier vs Open-Source LLM Evaluation Plan

**Project:** Rogers AI for Networks  
**System:** Network Incident Triage Assistant  
**Primary open-source model:** NVIDIA Open Nemotron Telco  
**Framework:** NVIDIA NeMo Agent Toolkit  
**Data:** Synthetic telecom data using production-faithful Ericsson ENIQ schemas  
**Document purpose:** Implementation plan for evaluating open-source LLMs against frontier commercial models on telecom/network incident triage  
**Version:** Eval Plan v1.0  
**Date:** August 2026  

---

# 1. Executive Summary

The objective of this evaluation is to determine whether an open-source model, with NVIDIA Open Nemotron Telco as the primary candidate, can provide sufficiently strong network incident triage performance to justify its operational and economic advantages over frontier commercial models.

The evaluation must answer two separate questions:

1. **Capability:** How accurately and reliably does each model perform telecom-specific reasoning tasks and end-to-end Root Cause Analysis (RCA)?
2. **Economics:** If an open-source model is slightly weaker or stronger, is the quality difference acceptable relative to inference cost, infrastructure cost, latency, privacy, control, and self-hosting requirements?

The benchmark will therefore evaluate models at two levels:

- **Model capability benchmark:** isolated telecom reasoning, schema understanding, KPI calculation, joins, SQL generation, and causal analysis.
- **Full agent benchmark:** the complete NeMo Agent Toolkit incident triage workflow, including tool selection, tool arguments, evidence collection, orchestration, RCA generation, confidence, latency, and cost.

The fundamental experimental rule is:

> **For the strict comparison, the model is the only variable.**

All candidate models receive the same incidents, tools, tool descriptions, synthetic ENIQ data, knowledge base, prompts, output schema, maximum agent steps, and evaluation criteria.

The final decision will not be based on one composite score alone. Results will be reported across quality, reliability, efficiency, and economics, with **quality acting as the deployment gate** and cost/operational factors determining the preferred model among models that pass the quality threshold.

---

# 2. Evaluation Questions

The evaluation should answer the following questions.

## 2.1 Primary Questions

1. Can Nemotron Telco identify the correct root cause of synthetic network incidents as reliably as frontier models?
2. Does telecom specialization improve understanding of Ericsson/ENIQ terminology and KPI counters?
3. How well does each model select and invoke the correct diagnostic tools?
4. How often does each model hallucinate tables, fields, counters, alarms, or evidence?
5. Does each model correctly correlate evidence across KPI, CM/configuration, alarm/availability, and knowledge sources?
6. How well does each model distinguish correlation from likely causation?
7. Does the model know when available evidence is insufficient?
8. How stable are results across repeated executions of the same incident?
9. What is the latency, token usage, model-call count, tool-call count, and monetary cost per incident?
10. For self-hosted models, what GPU capacity and infrastructure are required?
11. What is the **cost per correct RCA** for each model?
12. At what incident difficulty does the open-source model begin to meaningfully fall behind frontier models?

## 2.2 Secondary Questions

1. Does model performance vary significantly by incident family?
2. Does performance degrade as distractor evidence is added?
3. Does performance degrade with longer evidence histories?
4. Does performance change when information is incomplete?
5. Are incorrect answers accompanied by excessive confidence?
6. Are expensive models more efficient in the number of tool calls or investigation steps?
7. Is a smaller open-source model sufficient for easier task tiers?
8. Can a routing strategy eventually send easy incidents to a cheaper model and difficult incidents to a stronger model?

---

# 3. Scope

## 3.1 In Scope

The evaluation covers:

- NVIDIA Open Nemotron Telco
- At least one additional open-source model, if practical
- At least one frontier commercial model
- Preferably two frontier models if API access and budget allow
- Identical synthetic ENIQ-based datasets
- Existing NeMo Agent Toolkit orchestration
- KPI Agent
- CM / Configuration Agent
- Alarm / Availability Agent
- Knowledge / RAG Agent
- Orchestrator
- SQL generation and execution
- Root Cause Analysis
- Tool trajectory evaluation
- Deterministic scoring
- Semantic scoring where deterministic scoring is not possible
- Latency and usage profiling
- Open-source infrastructure estimates
- Cost comparison
- Statistical comparison of model results

## 3.2 Out of Scope for v1

The following are explicitly excluded from the first evaluation version:

- Fine-tuning
- Live ENIQ access
- Live OSS integration
- Live Splunk integration
- Production incident tickets
- Production human-in-the-loop workflows
- Full network-wide incident taxonomy
- Production security certification
- Production capacity planning
- Automated remediation
- Model routing in production
- Benchmarking generic academic LLM tasks unrelated to network operations

---

# 4. Experimental Principles

## 4.1 Freeze the Non-Model Components

For the strict benchmark, keep the following fixed:

- System prompt
- Agent instructions
- Tool descriptions
- Tool schemas
- Tool implementations
- Tool return formats
- Synthetic dataset version
- RAG corpus
- RAG retrieval settings
- Incident prompts
- Maximum agent iterations
- Maximum tool calls
- Output JSON schema
- Timeout policy
- Evaluation code
- Scoring thresholds
- Temperature and sampling settings where supported
- Maximum output tokens
- Retry policy

Only the model/provider configuration changes.

This prevents an unfair comparison where one model receives a better prompt, more context, additional tools, or extra retries.

## 4.2 Evaluate the System, Not Writing Style

The benchmark must prioritize whether the system:

- found the right evidence,
- used valid data,
- invoked the right tools,
- computed the right metrics,
- identified the correct cause,
- handled uncertainty correctly.

A polished explanation with an incorrect RCA should still fail.

## 4.3 Prefer Deterministic Scoring

Whenever ground truth is available, use code rather than an LLM judge.

Examples suitable for deterministic scoring:

- correct root cause code,
- correct table,
- correct field,
- correct counter,
- numerical KPI value,
- SQL execution success,
- SQL result set,
- expected tool,
- tool arguments,
- evidence source,
- timestamp ordering,
- presence of fabricated schema fields.

Use LLM-based evaluation only for genuinely semantic properties such as causal explanation quality.

## 4.4 Keep Test Data Held Out

Prompt engineering and agent development must use only a development dataset.

The final test dataset must not be inspected or manually tuned against before the benchmark is frozen.

## 4.5 Use Paired Evaluation

Every candidate model must execute the exact same test cases.

This allows direct per-case comparison:

```text
INC_TEST_001
    ├── Nemotron Telco
    ├── Open Model B
    ├── Frontier Model A
    └── Frontier Model B
```

The same scorers then evaluate every output.

---

# 5. Evaluation Architecture

```text
                    VERSIONED EVAL DATASET
                         /           \
                        /             \
               Model Capability      Full RCA Cases
                    Tasks                |
                     |                   |
                     v                   v
               +--------------------------------+
               |        Evaluation Runner       |
               +--------------------------------+
                   |        |        |        |
                   v        v        v        v
              Nemotron   Open-B   Frontier-A Frontier-B
                   \        |        |       /
                    \       |        |      /
                     +----------------------+
                     | SAME AGENT + TOOLS   |
                     | SAME DATA + PROMPTS  |
                     +----------------------+
                               |
                               v
                   Structured Result + Trace
                               |
              +----------------+----------------+
              |                |                |
              v                v                v
       Deterministic      Trajectory       Semantic
          Scorers           Scorer          Judge
              |                |                |
              +----------------+----------------+
                               |
                               v
                       RESULTS DATASET
                               |
                  +------------+------------+
                  |            |            |
                  v            v            v
                Quality     Reliability   Economics
```

---

# 6. Candidate Model Matrix

Create a configuration registry rather than hardcoding model names.

Example:

| Model ID | Category | Provider/Hosting | Purpose |
|---|---|---|---|
| `nemotron_telco` | Open | Self-hosted / NVIDIA-compatible endpoint | Primary open-source candidate |
| `open_b` | Open | Self-hosted/API | General open-model comparison |
| `frontier_a` | Frontier | Commercial API | Accuracy ceiling |
| `frontier_b` | Frontier | Commercial API | Second frontier reference |

Record exact model versions and endpoint configuration before the final run.

For every run store:

- model name,
- model version,
- provider,
- quantization if applicable,
- serving engine,
- temperature,
- top-p,
- max tokens,
- reasoning configuration if exposed,
- GPU type for self-hosted models,
- date/time of run.

Do not combine results from different model revisions under one model label.

---

# 7. Two Benchmark Layers

# 7.1 Benchmark A: Isolated Model Capability

This benchmark tests the LLM itself without relying on the complete multi-agent workflow.

It should preserve the ENIQ terminology used by the prototype.

## T1. Schema Understanding

Examples:

- Which table contains LTE cell configuration?
- Which table contains NR-DU counters?
- Which field identifies the LTE cell?
- Which counters are used for EN-DC setup success?
- Which fields contain coordinates?
- Which field represents administrative state?
- Which data domain should be queried for a recent parameter change?

### Scoring

- Exact table match
- Exact field match
- Exact counter-set match
- No hallucinated fields

### Purpose

Determines whether the model understands the telecom schema before agent/tool orchestration is involved.

---

## T2. KPI Calculation

Examples:

- Calculate EN-DC setup success.
- Calculate cell availability.
- Calculate accessibility from supplied component rates.
- Compare an incident-period KPI with a seven-day baseline.
- Determine percentage degradation.

### Scoring

Use numeric tolerance.

Example:

```text
abs(predicted - expected) <= tolerance
```

Recommended:

- percentage KPIs: absolute error <= 0.1 percentage point where appropriate,
- ratios: define KPI-specific tolerance,
- exact integer counters: exact match.

Also record:

- formula correctness,
- correct numerator,
- correct denominator,
- correct filtering window,
- unit correctness.

---

## T3. Multi-Table Reasoning / Join Planning

Examples:

- Find coordinates for the ten busiest cells.
- Join inventory and KPI data to identify impacted sites.
- Determine which neighbouring cells degraded after an event.
- Link a configuration change to the correct cell hierarchy.

### Scoring

- required tables selected,
- correct join keys,
- correct filter predicates,
- expected result rows,
- no invalid joins,
- no nonexistent fields.

---

## T4. RCA Reasoning

Provide an incident plus already-retrieved evidence, without allowing autonomous tool calls.

This isolates **reasoning quality** from tool selection.

Expected output:

- root cause code,
- evidence,
- confidence,
- further-investigation flag.

This is useful because:

```text
Poor T4 + good tools = reasoning problem
Good T4 + poor full-agent result = orchestration/tool-use problem
```

---

## T5. SQL Generation

Examples:

- Top 10 cells by average connected users.
- Cells below a specified EN-DC success rate.
- Config changes within two hours before an incident.
- Cells with availability degradation during an alarm window.

### Scoring

Do not grade SQL primarily by string equality.

Execute the SQL against the frozen synthetic database.

Score:

1. parses successfully,
2. executes successfully,
3. uses allowed schema,
4. result set matches expected output,
5. aggregation is correct,
6. filters are correct,
7. no hallucinated schema objects.

Recommended main metric:

> **Execution Correctness = expected result set obtained**

---

# 7.2 Benchmark B: Full Agent RCA

This benchmark evaluates the actual Network Incident Triage Assistant.

The orchestrator receives only the incident description.

It must autonomously:

1. understand the incident,
2. determine relevant diagnostic domains,
3. select tools,
4. provide correct tool arguments,
5. retrieve evidence,
6. re-query when needed,
7. correlate evidence,
8. identify potential root cause,
9. produce an evidence-based RCA,
10. express confidence,
11. indicate whether further investigation is required.

This is the primary deployment-oriented benchmark.

---

# 8. Dataset Design

## 8.1 Scenario Families

Keep the four current incident families and add a fifth class specifically for uncertainty.

### Family F1: KPI Degradation After Configuration Change

Ground-truth examples:

- administrative state change,
- cell barring,
- bandwidth change,
- power configuration change,
- frequency-related configuration change.

Expected correlation:

```text
configuration change
       ↓
timestamp precedes degradation
       ↓
relevant KPI changes
       ↓
RCA
```

Include unrelated configuration changes as distractors.

---

### Family F2: Cell/Site Outage With Alarm History

Ground-truth examples:

- backhaul link down,
- power failure,
- cell outage event.

Expected evidence:

- alarm window,
- availability degradation,
- downtime counters,
- affected site/cell hierarchy.

Include irrelevant alarms so that the model cannot simply choose the most recent alarm.

---

### Family F3: Neighbour Performance Degradation

Ground-truth examples:

- adjacent-cell interference,
- regional degradation,
- neighbour-specific load/performance problem.

Expected evidence:

- affected neighbouring elements,
- spatial relationship,
- no relevant local configuration change,
- correlated KPI degradation.

This family is particularly useful for testing whether the model over-focuses on the initially named cell.

---

### Family F4: EN-DC Accessibility Degradation

Ground truth:

- increased NR random-access failures or related EN-DC failure evidence.

Expected evidence:

- `pmEndcSetupUeSucc`,
- `pmEndcSetupUeAtt`,
- `pmEndcSetupFailNrRa`,
- LTE anchor remains healthy,
- NR-specific setup performance degrades.

---

### Family F5: Ambiguous / Insufficient / No Causal Evidence

This family is mandatory.

Examples:

- KPI degradation with no explanatory alarm or config change,
- configuration change exists but occurs after the incident,
- alarm exists but affects another cell,
- several plausible causes with insufficient distinguishing evidence,
- metrics partially missing,
- correlation exists but causal evidence is weak,
- degradation is within normal variation.

Correct output should often be:

```json
{
  "root_cause_code": "UNDETERMINED",
  "needs_further_investigation": true
}
```

This tests whether the model can resist inventing an RCA.

---

# 9. Dataset Size

Recommended v1 target:

```text
5 scenario families
× 25 cases per family
= 125 total cases
```

Split:

```text
Development:
5 cases × 5 families = 25

Held-out Test:
20 cases × 5 families = 100
```

The development set is used for:

- debugging,
- scorer validation,
- prompt improvement,
- output-schema validation,
- model adapter testing.

The 100-case test set is frozen before the final benchmark.

If schedule permits, increase the held-out set later rather than reducing rigor on scoring.

---

# 10. Difficulty Levels

Each family should contain multiple difficulty levels.

## Easy

Characteristics:

- one clear cause,
- strong KPI signal,
- little/no distractor evidence,
- straightforward time correlation.

## Medium

Characteristics:

- several events,
- multiple config changes,
- requires correlation across at least two sources,
- moderate distractors.

## Hard

Characteristics:

- multiple affected network elements,
- competing hypotheses,
- several alarms/config changes,
- subtle timing,
- evidence across three or more sources,
- requires re-querying.

## Ambiguous

Characteristics:

- insufficient evidence,
- contradictory evidence,
- missing data,
- no safe causal conclusion.

Recommended held-out distribution per family:

```text
Easy       5
Medium     7
Hard       5
Ambiguous  3
```

Adjust F5 as needed because that family is intentionally dominated by uncertainty cases.

---

# 11. Synthetic Case Generation

Every case must have machine-readable ground truth.

Recommended case format:

```json
{
  "case_id": "F1_TEST_014",
  "family": "config_change",
  "difficulty": "medium",
  "incident": {
    "target_cell": "CELL_123",
    "incident_time": "2026-07-14T14:00:00",
    "description": "Accessibility degradation detected on CELL_123"
  },
  "ground_truth": {
    "root_cause_code": "CELL_BARRED_CHANGE",
    "acceptable_root_cause_codes": [
      "CELL_BARRED_CHANGE"
    ],
    "required_tools": [
      "kpi_agent",
      "cm_agent"
    ],
    "optional_tools": [
      "knowledge_agent"
    ],
    "forbidden_or_irrelevant_tools": [],
    "required_evidence": [
      {
        "source": "CM",
        "table": "dc_e_bulk_cm_eutrancellfdd_raw",
        "field": "CELLBARRED"
      },
      {
        "source": "KPI",
        "metric": "accessibility"
      }
    ],
    "expected_temporal_relation": "config_before_kpi_drop",
    "needs_further_investigation": false
  }
}
```

Keep grader-only ground truth outside the prompt sent to the model.

---

# 12. Dataset Quality Checks

Before running model evals, validate every test case automatically.

## Required checks

- referenced table exists,
- referenced field exists,
- referenced counter exists,
- expected SQL can execute,
- expected KPI can be calculated,
- timestamps are internally consistent,
- root cause is actually injected,
- distractors do not accidentally provide a second equally valid root cause unless the case is intentionally ambiguous,
- tool queries can retrieve required evidence,
- case is reproducible from a seed.

Each generated case should record:

```text
generator_version
random_seed
dataset_version
schema_version
```

This makes failures reproducible.

---

# 13. Required Agent Output Schema

Force structured output.

Recommended structure:

```json
{
  "incident_id": "F1_TEST_014",
  "root_cause_code": "CELL_BARRED_CHANGE",
  "root_cause": "Cell barring configuration change",
  "alternative_hypotheses": [
    {
      "cause": "Backhaul issue",
      "probability": 0.05
    }
  ],
  "evidence": [
    {
      "source": "CM",
      "table": "dc_e_bulk_cm_eutrancellfdd_raw",
      "field": "CELLBARRED",
      "observation": "Changed from 0 to 1 before degradation"
    }
  ],
  "confidence": 0.92,
  "needs_further_investigation": false,
  "recommended_next_step": "Validate whether the cell barring change was intended."
}
```

The structured schema makes scoring reproducible and reduces reliance on semantic judges.

---

# 14. Evaluation Metrics

# 14.1 Root Cause Metrics

## Root Cause Accuracy

```text
correct RCA cases / total cases
```

Report:

- overall,
- by family,
- by difficulty,
- by model.

## Top-k RCA Accuracy

If alternative hypotheses are supported:

```text
ground truth appears in top k hypotheses / total cases
```

Recommended:

- Top-1
- Top-2
- Top-3 if models return enough candidates

## Root Cause Macro Accuracy

Compute accuracy independently for each incident family and average the family accuracies.

This prevents one easy family from dominating the overall result.

---

# 14.2 Evidence Metrics

For each case define a ground-truth evidence set.

## Evidence Precision

```text
correct evidence items cited
-----------------------------
all evidence items cited
```

## Evidence Recall

```text
required evidence items found
-----------------------------
all required evidence items
```

## Evidence F1

```text
2 × precision × recall
----------------------
precision + recall
```

## Unsupported Evidence Rate

```text
evidence claims not supported by retrieved data
-----------------------------------------------
all evidence claims
```

This is a particularly important enterprise safety metric.

---

# 14.3 Schema Grounding Metrics

## Valid Schema Reference Rate

```text
valid table/field/counter references
------------------------------------
all schema references
```

## Hallucinated Field Rate

```text
nonexistent fields/counters/tables
----------------------------------
all schema references
```

Break this into:

- hallucinated table rate,
- hallucinated field rate,
- hallucinated counter rate.

---

# 14.4 Tool-Use Metrics

The full-agent benchmark must preserve the tool trajectory.

For each case maintain:

```text
required_tools
optional_tools
irrelevant_tools
expected_argument_constraints
```

## Required Tool Recall

```text
required tools called
---------------------
required tools
```

## Tool Precision

```text
relevant tool calls
-------------------
all tool calls
```

## Tool F1

Harmonic mean of tool precision and required-tool recall.

## Tool Argument Accuracy

Validate arguments such as:

- target cell,
- site,
- KPI,
- date/time,
- time window,
- table/domain,
- requested counter,
- neighbour scope.

Possible scoring:

```text
correct required arguments
--------------------------
all required arguments
```

## Unnecessary Tool Call Rate

```text
irrelevant tool calls
---------------------
all tool calls
```

## Repeated Call Waste

Measure repeated identical or near-identical calls that do not add evidence.

---

# 14.5 Investigation Trajectory Metrics

Final correctness alone is insufficient.

Store the sequence:

```text
Incident
→ KPI query
→ CM query
→ Alarm query
→ evidence correlation
→ RCA
```

Score:

### Valid Investigation Path

Did the model inspect the minimum evidence required to justify its conclusion?

### Dependency Order Correctness

Examples:

- data is retrieved before conclusions based on that data,
- the correct cell is resolved before querying cell-specific metrics,
- neighbour evidence is retrieved before making a neighbour-impact claim.

### Premature Conclusion Rate

Did the model reach a root cause before checking required contradictory evidence?

### Recovery Rate

When an initial hypothesis was unsupported, did the model correctly change direction?

---

# 14.6 KPI Accuracy Metrics

For numerical tasks:

## Absolute Error

```text
| predicted - expected |
```

## Relative Error

```text
| predicted - expected |
------------------------
| expected |
```

Use KPI-specific tolerances.

Report pass/fail plus continuous error.

---

# 14.7 SQL Metrics

## SQL Parse Success

Did generated SQL parse?

## SQL Execution Success

Did it run on DuckDB/test database?

## Result Correctness

Compare result rows/sets to expected output.

## Aggregation Correctness

Check whether required aggregation/grouping is correct.

## Schema Validity

Check whether every referenced relation and column exists.

## SQL Efficiency

Optional v1 metric:

- excessive scans,
- redundant joins,
- unnecessary queries.

Correctness matters more than optimization for the first version.

---

# 14.8 Causal Reasoning Metrics

Some causal-quality scoring may require rubric-based evaluation.

Score whether the explanation:

1. identifies the relevant temporal relationship,
2. distinguishes correlation from causation,
3. uses evidence that actually supports the stated root cause,
4. considers contradictory evidence,
5. avoids unsupported claims.

Suggested rubric:

| Score | Meaning |
|---|---|
| 0 | Causal explanation is unsupported or contradictory |
| 1 | Partially plausible but important evidence is missing |
| 2 | Correct, evidence-linked causal explanation |

Keep this separate from deterministic root-cause accuracy.

---

# 14.9 Uncertainty and Calibration Metrics

Confidence must be evaluated rather than accepted at face value.

## Brier Score

For RCA correctness:

```text
Brier = mean((confidence - correctness)^2)
```

where:

```text
correctness = 1 if RCA correct
correctness = 0 otherwise
```

Lower is better.

## Expected Calibration Error

Bucket predictions by confidence and compare:

```text
average confidence vs actual accuracy
```

Example buckets:

```text
0.0–0.2
0.2–0.4
0.4–0.6
0.6–0.8
0.8–1.0
```

## High-Confidence Error Rate

Define a threshold, for example:

```text
confidence >= 0.80
```

Then measure:

```text
incorrect high-confidence RCAs
------------------------------
all high-confidence RCAs
```

## Abstention Accuracy

For ambiguous cases, evaluate whether:

```text
needs_further_investigation = true
```

when ground truth says the evidence is insufficient.

## False Abstention Rate

Measure cases where the model refuses to conclude despite sufficient evidence.

---

# 14.10 Stability Metrics

Run every held-out incident multiple times.

Recommended:

```text
3 repetitions per model per case
```

For 100 test incidents and 4 candidate models:

```text
100 × 4 × 3 = 1,200 full-agent executions
```

Report:

## RCA Consistency

Percentage of cases where all repetitions return the same root cause.

## Success Consistency

Percentage of cases where all runs agree on correctness.

## Tool Trajectory Variance

Variation in number and type of tool calls across repeated runs.

## Confidence Variance

Variance in confidence across runs for the same case.

---

# 14.11 Latency Metrics

Capture:

- end-to-end latency,
- model latency,
- tool execution latency,
- retrieval latency if practical.

Report:

```text
mean
median
p50
p90
p95
p99 if sample size supports it
```

p95 is particularly important for operational usability.

---

# 14.12 Usage Metrics

Capture per run:

- prompt tokens,
- completion tokens,
- total tokens,
- number of LLM calls,
- number of tool calls,
- number of RAG calls,
- number of agent iterations.

Report averages and distributions.

---

# 14.13 Cost Metrics

For commercial APIs:

```text
input token cost
+ output token cost
+ other model/provider charges
```

For self-hosted models:

Estimate:

```text
GPU hourly cost
× inference runtime
+ serving overhead allocation
```

Later add:

- idle capacity,
- utilization,
- storage,
- networking,
- operational overhead.

## Cost per Incident

```text
total inference cost
--------------------
number of incidents
```

## Cost per Correct RCA

Primary economic metric:

```text
total evaluation inference cost
--------------------------------
number of correct RCA outcomes
```

## Cost per Successful Hard RCA

Optional but valuable:

```text
cost
----
correct hard incidents
```

This prevents cheap success on easy cases from hiding weakness on difficult incidents.

---

# 14.14 Self-Hosting Metrics

For open-source models capture or estimate:

- GPU model/type,
- GPU count,
- VRAM used,
- model weight footprint,
- quantization,
- batch size,
- throughput,
- tokens/second,
- concurrent requests,
- GPU utilization,
- memory utilization,
- cold-start/load time,
- incidents/hour,
- estimated utilization needed for economic break-even.

These metrics feed the research/business comparison rather than the core accuracy score.

---

# 15. Composite Reporting

Do not hide the benchmark behind one overall score.

Use separate scorecards.

## 15.1 Quality Scorecard

- RCA Accuracy
- Macro RCA Accuracy
- Evidence F1
- Schema Grounding
- Hallucination Rate
- SQL Result Correctness
- KPI Accuracy

## 15.2 Agent Reliability Scorecard

- Tool Precision
- Tool Recall
- Argument Accuracy
- Trajectory Validity
- Unnecessary Calls
- Stability
- High-Confidence Error Rate
- Abstention Accuracy

## 15.3 Efficiency Scorecard

- p50 latency
- p95 latency
- total tokens
- LLM calls
- tool calls
- cost/incident
- cost/correct RCA

## 15.4 Infrastructure Scorecard

- GPU requirement
- VRAM
- throughput
- projected monthly cost
- operational complexity
- data-control/privacy benefit

---

# 16. Deployment Gate

Quality should be treated as a gate before economics.

Recommended initial gate based on the project PRD:

```text
RCA Accuracy                  >= 80%
Evidence Grounding            >= 80%
```

Add stricter operational gates once baseline results exist.

Possible additional gates:

```text
Hallucinated schema rate      <= 5%
High-confidence wrong RCA     <= agreed threshold
Ambiguous-case abstention     >= agreed threshold
Tool argument accuracy        >= 90%
```

Do not lock arbitrary thresholds for metrics that have no baseline yet. First run the development benchmark, inspect distributions, then freeze justified final thresholds before the held-out test.

---

# 17. Strict vs Optimized Evaluation Modes

Run two separate experiments.

# 17.1 Mode A: Strict Apples-to-Apples

Purpose:

> Measure interchangeability when only the underlying model changes.

Freeze:

- prompt,
- tools,
- tool descriptions,
- RAG,
- max steps,
- temperature,
- output schema,
- context supplied,
- retry policy.

This is the scientifically clean comparison.

---

# 17.2 Mode B: Best Deployable Configuration

Purpose:

> Measure the strongest realistic configuration Rogers could deploy for each model.

Allow model-specific tuning on the development set:

- prompt adjustments,
- reasoning configuration,
- temperature/top-p,
- max tokens,
- RAG/context strategy,
- tool descriptions if necessary,
- model-specific serving optimizations.

Once tuned:

1. freeze each model's configuration,
2. run the untouched held-out test set,
3. report results separately from strict-mode results.

Never mix strict and optimized results in the same comparison column without labeling them.

---

# 18. Repetition and Sampling Policy

Recommended full-agent evaluation:

```text
100 held-out cases
× 3 repetitions
× number of models
```

Recommended isolated T1–T5 evaluation:

At least:

```text
50–100 items per task tier
```

Where possible derive tasks from the same versioned schema but prevent direct overlap with development questions.

Use a fixed random-seed policy for dataset generation.

If deterministic decoding is supported and operationally realistic, evaluate both:

- deterministic/low-randomness mode,
- production-intended mode.

The primary score should use the intended production configuration.

---

# 19. Statistical Analysis

Raw percentage differences are not enough.

For paired model comparisons use the same test cases.

## 19.1 Confidence Intervals

Use paired bootstrap resampling to estimate 95% confidence intervals for:

- RCA accuracy delta,
- Evidence F1 delta,
- tool accuracy delta,
- cost/correct-RCA delta if appropriate.

Example output:

```text
Nemotron vs Frontier A RCA accuracy delta
= -2.8 percentage points
95% CI = [-4.5, -1.1]
```

## 19.2 McNemar Test

For paired binary correctness such as:

```text
RCA correct / incorrect
```

use McNemar's test to determine whether the models have significantly different error patterns.

## 19.3 Effect Size

Always report absolute effect size, not only p-values.

Example:

```text
Frontier A: 93%
Nemotron:   91%

Absolute delta: -2 pp
Relative retained accuracy: 97.8%
```

The operational importance of the delta matters more than statistical significance alone.

## 19.4 Segment Analysis

Compute metrics by:

- incident family,
- difficulty,
- ambiguous vs non-ambiguous,
- LTE vs 5G,
- number of required tools,
- number of distractors,
- evidence-source count.

This determines **where** open-source performance diverges.

---

# 20. Error Taxonomy

Every failed held-out RCA should be assigned one or more error categories.

Recommended taxonomy:

```text
E01 Schema misunderstanding
E02 Hallucinated table/field/counter
E03 Wrong KPI formula
E04 Incorrect arithmetic
E05 SQL syntax failure
E06 SQL semantic/result failure
E07 Wrong tool selected
E08 Required tool omitted
E09 Wrong tool argument
E10 Wrong cell/site/time window
E11 Relevant evidence missed
E12 Distractor evidence followed
E13 Correlation treated as causation
E14 Contradictory evidence ignored
E15 Premature conclusion
E16 Failed to revise hypothesis
E17 Incorrect RCA despite correct evidence
E18 Correct RCA with unsupported reasoning
E19 Overconfidence
E20 Unnecessary abstention
E21 Failed to abstain when evidence insufficient
E22 Agent loop / excessive calls
E23 Output schema violation
E24 Timeout/provider failure
```

Produce error distributions per model.

This is more actionable than accuracy alone.

Example:

```text
Nemotron failures:
35% tool argument errors
25% distractor susceptibility
20% causal reasoning errors
10% schema hallucination
10% other
```

This tells the engineering team what to improve.

---

# 21. LLM-as-a-Judge Policy

Use an LLM judge only when deterministic evaluation is insufficient.

Allowed semantic grading areas:

- causal explanation quality,
- logical linkage between evidence and conclusion,
- completeness of explanation,
- whether unsupported causal claims are introduced.

Do not use an LLM judge for:

- field existence,
- table existence,
- SQL result correctness,
- KPI values,
- root-cause code when ground truth is structured,
- expected tool calls,
- timestamps,
- known evidence items.

## Judge Requirements

- same judge for every candidate model,
- candidate model name hidden,
- consistent rubric,
- structured judge output,
- temperature minimized where possible,
- randomize A/B ordering for pairwise judging,
- periodically reverse pair ordering,
- validate judge agreement against human expert labels.

---

# 22. Human Evaluation

Create a small expert-labeled calibration set.

Recommended:

```text
20–30 RCA outputs
```

Have a network-domain reviewer score:

- RCA correctness,
- evidence quality,
- causal explanation,
- completeness,
- uncertainty.

Use this to:

1. validate the deterministic scorers,
2. validate the LLM judge,
3. identify rubric ambiguity,
4. establish confidence in automated large-scale scoring.

If judge/human agreement is poor, improve the rubric before using the judge across the entire benchmark.

---

# 23. NeMo Agent Toolkit Integration

Use the NeMo Agent Toolkit evaluation framework as the execution shell where practical.

The current toolkit provides workflow evaluation, profiling support, built-in evaluators, and a plugin mechanism for custom evaluators.

Recommended custom evaluators:

```text
RootCauseAccuracyEvaluator
EvidenceGroundingEvaluator
SchemaHallucinationEvaluator
ToolCallEvaluator
ToolArgumentEvaluator
KPIAccuracyEvaluator
SQLExecutionEvaluator
AbstentionEvaluator
CalibrationCollector
```

Use NeMo's trajectory/evaluation capabilities to preserve intermediate tool calls rather than evaluating only the final response.

Keep the scoring logic in the repository so the benchmark can be rerun after model or workflow changes.

---

# 24. Proposed Repository Structure

```text
network-rca/
|
├── app/
│   ├── agents/
│   ├── tools/
│   ├── workflow/
│   └── configs/
|
├── data/
│   ├── synthetic/
│   │   ├── v1/
│   │   └── manifest.json
│   └── knowledge/
|
├── eval/
│   ├── README.md
│   |
│   ├── datasets/
│   │   ├── dev/
│   │   │   ├── model_capability.jsonl
│   │   │   └── rca_cases.jsonl
│   │   └── test/
│   │       ├── model_capability.jsonl
│   │       └── rca_cases.jsonl
│   |
│   ├── generators/
│   │   ├── generate_f1_config.py
│   │   ├── generate_f2_outage.py
│   │   ├── generate_f3_neighbour.py
│   │   ├── generate_f4_endc.py
│   │   └── generate_f5_ambiguous.py
│   |
│   ├── validators/
│   │   ├── validate_schema.py
│   │   ├── validate_ground_truth.py
│   │   └── validate_cases.py
│   |
│   ├── scorers/
│   │   ├── root_cause.py
│   │   ├── evidence.py
│   │   ├── schema_grounding.py
│   │   ├── tool_calls.py
│   │   ├── tool_arguments.py
│   │   ├── kpi.py
│   │   ├── sql.py
│   │   ├── calibration.py
│   │   └── semantic_judge.py
│   |
│   ├── configs/
│   │   ├── models/
│   │   │   ├── nemotron_telco.yml
│   │   │   ├── open_b.yml
│   │   │   ├── frontier_a.yml
│   │   │   └── frontier_b.yml
│   │   ├── eval_strict.yml
│   │   └── eval_optimized.yml
│   |
│   ├── runner/
│   │   ├── run_capability_eval.py
│   │   ├── run_agent_eval.py
│   │   └── run_all_models.py
│   |
│   ├── analysis/
│   │   ├── aggregate_results.py
│   │   ├── statistics.py
│   │   ├── error_analysis.py
│   │   └── cost_analysis.py
│   |
│   └── results/
│       └── .gitkeep
|
└── reports/
    ├── figures/
    └── final_eval_report.md
```

---

# 25. Result Record Schema

Store one row per execution, not only aggregated metrics.

Recommended structure:

```json
{
  "run_id": "uuid",
  "case_id": "F1_TEST_014",
  "model_id": "nemotron_telco",
  "model_version": "...",
  "eval_mode": "strict",
  "repetition": 2,
  "family": "config_change",
  "difficulty": "medium",

  "predicted_root_cause": "CELL_BARRED_CHANGE",
  "ground_truth_root_cause": "CELL_BARRED_CHANGE",
  "rca_correct": true,

  "evidence_precision": 1.0,
  "evidence_recall": 0.67,
  "evidence_f1": 0.80,

  "schema_validity": 1.0,
  "hallucinated_field_count": 0,

  "required_tool_recall": 1.0,
  "tool_precision": 0.67,
  "tool_argument_accuracy": 1.0,
  "tool_call_count": 3,

  "confidence": 0.91,
  "needs_further_investigation": false,

  "latency_ms": 8420,
  "input_tokens": 10940,
  "output_tokens": 1280,
  "llm_calls": 4,

  "estimated_cost_usd": 0.07,
  "error_codes": []
}
```

Also save the full trace separately for forensic review.

---

# 26. Run Manifest

Every benchmark batch must generate a manifest.

Example:

```yaml
eval_run_id: eval_2026_08_XX_001
dataset_version: synthetic_eniq_v1
test_dataset_hash: ...
workflow_commit: ...
eval_code_commit: ...
eval_mode: strict
repetitions: 3

models:
  - id: nemotron_telco
    version: ...
  - id: frontier_a
    version: ...

settings:
  temperature: ...
  max_tokens: ...
  max_agent_steps: ...
```

This prevents accidental comparison of results generated from different code or datasets.

---

# 27. Logging Requirements

For every execution log:

- case ID,
- model/version,
- incident prompt,
- system prompt version,
- tool-call sequence,
- tool arguments,
- tool results or result hashes,
- final structured RCA,
- confidence,
- token counts,
- timestamps,
- latency,
- retries,
- errors,
- scorer outputs,
- model/provider metadata.

Do not rely solely on console logs.

Persist machine-readable JSON/JSONL/Parquet/CSV outputs.

---

# 28. Failure Handling

Separate **model-quality failures** from **system failures**.

System failure examples:

- API unavailable,
- serving endpoint unavailable,
- timeout,
- malformed provider response,
- tool exception unrelated to the model,
- database unavailable.

Track these independently.

Report:

```text
Task success rate
System execution reliability
```

A provider that fails frequently may still be operationally unsuitable, but infrastructure failure should not be silently counted as an RCA reasoning error.

---

# 29. Benchmark Execution Order

Recommended sequence:

## Step 1: Validate Dataset

Run all deterministic dataset validation.

Exit criterion:

```text
100% held-out cases valid
```

## Step 2: Validate Scorers

Use manually constructed outputs representing:

- perfect answer,
- partially correct answer,
- hallucinated answer,
- wrong tool call,
- wrong RCA,
- correct abstention.

Exit criterion:

```text
Every scorer behaves as expected on unit tests.
```

## Step 3: Run T1–T5 on Development Set

Purpose:

- validate model adapters,
- inspect gross capability differences,
- fix formatting problems.

Do not draw final conclusions.

## Step 4: Run Full Agent on Development Set

Tune only allowed components.

## Step 5: Freeze Strict Benchmark

Freeze:

- dataset,
- prompts,
- configs,
- scorers,
- workflow,
- model versions.

Generate hashes/manifest.

## Step 6: Run Strict Held-Out Benchmark

Execute every model against every held-out case.

Use three repetitions.

## Step 7: Aggregate Results

Compute:

- global metrics,
- family metrics,
- difficulty metrics,
- stability,
- cost,
- latency.

## Step 8: Statistical Comparison

Compute:

- paired deltas,
- confidence intervals,
- McNemar tests where applicable.

## Step 9: Error Analysis

Inspect failure taxonomy.

## Step 10: Run Optimized Mode

Only after strict evaluation is complete.

Tune models using the development set, freeze, then run the same held-out set.

## Step 11: Human Calibration

Sample outputs across:

- models,
- correct/incorrect cases,
- easy/hard cases.

Validate semantic judge/rubric.

## Step 12: Produce Recommendation

Assess capability + economics + infrastructure.

---

# 30. Suggested Implementation Phases

# Phase E0: Evaluation Foundations

### Tasks

- Freeze ENIQ schema v1.
- Version synthetic dataset.
- Define canonical root-cause codes.
- Define structured output schema.
- Define case JSON schema.
- Build case validator.
- Build run manifest.

### Deliverables

```text
eval/datasets/
eval/schema/
eval/validators/
```

### Exit Criteria

- Dataset version reproducible.
- Every ground-truth reference is valid.
- Every case can be replayed.

---

# Phase E1: Deterministic Scorers

Implement first:

1. RootCauseAccuracyEvaluator
2. SchemaHallucinationEvaluator
3. EvidenceGroundingEvaluator
4. ToolCallEvaluator
5. ToolArgumentEvaluator
6. KPIAccuracyEvaluator
7. SQLExecutionEvaluator
8. AbstentionEvaluator

### Exit Criteria

- Unit tests exist.
- Handcrafted good/bad examples score correctly.
- No LLM judge required for core correctness.

---

# Phase E2: Evaluation Dataset

### Tasks

Generate:

```text
25 development RCA cases
100 held-out RCA cases
```

Generate T1–T5 capability tasks.

Inject:

- clear cases,
- distractors,
- irrelevant config changes,
- irrelevant alarms,
- missing data,
- ambiguous cases.

### Exit Criteria

- balanced incident families,
- difficulty labels,
- hidden ground truth,
- no accidental leaks.

---

# Phase E3: Model Adapters

### Tasks

Create interchangeable model configurations.

Verify:

- output parsing,
- tool calling,
- timeout handling,
- usage logging,
- version capture.

### Exit Criteria

One command/config switch can change candidate model without modifying agent logic.

---

# Phase E4: Development Benchmark

### Tasks

Run all models on dev cases.

Use results only to:

- debug,
- fix schemas,
- tune generic prompt issues,
- validate limits,
- establish reasonable metric thresholds.

### Exit Criteria

- no pipeline-breaking output errors,
- all candidate models runnable,
- scorer outputs complete.

---

# Phase E5: Strict Held-Out Benchmark

### Tasks

- freeze all settings,
- execute test set,
- repeat each full-agent case three times,
- log full traces,
- collect profiling information.

### Exit Criteria

- no untracked configuration changes,
- complete run manifest,
- target coverage reached.

---

# Phase E6: Analysis

### Deliverables

Tables:

1. Overall model scorecard
2. RCA accuracy by incident family
3. Accuracy by difficulty
4. Evidence metrics
5. Tool metrics
6. Hallucination metrics
7. Confidence calibration
8. Stability
9. Latency
10. Cost
11. Cost per correct RCA
12. Open-source infrastructure footprint

Charts:

- Accuracy vs cost
- Accuracy vs p95 latency
- RCA accuracy by difficulty
- RCA accuracy by incident family
- Tool-call precision/recall
- Hallucination rate
- Confidence reliability diagram
- Error-category distribution
- Cost per correct RCA

---

# Phase E7: Optimized Benchmark

### Tasks

Tune each model on dev data.

Potential tunable components:

- prompt,
- context strategy,
- reasoning settings,
- max tokens,
- model-specific parameters.

Freeze after tuning.

Re-run held-out data.

### Goal

Determine whether an initially observed gap is intrinsic or can be removed through reasonable deployment optimization.

---

# Phase E8: Recommendation

Produce a final decision matrix.

Example:

| Dimension | Nemotron | Frontier A | Frontier B |
|---|---:|---:|---:|
| RCA Accuracy | | | |
| Hard-case Accuracy | | | |
| Evidence F1 | | | |
| Hallucination Rate | | | |
| Tool Accuracy | | | |
| High-confidence Error | | | |
| p95 Latency | | | |
| Cost / Incident | | | |
| Cost / Correct RCA | | | |
| Self-hostable | Yes | No/Depends | No/Depends |
| Data control | | | |
| Operational complexity | | | |

Then state:

```text
Recommended model:
Recommended deployment pattern:
Conditions:
Known limitations:
Next validation required:
```

---

# 31. Recommended Final Visual: Pareto Frontier

The most important management-facing figure should compare quality and economics.

Example:

```text
RCA Accuracy
     ^
100% |
     |                       ● Frontier A
 95% |                ● Nemotron
     |
 90% |        ● Open B
     |
     +------------------------------------> Cost / Correct RCA
```

A model is attractive if another model cannot simultaneously beat it on both quality and cost.

Do not automatically pick the cheapest model.

Do not automatically pick the highest-accuracy model.

First enforce quality/reliability requirements, then compare economics among acceptable candidates.

---

# 32. Suggested Decision Logic

## Recommend Open-Source Deployment if:

- quality gates are passed,
- the RCA accuracy gap is operationally acceptable,
- high-confidence error rate is acceptable,
- ambiguous cases are handled safely,
- infrastructure cost is lower at expected load,
- self-hosting complexity is manageable,
- data-control benefits are valuable.

## Recommend Frontier Model if:

- open-source misses the quality gate,
- open-source failure rate is concentrated in high-impact cases,
- open-source is substantially overconfident,
- self-hosting cost eliminates expected savings,
- operational maintenance exceeds the expected benefit.

## Recommend Hybrid Architecture if:

- open-source is strong on easy/medium incidents,
- frontier is materially better on hard/ambiguous incidents.

Potential future policy:

```text
Open-source first
       |
       v
confidence / complexity gate
       |
   +---+---+
   |       |
   v       v
Accept   Escalate to frontier/human
```

Do **not** implement routing until the benchmark proves that the performance pattern justifies it.

---

# 33. Minimum Viable Eval vs Full Eval

If time becomes constrained, preserve rigor by reducing breadth rather than removing critical controls.

## Minimum Viable Eval

Must contain:

- Nemotron + one frontier model,
- 100 held-out RCA cases if possible,
- three repetitions,
- root-cause accuracy,
- evidence grounding,
- schema hallucination,
- tool-call correctness,
- latency,
- cost,
- cost/correct RCA,
- ambiguous cases,
- paired comparison.

## Full Eval

Adds:

- second open model,
- second frontier model,
- T1–T5 expanded task suite,
- semantic judge,
- expert calibration,
- confidence calibration,
- deeper statistical analysis,
- optimized-mode benchmark,
- infrastructure break-even analysis.

---

# 34. Implementation Priority

Build in this order:

```text
1. Freeze output schema
2. Freeze root-cause taxonomy
3. Build case JSON format
4. Build dataset validator
5. Build RootCauseAccuracyEvaluator
6. Build SchemaHallucinationEvaluator
7. Build EvidenceGroundingEvaluator
8. Build ToolCallEvaluator
9. Build ToolArgumentEvaluator
10. Build SQLExecutionEvaluator
11. Build KPIAccuracyEvaluator
12. Generate development cases
13. Integrate multiple model configs
14. Run development eval
15. Generate/freeze held-out test cases
16. Add profiler/cost logging
17. Run strict final benchmark
18. Add statistics
19. Perform error analysis
20. Run optimized benchmark
21. Produce management scorecard
22. Produce build-vs-buy recommendation
```

This order keeps the project measurable from the beginning.

---

# 35. First Concrete Engineering Sprint

The immediate next sprint should produce the smallest end-to-end evaluation loop.

## Task A: Define Canonical RCA Labels

Example:

```text
CELL_BARRED_CHANGE
ADMIN_STATE_CHANGE
BANDWIDTH_CHANGE
POWER_CONFIG_CHANGE
BACKHAUL_LINK_DOWN
POWER_FAILURE
NEIGHBOUR_INTERFERENCE
NR_RANDOM_ACCESS_FAILURE
UNDETERMINED
```

Avoid scoring free-text root-cause names if a stable machine-readable label is possible.

## Task B: Lock Agent JSON Output

Validate with Pydantic/JSON Schema.

## Task C: Create 10 Development Cases

Two cases from each family.

Include at least:

- one obvious RCA,
- one distractor-heavy RCA,
- one insufficient-evidence case.

## Task D: Implement Four Core Scorers

Start with:

```text
RootCauseAccuracyEvaluator
SchemaHallucinationEvaluator
EvidenceGroundingEvaluator
ToolCallEvaluator
```

## Task E: Model-Swap Configuration

Run the same ten cases on:

```text
Nemotron Telco
Frontier A
```

## Task F: Generate `results.jsonl`

One row per execution.

## Task G: Produce First Comparison Table

```text
RCA Accuracy
Evidence F1
Hallucination Rate
Tool Precision
Tool Recall
Latency
Tokens
Estimated Cost
```

Once this loop works, scaling from ten cases to one hundred is mostly a dataset and automation problem.

---

# 36. Definition of Done

The evaluation project is complete when:

- [ ] A versioned, held-out benchmark dataset exists.
- [ ] The benchmark contains all four core incident families plus ambiguous/no-answer cases.
- [ ] Synthetic data preserves the required ENIQ schema.
- [ ] Ground truth exists for every test case.
- [ ] Candidate models can be swapped without modifying agent logic.
- [ ] The strict benchmark freezes all non-model variables.
- [ ] Core scoring is deterministic.
- [ ] Tool calls and arguments are scored.
- [ ] Schema hallucinations are measured.
- [ ] SQL is execution-tested.
- [ ] KPI calculations are numerically evaluated.
- [ ] Evidence precision/recall/F1 are measured.
- [ ] Confidence calibration is measured.
- [ ] Ambiguous-case abstention is measured.
- [ ] Every full-agent test is repeated.
- [ ] Latency and usage are recorded.
- [ ] Commercial API cost is calculated.
- [ ] Self-hosted infrastructure cost is estimated.
- [ ] Cost per correct RCA is reported.
- [ ] Results are segmented by incident family and difficulty.
- [ ] Statistical uncertainty is reported.
- [ ] Failure modes are categorized.
- [ ] A strict apples-to-apples comparison is complete.
- [ ] An optimized comparison is completed if time permits.
- [ ] Final recommendation explicitly states whether open-source capability is sufficient for future network operations use cases.

---

# 37. Final Deliverables

## Deliverable 1: Evaluation Harness

Reusable tooling that can evaluate any supported model against the same benchmark.

## Deliverable 2: Versioned Benchmark Dataset

Includes:

- model-capability tasks,
- full RCA cases,
- ground truth,
- difficulty labels,
- incident-family labels.

## Deliverable 3: Raw Evaluation Results

Machine-readable outputs and traces.

## Deliverable 4: Evaluation Report

Contains:

- methodology,
- model configurations,
- quality results,
- reliability results,
- economics,
- infrastructure analysis,
- statistical comparison,
- error analysis,
- limitations.

## Deliverable 5: Executive Recommendation

Answers:

> Can open-source AI provide sufficient telecom RCA capability to reduce enterprise network operations AI costs?

The recommendation must include the conditions under which the answer is yes or no.

---

# 38. Core Principle

The benchmark should ultimately allow Rogers to make a statement such as:

> "On a held-out telecom RCA benchmark using production-faithful ENIQ schemas, Model X retained Y% of frontier-model RCA performance, reduced cost per correct incident by Z%, showed a schema hallucination rate of A%, and met/did not meet the reliability thresholds required for network-operations use."

That is substantially stronger than comparing a handful of example answers and is the level of evidence required to make a defensible open-source versus frontier model recommendation.
