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
      <div className="relative w-full max-w-md space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl">
        <button type="button" className="absolute right-3 top-3 text-slate-400 hover:text-slate-600" onClick={onClose}>
          <X className="h-5 w-5" />
        </button>

        <div>
          <h3 className="text-lg font-bold text-slate-800">Select Counseling Modality</h3>
          <p className="mt-1 text-sm text-slate-600">
            Selecting a modality updates the course list. Current: {getSchoolDisplayName(currentSchool)}
          </p>
        </div>

        <select
          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
          value={selectedSchoolId}
          onChange={(event) => onSelectSchool(event.target.value)}
          disabled={!token}
        >
          <option value="" disabled>
            Select a modality...
          </option>
          {schools.map((school) => (
            <option key={school.id} value={school.id}>
              {getSchoolDisplayName(school)}
            </option>
          ))}
        </select>

        {!token ? <p className="text-xs text-amber-600">Please sign in before switching modalities.</p> : null}

        <button
          type="button"
          className="w-full rounded-lg bg-slate-100 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-200"
          onClick={onClose}
        >
          Close
        </button>
      </div>
    </div>
  );
}
