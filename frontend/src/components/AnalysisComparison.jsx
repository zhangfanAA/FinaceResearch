/**
 * @fileoverview 分析结果对比组件 - 并排对比 2-3 条分析结果
 * @module components/AnalysisComparison
 * @description 将多条分析结果以表格形式并排展示，高亮显示差异字段
 */

import { useTranslation } from 'react-i18next';
import SentimentMeter from './SentimentMeter';

/**
 * 从分析结果中提取指定字段的值
 * @function getFieldValue
 * @param {Object} item - 分析结果对象
 * @param {string} field - 字段名称（target, trend, sentiment_score, confidence, reasoning, key_factors, risk_warnings, suggestion）
 * @returns {*} 字段值，未找到返回 '--'
 */
function getFieldValue(item, field) {
  const r = item.result || item;
  switch (field) {
    case 'target':
      return r.target_sector || r.target_name || r.fund_name || r.fund_code || r.target_code || item.target_code || '--';
    case 'trend':
      return r.trend || r.judgment || '--';
    case 'sentiment_score':
      return r.sentiment_score;
    case 'confidence':
      return r.confidence;
    case 'reasoning':
      return r.reasoning || r.logic || '--';
    case 'key_factors':
      return r.key_factors || [];
    case 'risk_warnings':
      return r.risk_warnings || r.risk_factors || [];
    case 'suggestion':
      return r.suggestion || '--';
    default:
      return '--';
  }
}

/**
 * 获取趋势对应的显示基调
 * @function getTrendTone
 * @param {string} trend - 趋势值（bullish/positive/bearish/negative/neutral）
 * @returns {'good'|'bad'|'warn'} 对应的颜色基调
 */
function getTrendTone(trend) {
  if (trend === 'bullish' || trend === 'positive') return 'good';
  if (trend === 'bearish' || trend === 'negative') return 'bad';
  return 'warn';
}

/**
 * 格式化百分比显示
 * @function formatPercent
 * @param {number|null} value - 小数值（如 0.75）
 * @returns {string} 百分比字符串（如 '75%'），null 返回 '--'
 */
function formatPercent(value) {
  if (value == null) return '--';
  return (value * 100).toFixed(0) + '%';
}

/**
 * 检查指定字段在多条记录中是否存在差异
 * @function hasDifference
 * @param {Array} items - 分析结果数组
 * @param {string} field - 字段名称
 * @returns {boolean} 如果字段值不完全相同返回 true
 * @description 用于在对比表格中高亮显示差异行
 */
function hasDifference(items, field) {
  const values = items.map((item) => {
    const v = getFieldValue(item, field);
    if (Array.isArray(v)) return JSON.stringify(v);
    return String(v ?? '');
  });
  return new Set(values).size > 1;
}

/**
 * AnalysisComparison -- Side-by-side comparison of 2-3 analysis results.
 *
 * @param {Object} props
 * @param {Array} props.items - Array of 2-3 analysis result objects
 * @param {Function} props.onClose
 */
/**
 * 分析结果对比组件
 *
 * @component AnalysisComparison
 * @description 将 2-3 条分析结果以表格形式并排展示，支持以下功能：
 * - 多字段并排对比（目标、趋势、情感分数、置信度、推理逻辑等）
 * - 差异字段高亮显示
 * - 情感分数可视化（SentimentMeter）
 * - 列表字段（关键因素、风险提示）的对比展示
 *
 * @param {Object} props
 * @param {Array} props.items - 2-3 条分析结果对象数组
 * @param {Function} props.onClose - 关闭对比面板的回调
 *
 * @returns {JSX.Element} 对比面板 JSX
 *
 * @example
 * <AnalysisComparison
 *   items={[result1, result2]}
 *   onClose={() => setCompareItems(null)}
 * />
 */
export default function AnalysisComparison({ items, onClose }) {
  const { t } = useTranslation();

  if (!items || items.length < 2) {
    return (
      <div className="comparison-panel">
        <div className="comparison-panel__header">
          <h3>{t('comparison.title')}</h3>
          <button type="button" className="button button--sm button--secondary" onClick={onClose}>
            {t('comparison.close')}
          </button>
        </div>
        <p className="empty-state">{t('comparison.noItems')}</p>
      </div>
    );
  }

  const fields = [
    { key: 'target', label: t('comparison.target'), type: 'text' },
    { key: 'trend', label: t('comparison.trend'), type: 'badge' },
    { key: 'sentiment_score', label: t('comparison.sentiment'), type: 'meter' },
    { key: 'confidence', label: t('comparison.confidence'), type: 'percent' },
    { key: 'reasoning', label: t('comparison.reasoning'), type: 'text' },
    { key: 'key_factors', label: t('comparison.keyFactors'), type: 'list' },
    { key: 'risk_warnings', label: t('comparison.riskWarnings'), type: 'list' },
    { key: 'suggestion', label: t('comparison.suggestion'), type: 'text' },
  ];

  return (
    <div className="comparison-panel">
      <div className="comparison-panel__header">
        <h3>{t('comparison.title')}</h3>
        <button type="button" className="button button--sm button--secondary" onClick={onClose}>
          {t('comparison.close')}
        </button>
      </div>

      <div className="comparison-table-wrap">
        <table className="comparison-table">
          <thead>
            <tr>
              <th className="comparison-table__field-col">{t('comparison.field')}</th>
              {items.map((item, idx) => {
                const target = getFieldValue(item, 'target');
                return <th key={idx}>{target}</th>;
              })}
            </tr>
          </thead>
          <tbody>
            {fields.filter((f) => f.key !== 'target').map((field) => {
              const isDiff = hasDifference(items, field.key);
              return (
                <tr key={field.key} className={isDiff ? 'comparison-row--diff' : ''}>
                  <td className="comparison-table__field-label">
                    {field.label}
                    {isDiff ? <span className="comparison-diff-badge" title="Different">*</span> : null}
                  </td>
                  {items.map((item, idx) => {
                    const value = getFieldValue(item, field.key);
                    return (
                      <td key={idx} className="comparison-table__value">
                        {field.type === 'badge' ? (
                          <span className={`badge badge--${getTrendTone(value)}`}>
                            {value}
                          </span>
                        ) : field.type === 'meter' ? (
                          <SentimentMeter score={value} compact />
                        ) : field.type === 'percent' ? (
                          <span>{formatPercent(value)}</span>
                        ) : field.type === 'list' ? (
                          Array.isArray(value) && value.length > 0 ? (
                            <ul className="comparison-factor-list">
                              {value.map((v, i) => (
                                <li key={i}>{v}</li>
                              ))}
                            </ul>
                          ) : (
                            <span className="comparison-empty">--</span>
                          )
                        ) : (
                          <span className="comparison-text">{value || '--'}</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
