/**
 * @fileoverview 数据源选择器组件 - 支持交互式选择历史数据源
 * @module components/DataSourceSelector
 * @description 增强版数据源选择器，支持：
 * - 交互式选择数据源（Auto 回退链 / 指定适配器）
 * - 三级健康状态指示（健康/降级/离线）
 * - 优先级编号显示（1-4）
 * - 当前活跃源高亮
 * - 保存选择到后端并持久化
 * - 成功/失败计数、平均延迟、最近错误
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  getDataSourceStatus,
  getDataSourcePreference,
  setDataSourcePreference,
  getDeepSeekStatus,
} from '../api/client';

/**
 * 已知数据源的默认优先级映射
 * @type {Object<string, number>}
 */
const DEFAULT_PRIORITIES = {
  tushare: 1,
  baostock: 2,
  efinance: 3,
  akshare: 4,
  deepseek: 5,
};

/**
 * 数据源显示名称映射
 * @type {Object<string, string>}
 */
const SOURCE_LABELS = {
  auto: 'Auto (自动回退)',
  tushare: 'Tushare',
  baostock: 'Baostock',
  efinance: 'efinance',
  akshare: 'AkShare',
  deepseek: 'DeepSeek',
};

/**
 * 格式化延迟时间显示
 */
function formatLatency(ms) {
  if (ms === null || ms === undefined) return '--';
  const numeric = Number(ms);
  if (Number.isNaN(numeric)) return '--';
  if (numeric < 1000) return `${Math.round(numeric)}ms`;
  return `${(numeric / 1000).toFixed(2)}s`;
}

/**
 * 判断适配器健康状态
 */
function getHealthStatus(adapter) {
  if (adapter.name === 'mock') return 'healthy';

  const success = adapter.success_count ?? 0;
  const failure = adapter.failure_count ?? 0;
  const hasError = Boolean(adapter.last_error);
  const health = adapter.health;

  // If we have a health check result, use it
  if (health && typeof health === 'object') {
    if (health.ok === true) return 'healthy';
    if (health.ok === false && success > 0) return 'degraded';
    if (health.ok === false) return 'down';
  }

  if (success === 0 && (failure > 0 || hasError)) return 'down';
  if (success > 0 && hasError) return 'degraded';
  if (success > 0) return 'healthy';
  return 'degraded';
}

/**
 * 获取适配器优先级
 */
function getPriority(adapter, index) {
  if (adapter.priority != null) return adapter.priority;
  const name = (adapter.name || adapter.adapter || '').toLowerCase();
  return DEFAULT_PRIORITIES[name] ?? (index + 1);
}

/**
 * DataSourceSelector - 交互式数据源选择器组件
 *
 * @description
 * - 加载并展示各数据源适配器的状态和优先级
 * - 提供单选按钮选择数据源（Auto 或指定适配器）
 * - 三级健康指示：健康（绿）、降级（黄）、离线（红）
 * - 高亮当前活跃数据源
 * - 保存按钮将选择持久化到后端
 * - 可折叠面板：默认显示摘要，点击展开详情
 */
