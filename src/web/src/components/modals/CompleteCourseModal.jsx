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
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm">
      <div className="relative w-full max-w-lg space-y-4 rounded-3xl border border-[#F3E2CF] bg-[#FDF6EC] p-6 shadow-2xl">
        <button
          type="button"
          className="absolute right-4 top-4 rounded-full p-1.5 text-[#8A7B66] transition hover:bg-[#F6E8D5]"
          onClick={onClose}
          aria-label="Close complete course dialog"
        >
          <X className="h-5 w-5" />
        </button>

        <div>
          <h3 className="text-lg font-bold text-[#123B43]">Complete Course</h3>
          <p className="mt-1 text-sm text-[#6B7C7C]">
            The current therapy course will be marked as completed. Course: {currentCourse?.title || "Untitled Course"}
          </p>
        </div>

        <div className="flex gap-2">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 rounded-full bg-[#F6E8D5] py-2.5 text-sm font-semibold text-[#5B3A1E] transition hover:bg-[#F3DDC2]"
            disabled={submitting}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            className="flex-1 rounded-full bg-emerald-600 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={submitting}
          >
            {submitting ? "Processing..." : "Confirm Completion"}
          </button>
        </div>
      </div>
    </div>
  );
}
