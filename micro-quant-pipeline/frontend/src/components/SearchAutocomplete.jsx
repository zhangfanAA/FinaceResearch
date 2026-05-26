/**
 * @fileoverview 搜索自动完成组件 - 带防抖、最近搜索和键盘导航的搜索输入框
 * @module components/SearchAutocomplete
 * @description 可复用的搜索输入组件，支持防抖建议、最近搜索记录、静态建议过滤和键盘导航
 */

import { useCallback, useEffect, useRef, useState } from 'react';

const DEBOUNCE_MS = 300;
const MAX_RECENT = 5;

/**
 * SearchAutocomplete -- Input with debounced suggestions, recent searches, and keyboard nav.
 *
 * @param {Object} props
 * @param {string} props.value - Controlled input value
 * @param {Function} props.onChange - Called with new input string
 * @param {Function} props.onSelect - Called when a suggestion or recent item is selected
 * @param {Function} [props.onSearch] - Called when Enter is pressed with the current value
 * @param {Function} [props.onFetchSuggestions] - Async function(query) returning suggestion array
 * @param {string} [props.placeholder] - Input placeholder
 * @param {boolean} [props.disabled] - Whether input is disabled
 * @param {Array} [props.staticSuggestions] - Static list of suggestion strings to filter client-side
 * @param {string} [props.recentKey] - localStorage key for recent searches
 * @param {string} [props.label] - Label text above the input
 */
