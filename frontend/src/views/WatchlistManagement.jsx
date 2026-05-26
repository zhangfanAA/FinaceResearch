/**
 * @fileoverview 自选管理视图 - 顶级Tab板块，管理自选基金/股票
 * @module views/WatchlistManagement
 * @description 自选管理页面，包含以下功能：
 * - 基金/股票两个子Tab切换
 * - 自选列表表格展示
 * - 加仓/减仓操作弹窗
 * - AI 分析面板（右侧面板，sticky定位）
 * - 持仓汇总统计卡片
 * - 添加自选功能
 * - 图片识别批量导入
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  getWatchlist,
  addToWatchlist,
  removeFromWatchlist,
  parseWatchlistImage,
  analyzeFundSector,
  analyzeStockSector,
  addWatchlistOperation,
  getFundNavRealtime,
} from '../api/client';
import WatchlistTable from '../components/WatchlistTable';
import OperationModal from '../components/OperationModal';
import WatchlistAIAnalysis from '../components/WatchlistAIAnalysis';
import useToast from '../hooks/useToast';

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
 * 自选管理视图
 *
 * @component WatchlistManagement
 * @description 自选管理的主视图页面，整合以下功能模块：
 * - 基金/股票两个子Tab切换
 * - 自选列表表格 + 操作区
 * - AI 分析面板（sticky定位）
 * - 持仓汇总统计卡片
 * - 添加自选功能
 * - 图片识别批量导入
 *
 * @returns {JSX.Element} 自选管理页面
 */
