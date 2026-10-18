import { useEffect, useRef, useState } from "react";
import { FeedbackBanner } from "./components/common/FeedbackBanner";
import { AppSidebar } from "./components/layout/AppSidebar";
import { InfoPanel } from "./components/layout/InfoPanel";
import { MobileBottomSheet } from "./components/layout/MobileBottomSheet";
import { TopBar } from "./components/layout/TopBar";
import { AuthModal } from "./components/modals/AuthModal";
import { CompleteCourseModal } from "./components/modals/CompleteCourseModal";
import { CreateCourseModal } from "./components/modals/CreateCourseModal";
import { HelpModal } from "./components/modals/HelpModal";
import { SchoolModal } from "./components/modals/SchoolModal";
import { NotificationsPanel } from "./components/panels/NotificationsPanel";
import { ProgressView } from "./components/views/ProgressView";
import { SessionsView } from "./components/views/SessionsView";
import { SettingsView } from "./components/views/SettingsView";
import { SkillsView } from "./components/views/SkillsView";
import { useBackendStatus } from "./hooks/useBackendStatus";
import { useMindCareApp } from "./hooks/useMindCareApp";

const MAX_NOTIFICATIONS = 20;

export default function App() {
  const app = useMindCareApp();
  const { online: backendOnline, lastChecked } = useBackendStatus(30000);

  const [view, setView] = useState("sessions");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [showHelpModal, setShowHelpModal] = useState(false);
  const [showNotifications, setShowNotifications] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [notifReadAt, setNotifReadAt] = useState(0);
  const lastFeedbackTs = useRef(0);

  // Feed the notifications panel from app feedback (session) events.
  useEffect(() => {
    const fb = app.feedback;
    if (fb?.message && fb.timestamp !== lastFeedbackTs.current) {
      lastFeedbackTs.current = fb.timestamp;
      setNotifications((prev) => {
        if (prev[0]?.message === fb.message) return prev;
        return [{ id: `${fb.timestamp}`, type: fb.type || "info", message: fb.message, timestamp: fb.timestamp }, ...prev].slice(
          0,
          MAX_NOTIFICATIONS
        );
      });
    }
  }, [app.feedback]);

  const unreadCount = notifications.filter((n) => n.timestamp > notifReadAt).length;

  function handleSelectView(nextView) {
    setView(nextView);
    setDrawerOpen(false);
  }

  function handleOpenNotifications() {
    setShowNotifications(true);
    setNotifReadAt(Date.now());
  }

  const sessionInfoPanel = <InfoPanel currentCourse={app.currentCourse} currentVisit={app.currentVisit} />;

  return (
    <div className="flex h-screen w-full flex-col bg-gradient-to-br from-[#FDF1E7] to-[#FBE9DB] font-sans text-[#33484D] selection:bg-[#FBE3C8]">
      <TopBar
        user={app.user}
        unreadCount={unreadCount}
        onToggleSidebar={() => setDrawerOpen((v) => !v)}
        onOpenNotifications={handleOpenNotifications}
        onOpenHelp={() => setShowHelpModal(true)}
        onOpenAuth={() => app.setShowAuthModal(true)}
      />

      <div className="flex min-h-0 flex-1">
        <AppSidebar
          view={view}
          onSelectView={handleSelectView}
          backendOnline={backendOnline}
          drawerOpen={drawerOpen}
          onCloseDrawer={() => setDrawerOpen(false)}
        />

        <div className="flex min-w-0 flex-1 flex-col">
          <FeedbackBanner feedback={app.feedback} onClose={app.clearFeedback} />

          <div className="flex min-h-0 flex-1 flex-col">
            {view === "sessions" ? <SessionsView app={app} /> : null}
            {view === "skills" ? <SkillsView schools={app.schools} /> : null}
            {view === "progress" ? (
              <ProgressView
                courses={app.courses}
                currentCourse={app.currentCourse}
                visits={app.visits}
                hasToken={Boolean(app.token)}
                onSelectCourse={(courseId) => {
                  app.selectCourse(courseId);
                  handleSelectView("sessions");
                }}
              />
            ) : null}
            {view === "settings" ? (
              <SettingsView
                user={app.user}
                backendOnline={backendOnline}
                lastChecked={lastChecked}
                onOpenAuth={() => app.setShowAuthModal(true)}
                onLogout={app.logout}
              />
            ) : null}
          </div>

          <footer className="shrink-0 px-4 pb-24 pt-1 text-center text-[11px] leading-5 text-[#A08B6D] lg:pb-3">
            Research prototype — not medical advice. In crisis, contact local emergency services.
          </footer>
        </div>
      </div>

      {view === "sessions" ? (
        <MobileBottomSheet
          token={app.token}
          selectedSchoolId={app.selectedSchoolId}
          currentCourse={app.currentCourse}
          currentVisit={app.currentVisit}
          canCreateCourse={app.canCreateCourse}
          canStartNextVisit={app.canStartNextVisit}
          canCompleteCourse={app.canCompleteCourse}
          onOpenCreateCourseModal={() => app.setShowCreateCourseModal(true)}
          onStartNextVisit={app.startNextVisit}
          onContinueVisit={app.continueCurrentVisit}
          onCloseVisit={app.closeCurrentVisit}
          onOpenCompleteCourseModal={() => app.setShowCompleteCourseModal(true)}
        >
          {sessionInfoPanel}
        </MobileBottomSheet>
      ) : null}

      <NotificationsPanel
        open={showNotifications}
        notifications={notifications}
        onClose={() => setShowNotifications(false)}
      />

      <HelpModal open={showHelpModal} onClose={() => setShowHelpModal(false)} />

      <AuthModal
        open={app.showAuthModal}
        user={app.user}
        authMode={app.authMode}
        authForm={app.authForm}
        onClose={() => app.setShowAuthModal(false)}
        onChangeMode={app.setAuthMode}
        onChangeForm={app.setAuthForm}
        onSubmit={app.handleAuth}
        onLogout={app.logout}
      />

      <SchoolModal
        open={app.showSchoolModal}
        token={app.token}
        schools={app.schools}
        selectedSchoolId={app.selectedSchoolId}
        currentSchool={app.currentSchool}
        onClose={() => app.setShowSchoolModal(false)}
        onSelectSchool={app.setSelectedSchoolId}
      />

      <CreateCourseModal
        open={app.showCreateCourseModal}
        currentSchool={app.currentSchool}
        onClose={() => app.setShowCreateCourseModal(false)}
        onSubmit={async (payload) => {
          const data = await app.createCourse(payload);
          if (data) {
            app.setShowCreateCourseModal(false);
            return true;
          }
          return false;
        }}
      />

      <CompleteCourseModal
        open={app.showCompleteCourseModal}
        currentCourse={app.currentCourse}
        onClose={() => app.setShowCompleteCourseModal(false)}
        onConfirm={app.completeCurrentCourse}
      />
    </div>
  );
}
