# Design Document — Network Incident Triage Assistant

## Overview

The Network Incident Triage Assistant (NAT) is an agentic Root-Cause Analysis (RCA) system built on
the NVIDIA NeMo Agent Toolkit. Given a natural-language incident description that names a target
cell, an OSS instance, and a time window, the system:

1. Parses and scopes the incident to concrete ENIQ join keys.
2. Queries raw PM-counter CSVs via DuckDB and computes six KPIs using Ericsson-specified formulas.
3. Compares each KPI against a per-cell baseline and flags degradations.
4. Selectively dispatches specialist tools (CM config, alarm/downtime, EN-DC) based on which KPIs
   are degraded.
5. Correlates evidence across at least two independent data domains.
6. Returns a structured JSON `RCA_Output` with `root_cause`, `evidence[]`, `confidence`, and
   `recommended_next_step`.

A separate evaluation harness benchmarks a frontier API model against the self-hosted Nemotron Telco
model on four scripted incident scenarios across five capability tiers.

### Design Principles

- **Single-orchestrator pattern**: one `react_agent` owns all reasoning and routing; no separate
  router process. This suits the four-specialist scope of v1.
- **Tools, not sub-agents**: specialist logic is implemented as plain Python functions registered as
  NAT `python_function` tools. This keeps the architecture flat, testable, and YAML-declarable.
- **Schema fidelity first**: every column name used in code must match the exact casing in the
  source CSV headers (e.g., `PMRRCCONNESTABSUCC`, `pmEndcSetupUeSucc`). No aliased friendly names.
- **DuckDB in-process**: queries run inside the Python process with no external database. DuckDB
  reads CSVs directly, enabling ENIQ-compatible SQL without a server.
- **Dual-LLM config**: `workflow.yml` declares two named LLM entries. The active model is selected
  by pointing `llm_name` at either entry or by overriding `.env` variables — no code change needed.

---

## Architecture

### High-Level Flow

```
User (CLI / main.py)
        │  incident description (string)
        ▼
┌─────────────────────────────────────────────────────────┐
│  Orchestrator Agent  (react_agent, workflow.yml)        │
│                                                         │
│  1. parse_incident  → scope: cell, oss_id, dates        │
│  2. query_lte_kpi   → raw counters + computed KPIs      │
│  3. query_nr_endc   → EN-DC counters + KPI              │
│  4. [if CM needed]  → query_cm_config                   │
│  5. [if outage]     → query_alarm_history               │
│  6. synthesise evidence → RCA_Output JSON               │
└─────────────────────────────────────────────────────────┘
         ▲              ▲              ▲              ▲
   query_lte_kpi  query_nr_endc  query_cm_config  query_alarm_history
   (Python fn)    (Python fn)    (Python fn)      (Python fn)
         │              │              │              │
      DuckDB         DuckDB         DuckDB         DuckDB (synthetic)
      lte_kpi        nr_endc        cm_config      alarm_history
      _sample.csv    _sample.csv    _sample.csv    (in-memory table)
```

### Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Sub-agent topology | Single orchestrator + 4 tool functions | Four specialists fit comfortably in an LLM's context; a router adds complexity without benefit at this scale |
| Data access layer | DuckDB in-process | Zero-server, ANSI SQL, reads CSVs directly; SQL syntax matches future ENIQ queries |
| KPI computation | Dedicated `kpi_calculator.py` module | Isolates formulas from LLM prompting; independently unit-testable |
| Tool registration | NAT `python_function` | Native NAT pattern; tools appear in `workflow.yml` and are auto-wrapped as LangChain tools |
| Prompt location | Inline `system_prompt` in `workflow.yml` | Keeps the entire agent definition in one declarable file |
| Eval harness | Standalone `eval/run_eval.py` | Fully decoupled from production code; runs against both LLM configurations |

---

## Components and Interfaces

### 1. Project File Layout

```
telco-agent/
├── main.py                        # Entry point — accepts incident string, prints RCA JSON
├── workflow.yml                   # NAT workflow + LLMs + tool declarations
├── .env                           # Runtime secrets (LLM keys, model names, data paths)
├── requirements.txt               # nvidia-nat[langchain], duckdb, python-dotenv, hypothesis
├── nat/
│   └── tools/
│       ├── __init__.py
│       ├── query_lte_kpi.py       # Tool: query LTE PM counters, invoke KPI_Calculator
│       ├── query_nr_endc.py       # Tool: query NR EN-DC counters, compute EN-DC KPI
│       ├── query_cm_config.py     # Tool: query CM config for parameter changes
│       └── query_alarm_history.py # Tool: query synthetic alarm/downtime history
├── nat/
│   └── kpi_calculator.py          # Pure-function KPI formula module (all 6 formulas)
├── sample_data/
│   ├── lte_kpi_sample.csv
│   ├── nr_endc_sample.csv
│   └── cm_config_sample.csv
├── eval/
│   ├── run_eval.py                # Evaluation harness entry point
│   ├── scenarios.py               # INC-1..4 scripted incident definitions + ground truth
│   ├── scorers.py                 # T1–T5 scoring functions
│   └── results/                   # Per-run JSON result files (gitignored)
└── .kiro/specs/telco-incident-triage-agent/
    ├── requirements.md
    └── design.md
```

### 2. workflow.yml Design

```yaml
functions:
  query_lte_kpi:
    _type: python_function
    module: nat.tools.query_lte_kpi
    function: query_lte_kpi
    description: >
      Query raw LTE PM counters from lte_kpi_sample.csv for a given cell, OSS instance,
      and date range. Computes Accessibility, Retainability, DL Throughput, Cell Availability,
      and DL PDCP DRB Latency using Ericsson formulas. Returns KPI values, baselines, and
      degradation flags. Arguments: cell_id (str), oss_id (str), year (int), month (int),
      day (int). Use EUTRANCELLFDD column names exactly as in the CSV header.

  query_nr_endc:
    _type: python_function
    module: nat.tools.query_nr_endc
    function: query_nr_endc
    description: >
      Query NR EN-DC PM counters from nr_endc_sample.csv for a given NRCellCU, OSS instance,
      and date. Computes EN-DC Setup Success Rate from pmEndcSetupUeSucc / pmEndcSetupUeAtt.
      Returns the rate, raw counter values, baseline, and degradation flag.
      Arguments: nr_cell_id (str), oss_id (str), year (int), month (int), day (int).

  query_cm_config:
    _type: python_function
    module: nat.tools.query_cm_config
    function: query_cm_config
    description: >
      Query cm_config_sample.csv for configuration changes on a given EUTRANCELLFDD cell
      within a specified date window. Returns a list of parameter changes (parameter name,
      old value, new value, DATETIME_ID). Use this when Accessibility, DL Throughput, or
      DL PDCP DRB Latency is degraded to check for preceding CM changes.
      Arguments: cell_id (str), oss_id (str), before_date (str ISO-8601), days_back (int).

  query_alarm_history:
    _type: python_function
    module: nat.tools.query_alarm_history
    function: query_alarm_history
    description: >
      Retrieve synthetic alarm records and downtime counter values for a cell on a given date.
      Returns alarm name, severity, start/end time, PMCELLDOWNTIMEAUTO, and PMCELLDOWNTIMEMAN.
      Use when Cell Availability is flagged as degraded.
      Arguments: cell_id (str), oss_id (str), year (int), month (int), day (int).

llms:
  frontier_llm:
    _type: openai
    model_name: ${FRONTIER_MODEL_NAME}
    api_key: ${FRONTIER_API_KEY}
    base_url: ${FRONTIER_BASE_URL}
    max_tokens: 4096
    temperature: 0.0

  nemotron_telco:
    _type: nim
    model_name: ${NIM_MODEL_NAME}
    api_key: ${LLM_API_KEY}
    base_url: ${LLM_BASE_URL}
    max_tokens: 4096
    temperature: 0.0

workflow:
  _type: react_agent
  llm_name: nemotron_telco          # swap to frontier_llm for eval comparison
  tool_names:
    - query_lte_kpi
    - query_nr_endc
    - query_cm_config
    - query_alarm_history
  system_prompt: |
    <SYSTEM_PROMPT_PLACEHOLDER — see Orchestrator System Prompt section>
  verbose: true
```

