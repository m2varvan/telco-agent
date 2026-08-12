"""
Synthetic ENIQ Data Generator — Rogers AI for Networks
=======================================================
Generates realistic, schema-faithful CSVs for the Network Incident Triage Agent.

DATASET_VERSION is stamped into every generated file header as a comment.
When you connect to live ENIQ in the future, replace these CSVs with a DuckDB
view over the real tables — the column names are identical.

Generated files:
  sample_data/lte_kpi_sample.csv        ~2700 rows (30 cells × 90 days)
  sample_data/nr_endc_sample.csv        ~540 rows  (6 NR cells × 90 days)
  sample_data/cm_config_sample.csv      ~120 rows  (30 cells × 4 config snapshots)
  sample_data/alarm_history.csv         ~80 alarm records

Scenarios injected:
  INC-1  Config change (CELLBARRED + ADMINSTATE + BW) → accessibility drop
  INC-2  Backhaul link down → full availability collapse
  INC-3  Interference on co-site → multi-cell throughput drop
  INC-4  EN-DC 5G NSA failures → EN-DC rate drop, LTE anchor healthy
  INC-5  Ambiguous / partial evidence (for uncertainty testing)

Time-locking:
  DATASET_VERSION and GENERATED_AT are written to sample_data/dataset_manifest.json
  so evaluation runs can be pinned to a specific dataset state.

Usage:
  python sample_data/generate_synthetic_data.py          # regenerate all
  python sample_data/generate_synthetic_data.py --seed 99  # reproducible
"""

from __future__ import annotations
import argparse
import csv
import json
import math
import os
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# ── Version stamp ──────────────────────────────────────────────────────────────
DATASET_VERSION = "synthetic_eniq_v2"
SCHEMA_VERSION  = "eniq_ericsson_2026"

# ── Date window ────────────────────────────────────────────────────────────────
START_DATE = date(2026, 4, 1)
END_DATE   = date(2026, 6, 30)
PERIOD_DURATION = 86400  # daily ROP in seconds

# ── OSS ────────────────────────────────────────────────────────────────────────
OSS_ID = "eniq_oss_1"

# ── Cell topology ──────────────────────────────────────────────────────────────
# 6 eNodeBs, 30 LTE cells total (4-5 per eNB), 6 NR cells
CELLS = [
    # eNB_INC1 — config-change scenario cell + 3 healthy neighbours
    {"enb": "eNB_INC1", "cell": "INC1_CELL_A", "band": 3, "bw": 20000, "lat": 43.700110, "lon": -79.416298,  "traffic": "high",   "scenario": "inc1"},
    {"enb": "eNB_INC1", "cell": "INC1_CELL_B", "band": 3, "bw": 20000, "lat": 43.701100, "lon": -79.415200,  "traffic": "medium", "scenario": "healthy"},
    {"enb": "eNB_INC1", "cell": "INC1_CELL_C", "band": 7, "bw": 15000, "lat": 43.699500, "lon": -79.417000,  "traffic": "low",    "scenario": "healthy"},
    {"enb": "eNB_INC1", "cell": "INC1_CELL_D", "band": 7, "bw": 15000, "lat": 43.702000, "lon": -79.414500,  "traffic": "medium", "scenario": "healthy"},

    # eNB_INC2 — outage scenario cell + 3 healthy neighbours
    {"enb": "eNB_INC2", "cell": "INC2_CELL_B", "band": 7, "bw": 20000, "lat": 43.642567, "lon": -79.387054,  "traffic": "medium", "scenario": "inc2"},
    {"enb": "eNB_INC2", "cell": "INC2_CELL_C", "band": 7, "bw": 20000, "lat": 43.643500, "lon": -79.386000,  "traffic": "medium", "scenario": "healthy"},
    {"enb": "eNB_INC2", "cell": "INC2_CELL_D", "band": 3, "bw": 15000, "lat": 43.641800, "lon": -79.388200,  "traffic": "low",    "scenario": "healthy"},
    {"enb": "eNB_INC2", "cell": "INC2_CELL_E", "band": 2, "bw": 10000, "lat": 43.644000, "lon": -79.385500,  "traffic": "low",    "scenario": "healthy"},

    # eNB_INC3 — interference scenario (all 5 cells degraded same day)
    {"enb": "eNB_INC3", "cell": "INC3_CELL_C1", "band": 2, "bw": 20000, "lat": 43.653226, "lon": -79.383184, "traffic": "high",   "scenario": "inc3"},
    {"enb": "eNB_INC3", "cell": "INC3_CELL_C2", "band": 2, "bw": 20000, "lat": 43.654000, "lon": -79.382000, "traffic": "high",   "scenario": "inc3"},
    {"enb": "eNB_INC3", "cell": "INC3_CELL_C3", "band": 2, "bw": 20000, "lat": 43.652500, "lon": -79.384000, "traffic": "medium", "scenario": "inc3"},
    {"enb": "eNB_INC3", "cell": "INC3_CELL_C4", "band": 7, "bw": 15000, "lat": 43.655000, "lon": -79.381000, "traffic": "medium", "scenario": "inc3"},
    {"enb": "eNB_INC3", "cell": "INC3_CELL_C5", "band": 3, "bw": 20000, "lat": 43.651800, "lon": -79.385000, "traffic": "low",    "scenario": "inc3"},

    # eNB_INC4 — EN-DC scenario LTE anchor + 2 neighbours
    {"enb": "eNB_INC4", "cell": "INC4_LTE_ANCHOR", "band": 3, "bw": 20000, "lat": 43.677220, "lon": -79.347015, "traffic": "high", "scenario": "inc4_anchor"},
    {"enb": "eNB_INC4", "cell": "INC4_CELL_X",     "band": 7, "bw": 15000, "lat": 43.678000, "lon": -79.346000, "traffic": "medium", "scenario": "healthy"},
    {"enb": "eNB_INC4", "cell": "INC4_CELL_Y",     "band": 2, "bw": 10000, "lat": 43.676500, "lon": -79.348000, "traffic": "low",    "scenario": "healthy"},

    # eNB_GENERAL1 — healthy background cells (various traffic)
    {"enb": "eNB_GEN1", "cell": "GEN1_CELL_A", "band": 3, "bw": 20000, "lat": 43.660000, "lon": -79.370000, "traffic": "high",   "scenario": "healthy"},
    {"enb": "eNB_GEN1", "cell": "GEN1_CELL_B", "band": 7, "bw": 15000, "lat": 43.661000, "lon": -79.369000, "traffic": "medium", "scenario": "healthy"},
    {"enb": "eNB_GEN1", "cell": "GEN1_CELL_C", "band": 2, "bw": 20000, "lat": 43.659000, "lon": -79.371000, "traffic": "high",   "scenario": "healthy"},
    {"enb": "eNB_GEN1", "cell": "GEN1_CELL_D", "band": 3, "bw": 20000, "lat": 43.662000, "lon": -79.368000, "traffic": "low",    "scenario": "healthy"},

    # eNB_GENERAL2 — healthy background cells
    {"enb": "eNB_GEN2", "cell": "GEN2_CELL_A", "band": 7, "bw": 20000, "lat": 43.620000, "lon": -79.400000, "traffic": "medium", "scenario": "healthy"},
    {"enb": "eNB_GEN2", "cell": "GEN2_CELL_B", "band": 7, "bw": 20000, "lat": 43.621000, "lon": -79.399000, "traffic": "high",   "scenario": "healthy"},
    {"enb": "eNB_GEN2", "cell": "GEN2_CELL_C", "band": 3, "bw": 15000, "lat": 43.619000, "lon": -79.401000, "traffic": "medium", "scenario": "healthy"},
    {"enb": "eNB_GEN2", "cell": "GEN2_CELL_D", "band": 2, "bw": 10000, "lat": 43.622000, "lon": -79.398000, "traffic": "low",    "scenario": "healthy"},
    {"enb": "eNB_GEN2", "cell": "GEN2_CELL_E", "band": 3, "bw": 20000, "lat": 43.618000, "lon": -79.402000, "traffic": "low",    "scenario": "healthy"},

    # eNB_INC5 — ambiguous scenario (degradation but no clear cause)
    {"enb": "eNB_INC5", "cell": "INC5_CELL_F", "band": 3, "bw": 20000, "lat": 43.690000, "lon": -79.360000, "traffic": "medium", "scenario": "inc5_ambiguous"},
    {"enb": "eNB_INC5", "cell": "INC5_CELL_G", "band": 7, "bw": 15000, "lat": 43.691000, "lon": -79.359000, "traffic": "medium", "scenario": "healthy"},
    {"enb": "eNB_INC5", "cell": "INC5_CELL_H", "band": 2, "bw": 10000, "lat": 43.689000, "lon": -79.361000, "traffic": "low",    "scenario": "healthy"},
    {"enb": "eNB_INC5", "cell": "INC5_CELL_I", "band": 3, "bw": 20000, "lat": 43.692000, "lon": -79.358000, "traffic": "low",    "scenario": "healthy"},
    {"enb": "eNB_INC5", "cell": "INC5_CELL_J", "band": 7, "bw": 20000, "lat": 43.688000, "lon": -79.362000, "traffic": "high",   "scenario": "healthy"},
]

