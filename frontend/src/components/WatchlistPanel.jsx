/**
 * @fileoverview 自选管理全宽面板组件 - 独立Tab级别的自选管理
 * @module components/WatchlistPanel
 * @description 提供全宽独立的自选股/基金管理界面，支持：
 * - 股票/基金分类内部Tab切换
 * - 通过代码手动添加自选股/基金
 * - 图片识别批量导入（OCR）
 * - 基金购买信息录入（金额、净值、日期、份额）
 * - 触发单只股票/基金的 AI 分析
 * - 删除自选股/基金
 * - 宽表格展示
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  getWatchlist,
  addToWatchlist,
  removeFromWatchlist,
  parseWatchlistImage,
} from '../api/client';
import useToast from '../hooks/useToast';

/**
 * 自选管理全宽面板组件
 *
 * @component WatchlistPanel
 * @description 全宽独立的自选股/基金管理界面，作为与行业板块、概念板块平级的Tab使用
 *
 * @param {Object} props
 * @param {Function} [props.onAnalyze] - 触发分析的回调函数，参数为 (type: 'stock'|'fund', code: string)
 *
 * @returns {JSX.Element} 自选管理全宽面板
 */
export default function WatchlistPanel({ onAnalyze }) {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [codeInput, setCodeInput] = useState('');
  const [adding, setAdding] = useState(false);
  const [addType, setAddType] = useState('stock');
  const [activeTab, setActiveTab] = useState('stock');
  const [showImageUpload, setShowImageUpload] = useState(false);
  const [imagePreview, setImagePreview] = useState(null);
  const [parsedItems, setParsedItems] = useState([]);
  const [parsing, setParsing] = useState(false);
  const fileInputRef = useRef(null);
  const [showPurchaseInfo, setShowPurchaseInfo] = useState(false);
  const [purchaseAmount, setPurchaseAmount] = useState('');
  const [purchaseNav, setPurchaseNav] = useState('');
  const [purchaseDate, setPurchaseDate] = useState('');
  const [purchaseShares, setPurchaseShares] = useState('');

  /**
   * 加载自选列表
   */
  const loadWatchlist = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await getWatchlist('all');
      setItems(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.message || t('watchlist.empty'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    loadWatchlist();
  }, [loadWatchlist]);

  /**
   * 处理添加自选
   */
  async function handleAdd() {
    const code = codeInput.trim();
    if (!code) return;
    setAdding(true);
    try {
      const purchaseInfo = {};
      if (addType === 'fund' && showPurchaseInfo) {
        if (purchaseAmount) purchaseInfo.purchase_amount = parseFloat(purchaseAmount);
        if (purchaseNav) purchaseInfo.purchase_nav = parseFloat(purchaseNav);
        if (purchaseDate) purchaseInfo.purchase_date = purchaseDate;
        if (purchaseShares) purchaseInfo.shares = parseFloat(purchaseShares);
      }
      await addToWatchlist(addType, code, null, purchaseInfo);
      setCodeInput('');
      setPurchaseAmount('');
      setPurchaseNav('');
      setPurchaseDate('');
      setPurchaseShares('');
      setShowPurchaseInfo(false);
      showToast(t('toast.addSuccess'), 'success');
      await loadWatchlist();
    } catch (err) {
      if (err.status === 409 || /already exists|duplicate/i.test(err.message)) {
        setError(t('watchlist.duplicate') || 'Already exists');
        showToast(t('toast.duplicate'), 'warning');
      } else {
        setError(err.message || t('watchlist.addFailed'));
        showToast(t('toast.addFailed'), 'error');
      }
    } finally {
      setAdding(false);
    }
  }

  /**
   * 处理删除自选
   */
  async function handleRemove(id) {
    try {
      await removeFromWatchlist(id);
      setItems((prev) => prev.filter((item) => item.id !== id));
      showToast(t('toast.removeSuccess'), 'success');
    } catch {
      // silent
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleAdd();
    }
  }

  function handleFileSelect(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      setImagePreview(reader.result);
      setParsedItems([]);
    };
    reader.readAsDataURL(file);
  }

  async function handleParseImage() {
    if (!imagePreview) return;
    setParsing(true);
    try {
      const base64 = imagePreview.split(',')[1];
      const result = await parseWatchlistImage(base64);
      setParsedItems(result?.items || []);
    } catch {
      setParsedItems([]);
    } finally {
      setParsing(false);
    }
  }

  async function handleConfirmAddParsed() {
    for (const item of parsedItems) {
      try {
        await addToWatchlist(item.item_type, item.code);
      } catch {
        // skip duplicates
      }
    }
    setParsedItems([]);
    setImagePreview(null);
    setShowImageUpload(false);
    await loadWatchlist();
  }

  const stocks = items.filter((i) => i.item_type === 'stock');
  const funds = items.filter((i) => i.item_type === 'fund');
  const displayItems = activeTab === 'stock' ? stocks : funds;

  const TAB_OPTIONS = [
    { value: 'stock', label: t('watchlist.stockSection'), count: stocks.length },
    { value: 'fund', label: t('watchlist.fundSection'), count: funds.length },
  ];

  return (
    <div className="watchlist-panel">
      {/* Internal tab bar */}
      <div className="watchlist-panel__tabs">
        {TAB_OPTIONS.map((tab) => (
          <button
            key={tab.value}
            type="button"
            className={`tab-nav__button ${activeTab === tab.value ? 'tab-nav__button--active' : ''}`}
            onClick={() => setActiveTab(tab.value)}
          >
            {tab.label}
            <span className="watchlist-panel__tab-count">{tab.count}</span>
          </button>
        ))}
      </div>

      {/* Add controls */}
      <div className="watchlist-panel__controls">
        <div className="watchlist-add-row">
          <div className="watchlist-type-toggle">
            <button
              type="button"
              className={`button button--sm ${addType === 'stock' ? '' : 'button--secondary'}`}
              onClick={() => setAddType('stock')}
            >
              {t('watchlist.stock')}
            </button>
            <button
              type="button"
              className={`button button--sm ${addType === 'fund' ? '' : 'button--secondary'}`}
              onClick={() => setAddType('fund')}
            >
              {t('watchlist.fund')}
            </button>
          </div>
          <input
            type="text"
            className="watchlist-input"
            value={codeInput}
            onChange={(e) => setCodeInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t('watchlist.inputPlaceholder')}
            disabled={adding}
          />
          <button
            type="button"
            className="button button--sm"
            onClick={handleAdd}
            disabled={adding || !codeInput.trim()}
          >
            {adding ? t('watchlist.adding') : t('watchlist.add')}
          </button>
          <button
            type="button"
            className="button button--sm button--secondary"
            onClick={() => setShowImageUpload((p) => !p)}
          >
            {t('watchlist.imageUpload.title')}
          </button>
        </div>

        {/* Purchase info section (fund only) */}
        {addType === 'fund' && (
          <div className="purchase-info-section">
            <button
              type="button"
              className="purchase-info-toggle"
              onClick={() => setShowPurchaseInfo((p) => !p)}
            >
              {showPurchaseInfo
                ? t('watchlist.purchaseInfo.collapse')
                : t('watchlist.purchaseInfo.expand')}
              <span className={`purchase-info-chevron ${showPurchaseInfo ? 'purchase-info-chevron--open' : ''}`}>
                &#9662;
              </span>
            </button>
            {showPurchaseInfo && (
              <div className="purchase-info-form">
                <label className="purchase-info-field">
                  <span>{t('watchlist.purchaseInfo.amount')}</span>
                  <input
                    type="number"
                    value={purchaseAmount}
                    onChange={(e) => setPurchaseAmount(e.target.value)}
                    placeholder="0.00"
                    min="0"
                    step="0.01"
                  />
                </label>
                <label className="purchase-info-field">
                  <span>{t('watchlist.purchaseInfo.nav')}</span>
                  <input
                    type="number"
                    value={purchaseNav}
                    onChange={(e) => setPurchaseNav(e.target.value)}
                    placeholder="0.0000"
                    min="0"
                    step="0.0001"
                  />
                </label>
                <label className="purchase-info-field">
                  <span>{t('watchlist.purchaseInfo.date')}</span>
                  <input
                    type="date"
                    value={purchaseDate}
                    onChange={(e) => setPurchaseDate(e.target.value)}
                  />
                </label>
                <label className="purchase-info-field">
                  <span>{t('watchlist.purchaseInfo.shares')}</span>
                  <input
                    type="number"
                    value={purchaseShares}
                    onChange={(e) => setPurchaseShares(e.target.value)}
                    placeholder="0.00"
                    min="0"
                    step="0.01"
                  />
                </label>
              </div>
            )}
          </div>
        )}

        {/* Image upload section */}
        {showImageUpload && (
          <div className="watchlist-image-upload">
            <div
              className="watchlist-image-dropzone"
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                const file = e.dataTransfer.files?.[0];
                if (file) {
                  const reader = new FileReader();
                  reader.onload = () => {
                    setImagePreview(reader.result);
                    setParsedItems([]);
                  };
                  reader.readAsDataURL(file);
                }
              }}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                style={{ display: 'none' }}
                onChange={handleFileSelect}
              />
              {imagePreview ? (
                <img src={imagePreview} alt="preview" className="watchlist-image-preview" />
              ) : (
                <span className="watchlist-image-hint">{t('watchlist.imageUpload.dragHint')}</span>
              )}
            </div>
            {imagePreview && (
              <div className="watchlist-image-actions">
                <button
                  type="button"
                  className="button button--sm"
                  onClick={handleParseImage}
                  disabled={parsing}
                >
                  {parsing ? t('watchlist.imageUpload.uploading') : t('watchlist.imageUpload.uploadButton')}
                </button>
                <button
                  type="button"
                  className="button button--sm button--secondary"
                  onClick={() => {
                    setImagePreview(null);
                    setParsedItems([]);
                  }}
                >
                  {t('watchlist.imageUpload.cancel')}
                </button>
              </div>
            )}
            {parsedItems.length > 0 && (
              <div className="watchlist-parsed-items">
                <h4>{t('watchlist.imageUpload.parsedItems')}</h4>
                <ul>
                  {parsedItems.map((item, i) => (
                    <li key={i}>
                      <span className="badge badge--sm badge--warn">{t(`watchlist.${item.item_type}`)}</span>
                      <code>{item.code}</code>
                    </li>
                  ))}
                </ul>
                <button
                  type="button"
                  className="button button--sm"
                  onClick={handleConfirmAddParsed}
                >
                  {t('watchlist.imageUpload.confirmAdd')} ({parsedItems.length})
                </button>
              </div>
            )}
            {parsedItems.length === 0 && imagePreview && !parsing && (
              <p className="empty-state">{t('watchlist.imageUpload.noItems')}</p>
            )}
          </div>
        )}

        {error && <div className="inline-alert inline-alert--error">{error}</div>}
      </div>

      {/* Items table */}
      <div className="watchlist-panel__table-wrap">
        {loading ? (
          <p className="empty-state">{t('common.loading')}...</p>
        ) : displayItems.length > 0 ? (
          <div className="table-wrap">
            <table className="watchlist-panel__table">
              <thead>
                <tr>
                  <th>{t('watchlist.code')}</th>
                  <th>{t('watchlist.name')}</th>
                  <th>{t('watchlist.type')}</th>
                  {activeTab === 'fund' && (
                    <>
                      <th>{t('watchlist.purchaseInfo.amount')}</th>
                      <th>{t('watchlist.purchaseInfo.nav')}</th>
                      <th>{t('watchlist.purchaseInfo.shares')}</th>
                    </>
                  )}
                  <th>{t('stockSector.table.action')}</th>
                </tr>
              </thead>
              <tbody>
                {displayItems.map((item) => (
                  <tr key={item.id}>
                    <td className="watchlist-panel__code">{item.code}</td>
                    <td>{item.name || '--'}</td>
                    <td>
                      <span className={`badge badge--sm ${item.item_type === 'stock' ? 'badge--good' : 'badge--warn'}`}>
                        {t(`watchlist.${item.item_type}`)}
                      </span>
                    </td>
                    {activeTab === 'fund' && (
                      <>
                        <td>{item.purchase_amount != null ? Number(item.purchase_amount).toFixed(2) : '--'}</td>
                        <td>{item.purchase_nav != null ? Number(item.purchase_nav).toFixed(4) : '--'}</td>
                        <td>{item.shares != null ? Number(item.shares).toFixed(2) : '--'}</td>
                      </>
                    )}
                    <td>
                      <div className="watchlist-panel__actions">
                        {onAnalyze && (
                          <button
                            type="button"
                            className="button button--sm"
                            onClick={() => onAnalyze(item.item_type, item.code)}
                          >
                            {t('watchlist.analyze')}
                          </button>
                        )}
                        <button
                          type="button"
                          className="button button--sm button--secondary"
                          onClick={() => handleRemove(item.id)}
                        >
                          {t('watchlist.remove')}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty-state">{t('watchlist.empty')}</p>
        )}
      </div>
    </div>
  );
}
