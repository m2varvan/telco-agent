# eval/schema/root_cause_codes.py
"""
Canonical RCA taxonomy from evaluation plan Section 35.
Import these constants everywhere root-cause codes are compared to guarantee
consistent spelling and prevent silent string-mismatch bugs.
"""

# ── Configuration-change family ───────────────────────────────────────────────
CELL_BARRED_CHANGE  = "CELL_BARRED_CHANGE"
ADMIN_STATE_CHANGE  = "ADMIN_STATE_CHANGE"
BANDWIDTH_CHANGE    = "BANDWIDTH_CHANGE"
POWER_CONFIG_CHANGE = "POWER_CONFIG_CHANGE"

# ── Outage / availability family ─────────────────────────────────────────────
BACKHAUL_LINK_DOWN  = "BACKHAUL_LINK_DOWN"
POWER_FAILURE       = "POWER_FAILURE"

# ── Interference / neighbour family ──────────────────────────────────────────
NEIGHBOUR_INTERFERENCE = "NEIGHBOUR_INTERFERENCE"

# ── EN-DC / 5G family ────────────────────────────────────────────────────────
NR_RANDOM_ACCESS_FAILURE = "NR_RANDOM_ACCESS_FAILURE"

# ── Ambiguous / unknown ───────────────────────────────────────────────────────
UNDETERMINED = "UNDETERMINED"

# ── Full taxonomy set (for validation) ───────────────────────────────────────
ALL_CODES: frozenset[str] = frozenset({
    CELL_BARRED_CHANGE,
    ADMIN_STATE_CHANGE,
    BANDWIDTH_CHANGE,
    POWER_CONFIG_CHANGE,
    BACKHAUL_LINK_DOWN,
    POWER_FAILURE,
    NEIGHBOUR_INTERFERENCE,
    NR_RANDOM_ACCESS_FAILURE,
    UNDETERMINED,
})

# ── Mapping: family name → expected root-cause codes ─────────────────────────
FAMILY_CODES: dict[str, list[str]] = {
    "config_change": [
        CELL_BARRED_CHANGE,
        ADMIN_STATE_CHANGE,
        BANDWIDTH_CHANGE,
        POWER_CONFIG_CHANGE,
    ],
    "outage": [
        BACKHAUL_LINK_DOWN,
        POWER_FAILURE,
    ],
    "interference": [
        NEIGHBOUR_INTERFERENCE,
    ],
    "endc": [
        NR_RANDOM_ACCESS_FAILURE,
    ],
    "ambiguous": [
        UNDETERMINED,
    ],
}
