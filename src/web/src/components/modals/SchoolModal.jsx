import { X } from "lucide-react";
import { getSchoolDisplayName } from "../common/schoolText";

export function SchoolModal({
  open,
  token,
  schools,
  selectedSchoolId,
  currentSchool,
  onClose,
  onSelectSchool,
}) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm">
      <div className="relative w-full max-w-md space-y-4 rounded-3xl border border-[#F3E2CF] bg-[#FDF6EC] p-6 shadow-2xl">
        <button
          type="button"
          className="absolute right-4 top-4 rounded-full p-1.5 text-[#8A7B66] transition hover:bg-[#F6E8D5]"
          onClick={onClose}
          aria-label="Close modality picker"
        >
          <X className="h-5 w-5" />
        </button>

        <div>
          <h3 className="text-lg font-bold text-[#123B43]">Select Counseling Modality</h3>
          <p className="mt-1 text-sm text-[#6B7C7C]">
            Selecting a modality updates the course list. Current: {getSchoolDisplayName(currentSchool)}
          </p>
        </div>

        <div className="space-y-2">
          {schools.map((school) => {
            const selected = school.id === selectedSchoolId;
            return (
              <button
                key={school.id}
                type="button"
                disabled={!token}
                onClick={() => {
                  onSelectSchool(school.id);
                  onClose();
                }}
                className={`w-full rounded-2xl border p-3.5 text-left transition disabled:cursor-not-allowed disabled:opacity-60 ${
                  selected
                    ? "border-[#0E5F6B]/50 bg-[#0E5F6B]/[.06]"
                    : "border-[#EBD9C2] bg-white/70 hover:bg-white"
                }`}
              >
                <p className="text-sm font-bold text-[#123B43]">{getSchoolDisplayName(school)}</p>
                {school.desc ? (
                  <p className="mt-1 text-xs leading-5 text-[#6B7C7C]">{school.desc}</p>
                ) : null}
              </button>
            );
          })}
        </div>

        {!token ? <p className="text-xs text-amber-700">Please sign in before switching modalities.</p> : null}

        <button
          type="button"
          className="w-full rounded-full bg-[#F6E8D5] py-2.5 text-sm font-semibold text-[#5B3A1E] transition hover:bg-[#F3DDC2]"
          onClick={onClose}
        >
          Close
        </button>
      </div>
    </div>
  );
}
