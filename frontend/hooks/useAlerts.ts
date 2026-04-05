/**
 * useAlerts — Price Alert Management Hook
 *
 * Interacts with:
 *   POST /alerts/subscribe  → setAlert
 *   GET  /alerts/user/{id}  → checkAlerts
 *   DELETE /alerts/{id}     → deleteAlert
 *
 * Persists alerts in localStorage so they survive page reloads.
 * Polls the backend every 30 s and fires browser notifications
 * for newly-triggered alerts.
 */

import {
  useState,
  useEffect,
  useCallback,
  useRef,
} from "react";
import {
  setAlert as apiSetAlert,
  checkAlerts as apiCheckAlerts,
  deleteAlert as apiDeleteAlert,
  ApiError,
} from "@/lib/api";
import type {
  AlertRecord,
  SetAlertRequest,
  SetAlertResponse,
  CheckAlertsResponse,
} from "@/types";

// ── Constants ────────────────────────────────────────────────────────
const POLL_INTERVAL_MS = 30_000;
const STORAGE_KEY = "skymind_price_alerts_v2";

// ── localStorage helpers ─────────────────────────────────────────────
function loadFromStorage(): AlertRecord[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as AlertRecord[]) : [];
  } catch {
    return [];
  }
}

function saveToStorage(alerts: AlertRecord[]): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(alerts));
  } catch {
    /* quota exceeded — silent fail */
  }
}

function upsertInStorage(alert: AlertRecord): void {
  const existing = loadFromStorage();
  const idx = existing.findIndex((a) => a.id === alert.id);
  if (idx >= 0) {
    existing[idx] = alert;
  } else {
    existing.push(alert);
  }
  saveToStorage(existing);
}

function removeFromStorage(id: string): void {
  saveToStorage(loadFromStorage().filter((a) => a.id !== id));
}

// Track which alert IDs we've already notified this session
const _notifiedIds = new Set<string>();

// ── Hook return type ─────────────────────────────────────────────────
export interface UseAlertsReturn {
  alerts: AlertRecord[];
  triggered: AlertRecord[];
  loading: boolean;
  error: string | null;
  addAlert: (req: SetAlertRequest) => Promise<{ ok: boolean; message: string }>;
  removeAlert: (id: string) => Promise<void>;
  lastChecked: Date | null;
}

// ── Hook ─────────────────────────────────────────────────────────────
export function useAlerts(userId?: string): UseAlertsReturn {
  const [alerts, setAlerts] = useState<AlertRecord[]>(() =>
    loadFromStorage()
  );
  const [triggered, setTriggered] = useState<AlertRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Poll backend ─────────────────────────────────────────────────
  const poll = useCallback(async () => {
    try {
      const data: CheckAlertsResponse = await apiCheckAlerts(userId);

      const merged = data.alerts;
      setAlerts(merged);
      setTriggered(data.triggered);
      setLastChecked(new Date());
      saveToStorage(merged);

      // Fire notifications for newly triggered alerts
      for (const alert of data.triggered) {
        if (!_notifiedIds.has(alert.id)) {
          _notifiedIds.add(alert.id);
          _fireBrowserNotification(alert);
        }
      }
    } catch {
      // Backend unreachable → fall back to localStorage data
      const stored = loadFromStorage();
      if (stored.length > 0) {
        setAlerts(stored);
        setTriggered(stored.filter((a) => a.triggered));
      }
    }
  }, [userId]);

  // ── Mount / interval ────────────────────────────────────────────
  useEffect(() => {
    // Hydrate from storage immediately (no flash)
    const stored = loadFromStorage();
    if (stored.length > 0) setAlerts(stored);

    poll();
    timerRef.current = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [poll]);

  // ── addAlert ─────────────────────────────────────────────────────
  const addAlert = useCallback(
    async (req: SetAlertRequest) => {
      setLoading(true);
      setError(null);
      try {
        const res: SetAlertResponse = await apiSetAlert(req);

        // Optimistic local record
        const localAlert: AlertRecord = {
          id: res.alert_id,
          origin: req.origin.toUpperCase(),
          destination: req.destination.toUpperCase(),
          target_price: req.target_price,
          departure_date: req.departure_date,
          user_label: req.user_label,
          created_at: new Date().toISOString(),
          triggered: false,
          current_price: undefined,
        };

        upsertInStorage(localAlert);
        setAlerts((prev) => {
          const without = prev.filter((a) => a.id !== res.alert_id);
          return [...without, localAlert];
        });

        // Refresh from backend
        await poll();
        return { ok: true, message: res.message };
      } catch (err) {
        const msg =
          err instanceof ApiError
            ? err.message
            : "Failed to set alert. Please try again.";
        setError(msg);
        return { ok: false, message: msg };
      } finally {
        setLoading(false);
      }
    },
    [poll]
  );

  // ── removeAlert ──────────────────────────────────────────────────
  const removeAlert = useCallback(async (id: string) => {
    // Optimistic removal
    setAlerts((prev) => prev.filter((a) => a.id !== id));
    removeFromStorage(id);
    _notifiedIds.delete(id);

    try {
      await apiDeleteAlert(id);
    } catch {
      // Local removal already applied; server error is non-fatal
    }
  }, []);

  return {
    alerts,
    triggered,
    loading,
    error,
    addAlert,
    removeAlert,
    lastChecked,
  };
}

// ── Browser Notification helper ──────────────────────────────────────
function _fireBrowserNotification(alert: AlertRecord): void {
  const title = `🎯 Price Alert: ${alert.origin} → ${alert.destination}`;
  const body = `Current price ₹${
    alert.current_price?.toLocaleString("en-IN") ?? "--"
  } hit your target of ₹${alert.target_price.toLocaleString("en-IN")}!`;

  if (typeof window === "undefined" || !("Notification" in window)) return;

  if (Notification.permission === "granted") {
    new Notification(title, { body, icon: "/favicon.ico" });
  } else if (Notification.permission !== "denied") {
    Notification.requestPermission().then((perm) => {
      if (perm === "granted") new Notification(title, { body });
    });
  }
}
