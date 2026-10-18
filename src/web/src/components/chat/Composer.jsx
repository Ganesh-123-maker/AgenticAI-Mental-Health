import { SendHorizonal } from "lucide-react";

/**
 * Rounded message composer. Enter sends, Shift+Enter inserts a newline.
 * Mirrors the old ChatInput guards: no visit / closed visit show guidance.
 */
export function Composer({ currentCourse, currentVisit, input, isTyping, onInputChange, onSend }) {
  const nextVisitNo = (currentCourse?.latest_visit_no || 0) + 1;

  if (!currentVisit) {
    if (!currentCourse) return null;
    return (
      <div className="shrink-0 px-4 pb-24 pt-2 text-center text-sm text-[#8A7B66] sm:px-6 lg:pb-6">
        The current therapy course has not started. Please click &ldquo;Start Session {nextVisitNo}&rdquo; above.
      </div>
    );
  }

  if (currentVisit.status !== "open") {
    return (
      <div className="shrink-0 px-4 pb-24 pt-2 text-center text-sm text-[#8A7B66] sm:px-6 lg:pb-6">
        The current session has concluded. You may begin the next session.
      </div>
    );
  }

  const canSend = input.trim().length > 0 && !isTyping;

  return (
    <div className="shrink-0 px-4 pb-24 pt-2 sm:px-6 lg:pb-5">
      <div className="mx-auto max-w-3xl">
        <div className="flex items-end gap-2.5 rounded-[28px] border border-[#EBD9C2] bg-white p-2 pl-5 shadow-[0_8px_30px_rgba(180,130,80,0.12)] transition focus-within:border-[#0E5F6B]/50 focus-within:shadow-[0_8px_30px_rgba(14,95,107,0.15)]">
          <textarea
            value={input}
            onChange={(event) => onInputChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                onSend();
              }
            }}
            placeholder="Share what's on your mind..."
            aria-label="Message input"
            rows={1}
            className="max-h-32 min-h-[44px] w-full resize-none bg-transparent py-2.5 text-[15px] text-[#33484D] placeholder:text-[#B39B7D] focus:outline-none"
          />
          <button
            type="button"
            onClick={onSend}
            disabled={!canSend}
            aria-label="Send message"
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[#0E5F6B] text-white shadow-md transition hover:bg-[#0A4A55] disabled:cursor-not-allowed disabled:opacity-40"
          >
            <SendHorizonal className="h-5 w-5" />
          </button>
        </div>
        <p className="mt-2.5 text-center text-[11px] leading-5 text-[#A08B6D]">
          AI responses are for research and educational reference only and do not replace professional medical
          advice. If you are experiencing a crisis, please contact local emergency services immediately.
        </p>
      </div>
    </div>
  );
}
