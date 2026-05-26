/**
 * @fileoverview 数据源状态组件 - 显示各数据适配器的健康状态
 * @module components/DataSourceStatus
 * @description 展示 AkShare、东方财富等数据源适配器的连接状态、成功率、延迟等统计信息
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getDataSourceStatus } from '../api/client';

/**
 * 格式化延迟时间显示
 *
 * @param {number|null} ms - 延迟毫秒数
 * @returns {string} 格式化后的延迟字符串（如 "150ms" 或 "1.20s"）
 */
function formatLatency(ms) {
  if (ms === null || ms === undefined) return '--';
  const numeric = Number(ms);
  if (Number.isNaN(numeric)) return '--';
  if (numeric < 1000) return `${Math.round(numeric)}ms`;
  return `${(numeric / 1000).toFixed(2)}s`;
}

/**
 * 格式化日期时间显示
 *
 * @param {string|null} value - ISO 日期时间字符串
 * @returns {string} 本地化的日期时间字符串
 */
function formatDateTime(value) {
  if (!value) return '--';
  try {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString();
  } catch {
    return value;
  }
}

/**
 * DataSourceStatus - 数据源状态展示组件
 *
 * @description
 * - 加载并展示各数据源适配器的状态
 * - 显示成功次数、失败次数、平均延迟
 * - 健康状态以绿色/红色圆点标识
 * - 显示最近的错误信息（如有）
 * - mock 适配器始终标记为健康
 *
 * @returns {JSX.Element} 数据源状态列表组件
 *
 * @example
 * <DataSourceStatus />
 */
export default function DataSourceStatus() {
  const { t } = useTranslation();
  /** @type {[Array, Function]} 适配器列表 */
  const [adapters, setAdapters] = useState([]);
  /** @type {[boolean, Function]} 加载状态 */
  const [loading, setLoading] = useState(true);
  /** @type {[string, Function]} 错误信息 */
  const [error, setError] = useState('');

  /**
   * 加载数据源状态
   * @async
   */
  const loadStatus = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await getDataSourceStatus();
      // 后端返回扁平对象：{ akshare: {...}, eastmoney: {...}, mock: {...} }
      if (response && typeof response === 'object' && !Array.isArray(response)) {
        const adapterList = Object.entries(response).map(([name, stats]) => ({
          name,
          ...stats,
        }));
        setAdapters(adapterList);
      } else {
        setAdapters(Array.isArray(response?.adapters) ? response.adapters : []);
      }
    } catch (e) {
      setAdapters([]);
      setError(e.message || '');
    } finally {
      setLoading(false);
    }
  }, []);

  // 组件挂载时加载状态
  useEffect(() => { loadStatus(); }, [loadStatus]);

  // 加载中状态
  if (loading) {
    return <p className="empty-state">{t('common.loading')}</p>;
  }

  // 错误状态
  if (error) {
    return <p className="empty-state">{error}</p>;
  }

  // 空状态
  if (adapters.length === 0) {
    return <p className="data-source-status__empty">{t('dataSource.noAdapters')}</p>;
  }

  return (
    <div className="data-source-status">
      {adapters.map((adapter) => {
        // 判断健康状态：无最近错误且成功次数 > 0，mock 适配器始终健康
        const isHealthy = adapter.name === 'mock'
          ? true
          : !adapter.last_error && (adapter.success_count ?? 0) > 0;
        return (
          <article key={adapter.name || adapter.adapter} className="data-source-adapter">
            {/* 健康状态指示点 */}
            <span className={`data-source-adapter__dot ${isHealthy ? 'data-source-adapter__dot--healthy' : 'data-source-adapter__dot--failing'}`}
              title={isHealthy ? t('dataSource.healthy') : t('dataSource.failing')} />
            <div className="data-source-adapter__info">
              <div className="data-source-adapter__name">{adapter.name || adapter.adapter}</div>
              {/* 统计信息 */}
              <div className="data-source-adapter__stats">
                <span className="data-source-adapter__stat">
                  {t('dataSource.successCount')}:
                  <span className="data-source-adapter__stat-value">{adapter.success_count ?? 0}</span>
                </span>
                <span className="data-source-adapter__stat">
                  {t('dataSource.failureCount')}:
                  <span className="data-source-adapter__stat-value">{adapter.failure_count ?? 0}</span>
                </span>
                <span className="data-source-adapter__stat">
                  {t('dataSource.avgLatency')}:
                  <span className="data-source-adapter__stat-value">{formatLatency(adapter.avg_latency_ms)}</span>
                </span>
              </div>
              {/* 最近错误信息 */}
              {adapter.last_error ? (
                <div className="data-source-adapter__error" title={adapter.last_error}>
                  {t('dataSource.lastError')}: {adapter.last_error}
                </div>
              ) : null}
            </div>
          </article>
        );
      })}
    </div>
  );
}
