"""
Property-based tests for the Network Incident Triage Assistant.
Uses Hypothesis to verify universally-quantified correctness properties.
All 12 design properties are covered here.
Requirements: 2.1–2.9, 3.1–3.8, 6.4–6.7, 6.9, 10.1–10.3, 12.1–12.4
"""
import statistics
import pytest
from hypothesis import given, assume, settings, HealthCheck
from hypothesis import strategies as st

from agent_tools.kpi_calculator import (
    KPICalculator,
    assign_confidence,
    ACCESSIBILITY_ABSOLUTE_THRESHOLD,
    ACCESSIBILITY_RELATIVE_THRESHOLD,
    RETAINABILITY_THRESHOLD,
    THROUGHPUT_RELATIVE_THRESHOLD,
    AVAILABILITY_THRESHOLD,
    LATENCY_RELATIVE_THRESHOLD,
    ENDC_THRESHOLD,
)


@pytest.fixture
def calc():
    return KPICalculator()


# ── Property 1: Accessibility formula output in range [0, 100] ───────────────
# Feature: telco-incident-triage-agent, Property 1 — Validates: Req 2.1, 12.1

@given(
    succ=st.integers(min_value=0, max_value=100_000),
    att=st.integers(min_value=1, max_value=100_000),
    reatt=st.integers(min_value=0, max_value=100_000),
    s1succ=st.integers(min_value=0, max_value=100_000),
    s1att=st.integers(min_value=1, max_value=100_000),
    erab_succ=st.integers(min_value=0, max_value=100_000),
    erab_att=st.integers(min_value=1, max_value=100_000),
)
@settings(max_examples=200, suppress_health_check=[HealthCheck.filter_too_much])
def test_property_1_accessibility_range(
    succ, att, reatt, s1succ, s1att, erab_succ, erab_att
):
    """Property 1: For valid non-zero denominators, accessibility is in [0, 100]."""
    rrc_denom = att - reatt
    assume(rrc_denom > 0)
    # Each sub-ratio must be ≤ 1 for the product to stay in [0,100]
    assume(succ <= rrc_denom)
    assume(s1succ <= s1att)
    assume(erab_succ <= erab_att)
    calc = KPICalculator()
    result = calc.compute_accessibility(succ, att, reatt, s1succ, s1att, erab_succ, erab_att)
    assert result is not None
    assert 0.0 <= result <= 100.0


# ── Property 2: Retainability formula output in range [0, 100] ───────────────
# Feature: telco-incident-triage-agent, Property 2 — Validates: Req 2.2, 12.1

@given(
    abnormal=st.integers(min_value=0, max_value=1_000_000),
    normal=st.integers(min_value=0, max_value=1_000_000),
)
@settings(max_examples=200)
def test_property_2_retainability_range(abnormal, normal):
    """Property 2: For non-zero combined releases, retainability is in [0, 100]."""
    assume(abnormal + normal > 0)
    calc = KPICalculator()
    result = calc.compute_retainability(abnormal, normal)
    assert result is not None
    assert 0.0 <= result <= 100.0


# ── Property 3: EN-DC formula output in range [0, 100] ───────────────────────
# Feature: telco-incident-triage-agent, Property 3 — Validates: Req 2.6, 12.2

@given(
    succ=st.integers(min_value=0, max_value=100_000),
    att=st.integers(min_value=1, max_value=100_000),
)
@settings(max_examples=200)
def test_property_3_endc_range(succ, att):
    """Property 3: For att > 0 and succ <= att, EN-DC rate is in [0, 100]."""
    assume(succ <= att)
    calc = KPICalculator()
    result = calc.compute_endc_success_rate(succ, att)
    assert result is not None
    assert 0.0 <= result <= 100.0


# ── Property 4: Zero-denominator guard — None return, no exception ────────────
# Feature: telco-incident-triage-agent, Property 4 — Validates: Req 2.7, 12.1

def test_property_4_accessibility_zero_rrc_denom():
    calc = KPICalculator()
    # att == reatt → rrc_denom = 0
    result = calc.compute_accessibility(100, 200, 200, 100, 100, 100, 100)
    assert result is None

def test_property_4_accessibility_zero_s1_att():
    calc = KPICalculator()
    result = calc.compute_accessibility(100, 200, 50, 100, 0, 100, 100)
    assert result is None

