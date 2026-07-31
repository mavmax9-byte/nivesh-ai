"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError } from "@/lib/api-client";

interface AsyncState<T> {
  data: T | null;
  error: unknown;
  loading: boolean;
  /** convenience: error is a 404 ApiError -- usually means "not generated
   * yet" rather than a real failure, so callers can render an empty state
   * instead of an error banner. */
  notFound: boolean;
}

/**
 * Fetches `fn()` on mount and whenever `deps` changes. Client-side only
 * (no SSR data fetching in this app -- every screen here shows live,
 * frequently-changing backend state, so there is no meaningful page to
 * pre-render statically).
 */
export function useAsync<T>(
  fn: () => Promise<T>,
  deps: React.DependencyList,
): AsyncState<T> & { refetch: () => void } {
  const [state, setState] = useState<AsyncState<T>>({
    data: null,
    error: null,
    loading: true,
    notFound: false,
  });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null, notFound: false }));

    fn()
      .then((data) => {
        if (!cancelled) setState({ data, error: null, loading: false, notFound: false });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        const notFound = error instanceof ApiError && error.status === 404;
        setState({ data: null, error, loading: false, notFound });
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const refetch = useCallback(() => setTick((t) => t + 1), []);

  return { ...state, refetch };
}
