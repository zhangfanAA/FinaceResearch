/**
 * @fileoverview 技术指标图表组件 - 展示 RSI、MACD、KDJ、布林带等技术指标
 * @module components/TechnicalChart
 * @description 使用 SVG 和 CSS 实现的技术指标可视化组件，包含仪表盘、柱状图和均线图
 */

import { useMemo } from 'react';

/**
 * Gauge - 仪表盘组件（内部组件）
 *
 * @description 带颜色区间和指针的水平仪表盘
 *
 * @param {Object} props - 组件属性
 * @param {number} props.value - 当前值
 * @param {number} [props.min=0] - 最小值
 * @param {number} [props.max=100] - 最大值
 * @param {string} props.label - 标签文本
 * @param {Array<Object>} [props.zones] - 颜色区间配置数组
 * @returns {JSX.Element} 仪表盘组件
 */
function Gauge({ value, min = 0, max = 100, label, zones }) {
  const normalized = Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100));
  const color = zones
    ? zones.find((z) => value >= z.min && value <= z.max)?.color || '#7cb6ff'
    : '#7cb6ff';

  return (
    <div className="tech-gauge">
      <div className="tech-gauge__label">{label}</div>
      <div className="tech-gauge__track">
        {zones?.map((z) => (
          <div
            key={z.label}
            className="tech-gauge__zone"
            style={{
              left: `${((z.min - min) / (max - min)) * 100}%`,
              width: `${((z.max - z.min) / (max - min)) * 100}%`,
              background: `${z.color}20`,
            }}
          />
        ))}
        <div
          className="tech-gauge__fill"
          style={{ width: `${normalized}%`, background: color }}
        />
        <div
          className="tech-gauge__pointer"
          style={{ left: `${normalized}%` }}
        />
      </div>
      <div className="tech-gauge__value" style={{ color }}>
        {value != null ? value.toFixed(2) : '—'}
      </div>
    </div>
  );
}

/**
 * BarMeter - 柱状仪表组件（内部组件）
 *
 * @description 用于显示 MACD 等指标的水平柱状图
 *
 * @param {Object} props - 组件属性
 * @param {number} props.value - 指标值
 * @param {string} props.label - 标签文本
 * @param {boolean} [props.positive=true] - 是否为正值（决定颜色）
 * @returns {JSX.Element} 柱状仪表组件
 */
function BarMeter({ value, label, positive = true }) {
  const absVal = Math.abs(value ?? 0);
  const maxBar = Math.max(absVal, 1);
  const width = Math.min(100, (absVal / maxBar) * 100);
  const color = positive ? '#86efac' : '#fca5a5';

  return (
    <div className="tech-bar">
      <div className="tech-bar__label">{label}</div>
      <div className="tech-bar__track">
        <div
          className="tech-bar__fill"
          style={{ width: `${width}%`, background: color }}
        />
      </div>
      <div className="tech-bar__value" style={{ color }}>
        {value != null ? value.toFixed(4) : '—'}
      </div>
    </div>
  );
}

/**
 * MAViz - 均线可视化组件（内部组件）
 *
 * @description 使用 SVG 绘制 MA5/MA10/MA20/MA60 均线点和连线
 *
 * @param {Object} props - 组件属性
 * @param {number} props.ma5 - 5 日均线值
 * @param {number} props.ma10 - 10 日均线值
 * @param {number} props.ma20 - 20 日均线值
 * @param {number} props.ma60 - 60 日均线值
 * @returns {JSX.Element} 均线可视化组件
 */
