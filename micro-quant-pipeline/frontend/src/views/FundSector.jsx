/**
 * @fileoverview 基金板块分析视图 - 展示持仓基金分析和净值查询
 * @module views/FundSector
 * @description 基金板块分析页面，包含以下功能：
 * - 模拟持仓基金列表和 AI 分析
 * - 基金净值查询和历史走势
 * - 基金持仓详情表格
 * - 自定义提示词的 AI 判断
 * - 自动刷新和数据新鲜度追踪
 * - 分析历史记录查看
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getLots, getFundNav, analyzeFundSector } from '../api/client';
import AnalysisHistory from '../components/AnalysisHistory';
import AnalysisLoadingState from '../components/AnalysisLoadingState';
import AutoRefreshControls from '../components/AutoRefreshControls';
import ExportButton from '../components/ExportButton';
import DataFreshnessBadge from '../components/DataFreshnessBadge';
import ErrorWithRetry from '../components/ErrorWithRetry';
import SearchAutocomplete from '../components/SearchAutocomplete';
import SentimentMeter from '../components/SentimentMeter';
import SkeletonTable from '../components/SkeletonTable';
import Sparkline from '../components/Sparkline';
import FundHoldingsTable from '../components/FundHoldingsTable';
import WatchlistManager from '../components/WatchlistManager';
import useAutoRefresh from '../hooks/useAutoRefresh';
import useDataFreshness from '../hooks/useDataFreshness';

/**
 * 格式化数字显示
 * @function formatNumber
 * @param {*} value - 要格式化的值
 * @param {number} [fractionDigits=2] - 保留的小数位数
 * @returns {string} 格式化后的数字字符串，无效值返回 '--'
 */
function formatNumber(value, fractionDigits = 2) {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return '--';
  return numeric.toFixed(fractionDigits);
}

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
 * 持仓基金卡片组件
 *
 * @component HoldingCard
 * @description 展示单只持仓基金的基本信息和 AI 分析触发按钮
 *
 * @param {Object} props
 * @param {Object} props.lot - 持仓记录对象
 * @param {boolean} props.active - 是否为当前选中状态
 * @param {boolean} props.disabled - 是否禁用（分析进行中）
 * @param {Function} props.onAnalyze - 触发分析的回调
 * @param {Function} props.t - i18next 翻译函数
 * @returns {JSX.Element} 持仓卡片 JSX
 */
function HoldingCard({ lot, active, disabled, onAnalyze, t }) {
  return (
    <article className={`holding-card ${active ? 'holding-card--active' : ''}`}>
      <div className="holding-card__header">
        <h3>{lot.asset_code}</h3>
        <span className="badge badge--warn">{lot.holding_days} {t('fundSector.sidebar.holdingDays')}</span>
      </div>
      <dl className="key-value-grid key-value-grid--dense">
        <div><dt>{t('fundSector.sidebar.shares')}</dt><dd>{formatNumber(lot.shares, 4)}</dd></div>
        <div><dt>{t('fundSector.sidebar.pnlRatio')}</dt><dd>{formatPercent(lot.pnl_ratio)}</dd></div>
        <div><dt>{t('fundSector.sidebar.status')}</dt><dd>{lot.status || 'OPEN'}</dd></div>
      </dl>
      <button type="button" className="button holding-card__action" disabled={disabled} onClick={() => onAnalyze(lot)}>
        {disabled ? t('fundSector.sidebar.aiAnalyzing') : t('fundSector.sidebar.aiAnalysis')}
      </button>
    </article>
  );
}

/**
 * 基金净值表格组件
 *
 * @component FundNavTable
 * @description 展示基金净值数据表格，包括基金代码、名称、净值、日收益率、累计净值和日期
 *
 * @param {Object} props
 * @param {Array} props.navs - 基金净值数据数组
 * @param {boolean} props.loading - 是否正在加载
 * @param {string} props.error - 错误信息
 * @param {Function} props.onRetry - 重试回调
 * @param {Function} props.t - i18next 翻译函数
 * @returns {JSX.Element} 净值表格或加载/错误/空状态
 */
