import { useEffect, useState } from "react";
import { API_BASE } from "../config/api";

/**
 * Polls GET /health so the UI can show a real backend connection status.
 * online: true = reachable, false = unreachable, null = not checked yet.
 */
export function useBackendStatus(pollMs = 10000) {
  const [online, setOnline] = useState(null);
  const [lastChecked, setLastChecked] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function check() {
      // Bound each probe: a hung (not refused) backend must flip the
      // indicator to offline instead of stalling the poll indefinitely.
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 3000);
      try {
        const response = await fetch(`${API_BASE}/health`, {
          method: "GET",
          signal: controller.signal,
        });
        if (!cancelled) {
          setOnline(response.ok);
          setLastChecked(Date.now());
        }
      } catch {
        if (!cancelled) {
          setOnline(false);
          setLastChecked(Date.now());
        }
      } finally {
        clearTimeout(timeoutId);
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