### 3. Tool Function Signatures and Implementations

#### 3.1 `query_lte_kpi` (`nat/tools/query_lte_kpi.py`)

```python
import duckdb
import os
from typing import Any
from nat.kpi_calculator import KPICalculator

LTE_CSV = os.getenv("LTE_KPI_CSV", "sample_data/lte_kpi_sample.csv")

def query_lte_kpi(
    cell_id: str,
    oss_id: str,
    year: int,
    month: int,
    day: int,
) -> dict[str, Any]:
    """
    Query raw LTE PM counters for (cell_id, oss_id, year, month, day) and return
    computed KPIs with baselines and degradation flags.

    Returns:
        {
          "cell_id": str,
          "date": {"year": int, "month": int, "day": int},
          "kpis_evaluated": [
              {
                "kpi": str,        # e.g. "Accessibility"
                "value": float | None,
                "baseline": float | None,
                "status": "ok" | "degraded" | "unavailable",
                "data_quality_flag": bool  # only present for Cell Availability
              },
              ...
          ],
          "raw_counters": dict   # the raw PM column values for traceability
        }
    """
    con = duckdb.connect()
    # Incident-day row
    row = con.execute(
        """
        SELECT * FROM read_csv_auto(?)
        WHERE EUTRANCELLFDD = ?
          AND OSS_ID = ?
          AND YEAR_ID = ? AND MONTH_ID = ? AND DAY_ID = ?
        """,
        [LTE_CSV, cell_id, oss_id, year, month, day],
    ).fetchone()

    if row is None:
        return {"error": f"No data found for cell {cell_id} on {year}-{month:02d}-{day:02d}"}

    cols = [desc[0] for desc in con.description]
    counters = dict(zip(cols, row))

    # Baseline rows (all prior days for this cell)
    prior_rows = con.execute(
        """
        SELECT * FROM read_csv_auto(?)
        WHERE EUTRANCELLFDD = ?
          AND OSS_ID = ?
          AND (YEAR_ID < ? OR (YEAR_ID = ? AND MONTH_ID < ?)
               OR (YEAR_ID = ? AND MONTH_ID = ? AND DAY_ID < ?))
        """,
        [LTE_CSV, cell_id, oss_id,
         year, year, month,
         year, month, day],
    ).fetchall()

    calc = KPICalculator()
    return calc.evaluate_lte(counters, prior_rows, cols)
```

#### 3.2 `query_nr_endc` (`nat/tools/query_nr_endc.py`)

```python
import duckdb
import os
from typing import Any
from nat.kpi_calculator import KPICalculator

NR_CSV = os.getenv("NR_ENDC_CSV", "sample_data/nr_endc_sample.csv")

def query_nr_endc(
    nr_cell_id: str,
    oss_id: str,
    year: int,
    month: int,
    day: int,
) -> dict[str, Any]:
    """
    Query NR EN-DC counters and compute EN-DC Setup Success Rate.

    Returns:
        {
          "nr_cell_id": str,
          "date": {"year": int, "month": int, "day": int},
          "kpis_evaluated": [
              {
                "kpi": "EN-DC Setup Success Rate",
                "value": float | None,
                "baseline": float | None,
                "status": "ok" | "degraded" | "unavailable"
              }
          ],
          "raw_counters": {
              "pmEndcSetupUeSucc": int | None,
              "pmEndcSetupUeAtt": int | None,
              "pmEndcSetupScgUeSucc": int | None,
              "pmEndcSetupScgUeAtt": int | None,
          }
        }
    """
    con = duckdb.connect()
    row = con.execute(
        """
        SELECT * FROM read_csv_auto(?)
        WHERE NRCellCU = ?
          AND OSS_ID = ?
          AND YEAR_ID = ? AND MONTH_ID = ? AND DAY_ID = ?
        """,
        [NR_CSV, nr_cell_id, oss_id, year, month, day],
    ).fetchone()

    if row is None:
        return {"error": f"No NR data found for cell {nr_cell_id}"}

    cols = [desc[0] for desc in con.description]
    counters = dict(zip(cols, row))

    prior_rows = con.execute(
        """
        SELECT * FROM read_csv_auto(?)
        WHERE NRCellCU = ?
          AND OSS_ID = ?
          AND (YEAR_ID < ? OR (YEAR_ID = ? AND MONTH_ID < ?)
               OR (YEAR_ID = ? AND MONTH_ID = ? AND DAY_ID < ?))
        """,
        [NR_CSV, nr_cell_id, oss_id,
         year, year, month,
         year, month, day],
    ).fetchall()

    calc = KPICalculator()
    return calc.evaluate_nr_endc(counters, prior_rows, cols)
```

#### 3.3 `query_cm_config` (`nat/tools/query_cm_config.py`)

