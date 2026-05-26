/**
 * @fileoverview 主题切换按钮组件 - 深色/浅色主题切换
 * @module components/ThemeToggle
 * @description 提供一个图标按钮，在深色和浅色主题之间切换，使用 SVG 图标
 */

import { useTranslation } from 'react-i18next';
import useTheme from '../hooks/useTheme';

/**
 * ThemeToggle - 主题切换按钮组件
 *
 * @description
 * - 点击按钮切换深色/浅色主题
 * - 深色模式下显示太阳图标（提示切换到浅色）
 * - 浅色模式下显示月亮图标（提示切换到深色）
 * - 使用 useTheme Hook 管理主题状态
 * - 支持无障碍访问（aria-label 和 title）
 *
 * @returns {JSX.Element} 主题切换按钮
 *
 * @example
 * <ThemeToggle />
 */
export default function ThemeToggle() {
  const { t } = useTranslation();
  const { toggleTheme, isDark } = useTheme();

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={toggleTheme}
      aria-label={t('theme.toggle')}
      title={isDark ? t('theme.light') : t('theme.dark')}
    >
      {isDark ? (
        /* 太阳图标 - 深色模式下显示，点击切换到浅色 */
        <svg className="theme-toggle__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="5" />
          <line x1="12" y1="1" x2="12" y2="3" />
          <line x1="12" y1="21" x2="12" y2="23" />
          <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
          <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
          <line x1="1" y1="12" x2="3" y2="12" />
          <line x1="21" y1="12" x2="23" y2="12" />
          <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
          <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
        </svg>
      ) : (
        /* 月亮图标 - 浅色模式下显示，点击切换到深色 */
        <svg className="theme-toggle__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      )}
    </button>
  );
}
