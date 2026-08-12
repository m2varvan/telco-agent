"""
Network Incident Triage Assistant — Interactive CLI
Rogers AI for Networks | NVIDIA NeMo Agent Toolkit

Model support:
  - NVIDIA NIM (Nemotron Telco or any NIM-hosted model)  → ACTIVE_LLM=nemotron_nim
  - Azure OpenAI (company frontier model: GPT-4o, o1…)  → ACTIVE_LLM=azure_frontier

Agent strategy:
  1. tool_calling_agent (standard — OpenAI function-calling protocol, works with all modern models)
  2. react_agent fallback (text-based ReAct loop — used if tool_calling_agent times out/fails)

Tool failures are recorded in evidence ("Tool X failed: reason") — never assumed or fabricated.

Usage:
    .venv/bin/python main.py                           # interactive loop
    .venv/bin/python main.py "Cell INC1_CELL_A..."    # single shot
    .venv/bin/python main.py --model azure_frontier "..." # override model
"""

# ── stdlib ────────────────────────────────────────────────────────────────────
import asyncio
import copy
import json
import logging
import os
import re
import sys
import tempfile
import textwrap
import time
from datetime import datetime

# ── third-party ───────────────────────────────────────────────────────────────
import yaml
from dotenv import load_dotenv
from nat.builder.workflow_builder import WorkflowBuilder
from nat.runtime.loader import load_config

# ── project — runs @register_function decorators so NAT knows our tools ───────
import agent_tools.tools  # noqa: F401

load_dotenv()

# ── Timeouts ──────────────────────────────────────────────────────────────────
# Nemotron-Super-49B takes ~30s per tool call + ~40s synthesis = ~130s for 3 tool calls
TOOL_CALL_TIMEOUT      = 180   # seconds for tool_calling_agent (generous for multi-tool runs)
REACT_FALLBACK_TIMEOUT = 150   # seconds for react_agent fallback

# ── Required env vars ─────────────────────────────────────────────────────────
_REQUIRED_NIM   = ["LLM_MODEL_NAME", "LLM_API_KEY", "LLM_BASE_URL"]
_REQUIRED_AZURE = ["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_API_KEY"]

# ── react_agent system prompt (needs {tools} and {tool_names} placeholders) ───
_REACT_SYSTEM_PROMPT = """\
You are the Network Incident Triage Assistant for Rogers — AI for Networks.
You have access to these tools:

{tools}

Tool names: {tool_names}

You MUST call at least one tool before answering. Never fabricate data.

AVAILABLE DATA:
  LTE cells  (query_lte_kpi):  INC1_CELL_A, INC2_CELL_B, INC3_CELL_C1, INC3_CELL_C2, INC3_CELL_C3, INC4_LTE_ANCHOR
  NR/5G cells (query_nr_endc): INC4_NR_D
  OSS instance: eniq_oss_1

INVESTIGATION:
1. Call query_lte_kpi (LTE) or query_nr_endc (5G) first. Parse year/month/day as integers.
2. If Accessibility/Throughput/Latency degraded: call query_cm_config(cell_id, oss_id, before_date, days_back=7)
   If Availability degraded: call query_alarm_history(cell_id, oss_id, year, month, day)
   If EN-DC degraded: also call query_lte_kpi on INC4_LTE_ANCHOR
3. If a tool fails, record "Tool X failed: reason" in evidence. Do NOT guess.
4. Return ONLY this JSON when finished — replace all angle-bracket fields with real values:
   "incident": the original description
   "kpis_evaluated": list of kpi/value/baseline/status objects from tool output
   "root_cause": single statement under 200 characters
   "evidence": list of strings with actual numbers from tool output
   "confidence": high (2+ sources) or medium (1 source) or low (failure/ambiguous)
   "further_investigation_required": true or false
   "recommended_next_step": specific actionable step"""

