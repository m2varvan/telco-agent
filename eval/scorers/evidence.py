# eval/scorers/evidence.py
"""
Evidence Grounding Evaluator.

Measures whether the agent's evidence items match the required evidence items
defined in the ground truth.

Matching strategy (source-domain + field/counter text):
  - A predicted evidence item is "correct" if:
      1. Its source domain matches a required item's source domain, AND
      2. If the required item specifies a field/metric, that string appears
         (case-insensitive) somewhere in the predicted item's observation text,
         field attribute, or table attribute.
  - If the required item only specifies a source domain, a match on source alone
    is sufficient.

Metrics returned:
  precision          = correct predicted items / all predicted items
  recall             = required items matched / all required items
  f1                 = harmonic mean of precision and recall
  unsupported_rate   = predicted items with NO matching required item / all predicted
"""
from __future__ import annotations
import re


def _source_domain(source: str) -> str:
    """Normalise source domain label to one of: KPI, CM, Alarm, NR, Other."""
    s = source.strip().upper()
    if s in ("KPI", "LTE", "LTE_KPI"):
        return "KPI"
    if s in ("CM", "CONFIG", "CONFIGURATION"):
        return "CM"
    if s in ("ALARM", "ALARM_HISTORY", "ALARMS"):
        return "ALARM"
    if s in ("NR", "NR_ENDC", "ENDC", "5G"):
        return "NR"
    return s


def _item_text(item: dict) -> str:
    """Collect all searchable text from an evidence item."""
    parts = [
        item.get("observation", ""),
        item.get("field", ""),
        item.get("table", ""),
        item.get("metric", ""),
        # Some models return evidence as plain strings — include the whole value
        item.get("_raw_text", ""),
    ]
    return " ".join(str(p) for p in parts if p).lower()


def _normalise_evidence_item(item) -> dict:
    """Normalise evidence item to dict form regardless of input type."""
    if isinstance(item, dict):
        return item
    if isinstance(item, str):
        # Infer source domain from string content
        s = item.lower()
        if any(x in s for x in ("pmrrc", "pmerab", "pmpdcp", "pms1", "pmcell", "pmueth", "pmpdcplat",
                                  "accessibility", "retainability", "throughput", "latency", "availability")):
            src = "KPI"
        elif any(x in s for x in ("cellbarred", "administrativestate", "dlchannelbandwidth",
                                   "freqband", "earfcn", "cm", "config", "change")):
            src = "CM"
        elif any(x in s for x in ("alarm", "backhaul", "outage", "power failure",
                                   "interference", "downtime")):
            src = "ALARM"
        elif any(x in s for x in ("pmendcsetup", "en-dc", "endc", "nr ", "5g")):
            src = "NR"
        else:
            src = "Unknown"
        return {"source": src, "observation": item, "_raw_text": item}
    return {"source": "Unknown", "observation": str(item), "_raw_text": str(item)}


def _matches_required(predicted: dict, required: dict) -> bool:
    """
    Return True if the predicted evidence item satisfies the required item.
    """
    pred_domain = _source_domain(predicted.get("source", ""))
    req_domain = _source_domain(required.get("source", ""))

    if pred_domain != req_domain:
        return False

    # If no specific field/metric required, source match is enough
    req_field = (required.get("field") or required.get("metric") or "").strip()
    if not req_field:
        return True

    # Check whether required field/metric appears in predicted item text
    pred_text = _item_text(predicted)
    return req_field.lower() in pred_text


class EvidenceGroundingEvaluator:
    """Evaluates evidence precision, recall, F1, and unsupported rate."""

    def evaluate(
        self,
        predicted_evidence: list[dict],
        required_evidence: list[dict],
    ) -> dict:
        """
        Parameters
        ----------
        predicted_evidence : list[dict]
            Evidence items from the agent output. Each item has at least
            {"source": str, "observation": str} and optionally field/table.
        required_evidence : list[dict]
            Ground-truth required evidence items. Each has at least {"source": str}
            and optionally field/metric.

        Returns
        -------
        dict with keys:
            precision          (float)
            recall             (float)
            f1                 (float)
            unsupported_rate   (float)
            matched_required   (int)   – count of required items covered
            supported_count    (int)   – count of predicted items that matched something
        """
        if not predicted_evidence and not required_evidence:
            return {
                "precision": 1.0, "recall": 1.0, "f1": 1.0,
                "unsupported_rate": 0.0,
                "matched_required": 0, "supported_count": 0,
            }

        # Normalise all items to dict form
        predicted_evidence = [_normalise_evidence_item(e) for e in predicted_evidence]

        n_pred = len(predicted_evidence)
        n_req = len(required_evidence)

        # For each required item, track whether it was matched
        req_matched = [False] * n_req
        # For each predicted item, track whether it matched any required item
        pred_supported = [False] * n_pred

        for pi, pred in enumerate(predicted_evidence):
            for ri, req in enumerate(required_evidence):
                if _matches_required(pred, req):
                    req_matched[ri] = True
                    pred_supported[pi] = True

        matched_required = sum(req_matched)
        supported_count = sum(pred_supported)

        precision = supported_count / n_pred if n_pred > 0 else 0.0
        recall = matched_required / n_req if n_req > 0 else 1.0
        f1 = (
            (2 * precision * recall) / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )
        unsupported_rate = (
            (n_pred - supported_count) / n_pred if n_pred > 0 else 0.0
        )

        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "unsupported_rate": round(unsupported_rate, 4),
            "matched_required": matched_required,
            "supported_count": supported_count,
        }
