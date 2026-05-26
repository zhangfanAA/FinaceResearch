/**
 * @fileoverview 基金持仓表格组件 - 展示基金持仓详情和 AI 分析
 * @module components/FundHoldingsTable
 * @description 展示基金持仓的净值、收益率、盈亏等信息，支持单只基金的 AI 分析，
 * 移动端自动隐藏部分列并显示详情行
 */

import { Fragment, useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getFundHoldings, analyzeFundSector } from '../api/client';
import useToast from '../hooks/useToast';
import SkeletonTable from './SkeletonTable';

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
 * 获取数值变化的颜色基调
 * @function getChangeTone
 * @param {*} value - 数值
 * @returns {'up'|'down'|'neutral'} 正数返回 'up'，负数返回 'down'，零或无效返回 'neutral'
 */
function getChangeTone(value) {
  const numeric = Number(value);
  if (Number.isNaN(numeric) || numeric === 0) return 'neutral';
  return numeric > 0 ? 'up' : 'down';
}

/**
 * 基金持仓表格组件
 *
 * @component FundHoldingsTable
 * @description 展示用户持有的基金详情，支持以下功能：
 * - 基金净值、收益率、盈亏等信息展示
 * - 单只基金的 AI 分析触发
 * - 移动端自动隐藏部分列并显示可展开详情行
 * - 分析结果和错误信息的内联展示
 *
 * @returns {JSX.Element} 基金持仓表格或加载/空状态
 *
 * @example
 * <FundHoldingsTable />
 */
