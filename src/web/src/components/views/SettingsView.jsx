import { LogOut, PlugZap, Server, User } from "lucide-react";
import { API_BASE } from "../../config/api";

/**
 * Settings: account (existing auth flow), backend connection status,
 * and API base display. All data from existing endpoints/config only.
 */
export function SettingsView({ user, backendOnline, lastChecked, onOpenAuth, onLogout }) {
  const statusLabel = backendOnline === null ? "Checking…" : backendOnline ? "Connected" : "Reconnecting…";
  const statusClass =
    backendOnline === null
      ? "bg-amber-100 text-amber-800"
      : backendOnline
      ? "bg-emerald-100 text-emerald-800"
      : "bg-rose-100 text-rose-800";

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-8">
      <div className="mx-auto max-w-2xl space-y-4">
        <h2 className="text-xl font-bold text-[#123B43]">Settings</h2>

        <section className="rounded-3xl border border-[#F3E2CF] bg-white/85 p-5 shadow-sm">
          <div className="flex items-center gap-2">
            <User className="h-4 w-4 text-[#0E5F6B]" />
            <h3 className="text-sm font-bold text-[#123B43]">Account</h3>
          </div>
          {user ? (
            <div className="mt-3 space-y-3">
              <p className="text-sm text-[#5B6B6B]">
                Signed in as <span className="font-bold text-[#123B43]">{user.username}</span>
              </p>
              <button
                type="button"
                onClick={onLogout}
                className="inline-flex items-center gap-1.5 rounded-full bg-[#33484D] px-4 py-2 text-xs font-semibold text-white transition hover:bg-[#22333a]"
              >
                <LogOut className="h-3.5 w-3.5" />
                Sign Out
              </button>
            </div>
          ) : (
            <div className="mt-3 space-y-3">
              <p className="text-sm text-[#5B6B6B]">You are not signed in.</p>
              <button
                type="button"
                onClick={onOpenAuth}
                className="inline-flex items-center gap-1.5 rounded-full bg-[#0E5F6B] px-4 py-2 text-xs font-semibold text-white transition hover:bg-[#0A4A55]"
              >
                <User className="h-3.5 w-3.5" />
                Sign In / Register
              </button>
            </div>
          )}
        </section>

        <section className="rounded-3xl border border-[#F3E2CF] bg-white/85 p-5 shadow-sm">
          <div className="flex items-center gap-2">
            <PlugZap className="h-4 w-4 text-[#0E5F6B]" />
            <h3 className="text-sm font-bold text-[#123B43]">Connection</h3>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className={`rounded-full px-3 py-1 text-xs font-bold ${statusClass}`}>{statusLabel}</span>
            {lastChecked ? (
              <span className="text-[11px] text-[#A08B6D]">
                Last checked {new Date(lastChecked).toLocaleTimeString()}
              </span>
            ) : null}
          </div>
          <p className="mt-2 text-xs leading-5 text-[#6B7C7C]">
            The status above reflects a live <span className="font-mono">GET /health</span> check against the
            backend, refreshed automatically.
          </p>
        </section>

        <section className="rounded-3xl border border-[#F3E2CF] bg-white/85 p-5 shadow-sm">
          <div className="flex items-center gap-2">
            <Server className="h-4 w-4 text-[#0E5F6B]" />
            <h3 className="text-sm font-bold text-[#123B43]">API</h3>
          </div>
          <p className="mt-3 text-xs text-[#6B7C7C]">Backend base URL</p>
          <p className="mt-1 rounded-2xl bg-[#FDF6EC] px-3 py-2 font-mono text-xs text-[#33484D]">{API_BASE}</p>
        </section>

        <p className="pt-2 text-center text-[11px] leading-5 text-[#A08B6D]">
          Research prototype — not medical advice. In crisis, contact local emergency services.
        </p>
      </div>
    </div>
  );
}
