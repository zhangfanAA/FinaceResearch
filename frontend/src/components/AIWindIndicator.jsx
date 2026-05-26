/**
 * @fileoverview AI 风向标组件 - 展示热门板块、基金推荐和市场情绪
 * @module components/AIWindIndicator
 * @description 调用 getAIWind API 获取 AI 风向标数据，包含三个展示区域：
 * - 热门板块：卡片列表，显示板块名、涨跌幅和原因
 * - 基金推荐：卡片列表，显示方向、理由、基金代码和风险等级
 * - 市场情绪：情绪标签和 SentimentMeter 组件
 * 支持 5 分钟自动刷新和手动强制刷新
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getAIWind } from '../api/client';
import ErrorWithRetry from './ErrorWithRetry';
import SentimentMeter from './SentimentMeter';
import SkeletonTable from './SkeletonTable';

/**
 * 格式化百分比显示（带正负号）
 * @function formatPercent
 * @param {number} value - 数值
 * @returns {string} 格式化后的百分比字符串
 */
function formatPercent(value) {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return '--';
  const sign = numeric > 0 ? '+' : '';
  return `${sign}${numeric.toFixed(2)}%`;
}

/**
 * 获取涨跌颜色基调
 * @function getChangeTone
 * @param {number} value - 数值
 * @returns {'up'|'down'|'neutral'} 正数返回 'up'，负数返回 'down'，零返回 'neutral'
 */
function getChangeTone(value) {
  const numeric = Number(value);
  if (Number.isNaN(numeric) || numeric === 0) return 'neutral';
  return numeric > 0 ? 'up' : 'down';
}

/**
 * 获取风险等级对应的 badge 样式
 * @function getRiskTone
 * @param {string} level - 风险等级
 * @returns {'good'|'warn'|'bad'} badge 色调
 */
function getRiskTone(level) {
  if (!level) return 'warn';
  const normalized = String(level).toLowerCase();
  if (normalized.includes('low') || normalized.includes('低')) return 'good';
  if (normalized.includes('high') || normalized.includes('高')) return 'bad';
  return 'warn';
}

/**
 * 获取风险等级的 i18n key
 * @function getRiskLabel
 * @param {string} level - 风险等级
 * @param {Function} t - 翻译函数
 * @returns {string} 翻译后的风险等级文本
 */
function getRiskLabel(level, t) {
  if (!level) return t('aiWind.riskMedium');
  const normalized = String(level).toLowerCase();
  if (normalized.includes('low') || normalized.includes('低')) return t('aiWind.riskLow');
  if (normalized.includes('high') || normalized.includes('高')) return t('aiWind.riskHigh');
  return t('aiWind.riskMedium');
}

/**
 * 骨架屏组件 - AI 风向标加载状态
 */
function AIWindSkeleton() {
  return (
    <div className="ai-wind-skeleton">
      <div className="ai-wind-skeleton__section">
        <div className="skeleton-table__bar" style={{ width: '120px', height: '18px', marginBottom: '14px' }} />
        <SkeletonTable rows={3} columns={3} />
      </div>
      <div className="ai-wind-skeleton__section">
        <div className="skeleton-table__bar" style={{ width: '120px', height: '18px', marginBottom: '14px' }} />
        <SkeletonTable rows={2} columns={4} />
      </div>
    </div>
  );
}

/**
 * AI 风向标组件
 *
 * @component AIWindIndicator
 * @description 展示 AI 风向标数据，包含热门板块、基金推荐和市场情绪三个区域。
 * 支持 5 分钟自动刷新和手动强制刷新。
 *
 * @returns {JSX.Element} AI 风向标面板
 */
