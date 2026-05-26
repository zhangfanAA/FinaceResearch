/**
 * @fileoverview 主题切换 Hook - 管理深色/浅色主题状态
 * @module hooks/useTheme
 * @description 提供主题切换功能，支持深色和浅色两种主题，
 * 主题偏好持久化到 localStorage，并同步更新 document 属性
 */

import { useCallback, useEffect, useState } from 'react';

/** @type {string} localStorage 存储键名 */
const STORAGE_KEY = 'theme';
/** @type {string} 深色主题标识 */
const THEME_DARK = 'dark';
/** @type {string} 浅色主题标识 */
const THEME_LIGHT = 'light';

/**
 * 获取初始主题值
 *
 * @description 优先从 localStorage 读取，无效值或读取失败时默认为深色主题
 * @returns {string} 主题标识（'dark' 或 'light'）
 */
function getInitialTheme() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === THEME_DARK || stored === THEME_LIGHT) return stored;
  } catch {
    // localStorage 不可用时静默处理
  }
  return THEME_DARK;
}

/**
 * useTheme - 主题管理 Hook
 *
 * @description
 * - 管理深色/浅色主题状态
 * - 主题变更时自动更新 document.documentElement 的 data-theme 属性
 * - 主题偏好持久化到 localStorage
 * - 提供 toggleTheme 切换函数和 isDark 布尔值
 *
 * @returns {Object} 主题控制对象
 * @property {string} theme - 当前主题标识（'dark' 或 'light'）
 * @property {Function} toggleTheme - 切换主题的函数
 * @property {boolean} isDark - 当前是否为深色主题
 *
 * @example
 * const { theme, toggleTheme, isDark } = useTheme();
 *
 * <button onClick={toggleTheme}>
 *   {isDark ? '切换到浅色' : '切换到深色'}
 * </button>
 */
export default function useTheme() {
  /** @type {[string, Function]} 当前主题状态 */
  const [theme, setTheme] = useState(getInitialTheme);

  // 同步主题到 DOM 和 localStorage
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // localStorage 不可用时静默处理
    }
  }, [theme]);

  /**
   * 切换主题（深色 <-> 浅色）
   * @type {Function}
   */
  const toggleTheme = useCallback(() => {
    setTheme((prev) => (prev === THEME_DARK ? THEME_LIGHT : THEME_DARK));
  }, []);

  return { theme, toggleTheme, isDark: theme === THEME_DARK };
}