export default function FundHoldingsTable() {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const [holdings, setHoldings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [analyzingCode, setAnalyzingCode] = useState(null);
  const [analysisResults, setAnalysisResults] = useState({});
  const [analysisErrors, setAnalysisErrors] = useState({});
  const [expandedRowId, setExpandedRowId] = useState(null);

  /**
   * 加载基金持仓数据
   * @function loadHoldings
   * @description 从 API 获取基金持仓列表，更新状态
   */
  const loadHoldings = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await getFundHoldings();
      setHoldings(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.message || t('common.error'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    loadHoldings();
  }, [loadHoldings]);

  /**
   * 处理单只基金的 AI 分析
   * @async
   * @function handleAnalyze
   * @param {string} code - 基金代码
   * @description 调用 AI 分析接口，成功后将结果存储到 analysisResults，失败时显示错误提示
   */
  async function handleAnalyze(code) {
    setAnalyzingCode(code);
    setAnalysisErrors((prev) => ({ ...prev, [code]: '' }));
    try {
      const result = await analyzeFundSector(code);
      setAnalysisResults((prev) => ({ ...prev, [code]: result }));
    } catch (err) {
      const msg = err.status === 503
        ? t('toast.apiKeyRequired')
        : err.message || t('common.error');
      setAnalysisErrors((prev) => ({ ...prev, [code]: msg }));
      showToast(msg, 'error');
    } finally {
      setAnalyzingCode(null);
    }
  }

  /**
   * 切换行展开/收起状态
   * @function toggleRow
   * @param {number} id - 行的唯一标识
   * @description 点击行时切换详情行的显示状态（移动端使用）
   */
  function toggleRow(id) {
    setExpandedRowId((prev) => (prev === id ? null : id));
  }

  if (loading) {
    return (
      <div className="fund-holdings-table-wrap">
        <SkeletonTable rows={4} columns={10} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="fund-holdings-table-wrap">
        <p className="empty-state">{error}</p>
      </div>
    );
  }

  if (!holdings || holdings.length === 0) {
    return (
      <div className="fund-holdings-table-wrap">
        <p className="empty-state">{t('watchlist.fundHoldings.noHoldings')}</p>
      </div>
    );
  }

  // Compute summary stats
  const totalInvested = holdings.reduce((s, h) => s + (h.purchase_amount || 0), 0);
  const totalPnl = holdings.reduce((s, h) => s + (h.total_pnl || 0), 0);
  const totalPnlPct = totalInvested > 0 ? (totalPnl / totalInvested) * 100 : 0;
  const totalTone = getChangeTone(totalPnl);

  return (
    <div className="fund-holdings-table-wrap">
      {/* Summary cards */}
      <div className="fund-holdings-summary">
        <div className="fund-holdings-summary__card">
          <span className="fund-holdings-summary__label">{t('watchlist.fundHoldings.amount')}</span>
          <span className="fund-holdings-summary__value">{formatNumber(totalInvested, 2)}</span>
        </div>
        <div className="fund-holdings-summary__card">
          <span className="fund-holdings-summary__label">{t('watchlist.fundHoldings.totalPnl')}</span>
          <span className={`fund-holdings-summary__value fund-holdings-summary__value--${totalTone}`}>
            {totalPnl >= 0 ? '+' : ''}{formatNumber(totalPnl, 2)}
          </span>
        </div>
        <div className="fund-holdings-summary__card">
          <span className="fund-holdings-summary__label">{t('watchlist.fundHoldings.totalPnlPct')}</span>
          <span className={`fund-holdings-summary__value fund-holdings-summary__value--${totalTone}`}>
            {totalPnlPct >= 0 ? '+' : ''}{formatNumber(totalPnlPct, 2)}%
          </span>
        </div>
      </div>

      <div className="table-wrap">
        <table className="fund-holdings-table">
          <thead>
            <tr>
              <th>{t('watchlist.fundHoldings.code')}</th>
              <th>{t('watchlist.fundHoldings.name')}</th>
              <th>{t('watchlist.fundHoldings.purchaseNav')}</th>
              <th>{t('watchlist.fundHoldings.currentNav')}</th>
              <th className="fund-holdings-table__hide-mobile">{t('watchlist.fundHoldings.navDate')}</th>
              <th>{t('watchlist.fundHoldings.dailyReturn')}</th>
              <th className="fund-holdings-table__hide-mobile">{t('watchlist.fundHoldings.shares')}</th>
              <th className="fund-holdings-table__hide-mobile">{t('watchlist.fundHoldings.amount')}</th>
              <th>{t('watchlist.fundHoldings.totalPnl')}</th>
              <th>{t('watchlist.fundHoldings.totalPnlPct')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {holdings.map((h) => {
              const dailyTone = getChangeTone(h.daily_return);
              const pnlTone = getChangeTone(h.total_pnl);
              const isExpanded = expandedRowId === h.id;
              return (
                <Fragment key={h.id}>
                  <tr
                    className={`fund-holdings-table__row ${isExpanded ? 'fund-holdings-table__row--expanded' : ''}`}
                    onClick={() => toggleRow(h.id)}
                  >
                    <td className="fund-holdings-table__code">{h.code}</td>
                    <td>{h.name || '--'}</td>
                    <td>{formatNumber(h.purchase_nav, 4)}</td>
                    <td>{formatNumber(h.current_nav, 4)}</td>
                    <td className="fund-holdings-table__hide-mobile">{h.current_nav_date || '--'}</td>
                    <td className={`fund-holdings-table__${dailyTone}`}>
                      {formatNumber(h.daily_return, 2)}%
                    </td>
                    <td className="fund-holdings-table__hide-mobile">{formatNumber(h.shares, 2)}</td>
                    <td className="fund-holdings-table__hide-mobile">{formatNumber(h.purchase_amount, 2)}</td>
                    <td className={`fund-holdings-table__${pnlTone}`}>
                      {formatNumber(h.total_pnl, 2)}
                    </td>
                    <td className={`fund-holdings-table__${pnlTone}`}>
                      {formatNumber(h.total_pnl_pct, 2)}%
                    </td>
                    <td>
                      <button
                        type="button"
                        className="button button--sm"
                        onClick={(e) => { e.stopPropagation(); handleAnalyze(h.code); }}
                        disabled={analyzingCode === h.code}
                      >
                        {analyzingCode === h.code
                          ? t('watchlist.fundHoldings.analyzing')
                          : t('watchlist.fundHoldings.aiAnalysis')}
                      </button>
                    </td>
                  </tr>
                  {/* Mobile detail row - visible only on small screens when expanded */}
                  <tr
                    className={`fund-holdings-table__detail-row ${isExpanded ? 'fund-holdings-table__detail-row--visible' : ''}`}
                  >
                    <td colSpan="11">
                      <div className="fund-holdings-table__detail-grid">
                        <div className="fund-holdings-table__detail-item">
                          <span className="fund-holdings-table__detail-label">{t('watchlist.fundHoldings.navDate')}</span>
                          <span className="fund-holdings-table__detail-value">{h.current_nav_date || '--'}</span>
                        </div>
                        <div className="fund-holdings-table__detail-item">
                          <span className="fund-holdings-table__detail-label">{t('watchlist.fundHoldings.shares')}</span>
                          <span className="fund-holdings-table__detail-value">{formatNumber(h.shares, 2)}</span>
                        </div>
                        <div className="fund-holdings-table__detail-item">
                          <span className="fund-holdings-table__detail-label">{t('watchlist.fundHoldings.amount')}</span>
                          <span className="fund-holdings-table__detail-value">{formatNumber(h.purchase_amount, 2)}</span>
                        </div>
                      </div>
                    </td>
                  </tr>
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Inline analysis summaries */}
      {Object.entries(analysisResults).map(([code, result]) => (
        <div key={code} className="fund-holdings-analysis-summary">
          <strong>{code}</strong>:
          {result.judgment && (
            <span className={`badge badge--${result.judgment === 'positive' ? 'good' : result.judgment === 'negative' ? 'bad' : 'warn'}`}>
              {result.judgment}
            </span>
          )}
          {result.suggestion && (
            <span className={`badge badge--${result.suggestion === 'hold' ? 'good' : result.suggestion === 'caution' ? 'bad' : 'warn'}`}>
              {result.suggestion}
            </span>
          )}
          {result.reasoning && (
            <p className="fund-holdings-analysis-summary__text">{result.reasoning}</p>
          )}
        </div>
      ))}
      {Object.entries(analysisErrors).filter(([, msg]) => msg).map(([code, msg]) => (
        <div key={code} className="inline-alert inline-alert--error" style={{ marginTop: '8px' }}>
          <strong>{code}</strong>: {msg}
        </div>
      ))}
    </div>
  );
}
