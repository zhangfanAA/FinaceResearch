/**
 * @fileoverview 分析历史记录组件 - 展示和管理历史分析结果
 * @module components/AnalysisHistory
 * @description 展示历史分析记录列表，支持按类型筛选、搜索、日期过滤、
 * 展开详情、多选对比和导出功能
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getAnalysisHistory } from '../api/client';
import AnalysisComparison from './AnalysisComparison';
import ErrorWithRetry from './ErrorWithRetry';
import ExportButton from './ExportButton';

/**
 * 格式化日期时间显示
 * @function formatDate
 * @param {string|null} value - 日期字符串
 * @returns {string} 格式化后的本地日期时间字符串，无效值返回 '--'
 */
function formatDate(value) {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

/**
 * 判断日期是否在指定天数内
 * @function isWithinDays
 * @param {string} dateStr - 日期字符串
 * @param {number} days - 天数阈值
 * @returns {boolean} 如果日期在当前时间前 N 天内返回 true
 */
function isWithinDays(dateStr, days) {
  if (!dateStr) return false;
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return false;
  const now = new Date();
  const cutoff = new Date(now.getTime() - days * 24 * 60 * 60 * 1000);
  return date >= cutoff;
}

/**
 * 判断日期是否为今天
 * @function isToday
 * @param {string} dateStr - 日期字符串
 * @returns {boolean} 如果日期是今天返回 true
 */
function isToday(dateStr) {
  if (!dateStr) return false;
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return false;
  const now = new Date();
  return (
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()
  );
}

/**
 * 生成分析结果的简短摘要
 * @function formatBrief
 * @param {Object} item - 分析记录对象
 * @returns {string|null} 截断到 120 字符的摘要文本，无内容返回 null
 * @description 优先使用 summary 字段，其次从 result 中提取 reasoning 或 logic
 */
function formatBrief(item) {
  if (item.summary) return item.summary;
  if (item.result) {
    if (typeof item.result === 'string') {
      return item.result.length > 120 ? item.result.slice(0, 120) + '...' : item.result;
    }
    if (item.result.reasoning) {
      const text = item.result.reasoning;
      return text.length > 120 ? text.slice(0, 120) + '...' : text;
    }
    if (item.result.logic) {
      const text = item.result.logic;
      return text.length > 120 ? text.slice(0, 120) + '...' : text;
    }
  }
  return null;
}

/**
 * 单条历史记录项组件
 *
 * @component HistoryItem
 * @description 展示单条分析历史记录，支持展开/收起详情、选中对比
 *
 * @param {Object} props
 * @param {Object} props.item - 分析记录数据对象
 * @param {boolean} props.expanded - 是否展开详情
 * @param {Function} props.onToggle - 切换展开/收起的回调
 * @param {boolean} props.selected - 是否被选中对比
 * @param {Function} props.onSelectChange - 选中状态变更回调，参数为 (item, checked)
 * @param {Function} props.t - i18next 翻译函数
 *
 * @returns {JSX.Element} 历史记录项 JSX
 */
function HistoryItem({ item, expanded, onToggle, selected, onSelectChange, t }) {
  const typeTone = item.type === 'stock_sector' ? 'good' : item.type === 'fund_sector' ? 'warn' : 'bad';
  const typeLabel = item.type === 'stock_sector' ? t('analysisHistory.filterStock') : item.type === 'fund_sector' ? t('analysisHistory.filterFund') : t('common.unknown');
  const exportFilename = `${item.type || 'analysis'}-${item.target_code || item.target_name || 'result'}`;

  return (
    <article className={`history-item ${expanded ? 'history-item--expanded' : ''}`}>
      <div className="history-item__header"
        onClick={onToggle} role="button" tabIndex={0}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onToggle(); } }}>
        <div className="history-item__info">
          <label className="history-item__checkbox" onClick={(e) => e.stopPropagation()}>
            <input
              type="checkbox"
              checked={selected}
              onChange={(e) => onSelectChange(item, e.target.checked)}
              aria-label={t('analysisHistory.selectForCompare')}
            />
          </label>
          <span className={`badge badge--${typeTone}`}>{typeLabel}</span>
          <span className="history-item__target">{item.target_name || item.target_code || '--'}</span>
          {item.target_code && item.target_name ? <span className="history-item__code">{item.target_code}</span> : null}
        </div>
        <div className="history-item__meta">
          <ExportButton data={item.result || item} filename={exportFilename} size="sm" />
          <span className="history-item__time">{formatDate(item.created_at || item.timestamp)}</span>
          <span className={`history-item__chevron ${expanded ? 'history-item__chevron--open' : ''}`}>&#9662;</span>
        </div>
      </div>

      {!expanded ? <p className="history-item__brief">{formatBrief(item) || t('analysisHistory.noSummary')}</p> : null}

      {expanded ? (
        <div className="history-item__detail">
          {item.result && typeof item.result === 'object' ? (
            <div className="analysis-result-grid">
              {item.result.trend ? (
                <div className="analysis-result__header">
                  <h3>{item.target_name || item.target_code || t('analysisHistory.result')}</h3>
                  <div className="analysis-result__badges">
                    <span className={`badge badge--${item.result.trend === 'bullish' ? 'good' : item.result.trend === 'bearish' ? 'bad' : 'warn'}`}>
                      {item.result.trend === 'bullish' ? t('stockSector.trend.bullish') : item.result.trend === 'bearish' ? t('stockSector.trend.bearish') : t('stockSector.trend.neutral')}
                    </span>
                  </div>
                </div>
              ) : null}

              {item.result.judgment ? (
                <div className="analysis-result__header">
                  <h3>{item.target_name || item.target_code || t('analysisHistory.result')}</h3>
                  <div className="analysis-result__badges">
                    <span className={`badge badge--${item.result.judgment === 'positive' ? 'good' : item.result.judgment === 'negative' ? 'bad' : 'warn'}`}>
                      {item.result.judgment === 'positive' ? t('fundSector.judgment.positive') : item.result.judgment === 'negative' ? t('fundSector.judgment.negative') : t('fundSector.judgment.neutral')}
                    </span>
                  </div>
                </div>
              ) : null}

              {item.result.sentiment_score != null ? (
                <section className="subpanel">
                  <div className="subpanel__header"><h3>{t('analysisHistory.sentimentScore')}</h3></div>
                  <p className="research-copy">{(item.result.sentiment_score * 100).toFixed(0)}%</p>
                </section>
              ) : null}

              {item.result.reasoning ? (
                <section className="subpanel">
                  <div className="subpanel__header"><h3>{t('analysisHistory.reasoning')}</h3></div>
                  <p className="research-copy">{item.result.reasoning}</p>
                </section>
              ) : null}

              {item.result.logic ? (
                <section className="subpanel">
                  <div className="subpanel__header"><h3>{t('analysisHistory.reasoning')}</h3></div>
                  <p className="research-copy">{item.result.logic}</p>
                </section>
              ) : null}

              {item.result.suggestion ? (
                <section className="subpanel">
                  <div className="subpanel__header"><h3>{t('analysisHistory.suggestion')}</h3></div>
                  <p className="research-copy research-copy--suggestion">{item.result.suggestion}</p>
                </section>
              ) : null}

              {item.result.key_factors?.length > 0 ? (
                <section className="subpanel">
                  <div className="subpanel__header"><h3>{t('analysisHistory.keyFactors')}</h3></div>
                  <ul className="analysis-factor-list">
                    {item.result.key_factors.map((f, i) => (
                      <li key={i} className="analysis-factor-item"><span className="analysis-factor-icon">+</span>{f}</li>
                    ))}
                  </ul>
                </section>
              ) : null}

              {item.result.risk_warnings?.length > 0 ? (
                <section className="subpanel subpanel--warning">
                  <div className="subpanel__header"><h3>{t('analysisHistory.riskWarnings')}</h3></div>
                  <ul className="analysis-factor-list">
                    {item.result.risk_warnings.map((w, i) => (
                      <li key={i} className="analysis-factor-item analysis-factor-item--risk">
                        <span className="analysis-factor-icon analysis-factor-icon--risk">!</span>{w}
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}
            </div>
          ) : (
            <pre className="history-item__raw">
              {typeof item.result === 'string' ? item.result : JSON.stringify(item.result, null, 2)}
            </pre>
          )}
        </div>
      ) : null}
    </article>
  );
}

/**
 * 分析历史记录组件
 *
 * @component AnalysisHistory
 * @description 展示和管理历史分析结果，支持以下功能：
 * - 按类型筛选（全部/股票/基金）
 * - 按日期筛选（全部/今天/本周/本月）
 * - 关键词搜索（按名称或代码）
 * - 展开详情查看完整分析结果
 * - 多选对比（最多 3 条）
 * - 导出功能
 *
 * @param {Object} props
 * @param {'all'|'stock_sector'|'fund_sector'} [props.initialType='all'] - 初始筛选类型
 * @param {string} [props.className=''] - 自定义 CSS 类名
 *
 * @returns {JSX.Element} 分析历史记录界面
 *
 * @example
 * <AnalysisHistory initialType="stock_sector" />
 */
export default function AnalysisHistory({ initialType = 'all', className = '' }) {
  const { t } = useTranslation();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState(initialType);
  const [expandedId, setExpandedId] = useState(null);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [compareItems, setCompareItems] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [dateFilter, setDateFilter] = useState('all');

  const FILTER_OPTIONS = [
    { value: 'all', label: t('analysisHistory.filterAll') },
    { value: 'stock_sector', label: t('analysisHistory.filterStock') },
    { value: 'fund_sector', label: t('analysisHistory.filterFund') },
  ];

  const DATE_FILTER_OPTIONS = [
    { value: 'all', label: t('analysisHistory.dateFilter.all') },
    { value: 'today', label: t('analysisHistory.dateFilter.today') },
    { value: 'week', label: t('analysisHistory.dateFilter.week') },
    { value: 'month', label: t('analysisHistory.dateFilter.month') },
  ];

  const loadHistory = useCallback(async (type) => {
    setLoading(true); setError('');
    try {
      const data = await getAnalysisHistory(type, 20);
      setItems(Array.isArray(data) ? data : data?.items || []);
    } catch (err) {
      setItems([]);
      setError(err.message || '加载分析历史失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadHistory(filter); }, [filter, loadHistory]);

  const filteredItems = useMemo(() => {
    let result = items;

    // Apply search filter
    if (searchQuery.trim()) {
      const query = searchQuery.trim().toLowerCase();
      result = result.filter((item) => {
        const name = (item.target_name || '').toLowerCase();
        const code = (item.target_code || '').toLowerCase();
        return name.includes(query) || code.includes(query);
      });
    }

    // Apply date filter
    if (dateFilter !== 'all') {
      result = result.filter((item) => {
        const dateStr = item.created_at || item.timestamp;
        if (dateFilter === 'today') return isToday(dateStr);
        if (dateFilter === 'week') return isWithinDays(dateStr, 7);
        if (dateFilter === 'month') return isWithinDays(dateStr, 30);
        return true;
      });
    }

    return result;
  }, [items, searchQuery, dateFilter]);

  /**
   * 处理记录选中状态变更
   * @function handleSelectChange
   * @param {Object} item - 分析记录对象
   * @param {boolean} checked - 是否选中
   * @description 最多允许选择 3 条记录进行对比
   */
  function handleSelectChange(item, checked) {
    const itemId = item.id || `${item.type}-${item.target_code}-${item.created_at}`;
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (checked) {
        if (next.size >= 3) return prev; // max 3
        next.add(itemId);
      } else {
        next.delete(itemId);
      }
      return next;
    });
  }

  /**
   * 处理对比操作
   * @function handleCompare
   * @description 从筛选后的列表中提取选中的记录，至少 2 条时触发对比面板
   */
  function handleCompare() {
    const selected = filteredItems.filter((item) => {
      const itemId = item.id || `${item.type}-${item.target_code}-${item.created_at}`;
      return selectedIds.has(itemId);
    });
    if (selected.length >= 2) {
      setCompareItems(selected);
    }
  }

  // Clear selection when filter changes
  useEffect(() => {
    setSelectedIds(new Set());
    setCompareItems(null);
  }, [filter]);

  return (
    <div className={`analysis-history ${className}`}>
      {compareItems ? (
        <AnalysisComparison items={compareItems} onClose={() => setCompareItems(null)} />
      ) : null}

      <div className="analysis-history__header">
        <div className="analysis-history__title-row">
          <h3>{t('analysisHistory.title')}</h3>
          {!loading && filteredItems.length > 0 ? (
            <span className="analysis-history__count">{t('analysisHistory.resultCount', { count: filteredItems.length })}</span>
          ) : null}
        </div>
        <div className="analysis-history__filters">
          {FILTER_OPTIONS.map((opt) => (
            <button key={opt.value} type="button"
              className={`button button--sm ${filter === opt.value ? '' : 'button--secondary'}`}
              onClick={() => { setFilter(opt.value); setExpandedId(null); }}>
              {opt.label}
            </button>
          ))}
          {selectedIds.size > 0 ? (
            <button type="button" className="button button--sm"
              onClick={handleCompare} disabled={selectedIds.size < 2}>
              {t('analysisHistory.compareSelected')} ({selectedIds.size})
            </button>
          ) : null}
        </div>
      </div>

      <div className="analysis-history__search-row">
        <input
          type="text"
          className="analysis-history__search"
          placeholder={t('analysisHistory.searchPlaceholder')}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
        <div className="analysis-history__date-filters">
          {DATE_FILTER_OPTIONS.map((opt) => (
            <button key={opt.value} type="button"
              className={`button button--sm ${dateFilter === opt.value ? 'button--date-active' : 'button--secondary'}`}
              onClick={() => setDateFilter(opt.value)}>
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {error ? <ErrorWithRetry message={error} onRetry={() => loadHistory(filter)} retrying={loading} /> : null}

      {loading ? (
        <div className="analysis-history__loading">
          <div className="research-loading__skeleton">
            {[1, 2, 3].map((i) => <div key={i} className="research-loading__line" />)}
          </div>
        </div>
      ) : null}

      {!loading && filteredItems.length === 0 && !error ? (
        <div className="analysis-history__empty">
          <p className="empty-state">{t('analysisHistory.empty')}</p>
          <p className="analysis-history__empty-hint">{t('analysisHistory.emptyDescription')}</p>
        </div>
      ) : null}

      {!loading && filteredItems.length > 0 ? (
        <div className="analysis-history__list">
          {filteredItems.map((item) => {
            const itemId = item.id || `${item.type}-${item.target_code}-${item.created_at}`;
            return (
              <HistoryItem key={itemId}
                item={item} expanded={expandedId === (item.id || item.target_code)}
                onToggle={() => setExpandedId((prev) => (prev === (item.id || item.target_code) ? null : (item.id || item.target_code)))}
                selected={selectedIds.has(itemId)}
                onSelectChange={handleSelectChange}
                t={t} />
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
