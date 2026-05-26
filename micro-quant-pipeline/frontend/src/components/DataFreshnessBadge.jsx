/**
 * @fileoverview 数据新鲜度徽章组件 - 以颜色编码显示数据更新状态
 * @module components/DataFreshnessBadge
 * @description 根据数据新鲜度等级显示带颜色指示点的徽章。使用 React.memo 优化渲染。
 */

import { memo } from 'react';

/**
 * DataFreshnessBadge - 数据新鲜度徽章组件（已优化：React.memo）
 *
 * @description
 * - 根据 fresh/stale/old 等级显示不同颜色
 * - 包含一个发光的圆点指示器
 * - 使用 aria-live="polite" 确保状态变化可被屏幕阅读器感知
 * - label 为空时不渲染
 * - 使用 React.memo 避免父组件重渲染时不必要的更新
 *
 * @param {Object} props - 组件属性
 * @param {'fresh'|'stale'|'old'} props.level - 新鲜度等级
 * @param {string} props.label - 显示的文本标签（如 "30秒前更新"）
 * @returns {JSX.Element|null} 新鲜度徽章组件，label 为空时返回 null
 *
 * @example
 * <DataFreshnessBadge level="fresh" label="15秒前更新" />
 * <DataFreshnessBadge level="old" label="5分钟前更新" />
 */
export default memo(function DataFreshnessBadge({ level, label }) {
  if (!label) return null;

  return (
    <span className={`freshness-badge freshness-badge--${level}`} aria-live="polite">
      <span className="freshness-badge__dot" />
      {label}
    </span>
  );
})
