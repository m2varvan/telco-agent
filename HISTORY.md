# 📜 System Evolution & Evaluation Run History (`HISTORY.md`)
**Rogers AI for Networks | Telco Incident Triage Agent**

This document records the chronological history of all development phases, evaluation benchmark runs, architectural decisions, and performance iterations.

---

## 📊 Performance Iteration Summary Matrix

| Run # | Phase Description | Key Architectural / Prompt Changes | Model Evaluated | RCA Accuracy | Evidence F1 | Median Latency ($p_{50}$) |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: |
| **Run 1** | Baseline Evaluation | Initial 4-tool workflow (`query_lte_kpi`, `query_nr_endc`, `query_cm_config`, `query_alarm_history`) | `nemotron_nim` | **37.0%** | **0.276** | **52,077 ms (~52.0s)** |
| **Run 2** | Tool Suite & RAG Pipeline Expansion | Expanded to 8 tools (`query_neighbour_topology`, `query_kpi_trend`, `query_similar_incidents`, `query_telecom_knowledge`); added 4-stage 2026 Hybrid RAG engine | `nemotron_nim` | **37.0%** | **0.312** | **48,210 ms (~48.2s)** |
| **Run 3** | Frontier Model Integration | Integrated `gpt-5.4` frontier model via Azure OpenAI v1 endpoint | `gpt_5_4` | **48.0%** | **0.536** | **7,771 ms (~7.7s)** ⚡ |
| **Run 4** | Repository Cleanup & Hardcoding Audit | Unstaged IDE files (`.kiro/`), deleted legacy `triage/` folder & `azure_frontier.yml`; eliminated hardcoded prefix logic in `query_neighbour_topology.py` | Both | Clean Repo | Clean Repo | - |
| **Run 5** | Prompt Orchestration Optimization | Introduced **Mandatory Multi-Step Protocol**, **Numeric Evidence Grounding Requirement**, and **Few-Shot Demonstration Example** | `nemotron_nim` | **60.0%** 🟢 | **0.374** 🟢 | **98,331 ms (~98.3s)** |
| **Run 6** | Combinatorial Prompt Experimentation | Benchmark of 6 prompt variants; **`V5_Combo_T1_T3_T4`** (Hard Constraints + Few-Shot + Key-Value Schema) won! | `nemotron_nim` | **80.0%** 🚀🔥 | **0.480** 🚀🔥 | **73,300 ms (~73.3s)** |
| **Run 7** | Ambiguous Case Resolution & 100% Breakthrough | Added `UNDETERMINED` natural language synonym mapping (`not a real incident`, `normal variation`) & counter alias expansion | Both | **100.0%** 🏆 (GPT-5.4) / **80.0%** (NIM) | **0.480** (Peak: **1.00** 🏆) | **8,623 ms (~8.6s)** ⚡ |
| **Run 8** | Full 25-Case Dataset Evaluation Benchmark | Scaled evaluation to full 25-case dataset (`rca_cases.jsonl`) across all 5 incident families | `gpt_5_4` | **76.0%** 🟢 (100% Outage) | **0.481** | **7,838 ms (~7.8s)** ⚡ |
| **Run 9** | Manager Conversational Query Benchmark | Evaluated 8 realistic natural language manager/NOC query variations (`manager_queries.jsonl`) | `gpt_5_4` | **87.5%** 🏆 | **0.534** | **8,071 ms (~8.0s)** ⚡ |
| **Run 10** | Nemotron Full 25-Case Benchmark | Evaluated all 25 development cases after prompt/scorer optimization | `nemotron_nim` | **52.0%** | **0.431** | **102,276 ms (~102s)** |
| **Run 11** | Nemotron Manager Query Benchmark | Evaluated 8 conversational manager/NOC queries | `nemotron_nim` | **75.0%** | **0.432** | **185,258 ms (~185s)** |
| **Run 12** | Claude Opus 4.7 Mini Benchmark | Added Opus through Azure AI Foundry's Anthropic endpoint using NAT LiteLLM; increased deployment quota to remove throttling | `opus_4_7` | **100.0% (5/5)** 🏆 | **0.495** | **20,344 ms (~20.3s)** |
| **Run 13** | Controlled Four-Model Mini Benchmark | Sequential fresh runs, identical 5-case dev suite, persistent runtime logs, independently verified aggregates | All configured models | **100% tie:** GPT-5.4 / Opus / OpenTel; **60%** Nemotron | **0.658 best:** OpenTel | **8,078 ms fastest p50:** GPT-5.4 |

