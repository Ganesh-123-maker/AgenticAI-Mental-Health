import { ArrowDown, ArrowUp, Pause, Play, RotateCcw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { LotusLogo } from "../common/LotusLogo";

const PHASES = [
  { label: "Inhale", seconds: 4, instruction: "Breathe in slowly through your nose", Icon: ArrowUp },
  { label: "Hold", seconds: 4, instruction: "Hold your breath gently", Icon: Pause },
  { label: "Exhale", seconds: 4, instruction: "Breathe out slowly through your mouth", Icon: ArrowDown },
  { label: "Hold", seconds: 4, instruction: "Rest and stay present", Icon: Pause },
];

const TOTAL_ROUNDS = 4;
const RING_CIRCUMFERENCE = 2 * Math.PI * 44;

const PHASE_SECONDS = PHASES[0].seconds;
const ROUND_SECONDS = PHASES.length * PHASE_SECONDS;
const TOTAL_SECONDS = ROUND_SECONDS * TOTAL_ROUNDS;

function PhaseTimer() {
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0); // total seconds elapsed
  const intervalRef = useRef(null);

  const done = elapsed >= TOTAL_SECONDS;
  const round = Math.min(TOTAL_ROUNDS, Math.floor(elapsed / ROUND_SECONDS) + 1);
  const phaseIdx = Math.min(PHASES.length - 1, Math.floor((elapsed % ROUND_SECONDS) / PHASE_SECONDS));
  const secsLeft = PHASE_SECONDS - (elapsed % PHASE_SECONDS);
  const progress = (elapsed % PHASE_SECONDS) / PHASE_SECONDS;

  useEffect(() => {
    if (!running || done) return;
    intervalRef.current = setInterval(() => {
      setElapsed((prev) => {
        const next = prev + 1;
        if (next >= TOTAL_SECONDS) {
          setRunning(false);
          return TOTAL_SECONDS;
        }
        return next;
      });
    }, 1000);
    return () => clearInterval(intervalRef.current);
  }, [running, done]);

  useEffect(() => () => clearInterval(intervalRef.current), []);

  function reset() {
    clearInterval(intervalRef.current);
    setRunning(false);
    setElapsed(0);
  }

  const phase = PHASES[phaseIdx];
  const PhaseIcon = phase.Icon;

  return (
    <div className="mt-4 rounded-2xl border border-[#EBD9C2] bg-[#FDF6EC] p-4">
      <div className="flex items-center gap-4">
        <div className="relative h-24 w-24 shrink-0">
          <svg viewBox="0 0 100 100" className="h-24 w-24 -rotate-90">
            <circle cx="50" cy="50" r="44" fill="none" stroke="#F0DFC8" strokeWidth="8" />
            <circle
              cx="50"
              cy="50"
              r="44"
              fill="none"
              stroke="#0E5F6B"
              strokeWidth="8"
              strokeLinecap="round"
              strokeDasharray={RING_CIRCUMFERENCE}
              strokeDashoffset={RING_CIRCUMFERENCE * (1 - progress)}
              className="transition-all duration-1000 ease-linear"
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <PhaseIcon className="h-5 w-5 text-[#0E5F6B]" />
            <span className="text-xl font-bold text-[#123B43]">{secsLeft}s</span>
          </div>
        </div>

        <div className="min-w-0 flex-1">
          {done ? (
            <p className="text-sm font-semibold text-[#123B43]">
              Well done — you completed {TOTAL_ROUNDS} rounds. Notice how your body feels now.
            </p>
          ) : (
            <>
              <p className="text-sm font-bold text-[#123B43]">
                {phase.label}
                <span className="ml-2 text-xs font-medium text-[#8A7B66]">
                  Round {round} of {TOTAL_ROUNDS}
                </span>
              </p>
              <p className="mt-0.5 text-xs text-[#6B7C7C]">{phase.instruction}</p>
              <div className="mt-2 flex gap-1.5" aria-hidden="true">
                {Array.from({ length: TOTAL_ROUNDS }).map((_, i) => (
                  <span
                    key={i}
                    className={`h-1.5 flex-1 rounded-full ${i < round ? "bg-[#0E5F6B]" : "bg-[#EBD9C2]"}`}
                  />
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      <div className="mt-3 flex gap-2">
        {!done ? (
          <button
            type="button"
            onClick={() => setRunning((r) => !r)}
            className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-full bg-[#0E5F6B] px-4 py-2 text-xs font-semibold text-white transition hover:bg-[#0A4A55]"
            aria-label={running ? "Pause breathing timer" : "Start breathing timer"}
          >
            {running ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
            {running ? "Pause" : elapsed === 0 ? "Start guided breathing" : "Resume"}
          </button>
        ) : null}
        <button
          type="button"
          onClick={reset}
          className="inline-flex items-center justify-center gap-1.5 rounded-full border border-[#EBD9C2] bg-white px-4 py-2 text-xs font-semibold text-[#5B6B6B] transition hover:bg-[#FDF1E7]"
          aria-label="Reset breathing timer"
        >
          <RotateCcw className="h-3.5 w-3.5" />
          Reset
        </button>
      </div>
    </div>
  );
}

const STEP_TILES = [
  { title: "Step 1. Inhale", meta: "4s", instruction: "Breathe in slowly through your nose", Icon: ArrowUp },
  { title: "Hold 2", meta: "4s", instruction: "Hold your breath gently", Icon: Pause },
  { title: "Step 3. Exhale", meta: "", instruction: "Breathe out slowly through your mouth", Icon: ArrowDown },
  { title: "Hold 4", meta: "4s", instruction: "Rest and stay present", Icon: Pause },
];

/**
 * Rendered inside an assistant message when the response suggests a
 * breathing exercise. Includes a working guided 4s-phase timer.
 */
export function ExerciseCard() {
  return (
    <div className="mt-3 rounded-3xl border border-[#EBD9C2] bg-white/90 p-4 shadow-sm sm:p-5">
      <div className="flex items-start gap-3">
        <span className="rounded-2xl bg-[#0E5F6B]/10 p-2 text-[#0E5F6B]">
          <LotusLogo className="h-6 w-6" />
        </span>
        <div>
          <h4 className="text-[15px] font-bold text-[#123B43]">
            Let&apos;s try a box-breathing exercise to help calm your mind
          </h4>
          <p className="mt-1 text-sm leading-6 text-[#5B6B6B]">
            This can help slow your breathing and bring focus.
          </p>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        {STEP_TILES.map((step) => {
          const Icon = step.Icon;
          return (
            <div
              key={step.title}
              className="rounded-2xl border border-[#F3E2CF] bg-[#FDF6EC] p-3 text-center"
            >
              <Icon className="mx-auto h-4 w-4 text-[#0E5F6B]" />
              <p className="mt-1.5 text-xs font-bold text-[#123B43]">
                {step.title}
                {step.meta ? <span className="text-[#0E5F6B]"> {step.meta}</span> : null}
              </p>
              <p className="mt-1 text-[11px] leading-4 text-[#6B7C7C]">{step.instruction}</p>
            </div>
          );
        })}
      </div>

      <p className="mt-3 text-xs leading-5 text-[#8A7B66]">
        Repeat 3–4 rounds. Go at your own pace — I&apos;m here with you.
      </p>

      <PhaseTimer />
    </div>
  );
}

/** True when an assistant response suggests a breathing exercise. */
export function mentionsBreathingExercise(text) {
  return /(box[\s-]?breathing|breathing exercise)/i.test(String(text ?? ""));
}

/**
 * True when a user message asks to RECALL a previously taught breathing
 * exercise ("Can you remind me what breathing exercise you taught me?")
 * rather than asking to be taught one now. A recall question is not
 * itself evidence that an exercise was taught.
 */
export function isBreathingRecallQuestion(text) {
  const lower = String(text ?? "").toLowerCase();
  if (!/(breath|exercise)/i.test(lower)) return false;
  return /remind me|recall|remember|did you teach|have you taught|what .* (taught|teach|showed|gave|recommended)|which .* (taught|teach)/i.test(lower);
}

/**
 * True when a user message asks to be TAUGHT a breathing exercise (as
 * opposed to recalling one already taught). A teaching request is evidence
 * the exercise was introduced in that turn: the assistant's reply to it
 * is the teaching turn. A user saying the exercise helped is the same
 * evidence — they can only say that about an exercise already taught.
 */
export function requestsBreathingExerciseTeaching(text) {
  const lower = String(text ?? "").toLowerCase();
  if (!mentionsBreathingExercise(lower)) return false;
  if (isBreathingRecallQuestion(lower)) return false;
  if (/\b(helped|helps)\b/.test(lower)) return true;
  return /\b(teach|show|guide|try|practice|learn)\b|walk me through|let'?s (do|try)|do a|start a|give me/.test(lower);
}

/**
 * True when an exercise was actually taught earlier in this conversation.
 *
 * An earlier assistant message counts as a teaching turn when it mentions
 * a breathing exercise and the user message immediately before it was NOT
 * a recall question (a recall echo quotes the question's own wording, so
 * it must not bootstrap itself into "taught"). An assistant message with
 * no preceding user message (e.g. an opening that introduces the exercise
 * unprompted) also counts — the assistant introduced it.
 *
 * A user teaching request in an earlier turn counts too. This is what
 * makes the check work across visits: the thread only renders the current
 * visit's messages, but the visit state ships prior visits' USER turns
 * (`prior_visit_user_messages`, REG-1), so a teaching request from an
 * earlier session is visible even though its assistant reply is not.
 */
export function wasBreathingExerciseTaught(messages, upToIndex) {
  const list = Array.isArray(messages) ? messages : [];
  for (let j = 0; j < upToIndex && j < list.length; j += 1) {
    const msg = list[j];
    if (!msg) continue;
    if (msg.role === "user" && requestsBreathingExerciseTeaching(msg.text)) return true;
    if (msg.role !== "assistant") continue;
    if (!mentionsBreathingExercise(msg.text)) continue;
    let prevUser = null;
    for (let k = j - 1; k >= 0; k -= 1) {
      if (list[k] && list[k].role === "user") {
        prevUser = list[k];
        break;
      }
      if (list[k] && list[k].role === "assistant") break;
    }
    if (!prevUser || !isBreathingRecallQuestion(prevUser.text)) return true;
  }
  return false;
}

/**
 * Whether the exercise card should render under the assistant message at
 * `index` in `messages`.
 *
 * Round 3 fix (B-D4): the card used to fire on keyword match of the
 * current message alone, so a fresh user asking "remind me what breathing
 * exercise you taught me?" saw the box-breathing card even though nothing
 * was ever taught — the dummy echo quotes the question, which itself
 * contains "breathing exercise". Now the card shows only when this turn
 * teaches the exercise (the preceding user message is not a recall
 * question) or an earlier turn taught it.
 */
export function shouldShowExerciseCard(messages, index) {
  const list = Array.isArray(messages) ? messages : [];
  const msg = list[index];
  if (!msg || msg.role !== "assistant" || !mentionsBreathingExercise(msg.text)) return false;
  let prevUser = null;
  for (let k = index - 1; k >= 0; k -= 1) {
    if (list[k] && list[k].role === "user") {
      prevUser = list[k];
      break;
    }
    if (list[k] && list[k].role === "assistant") break;
  }
  if (prevUser && isBreathingRecallQuestion(prevUser.text)) {
    return wasBreathingExerciseTaught(list, index);
  }
  return true;
}