# NR cells (EN-DC paired with eNB_INC4 LTE anchor + 5 background NR cells)
NR_CELLS = [
    {"cell": "INC4_NR_D",  "enb": "eNB_INC4",  "scenario": "inc4_nr"},
    {"cell": "NR_GEN1_A",  "enb": "eNB_GEN1",  "scenario": "nr_healthy"},
    {"cell": "NR_GEN1_B",  "enb": "eNB_GEN1",  "scenario": "nr_healthy"},
    {"cell": "NR_GEN2_A",  "enb": "eNB_GEN2",  "scenario": "nr_healthy"},
    {"cell": "NR_GEN2_B",  "enb": "eNB_GEN2",  "scenario": "nr_healthy"},
    {"cell": "NR_INC5_F",  "enb": "eNB_INC5",  "scenario": "nr_healthy"},
]

# ── Scenario dates ─────────────────────────────────────────────────────────────
INC1_CONFIG_CHANGE_DATE = date(2026, 6, 27)  # CM change: CELLBARRED=1, ADMINSTATE=0
INC1_INCIDENT_DATE      = date(2026, 6, 29)  # Accessibility drop visible
INC2_OUTAGE_DATE        = date(2026, 6, 29)  # Full outage
INC3_INTERFERENCE_DATE  = date(2026, 6, 29)  # Multi-cell throughput drop
INC4_ENDC_FAIL_DATE     = date(2026, 6, 30)  # EN-DC drop
INC5_AMBIGUOUS_DATE     = date(2026, 6, 28)  # Mild degradation, no clear cause

# Also inject a mid-period minor degradation event for realism
MID_DEGRADATION_DATE    = date(2026, 5, 15)  # partial degradation on some cells


# ── Traffic-level base counters ────────────────────────────────────────────────
TRAFFIC_PROFILES = {
    "high":   {"rrc": 15000, "erab": 22000, "pdcp_vol": 800_000_000,  "thp_time": 7_000_000,  "lat_time": 350_000, "lat_pkts": 70_000},
    "medium": {"rrc": 8000,  "erab": 12000, "pdcp_vol": 450_000_000,  "thp_time": 4_000_000,  "lat_time": 200_000, "lat_pkts": 40_000},
    "low":    {"rrc": 3000,  "erab": 5000,  "pdcp_vol": 150_000_000,  "thp_time": 1_500_000,  "lat_time": 80_000,  "lat_pkts": 20_000},
}

def jitter(value: int | float, pct: float = 0.03, rng: random.Random = None) -> int:
    """Apply ±pct random jitter to a value for realism. Always returns int."""
    rng = rng or random
    delta = value * pct * (rng.random() * 2 - 1)
    return max(0, int(value + delta))

def weekday_factor(d: date) -> float:
    """Weekends have ~70% of weekday traffic."""
    return 0.70 if d.weekday() >= 5 else 1.0

def seasonal_factor(d: date) -> float:
    """Mild seasonal variation across the 90-day window."""
    day_of_year = d.timetuple().tm_yday
    return 1.0 + 0.05 * math.sin(2 * math.pi * day_of_year / 365)

