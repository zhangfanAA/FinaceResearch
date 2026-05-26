/**
 * @fileoverview 自选股管理组件 - 管理自选股票和基金列表
 * @module components/WatchlistManager
 * @description 提供自选股/基金的添加、删除、图片识别导入等功能，
 * 支持股票和基金两种类型，基金支持购买信息录入
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
 * 自选股管理组件
 *
 * @component WatchlistManager
 * @description 管理自选股票和基金列表，支持以下功能：
 * - 股票/基金分类管理和展示
 * - 通过代码手动添加自选股/基金
 * - 图片识别批量导入（OCR）
 * - 基金购买信息录入（金额、净值、日期、份额）
 * - 触发单只股票/基金的 AI 分析
 * - 删除自选股/基金
 *
 * @param {Object} props
 * @param {Function} [props.onAnalyze] - 触发分析的回调函数，参数为 (type: 'stock'|'fund', code: string)
 *
 * @returns {JSX.Element} 自选股管理界面
 *
 * @example
 * <WatchlistManager
 *   onAnalyze={(type, code) => {
 *     setActiveTab(type === 'stock' ? 'stock-sector' : 'fund-sector');
 *     setAnalysisCode(code);
 *   }}
 * />
 */
export default function WatchlistManager({ onAnalyze }) {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [codeInput, setCodeInput] = useState('');
  const [adding, setAdding] = useState(false);
  const [addType, setAddType] = useState('stock');
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
   * 加载自选股列表
   * @function loadWatchlist
   * @description 从 API 获取所有自选股/基金数据，更新列表状态
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
   * 处理添加自选股/基金
   * @async
   * @function handleAdd
   * @description 根据输入的代码和类型添加到自选股列表，基金类型支持附带购买信息
   * @throws {Error} 添加失败时显示错误提示
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
   * 处理删除自选股/基金
   * @async
   * @function handleRemove
   * @param {number} id - 自选股记录的 ID
   * @description 从自选股列表中移除指定项，成功后更新本地状态
   */
  async function handleRemove(id) {
    try {
      await removeFromWatchlist(id);
      setItems((prev) => prev.filter((item) => item.id !== id));
    } catch {
      // silent
    }
  }

  /**
   * 处理输入框键盘事件
   * @function handleKeyDown
   * @param {KeyboardEvent} e - 键盘事件
   * @description 按下回车键时触发添加操作
   */
  function handleKeyDown(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleAdd();
    }
  }

  /**
   * 处理文件选择事件
   * @function handleFileSelect
   * @param {Event} e - 文件输入 change 事件
   * @description 读取选中的图片文件并生成预览 URL
   */
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

  /**
   * 处理图片解析（OCR 识别）
   * @async
   * @function handleParseImage
   * @description 将预览图片的 base64 数据发送到后端进行 OCR 识别，提取自选股代码列表
   */
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

  /**
   * 确认添加 OCR 解析出的自选股
   * @async
   * @function handleConfirmAddParsed
   * @description 遍历解析结果，逐个添加到自选股列表（跳过重复项），完成后刷新列表并关闭上传面板
   */
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

  return (
    <div className="watchlist-manager">
      <div className="subpanel">
        <div className="subpanel__header">
          <h3>{t('watchlist.title')}</h3>
        </div>

        {/* Add controls */}
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
                      <span className="badge badge--sm">{t(`watchlist.${item.item_type}`)}</span>
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

        {/* Stock list */}
        {stocks.length > 0 && (
          <div className="watchlist-section">
            <h4 className="watchlist-section__title">{t('watchlist.stockSection')}</h4>
            <div className="watchlist-items">
              {stocks.map((item) => (
                <div key={item.id} className="watchlist-item">
                  <div className="watchlist-item__info">
                    <code className="watchlist-item__code">{item.code}</code>
                    {item.name && <span className="watchlist-item__name">{item.name}</span>}
                  </div>
                  <div className="watchlist-item__actions">
                    {onAnalyze && (
                      <button
                        type="button"
                        className="button button--sm"
                        onClick={() => onAnalyze('stock', item.code)}
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
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Fund list */}
        {funds.length > 0 && (
          <div className="watchlist-section">
            <h4 className="watchlist-section__title">{t('watchlist.fundSection')}</h4>
            <div className="watchlist-items">
              {funds.map((item) => (
                <div key={item.id} className="watchlist-item">
                  <div className="watchlist-item__info">
                    <code className="watchlist-item__code">{item.code}</code>
                    {item.name && <span className="watchlist-item__name">{item.name}</span>}
                  </div>
                  <div className="watchlist-item__actions">
                    {onAnalyze && (
                      <button
                        type="button"
                        className="button button--sm"
                        onClick={() => onAnalyze('fund', item.code)}
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
                </div>
              ))}
            </div>
          </div>
        )}

        {!loading && items.length === 0 && !error && (
          <p className="empty-state">{t('watchlist.empty')}</p>
        )}
      </div>
    </div>
  );
}
