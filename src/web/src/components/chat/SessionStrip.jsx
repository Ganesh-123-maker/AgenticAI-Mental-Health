import { CalendarPlus2, CheckCircle2, ChevronDown, PlayCircle, PlusCircle, XCircle } from "lucide-react";
import { useState } from "react";
import { getSchoolDisplayName } from "../common/schoolText";
import { formatVisitLabel, getCourseStatusText } from "../common/statusText";

/**
 * Horizontal session timeline + course/modality controls + header actions.
 * Replaces the old VisitTimeline column and HeaderBar action cluster.
 */
export function SessionStrip({
  currentSchool,
  schools,
  selectedSchoolId,
  courses,
  currentCourse,
  visits,
  currentVisit,
  canCreateCourse,
  canStartNextVisit,
  canCompleteCourse,
  token,
  onSelectSchool,
  onSelectCourse,
  onSelectVisit,
  onOpenCreateCourseModal,
  onStartNextVisit,
  onContinueVisit,
  onCloseVisit,
  onOpenCompleteCourseModal,
}) {
  const [courseMenuOpen, setCourseMenuOpen] = useState(false);
  const nextVisitNo = (currentCourse?.latest_visit_no || 0) + 1;
  const hasOpenVisit = currentVisit?.status === "open" || Boolean(currentCourse?.active_visit_id);

  const primaryAction = !currentCourse || currentCourse.status !== "active"
    ? {
        label: "New Course",
        icon: PlusCircle,
        onClick: onOpenCreateCourseModal,
        disabled: !canCreateCourse || !selectedSchoolId || !token,
      }
    : hasOpenVisit
    ? { label: "Resume Session", icon: PlayCircle, onClick: onContinueVisit, disabled: false }
    : {
        label: `Start Session ${nextVisitNo}`,
        icon: CalendarPlus2,
        onClick: onStartNextVisit,
        disabled: !canStartNextVisit,
      };
  const PrimaryIcon = primaryAction.icon;

  return (
    <div className="shrink-0 border-b border-[#F3E2CF] bg-[#FDF6EC]/70 px-4 py-3 sm:px-6">
      <div className="flex flex-wrap items-center gap-2">
        {/* Modality chip */}
        <button
          type="button"
          onClick={onSelectSchool}
          className="inline-flex items-center gap-1.5 rounded-full border border-[#EBD9C2] bg-white/80 px-3 py-1.5 text-xs font-semibold text-[#5B3A1E] transition hover:bg-white"
          title="Switch counseling modality"
        >
          {getSchoolDisplayName(currentSchool)}
          <ChevronDown className="h-3.5 w-3.5" />
        </button>

        {/* Course selector */}
        <div
          className="relative"
          onKeyDown={(event) => {
            if (event.key === "Escape") setCourseMenuOpen(false);
          }}
        >
          <button
            type="button"
            onClick={() => setCourseMenuOpen((v) => !v)}
            className="inline-flex items-center gap-1.5 rounded-full border border-[#EBD9C2] bg-white/80 px-3 py-1.5 text-xs font-semibold text-[#33484D] transition hover:bg-white"
            aria-haspopup="listbox"
            aria-expanded={courseMenuOpen}
            title="Select course"
          >
            <span className="max-w-40 truncate">
              {currentCourse ? currentCourse.title || "Untitled Course" : "Select course"}
            </span>
            {currentCourse ? (
              <span className="text-[10px] font-medium text-[#8A7B66]">
                {getCourseStatusText(currentCourse.status)}
              </span>
            ) : null}
            <ChevronDown className="h-3.5 w-3.5" />
          </button>
          {courseMenuOpen ? (
            <>
              <button
                type="button"
                className="fixed inset-0 z-10 cursor-default"
                onClick={() => setCourseMenuOpen(false)}
                aria-label="Close course list"
                tabIndex={-1}
              />
              <div className="absolute left-0 z-20 mt-2 max-h-64 w-64 overflow-y-auto rounded-2xl border border-[#EBD9C2] bg-white p-1.5 shadow-xl" role="listbox">
                {courses.length === 0 ? (
                  <p className="px-3 py-2 text-xs text-[#8A7B66]">No courses in this modality yet.</p>
                ) : (
                  courses.map((course) => (
                    <button
                      key={course.course_id}
                      type="button"
                      role="option"
                      aria-selected={currentCourse?.course_id === course.course_id}
                      onClick={() => {
                        onSelectCourse(course.course_id);
                        setCourseMenuOpen(false);
                      }}
                      className={`flex w-full items-center justify-between gap-2 rounded-xl px-3 py-2 text-left text-xs font-medium transition ${
                        currentCourse?.course_id === course.course_id
                          ? "bg-[#FBE3C8] text-[#5B3A1E]"
                          : "text-[#33484D] hover:bg-[#FDF1E7]"
                      }`}
                    >
                      <span className="truncate">{course.title || "Untitled Course"}</span>
                      <span className="shrink-0 text-[10px] text-[#8A7B66]">
                        {course.latest_visit_no || 0} sessions
                      </span>
                    </button>
                  ))
                )}
              </div>
            </>
          ) : null}
        </div>

        {/* Visit pills (session timeline) */}
        {visits.length > 0 ? (
          <div className="flex items-center gap-1.5 overflow-x-auto" role="list" aria-label="Session timeline">
            {visits.map((visit) => {
              const active = currentVisit?.visit_id === visit.visit_id;
              return (
                <button
                  key={visit.visit_id}
                  type="button"
                  role="listitem"
                  onClick={() => onSelectVisit(visit.visit_id)}
                  title={`${formatVisitLabel(visit.visit_no)} · ${visit.status === "open" ? "In progress" : "Closed"} · ${visit.message_count || 0} messages`}
                  className={`flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold transition ${
                    active
                      ? "border-[#0E5F6B] bg-[#0E5F6B] text-white shadow-sm"
                      : "border-[#EBD9C2] bg-white/70 text-[#5B6B6B] hover:bg-white"
                  }`}
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${visit.status === "open" ? "bg-emerald-400" : active ? "bg-white/70" : "bg-slate-300"}`}
                    aria-hidden="true"
                  />
                  S{visit.visit_no}
                </button>
              );
            })}
          </div>
        ) : null}

        <div className="ml-auto hidden items-center gap-2 sm:flex">
          <button
            type="button"
            onClick={primaryAction.onClick}
            disabled={primaryAction.disabled}
            className="inline-flex items-center gap-1.5 rounded-full bg-[#0E5F6B] px-4 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-[#0A4A55] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <PrimaryIcon className="h-3.5 w-3.5" />
            {primaryAction.label}
          </button>
          {hasOpenVisit ? (
            <button
              type="button"
              onClick={onCloseVisit}
              className="inline-flex items-center gap-1.5 rounded-full bg-[#FBE3E0] px-4 py-2 text-xs font-semibold text-[#A33B2E] transition hover:bg-[#F8D5D0]"
            >
              <XCircle className="h-3.5 w-3.5" />
              End Session
            </button>
          ) : null}
          {canCompleteCourse ? (
            <button
              type="button"
              onClick={onOpenCompleteCourseModal}
              className="inline-flex items-center gap-1.5 rounded-full bg-[#E4F3E4] px-4 py-2 text-xs font-semibold text-[#2E7D32] transition hover:bg-[#D5EBD5]"
            >
              <CheckCircle2 className="h-3.5 w-3.5" />
              Complete Course
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