```python
import duckdb
import os
from datetime import datetime, timedelta
from typing import Any

CM_CSV = os.getenv("CM_CONFIG_CSV", "sample_data/cm_config_sample.csv")

def query_cm_config(
    cell_id: str,
    oss_id: str,
    before_date: str,   # ISO-8601 date string: "2026-06-29"
    days_back: int = 7,
) -> dict[str, Any]:
    """
    Query cm_config_sample.csv for configuration changes on cell_id within the
    [before_date - days_back, before_date] window (inclusive).

    Returns:
        {
          "cell_id": str,
          "window": {"from": str, "to": str},
          "changes": [
              {
                "DATETIME_ID": str,
                "ADMINISTRATIVESTATE": int,
                "CELLBARRED": int,
                "FREQBAND": int,
                "EARFCNDL": int,
                "EARFCNUL": int,
                "DLCHANNELBANDWIDTH": int,
                "LATITUDE": float,
                "LONGITUDE": float,
              },
              ...
          ]
        }
    Joins on EUTRANCELLFDD + OSS_ID + DATETIME_ID only.
    """
    dt_to = datetime.fromisoformat(before_date)
    dt_from = dt_to - timedelta(days=days_back)

    con = duckdb.connect()
    rows = con.execute(
        """
        SELECT EUTRANCELLFDD, OSS_ID, DATETIME_ID,
               ADMINISTRATIVESTATE, CELLBARRED, FREQBAND,
               EARFCNDL, EARFCNUL, DLCHANNELBANDWIDTH,
               LATITUDE, LONGITUDE
        FROM read_csv_auto(?)
        WHERE EUTRANCELLFDD = ?
          AND OSS_ID = ?
          AND DATETIME_ID >= ?
          AND DATETIME_ID <= ?
        ORDER BY DATETIME_ID
        """,
        [CM_CSV, cell_id, oss_id, dt_from.isoformat(), dt_to.isoformat()],
    ).fetchall()

    cols = ["EUTRANCELLFDD", "OSS_ID", "DATETIME_ID",
            "ADMINISTRATIVESTATE", "CELLBARRED", "FREQBAND",
            "EARFCNDL", "EARFCNUL", "DLCHANNELBANDWIDTH",
            "LATITUDE", "LONGITUDE"]

    return {
        "cell_id": cell_id,
        "window": {"from": dt_from.isoformat(), "to": dt_to.isoformat()},
        "changes": [dict(zip(cols, r)) for r in rows],
    }
```

#### 3.4 `query_alarm_history` (`nat/tools/query_alarm_history.py`)

```python
import duckdb
import os
from typing import Any

LTE_CSV = os.getenv("LTE_KPI_CSV", "sample_data/lte_kpi_sample.csv")

# Synthetic alarm table is defined as an in-memory DuckDB table loaded from a
# Python constant (or a future CSV). Each record mirrors:
# {alarm_id, EUTRANCELLFDD, alarm_name, severity, start_time, end_time, status}
SYNTHETIC_ALARMS = [
    # Populated by eval/scenarios.py for scripted scenarios; empty by default.
]

def query_alarm_history(
    cell_id: str,
    oss_id: str,
    year: int,
    month: int,
    day: int,
) -> dict[str, Any]:
    """
    Retrieve downtime counters from lte_kpi_sample.csv AND any synthetic alarm
    records matching the given cell and date.

    Returns:
        {
          "cell_id": str,
          "PMCELLDOWNTIMEAUTO": int | None,
          "PMCELLDOWNTIMEMAN": int | None,
          "PERIOD_DURATION": int | None,
          "availability_pct": float | None,
          "alarms": [
              {
                "alarm_id": str,
                "alarm_name": str,
                "severity": str,
                "start_time": str,
                "end_time": str,
                "status": str,
              },
              ...
          ]
        }
    """
    con = duckdb.connect()
    row = con.execute(
        """
        SELECT PMCELLDOWNTIMEAUTO, PMCELLDOWNTIMEMAN, PERIOD_DURATION
        FROM read_csv_auto(?)
        WHERE EUTRANCELLFDD = ?
          AND OSS_ID = ?
          AND YEAR_ID = ? AND MONTH_ID = ? AND DAY_ID = ?
        """,
        [LTE_CSV, cell_id, oss_id, year, month, day],
    ).fetchone()

    downtime_auto = row[0] if row else None
    downtime_man  = row[1] if row else None
    period        = row[2] if row else None

    avail = None
    if downtime_auto is not None and downtime_man is not None and period:
        avail = 100.0 * (1 - (downtime_auto + downtime_man) / period)

    date_str = f"{year}-{month:02d}-{day:02d}"
    alarms = [
        a for a in SYNTHETIC_ALARMS
        if a["EUTRANCELLFDD"] == cell_id
        and a["start_time"][:10] == date_str
    ]

    return {
        "cell_id": cell_id,
        "PMCELLDOWNTIMEAUTO": downtime_auto,
        "PMCELLDOWNTIMEMAN": downtime_man,
        "PERIOD_DURATION": period,
        "availability_pct": avail,
        "alarms": alarms,
    }
```

---

## Data Models

### RCA_Output Schema

```python
from dataclasses import dataclass, field
from typing import Literal

@dataclass
class KPIResult:
    kpi: str                                         # "Accessibility", "Retainability", etc.
    value: float | None                              # computed numeric value
    baseline: float | None                           # per-cell median of prior days
    status: Literal["ok", "degraded", "unavailable"] # classification
    data_quality_flag: bool = False                  # True when availability capped at 100

@dataclass
class RCAOutput:
    incident: str                                    # original description
    kpis_evaluated: list[KPIResult]                  # one entry per KPI attempted
    root_cause: str                                  # ≤200 chars, single most-likely cause
    evidence: list[str]                              # strings citing actual CSV values
    confidence: Literal["high", "medium", "low"]
    further_investigation_required: bool
    recommended_next_step: str                       # names agent/source/counter to check
```

### KPI Computation Intermediate Types

```python
@dataclass
class CounterRow:
    """Typed view of one CSV row passed to KPICalculator."""
    EUTRANCELLFDD: str
    OSS_ID: str
    YEAR_ID: int; MONTH_ID: int; DAY_ID: int
    PERIOD_DURATION: int
    PMRRCCONNESTABSUCC: int | None
    PMRRCCONNESTABATT: int | None
    PMRRCCONNESTABATTREATT: int | None
    PMS1SIGCONNESTABSUCC: int | None
    PMS1SIGCONNESTABATT: int | None
    PMERABESTABSUCCINIT: int | None
    PMERABESTABATTINIT: int | None
    PMERABRELABNORMALENB: int | None
    PMERABRELNORMALENB: int | None
    PMPDCPVOLDLDRB: int | None
    PMPDCPVOLDLDRBLASTTTI: int | None
    PMUETHPTIMEDL: int | None
    PMCELLDOWNTIMEAUTO: int | None
    PMCELLDOWNTIMEMAN: int | None

@dataclass
class NRCounterRow:
    NRCellCU: str
    OSS_ID: str
    YEAR_ID: int; MONTH_ID: int; DAY_ID: int
    PERIOD_DURATION: int
    pmEndcSetupUeSucc: int | None
    pmEndcSetupUeAtt: int | None
    pmEndcSetupScgUeSucc: int | None
    pmEndcSetupScgUeAtt: int | None
```

### Scripted Incident Schema (`eval/scenarios.py`)

