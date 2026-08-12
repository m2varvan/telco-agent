# Implementation Plan: Network Incident Triage Assistant

## Overview

Build the Network Incident Triage Assistant (NAT) on the NVIDIA NeMo Agent Toolkit by:
- Extending `main.py` and `workflow.yml` in-place (no replacement from scratch)
- Creating the `nat/` package with a pure `kpi_calculator.py` module and four DuckDB-backed tool functions
- Wiring everything together as a `react_agent` in `workflow.yml` with a full system prompt
- Implementing an `eval/` harness with four scripted scenarios and T1–T5 scorers
- Adding Hypothesis property-based tests that exercise all twelve correctness properties from the design

---

## Tasks

- [x] 1. Phase 0 — KPI Formula Module
  - [x] 1.1 Create `nat/__init__.py` and `nat/kpi_calculator.py`
    - Create `nat/` directory and empty `nat/__init__.py`
    - Implement `KPICalculator` class with all six formula methods exactly as specified in the design:
      `compute_accessibility`, `compute_retainability`, `compute_dl_throughput`,
      `compute_cell_availability`, `compute_dl_latency`, `compute_endc_success_rate`
    - Add module-level threshold constants:
      `ACCESSIBILITY_ABSOLUTE_THRESHOLD = 95.0`, `ACCESSIBILITY_RELATIVE_THRESHOLD = 5.0`,
      `RETAINABILITY_THRESHOLD = 2.0`, `THROUGHPUT_RELATIVE_THRESHOLD = 0.30`,
      `AVAILABILITY_THRESHOLD = 99.0`, `LATENCY_RELATIVE_THRESHOLD = 0.30`, `ENDC_THRESHOLD = 90.0`
    - Implement `compute_baseline(prior_values: list[float]) -> float | None` using `statistics.median`
    - Implement `flag_degradation(kpi_name, value, baseline) -> str` returning "ok", "degraded", or "unavailable"
    - Implement `evaluate_lte(counters, prior_rows, cols) -> dict` that calls all LTE formulas, computes baselines, flags, and returns the full `kpis_evaluated` structure
    - Implement `evaluate_nr_endc(counters, prior_rows, cols) -> dict` for NR EN-DC KPI
    - Cell Availability must cap at 100.0 and set `data_quality_flag=True` when downtime > PERIOD_DURATION (Req 12.3)
    - Every denominator guard must return `None` without raising (Req 2.7)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 3.1–3.9, 12.1–12.4_

  - [ ]* 1.2 Write unit tests for `kpi_calculator.py`
    - Create `tests/__init__.py` and `tests/test_kpi_calculator.py`
    - Test each formula with known counter values against expected numeric results (regression)
    - Test boundary examples: denominator = 0, all-None inputs, availability exactly 99.0 → "ok"
    - Test availability capping: downtime > PERIOD_DURATION → value = 100.0, flag = True
    - Test `compute_baseline` with odd-length, even-length, and empty lists
    - Test `flag_degradation` for every KPI at threshold boundary (value exactly at threshold → "ok")
    - _Requirements: 2.1–2.9, 3.1–3.9, 12.1–12.4_