# ── ANSI colours ──────────────────────────────────────────────────────────────
RESET   = "\033[0m";  BOLD  = "\033[1m";  DIM    = "\033[2m"
CYAN    = "\033[36m"; GREEN = "\033[32m"; YELLOW = "\033[33m"
RED     = "\033[31m"; BLUE  = "\033[34m"; MAGENTA= "\033[35m"; WHITE = "\033[97m"

def _c(col: str, text: str) -> str:
    return f"{col}{text}{RESET}"


# ── Logger ────────────────────────────────────────────────────────────────────
class TriageLogger:
    def __init__(self):
        self._step = 0

    def _ts(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def _hdr(self, icon: str, label: str, col: str) -> None:
        self._step += 1
        print(f"\n{col}{BOLD}[{self._ts()}] {icon} STEP {self._step} — {label}{RESET}")
        print(_c(DIM, "─" * 60))

    def user_query(self, q: str) -> None:
        print()
        print(_c(BOLD + WHITE, "━" * 60))
        print(_c(BOLD + WHITE, "  🔍 INCIDENT QUERY"))
        print(_c(BOLD + WHITE, "━" * 60))
        print(_c(CYAN, f"  {q}"))
        print(_c(BOLD + WHITE, "━" * 60))
        self._step = 0

    def agent_mode(self, mode: str, model: str) -> None:
        self._hdr("🧠", f"AGENT: {mode}  |  model: {model}", MAGENTA)
        print(_c(MAGENTA, "  Preparing to call tools and synthesise RCA..."))

    def tool_called(self, name: str, args: dict) -> None:
        self._hdr("🔧", f"TOOL CALL → {name.upper()}", YELLOW)
        for k, v in args.items():
            print(_c(YELLOW, f"  {k}: {v}"))

    def tool_returned(self, name: str, result: dict, ms: int) -> None:
        self._hdr("📦", f"TOOL RESULT ← {name.upper()}  ({ms}ms)", GREEN)
        if "error" in result:
            print(_c(RED, f"  ⚠  {result['error']}"))
            return
        if "kpis_evaluated" in result:
            cell = result.get("cell_id") or result.get("nr_cell_id", "?")
            print(_c(GREEN, f"  Cell: {cell}"))
            for k in result["kpis_evaluated"]:
                icon = {"ok":"✅","degraded":"🔴","unavailable":"⚠️"}.get(k["status"],"?")
                v = f"{k['value']:.4g}" if k.get("value") is not None else "null"
                b = f"{k['baseline']:.4g}" if k.get("baseline") is not None else "null"
                print(_c(GREEN, f"  {icon} {k['kpi']:<32} value={v:>10}  baseline={b:>10}  [{k['status']}]"))
        elif "changes" in result:
            n = result.get("num_records", len(result["changes"]))
            w = result.get("window", {})
            print(_c(GREEN, f"  Config records [{str(w.get('from',''))[:10]} → {str(w.get('to',''))[:10]}]: {n}"))
            for ch in result["changes"][:5]:
                print(_c(GREEN, f"  📅 {str(ch.get('DATETIME_ID',''))[:10]}  "
                               f"ADMINSTATE={ch.get('ADMINISTRATIVESTATE','?')}  "
                               f"CELLBARRED={ch.get('CELLBARRED','?')}  "
                               f"BW={ch.get('DLCHANNELBANDWIDTH','?')}"))
        elif "PMCELLDOWNTIMEAUTO" in result:
            auto  = result.get("PMCELLDOWNTIMEAUTO", 0) or 0
            man   = result.get("PMCELLDOWNTIMEMAN", 0) or 0
            avail = result.get("availability_pct")
            avail_s = f"{avail:.2f}%" if avail is not None else "n/a"
            print(_c(GREEN, f"  Downtime AUTO={auto}s  MAN={man}s  Availability={avail_s}"))
            for a in result.get("alarms", []):
                print(_c(RED, f"  🚨 {a.get('alarm_name','?')}  [{a.get('severity','?')}]  {str(a.get('start_time',''))[:10]}"))
                if a.get("description"):
                    for line in textwrap.wrap(str(a["description"]), 54):
                        print(_c(DIM, f"     {line}"))
            if not result.get("alarms"):
                print(_c(GREEN, "  No alarms on record for this date."))
        elif "co_site_cells" in result:
            print(_c(GREEN, f"  Topology: eNodeB={result.get('enodeb')}  Co-site sectors={result.get('co_site_count')}  Spatial neighbours={result.get('neighbour_count')}"))
            for cs in result.get("co_site_cells", []):
                print(_c(GREEN, f"  📡 Co-site: {cs['cell_id']}  Band={cs['band']}"))
            for nb in result.get("spatial_neighbours", [])[:3]:
                print(_c(GREEN, f"  🛰 Neighbour: {nb['cell_id']}  Distance={nb['distance_km']}km"))
        elif "daily_trend" in result:
            summ = result.get("summary", {})
            print(_c(GREEN, f"  KPI Trend [{result.get('cell_id')}]: Pattern={summ.get('pattern')}  Days={result.get('window',{}).get('days')}"))
            print(_c(GREEN, f"  Baseline Acc={summ.get('baseline_accessibility_pct')}%  Latest Acc={summ.get('latest_accessibility_pct')}%"))
        elif "historical_tickets" in result:
            print(_c(GREEN, f"  Similar Incidents Found: {result.get('match_count')} tickets"))
            for tk in result.get("historical_tickets", [])[:3]:
                print(_c(GREEN, f"  🎫 [{tk.get('ticket_id')}] {tk.get('created_date')[:10]}  {tk.get('root_cause_code')} — {tk.get('summary')}"))
                if tk.get("resolution_notes"):
                    print(_c(DIM, f"     Resolution: {tk['resolution_notes']}"))
        elif "retrieved_knowledge" in result:
            print(_c(GREEN, f"  Knowledge Retrieved: {result.get('match_count')} sections"))
            for kn in result.get("retrieved_knowledge", []):
                print(_c(GREEN, f"  📚 {kn.get('title')} (score: {kn.get('relevance_score')})"))


    def synthesising(self, src: str) -> None:
        self._hdr("🤖", f"LLM SYNTHESISING  ({src})", MAGENTA)
        print(_c(MAGENTA, "  Correlating tool results → building RCA..."))

    def fallback(self, reason: str) -> None:
        print(_c(YELLOW + BOLD, f"\n  ⚠  FALLBACK: {reason}"))

    def final_rca(self, rca: dict) -> None:
        print()
        print(_c(BOLD + GREEN, "━" * 60))
        print(_c(BOLD + GREEN, "  📋 ROOT CAUSE ANALYSIS"))
        print(_c(BOLD + GREEN, "━" * 60))
        conf_col = {"high":GREEN,"medium":YELLOW,"low":RED}.get(rca.get("confidence","low"), WHITE)
        print(_c(BOLD + WHITE, "  Incident: ") + _c(CYAN, rca.get("incident", "")))
        print()
        kpis = rca.get("kpis_evaluated", [])
        if kpis:
            print(_c(BOLD + WHITE, "  KPIs Evaluated:"))
            for k in kpis:
                icon = {"ok":"✅","degraded":"🔴","unavailable":"⚠️"}.get(k.get("status",""),"?")
                v = f"{k['value']:.4g}" if k.get("value") is not None else "null"
                b = f"{k['baseline']:.4g}" if k.get("baseline") is not None else "null"
                print(f"    {icon}  {k.get('kpi','?'):<34} {v:>10}  (baseline {b})")
        print()
        print(_c(BOLD + WHITE, "  Root Cause:"))
        fir = rca.get("further_investigation_required", False)
        rc_col = RED if fir else GREEN
        for line in textwrap.wrap(rca.get("root_cause", ""), 56):
            print("    " + _c(BOLD + rc_col, line))
        print()
        evid = rca.get("evidence", [])
        if evid:
            print(_c(BOLD + WHITE, "  Evidence:"))
            for e in evid:
                for line in textwrap.wrap(str(e), 54):
                    print("    • " + _c(WHITE, line))
        print()
        print(_c(BOLD + WHITE, "  Confidence:     ") + _c(conf_col + BOLD, rca.get("confidence","?").upper()))
        print(_c(BOLD + WHITE, "  Further Invest: ") + _c(RED if fir else GREEN, "YES — escalate" if fir else "No"))
        print()
        print(_c(BOLD + WHITE, "  Next Step:"))
        for line in textwrap.wrap(rca.get("recommended_next_step",""), 56):
            print("    " + _c(BLUE, line))
        print(_c(BOLD + GREEN, "━" * 60))

    def raw_output(self, text: str) -> None:
        print(_c(BOLD + YELLOW, "\n  ⚠  Response was not clean JSON — showing raw:"))
        print(_c(YELLOW, "━" * 60))
        for line in text.strip().split("\n")[:40]:
            print(_c(WHITE, f"  {line}"))
        print(_c(YELLOW, "━" * 60))

    def error(self, msg: str) -> None:
        print(_c(RED + BOLD, f"\n  ✗ ERROR: {msg}"))

    def timing(self, elapsed: float) -> None:
        print(_c(DIM, f"\n  ⏱  Elapsed: {elapsed:.1f}s"))


LOG = TriageLogger()


# ── Env validation ─────────────────────────────────────────────────────────────
def _validate_env(override: str | None = None) -> str:
    active = (override or os.getenv("ACTIVE_LLM", "nemotron_nim")).strip()
    if active == "azure_frontier":
        missing = [v for v in _REQUIRED_AZURE if not os.getenv(v) or os.getenv(v,"").startswith("placeholder")]
        if missing:
            raise EnvironmentError(f"Azure vars not configured: {', '.join(missing)}. Set them in .env.")
    else:
        missing = [v for v in _REQUIRED_NIM if not os.getenv(v)]
        if missing:
            raise EnvironmentError(f"NVIDIA NIM vars missing: {', '.join(missing)}. Set them in .env.")
    return active


# ── JSON extraction ────────────────────────────────────────────────────────────
def _extract_json(raw: str) -> dict | None:
    """Extract the last valid JSON object from any LLM response format."""
    text = raw.strip()

    # 1. Try ```json ... ``` code blocks — take the last one
    import re as _re
    blocks = _re.findall(r'```(?:json)?\s*(\{.*?\})\s*```', text, _re.DOTALL)
    for candidate in reversed(blocks):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    # 2. Find the LAST outermost { ... } that parses as valid JSON
    depth = 0
    end_idx = -1
    for i in range(len(text) - 1, -1, -1):
        ch = text[i]
        if ch == '}':
            depth += 1
            if end_idx == -1:
                end_idx = i
        elif ch == '{':
            depth -= 1
            if depth == 0 and end_idx != -1:
                candidate = text[i:end_idx + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    # Keep looking for an earlier (outer) brace
                    end_idx = -1
                    depth = 0

    return None


# ── Config builder ─────────────────────────────────────────────────────────────
def _build_config_yaml(workflow_type: str, llm_name: str) -> str:
    """
    Read workflow.yml, expand env vars, switch workflow._type and llm_name.
    Returns a YAML string ready for NAT's load_config.
    """
    with open("workflow.yml") as f:
        raw = f.read()
    # Expand ${VAR} references
    for key, val in os.environ.items():
        raw = raw.replace(f"${{{key}}}", val or "")
    cfg = yaml.safe_load(raw)
    cfg["workflow"]["_type"] = workflow_type
    cfg["workflow"]["llm_name"] = llm_name
    if workflow_type == "react_agent":
        cfg["workflow"]["system_prompt"] = _REACT_SYSTEM_PROMPT
    return yaml.dump(cfg, allow_unicode=True)


# ── Resilient runner ──────────────────────────────────────────────────────────
async def run_with_fallback(incident: str, active_llm: str) -> str:
    """
    1. Try tool_calling_agent (standard — works with GPT-4 class models on any endpoint).
    2. Fall back to react_agent if it times out or produces no KPI data.
    Tool failures → recorded in evidence; never fabricated.
    """

    async def _run_workflow(yaml_str: str, agent_label: str, timeout: int) -> str:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False, dir=".") as tf:
            tf.write(yaml_str)
            tmp = tf.name
        try:
            cfg = load_config(tmp)
            async with asyncio.timeout(timeout):
                async with WorkflowBuilder.from_config(cfg) as builder:
                    workflow = await builder.build()
                    LOG.synthesising(f"{active_llm} / {agent_label}")
                    async with workflow.run(incident) as runner:
                        return await runner.result()
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    # ── Attempt 1: tool_calling_agent ─────────────────────────────────────────
    LOG.agent_mode("tool_calling_agent", active_llm)
    try:
        yaml1 = _build_config_yaml("tool_calling_agent", active_llm)
        result = await _run_workflow(yaml1, "tool_calling_agent", TOOL_CALL_TIMEOUT)
        rca = _extract_json(result)
        if rca and any(rca.get(k) for k in ("kpis_evaluated", "root_cause", "root_cause_code", "evidence", "confidence")):
            return result
        if result and len(result.strip()) > 50:
            # Accept any non-empty response even without clean JSON — scorer handles it
            return result
        LOG.fallback("tool_calling_agent returned empty response → react_agent")
    except asyncio.TimeoutError:
        LOG.fallback(f"tool_calling_agent timed out ({TOOL_CALL_TIMEOUT}s) → react_agent")
    except Exception as exc:
        LOG.fallback(f"tool_calling_agent error ({type(exc).__name__}: {exc}) → react_agent")

    # ── Attempt 2: react_agent (fallback) ─────────────────────────────────────
    LOG.agent_mode("react_agent (fallback)", active_llm)
    try:
        yaml2 = _build_config_yaml("react_agent", active_llm)
        result = await _run_workflow(yaml2, "react_agent", REACT_FALLBACK_TIMEOUT)
        return result
    except asyncio.TimeoutError:
        return json.dumps({
            "incident": incident,
            "kpis_evaluated": [],
            "root_cause": "Agent timed out — investigation incomplete.",
            "evidence": [
                f"tool_calling_agent timed out after {TOOL_CALL_TIMEOUT}s.",
                f"react_agent timed out after {REACT_FALLBACK_TIMEOUT}s."
            ],
            "confidence": "low",
            "further_investigation_required": True,
            "recommended_next_step": "Re-run the query or verify model endpoint connectivity.",
        })
    except Exception as exc:
        return json.dumps({
            "incident": incident,
            "kpis_evaluated": [],
            "root_cause": f"Both agent types failed: {exc}",
            "evidence": [f"tool_calling_agent and react_agent both raised errors. Last: {exc}"],
            "confidence": "low",
            "further_investigation_required": True,
            "recommended_next_step": "Check .env configuration and model endpoint.",
        })


# ── Sample queries ─────────────────────────────────────────────────────────────
SAMPLE_QUERIES = [
    "Cell INC1_CELL_A on eniq_oss_1 is showing poor accessibility on 2026-06-29. Investigate.",
    "Cell INC2_CELL_B on eniq_oss_1 went completely unavailable on 2026-06-29. Possible outage.",
    "Cells INC3_CELL_C1, INC3_CELL_C2, INC3_CELL_C3 on eNB_INC3 all show DL throughput degradation on 2026-06-29.",
    "NR cell INC4_NR_D on eniq_oss_1 reporting EN-DC setup failures on 2026-06-30. Anchor INC4_LTE_ANCHOR appears healthy.",
    "What is the DL latency and availability for INC2_CELL_B on 2026-06-29?",
]


def _print_banner(active_llm: str) -> None:
    print()
    print(_c(BOLD + CYAN, "╔══════════════════════════════════════════════════════════╗"))
    print(_c(BOLD + CYAN, "║   🛰  NETWORK INCIDENT TRIAGE ASSISTANT                  ║"))
    print(_c(BOLD + CYAN, "║   Rogers — AI for Networks  |  NVIDIA NeMo Agent Toolkit ║"))
    print(_c(BOLD + CYAN, "╚══════════════════════════════════════════════════════════╝"))
    print()
    print(_c(DIM, "  Active model:  ") + _c(WHITE, active_llm))
    print(_c(DIM, "  Agent type:    ") + _c(WHITE, "tool_calling_agent  →  react_agent (fallback)"))
    print(_c(DIM, "  Switch model:  ") + _c(DIM, "set ACTIVE_LLM=azure_frontier in .env  OR  type 'switch azure'"))
    print()
    print(_c(BOLD + WHITE, "  Sample queries:"))
    for i, q in enumerate(SAMPLE_QUERIES, 1):
        for j, line in enumerate(textwrap.wrap(q, 54)):
            print(_c(CYAN, f"  {'%d.' % i if j == 0 else '   '} {line}"))
    print()
    print(_c(DIM, "  Type your incident description and press Enter."))
    print(_c(DIM, "  Commands: 'switch azure' | 'switch nim' | 'quit'"))
    print()


# ── Interactive loop ───────────────────────────────────────────────────────────
async def interactive_loop(active_llm: str) -> None:
    _print_banner(active_llm)
    while True:
        try:
            raw = input(_c(BOLD + CYAN, "▶ ")).strip()
        except (EOFError, KeyboardInterrupt):
            print(_c(DIM, "\n  Goodbye."))
            break
        if not raw:
            continue
        if raw.lower() in ("quit", "exit", "q"):
            print(_c(DIM, "  Goodbye.")); break
        if raw.lower() in ("switch azure", "use azure"):
            try:
                active_llm = _validate_env("azure_frontier")
                print(_c(GREEN, f"  ✔ Switched to Azure OpenAI frontier model.\n"))
            except EnvironmentError as e:
                print(_c(RED, f"  ✗ {e}\n"))
            continue
        if raw.lower() in ("switch nim", "use nim", "switch nvidia"):
            active_llm = "nemotron_nim"
            print(_c(GREEN, "  ✔ Switched to NVIDIA NIM (Nemotron).\n"))
            continue

        LOG.user_query(raw)
        t0 = time.monotonic()
        try:
            result = await run_with_fallback(raw, active_llm)
            rca = _extract_json(result)
            if rca:
                LOG.final_rca(rca)
            else:
                LOG.raw_output(result)
        except KeyboardInterrupt:
            print(_c(YELLOW, "\n  ⚠  Query interrupted."))
        except Exception as exc:
            LOG.error(str(exc))
        LOG.timing(time.monotonic() - t0)
        print()


# ── Single-shot ────────────────────────────────────────────────────────────────
async def single_shot(incident: str, active_llm: str) -> None:
    LOG.user_query(incident)
    t0 = time.monotonic()
    result = await run_with_fallback(incident, active_llm)
    rca = _extract_json(result)
    if rca:
        LOG.final_rca(rca)
    else:
        LOG.raw_output(result)
    LOG.timing(time.monotonic() - t0)


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.disable(logging.WARNING)

    args = sys.argv[1:]
    override = None
    if "--model" in args:
        idx = args.index("--model")
        if idx + 1 < len(args):
            override = args.pop(idx + 1)
            args.pop(idx)

    try:
        active = _validate_env(override)
    except EnvironmentError as e:
        print(_c(RED, f"\n  ✗ {e}"))
        sys.exit(1)

    if args:
        asyncio.run(single_shot(" ".join(args), active))
    else:
        asyncio.run(interactive_loop(active))