```python
@dataclass
class ScriptedIncident:
    id: str                              # "INC-1" .. "INC-4"
    description: str                     # natural-language input string
    ground_truth_root_cause_category: str # "config_change" | "outage" | "interference" | "endc"
    ground_truth_evidence_keywords: list[str]  # counter/param names that must appear in evidence
    injected_alarms: list[dict]          # added to SYNTHETIC_ALARMS before run
```

---

## `kpi_calculator.py` Module Design

This module contains only pure functions. No I/O, no LLM calls, no DuckDB. All six KPI formulas
plus baseline computation and degradation flagging live here so they can be tested in complete
isolation.

```python
# nat/kpi_calculator.py
from __future__ import annotations
import statistics
from typing import Any

# Degradation thresholds (constants for testability)
ACCESSIBILITY_ABSOLUTE_THRESHOLD  = 95.0    # below this → degraded
ACCESSIBILITY_RELATIVE_THRESHOLD  = 5.0     # pp below baseline → degraded
RETAINABILITY_THRESHOLD           = 2.0     # % lost above this → degraded
THROUGHPUT_RELATIVE_THRESHOLD     = 0.30    # 30% below baseline → degraded
AVAILABILITY_THRESHOLD            = 99.0    # below this → degraded
LATENCY_RELATIVE_THRESHOLD        = 0.30    # 30% above baseline → degraded
ENDC_THRESHOLD                    = 90.0    # below this → degraded


class KPICalculator:
    # ------------------------------------------------------------------ #
    #  Formula 1 — Accessibility (E-RAB Setup Success Rate)              #
    # ------------------------------------------------------------------ #
    def compute_accessibility(
        self,
        PMRRCCONNESTABSUCC: int | None,
        PMRRCCONNESTABATT: int | None,
        PMRRCCONNESTABATTREATT: int | None,
        PMS1SIGCONNESTABSUCC: int | None,
        PMS1SIGCONNESTABATT: int | None,
        PMERABESTABSUCCINIT: int | None,
        PMERABESTABATTINIT: int | None,
    ) -> float | None:
        """
        100 * (PMRRCCONNESTABSUCC / (PMRRCCONNESTABATT - PMRRCCONNESTABATTREATT))
              * (PMS1SIGCONNESTABSUCC / PMS1SIGCONNESTABATT)
              * (PMERABESTABSUCCINIT  / PMERABESTABATTINIT)
        Returns None if any denominator is zero or any input is None.
        """
        try:
            rrc_denom = PMRRCCONNESTABATT - PMRRCCONNESTABATTREATT
            if rrc_denom == 0 or PMS1SIGCONNESTABATT == 0 or PMERABESTABATTINIT == 0:
                return None
            return 100.0 * (
                (PMRRCCONNESTABSUCC / rrc_denom)
                * (PMS1SIGCONNESTABSUCC / PMS1SIGCONNESTABATT)
                * (PMERABESTABSUCCINIT  / PMERABESTABATTINIT)
            )
        except TypeError:
            return None

    # ------------------------------------------------------------------ #
    #  Formula 2 — Retainability (E-RAB % Lost)                         #
    # ------------------------------------------------------------------ #
    def compute_retainability(
        self,
        PMERABRELABNORMALENB: int | None,
        PMERABRELNORMALENB: int | None,
    ) -> float | None:
        """
        100 * (PMERABRELABNORMALENB / (PMERABRELABNORMALENB + PMERABRELNORMALENB))
        Returns None if denominator is zero or inputs are None.
        """
        try:
            denom = PMERABRELABNORMALENB + PMERABRELNORMALENB
            if denom == 0:
                return None
            return 100.0 * (PMERABRELABNORMALENB / denom)
        except TypeError:
            return None

    # ------------------------------------------------------------------ #
    #  Formula 3 — DL Throughput (kbps)                                 #
    # ------------------------------------------------------------------ #
    def compute_dl_throughput(
        self,
        PMPDCPVOLDLDRB: int | None,
        PMPDCPVOLDLDRBLASTTTI: int | None,
        PMUETHPTIMEDL: int | None,
    ) -> float | None:
        """
        (PMPDCPVOLDLDRB - PMPDCPVOLDLDRBLASTTTI) / PMUETHPTIMEDL
        Inputs in bits and milliseconds; result in kbps.
        Returns None if denominator is zero or inputs are None.
        """
        try:
            if PMUETHPTIMEDL == 0:
                return None
            return (PMPDCPVOLDLDRB - PMPDCPVOLDLDRBLASTTTI) / PMUETHPTIMEDL
        except TypeError:
            return None

    # ------------------------------------------------------------------ #
    #  Formula 4 — Cell Availability (%)                                 #
    # ------------------------------------------------------------------ #
    def compute_cell_availability(
        self,
        PMCELLDOWNTIMEAUTO: int | None,
        PMCELLDOWNTIMEMAN: int | None,
        PERIOD_DURATION: int | None,
    ) -> tuple[float | None, bool]:
        """
        100 * (1 - (PMCELLDOWNTIMEAUTO + PMCELLDOWNTIMEMAN) / PERIOD_DURATION)
        Capped at 100.0 if downtime > PERIOD_DURATION; sets data_quality_flag=True.
        Returns (value, data_quality_flag).
        """
        try:
            if PERIOD_DURATION == 0:
                return None, False
            raw = 100.0 * (1 - (PMCELLDOWNTIMEAUTO + PMCELLDOWNTIMEMAN) / PERIOD_DURATION)
            if raw > 100.0:
                return 100.0, True
            return raw, False
        except TypeError:
            return None, False

    # ------------------------------------------------------------------ #
    #  Formula 5 — DL PDCP DRB Latency (ms)                             #
    # ------------------------------------------------------------------ #
    def compute_dl_latency(
        self,
        PMPDCPLATTIMEDL: int | None,
        PMPDCPLATPKTTRANSDL: int | None,
    ) -> float | None:
        """
        (PMPDCPLATTIMEDL / PMPDCPLATPKTTRANSDL) / 10
        PMPDCPLATTIMEDL accumulates in 0.1 ms units; dividing by 10 gives ms.
        Returns None if denominator is zero or inputs are None.
        Note: these counters are not present in the current sample CSV;
              formula is wired and ready for when they are added.
        """
        try:
            if PMPDCPLATPKTTRANSDL == 0:
                return None
            return (PMPDCPLATTIMEDL / PMPDCPLATPKTTRANSDL) / 10.0
        except TypeError:
            return None

    # ------------------------------------------------------------------ #
    #  Formula 6 — EN-DC Setup Success Rate (%)                         #
    # ------------------------------------------------------------------ #
    def compute_endc_success_rate(
        self,
        pmEndcSetupUeSucc: int | None,
        pmEndcSetupUeAtt: int | None,
    ) -> float | None:
        """
        100 * (pmEndcSetupUeSucc / pmEndcSetupUeAtt)
        Returns None if denominator is zero or inputs are None.
        """
        try:
            if pmEndcSetupUeAtt == 0:
                return None
            return 100.0 * (pmEndcSetupUeSucc / pmEndcSetupUeAtt)
        except TypeError:
            return None

    # ------------------------------------------------------------------ #
    #  Baseline computation                                               #
    # ------------------------------------------------------------------ #
    def compute_baseline(self, prior_values: list[float]) -> float | None:
        """
        Median of prior_values. Returns None if list is empty.
        """
        if not prior_values:
            return None
        return statistics.median(prior_values)

    # ------------------------------------------------------------------ #
    #  Degradation flagging                                               #
    # ------------------------------------------------------------------ #
    def flag_degradation(
        self,
        kpi_name: str,
        value: float | None,
        baseline: float | None,
    ) -> str:
        """
        Returns "degraded", "ok", or "unavailable" per requirements §3.
        """
        if value is None:
            return "unavailable"

        if kpi_name == "Accessibility":
            if value < ACCESSIBILITY_ABSOLUTE_THRESHOLD:
                return "degraded"
            if baseline is not None and (baseline - value) > ACCESSIBILITY_RELATIVE_THRESHOLD:
                return "degraded"
            return "ok"

        if kpi_name == "Retainability":
            return "degraded" if value > RETAINABILITY_THRESHOLD else "ok"

        if kpi_name == "DL Throughput":
            if baseline is None:
                return "unavailable"
            return "degraded" if value < baseline * (1 - THROUGHPUT_RELATIVE_THRESHOLD) else "ok"

        if kpi_name == "Cell Availability":
            return "degraded" if value < AVAILABILITY_THRESHOLD else "ok"

        if kpi_name == "DL PDCP DRB Latency":
            if baseline is None:
                return "unavailable"
            return "degraded" if value > baseline * (1 + LATENCY_RELATIVE_THRESHOLD) else "ok"

        if kpi_name == "EN-DC Setup Success Rate":
            return "degraded" if value < ENDC_THRESHOLD else "ok"

        return "ok"
```

