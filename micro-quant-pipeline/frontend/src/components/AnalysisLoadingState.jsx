/**
 * @fileoverview AI 分析加载状态组件 - 显示分析进度和步骤
 * @module components/AnalysisLoadingState
 * @description 用于 AI 分析过程中的加载动画，包含进度条、步骤指示器和骨架屏
 */

/**
 * AnalysisLoadingState - AI 分析加载动画组件
 *
 * @description
 * - 显示带进度条的步骤指示器
 * - 当前步骤高亮显示
 * - 底部显示骨架屏占位符
 * - 支持自定义状态消息
 * - 使用 aria-live="polite" 确保屏幕阅读器可访问
 *
 * @param {Object} props - 组件属性
 * @param {string[]} props.steps - 步骤标签数组（如 ["获取数据", "AI 分析", "生成报告"]）
 * @param {number} props.currentStep - 当前活动步骤的索引（从 0 开始）
 * @param {string} [props.message=''] - 可选的状态消息
 * @returns {JSX.Element} 加载状态组件
 *
 * @example
 * <AnalysisLoadingState
 *   steps={["获取板块数据", "AI 分析中", "生成分析报告"]}
 *   currentStep={1}
 *   message="正在分析中，请稍候..."
 * />
 */
export default function AnalysisLoadingState({ steps = [], currentStep = 0, message = '' }) {
  const totalSteps = steps.length || 1;
  const progress = ((currentStep + 1) / totalSteps) * 100;

  return (
    <div className="research-loading" aria-live="polite">
      {/* 进度条 */}
      <div className="research-progress">
        <div
          className="research-progress__bar step-transition"
          style={{ width: `${progress}%` }}
        />
      </div>
      {/* 步骤指示器 */}
      <div className="research-steps">
        {steps.map((step, index) => (
          <div
            key={step}
            className={`research-step ${index <= currentStep ? 'research-step--active' : ''}`}
          >
            <span className="research-step__dot" />
            <span>{step}</span>
          </div>
        ))}
      </div>
      {/* 骨架屏占位 */}
      <div className="research-loading__skeleton">
        <div className="research-loading__line" />
        <div className="research-loading__line research-loading__line--short" />
        <div className="research-loading__line" />
      </div>
      {/* 状态消息 */}
      {message ? <p>{message}</p> : null}
    </div>
  );
}
