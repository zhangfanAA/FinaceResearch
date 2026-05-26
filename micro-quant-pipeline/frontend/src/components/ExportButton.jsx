/**
 * @fileoverview 导出按钮组件 - 提供 JSON 和 Markdown 格式的数据导出功能
 * @module components/ExportButton
 * @description 下拉菜单式导出按钮，支持将分析结果导出为 JSON 或 Markdown 文件。
 * 使用 React.memo 优化渲染。
 */

import { memo, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import useToast from '../hooks/useToast';

/**
 * 下载 Blob 数据为文件
 *
 * @param {string} content - 文件内容
 * @param {string} filename - 文件名
 * @param {string} mimeType - MIME 类型
 */
function downloadBlob(content, filename, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * 将分析结果转换为 Markdown 格式
 *
 * @param {Object} data - 分析结果数据
 * @param {Function} t - 国际化翻译函数
 * @returns {string} Markdown 格式的字符串
 */
function toMarkdown(data, t) {
  const target = data.target_sector || data.target_name || data.fund_name || data.fund_code || data.target_code || '--';
  const trend = data.trend || data.judgment || '--';
  const sentiment = data.sentiment_score != null ? (data.sentiment_score * 100).toFixed(0) + '%' : '--';
  const confidence = data.confidence != null ? (data.confidence * 100).toFixed(0) + '%' : '--';

  let md = `# ${t('analysisHistory.result')}: ${target}\n\n`;
  md += `- ${t('comparison.trend')}: ${trend}\n`;
  md += `- ${t('comparison.sentiment')}: ${sentiment}\n`;
  md += `- ${t('comparison.confidence')}: ${confidence}\n`;

  if (data.suggestion) {
    md += `- ${t('comparison.suggestion')}: ${data.suggestion}\n`;
  }

  md += '\n';

  const reasoning = data.reasoning || data.logic;
  if (reasoning) {
    md += `## ${t('comparison.reasoning')}\n\n`;
    md += `${reasoning}\n\n`;
  }

  const factors = data.key_factors;
  if (factors && factors.length > 0) {
    md += `## ${t('comparison.keyFactors')}\n\n`;
    factors.forEach((f) => {
      md += `- ${f}\n`;
    });
    md += '\n';
  }

  const risks = data.risk_warnings || data.risk_factors;
  if (risks && risks.length > 0) {
    md += `## ${t('comparison.riskWarnings')}\n\n`;
    risks.forEach((r) => {
      md += `- ${r}\n`;
    });
    md += '\n';
  }

  return md;
}

/**
 * ExportButton - 数据导出按钮组件（已优化：React.memo）
 *
 * @description
 * - 点击按钮展开下拉菜单，提供 JSON 和 Markdown 两种导出格式
 * - 点击外部区域自动关闭下拉菜单
 * - 导出成功后显示 Toast 提示
 * - 支持小图标按钮模式（size="sm"）
 * - 使用 React.memo 避免父组件重渲染时不必要的更新
 *
 * @param {Object} props - 组件属性
 * @param {Object} props.data - 要导出的分析结果数据
 * @param {string} [props.filename='analysis-export'] - 导出文件名前缀
 * @param {string} [props.size] - 按钮尺寸，'sm' 为小图标模式
 * @returns {JSX.Element} 导出按钮组件
 *
 * @example
 * <ExportButton data={analysisResult} filename="stock-analysis-600519" />
 * <ExportButton data={item} size="sm" />
 */
export default memo(function ExportButton({ data, filename = 'analysis-export', size }) {
  const { t } = useTranslation();
  const { showToast } = useToast();
  /** @type {[boolean, Function]} 下拉菜单展开状态 */
  const [open, setOpen] = useState(false);
  /** @type {React.RefObject<HTMLElement>} 组件容器引用（用于检测外部点击） */
  const wrapperRef = useRef(null);

  // 点击外部区域关闭下拉菜单
  useEffect(() => {
    if (!open) return;
    function handleClick(event) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open]);

  /** 导出为 JSON 文件 */
  function handleExportJson() {
    if (!data) return;
    const json = JSON.stringify(data, null, 2);
    downloadBlob(json, `${filename}.json`, 'application/json');
    showToast(t('toast.exportSuccess'), 'success');
    setOpen(false);
  }

  /** 导出为 Markdown 文件 */
  function handleExportMarkdown() {
    if (!data) return;
    const md = toMarkdown(data, t);
    downloadBlob(md, `${filename}.md`, 'text/markdown');
    showToast(t('toast.exportSuccess'), 'success');
    setOpen(false);
  }

  const isSmall = size === 'sm';

  return (
    <div className="export-button" ref={wrapperRef}>
      <button
        type="button"
        className={`button ${isSmall ? 'button--sm' : 'button--secondary'}`}
        onClick={() => setOpen((prev) => !prev)}
        disabled={!data}
      >
        {isSmall ? '\u2B07' : t('export.json')}
      </button>

      {/* 下拉菜单 */}
      {open ? (
        <div className="export-button__dropdown">
          <button type="button" className="export-button__option" onClick={handleExportJson}>
            {t('export.json')}
          </button>
          <button type="button" className="export-button__option" onClick={handleExportMarkdown}>
            {t('export.markdown')}
          </button>
        </div>
      ) : null}
    </div>
  );
})