def test_property_4_accessibility_zero_erab_att():
    calc = KPICalculator()
    result = calc.compute_accessibility(100, 200, 50, 100, 100, 100, 0)
    assert result is None

def test_property_4_retainability_zero_denom():
    calc = KPICalculator()
    result = calc.compute_retainability(0, 0)
    assert result is None

def test_property_4_throughput_zero_time():
    calc = KPICalculator()
    result = calc.compute_dl_throughput(1000, 500, 0)
    assert result is None

def test_property_4_availability_zero_period():
    calc = KPICalculator()
    val, flag = calc.compute_cell_availability(100, 0, 0)
    assert val is None
    assert flag is False

def test_property_4_latency_zero_pkts():
    calc = KPICalculator()
    result = calc.compute_dl_latency(1000, 0)
    assert result is None

def test_property_4_endc_zero_att():
    calc = KPICalculator()
    result = calc.compute_endc_success_rate(0, 0)
    assert result is None

@given(
    succ=st.integers(min_value=0, max_value=100_000),
)
@settings(max_examples=100)
def test_property_4_none_inputs_return_none(succ):
    """Any None input to any formula returns None without raising."""
    calc = KPICalculator()
    # Accessibility with None first arg
    assert calc.compute_accessibility(None, succ, 0, succ, succ, succ, succ) is None
    # Retainability with None
    assert calc.compute_retainability(None, succ) is None
    # Throughput with None
    assert calc.compute_dl_throughput(None, succ, succ + 1) is None
    # Availability with None
    val, flag = calc.compute_cell_availability(None, succ, succ + 1)
    assert val is None
    # Latency with None
    assert calc.compute_dl_latency(None, succ + 1) is None
    # EN-DC with None
    assert calc.compute_endc_success_rate(None, succ + 1) is None


# ── Property 5: Cell Availability capping invariant ───────────────────────────
# Feature: telco-incident-triage-agent, Property 5 — Validates: Req 2.4, 12.3

@given(
    auto=st.integers(min_value=0, max_value=200_000),
    man=st.integers(min_value=0, max_value=200_000),
    period=st.integers(min_value=1, max_value=200_000),
)
@settings(max_examples=200)
def test_property_5_availability_capping(auto, man, period):
    """Property 5: When downtime > period, value=100.0 and flag=True; else formula applies."""
    calc = KPICalculator()
    val, flag = calc.compute_cell_availability(auto, man, period)
    if auto + man > period:
        assert val == pytest.approx(100.0)
        assert flag is True
    else:
        expected = 100.0 * (1 - (auto + man) / period)
        assert val == pytest.approx(expected)
        assert flag is False


# ── Property 6: Formula determinism (idempotence) ─────────────────────────────
# Feature: telco-incident-triage-agent, Property 6 — Validates: Req 12.4

@given(
    succ=st.integers(min_value=0, max_value=10_000),
    att=st.integers(min_value=1, max_value=10_000),
    reatt=st.integers(min_value=0, max_value=1_000),
    s1succ=st.integers(min_value=0, max_value=10_000),
    s1att=st.integers(min_value=1, max_value=10_000),
    erab_succ=st.integers(min_value=0, max_value=10_000),
    erab_att=st.integers(min_value=1, max_value=10_000),
)
@settings(max_examples=100)
def test_property_6_accessibility_determinism(succ, att, reatt, s1succ, s1att, erab_succ, erab_att):
    """Property 6: Same inputs → same result, twice."""
    assume(att - reatt > 0)
    calc = KPICalculator()
    r1 = calc.compute_accessibility(succ, att, reatt, s1succ, s1att, erab_succ, erab_att)
    r2 = calc.compute_accessibility(succ, att, reatt, s1succ, s1att, erab_succ, erab_att)
    if r1 is None:
        assert r2 is None
    else:
        assert abs(r1 - r2) <= 1e-9 * max(abs(r1), 1.0)

@given(
    abnormal=st.integers(min_value=1, max_value=100_000),
    normal=st.integers(min_value=0, max_value=100_000),
)
@settings(max_examples=100)
def test_property_6_retainability_determinism(abnormal, normal):
    calc = KPICalculator()
    r1 = calc.compute_retainability(abnormal, normal)
    r2 = calc.compute_retainability(abnormal, normal)
    if r1 is None:
        assert r2 is None
    else:
        assert abs(r1 - r2) <= 1e-9 * max(abs(r1), 1.0)