- [x] 2. Phase 1 — Tool Functions (DuckDB)
  - [x] 2.1 Create `nat/tools/__init__.py` and `nat/tools/query_lte_kpi.py`
    - Implement `query_lte_kpi(cell_id, oss_id, year, month, day) -> dict` as specified in the design
    - Use `duckdb.connect()` with `read_csv_auto` — no external server
    - Filter incident-day row on `EUTRANCELLFDD`, `OSS_ID`, `YEAR_ID`, `MONTH_ID`, `DAY_ID` only (Req 8.1, 8.6)
    - Filter prior rows using the date-comparison pattern from the design (year/month/day compound condition)
    - Return `{"error": ...}` dict when no row found for the cell (no exception propagation)
    - Call `KPICalculator().evaluate_lte(counters, prior_rows, cols)` and merge result
    - Read CSV path from `os.getenv("LTE_KPI_CSV", "sample_data/lte_kpi_sample.csv")`
    - _Requirements: 2.1–2.9, 3.1–3.9, 8.1, 8.4, 8.6_

  - [x] 2.2 Create `nat/tools/query_nr_endc.py`
    - Implement `query_nr_endc(nr_cell_id, oss_id, year, month, day) -> dict`
    - Filter on `NRCellCU`, `OSS_ID`, `YEAR_ID`, `MONTH_ID`, `DAY_ID` only (Req 8.2)
    - Use exact camelCase column names from `nr_endc_sample.csv` header: `pmEndcSetupUeSucc`, `pmEndcSetupUeAtt`, `pmEndcSetupScgUeSucc`, `pmEndcSetupScgUeAtt` (Req 8.7)
    - Call `KPICalculator().evaluate_nr_endc(counters, prior_rows, cols)` for KPI + baseline + status
    - Return `raw_counters` dict alongside `kpis_evaluated`
    - Read CSV path from `os.getenv("NR_ENDC_CSV", "sample_data/nr_endc_sample.csv")`
    - _Requirements: 2.6, 3.6, 8.2, 8.4, 8.7_

  - [x] 2.3 Create `nat/tools/query_cm_config.py`
    - Implement `query_cm_config(cell_id, oss_id, before_date, days_back=7) -> dict`
    - Filter on `EUTRANCELLFDD`, `OSS_ID`, `DATETIME_ID` only (Req 8.3)
    - Use exact UPPERCASE column names from `cm_config_sample.csv`: `ADMINISTRATIVESTATE`, `CELLBARRED`, `FREQBAND`, `EARFCNDL`, `EARFCNUL`, `DLCHANNELBANDWIDTH`, `LATITUDE`, `LONGITUDE` (Req 8.7)
    - Compute `dt_from = datetime.fromisoformat(before_date) - timedelta(days=days_back)` and `dt_to`
    - Return `{"cell_id", "window": {"from", "to"}, "changes": [...]}`
    - Read CSV path from `os.getenv("CM_CONFIG_CSV", "sample_data/cm_config_sample.csv")`
    - _Requirements: 4.1, 5.2, 7.1, 8.3, 8.5, 8.7_

  - [x] 2.4 Create `nat/tools/query_alarm_history.py`
    - Implement `query_alarm_history(cell_id, oss_id, year, month, day) -> dict`
    - Query `PMCELLDOWNTIMEAUTO`, `PMCELLDOWNTIMEMAN`, `PERIOD_DURATION` from `lte_kpi_sample.csv` using LTE join keys (Req 8.1)
    - Compute `availability_pct` inline (same formula as KPICalculator, no cap needed here — raw value for display)
    - Filter module-level `SYNTHETIC_ALARMS` list by `EUTRANCELLFDD` and `start_time[:10]`
    - Return `{"cell_id", "PMCELLDOWNTIMEAUTO", "PMCELLDOWNTIMEMAN", "PERIOD_DURATION", "availability_pct", "alarms": [...]}`
    - _Requirements: 4.2, 5.3, 7.2, 8.1_

  - [ ]* 2.5 Write unit tests for tool functions
    - Create `tests/test_query_tools.py`
    - Test `query_lte_kpi` against `sample_data/lte_kpi_sample.csv` with a known cell (e.g., `BC5501XD`, `eniq_oss_1`, 2026, 6, 29) — verify `kpis_evaluated` list is non-empty and all four fields present on each entry
    - Test `query_nr_endc` with known NR cell (`EPBNW`, `eniq_oss_1`, 2026, 6, 30)
    - Test `query_cm_config` with a known cell and date window — verify `changes` key present
    - Test `query_alarm_history` with a known cell — verify downtime counters returned
    - Test cell-not-found path for each tool — verify `{"error": ...}` returned
    - _Requirements: 8.1–8.7_

- [x] 3. Phase 1 Checkpoint — Ensure all unit tests pass
  - Run `pytest tests/ -m "not integration"` and confirm zero failures before proceeding to Phase 2.
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Phase 2 — Extend `workflow.yml` and `main.py`
  - [x] 4.1 Rewrite `workflow.yml` to declare the full NAT configuration
    - Replace existing stub content with the full design YAML (keep the file at workspace root)
    - Declare `functions:` section with four entries: `query_lte_kpi`, `query_nr_endc`, `query_cm_config`, `query_alarm_history` — each with `_type: python_function`, `module`, `function`, and `description` fields exactly as in the design (Req 11.1, 11.2)
    - Declare two `llms:` entries: `nemotron_telco` (`_type: nim`, reads `${LLM_MODEL_NAME}`, `${LLM_API_KEY}`, `${LLM_BASE_URL}`) and `frontier_llm` (`_type: openai`, reads `${FRONTIER_MODEL_NAME}`, `${FRONTIER_API_KEY}`, `${FRONTIER_BASE_URL}`) (Req 11.4)
    - Set `workflow._type: react_agent`, `llm_name: nemotron_telco`, `tool_names: [query_lte_kpi, query_nr_endc, query_cm_config, query_alarm_history]`, `verbose: true`
    - Leave `system_prompt` as a placeholder string — it will be filled in Phase 3
    - _Requirements: 11.1, 11.2, 11.4_

  - [x] 4.2 Extend `main.py` with env validation and CLI input
    - Keep the existing `asyncio`/`dotenv`/`WorkflowBuilder` imports
    - Add `_REQUIRED_VARS = ["LLM_MODEL_NAME", "LLM_API_KEY", "LLM_BASE_URL"]`
    - Add `_validate_env()` function that raises `EnvironmentError` naming the first missing variable (Req 11.3, 11.6)
    - Update `main(incident: str) -> str` to call `_validate_env()` before building the workflow
    - Add `__main__` block that reads the incident from `sys.argv[1:]` or `input()`, guards against empty string with `sys.exit(1)`, and prints the result (Req 11.5)
    - _Requirements: 11.3, 11.5, 11.6_

  - [ ]* 4.3 Write unit tests for `main.py` env validation
    - Create `tests/test_main.py`
    - Use `monkeypatch.delenv` to unset each of the three required variables one at a time and assert `EnvironmentError` is raised
    - Assert the error message contains the missing variable name
    - _Requirements: 11.3, 11.6_

