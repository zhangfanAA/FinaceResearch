/**
 * @fileoverview 股票板块分析视图 - 展示板块排名、个股查询和 AI 分析
 * @module views/StockSector
 * @description 股票板块分析页面，包含以下功能：
 * - 行业/概念板块涨跌排名表格
 * - 快速个股实时行情查询
 * - 板块详情面板（含龙头股）
 * - AI 趋势分析（情感分数、关键因素、风险提示）
 * - 技术指标可视化（RSI、MACD、KDJ、布林带）
 * - 自动刷新和数据新鲜度追踪
 * - 分析历史记录查看
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getStockSectors, getStockRealtime, analyzeStockSector } from '../api/client';
import AnalysisHistory from '../components/AnalysisHistory';
import AnalysisLoadingState from '../components/AnalysisLoadingState';
import AutoRefreshControls from '../components/AutoRefreshControls';
import ExportButton from '../components/ExportButton';
import DataFreshnessBadge from '../components/DataFreshnessBadge';
import ErrorWithRetry from '../components/ErrorWithRetry';
import SearchAutocomplete from '../components/SearchAutocomplete';
import SentimentMeter from '../components/SentimentMeter';
import SkeletonTable from '../components/SkeletonTable';
import TechnicalChart from '../components/TechnicalChart';
import WatchlistManager from '../components/WatchlistManager';
import useAutoRefresh from '../hooks/useAutoRefresh';
import useDataFreshness from '../hooks/useDataFreshness';
import useToast from '../hooks/useToast';

const COMMON_STOCK_CODES = [
  { code: '600519', label: '贵州茅台' },
  { code: '000001', label: '平安银行' },
  { code: '601318', label: '中国平安' },
  { code: '600036', label: '招商银行' },
  { code: '000858', label: '五粮液' },
  { code: '601398', label: '工商银行' },
  { code: '600276', label: '恒瑞医药' },
  { code: '000333', label: '美的集团' },
  { code: '600900', label: '长江电力' },
  { code: '601012', label: '隆基绿能' },
  { code: '300750', label: '宁德时代' },
  { code: '002594', label: '比亚迪' },
  { code: '600887', label: '伊利股份' },
  { code: '601888', label: '中国中免' },
  { code: '000568', label: '泸州老窖' },
];

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
 * 涨跌幅迷你条形图组件
 *
 * @component ChangeBar
 * @description 以水平条形图可视化涨跌幅百分比（最大 10%）
 *
 * @param {Object} props
 * @param {number} props.value - 涨跌幅百分比值
 * @returns {JSX.Element|null} 条形图 JSX，无效值返回 null
 */
function ChangeBar({ value }) {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return null;
  const abs = Math.min(Math.abs(numeric), 10);
  const width = (abs / 10) * 100;
  const tone = getChangeTone(numeric);
  return (
    <div className="change-bar">
      <div className={`change-bar__fill change-bar__fill--${tone}`} style={{ width: `${width}%` }} />
    </div>
  );
}

/**
 * 快速个股查询组件
 *
 * @component QuickStockLookup
 * @description 提供股票代码输入和实时行情查询功能，显示价格卡片并支持触发 AI 分析
 *
 * @param {Object} props
 * @param {Function} props.onAnalyze - 触发分析的回调，参数为股票代码
 * @param {boolean} props.disabled - 是否禁用（分析进行中）
 * @returns {JSX.Element} 快速查询界面
 */
