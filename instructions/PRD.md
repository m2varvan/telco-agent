**Product Requirements Document**

Network Incident Triage Assistant

*Multi-Agent RCA System + Frontier-vs-Open-Source Evaluation Harness*

Built on NVIDIA NeMo Agent Toolkit + Nemotron Telco

Synthetic data modelled on Ericsson ENIQ schema

Rogers — AI for Networks | Version 1.0 | July 2026

# Table of Contents

# 1. Document Control & Summary

| **Field** | **Value** |
| --- | --- |
| Product | Network Incident Triage Assistant (agentic RCA prototype) |
| Owner | Abdullah Amaan (Network AI Intern) |
| Sponsors | Neel Dayal (manager), Muhammad Varvani, Ezgi Yagci, Lihai Wang |
| Program | Rogers — AI for Networks |
| Frameworks | NVIDIA NeMo Agent Toolkit; NVIDIA Open Nemotron Telco reasoning model |
| Data | Synthetic CSVs using real Ericsson ENIQ table & column names |
| Status | Draft v1.0 — foundations / evaluation harness |

**Purpose of this PRD**

This document defines the foundations for two coupled deliverables: (1) an agentic Network Incident Triage Assistant that performs automated root-cause analysis over telecom data, and (2) an evaluation harness that benchmarks frontier (commercial) models against open-source models on an identical, telecom-realistic dataset. The dataset deliberately reuses the real ENIQ schema (table names, PM counter names, CM parameter names) so that findings on model capability transfer directly when the agent is later connected to live ENIQ/OSS/Splunk platforms.

# 2. Background & Problem Statement

Rogers network operations teams triage incidents by manually correlating three data domains: historical alarms, performance KPIs, and recent configuration changes. This is slow, expert-dependent, and inconsistent. The AI for Networks initiative is evaluating whether open-source AI (NVIDIA Nemotron Telco + NeMo Agent Toolkit) can automate this triage at materially lower cost than commercial LLM APIs while preserving accuracy.

Two questions must be answered together:

1. Capability — Can an agentic system reason over real telecom schemas (ENIQ tables, PM counters, CM parameters), select the right diagnostic tools, correlate evidence, and produce a defensible RCA?
2. Economics — When frontier and open-source models run the exact same tasks on the exact same data, where does open-source fall short, and is the accuracy gap acceptable given the cost/hosting trade-off?

**Design principle**

The evaluation dataset must not be simplified into friendly table names (e.g. "cell\_kpis"). It must mirror production ENIQ artefacts so the benchmark measures the ability to understand telecom-specific terminology, counter semantics, denominators, joins, and cell hierarchy — the same skills required against the live platform.

# 3. Goals, Non-Goals & Success Criteria

## 3.1 Goals

* Deliver a working orchestrator + specialist sub-agents prototype on the NeMo Agent Toolkit.
* Perform automated triage on a small set of predefined incident scenarios using synthetic data.
* Produce an RCA output that includes: identified root cause, supporting evidence across ≥2 data sources, a confidence indicator, and a 'further investigation required' flag.
* Ship a reproducible evaluation harness with a fixed, versioned dataset and deterministic scoring.
* Benchmark ≥1 frontier model vs ≥1 open-source model (incl. Nemotron Telco) on identical tasks.
* Document cost, infrastructure, and build-vs-buy implications.

## 3.2 Non-Goals (for v1)

* No connection to live ENIQ / OSS / Splunk (foundations only; schema-faithful synthetic data instead).
* No production-grade dashboarding or ticketing integration.
* No fine-tuning of the base models; prompt + tool orchestration only.
* No attempt to model every ENIQ table — a curated subset covering KPI, CM, alarm/availability, and knowledge.

## 3.3 Success Criteria

