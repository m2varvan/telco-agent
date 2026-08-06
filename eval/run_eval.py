# eval/run_eval.py
"""
Evaluation harness entry point.
Requirements: 7.5, 7.6, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7
"""
import asyncio
import hashlib
import json
import time
from pathlib import Path
from dotenv import load_dotenv

from eval.scenarios import SCENARIOS
from eval.scorers import score_t4

load_dotenv()

RESULTS_DIR = Path("eval/results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

CSV_FILES = [
    "sample_data/lte_kpi_sample.csv",
    "sample_data/nr_endc_sample.csv",
    "sample_data/cm_config_sample.csv",
]


def dataset_version() -> str:
    """SHA-256 of all three CSVs concatenated, truncated to 12 hex chars."""
    h = hashlib.sha256()
    for path in CSV_FILES:
        h.update(Path(path).read_bytes())
    return h.hexdigest()[:12]


async def run_scenario(workflow, scenario) -> dict:
    """Run a single scripted scenario and return scored result dict."""
    # Inject synthetic alarms before run
    import importlib
    ah_module = importlib.import_module("nat.tools.query_alarm_history")
    ah_module.SYNTHETIC_ALARMS = scenario.injected_alarms

    start = time.monotonic()
    raw_output = await workflow.run(scenario.description)
    elapsed = time.monotonic() - start

    try:
        rca = json.loads(raw_output)
    except (json.JSONDecodeError, TypeError):
        rca = {"root_cause": "", "evidence": [], "kpis_evaluated": []}

    t4_score = score_t4(
        rca,
        scenario.ground_truth_root_cause_category,
        scenario.ground_truth_evidence_keywords,
    )

    return {
        "scenario_id": scenario.id,
        "t4_score": t4_score,
        "correct": t4_score == 3,
        "latency_s": round(elapsed, 3),
        "rca": rca,
    }


async def run_eval(model_name: str, workflow_config: str = "workflow.yml") -> None:
    """Run all scripted scenarios and write results to eval/results/."""
    try:
        from nat.builder.workflow_builder import WorkflowBuilder
    except ImportError as e:
        raise ImportError(
            "nvidia-nat[langchain] is required. Install it with: pip install nvidia-nat[langchain]"
        ) from e

    workflow = WorkflowBuilder.from_config(workflow_config).build()
    version = dataset_version()
    results = []

    for scenario in SCENARIOS:
        print(f"Running {scenario.id} ...")
        result = await run_scenario(workflow, scenario)
        results.append(result)
        print(f"  T4 score: {result['t4_score']}/3  correct: {result['correct']}")

    total = len(SCENARIOS)
    correct = sum(1 for r in results if r["correct"])
    accuracy_pct = (correct / total) * 100

    summary = {
        "model": model_name,
        "dataset_version": version,
        "rca_accuracy_pct": round(accuracy_pct, 1),
        "correct_count": correct,
        "total_count": total,
        "results": results,
    }

    out_file = RESULTS_DIR / f"{model_name.replace('/', '_')}_{version}.json"
    out_file.write_text(json.dumps(summary, indent=2))
    print(f"\nSummary written to {out_file}")
    print(f"RCA accuracy: {accuracy_pct:.1f}% ({correct}/{total})")


if __name__ == "__main__":
    import sys
    model = sys.argv[1] if len(sys.argv) > 1 else "nemotron_telco"
    asyncio.run(run_eval(model))
