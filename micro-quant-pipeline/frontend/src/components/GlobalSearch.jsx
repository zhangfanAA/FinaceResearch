/**
 * @fileoverview 全局搜索组件 - 命令面板式搜索（Ctrl+K 触发）
 * @module components/GlobalSearch
 * @description 类似 VS Code 命令面板的全局搜索弹窗，支持自选股搜索、最近搜索和直接代码输入
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getWatchlist } from '../api/client';

/** 最大保存最近搜索记录数 */
const MAX_RECENT = 8;
/** localStorage 存储键名 */
const RECENT_KEY = 'global_search_recent';

/**
 * 根据代码格式判断是股票还是基金
 * @function classifyCode
 * @param {string} code - 证券代码
 * @returns {'stock'|'fund'|'unknown'} 代码类型：股票、基金或未知
 * @description 股票代码以 0/3/6 开头且为 6 位数字，基金代码为 6 位数字
 */
function classifyCode(code) {
  const trimmed = (code || '').trim();
  if (/^[036]\d{5}$/.test(trimmed)) return 'stock';
  if (/^\d{6}$/.test(trimmed)) return 'fund';
  return 'unknown';
}

/**
 * 从 localStorage 加载最近搜索记录
 * @function loadRecentSearches
 * @returns {string[]} 最近搜索的代码列表
 */
function loadRecentSearches() {
  try {
    const stored = localStorage.getItem(RECENT_KEY);
    return stored ? JSON.parse(stored) : [];
  } catch {
    return [];
  }
}

/**
 * 保存搜索记录到 localStorage
 * @function saveRecentSearch
 * @param {string} code - 搜索的证券代码
 * @description 将代码添加到最近搜索列表，去重并限制最大数量
 */
function saveRecentSearch(code) {
  try {
    const recent = loadRecentSearches();
    const next = [code, ...recent.filter((r) => r !== code)].slice(0, MAX_RECENT);
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    // ignore
  }
}

/**
 * 全局搜索命令面板组件
 *
 * @component GlobalSearch
 * @description 类似 VS Code 命令面板的全局搜索弹窗，支持以下功能：
 * - 自选股列表搜索和过滤
 * - 最近搜索记录管理（localStorage 持久化）
 * - 直接输入证券代码快速跳转
 * - 键盘导航（上下箭头选择、回车确认、ESC 关闭）
 * - 自动识别股票/基金代码类型
 *
 * @param {Object} props
 * @param {boolean} props.isOpen - 是否显示搜索面板
 * @param {Function} props.onClose - 关闭搜索面板的回调
 * @param {Function} props.onNavigate - 导航到分析页面的回调，参数为 { type: 'stock'|'fund', code: string, tab: string }
 *
 * @returns {JSX.Element|null} 搜索面板 JSX 或 null（未打开时）
 *
 * @example
 * const [searchOpen, setSearchOpen] = useState(false);
 *
 * // 使用 Ctrl+K 快捷键打开
 * useKeyboardShortcut('k', () => setSearchOpen(true), { ctrl: true });
 *
 * <GlobalSearch
 *   isOpen={searchOpen}
 *   onClose={() => setSearchOpen(false)}
 *   onNavigate={({ type, code, tab }) => navigateToAnalysis(type, code)}
 * />
 */