---

## Orchestrator System Prompt Design

The system prompt is embedded directly in `workflow.yml` under `workflow.system_prompt`. It has four
parts: identity, schema grounding, investigation protocol, and output contract.

```
You are the Network Incident Triage Assistant for Rogers — AI for Networks.
You have access to four tools: query_lte_kpi, query_nr_endc, query_cm_config, query_alarm_history.

=== IDENTITY ===
You perform automated Root Cause Analysis (RCA) on LTE and 5G NR network incidents.
You reason only from data returned by your tools. You never fabricate counter values,
column names, or KPI results.

=== SCHEMA GROUNDING ===
Use these EXACT column names — wrong casing = wrong query.

LTE KPI table (lte_kpi_sample.csv) join keys and PM counters:
  Join keys : EUTRANCELLFDD, OSS_ID, YEAR_ID, MONTH_ID, DAY_ID
  PM counters: PMRRCCONNESTABSUCC, PMRRCCONNESTABATT, PMRRCCONNESTABATTREATT,
               PMS1SIGCONNESTABSUCC, PMS1SIGCONNESTABATT,
               PMERABESTABSUCCINIT, PMERABESTABATTINIT,
               PMERABRELABNORMALENB, PMERABRELNORMALENB,
               PMPDCPVOLDLDRB, PMPDCPVOLDLDRBLASTTTI, PMUETHPTIMEDL,
               PMCELLDOWNTIMEAUTO, PMCELLDOWNTIMEMAN, PERIOD_DURATION

NR EN-DC table (nr_endc_sample.csv) join keys and PM counters:
  Join keys : NRCellCU, OSS_ID, YEAR_ID, MONTH_ID, DAY_ID
  PM counters: pmEndcSetupUeSucc, pmEndcSetupUeAtt,
               pmEndcSetupScgUeSucc, pmEndcSetupScgUeAtt

CM Config table (cm_config_sample.csv) join keys and parameters:
  Join keys : EUTRANCELLFDD, OSS_ID, DATETIME_ID
  Parameters: ADMINISTRATIVESTATE, CELLBARRED, FREQBAND,
              EARFCNDL, EARFCNUL, DLCHANNELBANDWIDTH, LATITUDE, LONGITUDE

=== INVESTIGATION PROTOCOL ===
Step 1 — SCOPE: Extract EUTRANCELLFDD (or NRCellCU or ENODEBFUNCTION), OSS_ID, and
  the incident date(s) from the description. Express each date as year/month/day integers.
  If any of these is missing or the cell is not found in the data, return a structured
  error immediately and stop.

Step 2 — KPI COMPUTATION: Call query_lte_kpi (and/or query_nr_endc for NR cells).
  Never skip this step. Never read a column named "Accessibility" or "Throughput" —
  KPIs are ALWAYS computed from raw PM counters.

Step 3 — SELECTIVE DISPATCH (based on degraded KPIs only):
  - Accessibility OR DL Throughput OR DL PDCP DRB Latency degraded →
      call query_cm_config with days_back=7 before first degraded DAY_ID
  - Cell Availability degraded →
      call query_alarm_history
  - EN-DC Setup Success Rate degraded →
      report pmEndcSetupUeSucc/pmEndcSetupUeAtt values; also call query_lte_kpi
      on the LTE anchor cell to check its Accessibility (must be >= 95% for
      NSA-layer isolation)
  - No KPIs degraded but symptom reported →
      call query_lte_kpi on all cells sharing the same ENODEBFUNCTION

Step 4 — EVIDENCE CORRELATION: Collect evidence from ≥2 distinct domains before
  setting confidence="high". Domains: (a) KPI counters, (b) CM config, (c) alarms.

Step 5 — OUTPUT: Return ONLY valid JSON conforming to the RCA_Output schema below.
  No prose outside the JSON object.

=== OUTPUT CONTRACT ===
Return exactly this JSON structure (all seven fields required):
{
  "incident": "<original description>",
  "kpis_evaluated": [
    {
      "kpi": "<name>",
      "value": <float or null>,
      "baseline": <float or null>,
      "status": "ok" | "degraded" | "unavailable"
    }
  ],
  "root_cause": "<single statement ≤200 characters>",
  "evidence": ["<string citing actual counter/value/table>", ...],
  "confidence": "high" | "medium" | "low",
  "further_investigation_required": true | false,
  "recommended_next_step": "<names agent/counter/source to investigate>"
}

Confidence rules:
  - high   → evidence from ≥2 distinct domains AND KPI degradation confirmed
  - medium → evidence from exactly 1 domain AND KPI degradation confirmed
  - low    → ambiguous, missing counters for >1 KPI, or no evidence collected

If counter data is absent, add "<COUNTER_NAME>: counter unavailable" to evidence.
Do NOT populate evidence with data not returned by a tool call.
```

---

## `main.py` Extension