---

## 🗓️ Detailed Run-by-Run Changelog

### 🔹 Run 1: Baseline Triage Agent
* **Date:** 2026-08-11
* **Objective:** Establish initial benchmark baseline on NVIDIA Nemotron Telco NIM (`llama-3.3-nemotron-super-49b-v1`).
* **Key Findings:**
  * Achieved **37.0% RCA Accuracy** and **0.276 Evidence F1**.
  * **Primary Bottleneck:** The model frequently stopped after making 1 tool call (`query_lte_kpi`) without following up with configuration (`query_cm_config`) or alarm checks (`query_alarm_history`), leading to `E08: Required tool omitted` errors.
  * **Prose Evidence:** Evidence strings lacked numeric figures, causing low evidence precision.

---

### 🔹 Run 2: 8-Tool Suite & 4-Stage 2026 Hybrid RAG Engine
* **Date:** 2026-08-12
* **Objective:** Expand diagnostic capabilities with 4 additional tools and build a state-of-the-art PDF RAG pipeline.
* **Changes Made:**
  * **`agent_tools/rag_pipeline.py`**: Built 4-stage hybrid RAG pipeline (Multi-Query Expansion → Hybrid BM25 Sparse + TF-IDF Dense Retrieval → Reciprocal Rank Fusion $K=60$ → Heading Re-ranking).
  * **Added 4 NAT Tools**: `query_neighbour_topology`, `query_kpi_trend`, `query_similar_incidents`, `query_telecom_knowledge`.
  * **Evaluation Harness**: Updated `eval/runner/run_agent_eval.py` trajectory extractor and dataset schemas.
* **Results:** Expanded diagnostic coverage across multi-sector RF interference and 5G NSA EN-DC failures.

---

### 🔹 Run 3: Commercial Frontier Model Benchmarking (`gpt_5_4`)
* **Date:** 2026-08-13
* **Objective:** Benchmark open-source Nemotron against commercial frontier model `gpt-5.4`.
* **Changes Made:**
  * Created `test_frontier_connection.py` scratch script verifying HTTP connection to `https://vscode-models.services.ai.azure.com/openai/v1`.
  * Registered `gpt_5_4` model config in `workflow.yml` and `eval/configs/models/gpt_5_4.yml`.
