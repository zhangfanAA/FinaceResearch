import { useCallback, useEffect, useRef } from 'react';

/**
 * usePrefetch -- Prefetch data on hover or during idle time.
 *
 * @param {Object} options
 * @param {Function} options.onPrefetch - Async function to call for prefetching
 * @param {number} [options.delay=200] - Hover delay in ms before triggering
 * @returns {{ onMouseEnter: Function, onMouseLeave: Function, prefetchNow: Function }}
 */
export function useHoverPrefetch({ onPrefetch, delay = 200 }) {
  const timerRef = useRef(null);
  const prefetchedRef = useRef(false);

  const onMouseEnter = useCallback(() => {
    if (prefetchedRef.current) return;
    timerRef.current = setTimeout(() => {
      prefetchedRef.current = true;
      onPrefetch();
    }, delay);
  }, [onPrefetch, delay]);

  const onMouseLeave = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const prefetchNow = useCallback(() => {
    if (!prefetchedRef.current) {
      prefetchedRef.current = true;
      onPrefetch();
    }
  }, [onPrefetch]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  return { onMouseEnter, onMouseLeave, prefetchNow };
}

/**
 * useIdlePrefetch -- Prefetch data during browser idle time.
 *
 * Uses requestIdleCallback when available, falls back to setTimeout.
 *
 * @param {Function} onPrefetch - Async function to call for prefetching
 * @param {boolean} [enabled=true] - Whether to enable idle prefetching
 */
export function useIdlePrefetch(onPrefetch, enabled = true) {
  const callbackRef = useRef(onPrefetch);

  useEffect(() => {
    callbackRef.current = onPrefetch;
  }, [onPrefetch]);

  useEffect(() => {
    if (!enabled) return;

    let cancelled = false;
    const run = () => {
      if (!cancelled) callbackRef.current();
    };

    if (typeof requestIdleCallback === 'function') {
      const handle = requestIdleCallback(run, { timeout: 2000 });
      return () => {
        cancelled = true;
        cancelIdleCallback(handle);
      };
    }

    const timer = setTimeout(run, 1000);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [enabled]);
}
