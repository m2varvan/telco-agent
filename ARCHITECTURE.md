# Architecture & System Design — Network Incident Triage Assistant

**Rogers — AI for Networks** | *NVIDIA NeMo Agent Toolkit (`nat`)*

---

## 1. Executive Summary & Overview

The **Network Incident Triage Assistant** is an agentic AI system designed to automate root cause analysis (RCA) for mobile network incidents across 4G LTE and 5G NSA domains.

Built on the **NVIDIA NeMo Agent Toolkit (`nat`)**, the system operates over synthetic telecom datasets mirroring real **Ericsson ENIQ (Ericsson Network IQ)** schemas (table names, PM counter semantics, CM configuration attributes, and alarm formats). It correlates evidence across performance management (PM), configuration management (CM), fault management (FM/Alarms), spatial topology, historical incident tickets, and technical SOP documentation.

```
                           ┌──────────────────────────────────┐
                           │   Incident Description (Query)   │
                           └────────────────┬─────────────────┘
                                            │
                                            ▼
                           ┌──────────────────────────────────┐
                           │        ORCHESTRATOR AGENT        │
                           │ (Nemotron Telco / Azure OpenAI)  │
                           └────────────────┬─────────────────┘
                                            │
        ┌───────────────────┬───────────────┼───────────────┬───────────────────┐
        ▼                   ▼               ▼               ▼                   ▼
 📊 LTE & 5G PM       🔧 CM Config     🚨 Alarms        🛰 Topology &       📚 Knowledge &
    Counters           Parameters       & Outages        Neighbours          SOP RAG
 (query_lte_kpi /   (query_cm_config) (query_alarm_ (query_neighbour_   (query_telecom_
  query_nr_endc)                        history)        topology)          knowledge)
        │                   │               │               │                   │
        └───────────────────┴───────┬───────┴───────────────┴───────────────────┘
                                    │
                                    ▼
                      ┌───────────────────────────┐
                      │   STRUCTURED RCA RESULT   │
                      │  (Root Cause + Evidence   │
                      │  + Confidence + Action)   │
                      └───────────────────────────┘
```

---

## 2. Complete Tool Catalog & Diagnostic Responsibilities

The agent dynamically selects and executes tools based on incident symptoms. The system includes **8 specialized tools**:

### Core Diagnostic Tools (Data Domains)

1. **`query_lte_kpi`**

   - **Purpose:** Queries raw 4G LTE PM counters (`dc_e_erbs_eutrancellfdd_day`) and computes 5 Ericsson KPIs: Accessibility (E-RAB setup success rate %), Retainability (E-RAB % lost), DL Throughput (kbps), Cell Availability (%), and DL Latency (ms). Compares values against historical median baselines.
   - **When invoked:** First-line tool for any 4G LTE incident.
2. **`query_nr_endc`**

   - **Purpose:** Queries 5G NR counters (`dc_e_nr_nrcellcu_day`) and computes 5G EN-DC Setup Success Rate (%) and NR random access failure counts (`pmEndcSetupFailNrRa`).
   - **When invoked:** First-line tool for 5G NSA / EN-DC incidents.
3. **`query_cm_config`**

   - **Purpose:** Queries physical and logical configuration parameter history (`dc_e_bulk_cm_eutrancellfdd_raw`) over a lookback window (e.g. `ADMINISTRATIVESTATE`, `CELLBARRED`, `DLCHANNELBANDWIDTH`, `FREQBAND`, coordinates).
   - **When invoked:** When Accessibility, DL Throughput, or Latency degrades to check for human/automated parameter changes.
4. **`query_alarm_history`**

   - **Purpose:** Queries cell downtime counters (`PMCELLDOWNTIMEAUTO/MAN`) and active fault alarm records (`alarm_name`, `severity`, `start/end time`, `description`).
   - **When invoked:** When Cell Availability degrades or cell goes completely down (0%).

### Advanced Reasoning & Contextual Tools

5. **`query_neighbour_topology`**

   - **Purpose:** Computes co-site sectors (same eNodeB) and spatial neighbour cells within a geographic radius ($R$ km) using Haversine distance math on `LATITUDE`/`LONGITUDE`.
   - **When invoked:** When evaluating multi-cell degradation or neighbour interference (e.g. INC-3).
6. **`query_kpi_trend`**

   - **Purpose:** Queries 14-day time-series KPI trends from DuckDB. Calculates daily values, slope, and classifies the drop trajectory (`step_drop` vs `gradual_decline` vs `stable`).
   - **When invoked:** To differentiate between sudden step-function failures (config/outage) and gradual capacity congestion.
7. **`query_similar_incidents`**

   - **Purpose:** Searches historical resolution tickets in `sample_data/incident_history.csv` for past failures on the target cell or root cause category, returning past engineer resolution notes.
   - **When invoked:** To cross-reference past fix actions and recommended next steps.