def build_healthy_lte_row(
    cell: dict, d: date, rng: random.Random
) -> dict:
    """Generate one healthy daily LTE KPI row for a cell on date d."""
    p = TRAFFIC_PROFILES[cell["traffic"]]
    wf = weekday_factor(d)
    sf = seasonal_factor(d)
    scale = wf * sf

    rrc_att  = jitter(int(p["rrc"] * scale), 0.04, rng)
    rrc_reatt = max(0, jitter(int(rrc_att * 0.0005), 0.20, rng))
    rrc_succ = max(0, rrc_att - rrc_reatt - jitter(5, 0.5, rng))

    s1_att  = rrc_att
    s1_succ = max(0, s1_att - jitter(2, 0.5, rng))

    erab_att  = jitter(int(p["erab"] * scale), 0.04, rng)
    erab_succ = max(0, erab_att - jitter(int(erab_att * 0.003), 0.30, rng))
    abnormal  = jitter(int(erab_att * 0.003), 0.25, rng)
    normal    = max(0, erab_att - abnormal)

    pdcp_vol      = jitter(int(p["pdcp_vol"] * scale), 0.05, rng)
    pdcp_last_tti = jitter(int(pdcp_vol * 0.18), 0.06, rng)
    thp_time      = jitter(int(p["thp_time"] * scale), 0.04, rng)

    lat_time = jitter(int(p["lat_time"] * scale), 0.05, rng)
    lat_pkts = jitter(int(p["lat_pkts"] * scale), 0.04, rng)

    return {
        "OSS_ID": OSS_ID,
        "ENODEBFUNCTION": cell["enb"],
        "EUTRANCELLFDD": cell["cell"],
        "YEAR_ID": d.year, "MONTH_ID": d.month, "DAY_ID": d.day,
        "PERIOD_DURATION": PERIOD_DURATION,
        "PMRRCCONNESTABSUCC": rrc_succ,
        "PMRRCCONNESTABATT": rrc_att,
        "PMRRCCONNESTABATTREATT": rrc_reatt,
        "PMS1SIGCONNESTABSUCC": s1_succ,
        "PMS1SIGCONNESTABATT": s1_att,
        "PMERABESTABSUCCINIT": erab_succ,
        "PMERABESTABATTINIT": erab_att,
        "PMERABRELABNORMALENB": abnormal,
        "PMERABRELNORMALENB": normal,
        "PMPDCPVOLDLDRB": pdcp_vol,
        "PMPDCPVOLDLDRBLASTTTI": pdcp_last_tti,
        "PMUETHPTIMEDL": thp_time,
        "PMCELLDOWNTIMEAUTO": 0,
        "PMCELLDOWNTIMEMAN": 0,
        "PMPDCPLATTIMEDL": lat_time,
        "PMPDCPLATPKTTRANSDL": lat_pkts,
    }

def apply_inc1_incident(row: dict, d: date) -> dict:
    """INC-1: Post-config-change accessibility degradation (2026-06-29 only for clean eval)."""
    if d == INC1_INCIDENT_DATE:
        # CELLBARRED → ~50% accessibility drop
        row["PMRRCCONNESTABSUCC"] = int(row["PMRRCCONNESTABSUCC"] * 0.50)
        row["PMS1SIGCONNESTABSUCC"] = int(row["PMS1SIGCONNESTABSUCC"] * 0.50)
        row["PMERABESTABSUCCINIT"] = int(row["PMERABESTABSUCCINIT"] * 0.50)
        row["PMERABRELABNORMALENB"] = int(row["PMERABESTABATTINIT"] * 0.025)
        # Also retainability worsens (more abnormal releases)
        row["PMERABRELNORMALENB"] = int(row["PMERABRELNORMALENB"] * 0.85)
    return row

def apply_inc2_outage(row: dict, d: date) -> dict:
    """INC-2: Full cell outage on 2026-06-29."""
    if d == INC2_OUTAGE_DATE:
        for col in ["PMRRCCONNESTABSUCC","PMRRCCONNESTABATT","PMRRCCONNESTABATTREATT",
                    "PMS1SIGCONNESTABSUCC","PMS1SIGCONNESTABATT",
                    "PMERABESTABSUCCINIT","PMERABESTABATTINIT",
                    "PMERABRELABNORMALENB","PMERABRELNORMALENB",
                    "PMPDCPVOLDLDRB","PMPDCPVOLDLDRBLASTTTI","PMUETHPTIMEDL",
                    "PMPDCPLATTIMEDL","PMPDCPLATPKTTRANSDL"]:
            row[col] = 0
        row["PMCELLDOWNTIMEAUTO"] = PERIOD_DURATION
    # Partial outages on nearby days for realism
    elif d == INC2_OUTAGE_DATE - timedelta(days=1):
        # Day before: minor downtime hint (power fluctuation)
        row["PMCELLDOWNTIMEAUTO"] = 300  # 5 minutes
    return row

def apply_inc3_interference(row: dict, d: date) -> dict:
    """INC-3: Interference-driven throughput drop on 2026-06-29."""
    if d == INC3_INTERFERENCE_DATE:
        row["PMPDCPVOLDLDRB"] = int(row["PMPDCPVOLDLDRB"] * 0.35)
        row["PMUETHPTIMEDL"]  = int(row["PMUETHPTIMEDL"] * 0.35)
        # Latency also increases
        row["PMPDCPLATTIMEDL"] = int(row["PMPDCPLATTIMEDL"] * 1.65)
        # Retainability slightly degrades
        row["PMERABRELABNORMALENB"] = int(row["PMERABESTABATTINIT"] * 0.008)
    return row

def apply_mid_degradation(row: dict, d: date, rng: random.Random) -> dict:
    """Mid-period mild throughput dip on some cells (background noise)."""
    if d == MID_DEGRADATION_DATE:
        row["PMPDCPVOLDLDRB"] = int(row["PMPDCPVOLDLDRB"] * rng.uniform(0.78, 0.92))
    return row

def apply_inc5_ambiguous(row: dict, d: date, rng: random.Random) -> dict:
    """INC-5: Mild accessibility degradation with no clear CM cause."""
    if d == INC5_AMBIGUOUS_DATE:
        row["PMRRCCONNESTABSUCC"] = int(row["PMRRCCONNESTABSUCC"] * rng.uniform(0.88, 0.93))
        row["PMS1SIGCONNESTABSUCC"] = int(row["PMS1SIGCONNESTABSUCC"] * rng.uniform(0.88, 0.93))
        row["PMERABESTABSUCCINIT"] = int(row["PMERABESTABSUCCINIT"] * rng.uniform(0.88, 0.93))
    return row


def build_healthy_nr_row(cell: dict, d: date, rng: random.Random) -> dict:
    """Generate one healthy daily NR EN-DC row."""
    base_att  = jitter(1000, 0.06, rng)
    base_succ = max(0, int(base_att * rng.uniform(0.96, 0.99)))
    scg_att   = jitter(base_att, 0.02, rng)
    scg_succ  = max(0, int(scg_att * rng.uniform(0.96, 0.99)))
    return {
        "OSS_ID": OSS_ID,
        "NRCellCU": cell["cell"],
        "YEAR_ID": d.year, "MONTH_ID": d.month, "DAY_ID": d.day,
        "PERIOD_DURATION": PERIOD_DURATION,
        "pmEndcSetupUeSucc": base_succ,
        "pmEndcSetupUeAtt": base_att,
        "pmEndcSetupScgUeSucc": scg_succ,
        "pmEndcSetupScgUeAtt": scg_att,
        "pmCellDowntimeAuto": 0,
        "pmCellDowntimeMan": 0,
    }