| **#** | **Criterion** | **Target** |
| --- | --- | --- |
| S1 | Functional agent prototype on NeMo Agent Toolkit | Runs end-to-end on all defined scenarios |
| S2 | Automated investigation on synthetic data | Correct RCA on ≥ 80% of scripted incidents |
| S3 | Evidence-based explanation | Cites correct tables/counters in ≥ 80% of runs |
| S4 | Frontier vs open-source comparison | Quantified accuracy + cost delta per task tier |
| S5 | Transferability | Same schema/counters as live ENIQ; zero renamed fields |

# 4. System Architecture

A single orchestrator agent owns reasoning and control flow. It dynamically decides which specialist sub-agents/tools to invoke, in what order, and how many times, then correlates their outputs into an RCA. A separate router is intentionally omitted for v1 — with four specialists the orchestrator's own reasoning performs the routing; a router only becomes useful at 10+ specialists or when cheap pre-classification is needed.

┌──────────────────────────┐

Incident ───────▶ │ ORCHESTRATOR │

(natural language) │ (Nemotron Telco / LLM) │

│ plan → call → correlate │

└────────────┬─────────────┘

┌───────────────┬───────────┼───────────────┐

▼ ▼ ▼ ▼

┌───────────┐ ┌───────────┐ ┌──────────┐ ┌──────────────┐

│ KPI Agent │ │ CM/Config │ │ Alarm/ │ │ Knowledge │

│ (ENIQ PM) │ │ Agent │ │ Avail. │ │ Agent (RAG) │

└───────────┘ └───────────┘ └──────────┘ └──────────────┘

│ │ │ │

└──────────────┴─────┬──────┴──────────────┘

▼

RCA: root cause + evidence + confidence

## 4.1 Why orchestrator, not router

| **Aspect** | **Router** | **Orchestrator (chosen)** |
| --- | --- | --- |
| Job | Classify → forward to ONE agent | Plan, call many agents, re-call, synthesise |
| State | Stateless switch | Maintains investigation state / evidence |
| Fit | Chatbot with distinct skills | Multi-source RCA — needs correlation |
| v1 decision | Not needed | Handles routing implicitly via reasoning |

# 5. Agent Specifications

## 5.1 Orchestrator Agent

*Model: Nemotron Telco (open-source arm) or frontier model (eval arm). Owns the investigation loop.*

**Responsibilities:**

* Parse the incident and identify the target cell(s), site, time window.
* Decide which specialists to call and in what order.
* Re-invoke specialists when evidence is inconclusive.
* Correlate signals across KPI + CM + Alarm domains.
* Emit structured RCA: {root\_cause, evidence[], confidence, needs\_further\_investigation}.

## 5.2 KPI Agent

*Queries synthetic PM-counter tables and computes KPIs exactly as defined in the Ericsson KPI guide (formulas in §7).*

**Backing tables (real ENIQ names):**

* dc\_e\_erbs\_eutrancellfdd\_day / \_raw — LTE FDD cell counters
* dc\_e\_erbs\_eutrancelltdd\_day / \_raw — LTE TDD cell counters
* dc\_e\_nr\_nrcelldu\_day / \_raw — 5G NR-DU counters
* dc\_e\_nr\_nrcellcu\_day / \_raw — 5G NR-CU counters (EN-DC / NSA)
* lte\_peak\_hour\_user\_cell\_fact — peak-hour active users per cell

Sample questions it must answer: 'Did accessibility drop on cell X in the incident window?', 'What is DL throughput vs the 7-day baseline?', 'Which cells have EN-DC setup success below 90%?'

## 5.3 CM / Configuration Agent

*Queries synthetic configuration-management tables to find recent parameter changes and static cell attributes (band, bandwidth, coordinates, admin state).*

**Backing tables (real ENIQ names):**

* dc\_e\_bulk\_cm\_eutrancellfdd\_raw — LTE cell CM parameters
* dc\_e\_bulk\_cm\_nrsectorcarrier\_raw — NR sector-carrier CM parameters
* dim\_e\_lte\_erbs, dim\_e\_lte\_eucell\_cell — inventory / hierarchy
* erp\_sector\_info\_csv9 — sector metadata

