/**
 * @fileoverview Toast 通知 Hook 和 Context - 提供全局 Toast 通知功能
 * @module hooks/useToast
 * @description
 * - ToastProvider：React Context Provider，管理 Toast 状态
 * - useToast：Hook，用于在组件中显示/关闭 Toast 通知
 * - 支持 success、error、warning、info 四种类型
 * - 自动消失（可配置时长）
 * - 最多同时显示 5 条通知
 */

import { createContext, useCallback, useContext, useRef, useState } from 'react';

/** @type {number} 最大同时显示的 Toast 数量 */
const MAX_TOASTS = 5;
/** @type {number} 默认自动消失时长（毫秒） */
const DEFAULT_DURATION = 3000;

/**
 * Toast Context - 提供 Toast 状态和操作方法
 * @type {React.Context<Object|null>}
 */
export const ToastContext = createContext(null);

/**
 * ToastProvider - Toast 状态管理 Provider 组件
 *
 * @description
 * - 包裹应用根组件，提供 Toast 状态管理
 * - 管理 Toast 列表的添加、删除和自动消失
 * - 超过 MAX_TOASTS 限制时自动移除最旧的通知
 *
 * @param {Object} props - 组件属性
 * @param {React.ReactNode} props.children - 子组件
 * @returns {JSX.Element} 包含 Toast Context 的 Provider 组件
 *
 * @example
 * <ToastProvider>
 *   <App />
 *   <ToastContainer />
 * </ToastProvider>
 */
export function ToastProvider({ children }) {
  /** @type {[Array, Function]} Toast 列表状态 */
  const [toasts, setToasts] = useState([]);
  /** @type {React.RefObject<number>} Toast ID 自增计数器 */
  const counterRef = useRef(0);

  /**
   * 关闭指定 Toast
   *
   * @param {number} id - 要关闭的 Toast ID
   */
  const dismissToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  /**
   * 显示一条 Toast 通知
   *
   * @param {string} message - 通知消息文本
   * @param {'info'|'success'|'warning'|'error'} [type='info'] - 通知类型
   * @param {number} [duration=3000] - 自动消失时长（毫秒），0 表示不自动消失
   * @returns {number} 新创建的 Toast ID
   */
  const showToast = useCallback((message, type = 'info', duration = DEFAULT_DURATION) => {
    const id = ++counterRef.current;
    setToasts((prev) => {
      const next = [...prev, { id, message, type }];
      // 保持最多 MAX_TOASTS 条通知
      if (next.length > MAX_TOASTS) return next.slice(-MAX_TOASTS);
      return next;
    });

    // 设置自动消失定时器
    if (duration > 0) {
      setTimeout(() => {
        dismissToast(id);
      }, duration);
    }

    return id;
  }, [dismissToast]);

  return (
    <ToastContext.Provider value={{ toasts, showToast, dismissToast }}>
      {children}
    </ToastContext.Provider>
  );
}

/**
 * useToast - 获取 Toast 操作方法的 Hook
 *
 * @description 必须在 ToastProvider 内部使用，否则抛出错误
 *
 * @returns {Object} Toast 操作对象
 * @property {Array} toasts - 当前 Toast 列表
 * @property {Function} showToast - 显示 Toast 的函数
 * @property {Function} dismissToast - 关闭 Toast 的函数
 *
 * @example
 * const { showToast, dismissToast } = useToast();
 *
 * showToast('操作成功', 'success');
 * showToast('加载失败', 'error', 5000);
 */
export default function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within a ToastProvider');
  return ctx;
}
