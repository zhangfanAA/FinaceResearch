/**
 * @fileoverview 加仓/减仓弹窗组件 - 自选管理的操作弹窗
 * @module components/OperationModal
 * @description 提供加仓/减仓操作的弹窗表单，支持：
 * - 操作类型选择（加仓/减仓）
 * - 金额、份额、净值输入
 * - 备注输入
 * - 提交和取消按钮
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';

/**
 * 加仓/减仓弹窗组件
 *
 * @component OperationModal
 * @description 自选管理的操作弹窗，支持加仓和减仓操作
 *
 * @param {Object} props
 * @param {Object} props.item - 当前操作的自选项目
 * @param {string} props.operationType - 操作类型：'add'（加仓）或 'reduce'（减仓）
 * @param {boolean} props.visible - 是否显示弹窗
 * @param {Function} props.onClose - 关闭弹窗回调
 * @param {Function} props.onSubmit - 提交回调，参数为 { amount, shares, nav, note }
 * @param {boolean} props.submitting - 是否正在提交
 * @returns {JSX.Element|null} 操作弹窗或 null
 */
export default function OperationModal({ item, operationType, visible, onClose, onSubmit, submitting }) {
  const { t } = useTranslation();
  const [amount, setAmount] = useState('');
  const [shares, setShares] = useState('');
  const [nav, setNav] = useState('');
  const [note, setNote] = useState('');

  if (!visible || !item) return null;

  const isAdd = operationType === 'add';
  const title = isAdd
    ? t('watchlistManagement.operations.addPosition')
    : t('watchlistManagement.operations.reducePosition');

  function handleSubmit(e) {
    e.preventDefault();
    onSubmit({
      amount: amount ? parseFloat(amount) : null,
      shares: shares ? parseFloat(shares) : null,
      nav: nav ? parseFloat(nav) : null,
      note: note.trim() || null,
    });
  }

  function handleClose() {
    setAmount('');
    setShares('');
    setNav('');
    setNote('');
    onClose();
  }

  return (
    <div className="modal-overlay" onClick={handleClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{title} - {item.code} {item.name || ''}</h3>
          <button type="button" className="modal-close" onClick={handleClose}>
            &times;
          </button>
        </div>
        <form className="modal-form" onSubmit={handleSubmit}>
          <label className="modal-field">
            <span>{t('watchlistManagement.operations.amount')}</span>
            <input
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="0.00"
              min="0"
              step="0.01"
              disabled={submitting}
            />
          </label>
          <label className="modal-field">
            <span>{t('watchlistManagement.operations.shares')}</span>
            <input
              type="number"
              value={shares}
              onChange={(e) => setShares(e.target.value)}
              placeholder="0.00"
              min="0"
              step="0.01"
              disabled={submitting}
            />
          </label>
          <label className="modal-field">
            <span>{t('watchlistManagement.operations.nav')}</span>
            <input
              type="number"
              value={nav}
              onChange={(e) => setNav(e.target.value)}
              placeholder="0.0000"
              min="0"
              step="0.0001"
              disabled={submitting}
            />
          </label>
          <label className="modal-field">
            <span>{t('watchlistManagement.operations.note')}</span>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder={t('watchlistManagement.operations.notePlaceholder')}
              rows={2}
              disabled={submitting}
            />
          </label>
          <div className="modal-actions">
            <button type="button" className="button button--secondary" onClick={handleClose} disabled={submitting}>
              {t('watchlist.imageUpload.cancel')}
            </button>
            <button type="submit" className="button" disabled={submitting}>
              {submitting ? t('watchlistManagement.operations.submitting') : t('watchlistManagement.operations.submit')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