export default function SearchAutocomplete({
  value,
  onChange,
  onSelect,
  onSearch,
  onFetchSuggestions,
  placeholder = '输入搜索...',
  disabled = false,
  staticSuggestions = [],
  recentKey = 'search_recent_default',
  label,
}) {
  const [open, setOpen] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [recentSearches, setRecentSearches] = useState([]);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [loading, setLoading] = useState(false);

  const wrapperRef = useRef(null);
  const inputRef = useRef(null);
  const debounceRef = useRef(null);

  // Load recent searches from localStorage
  useEffect(() => {
    try {
      const stored = localStorage.getItem(recentKey);
      if (stored) {
        setRecentSearches(JSON.parse(stored));
      }
    } catch {
      // ignore
    }
  }, [recentKey]);

  const saveRecent = useCallback(
    (term) => {
      if (!term || !term.trim()) return;
      const trimmed = term.trim();
      setRecentSearches((prev) => {
        const next = [trimmed, ...prev.filter((r) => r !== trimmed)].slice(0, MAX_RECENT);
        try {
          localStorage.setItem(recentKey, JSON.stringify(next));
        } catch {
          // ignore
        }
        return next;
      });
    },
    [recentKey]
  );

  // Debounced fetch/filter suggestions
  useEffect(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }

    const query = value?.trim();
    if (!query) {
      setSuggestions([]);
      return;
    }

    debounceRef.current = setTimeout(async () => {
      // If an async fetcher is provided, use it
      if (onFetchSuggestions) {
        setLoading(true);
        try {
          const results = await onFetchSuggestions(query);
          setSuggestions(Array.isArray(results) ? results : []);
        } catch {
          setSuggestions([]);
        } finally {
          setLoading(false);
        }
      } else if (staticSuggestions.length > 0) {
        // Client-side filter of static suggestions
        const lower = query.toLowerCase();
        const filtered = staticSuggestions.filter((s) => {
          const text = typeof s === 'string' ? s : s.code || s.label || '';
          return text.toLowerCase().includes(lower);
        });
        setSuggestions(filtered);
      }
    }, DEBOUNCE_MS);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [value, onFetchSuggestions, staticSuggestions]);

  // Close on outside click
  useEffect(() => {
    function handleClickOutside(event) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Build the dropdown items list
  const query = value?.trim();
  const showRecent = !query && recentSearches.length > 0;
  const showSuggestions = query && suggestions.length > 0;
  const dropdownItems = showRecent
    ? recentSearches.map((r) => ({ type: 'recent', text: r }))
    : showSuggestions
    ? suggestions.map((s) => ({
        type: 'suggestion',
        text: typeof s === 'string' ? s : s.code || s.label || '',
        label: typeof s === 'string' ? s : s.label || s.code || '',
        sub: typeof s === 'object' ? s.sub || '' : '',
      }))
    : [];

  const isOpen = open && (dropdownItems.length > 0 || loading);

  function handleSelect(text) {
    onChange(text);
    onSelect?.(text);
    saveRecent(text);
    setOpen(false);
    setActiveIndex(-1);
  }

  function handleKeyDown(event) {
    if (!isOpen) {
      if (event.key === 'ArrowDown' && dropdownItems.length > 0) {
        setOpen(true);
        setActiveIndex(0);
        event.preventDefault();
      }
      return;
    }

    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        setActiveIndex((prev) => (prev < dropdownItems.length - 1 ? prev + 1 : 0));
        break;
      case 'ArrowUp':
        event.preventDefault();
        setActiveIndex((prev) => (prev > 0 ? prev - 1 : dropdownItems.length - 1));
        break;
      case 'Enter':
        event.preventDefault();
        if (activeIndex >= 0 && activeIndex < dropdownItems.length) {
          handleSelect(dropdownItems[activeIndex].text);
        } else {
          saveRecent(value);
          onSearch?.(value);
          setOpen(false);
        }
        break;
      case 'Escape':
        setOpen(false);
        setActiveIndex(-1);
        break;
      default:
        break;
    }
  }

  function handleFocus() {
    setOpen(true);
    setActiveIndex(-1);
  }

  function handleChange(event) {
    onChange(event.target.value);
    setActiveIndex(-1);
    if (!open) setOpen(true);
  }

  function clearRecent() {
    setRecentSearches([]);
    try {
      localStorage.removeItem(recentKey);
    } catch {
      // ignore
    }
  }

  return (
    <div className="autocomplete" ref={wrapperRef}>
      {label ? (
        <label className="autocomplete__label">
          <span>{label}</span>
        </label>
      ) : null}
      <div className="autocomplete__input-wrap">
        <input
          ref={inputRef}
          type="text"
          className="autocomplete__input"
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          onFocus={handleFocus}
          placeholder={placeholder}
          disabled={disabled}
          autoComplete="off"
          role="combobox"
          aria-expanded={isOpen}
          aria-autocomplete="list"
          aria-haspopup="listbox"
        />
        {value ? (
          <button
            type="button"
            className="autocomplete__clear"
            onClick={() => {
              onChange('');
              setSuggestions([]);
              inputRef.current?.focus();
            }}
            aria-label="清除"
          >
            &times;
          </button>
        ) : null}
      </div>

      {isOpen ? (
        <ul className="autocomplete__dropdown" role="listbox">
          {showRecent && !query ? (
            <li className="autocomplete__dropdown-header">
              <span>最近搜索</span>
              <button
                type="button"
                className="autocomplete__clear-recent"
                onClick={(e) => {
                  e.stopPropagation();
                  clearRecent();
                }}
              >
                清除
              </button>
            </li>
          ) : null}
          {dropdownItems.map((item, index) => (
            <li
              key={`${item.type}-${item.text}-${index}`}
              className={`autocomplete__item ${
                index === activeIndex ? 'autocomplete__item--active' : ''
              }`}
              role="option"
              aria-selected={index === activeIndex}
              onMouseEnter={() => setActiveIndex(index)}
              onMouseDown={(e) => {
                e.preventDefault();
                handleSelect(item.text);
              }}
            >
              {item.type === 'recent' ? (
                <span className="autocomplete__item-recent-icon">&#8635;</span>
              ) : null}
              <span className="autocomplete__item-text">
                {item.label || item.text}
              </span>
              {item.sub ? (
                <span className="autocomplete__item-sub">{item.sub}</span>
              ) : null}
            </li>
          ))}
          {loading ? (
            <li className="autocomplete__loading">搜索中...</li>
          ) : null}
          {query && !loading && suggestions.length === 0 ? (
            <li className="autocomplete__empty">无匹配结果</li>
          ) : null}
        </ul>
      ) : null}
    </div>
  );
}
