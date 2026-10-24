import { useEffect } from "react";
import { CircleHelp, ShieldAlert, X } from "lucide-react";

const STEPS = [
  { title: "Pick a modality", text: "Choose a counseling approach (BT, CBT, HET, PDT, PMT) from the session bar." },
  { title: "Create a course", text: "Start a therapy course — the first session is generated automatically." },
  { title: "Chat in sessions", text: "Talk with the counselor, try suggested exercises, and end the session when ready." },
  { title: "Track progress", text: "Review stages, goals, and session history in the sidebar views." },
];

/**
 * Help modal: how the app works + safety information.
 * Safety wording kept verbatim from the existing UI.
 */
export function HelpModal({ open, onClose }) {
  // Escape closes the dialog, replicating the auth modal's pattern.
  useEffect(() => {
    if (!open) return undefined;
    function handleKey(event) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm">
      <div className="relative max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-3xl border border-[#F3E2CF] bg-[#FDF6EC] p-6 shadow-2xl">
        <button
          type="button"
          className="absolute right-4 top-4 rounded-full p-1.5 text-[#8A7B66] transition hover:bg-[#F6E8D5]"
          onClick={onClose}
          aria-label="Close help"
        >
          <X className="h-5 w-5" />
        </button>

        <div className="flex items-center gap-2.5">
          <span className="rounded-2xl bg-[#0E5F6B]/10 p-2 text-[#0E5F6B]">
            <CircleHelp className="h-5 w-5" />
          </span>
          <h2 className="text-lg font-bold text-[#123B43]">How PsychAgent Works</h2>
        </div>

        <ol className="mt-4 space-y-3">
          {STEPS.map((step, index) => (
            <li key={step.title} className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#0E5F6B] text-xs font-bold text-white">
                {index + 1}
              </span>
              <div>
                <p className="text-sm font-bold text-[#123B43]">{step.title}</p>
                <p className="text-xs leading-5 text-[#6B7C7C]">{step.text}</p>
              </div>
            </li>
          ))}
        </ol>

        <div className="mt-5 rounded-2xl border border-[#F3E2CF] bg-white/80 p-4">
          <div className="flex items-center gap-2">
            <ShieldAlert className="h-4 w-4 text-[#A33B2E]" />
            <h3 className="text-sm font-bold text-[#123B43]">Safety Information</h3>
          </div>
          <ul className="mt-2 space-y-1.5 text-xs leading-5 text-[#5B6B6B]">
            <li>AI responses are for research and educational reference only and do not replace professional medical advice.</li>
            <li>AI responses are for reference and do not replace professional clinical advice.</li>
            <li>If you are experiencing a crisis, please contact local emergency services immediately.</li>
          </ul>
        </div>

        <button
          type="button"
          onClick={onClose}
          className="mt-5 w-full rounded-full bg-[#0E5F6B] py-2.5 text-sm font-semibold text-white transition hover:bg-[#0A4A55]"
        >
          Got it
        </button>
      </div>
    </div>
  );
}