def apply_inc4_endc_failure(row: dict, d: date) -> dict:
    """INC-4: EN-DC setup failure on 2026-06-30."""
    if d == INC4_ENDC_FAIL_DATE:
        att = row["pmEndcSetupUeAtt"]
        row["pmEndcSetupUeSucc"]   = int(att * 0.55)
        row["pmEndcSetupScgUeSucc"] = int(att * 0.55)
    return row


def generate_lte_kpi(rng: random.Random) -> list[dict]:
    rows = []
    all_dates = [START_DATE + timedelta(days=i)
                 for i in range((END_DATE - START_DATE).days + 1)]

    for cell in CELLS:
        for d in all_dates:
            row = build_healthy_lte_row(cell, d, rng)

            if cell["scenario"] == "inc1":
                row = apply_inc1_incident(row, d)
            elif cell["scenario"] == "inc2":
                row = apply_inc2_outage(row, d)
            elif cell["scenario"] == "inc3":
                row = apply_inc3_interference(row, d)
            elif cell["scenario"] == "inc5_ambiguous":
                row = apply_inc5_ambiguous(row, d, rng)

            # All cells get mid-period mild noise
            row = apply_mid_degradation(row, d, rng)

            rows.append(row)
    return rows


def generate_nr_endc(rng: random.Random) -> list[dict]:
    rows = []
    all_dates = [START_DATE + timedelta(days=i)
                 for i in range((END_DATE - START_DATE).days + 1)]

    for cell in NR_CELLS:
        for d in all_dates:
            row = build_healthy_nr_row(cell, d, rng)
            if cell["scenario"] == "inc4_nr":
                row = apply_inc4_endc_failure(row, d)
            rows.append(row)
    return rows


def generate_cm_config() -> list[dict]:
    """
    CM config snapshots. Multiple snapshots per cell to simulate parameter changes.
    INC-1 has a deliberate CELLBARRED + ADMINSTATE change on 2026-06-27.
    Other cells have clean histories (distractors: unrelated BW changes on different cells).
    """
    rows = []

    # Helper to build a CM row
    def cm_row(enb, cell, dt_str, admin, barred, band, bw, lat, lon):
        dt = datetime.fromisoformat(dt_str.replace("Z",""))
        return {
            "OSS_ID": OSS_ID,
            "ENODEBFUNCTION": enb,
            "EUTRANCELLFDD": cell,
            "YEAR_ID": dt.year, "MONTH_ID": dt.month, "DAY_ID": dt.day,
            "DATETIME_ID": dt_str,
            "ADMINISTRATIVESTATE": admin,
            "CELLBARRED": barred,
            "FREQBAND": band,
            "EARFCNDL": band * 400 + 100,
            "EARFCNUL": band * 400 + 100 + 18000,
            "DLCHANNELBANDWIDTH": bw,
            "LATITUDE": lat,
            "LONGITUDE": lon,
        }

    # INC-1: clean config before 2026-06-27, then incident change
    rows.append(cm_row("eNB_INC1","INC1_CELL_A","2026-04-01T00:00:00Z",1,0,3,20000,43.700110,-79.416298))
    rows.append(cm_row("eNB_INC1","INC1_CELL_A","2026-06-27T00:00:00Z",0,1,3, 5000,43.700110,-79.416298))  # ← incident

    # INC-1 neighbours: clean histories
    rows.append(cm_row("eNB_INC1","INC1_CELL_B","2026-04-01T00:00:00Z",1,0,3,20000,43.701100,-79.415200))
    rows.append(cm_row("eNB_INC1","INC1_CELL_C","2026-04-01T00:00:00Z",1,0,7,15000,43.699500,-79.417000))
    rows.append(cm_row("eNB_INC1","INC1_CELL_D","2026-04-01T00:00:00Z",1,0,7,15000,43.702000,-79.414500))

    # INC-2: no CM changes near outage date (outage is unplanned backhaul failure)
    rows.append(cm_row("eNB_INC2","INC2_CELL_B","2026-04-01T00:00:00Z",1,0,7,20000,43.642567,-79.387054))
    rows.append(cm_row("eNB_INC2","INC2_CELL_C","2026-04-01T00:00:00Z",1,0,7,20000,43.643500,-79.386000))
    rows.append(cm_row("eNB_INC2","INC2_CELL_D","2026-04-01T00:00:00Z",1,0,3,15000,43.641800,-79.388200))
    # Distractor: INC2_CELL_E had a BW change in May (unrelated to outage)
    rows.append(cm_row("eNB_INC2","INC2_CELL_E","2026-04-01T00:00:00Z",1,0,2,15000,43.644000,-79.385500))
    rows.append(cm_row("eNB_INC2","INC2_CELL_E","2026-05-10T00:00:00Z",1,0,2,10000,43.644000,-79.385500))  # distractor BW change

    # INC-3: no CM changes on interference date
    for cell_id, lat, lon in [
        ("INC3_CELL_C1",43.653226,-79.383184),("INC3_CELL_C2",43.654000,-79.382000),
        ("INC3_CELL_C3",43.652500,-79.384000),("INC3_CELL_C4",43.655000,-79.381000),
        ("INC3_CELL_C5",43.651800,-79.385000),
    ]:
        rows.append(cm_row("eNB_INC3", cell_id, "2026-04-01T00:00:00Z",1,0,2,20000,lat,lon))

    # INC-4: LTE anchor clean, NR cells not in CM table (NR uses separate table)
    rows.append(cm_row("eNB_INC4","INC4_LTE_ANCHOR","2026-04-01T00:00:00Z",1,0,3,20000,43.677220,-79.347015))
    rows.append(cm_row("eNB_INC4","INC4_CELL_X","2026-04-01T00:00:00Z",1,0,7,15000,43.678000,-79.346000))
    rows.append(cm_row("eNB_INC4","INC4_CELL_Y","2026-04-01T00:00:00Z",1,0,2,10000,43.676500,-79.348000))

    # INC-5: No recent CM change (ambiguous — slight degradation without config cause)
    rows.append(cm_row("eNB_INC5","INC5_CELL_F","2026-04-01T00:00:00Z",1,0,3,20000,43.690000,-79.360000))
    rows.append(cm_row("eNB_INC5","INC5_CELL_G","2026-04-01T00:00:00Z",1,0,7,15000,43.691000,-79.359000))
    rows.append(cm_row("eNB_INC5","INC5_CELL_H","2026-04-01T00:00:00Z",1,0,2,10000,43.689000,-79.361000))
    rows.append(cm_row("eNB_INC5","INC5_CELL_I","2026-04-01T00:00:00Z",1,0,3,20000,43.692000,-79.358000))
    rows.append(cm_row("eNB_INC5","INC5_CELL_J","2026-04-01T00:00:00Z",1,0,7,20000,43.688000,-79.362000))

    # General cells
    for enb, cell_id, lat, lon, band, bw in [
        ("eNB_GEN1","GEN1_CELL_A",43.660000,-79.370000,3,20000),
        ("eNB_GEN1","GEN1_CELL_B",43.661000,-79.369000,7,15000),
        ("eNB_GEN1","GEN1_CELL_C",43.659000,-79.371000,2,20000),
        ("eNB_GEN1","GEN1_CELL_D",43.662000,-79.368000,3,20000),
        ("eNB_GEN2","GEN2_CELL_A",43.620000,-79.400000,7,20000),
        ("eNB_GEN2","GEN2_CELL_B",43.621000,-79.399000,7,20000),
        ("eNB_GEN2","GEN2_CELL_C",43.619000,-79.401000,3,15000),
        ("eNB_GEN2","GEN2_CELL_D",43.622000,-79.398000,2,10000),
        ("eNB_GEN2","GEN2_CELL_E",43.618000,-79.402000,3,20000),
    ]:
        rows.append(cm_row(enb, cell_id, "2026-04-01T00:00:00Z",1,0,band,bw,lat,lon))

    return rows