function QuickStockLookup({ onAnalyze, disabled }) {
  const { t } = useTranslation();
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [stockData, setStockData] = useState(null);
  const { showToast } = useToast();

  /**
   * 处理股票搜索
   * @async
   * @function handleSearch
   * @description 调用实时行情 API 获取股票数据并显示价格卡片
   */
  async function handleSearch() {
    const trimmed = code.trim();
    if (!trimmed) return;
    setLoading(true);
    setStockData(null);
    try {
      const data = await getStockRealtime([trimmed]);
      if (Array.isArray(data) && data.length > 0) {
        setStockData(data[0]);
      } else {
        showToast(t('common.empty'), 'warning');
      }
    } catch (err) {
      showToast(err.message || t('common.error'), 'error');
    } finally {
      setLoading(false);
    }
  }

  /**
   * 处理键盘事件
   * @function handleKeyDown
   * @param {KeyboardEvent} e - 键盘事件
   * @description 按下回车键时触发搜索
   */
  function handleKeyDown(e) {
    if (e.key === 'Enter') handleSearch();
  }

  /**
   * 处理分析按钮点击
   * @function handleAnalyze
   * @description 将当前查询的股票代码传递给分析回调
   */
  function handleAnalyze() {
    if (stockData?.code && onAnalyze) {
      onAnalyze(stockData.code);
    }
  }

  return (
    <div className="quick-lookup">
      <div className="quick-lookup__header">
        <h3>{t('stockSector.quickLookup.title')}</h3>
      </div>
      <div className="quick-lookup__row">
        <input
          type="text"
          className="quick-lookup__input"
          placeholder={t('stockSector.quickLookup.placeholder')}
          value={code}
          onChange={(e) => setCode(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading || disabled}
        />
        <button
          type="button"
          className="button button--sm"
          onClick={handleSearch}
          disabled={loading || disabled || !code.trim()}
        >
          {loading ? t('stockSector.quickLookup.searching') : t('stockSector.quickLookup.search')}
        </button>
      </div>
      {stockData && (
        <div className="stock-card">
          <div className="stock-card__header">
            <span className="stock-card__code">{stockData.code}</span>
            <span className="stock-card__name">{stockData.name || '--'}</span>
          </div>
          <div className="stock-card__body">
            <div className="stock-card__price-row">
              <span className={`stock-card__price stock-card__price--${getChangeTone(stockData.change_pct)}`}>
                {stockData.price != null ? Number(stockData.price).toFixed(2) : '--'}
              </span>
              <span className={`stock-card__change stock-card__change--${getChangeTone(stockData.change_pct)}`}>
                {formatPercent(stockData.change_pct)}
              </span>
            </div>
            <div className="stock-card__grid">
              <div className="stock-card__field">
                <span className="stock-card__label">{t('stockSector.stockCard.open')}</span>
                <span className="stock-card__value">{stockData.open != null ? Number(stockData.open).toFixed(2) : '--'}</span>
              </div>
              <div className="stock-card__field">
                <span className="stock-card__label">{t('stockSector.stockCard.high')}</span>
                <span className="stock-card__value">{stockData.high != null ? Number(stockData.high).toFixed(2) : '--'}</span>
              </div>
              <div className="stock-card__field">
                <span className="stock-card__label">{t('stockSector.stockCard.low')}</span>
                <span className="stock-card__value">{stockData.low != null ? Number(stockData.low).toFixed(2) : '--'}</span>
              </div>
              <div className="stock-card__field">
                <span className="stock-card__label">{t('stockSector.stockCard.prevClose')}</span>
                <span className="stock-card__value">{stockData.prev_close != null ? Number(stockData.prev_close).toFixed(2) : '--'}</span>
              </div>
              <div className="stock-card__field">
                <span className="stock-card__label">{t('stockSector.stockCard.volume')}</span>
                <span className="stock-card__value">{stockData.volume != null ? stockData.volume : '--'}</span>
              </div>
            </div>
          </div>
          <button type="button" className="button button--sm stock-card__analyze-btn" onClick={handleAnalyze} disabled={disabled}>
            {t('stockSector.analysis.analyze')}
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * 板块详情面板组件
 *
 * @component SectorDetailPanel
 * @description 展示选中板块的详细信息，包括板块名称、涨跌幅和龙头股实时行情列表
 *
 * @param {Object} props
 * @param {Object} props.sector - 板块数据对象
 * @param {Function} props.onAnalyzeSector - 分析板块的回调
 * @param {Function} props.onAnalyzeStock - 分析个股的回调
 * @returns {JSX.Element} 板块详情面板
 */
function SectorDetailPanel({ sector, onAnalyzeSector, onAnalyzeStock }) {
  const { t } = useTranslation();
  const [topStocks, setTopStocks] = useState([]);
  const [loadingStocks, setLoadingStocks] = useState(false);
  const tone = getChangeTone(sector?.change_pct);

  useEffect(() => {
    if (!sector?.top_stocks || !Array.isArray(sector.top_stocks) || sector.top_stocks.length === 0) {
      setTopStocks([]);
      return;
    }
    const codes = sector.top_stocks.slice(0, 5).map((s) => s.code || s);
    if (codes.length === 0) {
      setTopStocks([]);
      return;
    }
    let cancelled = false;
    setLoadingStocks(true);
    getStockRealtime(codes)
      .then((data) => { if (!cancelled) setTopStocks(Array.isArray(data) ? data.slice(0, 5) : []); })
      .catch(() => { if (!cancelled) setTopStocks([]); })
      .finally(() => { if (!cancelled) setLoadingStocks(false); });
    return () => { cancelled = true; };
  }, [sector]);

  if (!sector) return null;

  return (
    <div className="sector-detail">
      <div className="sector-detail__header">
        <div className="sector-detail__title-row">
          <h3>{t('stockSector.sectorDetail.title')}</h3>
          <span className={`sector-detail__change sector-detail__change--${tone}`}>
            {formatPercent(sector.change_pct)}
          </span>
        </div>
        <div className="sector-detail__name">{sector.sector_name}</div>
      </div>

      <div className="sector-detail__stocks">
        <h4>{t('stockSector.sectorDetail.topStocks')}</h4>
        {loadingStocks ? (
          <div className="sector-detail__stocks-loading">{t('common.loading')}...</div>
        ) : topStocks.length > 0 ? (
          <div className="sector-detail__stock-list">
            {topStocks.map((stock) => {
              const stockTone = getChangeTone(stock.change_pct);
              return (
                <div key={stock.code} className="sector-detail__stock-item">
                  <div className="sector-detail__stock-info">
                    <span className="sector-detail__stock-code">{stock.code}</span>
                    <span className="sector-detail__stock-name">{stock.name || '--'}</span>
                  </div>
                  <div className="sector-detail__stock-price">
                    <span>{stock.price != null ? Number(stock.price).toFixed(2) : '--'}</span>
                    <span className={`sector-detail__stock-change sector-detail__stock-change--${stockTone}`}>
                      {formatPercent(stock.change_pct)}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="empty-state">{t('stockSector.sectorDetail.noStocks')}</p>
        )}
      </div>

      <button type="button" className="button sector-detail__analyze-btn" onClick={() => onAnalyzeSector(sector)}>
        {t('stockSector.sectorDetail.analyzeSector')}
      </button>
    </div>
  );
}

/**
 * 板块排名表格组件
 *
 * @component SectorRankingTable
 * @description 展示板块涨跌排名表格，包含板块名称、涨跌幅、换手率、领涨股、涨跌家数等列
 *
 * @param {Object} props
 * @param {Array} props.sectors - 板块数据数组
 * @param {boolean} props.loading - 是否正在加载
 * @param {string} props.error - 错误信息
 * @param {Object} props.selectedSector - 当前选中的板块
 * @param {Function} props.onSelect - 选中板块的回调
 * @param {Function} props.onRetry - 重试加载的回调
 * @returns {JSX.Element} 板块排名表格或加载/错误/空状态
 */
function SectorRankingTable({ sectors, loading, error, selectedSector, onSelect, onRetry }) {
  const { t } = useTranslation();
  if (loading) return <SkeletonTable rows={8} columns={6} />;
  if (error) return <ErrorWithRetry message={error} onRetry={onRetry} />;
  if (!sectors || sectors.length === 0) return <p className="empty-state">{t('stockSector.table.empty')}</p>;

  return (
    <div className="table-wrap sector-table-wrap">
      <table className="sector-table">
        <thead>
          <tr>
            <th>{t('stockSector.table.sectorName')}</th>
            <th>{t('stockSector.table.changePct')}</th>
            <th>{t('stockSector.table.turnoverRate')}</th>
            <th>{t('stockSector.table.leadingStock')}</th>
            <th>{t('stockSector.table.riseFall')}</th>
            <th>{t('stockSector.table.action')}</th>
          </tr>
        </thead>
        <tbody>
          {sectors.map((sector) => {
            const tone = getChangeTone(sector.change_pct);
            const isSelected = selectedSector?.sector_code === sector.sector_code;
            return (
              <tr
                key={sector.sector_code}
                className={`sector-row ${isSelected ? 'sector-row--selected' : ''}`}
                onClick={() => onSelect(sector)}
              >
                <td className="sector-row__name">{sector.sector_name}</td>
                <td>
                  <div className="sector-row__change-cell">
                    <span className={`sector-row__change sector-row__change--${tone}`}>{formatPercent(sector.change_pct)}</span>
                    <ChangeBar value={sector.change_pct} />
                  </div>
                </td>
                <td>{sector.turnover_rate != null ? `${sector.turnover_rate.toFixed(2)}%` : '--'}</td>
                <td>{sector.leading_stock || '--'}</td>
                <td>
                  <span className="sector-row__rise-fall">
                    <span className="sector-row__rise">{sector.rise_count ?? 0}</span>
                    <span className="sector-row__separator">/</span>
                    <span className="sector-row__fall">{sector.fall_count ?? 0}</span>
                  </span>
                </td>
                <td>
                  <button type="button" className="button button--sm" onClick={(e) => { e.stopPropagation(); onSelect(sector); }}>
                    {t('stockSector.table.analyze')}
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/**
 * AI 分析结果展示面板
 *
 * @component AnalysisResultPanel
 * @description 展示股票/板块的 AI 分析结果，包括：
 * - 趋势判断（看涨/看跌/中性）
 * - 动量评估（强/弱/盘整）
 * - 情感分数仪表盘
 * - 推理逻辑文本
 * - 关键因素列表
 * - 风险提示列表
 * - 技术指标图表
 *
 * @param {Object} props
 * @param {Object} props.analysis - AI 分析结果对象
 * @returns {JSX.Element|null} 分析结果面板，无数据返回 null
 */
function AnalysisResultPanel({ analysis }) {
  const { t } = useTranslation();
  if (!analysis) return null;

  const trendLabel = { bullish: t('stockSector.trend.bullish'), bearish: t('stockSector.trend.bearish'), neutral: t('stockSector.trend.neutral') };
  const momentumLabel = { strong: t('stockSector.momentum.strong'), weak: t('stockSector.momentum.weak'), sideways: t('stockSector.momentum.sideways') };
  const trendTone = analysis.trend === 'bullish' ? 'good' : analysis.trend === 'bearish' ? 'bad' : 'warn';

  return (
    <div className="analysis-result-grid">
      <div className="analysis-result__header">
        <h3>{t('stockSector.result.title')}: {analysis.target_sector}</h3>
        <div className="analysis-result__badges">
          <span className={`badge badge--${trendTone}`}>{trendLabel[analysis.trend] || analysis.trend}</span>
          <span className="badge badge--warn">{momentumLabel[analysis.momentum] || analysis.momentum}</span>
        </div>
      </div>

      <SentimentMeter score={analysis.sentiment_score} title={t('stockSector.result.sentiment')}
        label={`${t('common.unknown')}: ${(analysis.confidence * 100).toFixed(0)}%`}
        badge={trendLabel[analysis.trend] || analysis.trend} badgeTone={trendTone} />

      <section className="subpanel">
        <div className="subpanel__header"><h3>{t('stockSector.result.reasoning')}</h3></div>
        <p className="research-copy">{analysis.reasoning || t('stockSector.result.noReasoning')}</p>
      </section>

      {analysis.key_factors?.length > 0 ? (
        <section className="subpanel">
          <div className="subpanel__header"><h3>{t('stockSector.result.keyFactors')}</h3></div>
          <ul className="analysis-factor-list">
            {analysis.key_factors.map((f, i) => (
              <li key={i} className="analysis-factor-item"><span className="analysis-factor-icon">+</span>{f}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {analysis.risk_warnings?.length > 0 ? (
        <section className="subpanel subpanel--warning">
          <div className="subpanel__header"><h3>{t('stockSector.result.riskWarnings')}</h3></div>
          <ul className="analysis-factor-list">
            {analysis.risk_warnings.map((w, i) => (
              <li key={i} className="analysis-factor-item analysis-factor-item--risk">
                <span className="analysis-factor-icon analysis-factor-icon--risk">!</span>{w}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {analysis.technical_summary && Object.keys(analysis.technical_summary).length > 0 ? (
        <TechnicalChart technicalSummary={analysis.technical_summary} />
      ) : null}

      {analysis.technical_summary && Object.keys(analysis.technical_summary).length > 0 ? (
        <section className="subpanel">
          <div className="subpanel__header"><h3>{t('stockSector.result.technicalSummary')}</h3></div>
          <dl className="key-value-grid key-value-grid--dense">
            {Object.entries(analysis.technical_summary).map(([key, value]) => (
              <div key={key}><dt>{key}</dt><dd>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</dd></div>
            ))}
          </dl>
        </section>
      ) : null}
    </div>
  );
}

/**
 * 股票板块分析视图
 *
 * @component StockSector
 * @description 股票板块分析的主视图页面，整合以下功能模块：
 * - 板块类型切换（行业/概念）
 * - 板块排名表格和详情面板
 * - 快速个股查询和实时行情
 * - AI 趋势分析（支持板块和个股两种模式）
 * - 自动刷新和数据新鲜度追踪
 * - 自选股管理侧边栏
 * - 分析历史记录查看
 *
 * @returns {JSX.Element} 股票板块分析页面
 *
 * @example
 * // 在 App.jsx 中懒加载使用
 * <Suspense fallback={<SkeletonTable />}>
 *   <StockSector />
 * </Suspense>
 */
export default function StockSector() {
  const { t } = useTranslation();
  const [sectorType, setSectorType] = useState('industry');
  const [sectors, setSectors] = useState([]);
  const [sectorsLoading, setSectorsLoading] = useState(false);
  const [sectorsError, setSectorsError] = useState('');
  const [selectedSector, setSelectedSector] = useState(null);
  const [stockInput, setStockInput] = useState('');
  const [analysis, setAnalysis] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState('');
  const [stepIndex, setStepIndex] = useState(0);
  const [showHistory, setShowHistory] = useState(false);
  const lastFetchedAtRef = useRef(null);
  const [lastFetchedAt, setLastFetchedAt] = useState(null);

  const ANALYSIS_STEPS = [t('stockSector.steps.0'), t('stockSector.steps.1'), t('stockSector.steps.2')];

  /**
   * 加载板块数据
   * @function loadSectors
   * @param {string} type - 板块类型（industry/concept）
   * @description 从 API 获取板块排名数据，更新最后获取时间
   */
  const loadSectors = useCallback(async (type) => {
    setSectorsLoading(true); setSectorsError('');
    try {
      const data = await getStockSectors(type, 20);
      setSectors(Array.isArray(data) ? data : []);
      const now = Date.now();
      lastFetchedAtRef.current = now;
      setLastFetchedAt(now);
    } catch (err) {
      setSectors([]);
      setSectorsError(err.message || '板块数据加载失败');
    } finally {
      setSectorsLoading(false);
    }
  }, []);

  const { autoRefreshEnabled, toggleAutoRefresh, secondsUntilRefresh, markRefreshed } = useAutoRefresh({
    onRefresh: () => loadSectors(sectorType), intervalMs: 60000, enabled: true, paused: analyzing,
  });

  const freshness = useDataFreshness(lastFetchedAt, { fresh: 60, stale: 180 });

  useEffect(() => { loadSectors(sectorType); }, [sectorType, loadSectors]);

  useEffect(() => {
    let timer = null;
    if (analyzing) {
      timer = window.setInterval(() => {
        setStepIndex((c) => (c < ANALYSIS_STEPS.length - 1 ? c + 1 : c));
      }, 1200);
    } else {
      setStepIndex(0);
    }
    return () => { if (timer) window.clearInterval(timer); };
  }, [analyzing, ANALYSIS_STEPS.length]);

  /**
   * 执行 AI 分析
   * @function runAnalysis
   * @param {Object} params - 分析参数
   * @param {string} [params.sectorName] - 板块名称（板块分析模式）
   * @param {string} [params.stockCode] - 股票代码（个股分析模式）
   * @param {string} params.sectorType - 板块类型
   * @description 调用 AI 分析接口，支持板块分析和个股分析两种模式
   */
  const runAnalysis = useCallback(async (params) => {
    setAnalysis(null); setAnalysisError(''); setAnalyzing(true); setStepIndex(0);
    try {
      setAnalysis(await analyzeStockSector(params));
    } catch (err) {
      setAnalysisError(
        err.status >= 500 || /timeout/i.test(err.message || '')
          ? t('stockSector.busy')
          : err.message
      );
    } finally {
      setAnalyzing(false);
    }
  }, [t]);

  /**
   * 处理板块类型切换
   * @function handleSectorTypeChange
   * @param {string} type - 板块类型（industry/concept）
   * @description 切换板块类型时清除选中状态和分析结果
   */
  const handleSectorTypeChange = useCallback((type) => {
    setSectorType(type); setSelectedSector(null); setAnalysis(null); setAnalysisError('');
  }, []);

  /**
   * 处理板块选中
   * @function handleSelectSector
   * @param {Object} sector - 选中的板块对象
   * @description 更新选中板块并清空股票输入
   */
  const handleSelectSector = useCallback((sector) => {
    setSelectedSector(sector);
    setStockInput('');
  }, []);

  /**
   * 处理板块分析
   * @function handleAnalyzeSector
   * @param {Object} sector - 要分析的板块对象
   * @description 设置选中板块并触发板块级别的 AI 分析
   */
  const handleAnalyzeSector = useCallback((sector) => {
    setSelectedSector(sector);
    setStockInput('');
    runAnalysis({ sectorName: sector.sector_name, sectorType });
  }, [runAnalysis, sectorType]);

  /**
   * 处理快速查询的分析请求
   * @function handleQuickLookupAnalyze
   * @param {string} code - 股票代码
   * @description 从快速查询组件触发个股分析
   */
  const handleQuickLookupAnalyze = useCallback((code) => {
    setStockInput(code);
    setSelectedSector(null);
    runAnalysis({ stockCode: code, sectorType });
  }, [runAnalysis, sectorType]);

  /**
   * 处理输入框的股票分析
   * @function handleStockAnalyze
   * @description 使用输入框中的股票代码触发分析，清除板块选中状态
   */
  const handleStockAnalyze = useCallback(() => {
    const code = stockInput.trim();
    if (!code) return;
    setSelectedSector(null);
    runAnalysis({ stockCode: code, sectorType });
  }, [stockInput, runAnalysis, sectorType]);

  const SECTOR_TYPE_OPTIONS = useMemo(() => [
    { value: 'industry', label: t('stockSector.industry') },
    { value: 'concept', label: t('stockSector.concept') },
  ], [t]);

  /**
   * 处理自选股分析请求
   * @function handleWatchlistAnalyze
   * @param {string} type - 证券类型（stock/fund）
   * @param {string} code - 证券代码
   * @description 从自选股管理组件触发分析，仅处理股票类型
   */
  const handleWatchlistAnalyze = useCallback((type, code) => {
    if (type === 'stock') {
      setStockInput(code);
      setSelectedSector(null);
      runAnalysis({ stockCode: code, sectorType });
    }
  }, [runAnalysis, sectorType]);

  return (
    <section className="panel stock-sector-panel">
      <div className="section-header">
        <div>
          <h2>{t('stockSector.title')}</h2>
          <p>{t('stockSector.subtitle')}</p>
        </div>
        <div className="section-header__actions">
          <DataFreshnessBadge level={freshness.level} label={freshness.label} />
          <AutoRefreshControls enabled={autoRefreshEnabled} onToggle={toggleAutoRefresh}
            secondsUntilRefresh={secondsUntilRefresh} paused={analyzing} />
          <button type="button" className="button button--secondary"
            onClick={() => { loadSectors(sectorType); markRefreshed(); }} disabled={sectorsLoading}>
            {sectorsLoading ? t('stockSector.refreshing') : t('stockSector.refresh')}
          </button>
        </div>
      </div>

      <div className="sector-type-selector">
        {SECTOR_TYPE_OPTIONS.map((opt) => (
          <button key={opt.value} type="button"
            className={`tab-nav__button ${sectorType === opt.value && !showHistory ? 'tab-nav__button--active' : ''}`}
            onClick={() => handleSectorTypeChange(opt.value)}>{opt.label}</button>
        ))}
        <button type="button" className={`tab-nav__button ${showHistory ? 'tab-nav__button--active' : ''}`}
          onClick={() => setShowHistory((p) => !p)}>
          {showHistory ? t('stockSector.backToList') : t('stockSector.viewHistory')}
        </button>
      </div>

      {showHistory ? (
        <AnalysisHistory initialType="stock_sector" />
      ) : (
        <>
          <QuickStockLookup onAnalyze={handleQuickLookupAnalyze} disabled={analyzing} />

          <div className="stock-sector-layout">
            <div className="stock-sector-layout__main">
              <SectorRankingTable sectors={sectors} loading={sectorsLoading} error={sectorsError}
                selectedSector={selectedSector} onSelect={handleSelectSector} onRetry={() => loadSectors(sectorType)} />

              {selectedSector && !analyzing && !analysis ? (
                <SectorDetailPanel
                  sector={selectedSector}
                  onAnalyzeSector={handleAnalyzeSector}
                  onAnalyzeStock={handleQuickLookupAnalyze}
                />
              ) : null}

              <div className="sector-analysis-panel">
                <div className="section-header"><h3>{t('stockSector.analysis.title')}</h3></div>
                <div className="sector-analysis-input">
                  <div className="sector-analysis-input__row">
                    <SearchAutocomplete value={stockInput} onChange={setStockInput}
                      onSelect={(code) => { setStockInput(code); setSelectedSector(null); runAnalysis({ stockCode: code, sectorType }); }}
                      onSearch={() => handleStockAnalyze()}
                      placeholder={t('stockSector.analysis.inputPlaceholder')} disabled={analyzing}
                      staticSuggestions={COMMON_STOCK_CODES} recentKey="stock_search_recent"
                      label={t('stockSector.analysis.inputLabel')} />
                    <button type="button" className="button" onClick={handleStockAnalyze}
                      disabled={analyzing || !stockInput.trim()}>
                      {analyzing ? t('stockSector.analysis.analyzing') : t('stockSector.analysis.analyze')}
                    </button>
                  </div>
                </div>

                {analysisError ? <div className="inline-alert inline-alert--error">{analysisError}</div> : null}
                {analyzing ? <AnalysisLoadingState steps={ANALYSIS_STEPS} currentStep={stepIndex} message={t('stockSector.loadingMessage')} /> : null}
                {!analyzing && !analysis && !analysisError ? <div className="subpanel empty-state">{t('stockSector.analysis.empty')}</div> : null}
                {!analyzing && analysis ? <AnalysisResultPanel analysis={analysis} /> : null}
                {!analyzing && analysis ? (
                  <div style={{ marginTop: 12, display: 'flex', justifyContent: 'flex-end' }}>
                    <ExportButton data={analysis} filename={`stock-analysis-${analysis.target_sector || 'result'}`} />
                  </div>
                ) : null}
              </div>
            </div>

            <aside className="stock-sector-layout__sidebar">
              <WatchlistManager onAnalyze={handleWatchlistAnalyze} />
            </aside>
          </div>
        </>
      )}
    </section>
  );
}
