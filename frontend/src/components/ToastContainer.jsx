/**
 * @fileoverview Toast 通知容器组件 - 渲染和管理 Toast 通知列表
 * @module components/ToastContainer
 * @description 从 useToast Hook 获取 Toast 列表并渲染，支持多种通知类型和退出动画
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import useToast from '../hooks/useToast';

/** @type {Object} 通知类型对应的图标映射 */
const ICONS = {
  success: '\u2713',   // 勾号
  error: '\u2717',     // 叉号
  warning: '\u26A0',   // 警告三角
  info: '\u2139',      // 信息圆圈
};

/**
 * ToastItem - 单条 Toast 通知组件
 *
 * @description
 * - 显示带图标的通知消息
 * - 支持关闭按钮
 * - 关闭时播放退出动画
 *
 * @param {Object} props - 组件属性
 * @param {Object} props.toast - Toast 数据对象
 * @param {number} props.toast.id - Toast 唯一 ID
 * @param {string} props.toast.message - 通知消息
 * @param {'info'|'success'|'warning'|'error'} props.toast.type - 通知类型
 * @param {Function} props.onDismiss - 关闭 Toast 的回调
 * @returns {JSX.Element} 单条 Toast 通知
 */
function ToastItem({ toast, onDismiss }) {
  const { t } = useTranslation();
  /** @type {[boolean, Function]} 退出动画状态 */
  const [exiting, setExiting] = useState(false);

  /** 处理关闭（先播放动画再移除） */
  function handleDismiss() {
    setExiting(true);
    setTimeout(() => onDismiss(toast.id), 250);
  }

  return (
    <div
      className={`toast-item toast-item--${toast.type} ${exiting ? 'toast-item--exit' : ''}`}
      role="alert"
      aria-live="polite"
    >
      <span className="toast-item__icon">{ICONS[toast.type] || ICONS.info}</span>
      <span className="toast-item__message">{toast.message}</span>
      <button
        type="button"
        className="toast-item__close"
        onClick={handleDismiss}
        aria-label={t('toast.close')}
      >
        {'\u2715'}
      </button>
    </div>
  );
}

/**
 * ToastContainer - Toast 通知容器组件
 *
 * @description
 * - 从 useToast Hook 获取当前 Toast 列表
 * - 列表为空时不渲染任何内容
 * - 渲染固定定位的通知容器
 *
 * @returns {JSX.Element|null} Toast 通知容器，列表为空时返回 null
 *
 * @example
 * // 在 App 组件中使用
 * <ToastContainer />
 */
export default function ToastContainer() {
  const { toasts, dismissToast } = useToast();

  if (toasts.length === 0) return null;

  return (
    <div className="toast-container" aria-label="Notifications">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onDismiss={dismissToast} />
      ))}
    </div>
  );
}
