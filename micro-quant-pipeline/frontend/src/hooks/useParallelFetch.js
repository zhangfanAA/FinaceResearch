import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * useParallelFetch -- Execute multiple fetch functions in parallel.
 *
 * Accepts an array of fetch functions and runs them all with Promise.allSettled.
 * Handles partial failures gracefully: each item is independent.
 *
 * @param {Function[]} fetchFns - Array of zero-arg async functions to execute
 * @param {Object} [options]
 * @param {boolean} [options.immediate=true] - Fetch on mount
 * @returns {{ data: any[], errors: (Error|null)[], loading: boolean, refetchAll: Function }}
 */
export default function useParallelFetch(fetchFns, { immediate = true } = {}) {
  const [data, setData] = useState(() => fetchFns.map(() => null));
  const [errors, setErrors] = useState(() => fetchFns.map(() => null));
  const [loading, setLoading] = useState(false);
  const mountedRef = useRef(true);

  const execute = useCallback(async () => {
    setLoading(true);
    const results = await Promise.allSettled(fetchFns.map((fn) => fn()));
    if (!mountedRef.current) return;

    const nextData = [];
    const nextErrors = [];
    results.forEach((result, i) => {
      if (result.status === 'fulfilled') {
        nextData[i] = result.value;
        nextErrors[i] = null;
      } else {
        nextData[i] = null;
        nextErrors[i] = result.reason instanceof Error ? result.reason : new Error(String(result.reason));
      }
    });
    setData(nextData);
    setErrors(nextErrors);
    setLoading(false);
  }, [fetchFns]);

  useEffect(() => {
    mountedRef.current = true;
    if (immediate) execute();
    return () => { mountedRef.current = false; };
  }, [execute, immediate]);

  return { data, errors, loading, refetchAll: execute };
}
