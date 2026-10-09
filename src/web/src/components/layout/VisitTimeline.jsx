import { Clock3, MessageSquarePlus, Milestone } from "lucide-react";
import { EmptyState } from "../common/EmptyState";
import { StatusPill } from "../common/StatusPill";
import { formatVisitLabel, getVisitStatusText } from "../common/statusText";

function getVisitTone(status) {
  if (status === "open") return "active";
  if (status === "closed") return "neutral";
  return "warning";
}

export function VisitTimeline({
  currentCourse,
  visits,
  currentVisit,
  canStartNextVisit,
  onStartNextVisit,
  onSelectVisit,
}) {
  const nextVisitNo = (currentCourse?.latest_visit_no || 0) + 1;

  return (
    <aside className="hidden shrink-0 lg:flex lg:w-64 xl:w-72 border-r border-slate-200 bg-slate-50/80 flex-col">
      <div className="border-b border-slate-200 p-4">
        <h2 className="text-sm font-semibold text-slate-800">Session Timeline</h2>
        <p className="mt-1 text-xs leading-5 text-slate-600">
          {currentCourse
            ? `Review timeline of sessions for ${currentCourse.title}.`
            : "Select a course to view session history."}
        </p>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {!currentCourse ? (
          <EmptyState
            icon={Milestone}
            title="No Course Selected"
            description="Please select a course from the left to view session progress."
          />
        ) : visits.length === 0 ? (
          <EmptyState
            icon={Clock3}
            title="No Sessions Recorded"
            description="The initial session is generated with the course, or can be started manually below."
            action={
              canStartNextVisit ? (
                <button
                  type="button"
                  className="inline-flex items-center rounded-lg bg-teal-600 px-3 py-2 text-xs font-semibold text-white hover:bg-teal-700"
                  onClick={onStartNextVisit}
                >
                  Start Session {nextVisitNo}
                </button>
              ) : null
            }
          />
        ) : (
          visits.map((visit) => (
            <button
              key={visit.visit_id}
              type="button"
              onClick={() => onSelectVisit?.(visit.visit_id)}
              className={`w-full rounded-xl border bg-white p-3 text-left transition ${
                currentVisit?.visit_id === visit.visit_id
                  ? "border-teal-300 ring-2 ring-teal-100"
                  : "border-slate-200 hover:border-teal-200"
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-semibold text-slate-800">{formatVisitLabel(visit.visit_no)}</p>
                  <p className="mt-1 text-xs text-slate-600">Stage: {visit.stage?.label || "Not Started"}</p>
                </div>
                <StatusPill text={getVisitStatusText(visit.status)} tone={getVisitTone(visit.status)} />
              </div>

              <div className="mt-3 flex items-center justify-between text-xs text-slate-600">
                <span className="inline-flex items-center gap-1">
                  <MessageSquarePlus className="h-3.5 w-3.5" />
                  {visit.message_count || 0} messages
                </span>
                <span>{visit.ended_at ? "Closed" : "Active"}</span>
              </div>
            </button>
          ))
        )}
      </div>
    </aside>
  );
}