- [x] 5. Phase 3 — Orchestrator System Prompt
  - [x] 5.1 Embed the full system prompt into `workflow.yml`
    - Replace the placeholder `system_prompt` value with the complete four-section prompt from the design:
      identity, schema grounding (exact column names for all three CSVs), investigation protocol (Steps 1–5), and output contract (JSON schema + confidence rules)
    - Ensure the schema grounding section lists all UPPERCASE LTE counter names, camelCase NR counter names, and UPPERCASE CM parameter names verbatim (Req 8.6, 8.7)
    - Investigation protocol must encode selective dispatch rules: CM for Accessibility/Throughput/Latency degradation, Alarm for Availability degradation, NR+LTE anchor for EN-DC degradation, multi-cell scan when no KPIs degraded (Req 4.1–4.6)
    - Output contract must specify all seven RCA_Output fields and three confidence levels (Req 6.1, 10.1–10.3)
    - _Requirements: 1.1–1.5, 4.1–4.6, 6.1–6.10, 10.1–10.6_

- [x] 6. Phase 4 — Evaluation Harness
  - [x] 6.1 Create `eval/__init__.py` and `eval/scenarios.py`
    - Define `ScriptedIncident` dataclass with fields: `id`, `description`, `ground_truth_root_cause_category`, `ground_truth_evidence_keywords`, `injected_alarms`
    - Implement `SCENARIOS` list with all four scripted incidents (INC-1 through INC-4) exactly as specified in the design, with correct descriptions, categories, evidence keywords, and injected alarms for INC-2 ("Backhaul Link Down" alarm on W01AXB, 2022-12-07)
    - _Requirements: 7.1–7.6, 9.1_

  - [x] 6.2 Create `eval/scorers.py`
    - Implement all five scoring functions exactly as designed:
      - `score_t1(response, expected) -> int` — exact string match (0 or 1)
      - `score_t2(computed, expected, tolerance=0.01) -> int` — numeric tolerance ±0.01
      - `score_t3(result_rows, expected_rows, key) -> int` — set match on key field
      - `score_t4(rca_output, ground_truth_category, evidence_keywords) -> int` — rubric 0–3 per design
      - `score_t5(generated_sql, required_tables, required_joins) -> int` — table + join reference check
    - T4 rubric: 3 = category match AND evidence keyword found; 2 = category only; 1 = evidence only; 0 = neither
    - _Requirements: 9.1, 9.3_

  - [x] 6.3 Create `eval/run_eval.py` and `eval/results/` directory
    - Implement `dataset_version() -> str` as SHA-256 of all three CSVs concatenated, truncated to 12 hex chars (Req 9.2)
    - Implement `run_scenario(workflow, scenario) -> dict` — inject `SYNTHETIC_ALARMS`, time the run, parse JSON output (catch `JSONDecodeError`), score T4, return result dict with `scenario_id`, `t4_score`, `correct`, `latency_s`, `rca`
    - Implement `run_eval(model_name, workflow_config) -> None` — build workflow, run all four scenarios, compute RCA accuracy %, write JSON to `eval/results/{model_name}_{version}.json`
    - Add `if __name__ == "__main__"` entry point reading model name from `sys.argv[1]`
    - Ensure `eval/results/` is created with `mkdir(parents=True, exist_ok=True)` (add to `.gitignore`)
    - _Requirements: 7.5, 7.6, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_

  - [ ]* 6.4 Write unit tests for eval scorers
    - Create `tests/test_eval_scorers.py`
    - Test `score_t1` with exact-match positive and negative cases
    - Test `score_t2` at boundary (value exactly ±0.01 from expected → 1; value 0.02 away → 0)
    - Test `score_t3` with matching and non-matching key sets
    - Test `score_t4` for all four rubric levels (0, 1, 2, 3) with crafted RCA dicts
    - Test `score_t5` with SQL that references required tables/joins and SQL that omits one
    - _Requirements: 9.1, 9.3_

