/**
 * @fileoverview 迷你折线图组件 - SVG 实现的迷你趋势图
 * @module components/Sparkline
 * @description 使用 SVG 绘制的迷你折线图，支持渐变填充、趋势颜色和数据点标记。
 * 使用 React.memo 优化渲染。
 */

import { memo, useMemo } from 'react';

/**
 * Sparkline - 迷你折线图组件（已优化：React.memo）
 *
 * @description
 * - 使用 SVG 绘制迷你折线图
 * - 支持渐变填充效果
 * - 根据趋势自动选择颜色（上涨绿色，下跌红色）
 * - 高亮最后一个数据点
 * - 可选显示所有数据点
 * - 数据不足 2 个点时显示空状态
 *
 * @param {Object} props - 组件属性
 * @param {Array<number|Object>} props.data - 数据数组，支持数字或包含 nav/value 的对象
 * @param {number} [props.width=120] - 图表宽度（像素）
 * @param {number} [props.height=32] - 图表高度（像素）
 * @param {string} [props.color='#7cb6ff'] - 渐变填充颜色
 * @param {boolean} [props.showDots=false] - 是否显示所有数据点
 * @returns {JSX.Element} SVG 迷你折线图
 *
 * @example
 * <Sparkline data={[10, 15, 12, 18, 20]} width={150} height={40} />
 * <Sparkline data={navHistory} showDots />
 */
export default memo(function Sparkline({ data = [], width = 120, height = 32, color = '#7cb6ff', showDots = false }) {
  /** 计算 SVG 绘图点坐标 */
  const points = useMemo(() => {
    if (!data || data.length < 2) return null;

    // 提取数值：支持数字或包含 nav/value 的对象
    const values = data.map((d) => (typeof d === 'number' ? d : d?.nav ?? d?.value ?? 0));
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    const padding = 2;

    // 将数值映射到 SVG 坐标
    return values.map((v, i) => ({
      x: padding + (i / (values.length - 1)) * (width - padding * 2),
      y: padding + (1 - (v - min) / range) * (height - padding * 2),
      value: v,
    }));
  }, [data, width, height]);

  // 数据不足时显示空状态
  if (!points || points.length < 2) {
    return (
      <div className="sparkline sparkline--empty" style={{ width, height }}>
        <span>—</span>
      </div>
    );
  }

  const polylinePoints = points.map((p) => `${p.x},${p.y}`).join(' ');
  const lastPoint = points[points.length - 1];
  const firstPoint = points[0];
  /** 趋势判断：最后一点 >= 第一点为上涨 */
  const trend = lastPoint.value >= firstPoint.value;

  return (
    <div className="sparkline" style={{ width, height }}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        {/* 渐变定义 */}
        <defs>
          <linearGradient id={`sparkline-grad-${color.replace('#', '')}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.3" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* 渐变填充区域 */}
        <polygon
          points={`${firstPoint.x},${height} ${polylinePoints} ${lastPoint.x},${height}`}
          fill={`url(#sparkline-grad-${color.replace('#', '')})`}
        />

        {/* 折线 */}
        <polyline
          points={polylinePoints}
          fill="none"
          stroke={trend ? '#86efac' : '#fca5a5'}
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* 数据点（可选） */}
        {showDots && points.map((p, i) => (
          <circle
            key={i}
            cx={p.x}
            cy={p.y}
            r="2"
            fill={trend ? '#86efac' : '#fca5a5'}
          />
        ))}

        {/* 最后一个数据点高亮 */}
        <circle
          cx={lastPoint.x}
          cy={lastPoint.y}
          r="3"
          fill={trend ? '#86efac' : '#fca5a5'}
          stroke="#0d1a2c"
          strokeWidth="1.5"
        />
      </svg>
    </div>
  );
})
