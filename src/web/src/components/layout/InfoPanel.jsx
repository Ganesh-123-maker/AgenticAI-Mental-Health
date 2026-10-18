import { Activity, Cpu, ShieldAlert, Sparkles, Target } from "lucide-react";
import { useEffect, useState } from "react";
import { catalogApi } from "../../services/mindcareApi";

const SESSION_FOCUS_DEFAULT = [
  "Establish initial rapport and counseling framework",
  "Gather background history and demographics",
  "Explore primary complaints and recent changes",
  "Clarify counseling motivation and expectations",
  "Conduct baseline psychosomatic and functional assessment",
  "Identify safety risks and available coping resources",
  "Summarize session and exchange collaborative feedback",
];

function buildSessionFocus(currentVisit) {
  const focus = [];
  const appendUnique = (rawValue) => {
    const text = String(rawValue ?? "").trim();
    if (!text || focus.includes(text)) return;
    focus.push(text);
  };
  (currentVisit?.psych_context?.session_focus || []).forEach(appendUnique);
  if (focus.length === 0) SESSION_FOCUS_DEFAULT.forEach(appendUnique);
  return focus.slice(0, 8);
}

function Card({ children, className = "" }) {
  return (
    <section className={`rounded-3xl border border-[#F3E2CF] bg-white/85 p-5 shadow-[0_6px_24px_rgba(180,130,80,0.08)] ${className}`}>
      {children}
    </section>
  );
}

function CardTitle({ icon: Icon, children }) {
  return (
    <div className="mb-3 flex items-center gap-2">
      <Icon className="h-4 w-4 text-[#0E5F6B]" />
      <h3 className="text-sm font-bold text-[#123B43]">{children}</h3>
    </div>
  );
}

/**
 * Right-hand panel: Session card + Today's skills (from GET /stages —
 * the closest backend data available; there is no per-skill endpoint),
 * counseling goals, agent trace, and the safety notice.
 */
