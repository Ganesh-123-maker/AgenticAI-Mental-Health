import { useEffect, useMemo, useState } from "react";
import { X } from "lucide-react";

const INITIAL_FORM = {
  title: "",
};

export function CreateCourseModal({ open, currentSchool, onClose, onSubmit }) {
  const [form, setForm] = useState(INITIAL_FORM);
  const [submitting, setSubmitting] = useState(false);

  const defaultTitle = useMemo(() => {
    if (!currentSchool?.name) return "";
    return `${currentSchool.name} Course`;
  }, [currentSchool?.name]);

  useEffect(() => {
    if (!open) return;
    setForm({ ...INITIAL_FORM, title: defaultTitle });
    setSubmitting(false);
  }, [open, defaultTitle]);

  if (!open) return null;

  async function handleSubmit(event) {
    event.preventDefault();
    if (submitting) return;

    setSubmitting(true);

    const payload = {
      title: form.title.trim(),
    };

    try {
      const ok = await onSubmit?.(payload);
      if (ok) {
        onClose?.();
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[85] flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm">
      <div className="relative w-full max-w-xl rounded-3xl border border-[#F3E2CF] bg-[#FDF6EC] p-6 shadow-2xl">
        <button
          type="button"
          className="absolute right-4 top-4 rounded-full p-1.5 text-[#8A7B66] transition hover:bg-[#F6E8D5]"
          onClick={onClose}
          disabled={submitting}
          aria-label="Close new course dialog"
        >
          <X className="h-5 w-5" />
        </button>

        <div className="mb-4">
          <h3 className="text-lg font-bold text-[#123B43]">New Therapy Course</h3>
          <p className="mt-1 text-sm text-[#6B7C7C]">
            Enter a course title. The initial session will be generated automatically.
          </p>
        </div>

        <form className="space-y-4" onSubmit={handleSubmit}>
          <div>
            <label htmlFor="course-title" className="mb-1.5 block text-sm font-semibold text-[#33484D]">
              Course Title
            </label>
            <input
              id="course-title"
              className="w-full rounded-2xl border border-[#EBD9C2] bg-white px-4 py-2.5 text-sm text-[#33484D] placeholder:text-[#B39B7D] focus:border-[#0E5F6B]/60 focus:outline-none"
              value={form.title}
              onChange={(event) => setForm((prev) => ({ ...prev, title: event.target.value }))}
              placeholder="e.g., Anxiety Management & Cognitive Reframing"
              maxLength={80}
            />
          </div>

          <div className="flex gap-2 pt-1">
            <button
              type="button"
              className="flex-1 rounded-full bg-[#F6E8D5] py-2.5 text-sm font-semibold text-[#5B3A1E] transition hover:bg-[#F3DDC2]"
              onClick={onClose}
              disabled={submitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="flex-1 rounded-full bg-[#0E5F6B] py-2.5 text-sm font-semibold text-white transition hover:bg-[#0A4A55] disabled:cursor-not-allowed disabled:opacity-50"
              disabled={submitting}
            >
              {submitting ? "Creating..." : "Create Course"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
