# nat/kpi_calculator.py
# Pure-function KPI formula module — no I/O, no LLM calls, no DuckDB.
from __future__ import annotations
import statistics
from typing import Any

# ── Degradation thresholds ─────────────────────────────────────────────────
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
            total_downtime = PMCELLDOWNTIMEAUTO + PMCELLDOWNTIMEMAN
            # If downtime exceeds period (bad data), cap at 100.0 and flag
            if total_downtime > PERIOD_DURATION:
                return 100.0, True
            raw = 100.0 * (1 - total_downtime / PERIOD_DURATION)
            # Also cap if somehow raw > 100 (e.g. negative downtime)
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

    # ------------------------------------------------------------------ #
    #  Evaluate LTE KPIs for a cell                                      #
    # ------------------------------------------------------------------ #
    def evaluate_lte(
        self,
        counters: dict[str, Any],
        prior_rows: list[tuple],
        cols: list[str],
    ) -> dict[str, Any]:
        """
        Compute all LTE KPIs, baselines, and degradation flags.
        Returns the full kpis_evaluated structure.
        """
        # Helper to safely get a counter value and coerce to int
        def g(name: str) -> Any:
            val = counters.get(name)
            if val is None:
                return None
            try:
                # DuckDB read_csv_auto may return strings; cast to int
                return int(val)
            except (ValueError, TypeError):
                return None

        # Compute each KPI for the incident day
        access = self.compute_accessibility(
            g("PMRRCCONNESTABSUCC"), g("PMRRCCONNESTABATT"), g("PMRRCCONNESTABATTREATT"),
            g("PMS1SIGCONNESTABSUCC"), g("PMS1SIGCONNESTABATT"),
            g("PMERABESTABSUCCINIT"), g("PMERABESTABATTINIT"),
        )
        retain = self.compute_retainability(
            g("PMERABRELABNORMALENB"), g("PMERABRELNORMALENB"),
        )
        dl_tp = self.compute_dl_throughput(
            g("PMPDCPVOLDLDRB"), g("PMPDCPVOLDLDRBLASTTTI"), g("PMUETHPTIMEDL"),
        )
        avail_val, avail_flag = self.compute_cell_availability(
            g("PMCELLDOWNTIMEAUTO"), g("PMCELLDOWNTIMEMAN"), g("PERIOD_DURATION"),
        )
        dl_lat = self.compute_dl_latency(
            g("PMPDCPLATTIMEDL"), g("PMPDCPLATPKTTRANSDL"),
        )

        # Compute baselines from prior rows
        def prior_values(kpi_fn):
            vals = []
            for row in prior_rows:
                rc = dict(zip(cols, row))
                v = kpi_fn(rc)
                if v is not None:
                    vals.append(v)
            return vals

        # Helper to coerce prior-row CSV values to int
        def _i(val):
            if val is None:
                return None
            try:
                return int(val)
            except (ValueError, TypeError):
                return None

        def prior_access(rc):
            return self.compute_accessibility(
                _i(rc.get("PMRRCCONNESTABSUCC")), _i(rc.get("PMRRCCONNESTABATT")),
                _i(rc.get("PMRRCCONNESTABATTREATT")), _i(rc.get("PMS1SIGCONNESTABSUCC")),
                _i(rc.get("PMS1SIGCONNESTABATT")), _i(rc.get("PMERABESTABSUCCINIT")),
                _i(rc.get("PMERABESTABATTINIT")),
            )

        def prior_retain(rc):
            return self.compute_retainability(
                _i(rc.get("PMERABRELABNORMALENB")), _i(rc.get("PMERABRELNORMALENB")),
            )

        def prior_dl_tp(rc):
            return self.compute_dl_throughput(
                _i(rc.get("PMPDCPVOLDLDRB")), _i(rc.get("PMPDCPVOLDLDRBLASTTTI")),
                _i(rc.get("PMUETHPTIMEDL")),
            )

        def prior_avail(rc):
            v, _ = self.compute_cell_availability(
                _i(rc.get("PMCELLDOWNTIMEAUTO")), _i(rc.get("PMCELLDOWNTIMEMAN")),
                _i(rc.get("PERIOD_DURATION")),
            )
            return v

        def prior_dl_lat(rc):
            return self.compute_dl_latency(
                _i(rc.get("PMPDCPLATTIMEDL")), _i(rc.get("PMPDCPLATPKTTRANSDL")),
            )

        access_baseline = self.compute_baseline(prior_values(prior_access))
        retain_baseline = self.compute_baseline(prior_values(prior_retain))
        dl_tp_baseline   = self.compute_baseline(prior_values(prior_dl_tp))
        avail_baseline   = self.compute_baseline(prior_values(prior_avail))
        dl_lat_baseline  = self.compute_baseline(prior_values(prior_dl_lat))

        kpis: list[dict] = [
            {
                "kpi": "Accessibility",
                "value": access,
                "baseline": access_baseline,
                "status": self.flag_degradation("Accessibility", access, access_baseline),
            },
            {
                "kpi": "Retainability",
                "value": retain,
                "baseline": retain_baseline,
                "status": self.flag_degradation("Retainability", retain, retain_baseline),
            },
            {
                "kpi": "DL Throughput",
                "value": dl_tp,
                "baseline": dl_tp_baseline,
                "status": self.flag_degradation("DL Throughput", dl_tp, dl_tp_baseline),
            },
            {
                "kpi": "Cell Availability",
                "value": avail_val,
                "baseline": avail_baseline,
                "status": self.flag_degradation("Cell Availability", avail_val, avail_baseline),
                "data_quality_flag": avail_flag,
            },
            {
                "kpi": "DL PDCP DRB Latency",
                "value": dl_lat,
                "baseline": dl_lat_baseline,
                "status": self.flag_degradation("DL PDCP DRB Latency", dl_lat, dl_lat_baseline),
            },
        ]

        return {
            "cell_id": counters.get("EUTRANCELLFDD"),
            "date": {
                "year": counters.get("YEAR_ID"),
                "month": counters.get("MONTH_ID"),
                "day": counters.get("DAY_ID"),
            },
            "kpis_evaluated": kpis,
            "raw_counters": counters,
        }

    # ------------------------------------------------------------------ #
    #  Evaluate NR EN-DC KPI for a cell                                  #
    # ------------------------------------------------------------------ #
    def evaluate_nr_endc(
        self,
        counters: dict[str, Any],
        prior_rows: list[tuple],
        cols: list[str],
    ) -> dict[str, Any]:
        """
        Compute EN-DC Setup Success Rate, baseline, and degradation flag.
        Returns the full kpis_evaluated structure for NR.
        """
        def _to_int(val):
            if val is None:
                return None
            try:
                return int(val)
            except (ValueError, TypeError):
                return None

        endc_val = self.compute_endc_success_rate(
            _to_int(counters.get("pmEndcSetupUeSucc")),
            _to_int(counters.get("pmEndcSetupUeAtt")),
        )

        prior_endc_vals = []
        for row in prior_rows:
            rc = dict(zip(cols, row))
            v = self.compute_endc_success_rate(
                _to_int(rc.get("pmEndcSetupUeSucc")), _to_int(rc.get("pmEndcSetupUeAtt")),
            )
            if v is not None:
                prior_endc_vals.append(v)

        endc_baseline = self.compute_baseline(prior_endc_vals)

        return {
            "nr_cell_id": counters.get("NRCellCU"),
            "date": {
                "year": counters.get("YEAR_ID"),
                "month": counters.get("MONTH_ID"),
                "day": counters.get("DAY_ID"),
            },
            "kpis_evaluated": [
                {
                    "kpi": "EN-DC Setup Success Rate",
                    "value": endc_val,
                    "baseline": endc_baseline,
                    "status": self.flag_degradation(
                        "EN-DC Setup Success Rate", endc_val, endc_baseline
                    ),
                }
            ],
            "raw_counters": {
                "pmEndcSetupUeSucc": counters.get("pmEndcSetupUeSucc"),
                "pmEndcSetupUeAtt": counters.get("pmEndcSetupUeAtt"),
                "pmEndcSetupScgUeSucc": counters.get("pmEndcSetupScgUeSucc"),
                "pmEndcSetupScgUeAtt": counters.get("pmEndcSetupScgUeAtt"),
            },
        }


def assign_confidence(
    evidence_domains: list[str],
    kpi_degraded: bool,
    ambiguous: bool,
) -> str:
    """
    Determine confidence level based on evidence domain count and KPI degradation.

    Rules:
      - "high"   if ≥2 distinct domains and kpi_degraded is True
      - "medium" if exactly 1 distinct domain and kpi_degraded is True
      - "low"    if ambiguous, empty, or conditions for high/medium not met
    """
    distinct = set(evidence_domains)
    if ambiguous or len(distinct) == 0:
        return "low"
    if len(distinct) >= 2 and kpi_degraded:
        return "high"
    if len(distinct) == 1 and kpi_degraded:
        return "medium"
    return "low"
