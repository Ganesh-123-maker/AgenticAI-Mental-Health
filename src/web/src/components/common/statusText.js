const COURSE_STATUS_LABELS = {
  active: "In Progress",
  completed: "Completed",
  archived: "Archived",
};

const VISIT_STATUS_LABELS = {
  open: "In Progress",
  closed: "Closed",
};

export function getCourseStatusText(status) {
  return COURSE_STATUS_LABELS[status] || "Unknown Status";
}

export function getVisitStatusText(status) {
  return VISIT_STATUS_LABELS[status] || "Unknown Status";
}

export function formatVisitLabel(visitNo) {
  const normalizedNo = Number(visitNo) || 0;
  return `Session ${normalizedNo}`;
}
