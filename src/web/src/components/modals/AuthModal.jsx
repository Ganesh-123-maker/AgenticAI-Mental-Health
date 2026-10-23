import { useEffect } from "react";
import { User, X } from "lucide-react";

export function AuthModal({
  open,
  user,
  authMode,
  authForm,
  onClose,
  onChangeMode,
  onChangeForm,
  onSubmit,
  onLogout,
}) {
  useEffect(() => {
    if (!open) return undefined;
    function handleKey(event) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm">
      <div className="relative w-full max-w-md space-y-4 rounded-3xl border border-[#F3E2CF] bg-[#FDF6EC] p-6 shadow-2xl">
        <button
          type="button"
          className="absolute right-4 top-4 rounded-full p-1.5 text-[#8A7B66] transition hover:bg-[#F6E8D5]"
          onClick={onClose}
          aria-label="Close account dialog"
        >
          <X className="h-5 w-5" />
        </button>

        <div className="space-y-1 text-center">
          <h2 className="text-xl font-bold text-[#123B43]">Account</h2>
          <p className="text-sm text-[#6B7C7C]">
            {user ? `Signed in as: ${user.username}` : "Enter your username and password, or register a new account."}
          </p>
        </div>

        {!user && (
          <div className="space-y-3">
            <input
              className="w-full rounded-2xl border border-[#EBD9C2] bg-white px-4 py-2.5 text-sm text-[#33484D] placeholder:text-[#B39B7D] focus:border-[#0E5F6B]/60 focus:outline-none"
              placeholder="Username"
              value={authForm.username}
              onChange={(event) => onChangeForm({ ...authForm, username: event.target.value })}
              aria-label="Username"
            />

            <input
              className="w-full rounded-2xl border border-[#EBD9C2] bg-white px-4 py-2.5 text-sm text-[#33484D] placeholder:text-[#B39B7D] focus:border-[#0E5F6B]/60 focus:outline-none"
              placeholder="Password"
              type="password"
              value={authForm.password}
              onChange={(event) => onChangeForm({ ...authForm, password: event.target.value })}
              aria-label="Password"
            />

            <div className="flex items-center justify-between text-xs text-[#8A7B66]">
              <div>Mode: {authMode === "login" ? "Sign In" : "Register"}</div>
              <button
                type="button"
                className="font-semibold text-[#0E5F6B] hover:text-[#0A4A55]"
                onClick={() => onChangeMode(authMode === "login" ? "register" : "login")}
              >
                Switch to {authMode === "login" ? "Register" : "Sign In"}
              </button>
            </div>

            <button
              type="button"
              className="w-full rounded-full bg-[#0E5F6B] py-2.5 text-sm font-semibold text-white transition hover:bg-[#0A4A55]"
              onClick={() => onSubmit(authMode)}
            >
              {authMode === "login" ? "Sign In" : "Register"}
            </button>
          </div>
        )}

        {user && (
          <div className="space-y-3 text-sm text-[#5B6B6B]">
            <div className="flex items-center gap-2 rounded-2xl bg-white/70 px-4 py-3">
              <User className="h-4 w-4 text-[#0E5F6B]" />
              <span className="font-medium text-[#33484D]">{user.username}</span>
            </div>

            <button
              type="button"
              className="w-full rounded-full bg-[#33484D] py-2.5 text-sm font-semibold text-white transition hover:bg-[#22333a]"
              onClick={onLogout}
            >
              Sign Out
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
