import { useEffect, useState } from "react";
import { X } from "lucide-react";

export function CompleteCourseModal({ open, currentCourse, onClose, onConfirm }) {
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setSubmitting(false);
  }, [open, currentCourse?.course_id]);

  if (!open) return null;

  async function handleConfirm() {
    if (submitting) return;
    setSubmitting(true);
    try {
      const ok = await onConfirm?.();
      if (ok) {
        onClose?.();
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center z-[80] p-4">
      <div className="bg-white border border-slate-200 shadow-2xl rounded-2xl w-full max-w-lg p-6 space-y-4 relative">
        <button className="absolute top-3 right-3 text-slate-400 hover:text-slate-600" onClick={onClose}>
          <X className="w-5 h-5" />
        </button>

        <div>
          <h3 className="text-lg font-bold text-slate-800">Complete Course</h3>
          <p className="text-sm text-slate-500 mt-1">
            The current therapy course will be marked as completed. Course: {currentCourse?.title || "Untitled Course"}
          </p>
        </div>

        <div className="flex gap-2">
          <button
            onClick={onClose}
            className="flex-1 bg-slate-100 text-slate-700 rounded-lg py-2 text-sm hover:bg-slate-200 transition"
            disabled={submitting}
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            className="flex-1 bg-emerald-600 text-white rounded-lg py-2 text-sm font-semibold hover:bg-emerald-700 transition disabled:opacity-50 disabled:cursor-not-allowed"
            disabled={submitting}
          >
            {submitting ? "Processing..." : "Confirm Completion"}
          </button>
        </div>
      </div>
    </div>
  );
}
