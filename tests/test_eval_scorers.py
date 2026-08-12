"""
Unit tests for eval/scorers.py — T1–T5 scoring functions.
Requirements: 9.1, 9.3
"""
import pytest
from eval.scorers import score_t1, score_t2, score_t3, score_t4, score_t5


# ── T1: Schema understanding ──────────────────────────────────────────────────

class TestScoreT1:
    def test_exact_match_returns_1(self):
        assert score_t1("PMRRCCONNESTABSUCC is the counter", "PMRRCCONNESTABSUCC") == 1

    def test_case_insensitive_match_returns_1(self):
        assert score_t1("pmrrcconnestabsucc is the counter", "PMRRCCONNESTABSUCC") == 1

    def test_no_match_returns_0(self):
        assert score_t1("some other response", "PMRRCCONNESTABSUCC") == 0

    def test_empty_expected_matches_anything(self):
        assert score_t1("any response", "") == 1

    def test_empty_response_no_match(self):
        assert score_t1("", "PMRRCCONNESTABSUCC") == 0


# ── T2: KPI calculation ───────────────────────────────────────────────────────

class TestScoreT2:
    def test_exact_match_returns_1(self):
        assert score_t2(95.5, 95.5) == 1

    def test_within_tolerance_returns_1(self):
        assert score_t2(95.505, 95.5, tolerance=0.01) == 1

    def test_at_tolerance_boundary_returns_1(self):
        # value is within tolerance (difference = 0.005 < 0.01)
        assert score_t2(95.505, 95.5, tolerance=0.01) == 1

    def test_just_outside_tolerance_returns_0(self):
        # value is 0.02 away — clearly outside ±0.01
        assert score_t2(95.5 + 0.02, 95.5, tolerance=0.01) == 0

    def test_none_computed_returns_0(self):
        assert score_t2(None, 95.5) == 0

    def test_negative_tolerance_distance_within(self):
        assert score_t2(95.495, 95.5, tolerance=0.01) == 1

    def test_large_difference_returns_0(self):
        assert score_t2(10.0, 95.5) == 0


# ── T3: Multi-table join ──────────────────────────────────────────────────────

class TestScoreT3:
    def test_matching_sets_returns_1(self):
        result_rows = [{"cell": "BC5501XD"}, {"cell": "C75ABX4"}]
        expected_rows = [{"cell": "C75ABX4"}, {"cell": "BC5501XD"}]
        assert score_t3(result_rows, expected_rows, "cell") == 1

    def test_non_matching_sets_returns_0(self):
        result_rows = [{"cell": "BC5501XD"}]
        expected_rows = [{"cell": "C75ABX4"}]
        assert score_t3(result_rows, expected_rows, "cell") == 0

    def test_subset_returns_0(self):
        result_rows = [{"cell": "BC5501XD"}]
        expected_rows = [{"cell": "BC5501XD"}, {"cell": "C75ABX4"}]
        assert score_t3(result_rows, expected_rows, "cell") == 0

    def test_empty_both_returns_1(self):
        assert score_t3([], [], "cell") == 1

    def test_extra_in_result_returns_0(self):
        result_rows = [{"cell": "BC5501XD"}, {"cell": "C75ABX4"}, {"cell": "EXTRA"}]
        expected_rows = [{"cell": "BC5501XD"}, {"cell": "C75ABX4"}]
        assert score_t3(result_rows, expected_rows, "cell") == 0


# ── T4: RCA reasoning ─────────────────────────────────────────────────────────

class TestScoreT4:
    def test_score_3_category_and_keyword_match(self):
        rca = {
            "root_cause": "Recent config_change on cell altered bandwidth",
            "evidence": ["DLCHANNELBANDWIDTH changed from 5000 to 10000"],
        }
        assert score_t4(rca, "config_change", ["DLCHANNELBANDWIDTH"]) == 3

    def test_score_2_category_only_no_keyword(self):
        rca = {
            "root_cause": "config_change detected in CM history",
            "evidence": ["Some evidence without keyword"],
        }
        assert score_t4(rca, "config_change", ["DLCHANNELBANDWIDTH"]) == 2

    def test_score_1_keyword_only_no_category(self):
        rca = {
            "root_cause": "Unknown root cause",
            "evidence": ["DLCHANNELBANDWIDTH was modified"],
        }
        assert score_t4(rca, "config_change", ["DLCHANNELBANDWIDTH"]) == 1

    def test_score_0_neither_matches(self):
        rca = {
            "root_cause": "Some unrelated reason",
            "evidence": ["unrelated evidence"],
        }
        assert score_t4(rca, "config_change", ["DLCHANNELBANDWIDTH"]) == 0

    def test_score_outage_scenario(self):
        rca = {
            "root_cause": "Cell outage detected — PMCELLDOWNTIMEAUTO spike",
            "evidence": ["PMCELLDOWNTIMEAUTO=86400", "Backhaul Link Down alarm"],
        }
        assert score_t4(rca, "outage", ["PMCELLDOWNTIMEAUTO", "Backhaul Link Down"]) == 3

    def test_empty_rca_returns_0(self):
        assert score_t4({}, "config_change", ["DLCHANNELBANDWIDTH"]) == 0

    def test_none_root_cause_handled(self):
        rca = {"root_cause": None, "evidence": []}
        assert score_t4(rca, "config_change", ["DLCHANNELBANDWIDTH"]) == 0


# ── T5: SQL generation ────────────────────────────────────────────────────────

class TestScoreT5:
    def test_all_tables_and_joins_present_returns_1(self):
        sql = """
        SELECT * FROM lte_kpi_sample
        JOIN cm_config_sample ON lte_kpi_sample.eutrancellfdd = cm_config_sample.eutrancellfdd
        WHERE eutrancellfdd = 'BC5501XD'
        """
        assert score_t5(sql, ["lte_kpi_sample", "cm_config_sample"], ["eutrancellfdd"]) == 1

    def test_missing_table_returns_0(self):
        sql = "SELECT * FROM lte_kpi_sample WHERE eutrancellfdd = 'BC5501XD'"
        assert score_t5(sql, ["lte_kpi_sample", "cm_config_sample"], ["eutrancellfdd"]) == 0

    def test_missing_join_key_returns_0(self):
        sql = "SELECT * FROM lte_kpi_sample JOIN cm_config_sample ON 1=1"
        assert score_t5(sql, ["lte_kpi_sample", "cm_config_sample"], ["eutrancellfdd"]) == 0

    def test_empty_requirements_returns_1(self):
        assert score_t5("SELECT 1", [], []) == 1

    def test_case_insensitive_matching(self):
        sql = "SELECT * FROM LTE_KPI_SAMPLE WHERE EUTRANCELLFDD = 'BC5501XD'"
        assert score_t5(sql, ["lte_kpi_sample"], ["eutrancellfdd"]) == 1