export function InfoPanel({ currentCourse, currentVisit }) {
  const [stages, setStages] = useState([]);
  const stage = currentVisit?.stage || currentCourse?.current_stage;
  const sessionFocus = buildSessionFocus(currentVisit);
  const trace = currentVisit?.psych_context?.profile_payload?.latest_agent_trace;
  const route = currentVisit?.psych_context?.profile_payload?.latest_route;

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

  const activeStageKey = stage?.key || stage?.label;

  return (
    <div className="space-y-4">
      <Card>
        <h3 className="text-base font-bold text-[#123B43]">Session</h3>
        {currentCourse ? (
          <div className="mt-2.5">
            <span className="inline-block rounded-full bg-[#FBE3C8] px-3.5 py-1.5 text-xs font-bold text-[#5B3A1E]">
              {stage?.label || "Not Started"}
            </span>
            <p className="mt-2.5 text-xs leading-5 text-[#6B7C7C]">
              Currently in session {currentVisit?.visit_no || currentCourse?.latest_visit_no || 0}.
            </p>
          </div>
        ) : (
          <p className="mt-2 text-xs leading-5 text-[#6B7C7C]">Select a course to view its stage and progress.</p>
        )}
      </Card>

      <Card>
        <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-[#A08B6D]">Today&apos;s skills</p>
        <div className="mt-3 space-y-2.5">
          {stages.length === 0 ? (
            <p className="text-xs leading-5 text-[#6B7C7C]">
              {currentCourse ? "Loading stage skills…" : "Create a course to see stage skills."}
            </p>
          ) : (
            stages.slice(0, 4).map((stageItem) => {
              const isActive =
                activeStageKey &&
                (stageItem.key === activeStageKey || stageItem.label === activeStageKey);
              return (
                <div
                  key={stageItem.key || stageItem.label}
                  className={`rounded-2xl border p-3.5 ${
                    isActive ? "border-[#0E5F6B]/30 bg-[#0E5F6B]/[.04]" : "border-[#F3E2CF] bg-[#FDF6EC]/60"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-start gap-2.5">
                      <Sparkles className={`mt-0.5 h-4 w-4 shrink-0 ${isActive ? "text-[#0E5F6B]" : "text-[#B39B7D]"}`} />
                      <div>
                        <p className="text-sm font-bold text-[#123B43]">{stageItem.label}</p>
                        <p className="mt-0.5 line-clamp-2 text-[11px] leading-4 text-[#6B7C7C]">
                          {stageItem.desc || stageItem.range || ""}
                        </p>
                      </div>
                    </div>
                    <span
                      className={`shrink-0 rounded-full px-2.5 py-1 text-[10px] font-bold ${
                        isActive ? "bg-[#0E5F6B] text-white" : "bg-[#F3E2CF] text-[#8A7B66]"
                      }`}
                    >
                      {isActive ? "Active" : "Available"}
                    </span>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </Card>

      <Card>
        <CardTitle icon={Target}>Counseling Goals</CardTitle>
        {currentCourse ? (
          <ul className="space-y-2">
            {sessionFocus.map((focusItem, index) => (
              <li key={`${index}-${focusItem}`} className="flex items-start gap-2.5 text-xs leading-5 text-[#5B6B6B]">
                <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-[#0E5F6B]" />
                <span>{focusItem}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs leading-5 text-[#6B7C7C]">Create a course to view and maintain counseling goals.</p>
        )}
      </Card>

      {trace ? (
        <Card>
          <CardTitle icon={Cpu}>Agent Execution Trace</CardTitle>
          <div className="space-y-2">
            <div className="flex items-center justify-between rounded-xl bg-[#FDF6EC] p-2 text-[11px] font-medium text-[#5B6B6B]">
              <span>Pipeline Route:</span>
              <span
                className={`rounded-md px-1.5 py-0.5 font-mono font-semibold ${
                  route === "HIGH-RISK"
                    ? "bg-rose-100 text-rose-700"
                    : route === "UNCERTAIN"
                    ? "bg-amber-100 text-amber-700"
                    : "bg-emerald-100 text-emerald-700"
                }`}
              >
                {route || "CLEAR"}
              </span>
            </div>
            <div className="space-y-1">
              {trace.map((step, idx) => {
                const agentName = String(step.agent || "Agent")
                  .replace(/_/g, " ")
                  .replace(/\b\w/g, (l) => l.toUpperCase());
                const status = step.route || step.verdict || step.status || "ok";
                const isCrisis = status === "HIGH-RISK" || status === "ESCALATE" || status === "HIGH";
                const isUncertain = status === "UNCERTAIN" || status === "REVISE";
                return (
                  <div
                    key={idx}
                    className="flex items-center justify-between border-b border-[#F6E8D5] py-1 text-[11px] last:border-0"
                  >
                    <span className="max-w-[130px] truncate text-[#6B7C7C]" title={agentName}>
                      {agentName}
                    </span>
                    <span
                      className={`rounded px-1 font-mono ${
                        isCrisis
                          ? "bg-rose-50 font-semibold text-rose-600"
                          : isUncertain
                          ? "bg-amber-50 font-semibold text-amber-600"
                          : "bg-[#FDF6EC] text-[#8A7B66]"
                      }`}
                    >
                      {status}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </Card>
      ) : null}

      <Card>
        <CardTitle icon={ShieldAlert}>Support &amp; Safety Notice</CardTitle>
        <ul className="space-y-1.5 text-xs leading-5 text-[#6B7C7C]">
          <li>AI responses are for reference and do not replace professional clinical advice.</li>
          <li>If experiencing a psychological crisis, contact local emergency services immediately.</li>
          <li>Structured homework and between-session practice modules will appear here.</li>
        </ul>
      </Card>

      <Card>
        <CardTitle icon={Activity}>About This Stage</CardTitle>
        <p className="text-xs leading-5 text-[#6B7C7C]">
          {stage?.desc || stage?.label
            ? `${stage?.label || ""}${stage?.desc ? ` — ${stage.desc}` : ""}`
            : "Stage details will appear here once a session is active."}
        </p>
      </Card>
    </div>
  );
}
