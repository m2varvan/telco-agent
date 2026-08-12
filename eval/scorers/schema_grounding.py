# eval/scorers/schema_grounding.py
"""
Schema Hallucination Evaluator.

Scans agent evidence observations and root_cause text for column/field/counter
references and checks them against the known-valid schema columns from the
actual sample CSV files.

Valid columns are derived directly from the CSV headers so they stay in sync
with the data files automatically.
"""
from __future__ import annotations
import re

# ── Valid columns derived from sample CSV headers ─────────────────────────────

VALID_LTE_COLUMNS: frozenset[str] = frozenset({
    "OSS_ID", "ENODEBFUNCTION", "EUTRANCELLFDD",
    "YEAR_ID", "MONTH_ID", "DAY_ID", "PERIOD_DURATION",
    "PMRRCCONNESTABSUCC", "PMRRCCONNESTABATT", "PMRRCCONNESTABATTREATT",
    "PMS1SIGCONNESTABSUCC", "PMS1SIGCONNESTABATT",
    "PMERABESTABSUCCINIT", "PMERABESTABATTINIT",
    "PMERABRELABNORMALENB", "PMERABRELNORMALENB",
    "PMPDCPVOLDLDRB", "PMPDCPVOLDLDRBLASTTTI", "PMUETHPTIMEDL",
    "PMCELLDOWNTIMEAUTO", "PMCELLDOWNTIMEMAN",
    "PMPDCPLATTIMEDL", "PMPDCPLATPKTTRANSDL",
})

VALID_NR_COLUMNS: frozenset[str] = frozenset({
    "OSS_ID", "NRCellCU", "YEAR_ID", "MONTH_ID", "DAY_ID", "PERIOD_DURATION",
    "pmEndcSetupUeSucc", "pmEndcSetupUeAtt",
    "pmEndcSetupScgUeSucc", "pmEndcSetupScgUeAtt",
    "pmCellDowntimeAuto", "pmCellDowntimeMan",
})

VALID_CM_COLUMNS: frozenset[str] = frozenset({
    "OSS_ID", "ENODEBFUNCTION", "EUTRANCELLFDD",
    "YEAR_ID", "MONTH_ID", "DAY_ID", "DATETIME_ID",
    "ADMINISTRATIVESTATE", "CELLBARRED", "FREQBAND",
    "EARFCNDL", "EARFCNUL", "DLCHANNELBANDWIDTH",
    "LATITUDE", "LONGITUDE",
})

VALID_ALARM_COLUMNS: frozenset[str] = frozenset({
    "alarm_id", "EUTRANCELLFDD", "OSS_ID",
    "alarm_name", "severity", "start_time", "end_time",
    "status", "description",
})

# Union of all valid column/field names (case-insensitive matching done at runtime)
ALL_VALID: frozenset[str] = (
    VALID_LTE_COLUMNS | VALID_NR_COLUMNS | VALID_CM_COLUMNS | VALID_ALARM_COLUMNS
)

# Pre-compute lowercase lookup for fast matching
_ALL_VALID_LOWER: frozenset[str] = frozenset(v.lower() for v in ALL_VALID)

# ── Token extraction ───────────────────────────────────────────────────────────

# Match identifiers that look like schema fields: ALLCAPS_WITH_UNDERSCORES or
# camelCase names that start with "pm" (ericsson counter prefix)
_FIELD_PATTERN = re.compile(
    r'\b(PM[A-Z][A-Z0-9_]{2,}|pm[A-Z][a-zA-Z0-9]+|[A-Z]{2,}[A-Z0-9_]*)\b'
)


def _extract_field_references(text: str) -> list[str]:
    """
    Extract tokens from text that look like schema field/column names.
    Returns a list of unique raw tokens (case preserved).
    """
    seen: set[str] = set()
    result: list[str] = []
    for m in _FIELD_PATTERN.finditer(text):
        tok = m.group(0)
        if tok not in seen:
            seen.add(tok)
            result.append(tok)
    return result


# ── Evaluator ─────────────────────────────────────────────────────────────────

class SchemaHallucinationEvaluator:
    """
    Scan agent RCA output for schema field references and identify hallucinations.
    """

    def evaluate(self, rca_output: dict) -> dict:
        """
        Parameters
        ----------
        rca_output : dict
            Agent output dict. Scans:
            - evidence[].observation, evidence[].field, evidence[].table
            - root_cause (string)

        Returns
        -------
        dict with keys:
            valid_rate          (float) – fraction of references that are valid
            hallucinated_fields (list[str]) – field names not in any known schema
            hallucinated_count  (int)
            total_references    (int)
        """
        # Collect all text to scan
        texts: list[str] = []

        root_cause = rca_output.get("root_cause", "") or ""
        if root_cause:
            texts.append(root_cause)

        for ev in rca_output.get("evidence", []) or []:
            if isinstance(ev, dict):
                for key in ("observation", "field", "table"):
                    val = ev.get(key, "")
                    if val:
                        texts.append(str(val))
            elif isinstance(ev, str):
                texts.append(ev)

        combined = " ".join(texts)
        references = _extract_field_references(combined)

        if not references:
            return {
                "valid_rate": 1.0,
                "hallucinated_fields": [],
                "hallucinated_count": 0,
                "total_references": 0,
            }

        hallucinated: list[str] = []
        for ref in references:
            if ref.lower() not in _ALL_VALID_LOWER:
                hallucinated.append(ref)

        total = len(references)
        hall_count = len(hallucinated)
        valid_rate = (total - hall_count) / total if total > 0 else 1.0

        return {
            "valid_rate": round(valid_rate, 4),
            "hallucinated_fields": hallucinated,
            "hallucinated_count": hall_count,
            "total_references": total,
        }
