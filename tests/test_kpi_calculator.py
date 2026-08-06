"""
Unit tests for triage/kpi_calculator.py
Requirements: 2.1–2.9, 3.1–3.9, 12.1–12.4
"""
import pytest
import statistics
from triage.kpi_calculator import (
    KPICalculator,
    ACCESSIBILITY_ABSOLUTE_THRESHOLD,
    RETAINABILITY_THRESHOLD,
    AVAILABILITY_THRESHOLD,
    ENDC_THRESHOLD,
)


@pytest.fixture
def calc():
    return KPICalculator()


# ── Formula 1: Accessibility ─────────────────────────────────────────────────

class TestComputeAccessibility:
    def test_known_value(self, calc):
        # From lte_kpi_sample.csv row for BC5501XD:
        # PMRRCCONNESTABSUCC=36500, PMRRCCONNESTABATT=36515, PMRRCCONNESTABATTREATT=13
        # PMS1SIGCONNESTABSUCC=36500, PMS1SIGCONNESTABATT=36500
        # PMERABESTABSUCCINIT=64016, PMERABESTABATTINIT=64019
        result = calc.compute_accessibility(36500, 36515, 13, 36500, 36500, 64016, 64019)
        assert result is not None
        assert 90.0 <= result <= 100.0

    def test_zero_rrc_denominator(self, calc):
        # att == reatt → denom = 0 → None
        result = calc.compute_accessibility(100, 200, 200, 100, 100, 100, 100)
        assert result is None

    def test_zero_s1_att(self, calc):
        result = calc.compute_accessibility(100, 200, 50, 100, 0, 100, 100)
        assert result is None

    def test_zero_erab_att(self, calc):
        result = calc.compute_accessibility(100, 200, 50, 100, 100, 100, 0)
        assert result is None

    def test_none_inputs(self, calc):
        result = calc.compute_accessibility(None, 100, 0, 100, 100, 100, 100)
        assert result is None

    def test_perfect_accessibility(self, calc):
        # All counters equal → 100%
        result = calc.compute_accessibility(1000, 1000, 0, 1000, 1000, 1000, 1000)
        assert result == pytest.approx(100.0)

    def test_result_in_range(self, calc):
        result = calc.compute_accessibility(900, 1000, 100, 900, 1000, 900, 1000)
        assert result is not None
        assert 0.0 <= result <= 100.0


# ── Formula 2: Retainability ──────────────────────────────────────────────────

class TestComputeRetainability:
    def test_known_value(self, calc):
        # abnormal=38, normal=62554 → very low retainability (good)
        result = calc.compute_retainability(38, 62554)
        assert result is not None
        assert 0.0 <= result <= 100.0
        assert result < 1.0  # should be very small

    def test_zero_denominator(self, calc):
        result = calc.compute_retainability(0, 0)
        assert result is None

    def test_none_inputs(self, calc):
        result = calc.compute_retainability(None, 100)
        assert result is None

    def test_all_abnormal(self, calc):
        result = calc.compute_retainability(100, 0)
        assert result == pytest.approx(100.0)

    def test_no_abnormal(self, calc):
        result = calc.compute_retainability(0, 1000)
        assert result == pytest.approx(0.0)


# ── Formula 3: DL Throughput ──────────────────────────────────────────────────

class TestComputeDlThroughput:
    def test_known_value(self, calc):
        # (214509811 - 72954092) / 1892457 = ~74.8 kbps
        result = calc.compute_dl_throughput(214509811, 72954092, 1892457)
        assert result is not None
        assert result > 0

    def test_zero_denominator(self, calc):
        result = calc.compute_dl_throughput(1000, 500, 0)
        assert result is None

    def test_none_inputs(self, calc):
        result = calc.compute_dl_throughput(None, 500, 1000)
        assert result is None

    def test_equal_volumes(self, calc):
        result = calc.compute_dl_throughput(1000, 1000, 1000)
        assert result == pytest.approx(0.0)


# ── Formula 4: Cell Availability ─────────────────────────────────────────────

class TestComputeCellAvailability:
    def test_full_availability(self, calc):
        val, flag = calc.compute_cell_availability(0, 0, 86400)
        assert val == pytest.approx(100.0)
        assert flag is False

    def test_zero_period_duration(self, calc):
        val, flag = calc.compute_cell_availability(100, 0, 0)
        assert val is None
        assert flag is False

    def test_none_inputs(self, calc):
        val, flag = calc.compute_cell_availability(None, 0, 86400)
        assert val is None
        assert flag is False

    def test_availability_exactly_99(self, calc):
        # 1% downtime of 86400 = 864 seconds
        downtime = int(86400 * 0.01)
        val, flag = calc.compute_cell_availability(downtime, 0, 86400)
        assert val is not None
        assert val == pytest.approx(99.0, abs=0.01)
        assert flag is False

    def test_capping_when_downtime_exceeds_period(self, calc):
        # downtime 90000 > period 86400 → cap at 100.0, flag=True
        val, flag = calc.compute_cell_availability(90000, 0, 86400)
        assert val == pytest.approx(100.0)
        assert flag is True

    def test_capping_combined_downtime(self, calc):
        # auto + man > period
        val, flag = calc.compute_cell_availability(50000, 40000, 86400)
        assert val == pytest.approx(100.0)
        assert flag is True

    def test_partial_downtime(self, calc):
        # 50% downtime
        val, flag = calc.compute_cell_availability(43200, 0, 86400)
        assert val == pytest.approx(50.0)
        assert flag is False