export default function DataSourceSelector() {
  const { t } = useTranslation();
  const [adapters, setAdapters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState(false);

  // Selection state
  const [activeSource, setActiveSource] = useState('auto');
  const [selectedSource, setSelectedSource] = useState('auto');
  const [availableSources, setAvailableSources] = useState([]);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState('');
  const [saveError, setSaveError] = useState('');

  // DeepSeek status
  const [deepseekStatus, setDeepseekStatus] = useState(null);
  const [deepseekError, setDeepseekError] = useState('');

  /**
   * 加载数据源状态和偏好
   */
  const loadData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [statusResponse, prefResponse] = await Promise.all([
        getDataSourceStatus(),
        getDataSourcePreference(),
      ]);

      // Parse status
      if (statusResponse && typeof statusResponse === 'object' && !Array.isArray(statusResponse)) {
        const adapterList = Object.entries(statusResponse)
          .filter(([name]) => name !== '_meta' && name !== 'historical_adapters')
          .map(([name, stats], index) => ({
            name,
            ...stats,
            _priority: stats.priority ?? DEFAULT_PRIORITIES[name] ?? (index + 1),
          }));
        adapterList.sort((a, b) => a._priority - b._priority);
        setAdapters(adapterList);
      }

      // Parse preference
      if (prefResponse) {
        const src = prefResponse.active_source || 'auto';
        setActiveSource(src);
        setSelectedSource(src);
        setAvailableSources(prefResponse.available_sources || []);
      }
    } catch (e) {
      setAdapters([]);
      setError(e.message || '');
    } finally {
      setLoading(false);
    }

    // Fetch DeepSeek status (non-blocking)
    try {
      const dsStatus = await getDeepSeekStatus();
      setDeepseekStatus(dsStatus);
      setDeepseekError('');
    } catch (e) {
      setDeepseekStatus(null);
      setDeepseekError(e.message || '');
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  /**
   * 保存数据源选择
   */
  const handleSave = useCallback(async () => {
    setSaving(true);
    setSaveMessage('');
    setSaveError('');
    try {
      const result = await setDataSourcePreference(selectedSource);
      setActiveSource(result.active_source || selectedSource);
      setSaveMessage(t('dataSourceSelector.saveSuccess', { source: selectedSource }));
      // Clear message after 3 seconds
      setTimeout(() => setSaveMessage(''), 3000);
    } catch (e) {
      setSaveError(e.message || t('dataSourceSelector.saveFailed'));
    } finally {
      setSaving(false);
    }
  }, [selectedSource, t]);

  /**
   * 计算摘要信息
   */
  const summary = useMemo(() => {
    if (adapters.length === 0) return null;

    const statuses = adapters.map((a) => ({ ...a, _health: getHealthStatus(a) }));
    const healthyCount = statuses.filter((s) => s._health === 'healthy').length;
    const degradedCount = statuses.filter((s) => s._health === 'degraded').length;
    const downCount = statuses.filter((s) => s._health === 'down').length;

    return { statuses, healthyCount, degradedCount, downCount };
  }, [adapters]);

  const hasChanges = selectedSource !== activeSource;

  // 加载中
  if (loading) {
    return (
      <div className="ds-selector">
        <p className="empty-state">{t('common.loading')}</p>
      </div>
    );
  }

  // 错误
  if (error) {
    return (
      <div className="ds-selector">
        <p className="empty-state">{error}</p>
      </div>
    );
  }

  // 空状态
  if (!summary || adapters.length === 0) {
    return (
      <div className="ds-selector">
        <p className="ds-selector__empty">{t('dataSource.noAdapters')}</p>
      </div>
    );
  }

  const { statuses, healthyCount, degradedCount, downCount } = summary;

  // Build the list of options: "auto" + all available adapters
  const options = [
    { value: 'auto', label: SOURCE_LABELS.auto || 'Auto (Fallback Chain)' },
    ...availableSources.map((name) => ({
      value: name,
      label: SOURCE_LABELS[name] || name,
    })),
  ];

  return (
    <div className="ds-selector">
      {/* 摘要栏 - 始终可见 */}
      <button
        type="button"
        className="ds-selector__summary"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <div className="ds-selector__summary-left">
          {/* 状态计数 */}
          <div className="ds-selector__counts">
            {healthyCount > 0 && (
              <span className="ds-selector__count ds-selector__count--healthy">
                <span className="ds-selector__count-dot ds-selector__count-dot--healthy" />
                {healthyCount}
              </span>
            )}
            {degradedCount > 0 && (
              <span className="ds-selector__count ds-selector__count--degraded">
                <span className="ds-selector__count-dot ds-selector__count-dot--degraded" />
                {degradedCount}
              </span>
            )}
            {downCount > 0 && (
              <span className="ds-selector__count ds-selector__count--down">
                <span className="ds-selector__count-dot ds-selector__count-dot--down" />
                {downCount}
              </span>
            )}
          </div>
          {/* 当前活跃源 */}
          <span className="ds-selector__primary-label">
            {t('dataSourceSelector.activeSource', '当前数据源')}:{' '}
            <strong>{SOURCE_LABELS[activeSource] || activeSource}</strong>
          </span>
        </div>
        {/* 展开/折叠箭头 */}
        <span className={`ds-selector__chevron ${expanded ? 'ds-selector__chevron--open' : ''}`}>
          {'\u25BC'}
        </span>
      </button>

      {/* 详情面板 - 可折叠 */}
      <div className={`ds-selector__details ${expanded ? 'ds-selector__details--open' : ''}`}>
        <div className="ds-selector__details-inner">
          {/* 选择区域 */}
          <div className="ds-selector__picker">
            <div className="ds-selector__picker-label">
              {t('dataSourceSelector.selectSource', '选择数据源')}:
            </div>
            <div className="ds-selector__options">
              {options.map((opt) => {
                const adapterData = statuses.find((a) => a.name === opt.value);
                const health = adapterData ? getHealthStatus(adapterData) : null;
                const isSelected = selectedSource === opt.value;

                return (
                  <label
                    key={opt.value}
                    className={`ds-option ${isSelected ? 'ds-option--selected' : ''} ${opt.value === 'deepseek' ? 'ds-option--deepseek' : ''}`}
                  >
                    <input
                      type="radio"
                      name="data-source"
                      value={opt.value}
                      checked={isSelected}
                      onChange={() => setSelectedSource(opt.value)}
                      className="ds-option__radio"
                    />
                    <div className="ds-option__content">
                      <div className="ds-option__header">
                        {health && (
                          <span
                            className={`ds-adapter__dot ds-adapter__dot--${health}`}
                            title={t(`dataSourceSelector.health.${health}`)}
                          />
                        )}
                        <span className="ds-option__name">{opt.label}</span>
                        {opt.value === activeSource && (
                          <span className="ds-adapter__active-badge">
                            {t('dataSourceSelector.active', '当前')}
                          </span>
                        )}
                      </div>
                      {adapterData && (
                        <div className="ds-option__stats">
                          <span className="ds-adapter__stat">
                            {t('dataSource.successCount')}:
                            <span className="ds-adapter__stat-value">{adapterData.stats?.success_count ?? 0}</span>
                          </span>
                          <span className="ds-adapter__stat">
                            {t('dataSource.failureCount')}:
                            <span className="ds-adapter__stat-value">{adapterData.stats?.failure_count ?? 0}</span>
                          </span>
                          <span className="ds-adapter__stat">
                            {t('dataSource.avgLatency')}:
                            <span className="ds-adapter__stat-value">
                              {formatLatency(adapterData.stats?.avg_latency_ms)}
                            </span>
                          </span>
                        </div>
                      )}
                      {adapterData?.stats?.last_error ? (
                        <div className="ds-option__error" title={adapterData.stats.last_error}>
                          {t('dataSource.lastError')}: {adapterData.stats.last_error}
                        </div>
                      ) : null}
                    </div>
                  </label>
                );
              })}
            </div>

            {/* DeepSeek usage stats */}
            {(selectedSource === 'deepseek' || activeSource === 'deepseek') && (
              <div className="ds-deepseek-status">
                {deepseekError && (
                  <div className="ds-deepseek-status__error">
                    <span className="ds-deepseek-status__error-icon">{'\u26A0'}</span>
                    {t('dataSourceSelector.deepseek.fetchError', 'Unable to fetch DeepSeek status')}: {deepseekError}
                  </div>
                )}
                {deepseekStatus && (
                  <>
                    <div className="ds-deepseek-status__header">
                      <span className="ds-deepseek-status__label">
                        {t('dataSourceSelector.deepseek.usageTitle', 'DeepSeek API Usage')}
                      </span>
                      {deepseekStatus.circuit_breaker_open && (
                        <span className="ds-deepseek-status__cb-open" title={t('dataSourceSelector.deepseek.cbOpen', 'Circuit breaker is open -- DeepSeek search temporarily unavailable')}>
                          {t('dataSourceSelector.deepseek.cbOpenBadge', 'CIRCUIT OPEN')}
                        </span>
                      )}
                    </div>
                    <div className="ds-deepseek-status__grid">
                      <div className="ds-deepseek-status__metric">
                        <span className="ds-deepseek-status__metric-label">
                          {t('dataSourceSelector.deepseek.remainingCalls', 'Remaining Calls')}
                        </span>
                        <span className="ds-deepseek-status__metric-value">
                          {deepseekStatus.remaining_calls ?? '--'}
                          {deepseekStatus.daily_limit != null && (
                            <span className="ds-deepseek-status__metric-limit"> / {deepseekStatus.daily_limit}</span>
                          )}
                        </span>
                      </div>
                      <div className="ds-deepseek-status__metric">
                        <span className="ds-deepseek-status__metric-label">
                          {t('dataSourceSelector.deepseek.cbStatus', 'Circuit Breaker')}
                        </span>
                        <span className={`ds-deepseek-status__metric-value ${deepseekStatus.circuit_breaker_open ? 'ds-deepseek-status__metric-value--error' : 'ds-deepseek-status__metric-value--ok'}`}>
                          {deepseekStatus.circuit_breaker_open
                            ? t('dataSourceSelector.deepseek.cbOpenText', 'Open')
                            : t('dataSourceSelector.deepseek.cbClosedText', 'Closed')}
                        </span>
                      </div>
                      {deepseekStatus.total_calls != null && (
                        <div className="ds-deepseek-status__metric">
                          <span className="ds-deepseek-status__metric-label">
                            {t('dataSourceSelector.deepseek.totalCalls', 'Total Calls Today')}
                          </span>
                          <span className="ds-deepseek-status__metric-value">
                            {deepseekStatus.total_calls}
                          </span>
                        </div>
                      )}
                    </div>
                    {deepseekStatus.circuit_breaker_open && (
                      <div className="ds-deepseek-status__warning">
                        <span className="ds-deepseek-status__warning-icon">{'\u26A0'}</span>
                        {t('dataSourceSelector.deepseek.cbWarning', 'Circuit breaker is open. DeepSeek search is temporarily unavailable due to repeated failures. It will automatically retry after a cooldown period.')}
                      </div>
                    )}
                  </>
                )}
                {!deepseekStatus && !deepseekError && (
                  <p className="ds-deepseek-status__loading">{t('common.loading')}</p>
                )}
              </div>
            )}

            {/* 保存按钮 */}
            <div className="ds-selector__actions">
              {saveMessage && (
                <span className="ds-selector__save-msg ds-selector__save-msg--success">
                  {saveMessage}
                </span>
              )}
              {saveError && (
                <span className="ds-selector__save-msg ds-selector__save-msg--error">
                  {saveError}
                </span>
              )}
              <button
                type="button"
                className="button button--sm"
                onClick={handleSave}
                disabled={saving || !hasChanges}
              >
                {saving
                  ? t('dataSourceSelector.saving', '保存中...')
                  : t('dataSourceSelector.save', '保存选择')}
              </button>
              {hasChanges && (
                <button
                  type="button"
                  className="button button--sm button--secondary"
                  onClick={() => setSelectedSource(activeSource)}
                  disabled={saving}
                >
                  {t('common.cancel', '取消')}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