export default function AIWindIndicator() {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [lastUpdated, setLastUpdated] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const intervalRef = useRef(null);

  /**
   * 加载 AI 风向标数据
   * @param {boolean} forceRefresh - 是否强制刷新
   */
  const loadData = useCallback(async (forceRefresh = false) => {
    if (forceRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError('');
    try {
      const result = await getAIWind(forceRefresh);
      setData(result);
      setLastUpdated(Date.now());
    } catch (err) {
      setError(err.message || t('aiWind.error'));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [t]);

  /* 初始加载 */
  useEffect(() => {
    loadData(false);
  }, [loadData]);

  /* 1 分钟自动刷新 */
  useEffect(() => {
    intervalRef.current = window.setInterval(() => {
      loadData(false);
    }, 60000);
    return () => {
      if (intervalRef.current) window.clearInterval(intervalRef.current);
    };
  }, [loadData]);

  /** 手动强制刷新 */
  const handleForceRefresh = useCallback(() => {
    loadData(true);
  }, [loadData]);

  /** 格式化最后更新时间 */
  const formattedTime = lastUpdated
    ? new Date(lastUpdated).toLocaleTimeString()
    : '--';

  /* 加载状态 */
  if (loading && !data) {
    return (
      <section className="subpanel ai-wind-indicator">
        <div className="subpanel__header">
          <h3>{t('aiWind.title')}</h3>
        </div>
        <AIWindSkeleton />
      </section>
    );
  }

  /* 错误状态 */
  if (error && !data) {
    return (
      <section className="subpanel ai-wind-indicator">
        <div className="subpanel__header">
          <h3>{t('aiWind.title')}</h3>
        </div>
        <ErrorWithRetry message={error} onRetry={handleForceRefresh} retrying={refreshing} />
      </section>
    );
  }

  /* 空数据状态 */
  if (!data) {
    return (
      <section className="subpanel ai-wind-indicator">
        <div className="subpanel__header">
          <h3>{t('aiWind.title')}</h3>
        </div>
        <p className="empty-state">{t('aiWind.noData')}</p>
      </section>
    );
  }

  const hotSectors = data.hot_sectors || data.hotSectors || [];
  const fundRecommendations = data.fund_recommendations || data.fundRecommendations || [];
  const marketSentiment = data.market_sentiment || data.marketSentiment || {};

  return (
    <section className="subpanel ai-wind-indicator">
      {/* Header with refresh controls */}
      <div className="subpanel__header">
        <h3>{t('aiWind.title')}</h3>
        <div className="ai-wind-indicator__controls">
          <span className="ai-wind-indicator__time">
            {t('aiWind.lastUpdate')}: {formattedTime}
          </span>
          <button
            type="button"
            className="button button--sm button--secondary"
            onClick={handleForceRefresh}
            disabled={refreshing}
          >
            {refreshing ? t('aiWind.refreshing') : t('aiWind.refresh')}
          </button>
        </div>
      </div>

      {/* Hot Sectors */}
      {hotSectors.length > 0 && (
        <div className="ai-wind-section">
          <h4 className="ai-wind-section__title">{t('aiWind.hotSectors')}</h4>
          <div className="ai-wind-card-grid">
            {hotSectors.map((sector, idx) => {
              const tone = getChangeTone(sector.change_pct ?? sector.changePct);
              return (
                <article key={idx} className="ai-wind-card">
                  <div className="ai-wind-card__header">
                    <span className="ai-wind-card__name">
                      {sector.sector_name || sector.sectorName || '--'}
                    </span>
                    <span className={`ai-wind-card__change ai-wind-card__change--${tone}`}>
                      {formatPercent(sector.change_pct ?? sector.changePct)}
                    </span>
                  </div>
                  {(sector.reason || sector.description) && (
                    <p className="ai-wind-card__reason">
                      {sector.reason || sector.description}
                    </p>
                  )}
                </article>
              );
            })}
          </div>
        </div>
      )}

      {/* Fund Recommendations */}
      {fundRecommendations.length > 0 && (
        <div className="ai-wind-section">
          <h4 className="ai-wind-section__title">{t('aiWind.fundRecommendations')}</h4>
          <div className="ai-wind-card-grid">
            {fundRecommendations.map((rec, idx) => (
              <article key={idx} className="ai-wind-card ai-wind-card--recommendation">
                <div className="ai-wind-card__header">
                  <span className="ai-wind-card__direction">
                    {rec.direction || '--'}
                  </span>
                  <span className={`badge badge--${getRiskTone(rec.risk_level || rec.riskLevel)}`}>
                    {getRiskLabel(rec.risk_level || rec.riskLevel, t)}
                  </span>
                </div>
                {(rec.rationale || rec.reason) && (
                  <p className="ai-wind-card__reason">
                    {rec.rationale || rec.reason}
                  </p>
                )}
                {(rec.fund_codes || rec.fundCodes || []).length > 0 && (
                  <div className="ai-wind-card__codes">
                    <span className="ai-wind-card__codes-label">{t('aiWind.fundCodes')}:</span>
                    <div className="ai-wind-card__codes-list">
                      {(rec.fund_codes || rec.fundCodes || []).map((code, i) => (
                        <code key={i} className="ai-wind-card__code">{code}</code>
                      ))}
                    </div>
                  </div>
                )}
              </article>
            ))}
          </div>
        </div>
      )}

      {/* Market Sentiment */}
      {(marketSentiment.score != null || marketSentiment.label) && (
        <div className="ai-wind-section">
          <h4 className="ai-wind-section__title">{t('aiWind.marketSentiment')}</h4>
          <SentimentMeter
            score={marketSentiment.score ?? 0}
            title={t('aiWind.sentimentLabel')}
            label={marketSentiment.label || marketSentiment.description || ''}
            badge={marketSentiment.label || ''}
            badgeTone={
              marketSentiment.score >= 0.5 ? 'good' :
              marketSentiment.score <= -0.5 ? 'bad' : 'warn'
            }
          />
        </div>
      )}

      {/* Auto-refresh hint */}
      <p className="ai-wind-indicator__hint">{t('aiWind.autoRefresh')}</p>
    </section>
  );
}
