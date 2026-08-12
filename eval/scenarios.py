# eval/scenarios.py
"""
Scripted incident scenarios (INC-1 through INC-4) with injected ground-truth root causes.
Requirements: 7.1–7.6, 9.1
"""
from dataclasses import dataclass, field


@dataclass
class ScriptedIncident:
    """Represents a single scripted incident scenario for evaluation."""
    id: str                                        # "INC-1" .. "INC-4"
    description: str                               # natural-language input string
    ground_truth_root_cause_category: str          # "config_change" | "outage" | "interference" | "endc"
    ground_truth_evidence_keywords: list[str]      # counter/param names that must appear in evidence
    injected_alarms: list[dict] = field(default_factory=list)  # added to SYNTHETIC_ALARMS before run


SCENARIOS: list[ScriptedIncident] = [
    ScriptedIncident(
        id="INC-1",
        description=(
            "Cell INC1_CELL_A on eniq_oss_1 is showing a significant accessibility drop "
            "on 2026-06-29. Baseline was healthy the previous 7 days. Please investigate."
        ),
        ground_truth_root_cause_category="config_change",
        ground_truth_evidence_keywords=["ADMINISTRATIVESTATE", "DLCHANNELBANDWIDTH", "2026-06-27"],
        injected_alarms=[],
    ),
    ScriptedIncident(
        id="INC-2",
        description=(
            "Cell INC2_CELL_B on eniq_oss_1 went completely unavailable on 2026-06-29. "
            "Suspected outage — availability collapsed to 0%. Please investigate."
        ),
        ground_truth_root_cause_category="outage",
        ground_truth_evidence_keywords=["PMCELLDOWNTIMEAUTO", "PMCELLDOWNTIMEMAN", "Backhaul Link Down"],
        injected_alarms=[{
            "alarm_id": "ALM-INC2-001",
            "EUTRANCELLFDD": "INC2_CELL_B",
            "alarm_name": "Backhaul Link Down",
            "severity": "Critical",
            "start_time": "2026-06-29T00:00:00Z",
            "end_time": "2026-06-29T23:59:59Z",
            "status": "cleared",
        }],
    ),
    ScriptedIncident(
        id="INC-3",
        description=(
            "Cells INC3_CELL_C1, INC3_CELL_C2, and INC3_CELL_C3 on eNodeB eNB_INC3 / eniq_oss_1 "
            "are all showing DL throughput degradation on 2026-06-29. "
            "No local config changes suspected. Please investigate."
        ),
        ground_truth_root_cause_category="interference",
        ground_truth_evidence_keywords=["PMPDCPVOLDLDRB", "PMUETHPTIMEDL", "eNB_INC3"],
        injected_alarms=[],
    ),
    ScriptedIncident(
        id="INC-4",
        description=(
            "NR cell INC4_NR_D on eniq_oss_1 is reporting EN-DC setup failures on 2026-06-30. "
            "EN-DC success rate dropped significantly. LTE anchor cell INC4_LTE_ANCHOR appears healthy. "
            "Please investigate."
        ),
        ground_truth_root_cause_category="endc",
        ground_truth_evidence_keywords=["pmEndcSetupUeSucc", "pmEndcSetupUeAtt", "INC4_NR_D"],
        injected_alarms=[],
    ),
]