```python
# main.py
import asyncio
import sys
import os
from dotenv import load_dotenv
from nat.builder.workflow_builder import WorkflowBuilder

load_dotenv()

_REQUIRED_VARS = ["LLM_MODEL_NAME", "LLM_API_KEY", "LLM_BASE_URL"]

def _validate_env() -> None:
    missing = [v for v in _REQUIRED_VARS if not os.getenv(v)]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Set them in .env before running."
        )

async def main(incident: str) -> str:
    _validate_env()
    workflow = WorkflowBuilder.from_config("workflow.yml").build()
    result = await workflow.run(incident)
    return result

if __name__ == "__main__":
    # Accept incident description from command-line args or stdin
    if len(sys.argv) > 1:
        incident_description = " ".join(sys.argv[1:])
    else:
        print("Enter incident description (press Enter when done):")
        incident_description = input().strip()

    if not incident_description:
        print("Error: incident description cannot be empty.")
        sys.exit(1)

    result = asyncio.run(main(incident_description))
    print(result)
```

Example invocations:

```bash
# From CLI arguments
python main.py "Cell BC5501XD on eniq_oss_1 showing poor accessibility on 2026-06-29"

# From stdin
echo "Cell BC5501XD on eniq_oss_1 showing poor accessibility on 2026-06-29" | python main.py
```

---

## Evaluation Harness Design (`eval/run_eval.py`)

### Scripted Scenarios (`eval/scenarios.py`)

```python
SCENARIOS = [
    ScriptedIncident(
        id="INC-1",
        description=(
            "Cell BC5501XD on eniq_oss_1 is showing a significant accessibility drop "
            "starting 2026-06-29. Please investigate."
        ),
        ground_truth_root_cause_category="config_change",
        ground_truth_evidence_keywords=["ADMINISTRATIVESTATE", "DLCHANNELBANDWIDTH", "DATETIME_ID"],
        injected_alarms=[],
    ),
    ScriptedIncident(
        id="INC-2",
        description=(
            "Cell W01AXB on eniq_oss_1 went completely unavailable on 2022-12-07. "
            "Possible outage. Please investigate."
        ),
        ground_truth_root_cause_category="outage",
        ground_truth_evidence_keywords=["PMCELLDOWNTIMEAUTO", "PMCELLDOWNTIMEMAN", "Backhaul Link Down"],
        injected_alarms=[{
            "alarm_id": "ALM-001",
            "EUTRANCELLFDD": "W01AXB",
            "alarm_name": "Backhaul Link Down",
            "severity": "Critical",
            "start_time": "2022-12-07T00:00:00Z",
            "end_time": "2022-12-07T06:00:00Z",
            "status": "cleared",
        }],
    ),
    ScriptedIncident(
        id="INC-3",
        description=(
            "Multiple cells on eNodeB 1 / eniq_oss_1 showing throughput degradation "
            "on 2026-06-29. No local config change suspected."
        ),
        ground_truth_root_cause_category="interference",
        ground_truth_evidence_keywords=["PMPDCPVOLDLDRB", "PMUETHPTIMEDL", "ENODEBFUNCTION"],
        injected_alarms=[],
    ),
    ScriptedIncident(
        id="INC-4",
        description=(
            "NR cell EPBNW on eniq_oss_1 reporting EN-DC setup failures on 2026-06-30. "
            "LTE anchor cell appears healthy."
        ),
        ground_truth_root_cause_category="endc",
        ground_truth_evidence_keywords=["pmEndcSetupUeSucc", "pmEndcSetupUeAtt"],
        injected_alarms=[],
    ),
]
```

### Scoring Functions (`eval/scorers.py`)

```python
import math

def score_t1(response: str, expected: str) -> int:
    """T1 Schema understanding — exact match (0 or 1)."""
    return 1 if expected.strip().lower() in response.strip().lower() else 0

def score_t2(computed: float | None, expected: float, tolerance: float = 0.01) -> int:
    """T2 KPI calculation — numeric tolerance ±0.01 pp or kbps/ms."""
    if computed is None:
        return 0
    return 1 if abs(computed - expected) <= tolerance else 0

def score_t3(result_rows: list[dict], expected_rows: list[dict], key: str) -> int:
    """T3 Multi-table join — set match on a key field (0 or 1)."""
    result_keys = {r[key] for r in result_rows}
    expected_keys = {r[key] for r in expected_rows}
    return 1 if result_keys == expected_keys else 0

def score_t4(rca_output: dict, ground_truth_category: str, evidence_keywords: list[str]) -> int:
    """
    T4 RCA reasoning — rubric score 0-3:
      3: root_cause matches category AND ≥1 evidence keyword found in evidence array
      2: root_cause matches category but no evidence keywords found
      1: root_cause does not match but evidence keywords found
      0: neither matches
    """
    rc_match = ground_truth_category.lower() in rca_output.get("root_cause", "").lower()
    evidence_str = " ".join(rca_output.get("evidence", []))
    ev_match = any(kw in evidence_str for kw in evidence_keywords)
    if rc_match and ev_match:
        return 3
    if rc_match:
        return 2
    if ev_match:
        return 1
    return 0

def score_t5(generated_sql: str, required_tables: list[str], required_joins: list[str]) -> int:
    """
    T5 SQL generation — valid SQL that references required tables and join keys.
    Returns 1 if all required_tables and required_joins appear in generated_sql, else 0.
    """
    sql_lower = generated_sql.lower()
    tables_ok = all(t.lower() in sql_lower for t in required_tables)
    joins_ok  = all(j.lower() in sql_lower for j in required_joins)
    return 1 if tables_ok and joins_ok else 0
```

### Harness Entry Point (`eval/run_eval.py`)

