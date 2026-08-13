"""
Unit tests for triage/tools/ query functions.
Uses the synthetic scenario CSV data (INC1_CELL_A, INC2_CELL_B, etc.)
Requirements: 8.1–8.7
"""
import importlib
import pytest
from agent_tools.tools.query_lte_kpi import execute_query_lte_kpi as query_lte_kpi
from agent_tools.tools.query_nr_endc import execute_query_nr_endc as query_nr_endc
from agent_tools.tools.query_cm_config import execute_query_cm_config as query_cm_config
from agent_tools.tools.query_alarm_history import execute_query_alarm_history as query_alarm_history


# ── query_lte_kpi ─────────────────────────────────────────────────────────────

class TestQueryLteKpi:
    def test_inc1_cell_baseline_day_returns_kpis(self):
        # INC1_CELL_A has 7 baseline days; use 2026-06-22
        result = query_lte_kpi("INC1_CELL_A", "eniq_oss_1", 2026, 6, 22)
        assert "error" not in result
        assert "kpis_evaluated" in result
        assert isinstance(result["kpis_evaluated"], list)
        assert len(result["kpis_evaluated"]) > 0

    def test_inc1_cell_incident_day_accessibility_degraded(self):
        # INC1_CELL_A on 2026-06-29 should show Accessibility = ~51% (degraded)
        result = query_lte_kpi("INC1_CELL_A", "eniq_oss_1", 2026, 6, 29)
        assert "error" not in result
        access_entry = next(e for e in result["kpis_evaluated"] if e["kpi"] == "Accessibility")
        assert access_entry["status"] == "degraded", f"Expected degraded, got {access_entry}"
        assert access_entry["value"] < 95.0

    def test_inc2_cell_incident_day_availability_degraded(self):
        # INC2_CELL_B on 2026-06-29: full outage, PMCELLDOWNTIMEAUTO=86400
        result = query_lte_kpi("INC2_CELL_B", "eniq_oss_1", 2026, 6, 29)
        assert "error" not in result
        avail_entry = next(e for e in result["kpis_evaluated"] if e["kpi"] == "Cell Availability")
        assert avail_entry["status"] == "degraded"
        assert avail_entry["value"] == pytest.approx(0.0)

    def test_inc3_cell_incident_day_throughput_degraded(self):
        # INC3_CELL_C1 on 2026-06-29: throughput drops ~65% below baseline (was ~90 kbps)
        result = query_lte_kpi("INC3_CELL_C1", "eniq_oss_1", 2026, 6, 29)
        assert "error" not in result
        tp_entry = next(e for e in result["kpis_evaluated"] if e["kpi"] == "DL Throughput")
        assert tp_entry["status"] == "degraded", f"Expected degraded, got {tp_entry}"
        # Value should be significantly below baseline (30%+ drop)
        assert tp_entry["value"] < tp_entry["baseline"] * 0.75

    def test_inc4_lte_anchor_incident_day_healthy(self):
        # INC4_LTE_ANCHOR on 2026-06-30: Accessibility should be ~99.9% (healthy)
        result = query_lte_kpi("INC4_LTE_ANCHOR", "eniq_oss_1", 2026, 6, 30)
        assert "error" not in result
        access_entry = next(e for e in result["kpis_evaluated"] if e["kpi"] == "Accessibility")
        assert access_entry["status"] == "ok"
        assert access_entry["value"] >= 95.0

    def test_kpi_entries_have_required_fields(self):
        result = query_lte_kpi("INC1_CELL_A", "eniq_oss_1", 2026, 6, 22)
        for entry in result["kpis_evaluated"]:
            assert "kpi" in entry
            assert "value" in entry
            assert "baseline" in entry
            assert "status" in entry
            assert isinstance(entry["kpi"], str)
            assert entry["status"] in ("ok", "degraded", "unavailable")

    def test_raw_counters_present(self):
        result = query_lte_kpi("INC1_CELL_A", "eniq_oss_1", 2026, 6, 22)
        raw = result["raw_counters"]
        assert "PMRRCCONNESTABSUCC" in raw
        assert "PMRRCCONNESTABATT" in raw

    def test_date_returned(self):
        result = query_lte_kpi("INC1_CELL_A", "eniq_oss_1", 2026, 6, 29)
        assert result["date"]["year"] == 2026
        assert result["date"]["month"] == 6
        assert result["date"]["day"] == 29

    def test_cell_not_found_returns_error(self):
        result = query_lte_kpi("NONEXISTENT_CELL", "eniq_oss_1", 2026, 6, 29)
        assert "error" in result


