/**
 * usePrediction — Price Prediction Hook
 *
 * Calls POST /predict and surfaces the full PredictionResult.
 * Handles debounce (300 ms), in-memory cache, loading/error state,
 * and stale-request guards so only the latest call wins.
 */

import { useState, useCallback, useRef } from "react";
import {
  predictPrice,
  ApiError,
} from "@/lib/api";
import type { PredictionResult, PredictRequest } from "@/types";

// ── In-memory cache keyed by "ORG-DST" ──────────────────────────────
const _cache = new Map<string, PredictionResult>();

interface UsePredictionReturn {
  result: PredictionResult | null;
  loading: boolean;
  error: string | null;
  predict: (req: PredictRequest) => void;
  reset: () => void;
}

export function usePrediction(): UsePredictionReturn {
  const [result, setResult] = useState<PredictionResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Refs for debounce & stale-response guard
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeReqRef = useRef<string | null>(null);

  const predict = useCallback((req: PredictRequest) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);

    const org = req.origin.trim().toUpperCase();
    const dst = req.destination.trim().toUpperCase();

    if (!org || !dst) {
      setError("Please enter both origin and destination.");
      return;
    }
    if (org === dst) {
      setError("Origin and destination cannot be the same.");
      return;
    }

    // ── Cache hit ────────────────────────────────────────────────────
    const cacheKey = `${org}-${dst}`;
    const cached = _cache.get(cacheKey);
    if (cached) {
      setResult(cached);
      setError(null);
      return;
    }

    // ── Debounced fetch ──────────────────────────────────────────────
    debounceRef.current = setTimeout(async () => {
      const reqId = `${cacheKey}:${Date.now()}`;
      activeReqRef.current = reqId;

      setLoading(true);
      setError(null);
      setResult(null);

      try {
        const data = await predictPrice({
          ...req,
          origin: org,
          destination: dst,
        });

        // Stale-response guard
        if (activeReqRef.current !== reqId) return;

        _cache.set(cacheKey, data);
        setResult(data);
      } catch (err) {
        if (activeReqRef.current !== reqId) return;

        const msg =
          err instanceof ApiError
            ? err.message
            : "Prediction failed. Please try again.";
        setError(msg);
      } finally {
        if (activeReqRef.current === reqId) {
          setLoading(false);
        }
      }
    }, 300);
  }, []);

  const reset = useCallback(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    setResult(null);
    setError(null);
    setLoading(false);
  }, []);

  return { result, loading, error, predict, reset };
}