function FundNavTable({ navs, loading, error, onRetry, t }) {
  if (loading) return <SkeletonTable rows={3} columns={6} />;
  if (error) return <ErrorWithRetry message={error} onRetry={onRetry} />;
  if (!navs || navs.length === 0) return <p className="empty-state">{t('fundSector.navTable.empty')}</p>;

  return (
    <div className="table-wrap">
      <table className="fund-nav-table">
        <thead>
          <tr>
            <th>{t('fundSector.navTable.fundCode')}</th>
            <th>{t('fundSector.navTable.fundName')}</th>
            <th>{t('fundSector.navTable.nav')}</th>
            <th>{t('fundSector.navTable.dailyReturn')}</th>
            <th>{t('fundSector.navTable.accNav')}</th>
            <th>{t('fundSector.navTable.navDate')}</th>
          </tr>
        </thead>
        <tbody>
          {navs.map((nav) => {
            const tone = getChangeTone(nav.daily_return);
            return (
              <tr key={nav.fund_code}>
                <td className="fund-nav-table__code">{nav.fund_code}</td>
                <td>{nav.fund_name || '--'}</td>
                <td>{formatNumber(nav.nav, 4)}</td>
                <td className={`sector-row__change sector-row__change--${tone}`}>{formatPercent(nav.daily_return)}</td>
                <td>{formatNumber(nav.acc_nav, 4)}</td>
                <td>{nav.nav_date || '--'}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/**
 * 基金分析结果展示组件
 *
 * @component FundAnalysisResult
 * @description 展示基金的 AI 分析结果，包括：
 * - 判断结果（正面/负面/中性）
 * - 操作建议（持有/观望/谨慎）
 * - 情感分数仪表盘
 * - 推理逻辑和净值趋势
 * - 新闻亮点和风险因素
 * - C 类基金短期持有费率警告
 *
 * @param {Object} props
 * @param {Object} props.analysis - AI 分析结果对象
 * @param {number} [props.holdingDays] - 持有天数（用于费率风险判断）
 * @param {Function} props.t - i18next 翻译函数
 * @returns {JSX.Element|null} 分析结果面板，无数据返回 null
 */
function FundAnalysisResult({ analysis, holdingDays, t }) {
  if (!analysis) return null;

  const judgmentLabel = { positive: t('fundSector.judgment.positive'), negative: t('fundSector.judgment.negative'), neutral: t('fundSector.judgment.neutral') };
  const judgmentTone = analysis.judgment === 'positive' ? 'good' : analysis.judgment === 'negative' ? 'bad' : 'warn';
  const suggestionLabel = { hold: t('fundSector.suggestion.hold'), watch: t('fundSector.suggestion.watch'), caution: t('fundSector.suggestion.caution') };
  const suggestionTone = analysis.suggestion === 'hold' ? 'good' : analysis.suggestion === 'caution' ? 'bad' : 'warn';
  const navTrendLabel = { rising: t('fundSector.navTrend.rising'), falling: t('fundSector.navTrend.falling'), stable: t('fundSector.navTrend.stable') };
  const feeRisk = holdingDays != null && holdingDays < 7 && analysis.c_class_fee_warning;

  return (
    <div className="analysis-result-grid">
      <div className="analysis-result__header">
        <h3>{t('fundSector.result.title')}: {analysis.fund_name || analysis.fund_code}</h3>
        <div className="analysis-result__badges">
          <span className={`badge badge--${judgmentTone}`}>{judgmentLabel[analysis.judgment] || analysis.judgment}</span>
          <span className={`badge badge--${suggestionTone}`}>{suggestionLabel[analysis.suggestion] || analysis.suggestion}</span>
        </div>
      </div>

      <SentimentMeter score={analysis.sentiment_score} title={t('fundSector.result.sentiment')}
        label={`${t('common.unknown')}: ${(analysis.confidence * 100).toFixed(0)}%`}
        badge={judgmentLabel[analysis.judgment] || analysis.judgment} badgeTone={judgmentTone} />

      <section className="subpanel">
        <div className="subpanel__header"><h3>{t('fundSector.result.reasoning')}</h3></div>
        <p className="research-copy">{analysis.reasoning || t('fundSector.result.noReasoning')}</p>
      </section>

      <section className="subpanel">
        <div className="subpanel__header">
          <h3>{t('fundSector.result.navTrend')}</h3>
          <span className={`badge badge--${analysis.nav_trend === 'rising' ? 'good' : analysis.nav_trend === 'falling' ? 'bad' : 'warn'}`}>
            {navTrendLabel[analysis.nav_trend] || analysis.nav_trend}
          </span>
        </div>
      </section>

      {analysis.news_highlights?.length > 0 ? (
        <section className="subpanel">
          <div className="subpanel__header"><h3>{t('fundSector.result.newsHighlights')}</h3></div>
          <ul className="analysis-factor-list">
            {analysis.news_highlights.map((item, i) => (
              <li key={i} className="analysis-factor-item"><span className="analysis-factor-icon">+</span>{item}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {analysis.risk_factors?.length > 0 ? (
        <section className="subpanel subpanel--warning">
          <div className="subpanel__header"><h3>{t('fundSector.result.riskFactors')}</h3></div>
          <ul className="analysis-factor-list">
            {analysis.risk_factors.map((risk, i) => (
              <li key={i} className="analysis-factor-item analysis-factor-item--risk">
                <span className="analysis-factor-icon analysis-factor-icon--risk">!</span>{risk}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {feeRisk ? (
        <div className="inline-alert inline-alert--error">
          <strong>{t('fundSector.result.feeWarning')}</strong>: {t('fundSector.result.feeWarningDetail')}
        </div>
      ) : null}

      <section className="subpanel">
        <div className="subpanel__header"><h3>{t('fundSector.result.suggestion')}</h3></div>
        <p className="research-copy research-copy--suggestion">
          {suggestionLabel[analysis.suggestion] || analysis.suggestion || t('fundSector.result.noSuggestion')}
        </p>
      </section>
    </div>
  );
}

/**
 * 基金板块分析视图
 *
 * @component FundSector
 * @description 基金板块分析的主视图页面，整合以下功能模块：
 * - 模拟持仓基金列表和快速分析
 * - 基金代码输入和净值查询
 * - AI 分析结果展示（判断、建议、风险因素）
 * - 自定义提示词输入
 * - 基金持仓详情表格
 * - 自选股管理
 * - 自动刷新和数据新鲜度追踪
 * - 分析历史记录查看
 *
 * @returns {JSX.Element} 基金板块分析页面
 *
 * @example
 * // 在 App.jsx 中懒加载使用
 * <Suspense fallback={<SkeletonTable />}>
 *   <FundSector />
 * </Suspense>
 */
export default function FundSector() {
  const { t } = useTranslation();
  const [lots, setLots] = useState([]);
  const [lotsLoading, setLotsLoading] = useState(true);
  const [lotsError, setLotsError] = useState('');
  const [selectedLot, setSelectedLot] = useState(null);
  const [fundCodeInput, setFundCodeInput] = useState('');
  const [customPrompt, setCustomPrompt] = useState('');
  const [promptExpanded, setPromptExpanded] = useState(false);
  const [fundNavs, setFundNavs] = useState([]);
  const [navsLoading, setNavsLoading] = useState(false);
  const [navsError, setNavsError] = useState('');
  const [analysis, setAnalysis] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState('');
  const [stepIndex, setStepIndex] = useState(0);
  const [showHistory, setShowHistory] = useState(false);
  const [lastLotsFetchedAt, setLastLotsFetchedAt] = useState(null);

  const ANALYSIS_STEPS = [t('fundSector.steps.0'), t('fundSector.steps.1'), t('fundSector.steps.2')];

  /** Whether a fund code is available for analysis */
  const hasCode = fundCodeInput.trim().length > 0;

  const fundSuggestions = useMemo(() => {
    return lots.map((lot) => ({ code: lot.asset_code, label: lot.asset_code, sub: `${lot.holding_days}${t('fundSector.sidebar.holdingDays')}` }));
  }, [lots, t]);

  /** Load simulated holdings */
  const loadLots = useCallback(async () => {
    setLotsLoading(true); setLotsError('');
    try {
      const response = await getLots();
      setLots(Array.isArray(response) ? response : []);
      setLastLotsFetchedAt(Date.now());
    } catch (err) {
      setLots([]);
      setLotsError(err.message || '持仓加载失败');
    } finally {
      setLotsLoading(false);
    }
  }, []);

  const { autoRefreshEnabled, toggleAutoRefresh, secondsUntilRefresh, markRefreshed } = useAutoRefresh({
    onRefresh: loadLots, intervalMs: 300000, enabled: true, paused: analyzing,
  });

  const lotsFreshness = useDataFreshness(lastLotsFetchedAt, { fresh: 60, stale: 300 });

  useEffect(() => { loadLots(); }, [loadLots]);

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

  /** Run AI analysis for a fund code */
  const runAnalysis = useCallback(async (fundCode) => {
    setAnalysis(null); setAnalysisError(''); setAnalyzing(true); setStepIndex(0);
    try {
      setAnalysis(await analyzeFundSector(fundCode, customPrompt));
    } catch (err) {
      setAnalysisError(
        err.status >= 500 || /timeout/i.test(err.message || '')
          ? t('fundSector.busy')
          : err.message
      );
    } finally {
      setAnalyzing(false);
    }
  }, [customPrompt, t]);

  /** Query NAV for entered fund code */
  const handleQueryNav = useCallback(async () => {
    const code = fundCodeInput.trim();
    if (!code) return;
    setNavsLoading(true); setNavsError(''); setFundNavs([]);
    try { setFundNavs(Array.isArray(await getFundNav([code])) ? await getFundNav([code]) : []); }
    catch (err) { setNavsError(err.message || '基金净值查询失败'); }
    finally { setNavsLoading(false); }
  }, [fundCodeInput]);

  /** Handle analysis from holding card click */
  const handleAnalyzeLot = useCallback((lot) => {
    setSelectedLot(lot); setFundCodeInput(lot.asset_code); runAnalysis(lot.asset_code);
  }, [runAnalysis]);

  /** Handle analysis from input field */
  const handleAnalyzeInput = useCallback(() => {
    const code = fundCodeInput.trim();
    if (!code) return;
    setSelectedLot(null);
    runAnalysis(code);
  }, [fundCodeInput, runAnalysis]);

  /** Handle analysis from watchlist */
  const handleWatchlistAnalyze = useCallback((type, code) => {
    if (type === 'fund') {
      setFundCodeInput(code);
      setSelectedLot(null);
      runAnalysis(code);
    }
  }, [runAnalysis]);

  /** Display name for the currently selected fund */
  const activeFundLabel = selectedLot
    ? selectedLot.asset_code
    : hasCode ? fundCodeInput.trim() : null;

  return (
    <section className="panel fund-sector-panel">
      {/* Header spans full width */}
      <div className="section-header">
        <div>
          <h2>{t('fundSector.title')}</h2>
          <p>{t('fundSector.subtitle')}</p>
        </div>
        <div className="section-header__actions">
          <DataFreshnessBadge level={lotsFreshness.level} label={lotsFreshness.label} />
          <AutoRefreshControls enabled={autoRefreshEnabled} onToggle={toggleAutoRefresh}
            secondsUntilRefresh={secondsUntilRefresh} paused={analyzing} />
          <button type="button" className="button button--secondary"
            onClick={() => { loadLots(); markRefreshed(); }}>{t('fundSector.refreshHoldings')}</button>
          <button type="button" className={`button ${showHistory ? '' : 'button--secondary'}`}
            onClick={() => setShowHistory((p) => !p)}>
            {showHistory ? t('fundSector.backToAnalysis') : t('fundSector.viewHistory')}
          </button>
        </div>
      </div>

      {showHistory ? (
        <AnalysisHistory initialType="fund_sector" />
      ) : (
        /* THE KEY FIX: Use a wrapper div with explicit flex layout */
        <div className="fund-sector-layout">
          {/* LEFT: All data and controls */}
          <div className="fund-sector-layout__left">
            {/* Holdings */}
            <div className="subpanel">
              <div className="subpanel__header"><h3>{t('fundSector.sidebar.holdings')}</h3></div>
              {lotsError ? <ErrorWithRetry message={lotsError} onRetry={loadLots} retrying={lotsLoading} /> : null}
              {lotsLoading && lots.length === 0 ? <SkeletonTable rows={3} columns={3} /> : null}
              {!lotsLoading && lots.length === 0 && !lotsError ? <p className="empty-state">{t('fundSector.sidebar.noHoldings')}</p> : null}
              {!lotsLoading && lots.length > 0 ? (
                <div className="holding-card-list">
                  {lots.map((lot) => (
                    <HoldingCard key={lot.id} lot={lot} active={selectedLot?.id === lot.id}
                      disabled={analyzing} onAnalyze={handleAnalyzeLot} t={t} />
                  ))}
                </div>
              ) : null}
            </div>

            {/* Fund code search + actions */}
            <div className="subpanel">
              <div className="subpanel__header"><h3>{t('fundSector.fundCode.title')}</h3></div>
              <SearchAutocomplete value={fundCodeInput} onChange={setFundCodeInput}
                onSelect={(code) => { setFundCodeInput(code); setSelectedLot(null); runAnalysis(code); }}
                onSearch={() => handleAnalyzeInput()}
                placeholder={t('fundSector.fundCode.placeholder')} disabled={analyzing}
                staticSuggestions={fundSuggestions} recentKey="fund_search_recent"
                label={t('fundSector.fundCode.label')} />

              <div className="button-row" style={{ marginTop: '12px' }}>
                <button type="button" className="button button--secondary" onClick={handleQueryNav}
                  disabled={navsLoading || !hasCode}>
                  {navsLoading ? t('fundSector.fundCode.querying') : t('fundSector.fundCode.queryNav')}
                </button>
                <button type="button" className="button" onClick={handleAnalyzeInput}
                  disabled={analyzing || !hasCode}>
                  {analyzing ? t('fundSector.fundCode.analyzing') : t('fundSector.fundCode.aiJudgment')}
                </button>
              </div>

              {/* Collapsible custom prompt accordion */}
              <div className="prompt-accordion">
                <button type="button" className="prompt-accordion__toggle" onClick={() => setPromptExpanded((p) => !p)}>
                  <span>{t('fundSector.prompt.title')}</span>
                  <span className={`prompt-accordion__arrow ${promptExpanded ? 'prompt-accordion__arrow--open' : ''}`}>&#9660;</span>
                </button>
                <div className={`prompt-accordion__body ${promptExpanded ? 'prompt-accordion__body--open' : ''}`}>
                  <label className="prompt-accordion__label">
                    <span>{t('fundSector.prompt.label')}</span>
                    <textarea rows={3} value={customPrompt} onChange={(e) => setCustomPrompt(e.target.value)}
                      placeholder={t('fundSector.prompt.placeholder')} />
                  </label>
                </div>
              </div>
            </div>

            {/* NAV table */}
            {fundNavs.length > 0 || navsLoading || navsError ? (
              <div className="subpanel">
                <div className="subpanel__header"><h3>{t('fundSector.navTable.title')}</h3></div>
                <FundNavTable navs={fundNavs} loading={navsLoading} error={navsError} onRetry={handleQueryNav} t={t} />
              </div>
            ) : null}

            {/* Watchlist */}
            <WatchlistManager onAnalyze={handleWatchlistAnalyze} />

            {/* Fund holdings table */}
            <div className="subpanel">
              <div className="subpanel__header">
                <h3>{t('watchlist.fundHoldings.title')}</h3>
              </div>
              <FundHoldingsTable />
            </div>
          </div>

          {/* RIGHT: AI panel only - SIBLING of left, not nested inside anything */}
          <div className="fund-sector-layout__right">
            {analyzing ? (
              <AnalysisLoadingState steps={ANALYSIS_STEPS} currentStep={stepIndex} message={t('fundSector.loadingMessage')} />
            ) : analysisError ? (
              <div className="inline-alert inline-alert--error">{analysisError}</div>
            ) : analysis ? (
              <>
                <FundAnalysisResult analysis={analysis} holdingDays={selectedLot?.holding_days} t={t} />
                <div style={{ marginTop: 12, display: 'flex', justifyContent: 'flex-end' }}>
                  <ExportButton data={analysis} filename={`fund-analysis-${analysis.fund_code || analysis.fund_name || 'result'}`} />
                </div>
              </>
            ) : (
              <div className="fund-sector-ai-empty">
                <div className="fund-sector-ai-empty__icon">&#128202;</div>
                <p className="fund-sector-ai-empty__title">{t('fundSector.empty')}</p>
                <p className="fund-sector-ai-empty__desc">
                  {hasCode
                    ? t('fundSector.emptyWithCode', { code: fundCodeInput.trim() })
                    : t('fundSector.emptyHint')}
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
