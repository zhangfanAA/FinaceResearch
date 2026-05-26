/**
 * @fileoverview 趋势图数据容器 - 自动获取历史数据并渲染 TrendChart
 * @module components/TrendChartWrapper
 * @description 封装数据获取 + 周期切换 + 加载/错误状态的容器组件
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getSectorHistory, getIndexHistory, getFundNavHistory } from '../api/client';
import TrendChart from './TrendChart';

const PERIOD_OPTIONS = [
  { label: '30天', days: 30 },
  { label: '60天', days: 60 },
  { label: '90天', days: 90 },
];

/**
 * 板块趋势图容器
 *
 * @param {Object} props
 * @param {string} props.sectorName - 板块名称
 * @param {string} [props.sectorType='industry'] - 板块类型
 * @param {number} [props.height=240] - 图表高度
 * @param {boolean} [props.showVolume=false] - 是否显示成交量
 * @returns {JSX.Element}
 */
export function SectorTrendChart({ sectorName, sectorType = 'industry', height = 240, showVolume = true }) {
  const { t } = useTranslation();
  const [days, setDays] = useState(60);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    if (!sectorName) return;
    setLoading(true);
    setError(null);
    try {
      const result = await getSectorHistory(sectorName, sectorType, days);
      setData(result?.data || []);
    } catch (err) {
      setError(err.message);
      setData([]);
    } finally {
      setLoading(false);
    }
  }, [sectorName, sectorType, days]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return (
    <div className="trend-chart-wrapper">
      <div className="trend-chart-wrapper__header">
        <span className="trend-chart-wrapper__title">{t('common.trend', '走势')}</span>
        <div className="trend-chart-wrapper__period-toggle">
          {PERIOD_OPTIONS.map((opt) => (
            <button
              key={opt.days}
              type="button"
              className={`trend-chart-wrapper__period-btn ${days === opt.days ? 'trend-chart-wrapper__period-btn--active' : ''}`}
              onClick={() => setDays(opt.days)}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>
      {loading && <div className="skeleton-table__bar" style={{ width: '100%', height: `${height}px` }} />}
      {error && !loading && <div className="inline-alert inline-alert--warning" style={{ fontSize: '0.8rem' }}>{error}</div>}
      {!loading && data && (
        <TrendChart data={data} valueKey="close" valueLabel="收盘" showVolume={showVolume} height={height} />
      )}
    </div>
  );
}

/**
 * 指数趋势图容器
 *
 * @param {Object} props
 * @param {string} props.indexCode - 指数代码
 * @param {string} [props.indexName] - 指数名称（显示用）
 * @param {number} [props.height=240] - 图表高度
 * @param {boolean} [props.showVolume=true] - 是否显示成交量
 * @returns {JSX.Element}
 */
export function IndexTrendChart({ indexCode, indexName, height = 240, showVolume = true }) {
  const { t } = useTranslation();
  const [days, setDays] = useState(60);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    if (!indexCode) return;
    setLoading(true);
    setError(null);
    try {
      const result = await getIndexHistory(indexCode, days);
      setData(result?.data || []);
    } catch (err) {
      setError(err.message);
      setData([]);
    } finally {
      setLoading(false);
    }
  }, [indexCode, days]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return (
    <div className="trend-chart-wrapper">
      <div className="trend-chart-wrapper__header">
        <span className="trend-chart-wrapper__title">
          {indexName || indexCode} {t('common.trend', '走势')}
        </span>
        <div className="trend-chart-wrapper__period-toggle">
          {PERIOD_OPTIONS.map((opt) => (
            <button
              key={opt.days}
              type="button"
              className={`trend-chart-wrapper__period-btn ${days === opt.days ? 'trend-chart-wrapper__period-btn--active' : ''}`}
              onClick={() => setDays(opt.days)}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>
      {loading && <div className="skeleton-table__bar" style={{ width: '100%', height: `${height}px` }} />}
      {error && !loading && <div className="inline-alert inline-alert--warning" style={{ fontSize: '0.8rem' }}>{error}</div>}
      {!loading && data && (
        <TrendChart data={data} valueKey="close" valueLabel="收盘" showVolume={showVolume} height={height} />
      )}
    </div>
  );
}

/**
 * 基金净值趋势图容器
 *
 * @param {Object} props
 * @param {string} props.fundCode - 基金代码
 * @param {number} [props.height=240] - 图表高度
 * @returns {JSX.Element}
 */
export function FundNavTrendChart({ fundCode, height = 240 }) {
  const { t } = useTranslation();
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const PERIOD_OPTIONS_FUND = [
    { label: '30天', days: 30 },
    { label: '60天', days: 60 },
    { label: '90天', days: 90 },
  ];

  const fetchData = useCallback(async () => {
    if (!fundCode) return;
    setLoading(true);
    setError(null);
    try {
      const result = await getFundNavHistory(fundCode, days);
      setData(result?.data || []);
    } catch (err) {
      setError(err.message);
      setData([]);
    } finally {
      setLoading(false);
    }
  }, [fundCode, days]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return (
    <div className="trend-chart-wrapper">
      <div className="trend-chart-wrapper__header">
        <span className="trend-chart-wrapper__title">{t('common.navTrend', '净值走势')}</span>
        <div className="trend-chart-wrapper__period-toggle">
          {PERIOD_OPTIONS_FUND.map((opt) => (
            <button
              key={opt.days}
              type="button"
              className={`trend-chart-wrapper__period-btn ${days === opt.days ? 'trend-chart-wrapper__period-btn--active' : ''}`}
              onClick={() => setDays(opt.days)}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>
      {loading && <div className="skeleton-table__bar" style={{ width: '100%', height: `${height}px` }} />}
      {error && !loading && <div className="inline-alert inline-alert--warning" style={{ fontSize: '0.8rem' }}>{error}</div>}
      {!loading && data && (
        <TrendChart data={data} valueKey="nav" valueLabel="净值" valueSuffix="" height={height} />
      )}
    </div>
  );
}