Key fields it reasons over: ADMINISTRATIVESTATE, CELLBARRED, FREQBAND, EARFCNDL/EARFCNUL, DLCHANNELBANDWIDTH, MAXIMUMTRANSMISSIONPOWER, CELLRANGE, LATITUDE, LONGITUDE, plus a synthetic change-history (parameter, old\_value, new\_value, change\_time, engineer).

## 5.4 Alarm / Availability Agent

*Correlates outage/alarm history with cell availability. Availability is derived from real downtime counters; alarm history is synthetic but schema-plausible.*

**Backing data:**

* Availability counters: pmCellDowntimeAuto, pmCellDowntimeMan (in the cell KPI tables)
* Synthetic alarm log: alarm\_id, cell\_id / EUTRANCELLFDD, alarm\_name, severity, start\_time, end\_time, status
* Example alarms: Cell Outage, Backhaul Link Down, Power Failure, High Interference

## 5.5 Knowledge Agent (RAG)

*Retrieval over the Ericsson KPI User Guide and a telecom glossary so the agent can define counters/KPIs and justify its reasoning (e.g. 'what does EN-DC accessibility mean?', 'what causes high abnormal E-RAB release?'). Sources: Key Performance Indicators guide, ENIQ schema descriptions, RCA playbooks.*

# 6. Synthetic Data Model (Schema-Faithful)

All synthetic CSVs reuse the exact ENIQ table and column names below so that model capability measured here transfers to the live platform. Only the values are synthetic; names, types, and join keys are real.

## 6.1 Common keys present on every fact table

| **Column** | **Type** | **Meaning** |
| --- | --- | --- |
| OSS\_ID | String | Source OSS instance (e.g. eniq\_oss\_1) |
| ENODEBFUNCTION | String | eNodeB / node identifier |
| EUTRANCELLFDD / EUTRANCELLTDD | String | LTE cell identifier (join key) |
| NRCELLDU / NRCELLCU | String | 5G NR cell identifier |
| YEAR\_ID, MONTH\_ID, DAY\_ID | Integer | Date partition keys |
| HOUR\_ID, MIN\_ID | Integer | Intra-day time keys |
| DATETIME\_ID / UTC\_DATETIME\_ID | Timestamp | Exact ROP timestamp |
| PERIOD\_DURATION | Long | ROP length (seconds) |

## 6.2 Curated table set for v1

| **Domain** | **ENIQ table** | **Used for** | **Agent** |
| --- | --- | --- | --- |
| LTE KPI | dc\_e\_erbs\_eutrancellfdd\_day | Accessibility, retainability, thp, latency, availability | KPI |
| LTE KPI | dc\_e\_erbs\_eutrancelltdd\_day | Same, TDD carriers | KPI |
| 5G KPI | dc\_e\_nr\_nrcelldu\_day | NR cell performance | KPI |
| 5G KPI | dc\_e\_nr\_nrcellcu\_day | EN-DC / NSA setup success | KPI |
| Users | lte\_peak\_hour\_user\_cell\_fact | Peak-hour active users | KPI |
| CM | dc\_e\_bulk\_cm\_eutrancellfdd\_raw | LTE config + coordinates | CM |
| CM | dc\_e\_bulk\_cm\_nrsectorcarrier\_raw | NR sector-carrier config | CM |
| Inventory | dim\_e\_lte\_erbs / dim\_e\_lte\_eucell\_cell | Cell↔site hierarchy | CM |
| Alarm | (synthetic) network\_alarms | Outage/alarm history | Alarm |
| Time | dim\_date / dim\_time | Date/time dimension joins | All |

# 7. KPI Catalogue (Ericsson-accurate)

These are the KPIs the KPI Agent must compute, taken directly from the Key Performance Indicators guide. Formulas are expressed by their PM counters; keep units and denominators exactly as documented.

## 7.1 Accessibility — Initial E-RAB Establishment Success Rate

Ratio of successful RRC + S1-signalling + E-RAB initial establishment vs attempts. Beneficial trend: rising. Level: EUtranCell.

**Primary counters:**

