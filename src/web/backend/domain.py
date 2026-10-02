from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import HTTPException
from pydantic import BaseModel


class StageInfo(BaseModel):
    key: str
    label: str
    desc: str
    range: List[int]
    color: Optional[str] = None


class SchoolInfo(BaseModel):
    id: str
    name: str
    color: str
    desc: str
    style: str


STAGES: Dict[str, Dict[str, object]] = {
    "assessment": {
        "label": "Problem Conceptualization & Goal Setting",
        "range": [1, 2],
        "desc": "Focuses on problem definition, information gathering, rapport building, and actionable goal setting",
        "color": "text-blue-600 bg-blue-50",
    },
    "intervention": {
        "label": "Core Cognitive & Behavioral Intervention",
        "range": [3, 8],
        "desc": "Structured interventions and exercises targeting key cognitive and behavioral patterns",
        "color": "text-purple-600 bg-purple-50",
    },
    "consolidation": {
        "label": "Consolidation & Relapse Prevention",
        "range": [9, 10],
        "desc": "Synthesizing gains, skill transfer, relapse prevention, and termination planning",
        "color": "text-green-600 bg-green-50",
    },
}


SCHOOLS: List[SchoolInfo] = [
    SchoolInfo(
        id="behavioral",
        name="Behavior Therapy (BT)",
        color="bg-amber-500",
        desc="Modifies specific behavioral patterns via reinforcement, desensitization, and modeling; emphasizes observable, actionable, and trackable change.",
        style="Direct, practical, training-oriented",
    ),
    SchoolInfo(
        id="cbt",
        name="Cognitive Behavioral Therapy (CBT)",
        color="bg-blue-500",
        desc="Focuses on connections between thoughts, emotions, and behaviors; identifies and restructures distressing automatic thoughts.",
        style="Rational, structured, problem-solving focused",
    ),
    SchoolInfo(
        id="humanistic",
        name="Humanistic-Existential Therapy (HET)",
        color="bg-rose-500",
        desc="Emphasizes genuine relationship, acceptance, and meaning exploration; empowers clients to understand present experience and make autonomous choices.",
        style="Warm, accepting, person-centered",
    ),
    SchoolInfo(
        id="psychodynamic",
        name="Psychodynamic Therapy (PDT)",
        color="bg-indigo-600",
        desc="Explores unconscious conflicts and early experiences impacting current relational and emotional patterns; fosters deep self-understanding.",
        style="In-depth exploration, insight-oriented, focused on relational dynamics",
    ),
    SchoolInfo(
        id="postmodern",
        name="Postmodern Therapy (PMT)",
        color="bg-teal-500",
        desc="Externalizes problems, deconstructs narratives, and identifies exceptions to help clients author empowering life stories.",
        style="Collaborative, empowering, multi-perspective",
    ),
]

SCHOOL_TO_PSYCHAGENT_SECT: Dict[str, str] = {
    "behavioral": "bt",
    "cbt": "cbt",
    "humanistic": "het",
    "psychodynamic": "pdt",
    "postmodern": "pmt",
}

STAGE_KEY_TO_SKILL_STAGE: Dict[str, int] = {
    "assessment": 1,
    "intervention": 2,
    "consolidation": 3,
}

SUMMARY_STAGE_TO_STAGE_KEY: Dict[str, str] = {
    "assessment": "assessment",
    "intervention": "intervention",
    "consolidation": "consolidation",
    "Problem Conceptualization & Goal Setting": "assessment",
    "Core Cognitive & Behavioral Intervention": "intervention",
    "Consolidation & Relapse Prevention": "consolidation",
    "Problem conceptualization and goal setting": "assessment",
    "Core cognitive and behavioral intervention": "intervention",
    "Consolidation and relapse prevention": "consolidation",
    # Backward-compatible aliases from older UI copy.
    "assessment_meeting": "assessment",
    "intervention_meeting": "intervention",
    "consolidation_meeting": "consolidation",
}


def stage_from_key(key: str) -> StageInfo:
    value = STAGES[key]
    return StageInfo(
        key=key,
        label=value["label"],
        desc=value["desc"],
        range=value["range"],
        color=value.get("color"),
    )


def get_stage_by_visit_no(visit_no: int) -> StageInfo:
    for key, value in STAGES.items():
        start, end = value["range"]
        if start <= visit_no <= end:
            return stage_from_key(key)
    last_key = list(STAGES.keys())[-1]
    return stage_from_key(last_key)


def pick_school(school_id: str) -> SchoolInfo:
    for school in SCHOOLS:
        if school.id == school_id:
            return school
    raise HTTPException(status_code=404, detail="School not found")


def school_to_psychagent_sect(school_id: str) -> str:
    sect = SCHOOL_TO_PSYCHAGENT_SECT.get(school_id)
    if not sect:
        raise HTTPException(status_code=404, detail="Unsupported school for PsychAgent prompts")
    return sect


def stage_key_to_skill_stage(stage_key: str) -> int:
    return STAGE_KEY_TO_SKILL_STAGE.get(stage_key, 1)


def summary_stage_to_stage_key(raw_stage: str) -> Optional[str]:
    text = str(raw_stage or "").strip()
    if not text:
        return None
    return SUMMARY_STAGE_TO_STAGE_KEY.get(text)
