# Requirements Document

## Introduction

The Network Incident Triage Assistant is a multi-agent agentic system built on the NVIDIA NeMo Agent Toolkit (NAT) for Rogers — AI for Networks. Given a natural-language incident description (cell ID, symptom, and time window), the system investigates using three CSV data sources (LTE KPIs, NR/EN-DC KPIs, and CM configuration), computes KPIs from raw PM counters, correlates evidence across at least two data sources, and produces a structured JSON Root Cause Analysis (RCA).

The system also includes an evaluation harness that benchmarks a frontier model against the open-source Nemotron Telco model on identical scripted incident scenarios using five task tiers (schema understanding, KPI calculation, multi-table join, RCA reasoning, SQL generation).

## Glossary

- **Orchestrator_Agent**: The top-level LLM agent that parses incident descriptions, plans the investigation, dispatches specialist sub-agents, and synthesises the final RCA.
- **KPI_Agent**: Specialist sub-agent that queries LTE and NR PM-counter tables and computes KPIs from raw counters.
- **CM_Agent**: Specialist sub-agent that queries configuration-management tables to detect recent parameter changes and retrieve static cell attributes.
- **Alarm_Agent**: Specialist sub-agent that correlates downtime counters and synthetic alarm history with cell availability.
- **Knowledge_Agent**: Specialist sub-agent that retrieves definitions and explanations from the Ericsson KPI guide and telecom glossary via RAG.
- **KPI_Calculator**: The internal logic (formulas + guard-rails) that derives KPI values from raw PM counters.
- **Baseline**: The per-cell median of a KPI across all earlier days in the dataset, used as the reference for degradation detection.
- **RCA_Output**: The structured JSON object `{incident, kpis_evaluated, root_cause, evidence[], confidence, further_investigation_required, recommended_next_step}` produced at the end of an investigation.
- **ENIQ**: Ericsson Network IQ — the source data-warehouse schema whose table and column names the synthetic data mirrors exactly.
- **OSS_ID**: Operational Support System identifier; a join key present on every fact table (e.g. `eniq_oss_1`).
- **EUTRANCELLFDD**: LTE FDD cell identifier; primary join key for LTE KPI and CM tables.
- **NRCellCU**: 5G NR CU cell identifier; primary join key for NR/EN-DC tables.
- **PERIOD_DURATION**: ROP (Result Output Period) length in seconds (typically 86400 for daily); used in availability calculation.
- **EN-DC**: E-UTRA New Radio Dual Connectivity — the 5G NSA architecture where an LTE anchor cell carries signalling and a 5G NR cell carries data.
- **INC-1 / INC-2 / INC-3 / INC-4**: The four scripted incident scenarios with injected ground-truth root causes used to validate and evaluate the system.
- **Tier (T1–T5)**: Evaluation task tiers — T1: schema understanding, T2: KPI calculation, T3: multi-table join, T4: RCA reasoning, T5: SQL generation.

---

## Requirements

### Requirement 1: Incident Ingestion and Scoping

**User Story:** As a network operations engineer, I want to submit a natural-language incident description and have the system automatically identify the target cell(s), OSS instance, and time window, so that the investigation is scoped correctly without manual data lookup.

#### Acceptance Criteria

1. WHEN a natural-language incident description is submitted containing a cell identifier, THEN THE Orchestrator_Agent SHALL extract the EUTRANCELLFDD (or NRCellCU or ENODEBFUNCTION), OSS_ID, and date(s) from the description, expressing each date as a (YEAR_ID, MONTH_ID, DAY_ID) tuple representing a calendar day.
2. WHEN the extracted cell identifier matches entries in `lte_kpi_sample.csv` or `nr_endc_sample.csv`, THEN THE Orchestrator_Agent SHALL return a scope confirmation response naming the resolved cell identifier(s), OSS_ID, and date window before proceeding to KPI computation.
3. IF the submitted description does not contain a string that matches an EUTRANCELLFDD pattern (alphanumeric cell ID), NRCellCU pattern, or ENODEBFUNCTION name, OR does not contain a parseable date or date range, THEN THE Orchestrator_Agent SHALL return a structured error that identifies which specific field (cell identifier or date) is missing and SHALL NOT proceed with investigation.
4. IF the submitted description contains a syntactically valid cell identifier that has no matching rows in either `lte_kpi_sample.csv` or `nr_endc_sample.csv`, THEN THE Orchestrator_Agent SHALL return a structured error stating that the cell is not found in the dataset and SHALL NOT proceed with investigation.
5. THE Orchestrator_Agent SHALL support incident descriptions that reference a single cell, a named site (ENODEBFUNCTION), or multiple cells on the same eNodeB.

