/**
 * @fileoverview 全局键盘快捷键 Hook - 注册全局键盘事件监听
 * @module hooks/useKeyboardShortcut
 * @description 提供全局键盘快捷键注册功能，自动跳过输入框等可编辑元素，
 * 支持 Ctrl/Cmd、Shift、Alt 组合键
 */

import { useEffect, useRef } from 'react';

/**
 * useKeyboardShortcut - 注册全局键盘快捷键
 *
 * @description
 * - 在 document 上注册 keydown 事件监听器
 * - 当焦点在 input、textarea 或 contentEditable 元素中时自动跳过
 *   （除非是 Ctrl/Cmd 组合键，如 Ctrl+K 应全局生效）
 * - 使用 ref 保持回调引用最新，避免不必要的事件监听器重建
 * - 组件卸载时自动清理事件监听器
 *
 * @param {string} key - 要监听的键名（如 'k'、'Escape'、'r'），不区分大小写
 * @param {Function} callback - 快捷键触发时的回调函数
 * @param {Object} [options] - 修饰键配置
 * @param {boolean} [options.ctrl] - 是否需要 Ctrl（Mac 上为 Cmd）键
 * @param {boolean} [options.shift] - 是否需要 Shift 键
 * @param {boolean} [options.alt] - 是否需要 Alt 键
 *
 * @example
 * // Ctrl+K 打开全局搜索
 * useKeyboardShortcut('k', () => setSearchOpen(true), { ctrl: true });
 *
 * // R 键刷新数据（输入框中不触发）
 * useKeyboardShortcut('r', refreshData);
 *
 * // Escape 关闭弹窗
 * useKeyboardShortcut('Escape', closeModal);
 */
export default function useKeyboardShortcut(key, callback, options = {}) {
  /** @type {React.RefObject<Function>} 回调函数引用（保持最新） */
  const callbackRef = useRef(callback);

  // 同步回调引用
  useEffect(() => {
    callbackRef.current = callback;
  }, [callback]);

  // 注册键盘事件监听
  useEffect(() => {
    /**
     * 处理键盘按下事件
     *
     * @param {KeyboardEvent} event - 键盘事件对象
     */
    function handleKeyDown(event) {
      const target = event.target;
      const tagName = target?.tagName?.toLowerCase();
      const isEditable = target?.isContentEditable;

      // 当焦点在输入区域时跳过（除非是 Ctrl/Cmd 组合键）
      if (!options.ctrl && (tagName === 'input' || tagName === 'textarea' || isEditable)) {
        return;
      }

      // 检查修饰键是否匹配
      const ctrlPressed = options.ctrl ? (event.ctrlKey || event.metaKey) : true;
      const shiftPressed = options.shift ? event.shiftKey : true;
      const altPressed = options.alt ? event.altKey : true;

      // 检查主键是否匹配
      const keyMatch = event.key.toLowerCase() === key.toLowerCase();

      if (keyMatch && ctrlPressed && shiftPressed && altPressed) {
        event.preventDefault();
        callbackRef.current(event);
      }
    }

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [key, options.ctrl, options.shift, options.alt]);
}
