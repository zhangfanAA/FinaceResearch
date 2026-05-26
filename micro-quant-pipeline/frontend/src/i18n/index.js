/**
 * @fileoverview 国际化（i18n）配置模块
 * @module i18n
 * @description 初始化 i18next 国际化框架，支持中文（zh）和英文（en）两种语言，
 * 默认语言为中文，语言偏好持久化到 localStorage
 */

import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

/** @type {Object} 中文翻译资源 */
import zh from './locales/zh.json';
/** @type {Object} 英文翻译资源 */
import en from './locales/en.json';

/**
 * 初始化 i18next 配置
 *
 * @description
 * - 使用 LanguageDetector 自动检测用户语言偏好
 * - 使用 initReactI18next 桥接 React 组件
 * - 语言检测顺序：localStorage > 浏览器语言
 * - 语言偏好缓存到 localStorage
 * - 禁用 HTML 转义（React 已内置 XSS 防护）
 */
i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    /** 翻译资源映射 */
    resources: {
      zh: { translation: zh },
      en: { translation: en },
    },
    /** 后备语言：当检测语言不可用时使用中文 */
    fallbackLng: 'zh',
    /** 优先从 localStorage 读取语言偏好，默认中文 */
    lng: localStorage.getItem('i18nextLng') || 'zh',
    interpolation: {
      /** 禁用自动转义，React 已内置安全机制 */
      escapeValue: false,
    },
    detection: {
      /** 语言检测优先级：localStorage > 浏览器 navigator.language */
      order: ['localStorage', 'navigator'],
      /** 仅缓存到 localStorage */
      caches: ['localStorage'],
    },
  });

export default i18n;