---

### Requirement 2: KPI Computation from Raw PM Counters

**User Story:** As a network analyst, I want all KPIs to be derived exclusively from raw PM counters using the Ericsson-specified formulas, so that computed values are accurate and traceable to source data.

#### Acceptance Criteria

1. THE KPI_Calculator SHALL compute Accessibility (E-RAB Setup Success Rate) as a percentage in the range [0, 100] using the formula: `100 * (PMRRCCONNESTABSUCC / (PMRRCCONNESTABATT - PMRRCCONNESTABATTREATT)) * (PMS1SIGCONNESTABSUCC / PMS1SIGCONNESTABATT) * (PMERABESTABSUCCINIT / PMERABESTABATTINIT)`.
2. THE KPI_Calculator SHALL compute Retainability (E-RAB % Lost) as a percentage using the formula: `100 * (PMERABRELABNORMALENB / (PMERABRELABNORMALENB + PMERABRELNORMALENB))`.
3. THE KPI_Calculator SHALL compute DL Throughput using the formula: `(PMPDCPVOLDLDRB - PMPDCPVOLDLDRBLASTTTI) / PMUETHPTIMEDL`, where PMPDCPVOLDLDRB and PMPDCPVOLDLDRBLASTTTI are in bits, PMUETHPTIMEDL is in milliseconds, and the result is expressed in kbps.
4. THE KPI_Calculator SHALL compute Cell Availability as a percentage using the formula: `100 * (1 - ((PMCELLDOWNTIMEAUTO + PMCELLDOWNTIMEMAN) / PERIOD_DURATION))`.
5. THE KPI_Calculator SHALL compute DL PDCP DRB Latency in milliseconds using the formula: `(PMPDCPLATTIMEDL / PMPDCPLATPKTTRANSDL) / 10`, where PMPDCPLATTIMEDL accumulates in 0.1 ms units and the division by 10 converts to milliseconds.
6. THE KPI_Calculator SHALL compute EN-DC Setup Success Rate as a percentage using the formula: `100 * (pmEndcSetupUeSucc / pmEndcSetupUeAtt)`, sourcing counters from `nr_endc_sample.csv`.
7. IF any denominator in a KPI formula evaluates to zero or SQL NULL, THEN THE KPI_Calculator SHALL assign a null value (Python `None` or SQL NULL) for that KPI and SHALL NOT raise a runtime error.
8. THE KPI_Agent SHALL NEVER read columns whose names match a computed KPI label rather than a raw PM counter column name (e.g., a column literally named "Accessibility" or "DL_Throughput_kbps"); THE KPI_Agent SHALL always derive KPI values by applying the formulas in AC 1–6 to raw counter columns.
9. THE KPI_Calculator SHALL compute a per-cell Baseline for each KPI as the median of that KPI's computed values across all DAY_IDs in the dataset strictly earlier than the DAY_ID of the incident under investigation; IF no prior days exist for a given cell, THE KPI_Calculator SHALL assign a null Baseline for that cell.

---

### Requirement 3: Degradation Detection and Flagging

**User Story:** As a network analyst, I want the system to automatically flag which KPIs are degraded on the incident day relative to the cell's own baseline, so that I can focus on the meaningful signals.

#### Acceptance Criteria