pmRrcConnEstabSucc, pmRrcConnEstabAtt, pmRrcConnEstabAttReatt

pmS1SigConnEstabSucc, pmS1SigConnEstabAtt

pmErabEstabSuccInit, pmErabEstabAttInit

Success rate ≈ (RRC succ / RRC att) × (S1 succ / S1 att) × (E-RAB init succ / E-RAB init att), with reattempts subtracted from attempts per the guide.

## 7.2 Retainability — E-RAB Retainability, % Lost (eNB-triggered)

Share of abnormal E-RAB releases. Beneficial trend: falling.

pmErabRelAbnormalEnbQci, pmErabRelNormalEnbQci, pmErabRelMmeQci

## 7.3 Integrity — DL/UL Throughput & Latency

Filtered MBB UE DL/UL PDCP throughput and DL PDCP DRB latency per QCI.

Throughput: pmUeThpDlMbbFiltered2Distr, pmUeExclThpDlShortDrb2 (per percentile)

Latency: pmPdcpLatTimeDlQci / pmPdcpLatPktTransDlQci

## 7.4 Availability — Cell Availability

Uptime derived from downtime counters over the ROP window.

Availability % = 1 − (pmCellDowntimeAuto + pmCellDowntimeMan) / period

## 7.5 5G — EN-DC (NSA) Accessibility / Setup Success

5G NSA attach success — key for incidents on dual-connectivity cells.

EN-DC setup success % = pmEndcSetupUeSucc / pmEndcSetupUeAtt

Related: pmEndcSetupFailNrRa, pmEndcSetupScgUeSucc/Att, pmEndcCapableUe

## 7.6 Mobility — Handover Execution Success Rate

Successful intra/inter-frequency handover executions vs attempts (EUtranCell level, beneficial trend rising).

**Rule: only KPIs whose full counter set exists in the synthetic tables are enabled. Any KPI with missing counters is dropped from the eval rather than approximated.**

# 8. Predefined Incident Scenarios

Each scenario is scripted into the synthetic data with a known ground-truth root cause so the RCA output can be scored deterministically.

| **ID** | **Scenario** | **Injected ground truth** | **Expected correlation** |
| --- | --- | --- | --- |
| INC-1 | KPI degradation after config change | ADMINISTRATIVESTATE / band param changed → accessibility drop | CM change\_time precedes KPI drop |
| INC-2 | Cell/site outage with alarm history | Backhaul Link Down alarm → availability collapse | pmCellDowntime spike aligns with alarm window |
| INC-3 | Neighbour degradation | High interference on adjacent cell → throughput loss | KPI drop on neighbours, no local config change |
| INC-4 | EN-DC accessibility drop | NR RA failures → pmEndcSetupFailNrRa rises | 5G setup success falls; LTE anchor healthy |

# 9. Evaluation Harness — Frontier vs Open-Source

The same fixed, versioned dataset and identical prompts/tasks are run against every model. Scoring is deterministic where possible (SQL correctness, KPI value match) and rubric-based for reasoning quality.

## 9.1 Task tiers

| **Tier** | **Capability tested** | **Example task** | **Scoring** |
| --- | --- | --- | --- |
| T1 | Schema understanding | Which table holds cell coordinates? Which field is OSS? | Exact match |
| T2 | KPI calculation | Compute EN-DC setup success for cell X | Numeric tolerance |
| T3 | Multi-table join | Coordinates for the 10 busiest cells | Row/set match |
| T4 | RCA reasoning | Given INC-1..4, name the root cause + evidence | Rubric + ground truth |
| T5 | SQL generation | Top 10 cells by avg connected users | Valid + correct tables/joins |

## 9.2 Metrics captured per model

* Task accuracy per tier (%)
* Schema/counter grounding accuracy (did it use the right table/counter?)
* Hallucinated field rate (references to non-existent columns)
* Tool-call correctness (right agent, right args)
* Tokens + latency + $ per task (cost arm)
* Self-hosting footprint for open-source (GPU/VRAM)

## 9.3 Candidate models

