/**
 * @fileoverview 应用入口文件 - 初始化 React 根节点并挂载 App 组件
 * @module main
 * @description
 * - 导入 i18n 配置以激活国际化
 * - 导入全局样式
 * - 使用 React 18 的 createRoot API 挂载应用
 * - 启用 StrictMode 以在开发模式下检测潜在问题
 */

import React from 'react';
import ReactDOM from 'react-dom/client';
import './i18n';
import App from './App.jsx';
import './styles.css';

/**
 * 挂载 React 应用到 DOM 根节点
 *
 * @description
 * - document.getElementById('root') 对应 index.html 中的 <div id="root">
 * - React.StrictMode 在开发模式下会双重渲染组件以检测副作用
 */
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