# ── query_nr_endc ─────────────────────────────────────────────────────────────

class TestQueryNrEndc:
    def test_inc4_nr_baseline_day_healthy(self):
        # INC4_NR_D baseline: EN-DC > 90% (healthy). Use first available day.
        result = query_nr_endc("INC4_NR_D", "eniq_oss_1", 2026, 6, 22)
        # If April data exists use that, otherwise try June early days
        if "error" in result:
            result = query_nr_endc("INC4_NR_D", "eniq_oss_1", 2026, 4, 1)
        assert "error" not in result, f"No NR data found: {result}"
        assert len(result["kpis_evaluated"]) == 1
        entry = result["kpis_evaluated"][0]
        assert entry["kpi"] == "EN-DC Setup Success Rate"
        val = entry["value"]
        if val is not None:
            assert val >= 90.0, f"Baseline EN-DC should be >= 90%, got {val}"

    def test_inc4_nr_incident_day_degraded(self):
        # INC4_NR_D on 2026-06-30: EN-DC drops to ~55% (degraded below 90%)
        result = query_nr_endc("INC4_NR_D", "eniq_oss_1", 2026, 6, 30)
        assert "error" not in result
        entry = result["kpis_evaluated"][0]
        assert entry["status"] == "degraded", f"Expected degraded EN-DC on incident day, got {entry}"
        if entry["value"] is not None:
            assert entry["value"] < 90.0

    def test_kpi_entry_has_required_fields(self):
        result = query_nr_endc("INC4_NR_D", "eniq_oss_1", 2026, 6, 30)
        entry = result["kpis_evaluated"][0]
        assert "kpi" in entry
        assert "value" in entry
        assert "baseline" in entry
        assert "status" in entry
        assert entry["status"] in ("ok", "degraded", "unavailable")

    def test_raw_counters_present(self):
        result = query_nr_endc("INC4_NR_D", "eniq_oss_1", 2026, 6, 30)
        raw = result["raw_counters"]
        assert "pmEndcSetupUeSucc" in raw
        assert "pmEndcSetupUeAtt" in raw

    def test_cell_not_found_returns_error(self):
        result = query_nr_endc("NONEXISTENT_NR", "eniq_oss_1", 2026, 6, 30)
        assert "error" in result

    def test_endc_value_in_range(self):
        result = query_nr_endc("INC4_NR_D", "eniq_oss_1", 2026, 6, 30)
        val = result["kpis_evaluated"][0]["value"]
        if val is not None:
            assert 0.0 <= val <= 100.0


# ── query_cm_config ───────────────────────────────────────────────────────────

