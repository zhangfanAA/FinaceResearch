/**
 * @fileoverview AI 分析面板组件 - 自选管理的 AI 分析展示
 * @module components/WatchlistAIAnalysis
 * @description 展示 AI 分析结果的右侧面板，支持：
 * - 分析触发按钮
 * - 分析结果展示（复用 FundAnalysisResult 的样式）
 * - 操作建议展示
 * - 风险提示
 */

import { useTranslation } from 'react-i18next';
import AnalysisLoadingState from './AnalysisLoadingState';
import SentimentMeter from './SentimentMeter';

/**
 * AI 分析结果展示组件
 *
 * @component WatchlistAIAnalysis
 * @description 自选管理的 AI 分析面板，展示分析结果
 *
 * @param {Object} props
 * @param {Object} props.analysis - AI 分析结果对象
 * @param {boolean} props.analyzing - 是否正在分析
 * @param {string} props.error - 错误信息
 * @param {Object} props.selectedItem - 当前选中的自选项目
 * @param {number} props.stepIndex - 当前步骤索引
 * @returns {JSX.Element} AI 分析面板
 */
export default function WatchlistAIAnalysis({ analysis, analyzing, error, selectedItem, stepIndex }) {
  const { t } = useTranslation();

  const ANALYSIS_STEPS = [
    t('watchlistManagement.analysis.steps.fetchData'),
    t('watchlistManagement.analysis.steps.calculateIndicators'),
    t('watchlistManagement.analysis.steps.aiAnalysis'),
  ];

  if (analyzing) {
    return (
      <AnalysisLoadingState
        steps={ANALYSIS_STEPS}
        currentStep={stepIndex}
        message={t('watchlistManagement.analysis.loadingMessage')}
      />
    );
  }

  if (error) {
    return (
      <div className="inline-alert inline-alert--error">{error}</div>
    );
  }

  if (!analysis) {
    return (
      <div className="watchlist-ai-empty">
        <div className="watchlist-ai-empty__icon">&#128202;</div>
        <p className="watchlist-ai-empty__title">{t('watchlistManagement.analysis.empty')}</p>
        <p className="watchlist-ai-empty__desc">
          {selectedItem
            ? t('watchlistManagement.analysis.emptyWithItem', { code: selectedItem.code })
            : t('watchlistManagement.analysis.emptyHint')}
        </p>
      </div>
    );
  }

  const judgmentLabel = {
    positive: t('fundSector.judgment.positive'),
    negative: t('fundSector.judgment.negative'),
    neutral: t('fundSector.judgment.neutral'),
  };
  const judgmentTone = analysis.judgment === 'positive' ? 'good' : analysis.judgment === 'negative' ? 'bad' : 'warn';
  const suggestionLabel = {
    hold: t('fundSector.suggestion.hold'),
    watch: t('fundSector.suggestion.watch'),
    caution: t('fundSector.suggestion.caution'),
  };
  const suggestionTone = analysis.suggestion === 'hold' ? 'good' : analysis.suggestion === 'caution' ? 'bad' : 'warn';

  return (
    <div className="analysis-result-grid">
      <div className="analysis-result__header">
        <h3>{t('watchlistManagement.analysis.title')}: {analysis.fund_name || analysis.stock_name || analysis.fund_code || analysis.stock_code}</h3>
        <div className="analysis-result__badges">
          <span className={`badge badge--${judgmentTone}`}>{judgmentLabel[analysis.judgment] || analysis.judgment}</span>
          <span className={`badge badge--${suggestionTone}`}>{suggestionLabel[analysis.suggestion] || analysis.suggestion}</span>
        </div>
      </div>

      {analysis.sentiment_score != null && (
        <SentimentMeter
          score={analysis.sentiment_score}
          title={t('fundSector.result.sentiment')}
          label={`${t('common.unknown')}: ${(analysis.confidence * 100).toFixed(0)}%`}
          badge={judgmentLabel[analysis.judgment] || analysis.judgment}
          badgeTone={judgmentTone}
        />
      )}

      <section className="subpanel">
        <div className="subpanel__header">
          <h3>{t('fundSector.result.reasoning')}</h3>
        </div>
        <p className="research-copy">{analysis.reasoning || t('fundSector.result.noReasoning')}</p>
      </section>

      {analysis.news_highlights?.length > 0 ? (
        <section className="subpanel">
          <div className="subpanel__header">
            <h3>{t('fundSector.result.newsHighlights')}</h3>
          </div>
          <ul className="analysis-factor-list">
            {analysis.news_highlights.map((item, i) => (
              <li key={i} className="analysis-factor-item">
                <span className="analysis-factor-icon">+</span>{item}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {analysis.risk_factors?.length > 0 ? (
        <section className="subpanel subpanel--warning">
          <div className="subpanel__header">
            <h3>{t('fundSector.result.riskFactors')}</h3>
          </div>
          <ul className="analysis-factor-list">
            {analysis.risk_factors.map((risk, i) => (
              <li key={i} className="analysis-factor-item analysis-factor-item--risk">
                <span className="analysis-factor-icon analysis-factor-icon--risk">!</span>{risk}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="subpanel">
        <div className="subpanel__header">
          <h3>{t('watchlistManagement.analysis.operationSuggestion')}</h3>
        </div>
        <p className="research-copy research-copy--suggestion">
          {suggestionLabel[analysis.suggestion] || analysis.suggestion || t('fundSector.result.noSuggestion')}
        </p>
      </section>

      <div className="inline-alert inline-alert--warning">
        <strong>{t('watchlistManagement.analysis.riskDisclaimer')}</strong>
      </div>
    </div>
  );
}
