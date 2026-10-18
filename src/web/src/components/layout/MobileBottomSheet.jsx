import { useMemo, useState } from "react";
import { CalendarPlus2, ClipboardList, PlayCircle, X, XCircle } from "lucide-react";

/**
 * Mobile action bar + info bottom sheet. Same props and behavior as before,
 * restyled for the new design. The info panel content is passed as children.
 */
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
        label: "Resume Session",
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
      label: "Course Info",
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
    <div className="fixed inset-x-0 bottom-0 z-40 border-t border-[#F3E2CF] bg-[#FDF6EC]/95 p-3 backdrop-blur lg:hidden">
      <div className="mx-auto max-w-5xl">
        <div className="grid grid-cols-[1fr_auto_auto] gap-2">
          <button
            type="button"
            className="inline-flex items-center justify-center gap-1.5 rounded-full bg-[#0E5F6B] px-3 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-[#0A4A55] disabled:cursor-not-allowed disabled:opacity-50"
            onClick={primaryAction.onClick}
            disabled={primaryAction.disabled}
          >
            <PrimaryIcon className="h-4 w-4" />
            {primaryAction.label}
          </button>

          <button
            type="button"
            className="rounded-full border border-[#EBD9C2] bg-white/80 px-4 py-2.5 text-xs font-semibold text-[#5B3A1E] transition hover:bg-white"
            onClick={() => setPanelOpen(true)}
          >
            Info
          </button>

          {canCloseCurrentVisit ? (
            <button
              type="button"
              className="inline-flex items-center justify-center gap-1 rounded-full bg-[#FBE3E0] px-4 py-2.5 text-xs font-semibold text-[#A33B2E] transition hover:bg-[#F8D5D0]"
              onClick={onCloseVisit}
            >
              <XCircle className="h-3.5 w-3.5" />
              End
            </button>
          ) : canCompleteCourse ? (
            <button
              type="button"
              className="rounded-full bg-[#E4F3E4] px-4 py-2.5 text-xs font-semibold text-[#2E7D32] transition hover:bg-[#D5EBD5]"
              onClick={onOpenCompleteCourseModal}
            >
              Complete
            </button>
          ) : (
            <div />
          )}
        </div>
      </div>

      {panelOpen ? (
        <div className="fixed inset-0 z-[75]">
          <button
            type="button"
            className="absolute inset-0 bg-slate-900/50"
            onClick={() => setPanelOpen(false)}
            aria-label="Close session information"
          />
          <div className="absolute inset-x-0 bottom-0 max-h-[80vh] overflow-y-auto rounded-t-[28px] border border-[#F3E2CF] bg-[#FDF6EC] p-4">
            <div className="mb-3 flex items-center justify-between">
              <p className="text-xs font-bold uppercase tracking-[0.12em] text-[#A08B6D]">
                Session Information
              </p>
              <button
                type="button"
                className="rounded-full p-1.5 text-[#8A7B66] transition hover:bg-[#F6E8D5]"
                onClick={() => setPanelOpen(false)}
                aria-label="Close session information"
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