def generate_alarm_history() -> list[dict]:
    """
    Realistic alarm history covering all 5 incident scenarios.
    Includes distractors (alarms on neighbouring cells, unrelated severities).
    """
    rows = []

    def alarm(alarm_id, cell, alarm_name, severity, start, end, status, desc):
        return {
            "alarm_id": alarm_id,
            "EUTRANCELLFDD": cell,
            "OSS_ID": OSS_ID,
            "alarm_name": alarm_name,
            "severity": severity,
            "start_time": start,
            "end_time": end,
            "status": status,
            "description": desc,
        }

    # ── INC-1: Config change alarms ────────────────────────────────────────────
    rows.append(alarm("ALM-INC1-001","INC1_CELL_A","Cell Barred Active","Major",
        "2026-06-27T08:30:00Z","2026-06-29T18:00:00Z","cleared",
        "CELLBARRED set to 1 and ADMINISTRATIVESTATE set to 0 following CM push at 08:30. Accessibility dropped from 99.88% to 51% on 2026-06-29."))
    rows.append(alarm("ALM-INC1-002","INC1_CELL_A","Accessibility Below Threshold","Major",
        "2026-06-29T00:00:00Z","2026-06-29T23:59:59Z","cleared",
        "Accessibility dropped to 51.1% against 95% threshold. Correlated with CELLBARRED change on 2026-06-27."))
    # Distractor: maintenance on neighbour cell (unrelated)
    rows.append(alarm("ALM-INC1-D01","INC1_CELL_B","Scheduled Maintenance","Info",
        "2026-06-26T02:00:00Z","2026-06-26T04:00:00Z","cleared",
        "Routine upgrade on INC1_CELL_B. No KPI impact."))

    # ── INC-2: Outage alarms ───────────────────────────────────────────────────
    rows.append(alarm("ALM-INC2-001","INC2_CELL_B","Backhaul Link Down","Critical",
        "2026-06-29T00:00:00Z","2026-06-29T23:59:59Z","cleared",
        "Fibre backhaul severed between eNB_INC2 and aggregation router. All traffic lost. PMCELLDOWNTIMEAUTO=86400s."))
    rows.append(alarm("ALM-INC2-002","INC2_CELL_B","Cell Outage","Critical",
        "2026-06-29T00:00:00Z","2026-06-29T23:59:59Z","cleared",
        "Cell completely unavailable — availability 0%. No UE could attach during full ROP period."))
    rows.append(alarm("ALM-INC2-003","INC2_CELL_B","Cell Availability Below Threshold","Critical",
        "2026-06-29T00:00:00Z","2026-06-29T23:59:59Z","cleared",
        "Cell availability fell to 0% against 99% threshold. PMCELLDOWNTIMEAUTO=86400, PERIOD_DURATION=86400."))
    # Minor alarm day before — distractor
    rows.append(alarm("ALM-INC2-D01","INC2_CELL_B","Power Fluctuation","Minor",
        "2026-06-28T14:00:00Z","2026-06-28T14:45:00Z","cleared",
        "Brief power fluctuation. Downtime < 5 minutes. No significant KPI impact."))
    # Distractor on neighbour cell
    rows.append(alarm("ALM-INC2-D02","INC2_CELL_C","High Retainability","Warning",
        "2026-06-29T06:00:00Z","2026-06-29T10:00:00Z","cleared",
        "E-RAB abnormal release rate slightly elevated on INC2_CELL_C. Not correlated with INC2_CELL_B outage."))

    # ── INC-3: Interference alarms ─────────────────────────────────────────────
    for cell_id, alarm_num in [
        ("INC3_CELL_C1","001"),("INC3_CELL_C2","002"),("INC3_CELL_C3","003"),
        ("INC3_CELL_C4","004"),("INC3_CELL_C5","005"),
    ]:
        rows.append(alarm(f"ALM-INC3-{alarm_num}", cell_id,"High Interference Detected","Major",
            "2026-06-29T06:00:00Z","2026-06-29T22:00:00Z","cleared",
            f"DL interference elevated on eNB_INC3 affecting {cell_id}. Co-site multi-cell degradation — consistent with external interference. DL throughput dropped ~65% from baseline."))

    # ── INC-4: EN-DC failure alarms ────────────────────────────────────────────
    rows.append(alarm("ALM-INC4-001","INC4_NR_D","EN-DC Setup Failure Rate High","Major",
        "2026-06-30T00:00:00Z","2026-06-30T23:59:59Z","active",
        "EN-DC setup success rate fell from 98% baseline to 55% on 2026-06-30. NR Random Access failures are the primary cause. LTE anchor INC4_LTE_ANCHOR remains healthy — confirms 5G NSA layer issue."))
    rows.append(alarm("ALM-INC4-002","INC4_NR_D","NR Random Access Failure","Major",
        "2026-06-30T00:00:00Z","2026-06-30T23:59:59Z","active",
        "pmEndcSetupUeSucc=550, pmEndcSetupUeAtt=1000. EN-DC success rate 55% against 90% threshold."))
    # INC4 LTE anchor: X2 degradation distractor (resolved before incident date)
    rows.append(alarm("ALM-INC4-D01","INC4_LTE_ANCHOR","X2 Interface Degraded","Warning",
        "2026-06-25T10:00:00Z","2026-06-25T12:00:00Z","cleared",
        "X2 interface latency elevated. Resolved at 12:00. No availability impact. Do not correlate with 2026-06-30 EN-DC failure."))

    # ── INC-5: Ambiguous — mild degradation, no clear alarm cause ─────────────
    rows.append(alarm("ALM-INC5-001","INC5_CELL_F","Accessibility Slightly Below Threshold","Warning",
        "2026-06-28T00:00:00Z","2026-06-28T23:59:59Z","cleared",
        "Accessibility dropped to 91% on 2026-06-28 — marginally below 95% threshold. No CM change found. No correlated alarm on neighbours. Cause undetermined."))
    # Distractor alarm on different cell same day
    rows.append(alarm("ALM-INC5-D01","INC5_CELL_G","Scheduled Maintenance","Info",
        "2026-06-28T03:00:00Z","2026-06-28T05:00:00Z","cleared",
        "Planned software upgrade on INC5_CELL_G. No impact on INC5_CELL_F."))

    # ── Historical background alarms ───────────────────────────────────────────
    rows.append(alarm("ALM-HIST-001","INC1_CELL_A","Scheduled Maintenance","Info",
        "2026-04-15T02:00:00Z","2026-04-15T04:00:00Z","cleared",
        "Routine software upgrade. Cell returned to service at 04:00Z. No KPI impact."))
    rows.append(alarm("ALM-HIST-002","GEN1_CELL_A","Power Fluctuation","Minor",
        "2026-05-03T14:00:00Z","2026-05-03T14:30:00Z","cleared",
        "Brief power event at GEN1 site. PMCELLDOWNTIMEAUTO < 30s. No significant impact."))
    rows.append(alarm("ALM-HIST-003","GEN2_CELL_B","Backhaul Latency Elevated","Warning",
        "2026-05-20T08:00:00Z","2026-05-20T10:00:00Z","cleared",
        "Backhaul latency briefly elevated at GEN2 site. Resolved automatically. No availability impact."))
    rows.append(alarm("ALM-HIST-004","INC2_CELL_C","Handover Failure Rate Elevated","Warning",
        "2026-05-15T12:00:00Z","2026-05-15T15:00:00Z","cleared",
        "Mid-period handover failures on INC2_CELL_C. Correlated with mid-period throughput dip. Resolved."))
    rows.append(alarm("ALM-HIST-005","INC3_CELL_C1","Temporary DL Interference","Warning",
        "2026-05-15T00:00:00Z","2026-05-15T23:59:59Z","cleared",
        "Mild interference event on 2026-05-15 (mid-period background). Not related to 2026-06-29 incident."))

    return rows


