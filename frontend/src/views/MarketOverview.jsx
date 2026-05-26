/**
 * @fileoverview 市场总览视图 - 展示 VIX 指数、主要指数和板块涨跌
 * @module views/MarketOverview
 * @description 市场总览页面，包含以下功能：
 * - VIX 恐慌指数仪表盘（SVG 可视化）
 * - 主要市场指数卡片（上证、深证、沪深 300、中证 500）
 * - 市场开闭市状态检测（基于北京时间）
 * - 涨跌板块条形图排名
 * - 市场摘要统计（涨跌板块数、平均涨跌幅）
 * - 自动刷新和数据新鲜度追踪
 */

import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getMarketOverview } from '../api/client';
import AutoRefreshControls from '../components/AutoRefreshControls';
import DataSourceBadge from '../components/DataSourceBadge';
import DataFreshnessBadge from '../components/DataFreshnessBadge';
import ErrorWithRetry from '../components/ErrorWithRetry';
import SkeletonTable from '../components/SkeletonTable';
import { IndexTrendChart } from '../components/TrendChartWrapper';
import useStaleData from '../hooks/useStaleData';

/* ---------- helpers ---------- */

/**
 * 格式化百分比显示（带正负号）
 * @function formatPercent
 * @param {number} value - 数值
 * @returns {string} 格式化后的百分比字符串（如 '+2.35%'），无效值返回 '--'
 */
function formatPercent(value) {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return '--';
  const sign = numeric > 0 ? '+' : '';
  return `${sign}${numeric.toFixed(2)}%`;
}

/**
 * 格式化数字显示（带千分位分隔符）
 * @function formatNumber
 * @param {*} value - 要格式化的值
 * @param {number} [fractionDigits=2] - 保留的小数位数
 * @returns {string} 格式化后的数字字符串，无效值返回 '--'
 */
function formatNumber(value, fractionDigits = 2) {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return '--';
  return numeric.toLocaleString(undefined, {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  });
}

/**
 * 格式化大数字为紧凑显示（万/亿）
 * @function formatCompact
 * @param {number} value - 数值
 * @returns {string} 紧凑格式字符串（如 '1.23亿'），无效值返回 '--'
 */