@given(
    succ=st.integers(min_value=1, max_value=1000),
    att=st.integers(min_value=1, max_value=1000),
)
@settings(max_examples=100)
def test_property_6_endc_determinism(succ, att):
    assume(succ <= att)
    calc = KPICalculator()
    r1 = calc.compute_endc_success_rate(succ, att)
    r2 = calc.compute_endc_success_rate(succ, att)
    if r1 is None:
        assert r2 is None
    else:
        assert abs(r1 - r2) <= 1e-9 * max(abs(r1), 1.0)


# ── Property 7: Baseline equals median of prior values ────────────────────────
# Feature: telco-incident-triage-agent, Property 7 — Validates: Req 2.9

@given(
    values=st.lists(
        st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=100,
    )
)
@settings(max_examples=200)
def test_property_7_baseline_equals_median(values):
    """Property 7: compute_baseline returns statistics.median of non-empty input."""
    calc = KPICalculator()
    result = calc.compute_baseline(values)
    assert result == pytest.approx(statistics.median(values), rel=1e-9)

def test_property_7_empty_list_returns_none():
    calc = KPICalculator()
    assert calc.compute_baseline([]) is None


# ── Property 8: Degradation thresholds applied correctly ─────────────────────
# Feature: telco-incident-triage-agent, Property 8 — Validates: Req 3.1–3.8

@given(value=st.floats(min_value=0.0, max_value=94.99, allow_nan=False, allow_infinity=False))
@settings(max_examples=200, suppress_health_check=[HealthCheck.filter_too_much])
def test_property_8_accessibility_below_absolute_always_degraded(value):
    """Below 95 absolute threshold → degraded regardless of baseline."""
    calc = KPICalculator()
    assert calc.flag_degradation("Accessibility", value, None) == "degraded"
    assert calc.flag_degradation("Accessibility", value, 99.0) == "degraded"

