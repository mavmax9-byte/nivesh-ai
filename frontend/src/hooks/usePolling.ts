"use client";

import { useEffect, useRef, useState } from "react";

interface PollingState<T> {
  data: T | null;
  error: unknown;
  loading: boolean;
  attempts: number;
  elapsedMs: number;
}

interface PollingOptions<T> {
  intervalMs?: number;
  enabled?: boolean;
  /** Stop polling once this returns true for the latest result. */
  stopWhen?: (data: T) => boolean;
}

/**
 * Repeatedly calls `fetcher` every `intervalMs` while `enabled`, until
 * `stopWhen` returns true. Used for the company hub's committee-generation
 * progress view -- there is no push/webhook channel from the backend, so
 * polling `GET /reports/{symbol}` (and each specialist's own GET) is the
 * only way to know a Celery-queued run has finished.
 */
export function usePolling<T>(
  fetcher: () => Promise<T>,
  { intervalMs = 4000, enabled = true, stopWhen }: PollingOptions<T> = {},
): PollingState<T> {
  const [state, setState] = useState<PollingState<T>>({
    data: null,
    error: null,
    loading: enabled,
    attempts: 0,
    elapsedMs: 0,
  });
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const stopWhenRef = useRef(stopWhen);
  stopWhenRef.current = stopWhen;

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout> | undefined;
    const startedAt = Date.now();

    async function tick() {
      try {
        const data = await fetcherRef.current();
        if (cancelled) return;
        setState((s) => ({
          data,
          error: null,
          loading: false,
          attempts: s.attempts + 1,
          elapsedMs: Date.now() - startedAt,
        }));
        const done = stopWhenRef.current ? stopWhenRef.current(data) : false;
        if (!done) timeoutId = setTimeout(tick, intervalMs);
      } catch (error) {
        if (cancelled) return;
        setState((s) => ({
          ...s,
          error,
          loading: false,
          attempts: s.attempts + 1,
          elapsedMs: Date.now() - startedAt,
        }));
        timeoutId = setTimeout(tick, intervalMs);
      }
    }

    tick();
    return () => {
      cancelled = true;
      if (timeoutId) clearTimeout(timeoutId);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, intervalMs]);

  return state;
}
