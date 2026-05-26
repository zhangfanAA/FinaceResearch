/**
 * @fileoverview 错误边界组件 - 捕获子组件渲染错误并显示友好的错误页面
 * @module components/ErrorBoundary
 * @description React 错误边界，捕获子组件树中的 JavaScript 渲染错误，
 * 防止整个应用崩溃，提供重新加载和返回首页的操作
 */

import { Component } from 'react';
import { withTranslation } from 'react-i18next';

/**
 * ErrorBoundary - React 错误边界类组件
 *
 * @description
 * - 捕获子组件树中的渲染错误、生命周期和构造函数中的错误
 * - 显示友好的错误页面，包含错误信息和操作按钮
 * - 支持展开/折叠详细错误堆栈信息
 * - 使用 withTranslation HOC 支持国际化
 *
 * @param {Object} props - 组件属性
 * @param {React.ReactNode} props.children - 子组件
 * @param {Function} props.t - 国际化翻译函数
 * @returns {JSX.Element} 错误页面或正常渲染的子组件
 *
 * @example
 * <ErrorBoundary>
 *   <MyComponent />
 * </ErrorBoundary>
 */
class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = {
      /** @type {boolean} 是否捕获到错误 */
      hasError: false,
      /** @type {Error|null} 捕获到的错误对象 */
      error: null,
      /** @type {Object|null} 错误组件堆栈信息 */
      errorInfo: null,
      /** @type {boolean} 是否显示详细错误信息 */
      showDetails: false,
    };
  }

  /**
   * 从错误中派生状态（静态方法）
   *
   * @param {Error} error - 捕获到的错误
   * @returns {Object} 更新后的状态
   */
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  /**
   * 捕获错误后的回调，记录错误详情
   *
   * @param {Error} error - 捕获到的错误
   * @param {Object} errorInfo - React 组件堆栈信息
   */
  componentDidCatch(error, errorInfo) {
    this.setState({ errorInfo });
    console.error('[ErrorBoundary] Caught error:', error, errorInfo);
  }

  /** 重新加载页面 */
  handleReload = () => {
    window.location.reload();
  };

  /** 返回首页 */
  handleGoHome = () => {
    window.location.href = '/';
  };

  /** 切换详细信息显示状态 */
  toggleDetails = () => {
    this.setState((prev) => ({ showDetails: !prev.showDetails }));
  };

  render() {
    const { t, children } = this.props;
    const { hasError, error, errorInfo, showDetails } = this.state;

    // 未捕获错误时正常渲染子组件
    if (!hasError) {
      return children;
    }

    // 捕获错误后显示友好的错误页面
    return (
      <div className="error-boundary">
        <div className="error-boundary__card">
          <div className="error-boundary__icon" aria-hidden="true">
            {'\u26A0'}
          </div>
          <h1 className="error-boundary__title">{t('errorBoundary.title')}</h1>
          <p className="error-boundary__description">{t('errorBoundary.description')}</p>
          <p className="error-boundary__message">{error?.message}</p>
          <div className="error-boundary__actions">
            <button type="button" className="button" onClick={this.handleReload}>
              {t('errorBoundary.reload')}
            </button>
            <button type="button" className="button button--secondary" onClick={this.handleGoHome}>
              {t('errorBoundary.goHome')}
            </button>
          </div>
          <button
            type="button"
            className="error-boundary__details-toggle"
            onClick={this.toggleDetails}
          >
            {showDetails ? t('errorBoundary.hideDetails') : t('errorBoundary.showDetails')}
          </button>
          {showDetails ? (
            <pre className="error-boundary__details">
              {error?.toString()}
              {'\n\n'}
              {errorInfo?.componentStack}
            </pre>
          ) : null}
        </div>
      </div>
    );
  }
}

export default withTranslation()(ErrorBoundary);