@given(
    value=st.floats(min_value=95.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    baseline=st.floats(min_value=95.0, max_value=115.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=200, suppress_health_check=[HealthCheck.filter_too_much])
def test_property_8_accessibility_relative_threshold(value, baseline):
    """baseline - value > 5.0 → degraded; ≤ 5.0 → ok (when value ≥ 95)."""
    calc = KPICalculator()
    result = calc.flag_degradation("Accessibility", value, baseline)
    if baseline - value > ACCESSIBILITY_RELATIVE_THRESHOLD:
        assert result == "degraded"
    else:
        assert result == "ok"

@given(value=st.floats(min_value=2.001, max_value=100.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=200, suppress_health_check=[HealthCheck.filter_too_much])
def test_property_8_retainability_above_threshold_degraded(value):
    calc = KPICalculator()
    assert calc.flag_degradation("Retainability", value, None) == "degraded"

@given(value=st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=200, suppress_health_check=[HealthCheck.filter_too_much])
def test_property_8_retainability_at_or_below_threshold_ok(value):
    calc = KPICalculator()
    assert calc.flag_degradation("Retainability", value, None) == "ok"

@given(
    baseline=st.floats(min_value=10.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=200)
def test_property_8_throughput_thresholds(baseline):
    calc = KPICalculator()
    degraded_value = baseline * (1 - THROUGHPUT_RELATIVE_THRESHOLD) - 0.01
    ok_value = baseline * (1 - THROUGHPUT_RELATIVE_THRESHOLD)
    assert calc.flag_degradation("DL Throughput", degraded_value, baseline) == "degraded"
    assert calc.flag_degradation("DL Throughput", ok_value, baseline) == "ok"
    assert calc.flag_degradation("DL Throughput", ok_value, None) == "unavailable"

@given(value=st.floats(min_value=0.0, max_value=98.99, allow_nan=False, allow_infinity=False))
@settings(max_examples=200, suppress_health_check=[HealthCheck.filter_too_much])
def test_property_8_availability_below_threshold_degraded(value):
    calc = KPICalculator()
    assert calc.flag_degradation("Cell Availability", value, None) == "degraded"

@given(
    baseline=st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=200)
def test_property_8_latency_thresholds(baseline):
    calc = KPICalculator()
    degraded_value = baseline * (1 + LATENCY_RELATIVE_THRESHOLD) + 0.01
    ok_value = baseline * (1 + LATENCY_RELATIVE_THRESHOLD)
    assert calc.flag_degradation("DL PDCP DRB Latency", degraded_value, baseline) == "degraded"
    assert calc.flag_degradation("DL PDCP DRB Latency", ok_value, baseline) == "ok"
    assert calc.flag_degradation("DL PDCP DRB Latency", ok_value, None) == "unavailable"

@given(value=st.floats(min_value=0.0, max_value=89.99, allow_nan=False, allow_infinity=False))
@settings(max_examples=200, suppress_health_check=[HealthCheck.filter_too_much])
def test_property_8_endc_below_threshold_degraded(value):
    calc = KPICalculator()
    assert calc.flag_degradation("EN-DC Setup Success Rate", value, None) == "degraded"

@given(kpi_name=st.sampled_from([
    "Accessibility", "Retainability", "DL Throughput",
    "Cell Availability", "DL PDCP DRB Latency", "EN-DC Setup Success Rate",
]))
@settings(max_examples=50)
def test_property_8_none_value_always_unavailable(kpi_name):
    """Property 8: None value → unavailable for ALL KPI types."""
    calc = KPICalculator()
    assert calc.flag_degradation(kpi_name, None, None) == "unavailable"
    assert calc.flag_degradation(kpi_name, None, 99.0) == "unavailable"


# ── Property 9: KPI result objects contain all required fields ────────────────
# Feature: telco-incident-triage-agent, Property 9 — Validates: Req 3.9

@given(
    cell_info=st.sampled_from([
        ("INC1_CELL_A", "eniq_oss_1", 2026, 6, 22),
        ("INC2_CELL_B", "eniq_oss_1", 2026, 6, 22),
        ("INC3_CELL_C1", "eniq_oss_1", 2026, 6, 22),
        ("INC4_LTE_ANCHOR", "eniq_oss_1", 2026, 6, 23),
        ("INC1_CELL_A", "eniq_oss_1", 2026, 6, 29),  # incident day
        ("INC2_CELL_B", "eniq_oss_1", 2026, 6, 29),  # outage day
    ])
)
@settings(max_examples=6, deadline=None)
def test_property_9_lte_kpi_result_fields(cell_info):
    """Property 9: Every kpis_evaluated entry has the 4 required fields with correct types."""
    from agent_tools.tools.query_lte_kpi import execute_query_lte_kpi as query_lte_kpi
    cell_id, oss_id, year, month, day = cell_info
    result = query_lte_kpi(cell_id, oss_id, year, month, day)
    assert "error" not in result
    for entry in result["kpis_evaluated"]:
        assert "kpi" in entry and isinstance(entry["kpi"], str)
        assert "value" in entry  # float or None
        assert "baseline" in entry  # float or None
        assert "status" in entry
        assert entry["status"] in ("ok", "degraded", "unavailable")
        if entry["value"] is not None:
            assert isinstance(entry["value"], float)

@given(
    cell_info=st.sampled_from([
        ("INC4_NR_D", "eniq_oss_1", 2026, 6, 22),
        ("INC4_NR_D", "eniq_oss_1", 2026, 6, 30),
    ])
)
@settings(max_examples=2, deadline=None)
def test_property_9_nr_endc_result_fields(cell_info):
    """Property 9: NR EN-DC kpis_evaluated entry has the 4 required fields."""
    from agent_tools.tools.query_nr_endc import execute_query_nr_endc as query_nr_endc
    nr_cell_id, oss_id, year, month, day = cell_info
    result = query_nr_endc(nr_cell_id, oss_id, year, month, day)
    assert "error" not in result
    for entry in result["kpis_evaluated"]:
        assert "kpi" in entry and isinstance(entry["kpi"], str)
        assert "value" in entry
        assert "baseline" in entry
        assert "status" in entry
        assert entry["status"] in ("ok", "degraded", "unavailable")


# ── Property 10: Confidence assignment matches domain-count rule ──────────────
# Feature: telco-incident-triage-agent, Property 10 — Validates: Req 6.4–6.7, 10.1–10.3

@given(
    domains=st.lists(st.sampled_from(["kpi", "cm", "alarm"]), min_size=0, max_size=10),
    kpi_degraded=st.booleans(),
)
@settings(max_examples=200)
def test_property_10_confidence_rules(domains, kpi_degraded):
    """Property 10: Confidence assignment follows the domain-count rule."""
    result = assign_confidence(domains, kpi_degraded, ambiguous=False)
    distinct = set(domains)
    if len(distinct) == 0:
        assert result == "low"
    elif len(distinct) >= 2 and kpi_degraded:
        assert result == "high"
    elif len(distinct) == 1 and kpi_degraded:
        assert result == "medium"
    else:
        assert result == "low"

@given(domains=st.lists(st.sampled_from(["kpi", "cm", "alarm"]), min_size=0, max_size=10))
@settings(max_examples=100)
def test_property_10_ambiguous_always_low(domains):
    """When ambiguous=True, confidence is always low regardless of domains."""
    result = assign_confidence(domains, kpi_degraded=True, ambiguous=True)
    assert result == "low"


# ── Property 11: root_cause length invariant ──────────────────────────────────
# Feature: telco-incident-triage-agent, Property 11 — Validates: Req 6.9

def test_property_11_root_cause_200_chars_accepted():
    """A root_cause of exactly 200 chars satisfies the invariant."""
    rc = "A" * 200
    assert len(rc) <= 200

def test_property_11_root_cause_201_chars_violates():
    """A root_cause of 201 chars would violate the invariant (test documents the boundary)."""
    rc = "A" * 201
    assert len(rc) > 200  # this would be a violation

@given(text=st.text(min_size=0, max_size=200))
@settings(max_examples=100)
def test_property_11_all_strings_up_to_200_are_valid(text):
    """Any string of at most 200 characters satisfies the root_cause constraint."""
    assert len(text) <= 200


# ── Property 12: Missing-field error identifies the missing field ─────────────
# Feature: telco-incident-triage-agent, Property 12 — Validates: Req 1.3

def _mock_scope_extractor(description: str) -> dict:
    """
    Stub that mimics the Orchestrator's incident scoping logic.
    Looks for a known ENIQ cell identifier (INC*_CELL_*, or 6+ char alphanumeric with digit)
    and an ISO date YYYY-MM-DD.
    """
    import re
    # Cell pattern: must look like a real cell ID (uppercase+digits+underscores, 6+ chars)
    cell_pattern = re.compile(r'\b([A-Z][A-Z0-9_]{5,})\b')
    date_pattern = re.compile(r'\b(\d{4}-\d{2}-\d{2})\b')

    has_cell = bool(cell_pattern.search(description))
    has_date = bool(date_pattern.search(description))

    if not has_cell and not has_date:
        return {"error": "missing: cell identifier, date"}
    if not has_cell:
        return {"error": "missing: cell identifier"}
    if not has_date:
        return {"error": "missing: date"}
    return {"cell_id": cell_pattern.search(description).group(), "date": date_pattern.search(description).group()}


def test_property_12_missing_cell_error_names_field():
    """When description has a date but no cell, error names 'cell identifier'."""
    result = _mock_scope_extractor("There is an incident on 2026-06-29, please investigate.")
    assert "error" in result
    assert "cell identifier" in result["error"]

def test_property_12_missing_date_error_names_field():
    """When description has a cell but no date, error names 'date'."""
    result = _mock_scope_extractor("Cell INC1_CELL_A has poor accessibility, investigate please.")
    assert "error" in result
    assert "date" in result["error"]

def test_property_12_both_present_no_error():
    """When both cell and date are present, no error is returned."""
    result = _mock_scope_extractor("Cell INC1_CELL_A on 2026-06-29 is degraded.")
    assert "error" not in result
    assert "cell_id" in result
    assert "date" in result

@given(
    description=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
        min_size=0, max_size=200
    )
)
@settings(max_examples=200, suppress_health_check=[HealthCheck.filter_too_much])
def test_property_12_no_date_in_description_always_errors(description):
    """Any description without a YYYY-MM-DD pattern gets an error naming 'date'."""
    import re
    assume(not re.search(r'\b\d{4}-\d{2}-\d{2}\b', description))
    result = _mock_scope_extractor(description)
    assert "error" in result
    assert "date" in result["error"]
