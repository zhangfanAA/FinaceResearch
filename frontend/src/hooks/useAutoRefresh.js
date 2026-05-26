/**
 * @fileoverview 自动刷新 Hook - 提供定时数据刷新和倒计时功能
 * @module hooks/useAutoRefresh
 * @description 可复用的自动刷新 Hook，支持启用/禁用、外部暂停信号和倒计时显示
 */

import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * useAutoRefresh - 自动刷新数据的 Hook
 *
 * @description
 * - 支持可配置的刷新间隔
 * - 支持启用/禁用切换
 * - 支持外部暂停信号（如 AI 分析进行中时暂停刷新）
 * - 提供倒计时秒数，便于 UI 显示
 * - 使用 ref 保持回调引用最新，避免不必要的重渲染
 *
 * @param {Object} options - 配置选项
 * @param {Function} options.onRefresh - 每次刷新时执行的异步回调函数
 * @param {number} options.intervalMs - 刷新间隔（毫秒）
 * @param {boolean} [options.enabled=true] - 是否默认启用自动刷新
 * @param {boolean} [options.paused=false] - 外部暂停信号（如 AI 分析进行中）
 * @returns {Object} 自动刷新控制对象
 * @property {boolean} autoRefreshEnabled - 当前自动刷新是否启用
 * @property {Function} toggleAutoRefresh - 切换自动刷新启用/禁用状态
 * @property {number} secondsUntilRefresh - 距离下次刷新的倒计时秒数
 * @property {number|null} lastRefreshAt - 上次刷新的时间戳（毫秒），未刷新时为 null
 * @property {Function} markRefreshed - 手动标记已刷新（重置倒计时）
 *
 * @example
 * const { autoRefreshEnabled, toggleAutoRefresh, secondsUntilRefresh } = useAutoRefresh({
 *   onRefresh: loadData,
 *   intervalMs: 60000,
 *   enabled: true,
 *   paused: isAnalyzing,
 * });
 */
export default function useAutoRefresh({ onRefresh, intervalMs, enabled = true, paused = false }) {
  /** @type {[boolean, Function]} 自动刷新启用状态 */
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(enabled);
  /** @type {[number, Function]} 距离下次刷新的倒计时秒数 */
  const [secondsUntilRefresh, setSecondsUntilRefresh] = useState(Math.floor(intervalMs / 1000));
  /** @type {[number|null, Function]} 上次刷新时间戳 */
  const [lastRefreshAt, setLastRefreshAt] = useState(null);

  /** @type {React.RefObject<number|null>} 主刷新定时器引用 */
  const intervalRef = useRef(null);
  /** @type {React.RefObject<number|null>} 倒计时定时器引用 */
  const countdownRef = useRef(null);
  /** @type {React.RefObject<Function>} 刷新回调引用（保持最新） */
  const onRefreshRef = useRef(onRefresh);

  // 保持回调引用最新，避免因回调变化导致定时器重建
  useEffect(() => {
    onRefreshRef.current = onRefresh;
  }, [onRefresh]);

  /**
   * 切换自动刷新启用/禁用状态
   * @type {Function}
   */
  const toggleAutoRefresh = useCallback(() => {
    setAutoRefreshEnabled((prev) => !prev);
  }, []);

  /**
   * 手动标记已刷新，重置倒计时
   * @type {Function}
   */
  const markRefreshed = useCallback(() => {
    setLastRefreshAt(Date.now());
    setSecondsUntilRefresh(Math.floor(intervalMs / 1000));
  }, [intervalMs]);

  // 主效果：管理刷新定时器和倒计时定时器
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

    // 如果禁用或暂停，不启动定时器
    if (!autoRefreshEnabled || paused) {
      return () => {
        if (intervalRef.current) clearInterval(intervalRef.current);
        if (countdownRef.current) clearInterval(countdownRef.current);
      };
    }

    // 重置倒计时
    setSecondsUntilRefresh(Math.floor(intervalMs / 1000));

    // 主刷新定时器：每隔 intervalMs 执行一次刷新
    intervalRef.current = setInterval(() => {
      onRefreshRef.current?.();
      setLastRefreshAt(Date.now());
      setSecondsUntilRefresh(Math.floor(intervalMs / 1000));
    }, intervalMs);

    // 倒计时定时器：每秒递减倒计时
    countdownRef.current = setInterval(() => {
      setSecondsUntilRefresh((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);

    // 清理函数：组件卸载或依赖变化时清除定时器
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      if (countdownRef.current) clearInterval(countdownRef.current);
    };
  }, [autoRefreshEnabled, paused, intervalMs]);

  return {
    autoRefreshEnabled,
    toggleAutoRefresh,
    secondsUntilRefresh,
    lastRefreshAt,
    markRefreshed,
  };
}
