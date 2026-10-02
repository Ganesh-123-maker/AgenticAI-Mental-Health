import { useMemo, useState } from "react";
import { CalendarPlus2, ChevronUp, ClipboardList, PlayCircle, X, XCircle } from "lucide-react";

export function MobileBottomSheet({
  token,
  selectedSchoolId,
  currentCourse,
  currentVisit,
  canCreateCourse,
  canStartNextVisit,
  canCompleteCourse,
  onOpenCreateCourseModal,
  onStartNextVisit,
  onContinueVisit,
  onCloseVisit,
  onOpenCompleteCourseModal,
  children,
}) {
  const [panelOpen, setPanelOpen] = useState(false);

  const hasOpenVisit = currentVisit?.status === "open" || Boolean(currentCourse?.active_visit_id);
  const canCloseCurrentVisit = currentVisit?.status === "open";
  const nextVisitNo = (currentCourse?.latest_visit_no || 0) + 1;

  const primaryAction = useMemo(() => {
    if (!currentCourse) {
      return {
        label: "New Course",
        onClick: onOpenCreateCourseModal,
        icon: CalendarPlus2,
        disabled: !canCreateCourse || !token || !selectedSchoolId,
      };
    }
    if (hasOpenVisit) {
      return {
        label: "Resume Current Session",
        onClick: onContinueVisit,
        icon: PlayCircle,
        disabled: false,
      };
    }
    if (canStartNextVisit) {
      return {
        label: `Start Session ${nextVisitNo}`,
        onClick: onStartNextVisit,
        icon: CalendarPlus2,
        disabled: false,
      };
    }
    return {
      label: "View Course Info",
      onClick: () => setPanelOpen(true),
      icon: ClipboardList,
      disabled: false,
    };
  }, [
    canStartNextVisit,
    currentCourse,
    hasOpenVisit,
    nextVisitNo,
    onContinueVisit,
    onOpenCreateCourseModal,
    onStartNextVisit,
    selectedSchoolId,
    token,
  ]);

  const PrimaryIcon = primaryAction.icon;

  return (
    <div className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-200 bg-white/95 p-3 backdrop-blur lg:hidden">
      <div className="mx-auto max-w-5xl">
        <div className="grid grid-cols-[1fr_auto_auto] gap-2">
          <button
            type="button"
            className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-teal-600 px-3 py-2 text-sm font-semibold text-white hover:bg-teal-700 disabled:cursor-not-allowed disabled:opacity-50"
            onClick={primaryAction.onClick}
            disabled={primaryAction.disabled}
          >
            <PrimaryIcon className="h-4 w-4" />
            {primaryAction.label}
          </button>

          <button
            type="button"
            className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50"
            onClick={() => setPanelOpen(true)}
          >
            Info
          </button>

          {canCloseCurrentVisit ? (
            <button
              type="button"
              className="inline-flex items-center justify-center gap-1 rounded-lg bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700 hover:bg-rose-100"
              onClick={onCloseVisit}
            >
              <XCircle className="h-3.5 w-3.5" />
              End
            </button>
          ) : canCompleteCourse ? (
            <button
              type="button"
              className="rounded-lg bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700 hover:bg-emerald-100"
              onClick={onOpenCompleteCourseModal}
            >
              Complete Course
            </button>
          ) : (
            <div />
          )}
        </div>
      </div>

      {panelOpen ? (
        <div className="fixed inset-0 z-[75] bg-slate-900/50">
          <button
            type="button"
            className="h-full w-full"
            onClick={() => setPanelOpen(false)}
            aria-label="Close course information"
          />
          <div className="absolute inset-x-0 bottom-0 max-h-[80vh] overflow-y-auto rounded-t-2xl border border-slate-200 bg-white p-4">
            <div className="mb-3 flex items-center justify-between">
              <div className="inline-flex items-center gap-1 text-xs font-medium text-slate-500">
                <ChevronUp className="h-4 w-4" />
                Course Information
              </div>
              <button
                type="button"
                className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                onClick={() => setPanelOpen(false)}
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            {children}
          </div>
        </div>
      ) : null}
    </div>
  );
}
