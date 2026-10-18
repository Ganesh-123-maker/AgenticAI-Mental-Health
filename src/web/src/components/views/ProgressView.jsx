import { CalendarCheck2, CheckCircle2, FolderOpen } from "lucide-react";
import { EmptyState } from "../common/EmptyState";
import { StatusPill } from "../common/StatusPill";
import { formatVisitLabel, getCourseStatusText, getVisitStatusText } from "../common/statusText";

function getCourseTone(status) {
  if (status === "active") return "active";
  if (status === "completed") return "success";
  if (status === "archived") return "neutral";
  return "warning";
}

function Stat({ value, label }) {
  return (
    <div className="rounded-3xl border border-[#F3E2CF] bg-white/85 p-4 text-center shadow-sm">
      <p className="text-2xl font-bold text-[#123B43]">{value}</p>
      <p className="mt-1 text-xs font-medium text-[#8A7B66]">{label}</p>
    </div>
  );
}

/**
 * Progress overview built from existing course/visit data already in the app.
 */
export function ProgressView({ courses, currentCourse, visits, hasToken, onSelectCourse }) {
  const activeCourses = courses.filter((c) => c.status === "active").length;
  const completedCourses = courses.filter((c) => c.status === "completed").length;
  const totalSessions = courses.reduce((sum, c) => sum + (c.latest_visit_no || 0), 0);

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-8">
      <div className="mx-auto max-w-4xl">
        <h2 className="text-xl font-bold text-[#123B43]">Your Progress</h2>
        <p className="mt-1 text-sm leading-6 text-[#6B7C7C]">
          Courses and sessions across your counseling journey.
        </p>

        {!hasToken ? (
          <div className="mt-6">
            <EmptyState
              icon={FolderOpen}
              title="Sign in to see your progress"
              description="Your courses and session history will appear here after you sign in."
            />
          </div>
        ) : (
          <>
            <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat value={courses.length} label="Courses" />
              <Stat value={activeCourses} label="Active" />
              <Stat value={completedCourses} label="Completed" />
              <Stat value={totalSessions} label="Sessions" />
            </div>

            <h3 className="mt-8 text-sm font-bold uppercase tracking-[0.12em] text-[#A08B6D]">Courses</h3>
            <div className="mt-3 space-y-3">
              {courses.map((course) => {
                const selected = currentCourse?.course_id === course.course_id;
                return (
                  <button
                    key={course.course_id}
                    type="button"
                    onClick={() => onSelectCourse(course.course_id)}
                    className={`w-full rounded-3xl border p-4 text-left shadow-sm transition ${
                      selected
                        ? "border-[#0E5F6B]/40 bg-white"
                        : "border-[#F3E2CF] bg-white/85 hover:bg-white"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-bold text-[#123B43]">{course.title || "Untitled Course"}</p>
                      <StatusPill text={getCourseStatusText(course.status)} tone={getCourseTone(course.status)} />
                    </div>
                    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[#6B7C7C]">
                      <span>Stage: {course.current_stage?.label || "Not Started"}</span>
                      <span>Sessions: {course.latest_visit_no || 0}</span>
                      <span>{course.active_visit_id ? "Session in progress" : "No active session"}</span>
                    </div>
                  </button>
                );
              })}
              {courses.length === 0 ? (
                <p className="text-sm text-[#8A7B66]">No courses yet. Create one from the Sessions view.</p>
              ) : null}
            </div>

            {currentCourse ? (
              <>
                <h3 className="mt-8 flex items-center gap-2 text-sm font-bold uppercase tracking-[0.12em] text-[#A08B6D]">
                  <CalendarCheck2 className="h-4 w-4" />
                  Sessions in {currentCourse.title || "current course"}
                </h3>
                <div className="mt-3 space-y-2.5">
                  {visits.map((visit) => (
                    <div
                      key={visit.visit_id}
                      className="flex items-center justify-between rounded-2xl border border-[#F3E2CF] bg-white/85 px-4 py-3"
                    >
                      <div>
                        <p className="text-sm font-bold text-[#123B43]">{formatVisitLabel(visit.visit_no)}</p>
                        <p className="text-[11px] text-[#8A7B66]">
                          {visit.stage?.label || "Not Started"} · {visit.message_count || 0} messages
                        </p>
                      </div>
                      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-[#6B7C7C]">
                        {visit.status === "closed" ? (
                          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                        ) : null}
                        {getVisitStatusText(visit.status)}
                      </span>
                    </div>
                  ))}
                  {visits.length === 0 ? (
                    <p className="text-sm text-[#8A7B66]">No sessions recorded for this course yet.</p>
                  ) : null}
                </div>
              </>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