function formatCompact(value) {
  const n = Number(value);
  if (Number.isNaN(n)) return '--';
  const abs = Math.abs(n);
  const sign = n < 0 ? '-' : '';
  if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${sign}${(abs / 1e4).toFixed(2)}万`;
  return n.toLocaleString();
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
 * 格式化日期时间显示
 * @function formatDateTime
 * @param {string|null} value - 日期时间字符串
 * @returns {string} 本地化的日期时间字符串，无效值返回 '--'
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
 * 获取当前市场开闭市状态
 * @function getMarketStatus
 * @returns {'open'|'closed'|'unknown'} 市场状态
 * @description 基于北京时间判断，工作日 9:30-11:30 和 13:00-15:00 为开市
 */
function getMarketStatus() {
  try {
    const now = new Date();
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: 'Asia/Shanghai',
      hour: 'numeric',
      minute: 'numeric',
      hour12: false,
      weekday: 'short',
    }).formatToParts(now);
    const weekday = parts.find((p) => p.type === 'weekday')?.value;
    const hour = parseInt(parts.find((p) => p.type === 'hour')?.value || '0', 10);
    const minute = parseInt(parts.find((p) => p.type === 'minute')?.value || '0', 10);
    const timeMin = hour * 60 + minute;
    if (weekday === 'Sat' || weekday === 'Sun') return 'closed';
    if ((timeMin >= 570 && timeMin <= 690) || (timeMin >= 780 && timeMin <= 900)) return 'open';
    return 'closed';
  } catch {
    return 'unknown';
  }
}

/* ---------- SVG VIX Gauge ---------- */

/**
 * VIX 恐慌指数仪表盘组件
 *
 * @component VixGauge
 * @description 以 SVG 半圆仪表盘形式展示 VIX 指数，包含：
 * - 四个区域弧线（低/正常/中/高恐慌）
 * - 指针指向当前值
 * - 颜色编码（绿色 < 25，黄色 25-30，红色 > 30）
 *
 * @param {Object} props
 * @param {number} props.value - VIX 指数值（0-50）
 * @returns {JSX.Element} SVG 仪表盘组件
 */
function VixGauge({ value }) {
  const { t } = useTranslation();
  const clamped = Math.max(0, Math.min(50, value || 0));
  const position = clamped / 50;

  const cx = 100;
  const cy = 90;
  const r = 65;
  const sw = 14;

  function pt(frac) {
    const a = Math.PI * (1 - frac);
    return { x: cx + r * Math.cos(a), y: cy - r * Math.sin(a) };
  }

  function describeArc(sf, ef) {
    const s = pt(sf);
    const e = pt(ef);
    const large = (ef - sf) * Math.PI > Math.PI ? 1 : 0;
    return `M ${s.x.toFixed(1)} ${s.y.toFixed(1)} A ${r} ${r} 0 ${large} 0 ${e.x.toFixed(1)} ${e.y.toFixed(1)}`;
  }

  let zoneLabel;
  let zoneColor;
  if (clamped < 15) {
    zoneLabel = t('marketOverview.vix.low');
    zoneColor = '#22c55e';
  } else if (clamped < 25) {
    zoneLabel = t('marketOverview.vix.normal');
    zoneColor = '#22c55e';
  } else if (clamped < 30) {
    zoneLabel = t('marketOverview.vix.medium');
    zoneColor = '#f59e0b';
  } else {
    zoneLabel = t('marketOverview.vix.high');
    zoneColor = '#ef4444';
  }

  const na = Math.PI * (1 - position);
  const nl = r - 15;
  const nx = cx + nl * Math.cos(na);
  const ny = cy - nl * Math.sin(na);

  return (
    <article className="vix-gauge">
      <svg
        viewBox="0 0 200 115"
        className="vix-gauge__svg"
        role="img"
        aria-label={`VIX: ${value}`}
      >
        {/* background zone arcs */}
        <path d={describeArc(0, 0.3)} fill="none" stroke="#22c55e" strokeWidth={sw} opacity="0.15" strokeLinecap="round" />
        <path d={describeArc(0.3, 0.5)} fill="none" stroke="#22c55e" strokeWidth={sw} opacity="0.15" />
        <path d={describeArc(0.5, 0.6)} fill="none" stroke="#f59e0b" strokeWidth={sw} opacity="0.15" />
        <path d={describeArc(0.6, 1)} fill="none" stroke="#ef4444" strokeWidth={sw} opacity="0.15" strokeLinecap="round" />

        {/* active filled arc */}
        {position > 0.005 && (
          <path d={describeArc(0, position)} fill="none" stroke={zoneColor} strokeWidth={sw} strokeLinecap="round" />
        )}

        {/* needle */}
        <line x1={cx} y1={cy} x2={nx} y2={ny} stroke="#eef5ff" strokeWidth="2.5" strokeLinecap="round" />
        <circle cx={cx} cy={cy} r="4.5" fill="#eef5ff" />
        <circle cx={cx} cy={cy} r="2.5" fill={zoneColor} />

        {/* value */}
        <text x={cx} y={cy - 12} textAnchor="middle" fill="#eef5ff" fontSize="22" fontWeight="700">
          {formatNumber(value, 1)}
        </text>

        {/* zone label */}
        <text x={cx} y={cy + 6} textAnchor="middle" fill={zoneColor} fontSize="10.5" fontWeight="600">
          {zoneLabel}
        </text>

        {/* end labels */}
        <text x={cx - r - 2} y={cy + 16} textAnchor="end" fill="#4a6080" fontSize="8.5">0</text>
        <text x={cx + r + 2} y={cy + 16} textAnchor="start" fill="#4a6080" fontSize="8.5">50</text>
      </svg>
      <div className="vix-gauge__label">{t('marketOverview.vix.title')}</div>
    </article>
  );
}

/* ---------- Market Summary ---------- */

/**
 * 市场摘要组件
 *
 * @component MarketSummary
 * @description 展示市场整体概况，包括涨跌板块数、平均涨跌幅和开闭市状态
 *
 * @param {Object} props
 * @param {number} props.risingCount - 上涨板块数
 * @param {number} props.fallingCount - 下跌板块数
 * @param {number} props.avgChange - 平均涨跌幅
 * @param {string} props.lastUpdate - 最后更新时间
 * @returns {JSX.Element} 市场摘要卡片
 */
function MarketSummary({ risingCount, fallingCount, avgChange, lastUpdate }) {
  const { t } = useTranslation();
  const status = getMarketStatus();
  const statusLabel =
    status === 'open'
      ? t('marketOverview.marketSummary.open')
      : t('marketOverview.marketSummary.closed');
  const avgTone = getChangeTone(avgChange);

  return (
    <div className="market-summary">
      <div className="market-summary__header">
        <h3 className="market-summary__title">{t('marketOverview.marketSummary.title')}</h3>
        <span className={`market-summary__status market-summary__status--${status}`}>
          <span className="market-summary__status-dot" />
          {statusLabel}
        </span>
      </div>
      <div className="market-summary__grid">
        <div className="market-summary__stat">
          <span className="market-summary__stat-value market-summary__stat-value--up">{risingCount}</span>
          <span className="market-summary__stat-label">{t('marketOverview.marketSummary.risingSectors')}</span>
        </div>
        <div className="market-summary__stat">
          <span className="market-summary__stat-value market-summary__stat-value--down">{fallingCount}</span>
          <span className="market-summary__stat-label">{t('marketOverview.marketSummary.fallingSectors')}</span>
        </div>
        <div className="market-summary__stat">
          <span className={`market-summary__stat-value market-summary__stat-value--${avgTone}`}>
            {formatPercent(avgChange)}
          </span>
          <span className="market-summary__stat-label">{t('marketOverview.marketSummary.avgChange')}</span>
        </div>
        <div className="market-summary__stat">
          <span className="market-summary__stat-value">{formatDateTime(lastUpdate)}</span>
          <span className="market-summary__stat-label">{t('marketOverview.marketSummary.lastUpdate')}</span>
        </div>
      </div>
    </div>
  );
}

/* ---------- Index Card ---------- */

/**
 * 市场指数卡片组件
 *
 * @component IndexCard
 * @description 展示单个市场指数的实时行情，包括价格、涨跌幅、涨跌条形图和成交额
 *
 * @param {Object} props
 * @param {string} props.name - 指数名称
 * @param {Object} props.quote - 行情数据对象（current_price, change_pct, change_amount, amount, volume）
 * @returns {JSX.Element} 指数卡片 JSX
 */
function IndexCard({ name, quote, selected, onClick }) {
  const { t } = useTranslation();
  const tone = getChangeTone(quote?.change_pct);
  const changeAmt = quote?.change_amount;
  const hasAmount = quote?.amount != null;
  const hasVolume = quote?.volume != null;

  return (
    <article
      className={`market-index-card ${selected ? 'market-index-card--selected' : ''}`}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onClick?.(); }}
    >
      <div className="market-index-card__name">{name}</div>
      <div className="market-index-card__price">{formatNumber(quote?.current_price, 2)}</div>
      <div className={`market-index-card__change market-index-card__change--${tone}`}>
        <span className={`market-index-card__arrow market-index-card__arrow--${tone}`} aria-hidden="true">
          {tone === 'up' ? '\u25B2' : tone === 'down' ? '\u25BC' : '\u25C6'}
        </span>
        {changeAmt != null ? (
          <span>{formatNumber(changeAmt, 2)} ({formatPercent(quote?.change_pct)})</span>
        ) : (
          <span>{formatPercent(quote?.change_pct)}</span>
        )}
      </div>
      <div className={`market-index-card__bar market-index-card__bar--${tone}`}>
        <div
          className="market-index-card__bar-fill"
          style={{ width: `${Math.min(100, Math.abs(Number(quote?.change_pct) || 0) * 10)}%` }}
        />
      </div>
      {(hasAmount || hasVolume) && (
        <div className="market-index-card__meta">
          {hasAmount && (
            <span>{t('marketOverview.indices.amount')}: {formatCompact(quote.amount)}</span>
          )}
          {!hasAmount && hasVolume && (
            <span>{t('marketOverview.indices.volume')}: {formatCompact(quote.volume)}</span>
          )}
        </div>
      )}
    </article>
  );
}

/* ---------- Sector Bar ---------- */

/**
 * 板块涨跌条形图组件
 *
 * @component SectorBar
 * @description 以水平条形图展示板块涨跌幅，支持点击跳转到板块详情
 *
 * @param {Object} props
 * @param {Object} props.sector - 板块数据对象
 * @param {number} props.maxChange - 最大涨跌幅（用于计算条形图比例）
 * @param {'up'|'down'} props.tone - 显示基调
 * @param {Function} props.onClick - 点击回调
 * @returns {JSX.Element} 板块条形图 JSX
 */
function SectorBar({ sector, maxChange, tone, onClick }) {
  const { t } = useTranslation();
  const change = Number(sector.change_pct || 0);
  const barWidth = maxChange > 0
    ? Math.max(2, Math.min(100, (Math.abs(change) / maxChange) * 100))
    : 0;

  function handleKeyDown(e) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onClick?.();
    }
  }

  return (
    <div
      className="sector-bar"
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={handleKeyDown}
    >
      <div className="sector-bar__header">
        <span className="sector-bar__name">{sector.sector_name}</span>
        <span className={`sector-bar__change sector-bar__change--${tone}`}>
          {formatPercent(change)}
        </span>
      </div>
      <div className="sector-bar__track">
        <div
          className={`sector-bar__fill sector-bar__fill--${tone}`}
          style={{ width: `${barWidth}%` }}
        />
      </div>
      {sector.leading_stock ? (
        <div className="sector-bar__leading">
          {t('marketOverview.sectors.leadingStock')}: {sector.leading_stock}
        </div>
      ) : null}
    </div>
  );
}

/* ---------- Skeleton ---------- */

/**
 * 市场总览加载骨架屏组件
 *
 * @component MarketOverviewSkeleton
 * @description 数据加载时显示的占位骨架屏，模拟市场摘要、指数卡片和板块表格的布局
 * @returns {JSX.Element} 骨架屏 JSX
 */
function MarketOverviewSkeleton() {
  return (
    <div className="market-skeleton">
      <div className="market-skeleton__summary">
        <div className="skeleton-table__bar" style={{ width: '100%', height: '60px' }} />
      </div>
      <div className="market-skeleton__indices">
        <div className="market-skeleton__vix-card">
          <div className="skeleton-table__bar" style={{ width: '80%', height: '80px', margin: '0 auto 8px' }} />
          <div className="skeleton-table__bar" style={{ width: '50%', height: '10px', margin: '0 auto' }} />
        </div>
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="market-skeleton__index-card">
            <div className="skeleton-table__bar" style={{ width: '50%', height: '10px', margin: '0 auto 8px' }} />
            <div className="skeleton-table__bar" style={{ width: '70%', height: '18px', margin: '0 auto 8px' }} />
            <div className="skeleton-table__bar" style={{ width: '40%', height: '10px', margin: '0 auto' }} />
          </div>
        ))}
      </div>
      <SkeletonTable rows={3} columns={3} />
    </div>
  );
}

/* ---------- Main Component ---------- */

/**
 * 市场总览视图
 *
 * @component MarketOverview
 * @description 市场总览的主视图页面，整合以下功能模块：
 * - VIX 恐慌指数仪表盘
 * - 主要市场指数实时行情卡片
 * - 涨跌板块条形图排名
 * - 市场摘要统计
 * - 数据来源标识（模拟/真实）
 * - 自动刷新（30 秒间隔）和数据新鲜度追踪
 *
 * @param {Object} props
 * @param {Function} [props.onNavigateTab] - 标签页导航回调，用于从板块条形图跳转到板块详情
 * @returns {JSX.Element} 市场总览页面
 *
 * @example
 * // 在 App.jsx 中懒加载使用
 * <Suspense fallback={<SkeletonTable />}>
 *   <MarketOverview onNavigateTab={setActiveTab} />
 * </Suspense>
 */
export default function MarketOverview({ onNavigateTab }) {
  const { t } = useTranslation();
  const [selectedIndex, setSelectedIndex] = useState('000001');

  const INDEX_NAME_MAP = useMemo(
    () => ({
      '000001': t('marketOverview.indexNames.000001'),
      '399001': t('marketOverview.indexNames.399001'),
      '000300': t('marketOverview.indexNames.000300'),
      '000905': t('marketOverview.indexNames.000905'),
    }),
    [t],
  );

  // 使用 useStaleData 管理市场总览数据，支持分时刷新
  const {
    data: overview,
    loading,
    refreshing,
    error,
    lastSuccessfulFetch: lastFetchedAt,
    refresh: refreshOverview,
    autoRefreshEnabled,
    toggleAutoRefresh,
    secondsUntilRefresh,
    freshness,
    serverStale,
    cachedAt,
  } = useStaleData(
    useCallback(async () => {
      return await getMarketOverview();
    }, []),
    { intervalMs: 60000, enabled: true, staggerMs: 0, freshThreshold: 60, staleThreshold: 180 }
  );

  const vix = overview?.vix;
  const majorIndices = overview?.major_indices || [];
  const topSectors = overview?.top_sectors || [];
  const bottomSectors = overview?.bottom_sectors || [];
  const fetchedAt = overview?.fetched_at;

  const allSectors = useMemo(
    () => [...topSectors, ...bottomSectors],
    [topSectors, bottomSectors],
  );
  const risingCount = useMemo(
    () => allSectors.filter((s) => Number(s.change_pct) > 0).length,
    [allSectors],
  );
  const fallingCount = useMemo(
    () => allSectors.filter((s) => Number(s.change_pct) < 0).length,
    [allSectors],
  );
  const avgChange = useMemo(() => {
    if (allSectors.length === 0) return 0;
    return allSectors.reduce((s, sec) => s + Number(sec.change_pct || 0), 0) / allSectors.length;
  }, [allSectors]);
  const maxAbsChange = useMemo(() => {
    const vals = allSectors.map((s) => Math.abs(Number(s.change_pct || 0)));
    return vals.length > 0 ? Math.max(...vals) : 1;
  }, [allSectors]);

  /**
   * 处理板块条形图点击
   * @function handleSectorClick
   * @description 导航到股票板块分析标签页
   */
  function handleSectorClick() {
    onNavigateTab?.('stock-sector');
  }

  return (
    <section className="panel market-overview-panel">
      <div className="section-header">
        <div>
          <h2>{t('marketOverview.title')}</h2>
          <p>{t('marketOverview.subtitle')}</p>
        </div>
        <div className="section-header__actions">
          <DataSourceBadge />
          {overview?.data_source && overview.data_source !== 'none' ? (
            <span className="real-data-badge">
              <span className="real-data-badge__dot" />
              {overview.data_source}
            </span>
          ) : null}
          <DataFreshnessBadge level={freshness.level} label={freshness.label} serverStale={serverStale} cachedAt={cachedAt} />
          <AutoRefreshControls
            enabled={autoRefreshEnabled}
            onToggle={toggleAutoRefresh}
            secondsUntilRefresh={secondsUntilRefresh}
          />
          <button
            type="button"
            className="button button--secondary"
            onClick={refreshOverview}
            disabled={loading || refreshing}
          >
            {(loading || refreshing) ? t('marketOverview.refreshing') : t('marketOverview.refresh')}
          </button>
        </div>
      </div>

      {error && !overview ? <ErrorWithRetry message={error} onRetry={refreshOverview} retrying={loading || refreshing} /> : null}
      {loading && !overview ? <MarketOverviewSkeleton /> : null}
      {error && overview ? <div className="inline-alert inline-alert--warning">{error}</div> : null}

      {overview ? (
        <>
          {/* Market Summary */}
          <MarketSummary
            risingCount={risingCount}
            fallingCount={fallingCount}
            avgChange={avgChange}
            lastUpdate={fetchedAt}
          />

          {/* VIX Gauge + Major Indices */}
          <div className="market-indices-section">
            {vix != null ? <VixGauge value={vix} /> : null}
            <div className="market-indices-grid">
              {majorIndices.map((idx) => (
                <IndexCard
                  key={idx.stock_code}
                  name={INDEX_NAME_MAP[idx.stock_code] || idx.stock_name || idx.stock_code}
                  quote={idx}
                  selected={idx.stock_code === selectedIndex}
                  onClick={() => setSelectedIndex(idx.stock_code)}
                />
              ))}
            </div>
          </div>

          {/* Index Trend Chart */}
          {selectedIndex && (
            <div className="subpanel">
              <IndexTrendChart
                indexCode={selectedIndex}
                indexName={INDEX_NAME_MAP[selectedIndex] || selectedIndex}
                height={260}
                showVolume
              />
            </div>
          )}

          {/* Top Sectors */}
          {topSectors.length > 0 ? (
            <div className="sector-bar-list">
              <h3 className="sector-bar-list__title sector-bar-list__title--up">
                {t('marketOverview.topSectors')}
              </h3>
              <div className="sector-bar-list__items">
                {topSectors.map((s) => (
                  <SectorBar
                    key={s.sector_code}
                    sector={s}
                    maxChange={maxAbsChange}
                    tone="up"
                    onClick={handleSectorClick}
                  />
                ))}
              </div>
            </div>
          ) : null}

          {/* Bottom Sectors */}
          {bottomSectors.length > 0 ? (
            <div className="sector-bar-list">
              <h3 className="sector-bar-list__title sector-bar-list__title--down">
                {t('marketOverview.bottomSectors')}
              </h3>
              <div className="sector-bar-list__items">
                {bottomSectors.map((s) => (
                  <SectorBar
                    key={s.sector_code}
                    sector={s}
                    maxChange={maxAbsChange}
                    tone="down"
                    onClick={handleSectorClick}
                  />
                ))}
              </div>
            </div>
          ) : null}

          {fetchedAt ? (
            <div className="market-timestamp">
              {t('marketOverview.timestamp', { time: formatDateTime(fetchedAt) })}
            </div>
          ) : null}
        </>
      ) : null}

      {!loading && !error && !overview ? (
        <div className="subpanel empty-state">{t('marketOverview.empty')}</div>
      ) : null}
    </section>
  );
}