| **Arm** | **Models (indicative)** | **Hosting** |
| --- | --- | --- |
| Open-source | Nemotron Telco (large), plus a smaller Nemotron variant | Self-host on cloud GPU (Azure/GCP) |
| Frontier | Commercial API model(s) as accuracy ceiling | Vendor API |

# 10. Technical Stack & Interfaces

* Orchestration: NVIDIA NeMo Agent Toolkit (workflows, tools, sub-agents).
* Reasoning models: Nemotron Telco (open) + frontier API (eval baseline).
* Data layer: synthetic CSVs in the ENIQ schema; queried via SQL (DuckDB/Spark-compatible) to mirror future ENIQ SQL.
* RAG: vector store over KPI guide + glossary for the Knowledge Agent.
* Eval runner: scripted task suite + deterministic scorers + cost logger.
* Future connectors (out of scope v1): live ENIQ, OSS, Splunk.

# 11. Milestones & Phasing

| **Phase** | **Deliverable** | **Exit criteria** |
| --- | --- | --- |
| P0 Foundations | Schema-faithful synthetic datasets + KPI formulas wired | Data validates; KPIs compute correctly |
| P1 Agents | KPI, CM, Alarm, Knowledge sub-agents on NeMo | Each agent answers its domain questions |
| P2 Orchestration | Orchestrator correlates ≥2 sources | INC-1..4 produce correct RCA |
| P3 Eval | Harness + frontier vs open-source run | Accuracy + cost deltas per tier |
| P4 Report | Findings + build-vs-buy recommendation | Reviewed with Neel / Muhammad / Ezgi |

# 12. Risks & Mitigations

| **Risk** | **Impact** | **Mitigation** |
| --- | --- | --- |
| Nemotron Telco too large to self-host cheaply | High | Benchmark smaller variant; quantify GPU cost in eval |
| Synthetic data not realistic enough | Med | Keep real counters/joins; script plausible distributions |
| Open-source hallucinates ENIQ fields | Med | Measure hallucinated-field rate; add schema grounding prompt |
| Scope creep (too many tables) | Med | Freeze curated table set in §6.2 |
| Scoring subjectivity on RCA | Low | Ground-truth injected per scenario + rubric |

# 13. Appendix A — Field Dictionary (selected)

## A.1 CM / config fields (dc\_e\_bulk\_cm\_eutrancellfdd\_raw)

| **Field** | **Type** | **Use in RCA** |
| --- | --- | --- |
| ADMINISTRATIVESTATE | Integer | Cell locked/unlocked — outage cause |
| CELLBARRED | Integer | Access barring — accessibility cause |
| FREQBAND | Integer | Band group for correlation |
| EARFCNDL / EARFCNUL | Integer | DL/UL carrier frequency |
| DLCHANNELBANDWIDTH | Integer | Bandwidth — throughput ceiling |
| MAXIMUMTRANSMISSIONPOWER | Integer | Power — coverage/interference |
| CELLRANGE | Integer | Coverage radius |
| LATITUDE / LONGITUDE | Integer | Cell coordinates (÷1e6) |
| EXPECTEDMAXNOOFUSERSINCELL | Integer | Capacity dimensioning |

## A.2 Key PM counters by KPI

| **KPI** | **Counters** |
| --- | --- |
| Accessibility | pmRrcConnEstabSucc/Att, pmS1SigConnEstabSucc/Att, pmErabEstabSuccInit/AttInit |
| Retainability | pmErabRelAbnormalEnbQci, pmErabRelNormalEnbQci, pmErabRelMmeQci |
| DL/UL Throughput | pmUeThpDlMbbFiltered2Distr, pmUeExclThpDlShortDrb2 |
| Latency | pmPdcpLatTimeDlQci, pmPdcpLatPktTransDlQci |
| Availability | pmCellDowntimeAuto, pmCellDowntimeMan |
| EN-DC (5G NSA) | pmEndcSetupUeSucc, pmEndcSetupUeAtt, pmEndcSetupFailNrRa |

*End of document — v1.0*