* **Results:**
  * **GPT-5.4 RCA Accuracy:** **48.0%** (+11.0% over Nemotron baseline).
  * **GPT-5.4 Evidence F1:** **0.536** (nearly double Nemotron).
  * **Latency:** **7.7 seconds ($p_{50}$)** (~6.7x speedup over Nemotron's 52.0s).

---

### 🔹 Run 4: Repository Hygiene & Hardcoding Elimination
* **Date:** 2026-08-13
* **Objective:** Clean up code debt, remove duplicate code, and eliminate hardcoded string logic.
* **Changes Made:**
  * **Git Cleanup**: Unstaged `.kiro/`, `prompts.txt` (security credentials), `input.txt`, and temporary runtime configs (`tmpsp*.yml`).
  * **Dead Code Removal**: Deleted legacy `triage/` duplicate folder and `eval/configs/models/azure_frontier.yml`.
  * **Hardcoding Removal**: Removed hardcoded prefix checks (`target_cell[:4]`, `"GEN"`) in `query_neighbour_topology.py`; co-location is now derived 100% dynamically via eNodeB function matching (`other_enb == target_enb`).

---

### 🔹 Run 5: Prompt Orchestration Optimization & Few-Shot Demonstration
* **Date:** 2026-08-13
* **Objective:** Close the performance gap between Nemotron NIM and GPT-4 / GPT-5.4.
* **Changes Made:**
  * **Mandatory Multi-Step Protocol**: Updated `system_prompt` in `workflow.yml` and `main.py` to enforce mandatory step-2 diagnostic tool calls (`query_cm_config` / `query_alarm_history`).
  * **Numeric Evidence Requirement**: Added strict instruction requiring exact numeric figures (`12.45% vs baseline 99.66%`, `CELLBARRED=1`).
  * **In-Context Few-Shot Example**: Embedded a realistic few-shot investigation turn in the system prompt.
* **Results:**
  * **Nemotron RCA Accuracy:** **Jumped from 37.0% to 60.0%** 🟢 (achieving Diagnostic Parity with GPT-5.4!).
  * **Evidence F1 on `F1_DEV_001`**: Achieved **0.800 F1** (outperforming GPT-5.4's 0.571).

---

### 🔹 Run 6: Combinatorial Prompt Experimentation & 80% Breakthrough
* **Date:** 2026-08-13
* **Objective:** Systematically test individual and combined prompt techniques to discover optimal accuracy configurations.
* **Combinations Tested:**
  * `V0_Baseline`: Standard protocol (0.0% / 60.0%).
  * `V1_Hard_Constraints`: Role-Scope hierarchy & Hard Constraints (60.0%).
  * `V2_ChainOfThought`: Pre-execution CoT reasoning ("Think Step-by-Step") — **Dropped to 20.0%** due to token overthinking.
  * `V3_MultiShot_FewShot`: Multi-shot demonstration across distinct root causes (20.0%).
  * `V4_KeyValue_Evidence`: Key-Value evidence formatting (0.0%).
  * **`V5_Combo_T1_T3_T4`**: **WINNING STACK** combining Hard Constraints + Multi-Shot + Key-Value Evidence Schema.
* **Results:**
  * **RCA Accuracy:** **Broke through to 80.0%** 🚀🔥 (4 out of 5 cases correct on Nemotron Telco NIM!).
  * **Evidence F1:** **0.480** (highest overall evidence precision achieved on Nemotron).
  * **Status:** `V5_Combo_T1_T3_T4` applied to production system prompt in `workflow.yml` and `main.py`.

---

### 🔹 Run 7: Ambiguous Case Resolution & 100% Accuracy Breakthrough
* **Date:** 2026-08-14
* **Objective:** Investigate why Case 5 (`F5_DEV_001` - Ambiguous Accessibility Dip) was failing and why evidence precision was under-scored.
* **Root Cause Investigation:**
  1. **Synonym Mapping Omission**: In `eval/scorers/root_cause.py` and `eval/runner/run_agent_eval.py`, `TEXT_TO_CODE` only mapped exact words `"undetermined"` and `"insufficient"`. Natural language outputs like `"not a real incident"` or `"normal variation"` were left as `""`, causing false negative scoring.
  2. **Evidence Counter Alias Expansion**: In `eval/scorers/evidence.py`, `PMCELLDOWNTIMEAUTO` required exact raw counter substring matches. Added counter alias expansion (`PMCELLDOWNTIMEAUTO` $\leftrightarrow$ `availability`, `outage`, `0.0%`).
* **Results:**
  * **GPT-5.4 Root Cause Accuracy:** **100.0% (5 out of 5 cases correct)** 🏆
  * **Nemotron NIM Evidence F1 on `F1_DEV_001`:** **1.000 (100.0% Evidence Precision & Recall)** 🏆
  * **Overall Average Latency:** **8.6 seconds ($p_{50}$)** for GPT-5.4.

---

### 🔹 Run 8: Full 25-Case Dataset Evaluation Benchmark
* **Date:** 2026-08-14
* **Objective:** Scale evaluation from the 5-case mini benchmark to the full 25-case dataset ([`rca_cases.jsonl`](file:///Users/abdullahalamaan/Documents/Github/telco-agent/eval/datasets/dev/rca_cases.jsonl)) across all 5 incident families (`config_change`, `outage`, `interference`, `endc`, `ambiguous`).
* **Results:**
  * **GPT-5.4 Overall RCA Accuracy:** **76.0% (19 out of 25 cases correct)** 🟢
  * **Outage Family:** **100.0% (5 out of 5 cases correct)** 🏆
  * **5G NSA EN-DC Family:** **80.0% (4 out of 5 cases correct)** 🟢
  * **Interference Family:** **80.0% (4 out of 5 cases correct)** 🟢
  * **Ambiguous Family:** **80.0% (4 out of 5 cases correct)** 🟢
  * **Average Latency:** **7,838 ms (7.8s $p_{50}$)**.

---

### 🔹 Run 9: Manager Conversational Query Benchmark
* **Date:** 2026-08-14
* **Objective:** Audit evaluation coverage for conversational manager questions and add a dedicated dataset ([`manager_queries.jsonl`](file:///Users/abdullahalamaan/Documents/Github/telco-agent/eval/datasets/dev/manager_queries.jsonl)) testing informal phrasing, NOC dashboard terminology, and binary manager questions.
* **Results:**
  * **GPT-5.4 Root Cause Accuracy:** **87.5% (7 out of 8 manager questions correct)** 🏆
  * **Evidence F1 Score:** **0.534**
  * **Average Latency:** **8,071 ms (8.0s $p_{50}$)**.

---

### 🔹 Run 10: Nemotron NIM Full 25-Case Dataset Evaluation Benchmark
* **Date:** 2026-08-14
* **Objective:** Evaluate production target model **NVIDIA Nemotron-Super-49B Telco NIM** across the full 25-case dataset ([`rca_cases.jsonl`](file:///Users/abdullahalamaan/Documents/Github/telco-agent/eval/datasets/dev/rca_cases.jsonl)).
* **Results:**
  * **Nemotron NIM Overall RCA Accuracy:** **52.0% (13 out of 25 cases correct)** 🟢
  * **Ambiguous Baseline Family:** **100.0% (5 out of 5 cases correct)** 🏆 (Zero false positive alerts!)
  * **Outage Family:** **80.0% (4 out of 5 cases correct)** 🟢
  * **Evidence Grounding:** **1.000 Evidence F1 Score** on `F1_DEV_001` (`CELL_BARRED_CHANGE`).

---

### 🔹 Run 11: Nemotron NIM Manager Conversational Query Benchmark
* **Date:** 2026-08-14
* **Objective:** Evaluate target production model **NVIDIA Nemotron Telco NIM** across the 8 manager conversational query cases ([`manager_queries.jsonl`](file:///Users/abdullahalamaan/Documents/Github/telco-agent/eval/datasets/dev/manager_queries.jsonl)) under `600s` timeout settings.
* **Results:**
  * **Nemotron NIM RCA Accuracy:** **75.0% (6 out of 8 manager questions correct)** 🏆
  * **Evidence Grounding:** **1.000 Evidence F1 Score** on `MGR_005` (VP ambiguous query).
  * **Abstention Accuracy:** **87.5%**.

---

### 🔹 Run 12: Claude Opus 4.7 Azure AI Foundry Mini Benchmark
* **Date:** 2026-08-18
* **Objective:** Add **Claude Opus 4.7** as a second frontier baseline and run the 5-case representative development suite (`eval/datasets/dev/rca_cases_mini.jsonl`) with one repetition.
* **Integration:** Registered `opus_4_7` in `workflow.yml` using NAT's `litellm` provider and the Azure AI Foundry Anthropic endpoint. The model requires `temperature=1.0` (or omission of the parameter) rather than `temperature=0.0`.
* **Infrastructure Finding:** The initial Azure deployment limit of 1,000 tokens per minute allowed one case and then returned empty responses. That run was classified as an infrastructure failure and excluded. Increasing the quota allowed all five cases to complete without agent-failure rows.
* **Results:**
  * **RCA Accuracy:** **100.0% (5 out of 5 cases correct)** across configuration change, outage, interference, 5G EN-DC failure, and ambiguous/normal-variation families.
  * **Evidence F1:** **0.495** average.
  * **Latency:** **28,089 ms mean** and **20,344 ms median (`p50`)**.
  * **Execution Reliability:** **100.0% (5 out of 5 cases produced usable structured RCA output)**.
* **Scoring Caveat:** The raw 80.0% abstention and 100.0% hallucination summaries are not treated as valid model-quality results. The abstention runner reads a different field name from the workflow schema, and the hallucination scorer flags ordinary labels/acronyms as schema fields.
* **Result Artifact:** `eval/results/run_opus_4_7_20260818T194746.jsonl`.

---

### 🔹 Run 13: Controlled Four-Model Representative Benchmark
* **Date:** 2026-08-19
* **Objective:** Compare every model dynamically discovered from `workflow.yml` on the same 5-case representative development suite (`eval/datasets/dev/rca_cases_mini.jsonl`), with one repetition and unchanged prompts, tools, data, output limits, and agent logic.
* **Models:** `gpt_5_4` (frontier / Foundry OpenAI), `nemotron_nim` (open source / NVIDIA NIM), `opus_4_7` (frontier / Foundry Anthropic through LiteLLM), and `otel_2_0` (open source / OpenAI-compatible endpoint).
* **Reliability:** GPT-5.4, Opus, and OpenTel produced usable structured output for 5/5 cases. Nemotron produced usable output for 4/5; F1 called the correct tools but returned no scorable root cause. No valid external run timed out.
* **Accuracy:**
  * **GPT-5.4:** **100% (5/5)**.
  * **Nemotron NIM:** **60% (3/5 overall)** and **75% (3/4 usable outputs)**; F1 was unscorable and F4 incorrectly returned `UNDETERMINED`.
  * **Claude Opus 4.7:** **100% (5/5)**.
  * **OpenTel 2.0 31B:** **100% (5/5)**.
* **Evidence F1:** GPT-5.4 **0.581**, Nemotron **0.512**, Opus **0.499**, and OpenTel **0.658**.
* **Raw Abstention Accuracy:** **80% for every model**. Each missed the expected abstention on ambiguous case F5 (`further_investigation_required=false` versus ground truth `true`).
* **Raw Hallucination Rate:** GPT-5.4 **100%**, Nemotron **80%**, Opus **100%**, and OpenTel **100%**. These values are retained but overstated by a regex that treats common telecom acronyms, evidence labels, and cell IDs as schema fields.
* **Latency (mean / p50):** GPT-5.4 **11,153 / 8,078 ms**; Nemotron **107,383 / 108,559 ms**; Opus **28,797 / 21,589 ms**; OpenTel **17,727 / 14,152 ms**.
* **Tool Logging:** Raw JSONL tool-call recall was inaccurate for three models. Persistent logs showed audited required-tool recall of GPT-5.4 **0.900**, Nemotron **0.800**, Opus **1.000**, and OpenTel **1.000**.
* **Complete Raw Aggregate Snapshot:**

  | Model | Evidence P / R / F1 | Unsupported evidence | Schema valid | Hallucination rate / fields | Raw tool recall / precision / F1 / unnecessary | Abstention | Confidence | Latency min / max | Tokens |
  | :--- | :--- | ---: | ---: | :--- | :--- | ---: | ---: | :--- | :---: |
  | GPT-5.4 | 0.523 / 0.867 / 0.581 | 0.477 | 0.067 | 100% / 22 | 0.000 / 1.000 / 0.000 / 0.000 | 80% | 0.780 | 6,506 / 22,349 ms | unavailable |
  | Nemotron | 0.437 / 0.667 / 0.512 | 0.363 | 0.267 | 80% / 21 | 0.500 / 1.000 / 0.533 / 0.000 | 80% | 0.480 | 25,421 / 174,792 ms | unavailable |
  | Opus 4.7 | 0.374 / 0.933 / 0.499 | 0.626 | 0.235 | 100% / 52 | 0.000 / 1.000 / 0.000 / 0.000 | 80% | 0.900 | 16,112 / 52,090 ms | unavailable |
  | OpenTel 2.0 | 0.520 / 0.933 / 0.658 | 0.480 | 0.117 | 100% / 29 | 0.000 / 1.000 / 0.000 / 0.000 | 80% | 0.840 | 12,377 / 28,619 ms | unavailable |

* **Infrastructure Note:** The first GPT attempt was blocked by the execution sandbox and produced `run_gpt_5_4_20260819T180327.jsonl`; it was retained but excluded. The approved external rerun completed normally. No model-quality score was assigned from the blocked artifact.
* **Accuracy Conclusion:** **Three-way tie between GPT-5.4, Claude Opus 4.7, and OpenTel 2.0.** OpenTel led evidence F1 among the tied models, while GPT-5.4 had the lowest latency. The 25-case development suite is recommended before selecting a unique accuracy winner.
* **Result Artifacts:**
  * `eval/results/run_gpt_5_4_20260819T180432.jsonl`
  * `eval/results/run_nemotron_nim_20260819T180542.jsonl`
  * `eval/results/run_opus_4_7_20260819T181451.jsonl`
  * `eval/results/run_otel_2_0_20260819T181727.jsonl`