# ── Incident Ticket History Generator ──────────────────────────────────────────

TICKET_COLS = [
    "ticket_id", "EUTRANCELLFDD", "OSS_ID", "created_date", "closed_date",
    "root_cause_code", "summary", "resolution_notes", "engineer_id"
]

def generate_incident_history() -> list[dict]:
    """Generate ~25 historical incident ticket records with resolution notes."""
    tickets = [
        # INC1 history
        {
            "ticket_id": "INC-2026-0412",
            "EUTRANCELLFDD": "INC1_CELL_A",
            "OSS_ID": OSS_ID,
            "created_date": "2026-04-12T09:15:00",
            "closed_date": "2026-04-12T14:30:00",
            "root_cause_code": "CELL_BARRED_CHANGE",
            "summary": "Accessibility dropped to 0% following maintenance window.",
            "resolution_notes": "Reverted CELLBARRED parameter from 1 back to 0. Cell accessibility restored immediately.",
            "engineer_id": "ENG_8820"
        },
        {
            "ticket_id": "INC-2026-0518",
            "EUTRANCELLFDD": "INC1_CELL_A",
            "OSS_ID": OSS_ID,
            "created_date": "2026-05-18T11:00:00",
            "closed_date": "2026-05-18T16:45:00",
            "root_cause_code": "ADMIN_STATE_CHANGE",
            "summary": "Cell locked in eNodeB configuration during frequency audit.",
            "resolution_notes": "Reset ADMINISTRATIVESTATE to 1 (Unlocked) via OSS Bulk CM script.",
            "engineer_id": "ENG_4412"
        },
        # INC2 history
        {
            "ticket_id": "INC-2026-0425",
            "EUTRANCELLFDD": "INC2_CELL_B",
            "OSS_ID": OSS_ID,
            "created_date": "2026-04-25T02:10:00",
            "closed_date": "2026-04-25T08:00:00",
            "root_cause_code": "BACKHAUL_LINK_DOWN",
            "summary": "Site outage — loss of connection to MME/S-GW.",
            "resolution_notes": "Field technician dispatched. Replaced faulty SFP module on microwave backhaul unit.",
            "engineer_id": "ENG_1094"
        },
        {
            "ticket_id": "INC-2026-0530",
            "EUTRANCELLFDD": "INC2_CELL_B",
            "OSS_ID": OSS_ID,
            "created_date": "2026-05-30T14:22:00",
            "closed_date": "2026-05-30T17:10:00",
            "root_cause_code": "POWER_FAILURE",
            "summary": "Site power lost due to local grid disturbance.",
            "resolution_notes": "UPS battery backup held site for 3 hours; main power restored by hydro utility.",
            "engineer_id": "ENG_3301"
        },
        # INC3 history
        {
            "ticket_id": "INC-2026-0504",
            "EUTRANCELLFDD": "INC3_CELL_C1",
            "OSS_ID": OSS_ID,
            "created_date": "2026-05-04T10:00:00",
            "closed_date": "2026-05-04T18:00:00",
            "root_cause_code": "NEIGHBOUR_INTERFERENCE",
            "summary": "DL Throughput degradation across eNB_INC3 co-site sectors.",
            "resolution_notes": "Adjusted electrical antenna downtilt on sector 1 to minimize inter-cell interference.",
            "engineer_id": "ENG_7719"
        },
        {
            "ticket_id": "INC-2026-0505",
            "EUTRANCELLFDD": "INC3_CELL_C2",
            "OSS_ID": OSS_ID,
            "created_date": "2026-05-04T10:30:00",
            "closed_date": "2026-05-04T18:00:00",
            "root_cause_code": "NEIGHBOUR_INTERFERENCE",
            "summary": "Correlated DL throughput drop on adjacent sector C2.",
            "resolution_notes": "Co-site interference resolved together with INC3_CELL_C1 antenna tilt adjustment.",
            "engineer_id": "ENG_7719"
        },
        # INC4 NR history
        {
            "ticket_id": "INC-2026-0512",
            "EUTRANCELLFDD": "INC4_NR_D",
            "OSS_ID": OSS_ID,
            "created_date": "2026-05-12T08:00:00",
            "closed_date": "2026-05-12T13:15:00",
            "root_cause_code": "NR_RANDOM_ACCESS_FAILURE",
            "summary": "High 5G NSA EN-DC setup failure rate.",
            "resolution_notes": "Re-indexed NR RACH preamble parameters on 5G gNodeB unit. EN-DC setup success restored to 98%.",
            "engineer_id": "ENG_9011"
        },
        # INC5 history
        {
            "ticket_id": "INC-2026-0418",
            "EUTRANCELLFDD": "INC5_CELL_F",
            "OSS_ID": OSS_ID,
            "created_date": "2026-04-18T15:00:00",
            "closed_date": "2026-04-18T16:00:00",
            "root_cause_code": "UNDETERMINED",
            "summary": "Transient KPI fluctuation reported during peak traffic hour.",
            "resolution_notes": "No network fault identified; KPI returned to baseline within 1 ROP. Ticket closed as non-incident.",
            "engineer_id": "ENG_4412"
        },
    ]

    # Add general history for background cells
    for i, c in enumerate(CELLS[15:], start=100):
        tickets.append({
            "ticket_id": f"INC-2026-0{i}",
            "EUTRANCELLFDD": c["cell"],
            "OSS_ID": OSS_ID,
            "created_date": "2026-04-05T10:00:00",
            "closed_date": "2026-04-05T12:00:00",
            "root_cause_code": "ROUTINE_MAINTENANCE",
            "summary": "Scheduled firmware upgrade.",
            "resolution_notes": "Upgraded software release; cell healthy.",
            "engineer_id": "ENG_5500"
        })
    return tickets