1. IF the computed Accessibility value is below 95%, OR IF the computed Accessibility value is more than 5 percentage points below the non-null Baseline for that cell, THEN THE KPI_Agent SHALL flag Accessibility as "degraded" (either sub-condition alone is sufficient to trigger the flag).
2. IF the computed Retainability (% lost) value exceeds 2%, THEN THE KPI_Agent SHALL flag Retainability as "degraded".
3. IF the computed DL Throughput value is more than 30% below the non-null Baseline for that cell, THEN THE KPI_Agent SHALL flag DL Throughput as "degraded".
4. IF the computed Cell Availability value is below 99%, THEN THE KPI_Agent SHALL flag Cell Availability as "degraded".
5. IF the computed DL PDCP DRB Latency value is more than 30% above the non-null Baseline for that cell, THEN THE KPI_Agent SHALL flag DL PDCP DRB Latency as "degraded".
6. IF the computed EN-DC Setup Success Rate is below 90%, THEN THE KPI_Agent SHALL flag EN-DC Setup Success Rate as "degraded".
7. IF a KPI value is null (denominator was zero or counters are missing), THEN THE KPI_Agent SHALL assign the status "unavailable" and SHALL NOT apply the degradation threshold.
8. IF the Baseline for DL Throughput or DL PDCP DRB Latency is null (no prior days exist for the cell), THEN THE KPI_Agent SHALL assign the status "unavailable — missing baseline" for that KPI and SHALL NOT apply the relative degradation threshold (AC 3 or AC 5).
9. THE KPI_Agent SHALL include each evaluated KPI in the `kpis_evaluated` array of the RCA_Output with fields: `kpi` (name string), `value` (computed numeric value or null), `baseline` (median numeric value or null), and `status` — where `status` is "ok" WHEN the KPI is non-null and does not meet any degradation condition in AC 1–6, "degraded" WHEN any degradation condition in AC 1–6 is met, and "unavailable" WHEN the KPI value or required baseline is null.

---

### Requirement 4: Selective Tool Dispatch by Degradation Type

**User Story:** As a system designer, I want the Orchestrator Agent to choose investigation tools based on which KPIs are degraded, so that the system avoids unnecessary queries and focuses on the most likely root causes.

#### Acceptance Criteria

1. WHEN Accessibility, DL Throughput, or DL PDCP DRB Latency is flagged as "degraded", THE Orchestrator_Agent SHALL invoke the CM_Agent to check for configuration changes on the target cell in `cm_config_sample.csv` with a DATETIME_ID within the 7 calendar days preceding the first KPI-degraded DAY_ID.
2. WHEN Cell Availability is flagged as "degraded", THE Orchestrator_Agent SHALL invoke the Alarm_Agent to retrieve alarm history and downtime counters (PMCELLDOWNTIMEAUTO, PMCELLDOWNTIMEMAN) for the target cell within the incident window.
3. WHEN EN-DC Setup Success Rate is flagged as "degraded", THE Orchestrator_Agent SHALL invoke the KPI_Agent to retrieve and report the pmEndcSetupUeSucc and pmEndcSetupUeAtt counter values for the target NR cell on the incident day.
4. WHEN EN-DC Setup Success Rate is flagged as "degraded", THE Orchestrator_Agent SHALL also invoke the KPI_Agent to compute the Accessibility KPI for the LTE anchor cell associated with the target NR cell; IF the LTE anchor Accessibility is below 95%, THE Orchestrator_Agent SHALL report the anchor cell as degraded and treat both degradation signals as independent evidence items.
5. WHEN no KPIs on the target cell are flagged as "degraded" but the incident description reports a user-perceived symptom, THE Orchestrator_Agent SHALL invoke the KPI_Agent on all cells sharing the same ENODEBFUNCTION as the target cell; IF at least 2 of those neighbouring cells show the same KPI flagged as "degraded" within the incident window, THE Orchestrator_Agent SHALL treat this as a multi-cell degradation event.
6. THE Orchestrator_Agent SHALL NOT invoke every specialist sub-agent unconditionally; THE Orchestrator_Agent SHALL select sub-agents based solely on the degradation profile determined in Requirement 3.

