import { BarChart3, MessagesSquare, Settings, Sparkles, X } from "lucide-react";
import { LotusLogo } from "../common/LotusLogo";

const NAV_ITEMS = [
  { key: "sessions", label: "Sessions", icon: MessagesSquare },
  { key: "skills", label: "Skills", icon: Sparkles },
  { key: "progress", label: "Progress", icon: BarChart3 },
  { key: "settings", label: "Settings", icon: Settings },
];

function ConnectionStatus({ online }) {
  const label = online === null ? "Checking…" : online ? "Connected" : "Reconnecting…";
  const dotClass = online === null ? "bg-amber-300" : online ? "bg-emerald-400" : "bg-rose-400";
  return (
    <div
      className="flex items-center gap-2.5 rounded-2xl bg-white/5 px-4 py-3"
      role="status"
      aria-label={`Backend status: ${label}`}
      title={label}
    >
      <span className="relative flex h-2.5 w-2.5">
        {online === false ? (
          <span className={`absolute inline-flex h-full w-full animate-ping rounded-full ${dotClass} opacity-60`} />
        ) : null}
        <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${dotClass}`} />
      </span>
      <span className="text-sm font-medium text-teal-50/90">{label}</span>
    </div>
  );
}

export function AppSidebar({ view, onSelectView, backendOnline, drawerOpen, onCloseDrawer }) {
  const sidebarBody = (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between px-5 pb-2 pt-6">
        <div className="flex items-center gap-2.5">
          <span className="text-teal-100">
            <LotusLogo className="h-9 w-9" />
          </span>
          <span className="text-lg font-bold tracking-tight text-white">PsychAgent</span>
        </div>
        <button
          type="button"
          onClick={onCloseDrawer}
          className="rounded-lg p-1.5 text-teal-100/70 transition hover:bg-white/10 hover:text-white md:hidden"
          aria-label="Close navigation menu"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      <nav className="flex-1 space-y-1.5 overflow-y-auto px-4 py-6" aria-label="Primary">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const active = view === item.key;
          return (
            <button
              key={item.key}
              type="button"
              onClick={() => onSelectView(item.key)}
              aria-current={active ? "page" : undefined}
              className={`flex w-full items-center gap-3 rounded-2xl px-4 py-3 text-[15px] font-medium transition ${
                active
                  ? "bg-[#FBE3C8] text-[#5B3A1E] shadow-sm"
                  : "text-teal-50/80 hover:bg-white/10 hover:text-white"
              }`}
            >
              <Icon className="h-5 w-5 shrink-0" />
              {item.label}
            </button>
          );
        })}
      </nav>

      <div className="px-4 pb-6">
        <ConnectionStatus online={backendOnline} />
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop: rounded dark panel */}
      <div className="m-3 mr-0 hidden w-60 shrink-0 md:block lg:w-64">
        <aside className="h-full overflow-hidden rounded-3xl bg-[#03353F] shadow-lg">{sidebarBody}</aside>
      </div>

      {/* Mobile: drawer */}
      <div
        className={`fixed inset-0 z-50 md:hidden ${drawerOpen ? "" : "pointer-events-none"}`}
        aria-hidden={!drawerOpen}
      >
        <div
          className={`absolute inset-0 bg-slate-900/50 transition-opacity ${drawerOpen ? "opacity-100" : "opacity-0"}`}
          onClick={onCloseDrawer}
        />
        <aside
          className={`absolute inset-y-0 left-0 w-72 max-w-[85vw] bg-[#03353F] shadow-2xl transition-transform duration-300 ${
            drawerOpen ? "translate-x-0" : "-translate-x-full"
          }`}
        >
          {sidebarBody}
        </aside>
      </div>
    </>
  );
}
