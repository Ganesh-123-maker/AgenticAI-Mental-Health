import { FolderOpen, LogIn, MessagesSquare } from "lucide-react";
import { EmptyState } from "../common/EmptyState";
import { formatMessageTime } from "../common/formatTime";
import { LotusLogo } from "../common/LotusLogo";
import { ExerciseCard, shouldShowExerciseCard } from "./ExerciseCard";
import { WelcomeHeader } from "./WelcomeHeader";

function extractResponseText(rawText) {
  const text = String(rawText ?? "");
  const match = text.match(/<response>([\s\S]*?)<\/response>/i);
  if (match && typeof match[1] === "string") {
    return match[1].trim();
  }
  return text;
}

function ChatEmptyState({ hasToken, currentCourse }) {
  if (!hasToken) {
    return (
      <EmptyState
        icon={LogIn}
        title="Sign in to Begin Counseling"
        description="Please sign in to select a counseling modality and create your therapy course."
      />
    );
  }

  if (!currentCourse) {
    return (
      <EmptyState
        icon={FolderOpen}
        title="Select or Create a Course"
        description="Select a modality from the chips above and create a course. The initial session will be established automatically."
      />
    );
  }

  return (
    <EmptyState
      icon={MessagesSquare}
      title="No Sessions in Current Course"
      description='Click "Start Session" above to start and view the session conversation history.'
    />
  );
}

function MessageBubble({ message, messages, index }) {
  const isUser = message.role === "user";
  const text = isUser ? message.text : extractResponseText(message.text);
  const timestamp = formatMessageTime(message.created_at);
  // Round 3 fix (B-D4): the card is history-gated, not keyword-gated —
  // a recall echo quoting the user's own question must not trigger it.
  const showExercise = !isUser && shouldShowExerciseCard(messages, index);

  if (message.role === "system") {
    return (
      <div className="my-4 flex w-full justify-center">
        <span className="rounded-full border border-[#EBD9C2] bg-white/70 px-3 py-1 text-xs font-medium text-[#8A7B66]">
          {message.text}
        </span>
      </div>
    );
  }

  return (
    <div className={`flex w-full ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`flex w-full max-w-[88%] gap-2.5 sm:max-w-[80%] ${isUser ? "flex-row-reverse" : "flex-row"}`}>
        {!isUser ? (
          <span className="mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#0E5F6B] text-white">
            <LotusLogo className="h-3.5 w-3.5" />
          </span>
        ) : null}
        <div className="min-w-0">
          <div
            className={`whitespace-pre-wrap rounded-3xl px-4 py-3 text-[15px] leading-relaxed shadow-sm ${
              isUser
                ? "rounded-br-lg bg-[#F6C89F] text-[#4A2E14]"
                : "rounded-bl-lg border border-[#F3E2CF] bg-white text-[#33484D]"
            }`}
          >
            {text}
          </div>
          {timestamp ? (
            <p className={`mt-1 px-1 text-[11px] text-[#A08B6D] ${isUser ? "text-right" : "text-left"}`}>
              {timestamp}
            </p>
          ) : null}
          {showExercise ? <ExerciseCard /> : null}
        </div>
      </div>
    </div>
  );
}

export function ChatThread({ currentCourse, currentVisit, canSend, isTyping, chatEndRef, hasToken, onQuickPrompt }) {
  const messages = currentVisit?.messages || [];
  // Round 3 fix (B-D4): the card check must see cross-visit history.
  // The thread renders only the current visit's messages, but the visit
  // state ships prior visits' USER turns (prior_visit_user_messages,
  // REG-1). A teaching request from an earlier session is evidence the
  // exercise was taught, even though that session's assistant reply is
  // not in this thread. The combined list is used ONLY for the card
  // decision; rendering still shows the current visit alone.
  const priorUserMessages = currentVisit?.prior_visit_user_messages || [];
  const historyMessages = [...priorUserMessages, ...messages];

  return (
    <div className="flex-1 overflow-y-auto px-4 pb-6 sm:px-6" aria-live="polite" aria-label="Conversation">
      <WelcomeHeader canSend={canSend} onQuickPrompt={onQuickPrompt} />

      <div className="mx-auto mt-6 w-full max-w-3xl space-y-5">
        {messages.length === 0 ? (
          <ChatEmptyState hasToken={hasToken} currentCourse={currentCourse} />
        ) : (
          messages.map((message, index) => (
            <MessageBubble
              key={message.id}
              message={message}
              messages={historyMessages}
              index={priorUserMessages.length + index}
            />
          ))
        )}

        {isTyping ? (
          <div className="flex w-full justify-start">
            <div className="flex items-center gap-2.5">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[#0E5F6B] text-white">
                <LotusLogo className="h-3.5 w-3.5" />
              </span>
              <div className="flex items-center gap-1.5 rounded-3xl rounded-bl-lg border border-[#F3E2CF] bg-white px-4 py-3 shadow-sm">
                <span className="h-2 w-2 animate-bounce rounded-full bg-[#0E5F6B]/50" />
                <span className="h-2 w-2 animate-bounce rounded-full bg-[#0E5F6B]/50 delay-75" />
                <span className="h-2 w-2 animate-bounce rounded-full bg-[#0E5F6B]/50 delay-150" />
              </div>
            </div>
          </div>
        ) : null}

        <div ref={chatEndRef} />
      </div>
    </div>
  );
}
