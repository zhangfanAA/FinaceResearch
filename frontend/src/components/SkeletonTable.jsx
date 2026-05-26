/**
 * @fileoverview 骨架屏表格组件 - 数据加载时的占位动画
 * @module components/SkeletonTable
 * @description 显示带闪烁动画的骨架屏表格，用于数据加载时的占位显示。
 * 使用 React.memo 优化渲染。
 */

import { memo } from 'react';

/**
 * SkeletonTable - 骨架屏表格组件（已优化：React.memo）
 *
 * @description
 * - 显示带闪烁动画的表格骨架屏
 * - 表头行使用较深的背景色
 * - 数据行的骨架条宽度随机变化，模拟真实数据
 * - 使用 aria-busy 和 aria-label 提供无障碍支持
 * - 使用 shimmer 动画实现闪烁效果
 *
 * @param {Object} props - 组件属性
 * @param {number} [props.rows=5] - 骨架数据行数
 * @param {number} [props.columns=4] - 骨架列数
 * @returns {JSX.Element} 骨架屏表格组件
 *
 * @example
 * <SkeletonTable rows={5} columns={6} />
 * <SkeletonTable rows={3} columns={3} />
 */
export default memo(function SkeletonTable({ rows = 5, columns = 4 }) {
  return (
    <div className="skeleton-table" aria-busy="true" aria-label="加载中">
      {/* 表头行 */}
      <div className="skeleton-table__row skeleton-table__row--header">
        {Array.from({ length: columns }).map((_, colIdx) => (
          <div
            key={colIdx}
            className="skeleton-table__cell skeleton-table__cell--header"
          >
            <div className="skeleton-table__bar" />
          </div>
        ))}
      </div>
      {/* 数据行 */}
      {Array.from({ length: rows }).map((_, rowIdx) => (
        <div key={rowIdx} className="skeleton-table__row">
          {Array.from({ length: columns }).map((_, colIdx) => (
            <div key={colIdx} className="skeleton-table__cell">
              <div
                className="skeleton-table__bar"
                style={{ width: `${50 + Math.random() * 40}%` }}
              />
            </div>
          ))}
        </div>
      ))}
    </div>
  );
})
