/**
 * @fileoverview 通用趋势折线图组件 - 基于 recharts
 * @module components/TrendChart
 * @description 可复用的趋势图，支持：
 * - 价格/净值折线 + 面积填充
 * - 成交量柱状图（可选）
 * - 涨跌幅颜色（红涨绿跌）
 * - 响应式尺寸
 * - Tooltip 悬浮提示
 */

import { useTranslation } from 'react-i18next';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

/**
 * 格式化数字
 */
function fmtNum(value, digits = 2) {
  const n = Number(value);
  if (Number.isNaN(n)) return '--';
  return n.toFixed(digits);
}

/**
 * 格式化成交量（万/亿）
 */
function fmtVolume(value) {
  const n = Number(value);
  if (Number.isNaN(n)) return '--';
  const abs = Math.abs(n);
  if (abs >= 1e8) return `${(abs / 1e8).toFixed(1)}亿`;
  if (abs >= 1e4) return `${(abs / 1e4).toFixed(1)}万`;
  return n.toFixed(0);
}

/**
 * 自定义 Tooltip
 */
function ChartTooltip({ active, payload, label, valueKey, valueLabel, valueSuffix }) {
  if (!active || !payload || !payload.length) return null;
  const point = payload[0]?.payload;
  if (!point) return null;

  return (
    <div className="trend-chart-tooltip">
      <div className="trend-chart-tooltip__date">{label}</div>
      <div className="trend-chart-tooltip__value">
        {valueLabel}: {fmtNum(point[valueKey])}{valueSuffix || ''}
      </div>
      {point.change_pct != null && (
        <div className={`trend-chart-tooltip__change ${Number(point.change_pct) >= 0 ? 'up' : 'down'}`}>
          {Number(point.change_pct) >= 0 ? '+' : ''}{fmtNum(point.change_pct)}%
        </div>
      )}
      {point.volume != null && point.volume > 0 && (
        <div className="trend-chart-tooltip__volume">
          成交量: {fmtVolume(point.volume)}
        </div>
      )}
    </div>
  );
}

/**
 * 价格/净值趋势图
 *
 * @component TrendChart
 * @param {Object} props
 * @param {Array} props.data - 数据数组，每项包含 { date, close/nav, volume?, change_pct? }
 * @param {string} [props.valueKey='close'] - 数值字段名
 * @param {string} [props.valueLabel='收盘价'] - 数值标签
 * @param {string} [props.valueSuffix=''] - 数值后缀
 * @param {boolean} [props.showVolume=false] - 是否显示成交量
 * @param {number} [props.height=260] - 图表高度
 * @param {string} [props.color] - 自定义颜色（不传则自动判断涨跌）
 * @returns {JSX.Element}
 */
export default function TrendChart({
  data,
  valueKey = 'close',
  valueLabel = '收盘价',
  valueSuffix = '',
  showVolume = false,
  height = 260,
  color,
}) {
  const { t } = useTranslation();

  if (!data || data.length === 0) {
    return (
      <div className="trend-chart-empty">
        <span>{t('common.noData', '暂无数据')}</span>
      </div>
    );
  }

  // Determine trend direction from first to last
  const firstVal = Number(data[0]?.[valueKey]) || 0;
  const lastVal = Number(data[data.length - 1]?.[valueKey]) || 0;
  const trendUp = lastVal >= firstVal;
  const lineColor = color || (trendUp ? '#ef4444' : '#22c55e'); // 红涨绿跌（A股规则）
  const fillColor = color || (trendUp ? 'rgba(239,68,68,0.1)' : 'rgba(34,197,94,0.1)');

  // Compute Y domain with padding
  const values = data.map((d) => Number(d[valueKey]) || 0).filter((v) => v > 0);
  const minVal = Math.min(...values);
  const maxVal = Math.max(...values);
  const padding = (maxVal - minVal) * 0.05 || 1;
  const yDomain = [Math.max(0, minVal - padding), maxVal + padding];

  if (showVolume) {
    // Combined chart: price area + volume bars
    return (
      <div className="trend-chart">
        <ResponsiveContainer width="100%" height={height}>
          <ComposedChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="trendFillGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={lineColor} stopOpacity={0.2} />
                <stop offset="100%" stopColor={lineColor} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(120,140,160,0.12)" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: '#6b7280' }}
              tickFormatter={(v) => (v?.length > 5 ? v.slice(5) : v)}
              interval="preserveStartEnd"
              minTickGap={40}
            />
            <YAxis
              domain={yDomain}
              tick={{ fontSize: 10, fill: '#6b7280' }}
              tickFormatter={(v) => fmtNum(v, 2)}
              width={60}
              yAxisId="price"
            />
            <YAxis
              orientation="right"
              tick={{ fontSize: 10, fill: '#6b7280' }}
              tickFormatter={fmtVolume}
              width={50}
              yAxisId="vol"
            />
            <Tooltip
              content={
                <ChartTooltip
                  valueKey={valueKey}
                  valueLabel={valueLabel}
                  valueSuffix={valueSuffix}
                />
              }
            />
            <Bar
              yAxisId="vol"
              dataKey="volume"
              fill="rgba(120,140,160,0.15)"
              isAnimationActive={false}
            />
            <Area
              yAxisId="price"
              type="monotone"
              dataKey={valueKey}
              stroke={lineColor}
              strokeWidth={2}
              fill="url(#trendFillGradient)"
              dot={false}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    );
  }

  // Simple area chart
  return (
    <div className="trend-chart">
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="trendFillGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={lineColor} stopOpacity={0.2} />
              <stop offset="100%" stopColor={lineColor} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(120,140,160,0.12)" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: '#6b7280' }}
            tickFormatter={(v) => (v?.length > 5 ? v.slice(5) : v)}
            interval="preserveStartEnd"
            minTickGap={40}
          />
          <YAxis
            domain={yDomain}
            tick={{ fontSize: 10, fill: '#6b7280' }}
            tickFormatter={(v) => fmtNum(v, 2)}
            width={60}
          />
          <Tooltip
            content={
              <ChartTooltip
                valueKey={valueKey}
                valueLabel={valueLabel}
                valueSuffix={valueSuffix}
              />
            }
          />
          <Area
            type="monotone"
            dataKey={valueKey}
            stroke={lineColor}
            strokeWidth={2}
            fill="url(#trendFillGradient)"
            dot={false}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