function MAViz({ ma5, ma10, ma20, ma60 }) {
  const values = [ma5, ma10, ma20, ma60].filter((v) => v != null);
  if (values.length === 0) return <div className="empty-state">No MA data</div>;

  const min = Math.min(...values) * 0.99;
  const max = Math.max(...values) * 1.01;
  const range = max - min || 1;

  const points = [
    { label: 'MA5', value: ma5, color: '#7cb6ff' },
    { label: 'MA10', value: ma10, color: '#86efac' },
    { label: 'MA20', value: ma20, color: '#fbbf24' },
    { label: 'MA60', value: ma60, color: '#fca5a5' },
  ].filter((p) => p.value != null);

  return (
    <div className="tech-ma">
      <div className="tech-ma__label">Moving Averages</div>
      <div className="tech-ma__chart">
        {points.map((p, i) => {
          const x = (i / Math.max(points.length - 1, 1)) * 100;
          const y = 100 - ((p.value - min) / range) * 80;
          return (
            <div
              key={p.label}
              className="tech-ma__point"
              style={{
                left: `${x}%`,
                top: `${y}%`,
                background: p.color,
              }}
              title={`${p.label}: ${p.value.toFixed(2)}`}
            />
          );
        })}
        {points.length > 1 && (
          <svg className="tech-ma__line" viewBox="0 0 100 100" preserveAspectRatio="none">
            <polyline
              points={points
                .map((p, i) => {
                  const x = (i / Math.max(points.length - 1, 1)) * 100;
                  const y = 100 - ((p.value - min) / range) * 80;
                  return `${x},${y}`;
                })
                .join(' ')}
              fill="none"
              stroke="#7cb6ff"
              strokeWidth="0.5"
              vectorEffect="non-scaling-stroke"
            />
          </svg>
        )}
      </div>
      <div className="tech-ma__legend">
        {points.map((p) => (
          <span key={p.label} className="tech-ma__legend-item" style={{ color: p.color }}>
            {p.label}: {p.value.toFixed(2)}
          </span>
        ))}
      </div>
    </div>
  );
}

const RSI_ZONES = [
  { min: 0, max: 30, color: '#86efac', label: 'Oversold' },
  { min: 30, max: 70, color: '#7cb6ff', label: 'Neutral' },
  { min: 70, max: 100, color: '#fca5a5', label: 'Overbought' },
];

/**
 * TechnicalChart - 技术指标图表主组件
 *
 * @description
 * - 展示 RSI、MACD、KDJ、布林带等技术指标
 * - 包含均线可视化
 * - 使用仪表盘、柱状图等多种可视化形式
 * - 数据为空时显示空状态
 *
 * @param {Object} props - 组件属性
 * @param {Object} props.technicalSummary - 技术指标汇总数据
 * @returns {JSX.Element} 技术指标图表组件
 *
 * @example
 * <TechnicalChart technicalSummary={analysis.technical_summary} />
 */
export default function TechnicalChart({ technicalSummary }) {
  const data = useMemo(() => technicalSummary || {}, [technicalSummary]);

  if (!technicalSummary || Object.keys(technicalSummary).length === 0) {
    return (
      <div className="tech-chart tech-chart--empty">
        <p className="empty-state">No technical data available</p>
      </div>
    );
  }

  return (
    <div className="tech-chart">
      <div className="tech-chart__header">
        <h3>Technical Indicators</h3>
      </div>

      <MAViz
        ma5={data.ma5}
        ma10={data.ma10}
        ma20={data.ma20}
        ma60={data.ma60}
      />

      <div className="tech-chart__grid">
        <Gauge
          value={data.rsi_14}
          min={0}
          max={100}
          label="RSI (14)"
          zones={RSI_ZONES}
        />

        <div className="tech-chart__macd">
          <h4>MACD</h4>
          <BarMeter value={data.macd} label="MACD" positive={(data.macd ?? 0) >= 0} />
          <BarMeter value={data.macd_signal} label="Signal" positive={(data.macd_signal ?? 0) >= 0} />
          <BarMeter value={data.macd_hist} label="Histogram" positive={(data.macd_hist ?? 0) >= 0} />
        </div>

        <div className="tech-chart__kdj">
          <h4>KDJ</h4>
          <Gauge value={data.kdj_k} min={0} max={100} label="K" />
          <Gauge value={data.kdj_d} min={0} max={100} label="D" />
          <div className="tech-kdj-j">
            <span className="tech-kdj-j__label">J</span>
            <span
              className="tech-kdj-j__value"
              style={{
                color: (data.kdj_j ?? 50) > 80 ? '#fca5a5' : (data.kdj_j ?? 50) < 20 ? '#86efac' : '#7cb6ff',
              }}
            >
              {data.kdj_j != null ? data.kdj_j.toFixed(2) : '—'}
            </span>
          </div>
        </div>

        <div className="tech-chart__boll">
          <h4>Bollinger Bands</h4>
          <div className="tech-boll-visual">
            <div className="tech-boll-visual__band tech-boll-visual__band--upper">
              <span>Upper</span>
              <strong>{data.boll_upper?.toFixed(2) ?? '—'}</strong>
            </div>
            <div className="tech-boll-visual__band tech-boll-visual__band--middle">
              <span>Middle</span>
              <strong>{data.boll_middle?.toFixed(2) ?? '—'}</strong>
            </div>
            <div className="tech-boll-visual__band tech-boll-visual__band--lower">
              <span>Lower</span>
              <strong>{data.boll_lower?.toFixed(2) ?? '—'}</strong>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