# ── Telecom Knowledge Base Generator ──────────────────────────────────────────

def generate_telecom_knowledge(out_dir: Path) -> None:
    """Generate seed Markdown knowledge document for RAG indexing."""
    content = """# Telecom Operations & Ericsson ENIQ Knowledge Base

## 1. Ericsson PM Counters & KPI Formulas Reference

### 1.1 Accessibility — E-RAB Initial Setup Success Rate (%)
- **Definition:** The percentage of attempts to establish an initial E-RAB (E-UTRAN Radio Access Bearer) that succeed.
- **Formula:** `100 * (PMRRCCONNESTABSUCC / (PMRRCCONNESTABATT - PMRRCCONNESTABATTREATT)) * (PMS1SIGCONNESTABSUCC / PMS1SIGCONNESTABATT) * (PMERABESTABSUCCINIT / PMERABESTABATTINIT)`
- **Key Counters:**
  - `PMRRCCONNESTABSUCC`: Successful RRC Connection Establishments.
  - `PMRRCCONNESTABATT`: RRC Connection Establishment Attempts.
  - `PMRRCCONNESTABATTREATT`: RRC Connection Establishment Reattempts.
  - `PMS1SIGCONNESTABSUCC`: Successful S1 Signalling Connection Establishments.
  - `PMS1SIGCONNESTABATT`: S1 Signalling Connection Establishment Attempts.
  - `PMERABESTABSUCCINIT`: Successful Initial E-RAB Establishments.
  - `PMERABESTABATTINIT`: Initial E-RAB Establishment Attempts.
- **Degradation Threshold:** Value < 95.0% or > 5.0 percentage points below baseline.

### 1.2 Retainability — E-RAB % Lost (eNB-Triggered)
- **Definition:** The share of active E-RAB connections released abnormally due to radio or eNodeB faults.
- **Formula:** `100 * (PMERABRELABNORMALENB / (PMERABRELABNORMALENB + PMERABRELNORMALENB))`
- **Degradation Threshold:** Value > 2.0%.

### 1.3 Downlink Throughput (kbps)
- **Definition:** User payload data rate on the DL Physical Downlink Shared Channel (PDSCH).
- **Formula:** `(PMPDCPVOLDLDRB - PMPDCPVOLDLDRBLASTTTI) / PMUETHPTIMEDL` (vol in bits, time in ms → result in kbps).
- **Degradation Threshold:** Value > 30% below baseline.

### 1.4 Cell Availability (%)
- **Definition:** The percentage of time a cell is operational and serving traffic during the ROP period.
- **Formula:** `100 * (1 - (PMCELLDOWNTIMEAUTO + PMCELLDOWNTIMEMAN) / PERIOD_DURATION)`
- **Degradation Threshold:** Value < 99.0%.

### 1.5 5G EN-DC Setup Success Rate (%)
- **Definition:** Success rate of dual-connectivity (E-UTRAN New Radio Dual Connectivity) setup attempts for 5G NSA UEs.
- **Formula:** `100 * (pmEndcSetupUeSucc / pmEndcSetupUeAtt)`
- **Degradation Threshold:** Value < 90.0%.

---

## 2. Configuration Parameters (CM) Reference

- **ADMINISTRATIVESTATE:** Cell operational lock state. `1` = Unlocked (Normal), `0` = Locked (Cell shut down manually/administratively).
- **CELLBARRED:** Cell access barring state. `0` = Cell Barred false (Normal), `1` = Cell Barred true (No UEs allowed to attach).
- **DLCHANNELBANDWIDTH:** Channel bandwidth in kHz (e.g. `20000` = 20 MHz, `15000` = 15 MHz, `10000` = 10 MHz, `5000` = 5 MHz).
- **FREQBAND:** E-UTRA Absolute Radio Frequency Channel Number / Frequency Band (Band 2 = 1900 MHz, Band 3 = 1800 MHz, Band 7 = 2600 MHz).

---

## 3. Standard Operating Procedures (SOPs) & Root Cause Playbooks

### SOP-01: Recent Configuration Change (CELL_BARRED_CHANGE / ADMIN_STATE_CHANGE)
- **Symptom:** Accessibility drops sharply to ~0% or low values on a specific cell.
- **Diagnostic Procedure:** Query `cm_config_sample` for parameter modifications within 7 days prior to incident date. Check if `CELLBARRED` changed from `0` to `1` or `ADMINISTRATIVESTATE` changed from `1` to `0`.
- **Recommended Action:** Revert parameter change via OSS Bulk CM or reset cell administrative state.

### SOP-02: Cell / Site Outage (BACKHAUL_LINK_DOWN / POWER_FAILURE)
- **Symptom:** Cell availability collapses to 0% (`PMCELLDOWNTIMEAUTO` = 86400s). All traffic counters zero.
- **Diagnostic Procedure:** Query `alarm_history` for active alarms during the downtime window. Check for critical alarms like `Backhaul Link Down` or `Power Failure`.
- **Recommended Action:** Dispatch field technician to inspect optical SFP module, microwave backhaul link, or local AC/DC power supply.

### SOP-03: Co-Site / Sector Interference (NEIGHBOUR_INTERFERENCE)
- **Symptom:** DL Throughput drops significantly across multiple co-located sectors on the same eNodeB (e.g., C1, C2, C3) while local CM config and alarms are clean.
- **Diagnostic Procedure:** Query neighbour cell KPIs to confirm correlated throughput drops on surrounding sectors.
- **Recommended Action:** Perform RF interference scan, inspect physical antenna orientation/downtilt, and check for external RF interference sources.

### SOP-04: 5G NSA Setup Failure (NR_RANDOM_ACCESS_FAILURE)
- **Symptom:** 5G `pmEndcSetupUeSucc` drops while LTE anchor cell accessibility remains healthy.
- **Diagnostic Procedure:** Query `query_nr_endc` for NR cell and verify LTE anchor cell via `query_lte_kpi`.
- **Recommended Action:** Audit NR RACH preamble parameters on gNodeB CU/DU and verify 5G NR radio link alignment.
"""
    kb_path = out_dir / "telecom_knowledge.md"
    kb_path.write_text(content)
    print(f"  ✓ {kb_path.name:40s} (seed RAG corpus)")


