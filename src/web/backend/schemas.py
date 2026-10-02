from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from .domain import SchoolInfo, StageInfo


CourseStatus = Literal["active", "completed", "archived"]
VisitStatus = Literal["open", "closed"]
MessageRole = Literal["user", "assistant", "system"]


class VisitMessageOut(BaseModel):
    id: str
    role: MessageRole
    text: str
    created_at: Optional[datetime] = None


class CourseGoalOut(BaseModel):
    goal_id: str
    content: str
    sort_order: int
    status: str


class CourseStats(BaseModel):
    visit_count: int
    closed_visit_count: int
    message_count: int


class CoursePreview(BaseModel):
    course_id: str
    school: SchoolInfo
    title: str
    status: CourseStatus
    current_stage: StageInfo
    latest_visit_no: int
    active_visit_id: Optional[str] = None
    planned_visit_count: Optional[int] = None
    goal_summary: str = ""
    summary: str = ""
    updated_at: datetime
    created_at: datetime


class CourseDetail(CoursePreview):
    intake_note: str = ""
    goals: List[CourseGoalOut] = Field(default_factory=list)
    stats: CourseStats


class VisitPreview(BaseModel):
    visit_id: str
    visit_no: int
    stage: StageInfo
    status: VisitStatus
    message_count: int
    started_at: datetime
    ended_at: Optional[datetime] = None
    summary: str = ""


class VisitPsychContextOut(BaseModel):
    client_info: Dict[str, Any] = Field(default_factory=dict)
    session_focus: List[str] = Field(default_factory=list)
    history: List[Dict[str, Any]] = Field(default_factory=list)
    homework: List[str] = Field(default_factory=list)
    summary_payload: Dict[str, Any] = Field(default_factory=dict)
    profile_payload: Dict[str, Any] = Field(default_factory=dict)
    source: str = "derived_from_course_data_v1"
    updated_at: Optional[datetime] = None


class VisitState(VisitPreview):
    course_id: str
    messages: List[VisitMessageOut] = Field(default_factory=list)
    psych_context: Optional[VisitPsychContextOut] = None


class CreateCourseRequest(BaseModel):
    school_id: str = Field(..., description="Therapy modality ID")
    title: str = Field("", description="Therapy course title, optional")
    planned_visit_count: Optional[int] = Field(None, ge=1, description="Estimated total session count")
    goal_summary: str = Field("", description="Therapy course goal summary")
    intake_note: str = Field("", description="Initial intake background notes")
    goals: List[str] = Field(default_factory=list, description="Initial list of goals")
    auto_start_first_visit: bool = Field(True, description="Whether to automatically start the first session")
    opening_note: str = Field("", description="Opening note for the first session")


class CreateCourseResponse(BaseModel):
    course: CourseDetail
    created_visit: Optional[VisitState] = None


class UpdateCourseRequest(BaseModel):
    title: Optional[str] = None
    planned_visit_count: Optional[int] = Field(None, ge=1)
    goal_summary: Optional[str] = None
    intake_note: Optional[str] = None
    summary: Optional[str] = None
    goals: Optional[List[str]] = None


class CompleteCourseRequest(BaseModel):
    summary: str = Field("", description="Therapy course summary")


class CreateVisitRequest(BaseModel):
    opening_note: str = Field("", description="Opening note for the new session")


class SendVisitMessageRequest(BaseModel):
    text: str = Field(..., min_length=1, description="User input text")


class CourseMetaOut(BaseModel):
    course_id: str
    last_message_at: datetime
    updated_at: datetime


class SendVisitMessageResponse(BaseModel):
    visit: VisitState
    course_meta: CourseMetaOut


class CloseVisitRequest(BaseModel):
    summary: str = Field("", description="Session summary")


class CloseVisitResponse(BaseModel):
    visit_id: str
    status: VisitStatus
    ended_at: Optional[datetime] = None
    summary: str = ""
