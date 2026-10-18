import { Layers, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { catalogApi } from "../../services/mindcareApi";
import { getSchoolDisplayName } from "../common/schoolText";

/**
 * Stage catalog from GET /stages, plus modality descriptions from
 * GET /schools. There is no dedicated per-skill endpoint, so stages are
 * the closest backend-provided skill structure.
 */
export function SkillsView({ schools }) {
  const [stages, setStages] = useState(null);

  useEffect(() => {
    let cancelled = false;
    catalogApi
      .listStages()
      .then((data) => {
        if (!cancelled) setStages(Array.isArray(data) ? data : []);
      })
      .catch(() => {
        if (!cancelled) setStages([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-8">
      <div className="mx-auto max-w-4xl">
        <h2 className="text-xl font-bold text-[#123B43]">Counseling Stages &amp; Skills</h2>
        <p className="mt-1 text-sm leading-6 text-[#6B7C7C]">
          Each counseling modality moves through structured stages. The stage catalog below comes from the
          backend — pick a stage to see what it covers.
        </p>

        <h3 className="mt-6 text-sm font-bold uppercase tracking-[0.12em] text-[#A08B6D]">Modalities</h3>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {schools.map((school) => (
            <div key={school.id} className="rounded-3xl border border-[#F3E2CF] bg-white/85 p-4 shadow-sm">
              <p className="text-sm font-bold text-[#123B43]">{getSchoolDisplayName(school)}</p>
              {school.desc ? (
                <p className="mt-1 text-xs leading-5 text-[#6B7C7C]">{school.desc}</p>
              ) : null}
              {school.style ? (
                <p className="mt-1 text-[11px] text-[#A08B6D]">{school.style}</p>
              ) : null}
            </div>
          ))}
          {schools.length === 0 ? (
            <p className="text-sm text-[#8A7B66]">Loading modalities…</p>
          ) : null}
        </div>

        <h3 className="mt-8 text-sm font-bold uppercase tracking-[0.12em] text-[#A08B6D]">Stages</h3>
        {stages === null ? (
          <div className="mt-4 flex items-center gap-2 text-sm text-[#8A7B66]">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading stages…
          </div>
        ) : stages.length === 0 ? (
          <p className="mt-4 text-sm text-[#8A7B66]">No stage data available from the backend.</p>
        ) : (
          <div className="mt-3 space-y-3">
            {stages.map((stage) => (
              <div
                key={stage.key || stage.label}
                className="rounded-3xl border border-[#F3E2CF] bg-white/85 p-5 shadow-sm"
              >
                <div className="flex items-center gap-3">
                  <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#0E5F6B]/10 text-[#0E5F6B]">
                    <Layers className="h-5 w-5" />
                  </span>
                  <div>
                    <p className="text-[15px] font-bold text-[#123B43]">{stage.label}</p>
                    {stage.range ? (
                      <p className="text-[11px] font-medium text-[#A08B6D]">{stage.range}</p>
                    ) : null}
                  </div>
                </div>
                {stage.desc ? (
                  <p className="mt-3 text-sm leading-6 text-[#5B6B6B]">{stage.desc}</p>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
