import { useEffect, useState } from "react";
import { API_BASE } from "../config/api";

/**
 * Polls GET /health so the UI can show a real backend connection status.
 * online: true = reachable, false = unreachable, null = not checked yet.
 */
export function useBackendStatus(pollMs = 30000) {
  const [online, setOnline] = useState(null);
  const [lastChecked, setLastChecked] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function check() {
      try {
        const response = await fetch(`${API_BASE}/health`, { method: "GET" });
        if (!cancelled) {
          setOnline(response.ok);
          setLastChecked(Date.now());
        }
      } catch {
        if (!cancelled) {
          setOnline(false);
          setLastChecked(Date.now());
        }
      }
    }

    check();
    const timerId = setInterval(check, pollMs);
    return () => {
      cancelled = true;
      clearInterval(timerId);
    };
  }, [pollMs]);

  return { online, lastChecked };
}
