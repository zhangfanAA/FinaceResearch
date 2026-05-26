/**
 * @fileoverview Stale Data Hook - 带过期数据保留的自动刷新 Hook
 * @module hooks/useStaleData
 * @description 组合了数据状态 + 新鲜度追踪 + 错误恢复的可复用 Hook
 * - 刷新失败时保留上次成功获取的数据
 * - 只在成功获取数据时更新时间戳
 * - 首次加载失败显示"暂无数据"
 * - 支持分时刷新避免多个面板同时请求
 * - 组件 remount 时不会重复请求，继续使用现有数据和倒计时
 */

import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * useStaleData - 带过期数据保留的自动刷新 Hook
 *
 * @param {Function} fetchFn - 数据获取函数，返回 Promise<T>
 * @param {Object} options - 配置选项
 * @param {number} [options.intervalMs=60000] - 刷新间隔（毫秒）
 * @param {boolean} [options.enabled=true] - 是否启用自动刷新
 * @param {boolean} [options.paused=false] - 外部暂停信号
 * @param {number} [options.staggerMs=0] - 分时延迟（毫秒）
 * @param {number} [options.freshThreshold=60] - "新鲜"状态阈值（秒）
 * @param {number} [options.staleThreshold=300] - "过期"状态阈值（秒）
 * @returns {Object} 数据状态和控制对象
 */
export default function useStaleData(fetchFn, options = {}) {
  const {
    intervalMs = 60000,
    enabled = true,
    paused = false,
    staggerMs = 0,
    freshThreshold = 60,
    staleThreshold = 300,
  } = options;

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true); // 仅首次加载为 true
  const [refreshing, setRefreshing] = useState(false); // 非首次刷新时为 true
  const [error, setError] = useState(null);
  const [lastSuccessfulFetch, setLastSuccessfulFetch] = useState(null);
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(enabled);
  const [secondsUntilRefresh, setSecondsUntilRefresh] = useState(Math.floor(intervalMs / 1000));
  const [serverStale, setServerStale] = useState(false); // 服务端返回的 stale 标记
  const [cachedAt, setCachedAt] = useState(null); // 服务端缓存时间

  const intervalRef = useRef(null);
  const countdownRef = useRef(null);
  const staggerRef = useRef(null);
  const fetchFnRef = useRef(fetchFn);
  const isFirstLoadRef = useRef(true);
  const mountedRef = useRef(false);

  // 保持回调引用最新
  useEffect(() => {
    fetchFnRef.current = fetchFn;
  }, [fetchFn]);

  /**
   * 执行数据获取 - 使用 ref 保持稳定引用
   * @param {boolean} isManualRefresh - 是否为手动刷新
   */
  const executeFetchRef = useRef(async (isManualRefresh = false) => {
    const isFirst = isFirstLoadRef.current;

    if (isFirst) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }

    try {
      const result = await fetchFnRef.current();
      setData(result);
      setError(null);
      setLastSuccessfulFetch(Date.now());
      isFirstLoadRef.current = false;

      // Detect server-side stale flag from API response
      if (result && typeof result === 'object') {
        // Object responses (sector-history, index-history, etc.)
        if ('stale' in result) {
          setServerStale(Boolean(result.stale));
          setCachedAt(result.cached_at || null);
        } else {
          setServerStale(false);
          setCachedAt(null);
        }
      } else if (Array.isArray(result) && result.length > 0 && typeof result[0] === 'object') {
        // Array responses (stock-realtime, fund-nav, sectors)
        const firstItem = result[0];
        if ('stale' in firstItem) {
          setServerStale(Boolean(firstItem.stale));
          setCachedAt(null);
        } else {
          setServerStale(false);
          setCachedAt(null);
        }
      } else {
        setServerStale(false);
        setCachedAt(null);
      }
    } catch (err) {
      // 刷新失败时保留现有数据，只更新错误状态
      setError(err.message || '数据获取失败');
      // 不更新 lastSuccessfulFetch
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  });

  /**
   * 手动刷新 - 稳定引用，不会因 fetchFn 变化而重建
   */
  const refresh = useCallback(() => {
    executeFetchRef.current(true);
  }, []);

  /**
   * 切换自动刷新
   */
  const toggleAutoRefresh = useCallback(() => {
    setAutoRefreshEnabled((prev) => !prev);
  }, []);

  /**
   * 手动标记已刷新
   */
  const markRefreshed = useCallback(() => {
    setLastSuccessfulFetch(Date.now());
    setSecondsUntilRefresh(Math.floor(intervalMs / 1000));
  }, [intervalMs]);

  // 初始加载 - 仅在 mount 时执行一次
  useEffect(() => {
    if (!mountedRef.current) {
      mountedRef.current = true;
      executeFetchRef.current();
    }
  }, []);

  // 自动刷新定时器 - 不依赖 executeFetch，通过 ref 调用
  useEffect(() => {
    // 清除现有定时器
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    if (countdownRef.current) {
      clearInterval(countdownRef.current);
      countdownRef.current = null;
    }
    if (staggerRef.current) {
      clearTimeout(staggerRef.current);
      staggerRef.current = null;
    }

    // 如果禁用或暂停，不启动定时器
    if (!autoRefreshEnabled || paused) {
      return () => {
        if (intervalRef.current) clearInterval(intervalRef.current);
        if (countdownRef.current) clearInterval(countdownRef.current);
        if (staggerRef.current) clearTimeout(staggerRef.current);
      };
    }

    // 重置倒计时
    setSecondsUntilRefresh(Math.floor(intervalMs / 1000));

    // 分时刷新：使用 setTimeout 延迟第一次刷新，然后切换到 setInterval
    const startInterval = () => {
      intervalRef.current = setInterval(() => {
        executeFetchRef.current();
        setSecondsUntilRefresh(Math.floor(intervalMs / 1000));
      }, intervalMs);
    };

    if (staggerMs > 0) {
      staggerRef.current = setTimeout(() => {
        executeFetchRef.current();
        setSecondsUntilRefresh(Math.floor(intervalMs / 1000));
        startInterval();
      }, staggerMs);
    } else {
      startInterval();
    }

    // 倒计时定时器
    countdownRef.current = setInterval(() => {
      setSecondsUntilRefresh((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      if (countdownRef.current) clearInterval(countdownRef.current);
      if (staggerRef.current) clearTimeout(staggerRef.current);
    };
  }, [autoRefreshEnabled, paused, intervalMs, staggerMs]);

  // 计算新鲜度
  const freshness = (() => {
    if (!lastSuccessfulFetch) {
      return { elapsed: null, level: 'unknown', label: '暂无数据' };
    }
    const elapsed = Math.floor((Date.now() - lastSuccessfulFetch) / 1000);
    if (elapsed < freshThreshold) {
      return { elapsed, level: 'fresh', label: '数据新鲜' };
    }
    if (elapsed < staleThreshold) {
      return { elapsed, level: 'stale', label: '数据较旧' };
    }
    return { elapsed, level: 'expired', label: '数据过期' };
  })();

  return {
    data,
    loading,
    refreshing,
    error,
    lastSuccessfulFetch,
    refresh,
    markRefreshed,
    autoRefreshEnabled,
    toggleAutoRefresh,
    secondsUntilRefresh,
    freshness,
    serverStale,
    cachedAt,
  };
}
