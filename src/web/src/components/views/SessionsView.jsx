import { ChatThread } from "../chat/ChatThread";
import { Composer } from "../chat/Composer";
import { SessionStrip } from "../chat/SessionStrip";
import { InfoPanel } from "../layout/InfoPanel";

/**
 * Default workspace view: session strip (timeline + actions),
 * chat thread, composer, and the info panel on wide screens.
 */
export function SessionsView({ app }) {
  const canSend = Boolean(app.currentVisit && app.currentVisit.status === "open" && !app.isTyping);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <SessionStrip
        currentSchool={app.currentSchool}
        schools={app.schools}
        selectedSchoolId={app.selectedSchoolId}
        courses={app.courses}
        currentCourse={app.currentCourse}
        visits={app.visits}
        currentVisit={app.currentVisit}
        canCreateCourse={app.canCreateCourse}
        canStartNextVisit={app.canStartNextVisit}
        canCompleteCourse={app.canCompleteCourse}
        token={app.token}
        onSelectSchool={() => app.setShowSchoolModal(true)}
        onSelectCourse={app.selectCourse}
        onSelectVisit={app.selectVisit}
        onOpenCreateCourseModal={() => app.setShowCreateCourseModal(true)}
        onStartNextVisit={app.startNextVisit}
        onContinueVisit={app.continueCurrentVisit}
        onCloseVisit={app.closeCurrentVisit}
        onOpenCompleteCourseModal={() => app.setShowCompleteCourseModal(true)}
      />

      <div className="flex min-h-0 flex-1">
        <main className="flex min-w-0 flex-1 flex-col">
          <ChatThread
            currentCourse={app.currentCourse}
            currentVisit={app.currentVisit}
            canSend={canSend}
            isTyping={app.isTyping}
            chatEndRef={app.chatEndRef}
            hasToken={Boolean(app.token)}
            onQuickPrompt={app.sendTextMessage}
          />
          <Composer
            currentCourse={app.currentCourse}
            currentVisit={app.currentVisit}
            input={app.input}
            isTyping={app.isTyping}
            onInputChange={app.setInput}
            onSend={app.sendMessage}
          />
        </main>

        <aside className="hidden w-72 shrink-0 overflow-y-auto border-l border-[#F3E2CF] bg-[#FDF6EC]/50 p-4 xl:block 2xl:w-80" aria-label="Session information">
          <InfoPanel currentCourse={app.currentCourse} currentVisit={app.currentVisit} />
        </aside>
      </div>
    </div>
  );
}
