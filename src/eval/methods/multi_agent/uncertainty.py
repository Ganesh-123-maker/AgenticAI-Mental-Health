"""Uncertainty Evaluation Method for PsychAgent Multi-Agent System.

Computes:
- precision / recall / F1 of uncertainty_agent.status vs benchmark expected_route
- false_certainty_rate: CLEAR predicted when benchmark says UNCERTAIN / HIGH-RISK
- clarification_relevance: whether clarification questions target actual missing_information
- reassessment_accuracy: whether reassessment updated state appropriately
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ...core.base import EvaluationMethod


class Uncertainty(EvaluationMethod):
    """Evaluates uncertainty detection, false-certainty rate, and clarification/reassessment quality."""

    async def evaluate(
        self,
        gpt_api: Any = None,
        dialogue: Any = None,
        profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, float]:
        trail, meta = self._extract_trail_and_meta(dialogue, profile)
        return self.compute_metrics(trail, meta)

    @classmethod
    def compute_metrics(
        cls,
        trail: List[Dict[str, Any]],
        benchmark_meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, float]:
        """Synchronously compute uncertainty metrics."""
        meta = benchmark_meta or {}
        expected_route = str(meta.get("expected_route", "CLEAR")).upper()
        missing_fields = list(meta.get("missing_information", []) or [])

        # Ground truth: is this case expected to route to UNCERTAIN/HIGH-RISK vs CLEAR?
        gt_uncertain = expected_route in ("UNCERTAIN", "HIGH-RISK", "AMBIGUOUS")

        # Extract uncertainty agent prediction
        unc_status = "CLEAR"
        pred_uncertain = False
        unc_missing = []

        for step in trail:
            if step.get("agent") == "uncertainty_agent":
                payload = step.get("payload", {})
                unc_status = str(payload.get("status", "CLEAR")).upper()
                unc_missing = list(payload.get("missing_information", []) or [])
                pred_uncertain = unc_status in ("UNCERTAIN", "AMBIGUOUS")
                break

        # 1. Precision / Recall / F1 of uncertainty_agent.status vs benchmark expected_route
        if pred_uncertain == gt_uncertain:
            prec, rec, f1 = 1.0, 1.0, 1.0
        elif pred_uncertain and not gt_uncertain:
            prec, rec, f1 = 0.0, 1.0, 0.0
        else:
            prec, rec, f1 = 1.0, 0.0, 0.0

        # 2. False Certainty Rate
        # CLEAR predicted when benchmark expected UNCERTAIN or HIGH-RISK
        false_certainty = 1.0 if (not pred_uncertain and gt_uncertain) else 0.0

        # 3. Clarification Relevance
        # Did clarification_agent ask questions targeting the missing information?
        clarification_questions = []
        for step in trail:
            if step.get("agent") == "clarification_agent":
                payload = step.get("payload", {})
                qs = payload.get("clarifying_questions", []) or payload.get("questions", [])
                if isinstance(qs, list):
                    clarification_questions.extend(str(q) for q in qs)

        if not missing_fields:
            # No missing information expected
            clarification_relevance = 1.0 if not clarification_questions else 0.5
        elif not clarification_questions:
            # Missing info existed, but clarification wasn't called (or was skipped)
            clarification_relevance = 1.0 if not pred_uncertain else 0.0
        else:
            # Check overlap between clarification questions and target missing fields
            combined_q_text = " ".join(clarification_questions).lower()
            field_hits = 0
            for field in missing_fields:
                field_lower = field.lower()
                tokens = re.findall(r"\w+", field_lower)
                # Map domain concepts
                keywords = tokens + ["medical", "physical", "diagnosis", "treatment", "medication", "history", "past", "experience"] if "medical" in field_lower else tokens
                if any(k in combined_q_text for k in keywords if len(k) >= 2):
                    field_hits += 1
            clarification_relevance = field_hits / len(missing_fields) if missing_fields else 1.0

        # 4. Reassessment Accuracy
        # If reassessment agent ran, did it update the status/route accurately?
        reassessment_ran = False
        reassessment_accurate = 1.0
        for step in trail:
            if step.get("agent") == "reassessment_agent":
                reassessment_ran = True
                payload = step.get("payload", {})
                new_status = str(payload.get("status", "")).upper()
                if new_status == "CLEAR":
                    reassessment_accurate = 1.0
                elif new_status in ("UNCERTAIN", "AMBIGUOUS"):
                    reassessment_accurate = 1.0 if gt_uncertain else 0.0

        return {
            "uncertainty_precision": round(float(prec), 4),
            "uncertainty_recall": round(float(rec), 4),
            "uncertainty_f1": round(float(f1), 4),
            "false_certainty_rate": round(float(false_certainty), 4),
            "clarification_relevance": round(float(clarification_relevance), 4),
            "reassessment_accuracy": round(float(reassessment_accurate), 4),
        }

    def _extract_trail_and_meta(
        self,
        dialogue: Any,
        profile: Optional[Dict[str, Any]],
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        trail: List[Dict[str, Any]] = []
        meta: Dict[str, Any] = profile or {}

        if isinstance(dialogue, dict):
            if "trail" in dialogue and isinstance(dialogue["trail"], list):
                trail = dialogue["trail"]
            if "profile" in dialogue and isinstance(dialogue["profile"], dict):
                meta = dialogue["profile"]
            elif "expected_route" in dialogue:
                meta = dialogue
        elif isinstance(dialogue, list):
            if dialogue and isinstance(dialogue[0], dict) and "agent" in dialogue[0]:
                trail = dialogue

        return trail, meta
