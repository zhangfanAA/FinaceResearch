/**
 * @fileoverview 数据源徽章组件 - 显示当前活跃的历史数据源
 * @module components/DataSourceBadge
 * @description 从后端获取当前活跃数据源设置并显示为徽章。
 * 用于各面板标题栏，让用户知道当前使用的是哪个数据源。
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getDataSourcePreference } from '../api/client';

/**
 * 数据源显示名称映射
 */
const SOURCE_LABELS = {
  auto: 'Auto',
  tushare: 'Tushare',
  baostock: 'Baostock',
  efinance: 'efinance',
  akshare: 'AkShare',
  deepseek: 'DeepSeek',
};

/**
 * DataSourceBadge - 数据源徽章组件
 *
 * @param {Object} props
 * @param {string} [props.className] - 额外的 CSS 类名
 * @returns {JSX.Element|null} 数据源徽章，加载中返回 null
 */
export default function DataSourceBadge({ className = '' }) {
  const { t } = useTranslation();
  const [source, setSource] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getDataSourcePreference()
      .then((res) => {
        if (!cancelled) setSource(res?.active_source || 'auto');
      })
      .catch(() => {
        if (!cancelled) setSource('auto');
      });
    return () => { cancelled = true; };
  }, []);

  if (source === null) return null;

  const label = SOURCE_LABELS[source] || source;
  const variantClass = source === 'deepseek' ? 'data-source-badge--deepseek' : '';

  return (
    <span className={`data-source-badge ${variantClass} ${className}`} title={t('dataSourceSelector.activeSource', '当前数据源')}>
      <span className="data-source-badge__dot" />
      {label}
    </span>
  );
}