- [x] 7. Phase 4 Checkpoint — Ensure all tests pass
  - Run `pytest tests/ -m "not integration"` and confirm zero failures before proceeding to Phase 5.
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Phase 5 — Property-Based Tests (Hypothesis)
  - [x] 8.1 Write property test for Property 1 — Accessibility formula range
    - Create `tests/test_properties.py`
    - Use `@given` with integer strategies for all seven accessibility counters; `assume(att - reatt > 0)`, `assume(s1att > 0)`, `assume(erab_att > 0)`
    - Assert result is not None and `0.0 <= result <= 100.0`
    - Annotate: `# Feature: telco-incident-triage-agent, Property 1`
    - Use `@settings(max_examples=200)`
    - _Requirements: 2.1, 12.1 — **Property 1**_

  - [x] 8.2 Write property test for Property 2 — Retainability formula range
    - Add to `tests/test_properties.py`
    - `@given` with non-negative integers; `assume(abnormal + normal > 0)`
    - Assert result not None and `0.0 <= result <= 100.0`
    - Annotate: `# Feature: telco-incident-triage-agent, Property 2`
    - _Requirements: 2.2, 12.1 — **Property 2**_

  - [x] 8.3 Write property test for Property 3 — EN-DC formula range
    - `@given` with non-negative integers for succ/att; `assume(att > 0)`, `assume(succ <= att)`
    - Assert result not None and `0.0 <= result <= 100.0`
    - Annotate: `# Feature: telco-incident-triage-agent, Property 3`
    - _Requirements: 2.6, 12.2 — **Property 3**_

  - [x] 8.4 Write property test for Property 4 — Zero-denominator guard (no exception, None return)
    - For each of the six formula methods, generate inputs where the relevant denominator equals zero (or inputs are None)
    - Use `pytest.raises` context manager inverted — assert no exception is raised
    - Assert return value is `None` (or `(None, False)` for `compute_cell_availability`)
    - Cover: RRC denom = 0, S1 att = 0, ERAB att = 0, combined abnormal+normal = 0, PMUETHPTIMEDL = 0, PERIOD_DURATION = 0, PMPDCLATPKTTRANSDL = 0, pmEndcSetupUeAtt = 0
    - Annotate: `# Feature: telco-incident-triage-agent, Property 4`
    - _Requirements: 2.7, 12.1 — **Property 4**_

  - [x] 8.5 Write property test for Property 5 — Cell Availability capping invariant
    - `@given` integers for auto, man, period; `assume(period > 0)`
    - Branch A: `auto + man > period` → assert value == 100.0 and flag == True
    - Branch B: `auto + man <= period` → assert value == raw formula result and flag == False
    - Annotate: `# Feature: telco-incident-triage-agent, Property 5`
    - _Requirements: 2.4, 12.3 — **Property 5**_

  - [x] 8.6 Write property test for Property 6 — Formula determinism (idempotence)
    - For each formula, generate valid non-zero inputs, call the formula twice with identical values
    - Assert `abs(result1 - result2) <= 1e-9 * max(abs(result1), 1.0)`
    - Cover all six formulas in one test or separate sub-tests
    - Annotate: `# Feature: telco-incident-triage-agent, Property 6`
    - _Requirements: 12.4 — **Property 6**_

  - [x] 8.7 Write property test for Property 7 — Baseline equals median of prior values
    - `@given(st.lists(st.floats(allow_nan=False, allow_infinity=False), min_size=1))`
    - Assert `compute_baseline(values) == statistics.median(values)`
    - Also test empty list → `compute_baseline([]) is None`
    - Annotate: `# Feature: telco-incident-triage-agent, Property 7`
    - _Requirements: 2.9 — **Property 7**_

  - [x] 8.8 Write property test for Property 8 — Degradation thresholds applied correctly
    - Use `@given` with `st.sampled_from` for kpi_name and `st.floats` for value/baseline
    - Parameterize per KPI threshold rule from the design:
      - Accessibility: value < 95.0 → "degraded"; baseline - value > 5.0 (with value ≥ 95) → "degraded"
      - Retainability: value > 2.0 → "degraded"
      - DL Throughput: value < baseline * 0.70 → "degraded"; baseline = None → "unavailable"
      - Cell Availability: value < 99.0 → "degraded"
      - DL PDCP DRB Latency: value > baseline * 1.30 → "degraded"; baseline = None → "unavailable"
      - EN-DC: value < 90.0 → "degraded"
      - value = None → "unavailable" for all KPI names
    - Annotate: `# Feature: telco-incident-triage-agent, Property 8`
    - _Requirements: 3.1–3.8 — **Property 8**_

  - [x] 8.9 Write property test for Property 9 — KPI result objects contain all required fields
    - `@given` valid cell_id, oss_id, date drawn from actual sample CSV values (use `st.sampled_from`)
    - Call `query_lte_kpi` and `query_nr_endc` with real CSV paths
    - For each entry in `kpis_evaluated`, assert all four fields present: `kpi` (str), `value` (float or None), `baseline` (float or None), `status` (one of three strings)
    - Annotate: `# Feature: telco-incident-triage-agent, Property 9`
    - _Requirements: 3.9 — **Property 9**_

  - [x] 8.10 Write property test for Property 10 — Confidence assignment matches domain-count rule
    - Implement a helper `assign_confidence(evidence_domains: list[str], kpi_degraded: bool, ambiguous: bool) -> str` in `nat/kpi_calculator.py` or a separate module
    - `@given` with `st.lists(st.sampled_from(["kpi", "cm", "alarm"]))` and `st.booleans()`
    - Assert: len(set(domains)) >= 2 and kpi_degraded → "high"; len(set(domains)) == 1 and kpi_degraded → "medium"; ambiguous or empty → "low"
    - Annotate: `# Feature: telco-incident-triage-agent, Property 10`
    - _Requirements: 6.4–6.7, 10.1–10.3 — **Property 10**_

  - [x] 8.11 Write property test for Property 11 — root_cause length invariant
    - `@given(st.text(max_size=500))`
    - Construct a minimal `RCAOutput`-shaped dict with the generated string as `root_cause`
    - Only assert the invariant on outputs returned by the actual system — for pure unit testing of the constraint, verify that any string the system generates satisfies `len(root_cause) <= 200`
    - Add a direct test: given a root_cause string of exactly 200 chars → accepted; 201 chars → would violate invariant
    - Annotate: `# Feature: telco-incident-triage-agent, Property 11`
    - _Requirements: 6.9 — **Property 11**_

  - [x] 8.12 Write property test for Property 12 — Missing-field error identifies the missing field
    - `@given` incident descriptions generated by `st.text()` that are guaranteed to omit either the cell identifier pattern or the date pattern (use `assume` or constructive generation)
    - Call the extraction/scope logic (or mock the Orchestrator response) and assert the error dict contains the name of the missing field
    - This test covers the Orchestrator's structured-error path, not the LLM itself — wire against a stub that mimics the expected behaviour
    - Annotate: `# Feature: telco-incident-triage-agent, Property 12`
    - _Requirements: 1.3 — **Property 12**_

