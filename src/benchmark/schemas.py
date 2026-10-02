"""Typed schema for the ambiguous-case benchmark.

Follows the dataclass/plain-dict style used throughout the project
(see src/sample/core/schemas.py).  No external runtime dependencies
beyond the stdlib.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal


# ---------------------------------------------------------------------------
# AmbiguousCase record
# ---------------------------------------------------------------------------

@dataclass
class AmbiguousCase:
    """One ambiguous-case benchmark record derived from a real source profile.

    Fields
    ------
    case_id
        Stable identifier composed as ``<modality>_<profile_stem>_<track>``.
    source_file
        Relative path to the original profile JSON under assets/profiles/.
    modality
        One of ``bt | cbt | het | pdt | pmt``.
    therapy_stage
        Inferred from ``growth_experiences`` when possible; otherwise
        ``"Problem conceptualization and goal setting"`` (earliest stage).  A ``stage_inferred``
        flag records whether inference succeeded.
    stage_inferred
        True when therapy_stage was derived from the profile; False when
        defaulted.
    track
        ``"ordinary"`` hides non-safety fields; ``"safety"`` hides fields
        that would reveal risk level or safety status.
    full_context
        Complete original profile dict (read-only copy, never modified).
    ambiguous_context
        Same structure as full_context but with the fields listed in
        ``missing_information`` removed.
    uncertainty_type
        Short label for the information gap, e.g. ``"missing_duration"``.
    missing_information
        List of dot-notation field paths that were hidden, e.g.
        ``["basic_info.growth_experiences"]``.
    expected_clarification
        One or two plausible questions a counsellor should ask to recover
        the hidden information.
    risk_level
        Assessed from the FULL profile, not the ambiguous one.
    expected_route
        ``"CLEAR"`` / ``"UNCERTAIN"`` / ``"HIGH-RISK"``.
    expected_action
        One-line description of the correct system behaviour.
    ground_truth_evidence
        Mapping from field path to its literal hidden value, enabling
        automated scoring against model output.
    """

    case_id: str
    source_file: str
    modality: str
    therapy_stage: str
    stage_inferred: bool
    track: Literal["ordinary", "safety"]
    full_context: Dict[str, Any]
    ambiguous_context: Dict[str, Any]
    uncertainty_type: str
    missing_information: List[str]
    expected_clarification: List[str]
    risk_level: Literal["LOW", "MODERATE", "HIGH", "UNCERTAIN"]
    expected_route: Literal["CLEAR", "UNCERTAIN", "HIGH-RISK"]
    expected_action: str
    ground_truth_evidence: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, *, indent: int = 2, ensure_ascii: bool = False) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=ensure_ascii)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AmbiguousCase":
        return cls(
            case_id=str(data["case_id"]),
            source_file=str(data["source_file"]),
            modality=str(data["modality"]),
            therapy_stage=str(data["therapy_stage"]),
            stage_inferred=bool(data["stage_inferred"]),
            track=str(data["track"]),  # type: ignore[arg-type]
            full_context=dict(data["full_context"]),
            ambiguous_context=dict(data["ambiguous_context"]),
            uncertainty_type=str(data["uncertainty_type"]),
            missing_information=list(data["missing_information"]),
            expected_clarification=list(data["expected_clarification"]),
            risk_level=str(data["risk_level"]),  # type: ignore[arg-type]
            expected_route=str(data["expected_route"]),  # type: ignore[arg-type]
            expected_action=str(data["expected_action"]),
            ground_truth_evidence=dict(data["ground_truth_evidence"]),
        )