# ── CSV writers ────────────────────────────────────────────────────────────────

LTE_COLS = [
    "OSS_ID","ENODEBFUNCTION","EUTRANCELLFDD","YEAR_ID","MONTH_ID","DAY_ID",
    "PERIOD_DURATION","PMRRCCONNESTABSUCC","PMRRCCONNESTABATT","PMRRCCONNESTABATTREATT",
    "PMS1SIGCONNESTABSUCC","PMS1SIGCONNESTABATT","PMERABESTABSUCCINIT","PMERABESTABATTINIT",
    "PMERABRELABNORMALENB","PMERABRELNORMALENB","PMPDCPVOLDLDRB","PMPDCPVOLDLDRBLASTTTI",
    "PMUETHPTIMEDL","PMCELLDOWNTIMEAUTO","PMCELLDOWNTIMEMAN","PMPDCPLATTIMEDL","PMPDCPLATPKTTRANSDL",
]
NR_COLS = [
    "OSS_ID","NRCellCU","YEAR_ID","MONTH_ID","DAY_ID","PERIOD_DURATION",
    "pmEndcSetupUeSucc","pmEndcSetupUeAtt","pmEndcSetupScgUeSucc","pmEndcSetupScgUeAtt",
    "pmCellDowntimeAuto","pmCellDowntimeMan",
]
CM_COLS = [
    "OSS_ID","ENODEBFUNCTION","EUTRANCELLFDD","YEAR_ID","MONTH_ID","DAY_ID",
    "DATETIME_ID","ADMINISTRATIVESTATE","CELLBARRED","FREQBAND","EARFCNDL","EARFCNUL",
    "DLCHANNELBANDWIDTH","LATITUDE","LONGITUDE",
]
ALARM_COLS = [
    "alarm_id","EUTRANCELLFDD","OSS_ID","alarm_name","severity",
    "start_time","end_time","status","description",
]

def write_csv(path: Path, rows: list[dict], cols: list[str]) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"  ✓ {path.name:40s} {len(rows):>6} rows")


def write_manifest(out_dir: Path, seed: int, row_counts: dict) -> None:
    manifest = {
        "dataset_version": DATASET_VERSION,
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "random_seed": seed,
        "date_range": {"start": str(START_DATE), "end": str(END_DATE)},
        "row_counts": row_counts,
        "scenario_dates": {
            "INC1_config_change": str(INC1_CONFIG_CHANGE_DATE),
            "INC1_incident":      str(INC1_INCIDENT_DATE),
            "INC2_outage":        str(INC2_OUTAGE_DATE),
            "INC3_interference":  str(INC3_INTERFERENCE_DATE),
            "INC4_endc_failure":  str(INC4_ENDC_FAIL_DATE),
            "INC5_ambiguous":     str(INC5_AMBIGUOUS_DATE),
        },
        "cells": {
            "lte_cells": [c["cell"] for c in CELLS],
            "nr_cells":  [c["cell"] for c in NR_CELLS],
        },
    }
    mf_path = out_dir / "dataset_manifest.json"
    mf_path.write_text(json.dumps(manifest, indent=2))
    print(f"  ✓ {mf_path.name:40s} (version lock)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic ENIQ data")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducibility (default: 42)")
    parser.add_argument("--out", default="sample_data",
                        help="Output directory (default: sample_data)")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'─'*55}")
    print(f"  Synthetic Data Generator — {DATASET_VERSION}")
    print(f"  Seed: {args.seed}  |  Date range: {START_DATE} → {END_DATE}")
    print(f"  Cells: {len(CELLS)} LTE + {len(NR_CELLS)} NR")
    print(f"{'─'*55}\n")

    print("Generating LTE KPI data...")
    lte_rows = generate_lte_kpi(rng)
    write_csv(out_dir / "lte_kpi_sample.csv", lte_rows, LTE_COLS)

    print("Generating NR EN-DC data...")
    nr_rows = generate_nr_endc(rng)
    write_csv(out_dir / "nr_endc_sample.csv", nr_rows, NR_COLS)

    print("Generating CM config data...")
    cm_rows = generate_cm_config()
    write_csv(out_dir / "cm_config_sample.csv", cm_rows, CM_COLS)

    print("Generating alarm history...")
    alarm_rows = generate_alarm_history()
    write_csv(out_dir / "alarm_history.csv", alarm_rows, ALARM_COLS)

    print("Generating incident ticket history...")
    ticket_rows = generate_incident_history()
    write_csv(out_dir / "incident_history.csv", ticket_rows, TICKET_COLS)

    print("Generating telecom knowledge base...")
    generate_telecom_knowledge(out_dir)

    row_counts = {
        "lte_kpi": len(lte_rows),
        "nr_endc": len(nr_rows),
        "cm_config": len(cm_rows),
        "alarm_history": len(alarm_rows),
        "incident_history": len(ticket_rows),
    }
    write_manifest(out_dir, args.seed, row_counts)

    total = sum(row_counts.values())
    print(f"\n{'─'*55}")
    print(f"  Done. {total} total rows written.")
    print(f"  Regenerate: python sample_data/generate_synthetic_data.py --seed {args.seed}")
    print(f"{'─'*55}\n")


if __name__ == "__main__":
    main()