- [x] 9. Final Checkpoint — Ensure all tests pass
  - Run `pytest tests/ -m "not integration"` and confirm zero failures.
  - Run `pytest tests/test_properties.py -v` to confirm all 12 property tests pass.
  - Ensure all tests pass, ask the user if questions arise.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for full traceability
- The six-phase order (P0 → P1 → P2 → P3 → P4 → P5) mirrors the design document phasing
- `workflow.yml` and `main.py` are extended in-place; never replaced from scratch
- DuckDB reads CSV files in-process — no external database server required
- Column name casing is critical: UPPERCASE for LTE/CM counters, camelCase for NR counters (Req 8.6, 8.7)
- Hypothesis default `max_examples` is overridden to 200 for numeric formula properties
- Integration tests (requiring a live LLM endpoint) are tagged `@pytest.mark.integration` and excluded from the default run
- Add `eval/results/` to `.gitignore` before committing

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4"] },
    { "id": 3, "tasks": ["2.5", "4.1", "4.2"] },
    { "id": 4, "tasks": ["4.3", "5.1"] },
    { "id": 5, "tasks": ["6.1", "6.2"] },
    { "id": 6, "tasks": ["6.3", "6.4"] },
    { "id": 7, "tasks": ["8.1", "8.2", "8.3", "8.4", "8.5", "8.6", "8.7"] },
    { "id": 8, "tasks": ["8.8", "8.9", "8.10", "8.11", "8.12"] }
  ]
}
```
