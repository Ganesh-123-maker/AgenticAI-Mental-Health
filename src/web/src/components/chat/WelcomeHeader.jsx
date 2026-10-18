import { MoonStar, Sparkles, Sun } from "lucide-react";
import { timeOfDayGreeting } from "../common/formatTime";

const QUICK_PROMPTS = [
  { text: "I'm feeling anxious", icon: Sparkles },
  { text: "Trouble sleeping", icon: MoonStar },
  { text: "Talk through my day", icon: Sun },
];

/**
 * Time-of-day greeting + quick-prompt chips shown at the top of the chat.
 * Chips send the prompt as a message when a session is open.
 */
export function WelcomeHeader({ canSend, onQuickPrompt }) {
  return (
    <div className="mx-auto w-full max-w-3xl px-4 pt-8 sm:px-6 sm:pt-10">
      <h1 className="text-center text-2xl font-bold tracking-tight text-[#123B43] sm:text-[28px]">
        {timeOfDayGreeting()}
      </h1>
      <p className="mx-auto mt-2 max-w-xl text-center text-sm leading-6 text-[#6B7C7C]">
        How are you feeling today? Start with one of the prompts below, or just share what&apos;s on your mind.
      </p>
      <div className="mt-5 flex flex-wrap items-center justify-center gap-2.5">
        {QUICK_PROMPTS.map((prompt) => {
          const Icon = prompt.icon;
          return (
            <button
              key={prompt.text}
              type="button"
              onClick={() => onQuickPrompt(prompt.text)}
              disabled={!canSend}
              title={canSend ? `Send: ${prompt.text}` : "Start a session to begin chatting"}
              className="inline-flex items-center gap-2 rounded-full border border-[#EBD9C2] bg-white/80 px-4 py-2.5 text-sm font-medium text-[#33484D] shadow-sm transition hover:-translate-y-0.5 hover:bg-white hover:shadow disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0"
            >
              <Icon className="h-4 w-4 text-[#0E5F6B]" />
              {prompt.text}
            </button>
          );
        })}
      </div>
    </div>
  );
}