# ── Formula 5: DL PDCP DRB Latency ───────────────────────────────────────────

class TestComputeDlLatency:
    def test_known_formula(self, calc):
        # 1000 / 100 / 10 = 1.0 ms
        result = calc.compute_dl_latency(1000, 100)
        assert result == pytest.approx(1.0)

    def test_zero_denominator(self, calc):
        result = calc.compute_dl_latency(1000, 0)
        assert result is None

    def test_none_inputs(self, calc):
        result = calc.compute_dl_latency(None, 100)
        assert result is None


# ── Formula 6: EN-DC Setup Success Rate ──────────────────────────────────────

class TestComputeEndcSuccessRate:
    def test_known_value(self, calc):
        # From nr_endc_sample.csv: EPBNW → succ=31, att=34
        result = calc.compute_endc_success_rate(31, 34)
        assert result is not None
        expected = 100.0 * (31 / 34)
        assert result == pytest.approx(expected)

    def test_zero_att(self, calc):
        result = calc.compute_endc_success_rate(0, 0)
        assert result is None

    def test_none_inputs(self, calc):
        result = calc.compute_endc_success_rate(None, 100)
        assert result is None

    def test_perfect(self, calc):
        result = calc.compute_endc_success_rate(100, 100)
        assert result == pytest.approx(100.0)

    def test_range(self, calc):
        result = calc.compute_endc_success_rate(50, 100)
        assert 0.0 <= result <= 100.0


# ── Baseline computation ──────────────────────────────────────────────────────

class TestComputeBaseline:
    def test_empty_list(self, calc):
        assert calc.compute_baseline([]) is None

    def test_single_element(self, calc):
        assert calc.compute_baseline([42.0]) == 42.0

    def test_odd_length(self, calc):
        vals = [1.0, 3.0, 5.0]
        assert calc.compute_baseline(vals) == statistics.median(vals)

    def test_even_length(self, calc):
        vals = [1.0, 2.0, 3.0, 4.0]
        assert calc.compute_baseline(vals) == statistics.median(vals)

    def test_consistent_with_statistics_median(self, calc):
        vals = [10.5, 20.3, 15.8, 8.1, 30.0]
        assert calc.compute_baseline(vals) == pytest.approx(statistics.median(vals))


# ── Degradation flagging ──────────────────────────────────────────────────────

class TestFlagDegradation:
    # Accessibility
    def test_accessibility_below_absolute_threshold(self, calc):
        assert calc.flag_degradation("Accessibility", 94.9, None) == "degraded"

    def test_accessibility_at_threshold_ok(self, calc):
        assert calc.flag_degradation("Accessibility", 95.0, None) == "ok"

    def test_accessibility_relative_degraded(self, calc):
        # value=95.0, baseline=101.0 → baseline-value=6.0 > 5.0 → degraded
        assert calc.flag_degradation("Accessibility", 95.0, 101.0) == "degraded"

    def test_accessibility_relative_ok_at_threshold(self, calc):
        # value=95.0, baseline=100.0 → baseline-value=5.0 ≤ 5.0 → ok
        assert calc.flag_degradation("Accessibility", 95.0, 100.0) == "ok"

    def test_accessibility_none_value(self, calc):
        assert calc.flag_degradation("Accessibility", None, 95.0) == "unavailable"

    # Retainability
    def test_retainability_above_threshold(self, calc):
        assert calc.flag_degradation("Retainability", 2.1, None) == "degraded"

    def test_retainability_at_threshold_ok(self, calc):
        assert calc.flag_degradation("Retainability", 2.0, None) == "ok"

    def test_retainability_none(self, calc):
        assert calc.flag_degradation("Retainability", None, None) == "unavailable"

    # DL Throughput
    def test_dl_throughput_degraded(self, calc):
        # value < baseline * 0.70
        assert calc.flag_degradation("DL Throughput", 69.9, 100.0) == "degraded"

    def test_dl_throughput_ok_at_threshold(self, calc):
        assert calc.flag_degradation("DL Throughput", 70.0, 100.0) == "ok"

    def test_dl_throughput_no_baseline(self, calc):
        assert calc.flag_degradation("DL Throughput", 50.0, None) == "unavailable"

    # Cell Availability
    def test_availability_below_threshold(self, calc):
        assert calc.flag_degradation("Cell Availability", 98.9, None) == "degraded"

    def test_availability_at_threshold_ok(self, calc):
        assert calc.flag_degradation("Cell Availability", 99.0, None) == "ok"

    def test_availability_none(self, calc):
        assert calc.flag_degradation("Cell Availability", None, None) == "unavailable"

    # DL PDCP DRB Latency
    def test_latency_degraded(self, calc):
        # value > baseline * 1.30
        assert calc.flag_degradation("DL PDCP DRB Latency", 131.0, 100.0) == "degraded"

    def test_latency_ok_at_threshold(self, calc):
        assert calc.flag_degradation("DL PDCP DRB Latency", 130.0, 100.0) == "ok"

    def test_latency_no_baseline(self, calc):
        assert calc.flag_degradation("DL PDCP DRB Latency", 100.0, None) == "unavailable"

    # EN-DC
    def test_endc_below_threshold(self, calc):
        assert calc.flag_degradation("EN-DC Setup Success Rate", 89.9, None) == "degraded"

    def test_endc_at_threshold_ok(self, calc):
        assert calc.flag_degradation("EN-DC Setup Success Rate", 90.0, None) == "ok"

    def test_endc_none(self, calc):
        assert calc.flag_degradation("EN-DC Setup Success Rate", None, None) == "unavailable"