```python
# eval/run_eval.py
import asyncio
import hashlib
import json
import time
from pathlib import Path
from dotenv import load_dotenv
from nat.builder.workflow_builder import WorkflowBuilder
from eval.scenarios import SCENARIOS
from eval.scorers import score_t4

load_dotenv()

RESULTS_DIR = Path("eval/results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

CSV_FILES = [
    "sample_data/lte_kpi_sample.csv",
    "sample_data/nr_endc_sample.csv",
    "sample_data/cm_config_sample.csv",
]

def dataset_version() -> str:
    """SHA-256 of all three CSVs concatenated."""
    h = hashlib.sha256()
    for path in CSV_FILES:
        h.update(Path(path).read_bytes())
    return h.hexdigest()[:12]

async def run_scenario(workflow, scenario) -> dict:
    # Inject synthetic alarms before run
    import nat.tools.query_alarm_history as ah_module
    ah_module.SYNTHETIC_ALARMS = scenario.injected_alarms

    start = time.monotonic()
    raw_output = await workflow.run(scenario.description)
    elapsed = time.monotonic() - start

    try:
        rca = json.loads(raw_output)
    except json.JSONDecodeError:
        rca = {"root_cause": "", "evidence": [], "kpis_evaluated": []}

    t4_score = score_t4(
        rca,
        scenario.ground_truth_root_cause_category,
        scenario.ground_truth_evidence_keywords,
    )

    return {
        "scenario_id": scenario.id,
        "t4_score": t4_score,
        "correct": t4_score == 3,
        "latency_s": round(elapsed, 3),
        "rca": rca,
    }

async def run_eval(model_name: str, workflow_config: str = "workflow.yml") -> None:
    workflow = WorkflowBuilder.from_config(workflow_config).build()
    version = dataset_version()
    results = []

    for scenario in SCENARIOS:
        print(f"Running {scenario.id} ...")
        result = await run_scenario(workflow, scenario)
        results.append(result)
        print(f"  T4 score: {result['t4_score']}/3  correct: {result['correct']}")

    total = len(SCENARIOS)
    correct = sum(1 for r in results if r["correct"])
    accuracy_pct = (correct / total) * 100

    summary = {
        "model": model_name,
        "dataset_version": version,
        "rca_accuracy_pct": round(accuracy_pct, 1),
        "correct_count": correct,
        "total_count": total,
        "results": results,
    }

    out_file = RESULTS_DIR / f"{model_name.replace('/', '_')}_{version}.json"
    out_file.write_text(json.dumps(summary, indent=2))
    print(f"\nSummary written to {out_file}")
    print(f"RCA accuracy: {accuracy_pct:.1f}% ({correct}/{total})")

if __name__ == "__main__":
    import sys
    model = sys.argv[1] if len(sys.argv) > 1 else "nemotron_telco"
    asyncio.run(run_eval(model))
```

---

## `.env` Schema

```bash
# ── Active LLM (read by workflow.yml via ${} substitution) ──────────────────
# Required — raise EnvironmentError if absent
LLM_MODEL_NAME=nvidia/nemotron-telco-reasoning-70b-instruct
LLM_API_KEY=nvapi-xxxxxxxxxxxxxxxxxxxxxxxxxxxx
LLM_BASE_URL=https://integrate.api.nvidia.com/v1

# ── Frontier LLM (eval comparison arm) ───────────────────────────────────────
FRONTIER_MODEL_NAME=gpt-4o
FRONTIER_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxx
FRONTIER_BASE_URL=https://api.openai.com/v1

# ── Data paths (optional overrides; defaults shown) ─────────────────────────
LTE_KPI_CSV=sample_data/lte_kpi_sample.csv
NR_ENDC_CSV=sample_data/nr_endc_sample.csv
CM_CONFIG_CSV=sample_data/cm_config_sample.csv
```

Variable roles:

| Variable | Required | Used by |
|----------|----------|---------|
| `LLM_MODEL_NAME` | Yes | `workflow.yml` `nemotron_telco` LLM entry |
| `LLM_API_KEY` | Yes | `workflow.yml` `nemotron_telco` LLM entry |
| `LLM_BASE_URL` | Yes | `workflow.yml` `nemotron_telco` LLM entry |
| `FRONTIER_MODEL_NAME` | No (eval only) | `workflow.yml` `frontier_llm` entry |
| `FRONTIER_API_KEY` | No (eval only) | `workflow.yml` `frontier_llm` entry |
| `FRONTIER_BASE_URL` | No (eval only) | `workflow.yml` `frontier_llm` entry |
| `LTE_KPI_CSV` | No | `query_lte_kpi.py`, `query_alarm_history.py` |
| `NR_ENDC_CSV` | No | `query_nr_endc.py` |
| `CM_CONFIG_CSV` | No | `query_cm_config.py` |

`main.py` enforces that `LLM_MODEL_NAME`, `LLM_API_KEY`, and `LLM_BASE_URL` are non-empty at
workflow build time, raising `EnvironmentError` with the missing variable name(s) if not.

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a
system — essentially, a formal statement about what the system should do. Properties serve as the
bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Accessibility formula output in range

*For any* non-null counter tuple with non-zero denominators
(`PMRRCCONNESTABATT - PMRRCCONNESTABATTREATT > 0`, `PMS1SIGCONNESTABATT > 0`,
`PMERABESTABATTINIT > 0`), `compute_accessibility` SHALL return a value in the closed interval
[0.0, 100.0].

**Validates: Requirements 2.1, 12.1**

---

### Property 2: Retainability formula output in range

*For any* non-null counter tuple where `PMERABRELABNORMALENB + PMERABRELNORMALENB > 0`,
`compute_retainability` SHALL return a value in [0.0, 100.0].

**Validates: Requirements 2.2, 12.1**

---

### Property 3: EN-DC formula output in range

*For any* non-null NR counter tuple where `pmEndcSetupUeAtt > 0`,
`compute_endc_success_rate` SHALL return a value in [0.0, 100.0].

**Validates: Requirements 2.6, 12.2**

---

### Property 4: Zero-denominator guard — null return, no exception

*For any* KPI formula, when any denominator in that formula evaluates to zero (or any input is
`None`), the corresponding compute function SHALL return `None` and SHALL NOT raise a runtime
exception.

**Validates: Requirements 2.7, 12.1**

---

### Property 5: Cell Availability capping invariant

*For any* input where `PMCELLDOWNTIMEAUTO + PMCELLDOWNTIMEMAN > PERIOD_DURATION` (and
`PERIOD_DURATION > 0`), `compute_cell_availability` SHALL return exactly `100.0` as the value AND
set `data_quality_flag = True`.

*For any* input where the raw result is ≤ 100.0, the returned value SHALL equal the raw formula
result and `data_quality_flag` SHALL be `False`.

**Validates: Requirements 2.4, 12.3**

---

### Property 6: KPI formula determinism (idempotence)

*For any* valid counter tuple (all inputs non-null, all denominators > 0), applying any KPI formula
twice with the same unmodified inputs SHALL produce the same numeric result within a relative error
of 1×10⁻⁹.

**Validates: Requirements 12.4**

---

### Property 7: Baseline is the median of prior values

*For any* non-empty list of prior KPI values, `compute_baseline` SHALL return the statistical
median of those values. *For any* empty list, `compute_baseline` SHALL return `None`.

**Validates: Requirements 2.9**

---

### Property 8: Degradation thresholds applied correctly for all KPIs

*For any* (kpi_name, value, baseline) triple:

- Accessibility with `value < 95.0` → status is "degraded"
- Accessibility with `baseline - value > 5.0` (and value ≥ 95.0) → status is "degraded"
- Retainability with `value > 2.0` → status is "degraded"
- DL Throughput with `value < baseline × 0.70` → status is "degraded"
- Cell Availability with `value < 99.0` → status is "degraded"
- DL PDCP DRB Latency with `value > baseline × 1.30` → status is "degraded"
- EN-DC Setup Success Rate with `value < 90.0` → status is "degraded"
- `value = None` → status is "unavailable" for all KPI names
- `baseline = None` for relative KPIs (DL Throughput, Latency) → status is "unavailable"

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8**

