/**
 * @fileoverview 数据新鲜度徽章组件 - 以颜色编码显示数据更新状态
 * @module components/DataFreshnessBadge
 * @description 根据数据新鲜度等级显示带颜色指示点的徽章。使用 React.memo 优化渲染。
 * 支持服务端 stale 标记，显示"使用缓存数据"指示。
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
 * - 当 serverStale=true 时显示"使用缓存数据"警告徽章
 * - 使用 React.memo 避免父组件重渲染时不必要的更新
 *
 * @param {Object} props - 组件属性
 * @param {'fresh'|'stale'|'old'} props.level - 新鲜度等级
 * @param {string} props.label - 显示的文本标签（如 "30秒前更新"）
 * @param {boolean} [props.serverStale=false] - 服务端返回的 stale 标记
 * @param {string} [props.cachedAt] - 服务端缓存时间（ISO 字符串）
 * @returns {JSX.Element|null} 新鲜度徽章组件，label 为空时返回 null
 *
 * @example
 * <DataFreshnessBadge level="fresh" label="15秒前更新" />
 * <DataFreshnessBadge level="old" label="5分钟前更新" serverStale={true} cachedAt="2026-05-25T10:00:00" />
 */
export default memo(function DataFreshnessBadge({ level, label, serverStale = false, cachedAt }) {
  if (!label && !serverStale) return null;

  return (
    <span style={{ display: 'inline-flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
      {serverStale && (
        <span className="mock-data-badge" aria-live="polite" title={cachedAt ? `缓存时间: ${cachedAt}` : undefined}>
          <span className="mock-data-badge__dot" />
          使用缓存数据
        </span>
      )}
      {label && (
        <span className={`freshness-badge freshness-badge--${level}`} aria-live="polite">
          <span className="freshness-badge__dot" />
          {label}
        </span>
      )}
    </span>
  );
})