---

### Requirement 5: Multi-Source Evidence Correlation

**User Story:** As a network analyst, I want the system to confirm a root cause by correlating evidence from at least two independent data sources, so that the RCA has a verifiable factual basis and not just a single signal.

#### Acceptance Criteria

1. THE Orchestrator_Agent SHALL collect evidence items from a minimum of 2 distinct source domains — where valid domains are (a) KPI counters from `lte_kpi_sample.csv` or `nr_endc_sample.csv`, (b) configuration parameters from `cm_config_sample.csv`, and (c) alarm or downtime records from the Alarm_Agent — before assigning `confidence` = "high" to the RCA_Output.
2. WHEN a configuration change in `cm_config_sample.csv` has a DATETIME_ID within the 7 calendar days preceding the first DAY_ID on which any monitored KPI (Accessibility < 95%, Retainability > 2%, DL Throughput > 30% below baseline, Availability < 99%, DL Latency > 30% above baseline, or EN-DC Success < 90%) is degraded for the same EUTRANCELLFDD and OSS_ID, THEN THE Orchestrator_Agent SHALL record the CM change and the KPI drop as correlated evidence items for a config-change root cause.
3. WHEN a value of PMCELLDOWNTIMEAUTO or PMCELLDOWNTIMEMAN greater than 0 is found for the target cell on the incident DAY_ID, AND an alarm record exists for the same EUTRANCELLFDD (or NRCellCU) on that same DATETIME_ID date, THEN THE Orchestrator_Agent SHALL record the downtime counter value and the alarm record as correlated evidence items for an outage root cause.
4. WHILE EN-DC Setup Success Rate for the target NRCellCU is below 90% on the incident day AND the Accessibility KPI for the associated LTE anchor cell is at or above 95% on the same day, THE Orchestrator_Agent SHALL record the EN-DC drop and the healthy LTE anchor as correlated evidence items for a 5G NSA-layer root cause.
5. WHEN KPI degradation (any of the six KPIs below its configured threshold) is observed on at least 2 cells sharing the same ENODEBFUNCTION on the incident DAY_ID, AND no CM change exists in `cm_config_sample.csv` for any of those cells within the preceding 7 calendar days, THEN THE Orchestrator_Agent SHALL record the multi-cell KPI spread and the absence of CM changes as correlated evidence items for an interference or neighbour-affecting root cause.

---

### Requirement 6: Structured RCA Output

**User Story:** As a network operations engineer, I want the investigation to produce a machine-readable JSON RCA report, so that results can be reviewed, audited, and potentially ingested by downstream ticketing or dashboarding systems.

#### Acceptance Criteria

1. THE Orchestrator_Agent SHALL produce an RCA_Output JSON object containing exactly the fields: `incident`, `kpis_evaluated`, `root_cause`, `evidence`, `confidence`, `further_investigation_required`, and `recommended_next_step`.
2. THE `evidence` field SHALL be an array of strings, each citing an actual computed value, counter name, table name, or timestamp from the source CSVs.
3. THE Orchestrator_Agent SHALL NOT populate any evidence entry with data that is not present in the source CSVs or returned by a specialist sub-agent tool call.
4. IF evidence items from at least 2 distinct source domains (as defined in Requirement 5 AC 1) are collected, THEN THE Orchestrator_Agent SHALL set `confidence` to "high".
5. IF evidence items from exactly 1 distinct source domain are collected and KPI degradation is confirmed, THEN THE Orchestrator_Agent SHALL set `confidence` to "medium".
6. IF the signal is ambiguous — defined as two or more root-cause hypotheses each supported by an equal number of evidence items with no differentiating signal — or if counters are unavailable for more than one of the six KPIs defined in Requirement 2, THEN THE Orchestrator_Agent SHALL set `confidence` to "low".
7. IF no evidence items are collected (no KPI degradation detected and no corroborating data found), THEN THE Orchestrator_Agent SHALL set `confidence` to "low" and SHALL set `further_investigation_required` to false.
8. IF `confidence` is "low" and at least one evidence item was collected, THEN THE Orchestrator_Agent SHALL set `further_investigation_required` to true.
9. THE `root_cause` field SHALL contain a single statement of 200 characters or fewer identifying the most likely root cause; alternative hypotheses SHALL be recorded only in `recommended_next_step`.
10. IF a counter column referenced by a KPI formula is absent from the source CSV for the queried cell and date, THEN THE Orchestrator_Agent SHALL include an entry in the `evidence` array with the notation "<counter_name>: counter unavailable" and SHALL NOT fabricate a value for it.

