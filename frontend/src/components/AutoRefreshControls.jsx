/**
 * @fileoverview 自动刷新控制组件 - 切换按钮和倒计时显示
 * @module components/AutoRefreshControls
 * @description 提供自动刷新的开关按钮和倒计时显示，支持暂停状态。使用 React.memo 优化渲染。
 */

import { memo } from 'react';

/**
 * AutoRefreshControls - 自动刷新控制组件（已优化：React.memo）
 *
 * @description
 * - 显示自动刷新的启用/禁用按钮
 * - 启用时显示倒计时秒数
 * - 暂停时显示"已暂停"标识（如 AI 分析进行中）
 * - 按钮样式根据状态变化
 * - 使用 React.memo 避免父组件重渲染时不必要的更新
 *
 * @param {Object} props - 组件属性
 * @param {boolean} props.enabled - 自动刷新是否启用
 * @param {Function} props.onToggle - 切换自动刷新状态的回调
 * @param {number} props.secondsUntilRefresh - 距离下次刷新的倒计时秒数
 * @param {boolean} [props.paused=false] - 是否处于暂停状态（如 AI 分析中）
 * @returns {JSX.Element} 自动刷新控制组件
 *
 * @example
 * <AutoRefreshControls
 *   enabled={autoRefreshEnabled}
 *   onToggle={toggleAutoRefresh}
 *   secondsUntilRefresh={45}
 *   paused={isAnalyzing}
 * />
 */
export default memo(function AutoRefreshControls({ enabled, onToggle, secondsUntilRefresh, paused = false }) {
  const label = paused
    ? '自动刷新: 已暂停'
    : enabled
      ? `自动刷新: 开 (${secondsUntilRefresh}s)`
      : '自动刷新: 关';

  return (
    <div className="auto-refresh-controls">
      <button
        type="button"
        className={`button button--sm ${enabled && !paused ? 'button--auto-refresh-on' : 'button--secondary'}`}
        onClick={onToggle}
        title={paused ? 'AI 分析进行中，自动刷新已暂停' : enabled ? '关闭自动刷新' : '开启自动刷新'}
      >
        {label}
      </button>
    </div>
  );
})
