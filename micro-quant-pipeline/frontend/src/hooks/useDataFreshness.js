/**
 * @fileoverview 数据新鲜度追踪 Hook - 监控数据更新时间并返回新鲜度状态
 * @module hooks/useDataFreshness
 * @description 根据数据最后更新时间戳，实时计算数据新鲜度等级（fresh/stale/old），
 * 用于在 UI 中显示数据是否过期
 */

import { useEffect, useState } from 'react';

/**
 * useDataFreshness - 数据新鲜度追踪 Hook
 *
 * @description
 * - 接收数据最后更新的时间戳
 * - 每秒计算经过的秒数
 * - 根据可配置的阈值返回新鲜度等级：
 *   - 'fresh'：数据新鲜（绿色指示）
 *   - 'stale'：数据略旧（黄色指示）
 *   - 'old'：数据过期（红色指示）
 * - 返回人类可读的时间标签（如 "30秒前更新"、"2分钟前更新"）
 *
 * @param {number|null} lastUpdated - 数据最后更新的时间戳（毫秒），null 表示未更新
 * @param {Object} [thresholds] - 新鲜度阈值配置
 * @param {number} [thresholds.fresh=30] - 小于此秒数为 "fresh"（新鲜）
 * @param {number} [thresholds.stale=120] - 小于此秒数为 "stale"（略旧），大于等于为 "old"（过期）
 * @returns {Object} 新鲜度状态对象
 * @property {number} elapsed - 距离上次更新经过的秒数
 * @property {'fresh'|'stale'|'old'} level - 新鲜度等级
 * @property {string} label - 人类可读的时间标签
 *
 * @example
 * const freshness = useDataFreshness(lastFetchedAt, { fresh: 60, stale: 300 });
 * // freshness = { elapsed: 45, level: 'fresh', label: '45秒前更新' }
 *
 * <DataFreshnessBadge level={freshness.level} label={freshness.label} />
 */
export default function useDataFreshness(lastUpdated, { fresh = 30, stale = 120 } = {}) {
  /** @type {[number, Function]} 距离上次更新经过的秒数 */
  const [elapsed, setElapsed] = useState(0);

  // 每秒更新经过时间
  useEffect(() => {
    if (!lastUpdated) {
      setElapsed(0);
      return () => {};
    }

    /** 计算经过秒数并更新状态 */
    function tick() {
      const diff = Math.floor((Date.now() - lastUpdated) / 1000);
      setElapsed(diff);
    }

    tick(); // 立即执行一次
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [lastUpdated]);

  /** @type {string} 新鲜度等级 */
  let level = 'fresh';
  /** @type {string} 人类可读的时间标签 */
  let label = '';

  if (!lastUpdated) {
    level = 'old';
    label = '未更新';
  } else if (elapsed < fresh) {
    level = 'fresh';
    label = `${elapsed}秒前更新`;
  } else if (elapsed < stale) {
    level = 'stale';
    label = `${elapsed}秒前更新`;
  } else {
    level = 'old';
    if (elapsed < 60) {
      label = `${elapsed}秒前更新`;
    } else {
      label = `${Math.floor(elapsed / 60)}分钟前更新`;
    }
  }

  return { elapsed, level, label };
}