---

### Property 9: KPI result objects contain all required fields

*For any* invocation of `query_lte_kpi` or `query_nr_endc` that returns successfully, every entry
in the `kpis_evaluated` array SHALL contain exactly the fields: `kpi` (str), `value` (float or
null), `baseline` (float or null), and `status` (one of "ok", "degraded", "unavailable").

**Validates: Requirements 3.9**

---

### Property 10: Confidence assignment matches domain-count rule

*For any* evidence collection, the confidence value SHALL be:

- "high" if evidence items span ≥ 2 distinct domains (KPI counters, CM config, alarms)
- "medium" if evidence items span exactly 1 domain and KPI degradation is confirmed
- "low" if the signal is ambiguous, counters are missing for > 1 KPI, or evidence is empty

**Validates: Requirements 6.4, 6.5, 6.6, 6.7, 10.1, 10.2, 10.3**

---

### Property 11: root_cause length invariant

*For any* RCA_Output produced by the system, `len(root_cause) ≤ 200`.

**Validates: Requirements 6.9**

---

### Property 12: Incident extraction — missing-field error identifies the missing field

*For any* incident description that is missing one or more of {cell identifier, date}, the
extraction step SHALL return a structured error that names the specific missing field(s) and SHALL
NOT return a scope confirmation or proceed to KPI computation.

**Validates: Requirements 1.3**

---

## Error Handling

| Error condition | Behaviour |
|----------------|-----------|
| Missing env variable at startup | `EnvironmentError` raised in `main.py` before NAT workflow builds; names the missing variable |
| Cell ID not found in any CSV | Orchestrator returns `{"error": "Cell <id> not found in dataset"}` immediately |
| Missing cell ID or date in description | Orchestrator returns structured error naming the missing field |
| Zero denominator in KPI formula | `KPICalculator` returns `None`; status set to "unavailable"; no exception propagates |
| Downtime > PERIOD_DURATION | Availability capped at 100.0; `data_quality_flag = True` |
| Counter column absent from CSV | Evidence entry `"<COUNTER_NAME>: counter unavailable"` added; KPI status "unavailable" |
| DuckDB query failure | Python exception propagates to NAT tool handler; tool returns error string to LLM |
| LLM returns non-JSON output | `eval/run_eval.py` catches `json.JSONDecodeError`; scores the run as 0 |
| EN-DC `pmEndcSetupUeAtt = 0` | `compute_endc_success_rate` returns `None`; status "unavailable" |

---

## Testing Strategy

### Dual Testing Approach

Unit tests verify specific examples, edge cases, and formula correctness. Property-based tests
verify universal correctness guarantees across the full input space. Both are needed: unit tests
catch concrete regressions; property tests find edge cases that examples miss.

### Unit Tests (`tests/`)

```
tests/
├── test_kpi_calculator.py      # Formula correctness against known values, edge cases
├── test_query_tools.py         # Tool functions against sample CSVs (DuckDB integration)
├── test_degradation_flags.py   # Threshold boundary examples
└── test_eval_scorers.py        # T1–T5 scorer functions
```

Unit tests focus on:
- Known counter values → expected KPI numeric result (regression check)
- Boundary examples: value exactly at threshold (e.g., availability = 99.0 → "ok")
- Cell-not-found → error dict returned
- Missing environment variable → `EnvironmentError` raised
- `score_t4` rubric mapping examples for each of the 4 score levels

### Property-Based Tests (`tests/test_properties.py`)

Property-based testing library: **[Hypothesis](https://hypothesis.readthedocs.io/)** (Python).
Minimum 100 iterations per property (Hypothesis default ≥ 100; configured via
`@settings(max_examples=200)` for the numeric formula properties).

Each test is tagged with a comment referencing its design property:

```python
# Feature: telco-incident-triage-agent, Property 1: Accessibility formula output in range
@given(
    succ=st.integers(min_value=0, max_value=10_000),
    att=st.integers(min_value=1, max_value=10_000),
    reatt=st.integers(min_value=0),
    s1succ=st.integers(min_value=0, max_value=10_000),
    s1att=st.integers(min_value=1, max_value=10_000),
    erab_succ=st.integers(min_value=0, max_value=10_000),
    erab_att=st.integers(min_value=1, max_value=10_000),
)
@settings(max_examples=200)
def test_accessibility_range(succ, att, reatt, s1succ, s1att, erab_succ, erab_att):
    assume(att - reatt > 0)
    calc = KPICalculator()
    result = calc.compute_accessibility(succ, att, reatt, s1succ, s1att, erab_succ, erab_att)
    assert result is not None
    assert 0.0 <= result <= 100.0
```

Property tests to implement (one test function per property):

| Property | Test description |
|----------|-----------------|
| P1 Accessibility range | Generated valid counters → result in [0, 100] |
| P2 Retainability range | Generated valid counters → result in [0, 100] |
| P3 EN-DC range | Generated valid NR counters → result in [0, 100] |
| P4 Zero-denominator guard | Generated zero-denominator inputs → None returned, no exception |
| P5 Availability capping | Generated downtime > period → 100.0 + flag=True |
| P6 Formula determinism | Same inputs applied twice → equal result within 1e-9 |
| P7 Baseline = median | Generated float lists → result == statistics.median |
| P8 Degradation thresholds | Generated (kpi, value, baseline) triples → correct status string |
| P9 KPI result fields | Generated valid tool inputs → kpis_evaluated entries have all 4 fields |
| P10 Confidence assignment | Generated evidence domain sets → correct confidence string |
| P11 root_cause length | Any RCA_Output → len(root_cause) ≤ 200 |
| P12 Missing-field error | Descriptions with omitted fields → error names missing field |

### Integration Tests (`tests/test_integration.py`)

Integration tests run the four scripted incidents end-to-end through the NAT workflow. These are
not property tests — they verify the correct agent is dispatched and evidence cites actual CSV
values.

Run against a real LLM endpoint (requires `.env` to be populated):

```bash
pytest tests/test_integration.py -m integration --run_integration
```

These tests verify:
- INC-1: `query_cm_config` is called; RCA mentions a CM parameter
- INC-2: `query_alarm_history` is called; evidence cites `PMCELLDOWNTIMEAUTO`
- INC-3: `query_lte_kpi` called on multiple cells; no CM change in evidence
- INC-4: `query_nr_endc` called; LTE anchor Accessibility confirmed ≥ 95%

### Running Tests

```bash
# Unit + property tests (no LLM required)
pytest tests/ -m "not integration"

# Property tests only
pytest tests/test_properties.py

# All tests including integration (requires .env)
pytest tests/ --run_integration

# Evaluation harness
python eval/run_eval.py nemotron_telco
python eval/run_eval.py frontier_llm
```