---

### Requirement 7: Four Scripted Incident Scenarios

**User Story:** As an evaluator, I want the system to correctly diagnose four pre-scripted incident scenarios with known ground-truth root causes, so that system accuracy can be measured deterministically.

#### Acceptance Criteria

1. WHEN INC-1 is submitted (KPI degradation after a configuration change), THE Orchestrator_Agent SHALL identify the root cause as a recent CM parameter change, SHALL cite the specific parameter name (e.g., ADMINISTRATIVESTATE or DLCHANNELBANDWIDTH), the old and new values, and the DATETIME_ID of the change that precedes the first KPI-degraded DAY_ID.
2. WHEN INC-2 is submitted (cell/site outage), THE Orchestrator_Agent SHALL identify the root cause as a cell outage, SHALL cite the PMCELLDOWNTIMEAUTO or PMCELLDOWNTIMEMAN spike value (greater than 0) and the aligned alarm record name (e.g., "Backhaul Link Down"), and SHALL note in `recommended_next_step` whether the CM change log is empty for that cell (indicating unplanned outage).
3. WHEN INC-3 is submitted (neighbour degradation / interference), THE Orchestrator_Agent SHALL identify the root cause as an interference or neighbour-affecting condition, SHALL cite KPI degradation on at least 2 cells sharing the same ENODEBFUNCTION as the reported cell, and SHALL confirm in the `evidence` array that no CM change was found for the target cell in the 7 days preceding the incident.
4. WHEN INC-4 is submitted (EN-DC accessibility drop), THE Orchestrator_Agent SHALL identify the root cause as a 5G NSA / EN-DC setup failure, SHALL cite the degraded pmEndcSetupUeSucc/pmEndcSetupUeAtt ratio value on the NR cell, and SHALL confirm in the `evidence` array that the LTE anchor cell's Accessibility KPI is at or above 95% on the incident day.
5. THE system SHALL produce a correct RCA (matching the injected ground truth) on at least 80% of scripted incident runs across the four scenarios.
6. A run is scored "correct" WHEN the `root_cause` field identifies the same causal category as the injected ground truth AND the `evidence` array cites at least one counter or parameter name that directly supports that category.

---

### Requirement 8: Data Source Fidelity and Schema Grounding

**User Story:** As an evaluator, I want the agents to use only columns that actually exist in the source CSVs and reference them by their real ENIQ names, so that schema grounding accuracy can be measured and the system transfers directly to a live ENIQ deployment.

#### Acceptance Criteria