8. **`query_telecom_knowledge` (2026 Hybrid RAG Engine)**

   - **Purpose:** Executes multi-stage hybrid RAG over [Key Performance Indicators.pdf](<file:///Users/abdullahalamaan/Documents/Github/telco-agent/sample_data/Key%20Performance%20Indicators.pdf>) and markdown playbooks in `sample_data/`.
   - **Architecture:** 4-Stage Pipeline: Multi-Query Expansion → Hybrid Sparse BM25 + Dense Vector Similarity → Reciprocal Rank Fusion (RRF) → PM Counter & Heading Exact Re-Ranking.
   - **When invoked:** To cite standard operating procedures, counter definitions, and technical recommendations in the RCA output.

---

## 3. Key Architectural Decisions & Technical Rationale

### Decision 1: Single Orchestrator Agent over Multi-Agent Router

- **Rationale:** With 8 specialist tools, a single orchestrator maintaining conversation state and evidence context outperforms a separate classifier router. A router introduces extra latency and cannot easily re-query specialists when evidence is inconclusive.

### Decision 2: Pure-Function KPI Calculation Engine (`KPICalculator`)

- **Rationale:** LLMs are prone to arithmetic errors when computing complex ratio formulas (e.g., product of 3 ratios with reattempt subtractions). All KPI formulas are executed deterministically in Python ([kpi_calculator.py](file:///Users/abdullahalamaan/Documents/Github/telco-agent/agent_tools/kpi_calculator.py)) with divide-by-zero protection.

### Decision 3: Standard Function-Calling with Resilient ReAct Fallback

- **Rationale:** [main.py](file:///Users/abdullahalamaan/Documents/Github/telco-agent/main.py) attempts `tool_calling_agent` first (fastest, standard OpenAI tool-calling protocol). If an endpoint times out or fails, it automatically falls back to a text-based `react_agent` loop, ensuring zero crash rate in production.

### Decision 4: Schema-Faithful Synthetic Data Layer with DuckDB

- **Rationale:** All CSV files reuse exact Ericsson ENIQ column names (`EUTRANCELLFDD`, `NRCellCU`, `PMCELLDOWNTIMEAUTO`, `ADMINISTRATIVESTATE`). When transitioning from synthetic prototypes to production, DuckDB queries against CSVs are replaced with DuckDB/Spark SQL views over live ENIQ tables without changing agent prompts.

### Decision 5: 4-Stage 2026 Advanced Hybrid RAG Pipeline Architecture (`rag_pipeline.py`)

- **Rationale:** Technical PDF manuals like [Key Performance Indicators.pdf](<file:///Users/abdullahalamaan/Documents/Github/telco-agent/sample_data/Key%20Performance%20Indicators.pdf>) contain both exact alphanumeric PM counters (e.g. `PMRRCCONNESTABSUCC`) and natural language explanations. A simple vector search misses exact counter names, while a keyword search misses conceptual queries.
  - **Stage 1 (Query Expansion):** Generates 3 query variations for acronyms and counter codes.
  - **Stage 2 (Hybrid Search):** Combines Sparse BM25 (`rank_bm25`) for exact counter tokens + Dense TF-IDF Vector Embeddings for conceptual match.
  - **Stage 3 (Reciprocal Rank Fusion - RRF):** Merges ranks via $RRF(d) = \sum \frac{1}{60 + r(d)}$.
  - **Stage 4 (Exact Re-Ranking):** Boosts exact PM counter and section heading matches.

---

## 4. System File Map

```
telco-agent/
├── ARCHITECTURE.md                    # Root system architecture document
├── main.py                            # Interactive CLI & resilient fallback runner
├── workflow.yml                       # NAT workflow & tool registration manifest
├── agent_tools/
│   ├── kpi_calculator.py              # Pure-function Ericsson KPI formula engine
│   └── tools/
│       ├── query_lte_kpi.py           # 4G LTE PM counters tool
│       ├── query_nr_endc.py           # 5G NSA EN-DC setup tool
│       ├── query_cm_config.py         # CM parameter change log tool
│       ├── query_alarm_history.py     # Fault & downtime alarm tool
│       ├── query_neighbour_topology.py# Spatial & co-site topology tool
│       ├── query_kpi_trend.py         # 14-day time-series trend tool
│       ├── query_similar_incidents.py # Historical ticket lookup tool
│       └── query_telecom_knowledge.py # RAG SOP & Knowledge search tool
├── sample_data/
│   ├── generate_synthetic_data.py    # Time-locked synthetic dataset generator
│   ├── lte_kpi_sample.csv             # 4G LTE daily PM dataset
│   ├── nr_endc_sample.csv             # 5G NR daily PM dataset
│   ├── cm_config_sample.csv           # CM config parameter dataset
│   ├── alarm_history.csv              # Alarm history log
│   ├── incident_history.csv           # Historical ticket log
│   └── telecom_knowledge.md           # RAG SOP knowledge base
├── eval/
│   ├── runner/run_agent_eval.py       # Benchmark evaluation runner
│   ├── datasets/                      # Dev & Test ground-truth datasets
│   └── scorers/                       # Deterministic & semantic evaluators
└── tests/                             # Unit & property test suite (pytest)
```
