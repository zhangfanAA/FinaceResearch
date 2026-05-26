/**
 * @fileoverview 语言切换组件 - 中英文切换按钮
 * @module components/LanguageSwitcher
 * @description 提供中英文切换功能，显示当前语言并支持点击切换
 */

import { useTranslation } from 'react-i18next';

/**
 * LanguageSwitcher - 语言切换按钮组件
 *
 * @description
 * - 显示 "中 / EN" 样式的切换按钮
 * - 当前语言高亮显示
 * - 点击在中文和英文之间切换
 * - 使用 i18next 的 changeLanguage 方法
 * - 支持无障碍访问（aria-label）
 *
 * @returns {JSX.Element} 语言切换按钮
 *
 * @example
 * <LanguageSwitcher />
 */
export default function LanguageSwitcher() {
  const { i18n } = useTranslation();
  /** @type {string} 当前语言标识 */
  const current = i18n.language?.startsWith('en') ? 'en' : 'zh';

  /** 切换语言 */
  function toggle() {
    const next = current === 'zh' ? 'en' : 'zh';
    i18n.changeLanguage(next);
  }

  return (
    <button
      type="button"
      className="language-switcher"
      onClick={toggle}
      aria-label={current === 'zh' ? 'Switch to English' : '切换到中文'}
    >
      <span className={`language-switcher__option ${current === 'zh' ? 'language-switcher__option--active' : ''}`}>
        中
      </span>
      <span className="language-switcher__divider">/</span>
      <span className={`language-switcher__option ${current === 'en' ? 'language-switcher__option--active' : ''}`}>
        EN
      </span>
    </button>
  );
}