1. WHEN the KPI_Agent queries `lte_kpi_sample.csv`, THE KPI_Agent SHALL filter rows using the join keys `EUTRANCELLFDD`, `OSS_ID`, `YEAR_ID`, `MONTH_ID`, and `DAY_ID` only.
2. WHEN the KPI_Agent queries `nr_endc_sample.csv`, THE KPI_Agent SHALL filter rows using the join keys `NRCellCU`, `OSS_ID`, `YEAR_ID`, `MONTH_ID`, and `DAY_ID` only.
3. WHEN the CM_Agent queries `cm_config_sample.csv`, THE CM_Agent SHALL filter rows using the join keys `EUTRANCELLFDD`, `OSS_ID`, and `DATETIME_ID` only.
4. WHEN the KPI_Agent constructs any query or data-access call targeting `lte_kpi_sample.csv` or `nr_endc_sample.csv`, IF the query references a column name that is not present in the respective CSV header row, THEN that column reference SHALL be counted as one hallucinated-field occurrence and recorded in the per-query hallucinated-field counter for evaluation.
5. WHEN the CM_Agent constructs any query or data-access call targeting `cm_config_sample.csv`, IF the query references a column name that is not present in the CSV header row, THEN that column reference SHALL be counted as one hallucinated-field occurrence and recorded in the per-query hallucinated-field counter for evaluation.
6. THE system SHALL use the exact ENIQ column name casing and spelling as defined in the source CSV headers when querying LTE KPI data — e.g., `PMRRCCONNESTABSUCC` (UPPERCASE, as in `lte_kpi_sample.csv`), not `pmRrcConnEstabSucc`.
7. THE system SHALL use the exact casing for NR EN-DC counter columns as defined in `nr_endc_sample.csv` — e.g., `pmEndcSetupUeSucc` (camelCase) — and the exact casing for CM columns as defined in `cm_config_sample.csv` — e.g., `ADMINISTRATIVESTATE` (UPPERCASE).

---

### Requirement 9: Evaluation Harness — Task Tiers

**User Story:** As a researcher, I want a reproducible evaluation harness that benchmarks frontier and open-source models across five capability tiers on a fixed, versioned dataset, so that I can quantify capability and cost trade-offs objectively.

#### Acceptance Criteria

1. THE Evaluation_Harness SHALL define five task tiers: T1 (schema understanding — exact-match scoring), T2 (KPI calculation — numeric tolerance of ±0.01 percentage points or ±0.01 kbps/ms), T3 (multi-table join — row/set match scoring), T4 (RCA reasoning — rubric scoring on a 0–3 integer scale with a published rubric mapping each score to observable output characteristics), and T5 (SQL generation — valid-SQL scoring where "correct" requires the generated SQL to reference at least the same tables and join keys as the reference solution).
2. WHEN the Evaluation_Harness runs a task suite, THE Evaluation_Harness SHALL identify the dataset version (e.g., a checksum or version tag of the three CSV files) in the run output and SHALL use the same versioned dataset for every model being compared in that run.
3. THE Evaluation_Harness SHALL record per-model, per-tier task accuracy as a percentage, calculated as (number of correct responses / total tasks in that tier) × 100.
4. THE Evaluation_Harness SHALL record a hallucinated-field rate per model per run, defined as (total hallucinated-field occurrences across all tool calls) / (total tool calls) × 100.
5. THE Evaluation_Harness SHALL record tool-call correctness per model, defined as (tool calls where the invoked agent name matches the expected agent AND all required argument keys are present with values within the valid domain) / (total tool calls) × 100.
6. THE Evaluation_Harness SHALL record, per task per model: prompt tokens consumed, completion tokens consumed, end-to-end wall-clock latency in seconds from prompt submission to final response receipt, and estimated cost in USD.
7. WHEN all models complete the task suite, THE Evaluation_Harness SHALL produce a summary report containing a table with one row per model and columns for each of the six metrics defined in AC 3–6, plus a per-tier accuracy breakdown for each model.

---

### Requirement 10: Confidence and Uncertainty Handling

**User Story:** As a network operations engineer, I want the system to clearly signal when evidence is insufficient or ambiguous, so that I know when to escalate to a human expert rather than act on a low-confidence RCA.

#### Acceptance Criteria

