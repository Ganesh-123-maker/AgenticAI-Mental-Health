import { AlertCircle, BellRing, CheckCircle2, Info, X } from "lucide-react";

const toneConfig = {
  success: { icon: CheckCircle2, chip: "bg-emerald-100 text-emerald-800" },
  error: { icon: AlertCircle, chip: "bg-rose-100 text-rose-800" },
  info: { icon: Info, chip: "bg-sky-100 text-sky-800" },
};

/**
 * Dropdown panel fed by app feedback/session events.
 * Parent owns the notifications list; this only renders it.
 */
export function NotificationsPanel({ open, notifications, onClose }) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[60]">
      <button
        type="button"
        className="absolute inset-0 cursor-default bg-transparent"
        onClick={onClose}
        aria-label="Close notifications"
        tabIndex={-1}
      />
      <div className="absolute right-3 top-[68px] flex max-h-[70vh] w-80 max-w-[calc(100vw-1.5rem)] flex-col overflow-hidden rounded-3xl border border-[#F3E2CF] bg-[#FDF6EC] shadow-2xl sm:right-5">
        <div className="flex items-center justify-between border-b border-[#F3E2CF] px-4 py-3">
          <div className="flex items-center gap-2">
            <BellRing className="h-4 w-4 text-[#0E5F6B]" />
            <h2 className="text-sm font-bold text-[#123B43]">Notifications</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full p-1.5 text-[#8A7B66] transition hover:bg-[#F6E8D5]"
            aria-label="Close notifications"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-3">
          {notifications.length === 0 ? (
            <p className="px-2 py-6 text-center text-xs leading-5 text-[#8A7B66]">
              Nothing yet. Session events and updates will appear here.
            </p>
          ) : (
            <ul className="space-y-2">
              {notifications.map((item) => {
                const tone = toneConfig[item.type] || toneConfig.info;
                const Icon = tone.icon;
                return (
                  <li
                    key={item.id}
                    className="flex items-start gap-2.5 rounded-2xl border border-[#F3E2CF] bg-white/80 p-3"
                  >
                    <span className={`rounded-full p-1.5 ${tone.chip}`}>
                      <Icon className="h-3.5 w-3.5" />
                    </span>
                    <div className="min-w-0">
                      <p className="text-xs leading-5 text-[#33484D]">{item.message}</p>
                      <p className="mt-1 text-[10px] text-[#A08B6D]">
                        {new Date(item.timestamp).toLocaleString()}
                      </p>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
