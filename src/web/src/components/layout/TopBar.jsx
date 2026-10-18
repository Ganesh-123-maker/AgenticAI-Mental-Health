import { Bell, CircleHelp, Menu, User } from "lucide-react";
import { LotusLogo } from "../common/LotusLogo";

export function TopBar({
  user,
  unreadCount,
  onToggleSidebar,
  onOpenNotifications,
  onOpenHelp,
  onOpenAuth,
}) {
  return (
    <header className="relative z-30 flex h-16 shrink-0 items-center justify-between border-b border-[#F3E2CF] bg-[#FDF6EC]/90 px-4 backdrop-blur sm:px-6">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onToggleSidebar}
          className="rounded-xl p-2 text-[#5B6B6B] transition hover:bg-[#F6E8D5] md:hidden"
          aria-label="Open navigation menu"
        >
          <Menu className="h-5 w-5" />
        </button>
        <div className="flex items-center gap-2.5">
          <span className="text-[#0E5F6B]">
            <LotusLogo className="h-8 w-8" />
          </span>
          <span className="text-xl font-bold tracking-tight text-[#123B43]">PsychAgent</span>
        </div>
      </div>

      <div className="flex items-center gap-1.5 sm:gap-2">
        <button
          type="button"
          onClick={onOpenNotifications}
          className="relative rounded-xl p-2.5 text-[#5B6B6B] transition hover:bg-[#F6E8D5] hover:text-[#123B43]"
          aria-label={`Notifications${unreadCount > 0 ? `, ${unreadCount} unread` : ""}`}
          title="Notifications"
        >
          <Bell className="h-5 w-5" />
          {unreadCount > 0 ? (
            <span className="absolute right-1.5 top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-[#E0654F] px-1 text-[10px] font-bold text-white">
              {unreadCount > 9 ? "9+" : unreadCount}
            </span>
          ) : null}
        </button>

        <button
          type="button"
          onClick={onOpenHelp}
          className="rounded-xl p-2.5 text-[#5B6B6B] transition hover:bg-[#F6E8D5] hover:text-[#123B43]"
          aria-label="Help and safety information"
          title="Help"
        >
          <CircleHelp className="h-5 w-5" />
        </button>

        <button
          type="button"
          onClick={onOpenAuth}
          className="relative ml-1 flex items-center gap-2 rounded-2xl border border-[#EBD9C2] bg-white/70 p-1.5 pr-2.5 transition hover:bg-white"
          aria-label={user ? `Account: ${user.username}` : "Sign in or register"}
          title={user ? `Signed in as ${user.username}` : "Sign in / Register"}
        >
          <span className="relative flex h-8 w-8 items-center justify-center rounded-full bg-[#0E5F6B]/10 text-[#0E5F6B]">
            <User className="h-4 w-4" />
            <span
              className={`absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-white ${
                user ? "bg-emerald-500" : "bg-slate-300"
              }`}
              aria-hidden="true"
            />
          </span>
          <span className="hidden max-w-28 truncate text-sm font-medium text-[#33484D] sm:block">
            {user ? user.username : "Sign in"}
          </span>
        </button>
      </div>
    </header>
  );
}