class TestQueryCmConfig:
    def test_inc1_cell_has_config_change_before_incident(self):
        # INC1_CELL_A had a CM change on 2026-06-27 (before 2026-06-29 incident)
        result = query_cm_config("INC1_CELL_A", "eniq_oss_1", "2026-06-29", days_back=7)
        assert "changes" in result
        assert result["num_records"] >= 1
        # The change on 2026-06-27 should appear
        datetimes = [c["DATETIME_ID"] for c in result["changes"]]
        assert any("2026-06-27" in dt for dt in datetimes)

    def test_inc1_cell_config_shows_locked_state(self):
        result = query_cm_config("INC1_CELL_A", "eniq_oss_1", "2026-06-29", days_back=7)
        # The 2026-06-27 record has ADMINISTRATIVESTATE=0 (locked)
        locked = [c for c in result["changes"] if "2026-06-27" in c.get("DATETIME_ID", "")]
        assert len(locked) >= 1
        assert str(locked[0]["ADMINISTRATIVESTATE"]) == "0"

    def test_inc2_cell_no_changes_near_incident(self):
        # INC2_CELL_B has no CM record within 7 days before 2026-06-29
        result = query_cm_config("INC2_CELL_B", "eniq_oss_1", "2026-06-29", days_back=7)
        assert "changes" in result
        assert result["num_records"] == 0  # no recent CM changes = outage, not config change

    def test_inc3_cells_no_changes(self):
        # INC3 cells have no CM changes — confirming interference scenario
        for cell in ["INC3_CELL_C1", "INC3_CELL_C2", "INC3_CELL_C3"]:
            result = query_cm_config(cell, "eniq_oss_1", "2026-06-29", days_back=7)
            assert result["num_records"] == 0, f"{cell} should have no recent CM changes"

    def test_window_keys_present(self):
        result = query_cm_config("INC1_CELL_A", "eniq_oss_1", "2026-06-29")
        assert "from" in result["window"]
        assert "to" in result["window"]

    def test_changes_have_correct_columns(self):
        result = query_cm_config("INC1_CELL_A", "eniq_oss_1", "2026-06-29", days_back=10)
        if result["changes"]:
            change = result["changes"][0]
            assert "DATETIME_ID" in change
            assert "ADMINISTRATIVESTATE" in change
            assert "DLCHANNELBANDWIDTH" in change

    def test_cell_not_found_returns_empty_changes(self):
        result = query_cm_config("NONEXISTENT_CM", "eniq_oss_1", "2026-06-29")
        assert result["changes"] == []
        assert result["num_records"] == 0


# ── query_alarm_history ───────────────────────────────────────────────────────

class TestQueryAlarmHistory:
    def test_inc2_cell_outage_day_shows_full_downtime(self):
        # INC2_CELL_B on 2026-06-29: PMCELLDOWNTIMEAUTO=86400
        result = query_alarm_history("INC2_CELL_B", "eniq_oss_1", 2026, 6, 29)
        assert "error" not in result
        assert result["PMCELLDOWNTIMEAUTO"] == 86400
        assert result["has_downtime"] is True
        assert result["availability_pct"] == pytest.approx(0.0)

    def test_healthy_cell_no_downtime(self):
        # INC1_CELL_A on baseline day 2026-06-22: 0 downtime
        result = query_alarm_history("INC1_CELL_A", "eniq_oss_1", 2026, 6, 22)
        assert "error" not in result
        assert result["PMCELLDOWNTIMEAUTO"] == 0
        assert result["PMCELLDOWNTIMEMAN"] == 0
        assert result["availability_pct"] == pytest.approx(100.0)

    def test_cell_id_returned(self):
        result = query_alarm_history("INC1_CELL_A", "eniq_oss_1", 2026, 6, 22)
        assert result["cell_id"] == "INC1_CELL_A"

    def test_alarms_key_present(self):
        result = query_alarm_history("INC1_CELL_A", "eniq_oss_1", 2026, 6, 22)
        assert "alarms" in result
        assert isinstance(result["alarms"], list)

    def test_cell_not_found_returns_error(self):
        result = query_alarm_history("NONEXISTENT_ALARM", "eniq_oss_1", 2026, 6, 29)
        assert "error" in result

    def test_synthetic_alarms_injected(self):
        ah_module = importlib.import_module("agent_tools.tools.query_alarm_history")
        original = ah_module.SYNTHETIC_ALARMS[:]
        ah_module.SYNTHETIC_ALARMS = [{
            "alarm_id": "TEST-001",
            "EUTRANCELLFDD": "INC2_CELL_B",
            "alarm_name": "Backhaul Link Down",
            "severity": "Critical",
            "start_time": "2026-06-29T00:00:00Z",
            "end_time": "2026-06-29T23:59:59Z",
            "status": "cleared",
        }]
        result = query_alarm_history("INC2_CELL_B", "eniq_oss_1", 2026, 6, 29)
        assert any(a["alarm_id"] == "TEST-001" for a in result["alarms"])
        # Restore
        ah_module.SYNTHETIC_ALARMS = original
