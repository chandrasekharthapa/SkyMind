/**
 * useAlerts — Price Alert Management Hook (2026)
 *
 * Interacts with:
 *   POST /alerts/subscribe  → addAlert
 *   GET  /alerts/user/{id}  → poll
 *   DELETE /alerts/{id}     → removeAlert
 *
 * Uses localStorage for offline persistence.
 * Polls backend every 30s.
 *
 * FIX: useState initializer no longer calls loadFromStorage() directly,
 * which caused SSR crashes. Storage is hydrated in a useEffect instead.
 */

import { useState, useEffect, useCallback, useRef } from "react";
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

const POLL_INTERVAL_MS = 30_000;
const STORAGE_KEY = "skymind_price_alerts_v3";

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
    /* quota exceeded — fail silently */
  }
}

function upsertInStorage(alert: AlertRecord): void {
  const existing = loadFromStorage();
  const idx = existing.findIndex((a) => a.id === alert.id);
  if (idx >= 0) existing[idx] = alert;
  else existing.push(alert);
  saveToStorage(existing);
}

function removeFromStorage(id: string): void {
  saveToStorage(loadFromStorage().filter((a) => a.id !== id));
}

const _notifiedIds = new Set<string>();

export interface UseAlertsReturn {
  alerts: AlertRecord[];
  triggered: AlertRecord[];
  loading: boolean;
  error: string | null;
  addAlert: (req: SetAlertRequest) => Promise<{ ok: boolean; message: string }>;
  removeAlert: (id: string) => Promise<void>;
  lastChecked: Date | null;
}

export function useAlerts(userId?: string): UseAlertsReturn {
  // FIX: start with empty array — hydrate from localStorage in useEffect
  // to avoid SSR crash (window is not defined on the server).
  const [alerts, setAlerts] = useState<AlertRecord[]>([]);
  const [triggered, setTriggered] = useState<AlertRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Hydrate from localStorage after mount (client-only)
  useEffect(() => {
    const stored = loadFromStorage();
    if (stored.length > 0) {
      setAlerts(stored);
      setTriggered(stored.filter((a) => a.triggered));
    }
  }, []);

  const poll = useCallback(async () => {
    try {
      const data: CheckAlertsResponse = await apiCheckAlerts(userId);
      setAlerts(data.alerts);
      setTriggered(data.triggered);
      setLastChecked(new Date());
      saveToStorage(data.alerts);

      for (const alert of data.triggered) {
        if (!_notifiedIds.has(alert.id)) {
          _notifiedIds.add(alert.id);
          _fireBrowserNotification(alert);
        }
      }
    } catch {
      // Fall back to whatever is in localStorage
      const stored = loadFromStorage();
      if (stored.length > 0) {
        setAlerts(stored);
        setTriggered(stored.filter((a) => a.triggered));
      }
    }
  }, [userId]);

  useEffect(() => {
    poll();
    timerRef.current = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [poll]);

  const addAlert = useCallback(
    async (req: SetAlertRequest) => {
      setLoading(true);
      setError(null);
      try {
        const res: SetAlertResponse = await apiSetAlert(req);
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
        await poll();
        return { ok: true, message: res.message };
      } catch (err) {
        const msg =
          err instanceof ApiError ? err.message : "Failed to set alert.";
        setError(msg);
        return { ok: false, message: msg };
      } finally {
        setLoading(false);
      }
    },
    [poll]
  );

  const removeAlert = useCallback(async (id: string) => {
    setAlerts((prev) => prev.filter((a) => a.id !== id));
    removeFromStorage(id);
    _notifiedIds.delete(id);
    try {
      await apiDeleteAlert(id);
    } catch {
      // local removal already applied — ignore network error
    }
  }, []);

  return { alerts, triggered, loading, error, addAlert, removeAlert, lastChecked };
}

function _fireBrowserNotification(alert: AlertRecord): void {
  const title = `🎯 Price Alert: ${alert.origin} → ${alert.destination}`;
  const body = `Price ₹${
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