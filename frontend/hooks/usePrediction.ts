/**
 * SkyMind — Price Prediction Hook (2026 Production)
 */

import { useState, useCallback, useRef } from "react";
import { predictPrice, ApiError } from "@/lib/api";
import type { PredictionResult, PredictRequest } from "@/types";

// ─── Module-level response cache (kept but not used for now) ─
const _cache = new Map<string, PredictionResult>();

export interface UsePredictionReturn {
  result: PredictionResult | null;
  loading: boolean;
  error: string | null;
  /**
   * HTTP status behind `error`, or null when the request never got a response.
   *
   * The hook used to flatten `ApiError` to `err.message` and drop this, which left
   * the page unable to tell "the server declined, by design" from "something
   * broke". A 503 from `/predict` is the fail-closed path — no model has cleared
   * the acceptance gate — and it rendered under a red "Inference Session Error"
   * heading beside a Retry button that could not ever succeed.
   */
  errorStatus: number | null;
  predict: (req: PredictRequest) => void;
  reset: () => void;
}

export function usePrediction(): UsePredictionReturn {
  const [result, setResult] = useState<PredictionResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeReqRef = useRef<string | null>(null);

  const predict = useCallback((req: PredictRequest) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);

    const org = req.origin.trim().toUpperCase();
    const dst = req.destination.trim().toUpperCase();
    const date = req.departure_date?.trim() ?? "";

    if (!org || !dst) {
      setError("Please enter both origin and destination.");
      setErrorStatus(null);
      return;
    }
    if (org === dst) {
      setError("Origin and destination cannot be the same.");
      setErrorStatus(null);
      return;
    }

    const cacheKey = `${org}-${dst}-${date}`;

    debounceRef.current = setTimeout(async () => {
      const reqId = `${cacheKey}:${Date.now()}`;
      activeReqRef.current = reqId;

      setLoading(true);
      setResult(null);
      setError(null);
      setErrorStatus(null);

      try {
        const data = await predictPrice({
          ...req,
          origin: org,
          destination: dst,
        });

        if (activeReqRef.current !== reqId) return;

        // _cache.set(cacheKey, data); // optional (disabled)

        setResult(data);
        setError(null);
        setErrorStatus(null);
      } catch (err) {
        if (activeReqRef.current !== reqId) return;

        const msg =
          err instanceof ApiError
            ? err.message
            : "Intelligence Engine is offline. Please try again.";

        setError(msg);
        setErrorStatus(err instanceof ApiError ? err.statusCode ?? null : null);
        setResult(null);
      } finally {
        if (activeReqRef.current === reqId) {
          setLoading(false);
        }
      }
    }, 300);
  }, []);

  const reset = useCallback(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    activeReqRef.current = null;
    setResult(null);
    setError(null);
    setErrorStatus(null);
    setLoading(false);
  }, []);

  return { result, loading, error, errorStatus, predict, reset };
}