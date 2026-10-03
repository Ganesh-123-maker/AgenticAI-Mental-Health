import { Activity, Cpu, ShieldAlert, Target } from "lucide-react";

const SESSION_FOCUS_DEFAULT = [
  "Establish initial rapport and counseling framework",
  "Gather background history and demographics",
  "Explore primary complaints and recent changes",
  "Clarify counseling motivation and expectations",
  "Conduct baseline psychosomatic and functional assessment",
  "Identify safety risks and available coping resources",
  "Summarize session and exchange collaborative feedback",
];

function Section({ title, icon: Icon, children }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-2 flex items-center gap-2 text-slate-800">
        <Icon className="h-4 w-4" />
        <h3 className="text-sm font-semibold">{title}</h3>
      </div>
      <div className="text-xs leading-6 text-slate-600">{children}</div>
    </section>
  );
}

function buildPromptSessionFocus(currentVisit) {
  const focus = [];
  const appendUnique = (rawValue) => {
    const text = String(rawValue ?? "").trim();
    if (!text || focus.includes(text)) return;
    focus.push(text);
  };

  (currentVisit?.psych_context?.session_focus || []).forEach(appendUnique);
  if (focus.length === 0) {
    SESSION_FOCUS_DEFAULT.forEach(appendUnique);
  }
  return focus.slice(0, 8);
}

export function RightPanel({ currentCourse, currentVisit, embedded = false }) {
  const stage = currentVisit?.stage || currentCourse?.current_stage;
  const sessionFocus = buildPromptSessionFocus(currentVisit);

  const wrapperClassName = embedded
    ? "space-y-4"
    : "hidden shrink-0 xl:block xl:w-64 2xl:w-72 border-l border-slate-200 bg-slate-50/70 p-4 overflow-y-auto";

  return (
    <aside className={wrapperClassName}>
      <Section title="Current Stage" icon={Activity}>
        {currentCourse ? (
          <div className="space-y-1">
            <p className="font-semibold text-slate-800">{stage?.label || "Not Started"}</p>
            <p>Currently in session {currentVisit?.visit_no || currentCourse?.latest_visit_no || 0}.</p>
          </div>
        ) : (
          <p>Select a course to view its stage and progress.</p>
        )}
      </Section>

      <Section title="Counseling Goals" icon={Target}>
        {currentCourse ? (
          sessionFocus.length > 0 ? (
            <ul className="space-y-1">
              {sessionFocus.map((focusItem, index) => (
                <li key={`${index}-${focusItem}`} className="flex items-start gap-2">
                  <span className="mt-2 h-1.5 w-1.5 rounded-full bg-teal-500" />
                  <span>{focusItem}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p>No goal information for current session.</p>
          )
        ) : (
          <p>Create a course to view and maintain counseling goals.</p>
        )}
      </Section>

      {currentVisit?.psych_context?.profile_payload?.latest_agent_trace && (
        <Section title="Agent Execution Trace" icon={Cpu}>
          <div className="space-y-2">
            <div className="flex items-center justify-between text-[11px] font-medium text-slate-700 bg-slate-100 p-1.5 rounded">
              <span>Pipeline Route:</span>
              <span className={`px-1.5 py-0.5 rounded font-mono font-semibold ${
                currentVisit.psych_context.profile_payload.latest_route === 'HIGH-RISK' 
                  ? 'bg-rose-100 text-rose-700' 
                  : currentVisit.psych_context.profile_payload.latest_route === 'UNCERTAIN'
                  ? 'bg-amber-100 text-amber-700'
                  : 'bg-emerald-100 text-emerald-700'
              }`}>
                {currentVisit.psych_context.profile_payload.latest_route || 'CLEAR'}
              </span>
            </div>
            <div className="space-y-1">
              {currentVisit.psych_context.profile_payload.latest_agent_trace.map((step, idx) => {
                const agentName = (step.agent || 'Agent').replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                const status = step.route || step.verdict || step.status || 'ok';
                const isCrisis = status === 'HIGH-RISK' || status === 'ESCALATE' || status === 'HIGH';
                const isUncertain = status === 'UNCERTAIN' || status === 'REVISE';
                return (
                  <div key={idx} className="flex items-center justify-between border-b border-slate-100 py-0.5 text-[10px]">
                    <span className="text-slate-600 truncate max-w-[120px]" title={agentName}>{agentName}</span>
                    <span className={`font-mono px-1 rounded ${
                      isCrisis ? 'bg-rose-50 text-rose-600 font-semibold' : isUncertain ? 'bg-amber-50 text-amber-600 font-semibold' : 'bg-slate-50 text-slate-500'
                    }`}>
                      {status}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </Section>
      )}

      <Section title="Support & Safety Notice" icon={ShieldAlert}>
        <ul className="space-y-1">
          <li>AI responses are for reference and do not replace professional clinical advice.</li>
          <li>If experiencing a psychological crisis, contact local emergency services immediately.</li>
          <li>Structured homework and between-session practice modules will appear here.</li>
        </ul>
      </Section>
    </aside>
  );
}