export default function GlobalSearch({ isOpen, onClose, onNavigate }) {
  const { t } = useTranslation();
  const [query, setQuery] = useState('');
  const [watchlistItems, setWatchlistItems] = useState([]);
  const [recentSearches, setRecentSearches] = useState([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef(null);
  const listRef = useRef(null);

  // Load watchlist and recent searches when opened
  useEffect(() => {
    if (!isOpen) return;
    setQuery('');
    setActiveIndex(0);

    getWatchlist('all')
      .then((data) => setWatchlistItems(Array.isArray(data) ? data : []))
      .catch(() => setWatchlistItems([]));

    setRecentSearches(loadRecentSearches());
  }, [isOpen]);

  // Focus input when opened
  useEffect(() => {
    if (isOpen) {
      // Small delay to allow the modal to render
      const timer = setTimeout(() => inputRef.current?.focus(), 50);
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  // Build results list
  const trimmedQuery = query.trim();
  const isCodeInput = /^\d{4,6}$/.test(trimmedQuery);

  const filteredWatchlist = trimmedQuery
    ? watchlistItems.filter((item) => {
        const q = trimmedQuery.toLowerCase();
        return (
          (item.code || '').toLowerCase().includes(q) ||
          (item.name || '').toLowerCase().includes(q)
        );
      })
    : watchlistItems;

  const filteredRecent = trimmedQuery
    ? recentSearches.filter((r) => r.toLowerCase().includes(trimmedQuery.toLowerCase()))
    : recentSearches;

  // Results: watchlist first, then recent searches, then "search directly" option
  const results = [];

  if (filteredWatchlist.length > 0) {
    results.push({ type: 'header', label: t('globalSearch.watchlist') });
    filteredWatchlist.forEach((item) => {
      results.push({
        type: 'watchlist',
        code: item.code,
        name: item.name || '',
        itemType: item.item_type,
        id: item.id,
      });
    });
  }

  if (filteredRecent.length > 0) {
    results.push({ type: 'header', label: t('globalSearch.recentSearches') });
    filteredRecent.forEach((code) => {
      results.push({ type: 'recent', code });
    });
  }

  if (isCodeInput && !results.some((r) => r.code === trimmedQuery)) {
    results.push({ type: 'direct', code: trimmedQuery });
  }

  // Clamp activeIndex
  const selectableResults = results.filter((r) => r.type !== 'header');
  const maxIndex = Math.max(0, selectableResults.length - 1);

  useEffect(() => {
    setActiveIndex((prev) => Math.min(prev, maxIndex));
  }, [maxIndex]);

  // Scroll active item into view
  useEffect(() => {
    if (!listRef.current) return;
    const activeItem = listRef.current.querySelector('.global-search-item--active');
    if (activeItem) {
      activeItem.scrollIntoView({ block: 'nearest' });
    }
  }, [activeIndex]);

  /**
   * 处理搜索结果选择
   * @function handleSelect
   * @param {Object} result - 选中的搜索结果对象
   * @param {string} result.code - 证券代码
   * @param {string} [result.itemType] - 项目类型（stock/fund）
   * @description 保存搜索记录到本地存储，判断代码类型并触发页面导航
   */
  const handleSelect = useCallback(
    (result) => {
      const code = result.code;
      if (!code) return;
      saveRecentSearch(code);

      const itemType = result.itemType || classifyCode(code);
      const tab = itemType === 'stock' ? 'stock-sector' : 'fund-sector';

      onNavigate({ type: itemType, code, tab });
      onClose();
    },
    [onNavigate, onClose]
  );

  /**
   * 处理键盘事件
   * @function handleKeyDown
   * @param {KeyboardEvent} event - 键盘事件对象
   * @description 处理以下按键：
   * - ArrowDown: 选择下一项
   * - ArrowUp: 选择上一项
   * - Enter: 确认选择当前项
   * - Escape: 关闭搜索面板
   */
  function handleKeyDown(event) {
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        setActiveIndex((prev) => (prev < maxIndex ? prev + 1 : 0));
        break;
      case 'ArrowUp':
        event.preventDefault();
        setActiveIndex((prev) => (prev > 0 ? prev - 1 : maxIndex));
        break;
      case 'Enter':
        event.preventDefault();
        if (selectableResults.length > 0 && activeIndex < selectableResults.length) {
          handleSelect(selectableResults[activeIndex]);
        }
        break;
      case 'Escape':
        event.preventDefault();
        onClose();
        break;
      default:
        break;
    }
  }

  /**
   * 处理遮罩层点击事件
   * @function handleOverlayClick
   * @param {MouseEvent} event - 鼠标点击事件
   * @description 点击遮罩层外部区域时关闭搜索面板
   */
  function handleOverlayClick(event) {
    if (event.target === event.currentTarget) {
      onClose();
    }
  }

  if (!isOpen) return null;

  let selectableIdx = -1;

  return (
    <div className="global-search-overlay" onClick={handleOverlayClick} role="dialog" aria-modal="true">
      <div className="global-search-modal">
        <div className="global-search-input-wrap">
          <span className="global-search-icon" aria-hidden="true">&#128269;</span>
          <input
            ref={inputRef}
            type="text"
            className="global-search-input"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setActiveIndex(0); }}
            onKeyDown={handleKeyDown}
            placeholder={t('globalSearch.placeholder')}
            autoComplete="off"
            role="combobox"
            aria-expanded
            aria-autocomplete="list"
          />
          <kbd className="global-search-kbd">ESC</kbd>
        </div>

        <div className="global-search-results" ref={listRef} role="listbox">
          {results.length === 0 && trimmedQuery ? (
            <div className="global-search-empty">{t('globalSearch.noResults')}</div>
          ) : null}

          {!trimmedQuery && results.length === 0 ? (
            <div className="global-search-hint">{t('globalSearch.hint')}</div>
          ) : null}

          {results.map((result, idx) => {
            if (result.type === 'header') {
              return (
                <div key={`header-${result.label}`} className="global-search-header">
                  {result.label}
                </div>
              );
            }

            selectableIdx++;
            const isActive = selectableIdx === activeIndex;
            const currentSelectableIdx = selectableIdx;

            return (
              <div
                key={`${result.type}-${result.code}-${idx}`}
                className={`global-search-item ${isActive ? 'global-search-item--active' : ''}`}
                role="option"
                aria-selected={isActive}
                onMouseEnter={() => setActiveIndex(currentSelectableIdx)}
                onClick={() => handleSelect(result)}
              >
                <span className="global-search-item__code">{result.code}</span>
                {result.name ? (
                  <span className="global-search-item__name">{result.name}</span>
                ) : null}
                {result.itemType ? (
                  <span className={`badge badge--${result.itemType === 'stock' ? 'good' : 'warn'}`}>
                    {result.itemType === 'stock' ? t('watchlist.stock') : t('watchlist.fund')}
                  </span>
                ) : result.type === 'recent' ? (
                  <span className="global-search-item__type">{classifyCode(result.code)}</span>
                ) : result.type === 'direct' ? (
                  <span className="global-search-item__type">
                    {classifyCode(result.code) === 'stock' ? t('watchlist.stock') : t('watchlist.fund')}
                  </span>
                ) : null}
              </div>
            );
          })}
        </div>

        <div className="global-search-footer">
          <span className="global-search-hint-text">
            <kbd>&uarr;</kbd><kbd>&darr;</kbd> {t('globalSearch.search')}
            <kbd style={{ marginLeft: 12 }}>Enter</kbd> {t('globalSearch.close')}
          </span>
        </div>
      </div>
    </div>
  );
}
