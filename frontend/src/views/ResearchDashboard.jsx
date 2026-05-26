/**
 * @fileoverview 研究仪表盘视图 - 基金深度分析和持仓管理
 * @module views/ResearchDashboard
 * @description 研究仪表盘页面，包含以下功能：
 * - 模拟持仓基金列表展示
 * - 自定义提示词的深度 AI 分析
 * - 分析结果结构化展示（情感、推理、建议）
 * - C 类基金短期赎回费率风险警告
 * - 分析进度动画
 */

import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { analyzeFund, getLots } from '../api/client';

/**
 * 尝试解析 AI 分析输出为 JSON 对象
 * @function tryParseAnalysis
 * @param {string} output - AI 分析的原始输出文本
 * @returns {Object|null} 解析后的 JSON 对象，解析失败返回 null
 * @description 支持 markdown 代码块包裹的 JSON 格式
 */
function tryParseAnalysis(output) {
  if (!output || typeof output !== 'string') return null;
  const trimmed = output.trim();
  const cleaned = trimmed.startsWith('```')
    ? trimmed.replace(/^```json\s*/i, '').replace(/^```\s*/i, '').replace(/\s*```$/, '')
    : trimmed;
  try { return JSON.parse(cleaned); } catch { return null; }
}

/**
 * 将情感分数转换为显示分数（0-100）
 * @function toDisplayScore
 * @param {number} value - 原始分数（支持 -1 到 1 或 0 到 100 范围）
 * @returns {number} 0-100 范围的显示分数
 */
function toDisplayScore(value) {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return 0;
  if (numeric <= 1 && numeric >= -1) return Math.max(0, Math.min(100, ((numeric + 1) / 2) * 100));
  return Math.max(0, Math.min(100, numeric));
}

/**
 * 格式化数字显示
 * @function formatNumber
 * @param {*} value - 要格式化的值
 * @param {number} [fractionDigits=2] - 保留的小数位数
 * @returns {string} 格式化后的数字字符串，无效值返回 '—'
 */
function formatNumber(value, fractionDigits = 2) {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return '—';
  return numeric.toFixed(fractionDigits);
}

/**
 * 格式化百分比显示
 * @function formatPercent
 * @param {number} value - 数值
 * @returns {string} 格式化后的百分比字符串，无效值返回 '—'
 */
function formatPercent(value) {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return '—';
  return `${numeric.toFixed(2)}%`;
}

/**
 * 检测文本中是否包含费率风险警告关键词
 * @function containsFeeRiskWarning
 * @param {string} text - 要检测的文本
 * @returns {boolean} 如果包含费率相关关键词返回 true
 * @description 用于检测 C 类基金短期赎回费率风险
 */
function containsFeeRiskWarning(text = '') {
  return /手续费|7天|七天|短期赎回|赎回费|fee/i.test(text);
}

/**
 * 分析加载状态组件
 *
 * @component LoadingState
 * @description 展示分析进度条、步骤指示器和骨架屏占位
 *
 * @param {Object} props
 * @param {number} props.stepIndex - 当前步骤索引
 * @param {Function} props.t - i18next 翻译函数
 * @returns {JSX.Element} 加载状态 JSX
 */
function LoadingState({ stepIndex, t }) {
  const steps = [t('research.steps.0'), t('research.steps.1'), t('research.steps.2')];
  const progress = ((stepIndex + 1) / steps.length) * 100;

  return (
    <div className="research-loading" aria-live="polite">
      <div className="research-progress">
        <div className="research-progress__bar step-transition" style={{ width: `${progress}%` }} />
      </div>
      <div className="research-steps">
        {steps.map((step, index) => (
          <div key={step} className={`research-step ${index <= stepIndex ? 'research-step--active' : ''}`}>
            <span className="research-step__dot" />
            <span>{step}</span>
          </div>
        ))}
      </div>
      <div className="research-loading__skeleton">
        <div className="research-loading__line" />
        <div className="research-loading__line research-loading__line--short" />
        <div className="research-loading__line" />
      </div>
      <p>{t('research.loadingMessage')}</p>
    </div>
  );
}

/**
 * 持仓基金卡片组件
 *
 * @component HoldingCard
 * @description 展示单只持仓基金的基本信息和深度分析触发按钮
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
        <span className="badge badge--warn">{lot.holding_days} {t('research.sidebar.holdingDays')}</span>
      </div>
      <dl className="key-value-grid key-value-grid--dense">
        <div><dt>{t('research.sidebar.shares')}</dt><dd>{formatNumber(lot.shares, 4)}</dd></div>
        <div><dt>{t('research.sidebar.pnlRatio')}</dt><dd>{formatPercent(lot.pnl_ratio)}</dd></div>
        <div><dt>{t('research.sidebar.status')}</dt><dd>{lot.status || 'OPEN'}</dd></div>
      </dl>
      <button type="button" className="button holding-card__action" disabled={disabled} onClick={() => onAnalyze(lot)}>
        {disabled ? t('research.sidebar.analyzing') : t('research.sidebar.deepAnalysis')}
      </button>
    </article>
  );
}

/**
 * 研究结果展示组件
 *
 * @component ResearchResult
 * @description 展示基金深度分析结果，包括：
 * - 情感分析分数和可视化条
 * - 推理逻辑文本
 * - 操作建议（含费率风险警告）
 * - 结构化 JSON 输出
 *
 * @param {Object} props
 * @param {Object} props.selectedLot - 选中的持仓记录
 * @param {Object} props.result - AI 分析结果对象
 * @param {Function} props.t - i18next 翻译函数
 * @returns {JSX.Element} 分析结果面板
 */
function ResearchResult({ selectedLot, result, t }) {
  const parsed = useMemo(() => tryParseAnalysis(result?.output), [result]);
  const sentiment = parsed?.sentiment ?? t('common.unknown');
  const score = parsed?.score ?? 0;
  const logic = parsed?.logic ?? result?.output ?? t('common.empty');
  const suggestion = parsed?.suggestion ?? t('common.empty');
  const displayScore = toDisplayScore(score);
  const positiveTone = displayScore >= 50;
  const feeRisk = Number(selectedLot?.holding_days) < 7 && containsFeeRiskWarning(String(suggestion));

  return (
    <div className="research-result-grid">
      <section className="subpanel">
        <div className="subpanel__header">
          <h3>{t('research.result.sentiment')}</h3>
          <span className={`badge ${positiveTone ? 'badge--good' : 'badge--bad'}`}>{sentiment}</span>
        </div>
        <div className="sentiment-meter">
          <div className="sentiment-meter__track">
            <div className={`sentiment-meter__fill ${positiveTone ? 'sentiment-meter__fill--positive' : 'sentiment-meter__fill--negative'} step-transition`}
              style={{ width: `${displayScore}%` }} />
          </div>
          <div className="sentiment-meter__meta">
            <strong>{score}</strong>
            <span>score</span>
          </div>
        </div>
      </section>

      <section className="subpanel">
        <div className="subpanel__header"><h3>{t('research.result.reasoning')}</h3></div>
        <p className="research-copy">{logic}</p>
      </section>

      <section className={`subpanel ${feeRisk ? 'subpanel--warning' : ''}`}>
        <div className="subpanel__header">
          <h3>{t('research.result.suggestion')}</h3>
          {feeRisk ? <span className="research-warning">{'\u26A0'} {t('research.result.feeWarning')}</span> : null}
        </div>
        <p className="research-copy research-copy--suggestion">{suggestion}</p>
      </section>

      <section className="subpanel">
        <div className="subpanel__header"><h3>{t('research.result.structured')}</h3></div>
        <pre>{JSON.stringify(parsed || result, null, 2)}</pre>
      </section>
    </div>
  );
}

/**
 * 研究仪表盘视图
 *
 * @component ResearchDashboard
 * @description 研究仪表盘的主视图页面，整合以下功能模块：
 * - 模拟持仓基金列表和快速分析
 * - 自定义提示词输入
 * - AI 深度分析结果展示
 * - 分析进度动画
 * - C 类基金费率风险检测
 *
 * @returns {JSX.Element} 研究仪表盘页面
 *
 * @example
 * <ResearchDashboard />
 */
export default function ResearchDashboard() {
  const { t } = useTranslation();
  const [lots, setLots] = useState([]);
  const [lotsLoading, setLotsLoading] = useState(true);
  const [lotsError, setLotsError] = useState('');
  const [selectedLot, setSelectedLot] = useState(null);
  const [customPrompt, setCustomPrompt] = useState('');
  const [analysisResult, setAnalysisResult] = useState(null);
  const [analysisError, setAnalysisError] = useState('');
  const [analyzingAssetCode, setAnalyzingAssetCode] = useState('');
  const [stepIndex, setStepIndex] = useState(0);

  const RESEARCH_STEPS = [t('research.steps.0'), t('research.steps.1'), t('research.steps.2')];

  useEffect(() => {
    let timer = null;
    if (analyzingAssetCode) {
      timer = window.setInterval(() => {
        setStepIndex((c) => (c < RESEARCH_STEPS.length - 1 ? c + 1 : c));
      }, 900);
    } else {
      setStepIndex(0);
    }
    return () => { if (timer) window.clearInterval(timer); };
  }, [analyzingAssetCode, RESEARCH_STEPS.length]);

  /**
   * 加载模拟持仓数据
   * @async
   * @function loadLots
   * @description 从 API 获取模拟交易的持仓记录列表
   */
  async function loadLots() {
    setLotsLoading(true); setLotsError('');
    try {
      const response = await getLots();
      setLots(Array.isArray(response) ? response : []);
    } catch (e) {
      setLots([]);
      setLotsError(e.message || '持仓加载失败');
    } finally {
      setLotsLoading(false);
    }
  }

  useEffect(() => { loadLots(); }, []);

  /**
   * 处理基金深度分析
   * @async
   * @function handleAnalyze
   * @param {Object} lot - 持仓记录对象
   * @description 选中持仓并触发 AI 深度分析，支持自定义提示词
   */
  async function handleAnalyze(lot) {
    setSelectedLot(lot); setAnalysisResult(null); setAnalysisError('');
    setAnalyzingAssetCode(lot.asset_code); setStepIndex(0);
    try {
      setAnalysisResult(await analyzeFund(lot.asset_code, customPrompt));
    } catch (e) {
      setAnalysisError(
        e.status >= 500 || /timeout/i.test(e.message || '') ? t('research.busy') : e.message
      );
    } finally {
      setAnalyzingAssetCode('');
    }
  }

  return (
    <section className="panel research-dashboard-panel">
      <div className="section-header">
        <div>
          <h2>{t('research.title')}</h2>
          <p>{t('research.subtitle')}</p>
        </div>
        <button type="button" className="button button--secondary" onClick={loadLots}>
          {t('research.refreshHoldings')}
        </button>
      </div>

      <div className="research-layout">
        <aside className="research-layout__sidebar">
          <div className="subpanel">
            <div className="subpanel__header"><h3>{t('research.sidebar.holdings')}</h3></div>
            {lotsError ? <div className="inline-alert inline-alert--error">{lotsError}</div> : null}
            {lotsLoading ? <p className="empty-state">{t('research.sidebar.loading')}</p> : null}
            {!lotsLoading && lots.length === 0 ? <p className="empty-state">{t('research.sidebar.noHoldings')}</p> : null}
            {!lotsLoading && lots.length > 0 ? (
              <div className="holding-card-list">
                {lots.map((lot) => (
                  <HoldingCard key={lot.id} lot={lot} active={selectedLot?.id === lot.id}
                    disabled={analyzingAssetCode === lot.asset_code} onAnalyze={handleAnalyze} t={t} />
                ))}
              </div>
            ) : null}
          </div>
        </aside>

        <div className="research-layout__main">
          <div className="subpanel">
            <div className="subpanel__header"><h3>{t('research.prompt.title')}</h3></div>
            <label>
              <span>{t('research.prompt.label')}</span>
              <textarea rows={4} value={customPrompt} onChange={(e) => setCustomPrompt(e.target.value)}
                placeholder={t('research.prompt.placeholder')} />
            </label>
          </div>

          {analysisError ? <div className="inline-alert inline-alert--error">{analysisError}</div> : null}
          {!analysisError && analyzingAssetCode ? <LoadingState stepIndex={stepIndex} t={t} /> : null}
          {!analysisError && !analyzingAssetCode && !analysisResult ? (
            <div className="subpanel empty-state">{t('research.empty')}</div>
          ) : null}
          {!analysisError && !analyzingAssetCode && analysisResult ? (
            <ResearchResult selectedLot={selectedLot} result={analysisResult} t={t} />
          ) : null}
        </div>
      </div>
    </section>
  );
}