1. WHEN the computed evidence supports a root cause from at least 2 distinct source domains (as defined in Requirement 5 AC 1), THE Orchestrator_Agent SHALL set `confidence` to "high" and SHALL set `further_investigation_required` to false.
2. WHEN the computed evidence supports a root cause from exactly 1 distinct source domain only, THE Orchestrator_Agent SHALL set `confidence` to "medium" and SHALL set `further_investigation_required` to false.
3. IF two or more root-cause hypotheses are each supported by an equal number of evidence items and no differentiating signal exists, OR IF counter data is unavailable for more than one of the six KPIs defined in Requirement 2, OR IF no corroborating data source from a second domain can be identified, THEN THE Orchestrator_Agent SHALL set `confidence` to "low" and SHALL set `further_investigation_required` to true.
4. THE Orchestrator_Agent SHALL populate `recommended_next_step` with a string that names at least one of the following: a specific sub-agent to invoke, a data source to query, a counter or KPI to inspect, or a threshold to verify.
5. THE Orchestrator_Agent SHALL list only the single most likely root cause in the `root_cause` field; alternative hypotheses SHALL appear only in `recommended_next_step`.
6. IF no evidence items are collected and no KPI degradation is detected, THEN THE Orchestrator_Agent SHALL set `root_cause` to "No degradation detected — root cause undetermined" and SHALL set `recommended_next_step` to an action that names at least one sub-agent or data source to investigate further.

---

### Requirement 11: NeMo Agent Toolkit Integration

**User Story:** As a developer, I want the agent system to be built natively on the NVIDIA NeMo Agent Toolkit workflow and function primitives, so that the architecture is maintainable and extensible using the established NAT patterns already present in the workspace.

#### Acceptance Criteria

1. THE Orchestrator_Agent SHALL be implemented as a `react_agent` declared under the `workflow:` section of a `workflow.yml` file located at the workspace root.
2. THE KPI_Agent, CM_Agent, Alarm_Agent, and Knowledge_Agent SHALL each be registered as named entries under the `functions:` section of `workflow.yml`, each containing a non-empty `description` field and appearing in the `tool_names` list of the Orchestrator_Agent.
3. THE system SHALL call `load_dotenv()` before building the NAT workflow, sourcing at minimum three environment variables — `LLM_MODEL_NAME`, `LLM_API_KEY`, and `LLM_BASE_URL` — and SHALL raise a `EnvironmentError` at build time if any of these variables is absent or empty.
4. THE `workflow.yml` SHALL declare at least two named `llms:` entries — one for a frontier API provider and one for a self-hosted Nemotron Telco endpoint — such that switching the active model requires only an update to the `llm_name` reference in the workflow or an override of the corresponding `.env` variables, with no code changes.
5. WHEN the NAT workflow is invoked via `main.py` with a non-empty incident description string, THE system SHALL return a valid, parseable JSON string that conforms to the RCA_Output schema defined in Requirement 6 AC 1.
6. IF any required environment variable (`LLM_MODEL_NAME`, `LLM_API_KEY`, or `LLM_BASE_URL`) is absent or empty at workflow build time, THEN THE system SHALL raise an `EnvironmentError` with a message identifying the missing variable name and SHALL NOT proceed to start the NAT workflow.

---

### Requirement 12: KPI Formula Round-Trip Correctness

**User Story:** As a developer, I want to verify that the KPI computation logic is numerically correct and handles edge cases robustly, so that the evaluation harness produces reliable scores.

#### Acceptance Criteria

1. FOR ALL rows in `lte_kpi_sample.csv` where every counter referenced in a given KPI formula (AC 1–5 of Requirement 2) is non-null and every denominator is strictly greater than zero, THE KPI_Calculator SHALL produce a non-null numeric value for that KPI.
2. FOR ALL rows in `nr_endc_sample.csv` where `pmEndcSetupUeAtt` is strictly greater than zero and `pmEndcSetupUeSucc` is non-null, THE KPI_Calculator SHALL produce a non-null EN-DC Setup Success Rate value in the closed interval [0, 100].
3. IF the computed Cell Availability before capping exceeds 100% (i.e., PMCELLDOWNTIMEAUTO + PMCELLDOWNTIMEMAN > PERIOD_DURATION), THEN THE KPI_Calculator SHALL return 100.0 as the Cell Availability value and SHALL set a boolean `data_quality_flag` field to true in the KPI result object for that row.
4. FOR ALL rows where the KPI formula inputs are non-null and denominators are non-zero, THE KPI_Calculator SHALL produce the same numeric result (within a floating-point tolerance of 1×10⁻⁹ relative error) when the formula is applied once versus when it is applied a second time to the same unmodified input values (idempotence and determinism).
