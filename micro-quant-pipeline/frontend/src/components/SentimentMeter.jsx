/**
 * @fileoverview 情绪指标仪表组件 - 水平条形图可视化情绪分数
 * @module components/SentimentMeter
 * @description 可复用的情绪指标可视化组件，支持 -1 到 1 或 0 到 100 的分数范围。
 * 使用 React.memo 优化渲染。
 */

import { memo, useMemo } from 'react';

/**
 * 将情绪分数转换为 0-100 的显示值
 *
 * @description
 * - 支持 -1..1 范围（映射到 0..100）
 * - 支持 0..100 范围（直接使用）
 * - 超出范围的值会被钳制
 *
 * @param {number} value - 原始情绪分数
 * @returns {number} 0-100 的显示值
 */
function toDisplayScore(value) {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) {
    return 0;
  }

  if (numeric <= 1 && numeric >= -1) {
    return Math.max(0, Math.min(100, ((numeric + 1) / 2) * 100));
  }

  return Math.max(0, Math.min(100, numeric));
}

/**
 * SentimentMeter - 情绪指标仪表组件（已优化：React.memo）
 *
 * @description
 * - 显示水平条形图，根据分数填充不同颜色
 * - 分数 >= 50 显示绿色（积极），< 50 显示红色（消极）
 * - compact 模式下只显示仪表条，不包含外层容器
 * - 非 compact 模式下包含标题和徽章
 * - 使用 step-transition 实现平滑动画
 *
 * @param {Object} props - 组件属性
 * @param {number} props.score - 原始情绪分数（-1.0 到 1.0 或 0 到 100）
 * @param {string} [props.label='score'] - 分数旁边的标签文本
 * @param {string} [props.title=''] - 仪表区域的标题
 * @param {string} [props.badge=''] - 徽章文本（如 "bullish"、"positive"）
 * @param {string} [props.badgeTone] - 徽章色调："good"、"bad"、"warn"（省略时自动判断）
 * @param {boolean} [props.compact=false] - 是否为紧凑模式（无外层容器）
 * @returns {JSX.Element} 情绪指标组件
 *
 * @example
 * // 完整模式
 * <SentimentMeter
 *   score={0.75}
 *   title="情绪分析"
 *   label="置信度: 85%"
 *   badge="看涨"
 *   badgeTone="good"
 * />
 *
 * // 紧凑模式（用于表格或列表）
 * <SentimentMeter score={0.3} compact />
 */
export default memo(function SentimentMeter({
  score = 0,
  label = 'score',
  title = '',
  badge = '',
  badgeTone,
  compact = false,
}) {
  const displayScore = toDisplayScore(score);
  const positiveTone = displayScore >= 50;

  const resolvedBadgeTone = badgeTone || (positiveTone ? 'good' : 'bad');
  const fillClass = positiveTone
    ? 'sentiment-meter__fill--positive'
    : 'sentiment-meter__fill--negative';

  /* 仪表条内容 */
  const meterContent = (
    <div className="sentiment-meter">
      <div className="sentiment-meter__track">
        <div
          className={`sentiment-meter__fill ${fillClass} step-transition`}
          style={{ width: `${displayScore}%` }}
        />
      </div>
      <div className="sentiment-meter__meta">
        <strong>{score}</strong>
        <span>{label}</span>
      </div>
    </div>
  );

  /* 紧凑模式：只返回仪表条 */
  if (compact) {
    return meterContent;
  }

  /* 完整模式：包含标题和徽章 */
  return (
    <section className="subpanel">
      {title || badge ? (
        <div className="subpanel__header">
          {title ? <h3>{title}</h3> : null}
          {badge ? <span className={`badge badge--${resolvedBadgeTone}`}>{badge}</span> : null}
        </div>
      ) : null}
      {meterContent}
    </section>
  );
})
