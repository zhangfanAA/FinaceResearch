/**
 * @fileoverview 带重试按钮的错误提示组件
 * @module components/ErrorWithRetry
 * @description 显示错误消息并提供重试按钮，常用于数据加载失败的场景
 */

/**
 * ErrorWithRetry - 带重试按钮的错误提示组件
 *
 * @description
 * - 显示红色错误消息
 * - 提供重试按钮，点击触发重试回调
 * - 支持重试中状态（按钮禁用并显示加载文本）
 *
 * @param {Object} props - 组件属性
 * @param {string} props.message - 错误消息文本
 * @param {Function} props.onRetry - 点击重试按钮时的回调函数
 * @param {boolean} [props.retrying=false] - 是否正在重试中
 * @returns {JSX.Element} 错误提示组件
 *
 * @example
 * <ErrorWithRetry
 *   message="数据加载失败"
 *   onRetry={loadData}
 *   retrying={isLoading}
 * />
 */
export default function ErrorWithRetry({ message, onRetry, retrying = false }) {
  return (
    <div className="error-with-retry">
      <div className="inline-alert inline-alert--error">
        {message || '数据加载失败'}
      </div>
      <button
        type="button"
        className="button button--sm button--secondary"
        onClick={onRetry}
        disabled={retrying}
      >
        {retrying ? '重试中...' : '重试'}
      </button>
    </div>
  );
}
