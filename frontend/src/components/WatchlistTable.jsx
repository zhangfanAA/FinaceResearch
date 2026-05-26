/**
 * @fileoverview 自选列表表格组件 - 展示自选基金/股票的持仓和盈亏信息
 * @module components/WatchlistTable
 * @description 展示自选列表的表格视图，支持：
 * - 代码、名称、持仓金额、当前净值、盈亏、操作按钮
 * - 加仓/减仓操作触发
 * - AI 分析触发
 * - 删除自选
 * - 移动端响应式布局
 */

import { useTranslation } from 'react-i18next';

/**
 * 格式化数字显示
 * @function formatNumber
 * @param {*} value - 要格式化的值
 * @param {number} [fractionDigits=2] - 保留的小数位数
 * @returns {string} 格式化后的数字字符串，无效值返回 '--'
 */
function formatNumber(value, fractionDigits = 2) {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return '--';
  return numeric.toFixed(fractionDigits);
}

/**
 * 格式化百分比显示（带正负号）
 * @function formatPercent
 * @param {number} value - 数值
 * @returns {string} 格式化后的百分比字符串，无效值返回 '--'
 */
function formatPercent(value) {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return '--';
  const sign = numeric > 0 ? '+' : '';
  return `${sign}${numeric.toFixed(2)}%`;
}

/**
 * 获取涨跌颜色基调
 * @function getChangeTone
 * @param {number} value - 数值
 * @returns {'up'|'down'|'neutral'} 正数返回 'up'，负数返回 'down'，零返回 'neutral'
 */
function getChangeTone(value) {
  const numeric = Number(value);
  if (Number.isNaN(numeric) || numeric === 0) return 'neutral';
  return numeric > 0 ? 'up' : 'down';
}

/**
 * 自选列表表格组件
 *
 * @component WatchlistTable
 * @description 展示自选基金/股票的持仓信息表格
 *
 * @param {Object} props
 * @param {Array} props.items - 自选列表数据
 * @param {string} props.activeTab - 当前激活的子Tab（'fund' 或 'stock'）
 * @param {boolean} props.loading - 是否正在加载
 * @param {Function} props.onOperate - 操作回调（加仓/减仓），参数为 (item, operationType)
 * @param {Function} props.onAnalyze - AI 分析回调，参数为 (item)
 * @param {Function} props.onRemove - 删除回调，参数为 (itemId)
 * @param {Function} props.t - i18next 翻译函数
 * @returns {JSX.Element} 自选列表表格或加载/空状态
 */
export default function WatchlistTable({ items, activeTab, loading, onOperate, onAnalyze, onRemove, t, fundNavMap }) {
  if (loading) {
    return (
      <div className="watchlist-table-wrap">
        <p className="empty-state">{t('common.loading')}...</p>
      </div>
    );
  }

  if (!items || items.length === 0) {
    return (
      <div className="watchlist-table-wrap">
        <p className="empty-state">{t('watchlist.empty')}</p>
      </div>
    );
  }

  return (
    <div className="watchlist-table-wrap">
      <div className="table-wrap">
        <table className="watchlist-table">
          <thead>
            <tr>
              <th>{t('watchlist.code')}</th>
              <th>{t('watchlist.name')}</th>
              <th>{t('watchlistManagement.table.amount')}</th>
              <th>{t('watchlistManagement.table.currentNav')}</th>
              {activeTab === 'fund' && fundNavMap && (
                <>
                  <th className="watchlist-table__hide-mobile">{t('watchlist.fundHoldings.currentNav')} (RT)</th>
                  <th className="watchlist-table__hide-mobile">{t('watchlist.fundHoldings.dailyReturn')} (RT)</th>
                </>
              )}
              <th className="watchlist-table__hide-mobile">{t('watchlistManagement.table.dailyReturn')}</th>
              <th>{t('watchlistManagement.table.pnl')}</th>
              <th>{t('watchlistManagement.table.pnlPct')}</th>
              <th>{t('stockSector.table.action')}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => {
              const dailyTone = getChangeTone(item.daily_return);
              const pnlTone = getChangeTone(item.total_pnl || item.pnl_ratio);
              return (
                <tr key={item.id} className="watchlist-table__row">
                  <td className="watchlist-table__code">{item.code}</td>
                  <td className="watchlist-table__name">{item.name || '--'}</td>
                  <td>{formatNumber(item.purchase_amount || item.amount, 2)}</td>
                  <td>{formatNumber(item.current_nav || item.nav, 4)}</td>
                  {activeTab === 'fund' && fundNavMap && (
                    <>
                      <td className="watchlist-table__realtime-nav watchlist-table__hide-mobile">
                        {fundNavMap[item.code] ? formatNumber(fundNavMap[item.code].nav || fundNavMap[item.code].current_nav, 4) : '--'}
                      </td>
                      <td className={`watchlist-table__change watchlist-table__change--${fundNavMap[item.code] ? getChangeTone(fundNavMap[item.code].daily_return) : 'neutral'} watchlist-table__hide-mobile`}>
                        {fundNavMap[item.code] ? formatPercent(fundNavMap[item.code].daily_return) : '--'}
                      </td>
                    </>
                  )}
                  <td className={`watchlist-table__change watchlist-table__change--${dailyTone} watchlist-table__hide-mobile`}>
                    {formatPercent(item.daily_return)}
                  </td>
                  <td className={`watchlist-table__change watchlist-table__change--${pnlTone}`}>
                    {item.total_pnl != null ? (item.total_pnl >= 0 ? '+' : '') + formatNumber(item.total_pnl, 2) : '--'}
                  </td>
                  <td className={`watchlist-table__change watchlist-table__change--${pnlTone}`}>
                    {formatPercent(item.total_pnl_pct || item.pnl_ratio)}
                  </td>
                  <td>
                    <div className="watchlist-table__actions">
                      <button
                        type="button"
                        className="button button--sm"
                        onClick={() => onOperate(item, 'add')}
                        title={t('watchlistManagement.operations.addPosition')}
                      >
                        {t('watchlistManagement.operations.addPosition')}
                      </button>
                      <button
                        type="button"
                        className="button button--sm button--secondary"
                        onClick={() => onOperate(item, 'reduce')}
                        title={t('watchlistManagement.operations.reducePosition')}
                      >
                        {t('watchlistManagement.operations.reducePosition')}
                      </button>
                      <button
                        type="button"
                        className="button button--sm"
                        onClick={() => onAnalyze(item)}
                        title={t('watchlist.analyze')}
                      >
                        {t('watchlist.analyze')}
                      </button>
                      <button
                        type="button"
                        className="button button--sm button--secondary"
                        onClick={() => onRemove(item.id)}
                        title={t('watchlist.remove')}
                      >
                        {t('watchlist.remove')}
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