export default function WatchlistManagement() {
  const { t } = useTranslation();
  const { showToast } = useToast();

  // Data state
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Tab state
  const [activeTab, setActiveTab] = useState('fund');

  // Add item state
  const [codeInput, setCodeInput] = useState('');
  const [addType, setAddType] = useState('fund');
  const [adding, setAdding] = useState(false);
  const [showPurchaseInfo, setShowPurchaseInfo] = useState(false);
  const [purchaseAmount, setPurchaseAmount] = useState('');
  const [purchaseNav, setPurchaseNav] = useState('');
  const [purchaseDate, setPurchaseDate] = useState('');
  const [purchaseShares, setPurchaseShares] = useState('');

  // Image upload state
  const [showImageUpload, setShowImageUpload] = useState(false);
  const [imagePreview, setImagePreview] = useState(null);
  const [parsedItems, setParsedItems] = useState([]);
  const [parsing, setParsing] = useState(false);

  // Operation modal state
  const [modalVisible, setModalVisible] = useState(false);
  const [modalItem, setModalItem] = useState(null);
  const [modalOperationType, setModalOperationType] = useState('add');
  const [submitting, setSubmitting] = useState(false);

  // Realtime NAV state
  const [fundNavMap, setFundNavMap] = useState({});

  // AI analysis state
  const [analysis, setAnalysis] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState('');
  const [selectedItem, setSelectedItem] = useState(null);
  const [stepIndex, setStepIndex] = useState(0);

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
   * 分析步骤动画
   */
  useEffect(() => {
    let timer = null;
    if (analyzing) {
      timer = window.setInterval(() => {
        setStepIndex((c) => (c < 2 ? c + 1 : c));
      }, 1200);
    } else {
      setStepIndex(0);
    }
    return () => { if (timer) window.clearInterval(timer); };
  }, [analyzing]);

  // Filter items by type (must be before useEffect that references funds)
  const stocks = items.filter((i) => i.item_type === 'stock');
  const funds = items.filter((i) => i.item_type === 'fund');

  /**
   * 基金实时净值轮询 - 每 60 秒刷新
   */
  useEffect(() => {
    if (activeTab !== 'fund' || funds.length === 0) return;

    let timer = null;
    let disposed = false;

    async function fetchRealtimeNav() {
      try {
        const codes = funds.map((f) => f.code);
        const data = await getFundNavRealtime(codes);
        if (disposed) return;
        const map = {};
        if (Array.isArray(data)) {
          data.forEach((item) => {
            map[item.fund_code || item.code] = item;
          });
        }
        setFundNavMap(map);
      } catch {
        // silent fail for polling
      }
    }

    fetchRealtimeNav();
    timer = window.setInterval(fetchRealtimeNav, 60000);

    return () => {
      disposed = true;
      if (timer) window.clearInterval(timer);
    };
  }, [activeTab, funds]);

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
        showToast(t('toast.duplicate'), 'warning');
      } else {
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
      // Clear analysis if the removed item was selected
      if (selectedItem?.id === id) {
        setAnalysis(null);
        setSelectedItem(null);
      }
    } catch {
      // silent
    }
  }

  /**
   * 处理打开操作弹窗
   */
  function handleOperate(item, operationType) {
    setModalItem(item);
    setModalOperationType(operationType);
    setModalVisible(true);
  }

  /**
   * 处理提交操作
   */
  async function handleSubmitOperation(formData) {
    if (!modalItem) return;
    setSubmitting(true);
    try {
      await addWatchlistOperation(modalItem.id, {
        operation_type: modalOperationType,
        ...formData,
      });
      showToast(
        modalOperationType === 'add'
          ? t('watchlistManagement.operations.addSuccess')
          : t('watchlistManagement.operations.reduceSuccess'),
        'success'
      );
      setModalVisible(false);
      await loadWatchlist();
    } catch (err) {
      showToast(err.message || t('watchlistManagement.operations.operationFailed'), 'error');
    } finally {
      setSubmitting(false);
    }
  }

  /**
   * 处理 AI 分析
   */
  const handleAnalyze = useCallback(async (item) => {
    setSelectedItem(item);
    setAnalysis(null);
    setAnalysisError('');
    setAnalyzing(true);
    setStepIndex(0);
    try {
      let result;
      if (item.item_type === 'fund') {
        result = await analyzeFundSector(item.code);
      } else {
        result = await analyzeStockSector({ stockCode: item.code });
      }
      setAnalysis(result);
    } catch (err) {
      setAnalysisError(
        err.status >= 500 || /timeout/i.test(err.message || '')
          ? t('fundSector.busy')
          : err.message
      );
    } finally {
      setAnalyzing(false);
    }
  }, [t]);

  /**
   * 处理图片选择
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
   * 处理图片解析
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
   * 处理确认添加解析的项目
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

  function handleKeyDown(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleAdd();
    }
  }

  // Display items based on active tab
  const displayItems = activeTab === 'fund' ? funds : stocks;

  // Compute summary stats
  const totalInvested = displayItems.reduce((s, h) => s + (h.purchase_amount || h.amount || 0), 0);
  const totalPnl = displayItems.reduce((s, h) => s + (h.total_pnl || 0), 0);
  const totalPnlPct = totalInvested > 0 ? (totalPnl / totalInvested) * 100 : 0;
  const totalTone = getChangeTone(totalPnl);

  const TAB_OPTIONS = [
    { value: 'fund', label: t('watchlist.fundSection'), count: funds.length },
    { value: 'stock', label: t('watchlist.stockSection'), count: stocks.length },
  ];

  return (
    <section className="panel watchlist-management-panel">
      {/* Header */}
      <div className="section-header">
        <div>
          <h2>{t('watchlistManagement.title')}</h2>
          <p>{t('watchlistManagement.subtitle')}</p>
        </div>
        <div className="section-header__actions">
          <button type="button" className="button button--secondary" onClick={loadWatchlist}>
            {t('fundSector.refreshHoldings')}
          </button>
        </div>
      </div>

      {/* Sub-tabs */}
      <div className="watchlist-management__tabs">
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

      {/* Main layout: left-right split */}
      <div className="watchlist-management-layout">
        {/* Left panel */}
        <div className="watchlist-management-layout__left">
          {/* Summary cards */}
          <div className="watchlist-management__summary">
            <div className="fund-holdings-summary__card">
              <span className="fund-holdings-summary__label">{t('watchlistManagement.summary.totalInvested')}</span>
              <span className="fund-holdings-summary__value">{formatNumber(totalInvested, 2)}</span>
            </div>
            <div className="fund-holdings-summary__card">
              <span className="fund-holdings-summary__label">{t('watchlistManagement.summary.totalPnl')}</span>
              <span className={`fund-holdings-summary__value fund-holdings-summary__value--${totalTone}`}>
                {totalPnl >= 0 ? '+' : ''}{formatNumber(totalPnl, 2)}
              </span>
            </div>
            <div className="fund-holdings-summary__card">
              <span className="fund-holdings-summary__label">{t('watchlistManagement.summary.totalPnlPct')}</span>
              <span className={`fund-holdings-summary__value fund-holdings-summary__value--${totalTone}`}>
                {totalPnlPct >= 0 ? '+' : ''}{formatNumber(totalPnlPct, 2)}%
              </span>
            </div>
            <div className="fund-holdings-summary__card">
              <span className="fund-holdings-summary__label">{t('watchlistManagement.summary.itemCount')}</span>
              <span className="fund-holdings-summary__value">{displayItems.length}</span>
            </div>
          </div>

          {/* Add controls */}
          <div className="subpanel">
            <div className="subpanel__header">
              <h3>{t('watchlistManagement.addSection.title')}</h3>
            </div>
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
                  onClick={() => document.getElementById('watchlist-file-input')?.click()}
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
                    id="watchlist-file-input"
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
          </div>

          {/* Watchlist table */}
          <div className="subpanel">
            <div className="subpanel__header">
              <h3>{activeTab === 'fund' ? t('watchlist.fundSection') : t('watchlist.stockSection')}</h3>
            </div>
            <WatchlistTable
              items={displayItems}
              activeTab={activeTab}
              loading={loading}
              onOperate={handleOperate}
              onAnalyze={handleAnalyze}
              onRemove={handleRemove}
              t={t}
              fundNavMap={fundNavMap}
            />
          </div>
        </div>

        {/* Right panel: AI Analysis */}
        <div className="watchlist-management-layout__right">
          <WatchlistAIAnalysis
            analysis={analysis}
            analyzing={analyzing}
            error={analysisError}
            selectedItem={selectedItem}
            stepIndex={stepIndex}
          />
        </div>
      </div>

      {/* Operation Modal */}
      <OperationModal
        item={modalItem}
        operationType={modalOperationType}
        visible={modalVisible}
        onClose={() => setModalVisible(false)}
        onSubmit={handleSubmitOperation}
        submitting={submitting}
      />
    </section>
  );
}
