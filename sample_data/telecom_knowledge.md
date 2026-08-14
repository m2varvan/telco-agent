S

# Telecom Operations & Ericsson ENIQ Knowledge Base

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
