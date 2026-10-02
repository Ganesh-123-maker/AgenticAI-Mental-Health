import { Brain, FolderOpen, LogIn, MessageSquare, User } from "lucide-react";
import { EmptyState } from "../common/EmptyState";

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
        description="Select a modality from the sidebar and create a course. The initial session will be established automatically."
      />
    );
  }

  return (
    <EmptyState
      icon={MessageSquare}
      title="No Sessions in Current Course"
      description='Click "Start Session N" to start and view the session conversation history.'
    />
  );
}

export function ChatMessages({ currentCourse, currentVisit, currentSchool, isTyping, chatEndRef, hasToken }) {
  const shouldShowEmpty = !currentVisit;

  return (
    <div className="flex-1 space-y-6 overflow-y-auto bg-slate-50/40 p-4 pb-28 sm:p-6 sm:pb-8">
      {shouldShowEmpty ? (
        <div className="mx-auto mt-6 max-w-2xl">
          <ChatEmptyState hasToken={hasToken} currentCourse={currentCourse} />
        </div>
      ) : null}

	      {currentVisit?.messages?.map((message) => (
        <div
          key={message.id}
          className={`flex w-full ${message.role === "user" ? "justify-end" : "justify-start"}`}
        >
          {message.role === "system" ? (
            <div className="my-4 flex w-full justify-center">
              <span className="rounded-full border border-slate-200 bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
                {message.text}
              </span>
            </div>
          ) : (
            <div
              className={`flex max-w-[85%] gap-3 md:max-w-[72%] ${
                message.role === "user" ? "flex-row-reverse" : "flex-row"
              }`}
            >
              <div
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full shadow-sm md:h-10 md:w-10 ${
                  message.role === "user"
                    ? "bg-slate-200 text-slate-600"
                    : `${currentSchool?.color || "bg-teal-500"} text-white`
                }`}
              >
                {message.role === "user" ? <User className="h-5 w-5" /> : <Brain className="h-5 w-5" />}
              </div>

              <div
                className={`whitespace-pre-wrap rounded-2xl p-3 text-sm leading-relaxed shadow-sm md:p-4 md:text-base ${
                  message.role === "user"
                    ? "rounded-tr-none bg-slate-800 text-white"
                    : "rounded-tl-none border border-slate-100 bg-white text-slate-700"
                }`}
              >
	                {message.role === "assistant" ? extractResponseText(message.text) : message.text}
              </div>
            </div>
          )}
        </div>
      ))}

      {isTyping ? (
        <div className="flex w-full justify-start">
          <div className="flex max-w-[80%] gap-3">
            <div
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-white opacity-70 ${
                currentSchool?.color || "bg-teal-500"
              }`}
            >
              <Brain className="h-5 w-5" />
            </div>
            <div className="flex h-12 items-center gap-1 rounded-2xl rounded-tl-none border border-slate-100 bg-white p-4 shadow-sm">
              <div className="h-2 w-2 animate-bounce rounded-full bg-slate-400" />
              <div className="h-2 w-2 animate-bounce rounded-full bg-slate-400 delay-75" />
              <div className="h-2 w-2 animate-bounce rounded-full bg-slate-400 delay-150" />
            </div>
          </div>
        </div>
      ) : null}

      <div ref={chatEndRef} />
    </div>
  );
}
