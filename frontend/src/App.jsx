/**
 * @fileoverview 应用主组件 - 微量化投研系统的根组件
 * @module App
 * @description 应用的主入口组件，包含以下核心功能：
 * - 多标签页导航（Dashboard、股票板块、基金板块、市场概览）
 * - 系统状态监控和 LLM 设置管理
 * - 管道触发和运行日志查看
 * - 全局搜索（Ctrl+K）
 * - 懒加载视图组件
 */

import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  getApiBaseUrl,
  getLlmSettings,
  getLogs,
  getLots,
  getStatus,
  saveLlmSettings,
  testLlmSettings,
  triggerRun,
} from './api/client';
import DataSourceStatus from './components/DataSourceStatus';
import ErrorBoundary from './components/ErrorBoundary';
import GlobalSearch from './components/GlobalSearch';
import LanguageSwitcher from './components/LanguageSwitcher';
import SkeletonTable from './components/SkeletonTable';
import ThemeToggle from './components/ThemeToggle';
import ToastContainer from './components/ToastContainer';
import { ToastProvider } from './hooks/useToast';
import useKeyboardShortcut from './hooks/useKeyboardShortcut';

const StockSector = lazy(() => import('./views/StockSector'));
const FundSector = lazy(() => import('./views/FundSector'));
const MarketOverview = lazy(() => import('./views/MarketOverview'));
const WatchlistManagement = lazy(() => import('./views/WatchlistManagement'));

/**
 * 格式化 JSON 值用于显示
 * @function formatJson
 * @param {*} value - 要格式化的值
 * @returns {string} JSON 字符串或原始字符串，空值返回 '—'
 */
function formatJson(value) {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'string') return value;
  try { return JSON.stringify(value, null, 2); } catch { return String(value); }
}

/**
 * 格式化日期时间显示
 * @function formatDate
 * @param {string|null} value - 日期字符串
 * @returns {string} 本地化的日期时间字符串，无效值返回 '—'
 */
function formatDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

/**
 * 格式化数字显示
 * @function formatNumber
 * @param {*} value - 要格式化的值
 * @param {number} [fractionDigits=2] - 保留的小数位数
 * @returns {string} 格式化后的数字字符串，无效值返回 '—'
 */
function formatNumber(value, fractionDigits = 2) {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return '—';
  return numeric.toFixed(fractionDigits);
}

/**
 * 获取状态对应的颜色基调
 * @function getStatusTone
 * @param {string} status - 状态值
 * @returns {'good'|'warn'|'bad'} 对应的颜色基调
 * @description ok/configured/ready/buy/sell → good, degraded/warning/unknown/loading/hold → warn, 其他 → bad
 */
function getStatusTone(status) {
  switch (String(status || '').toLowerCase()) {
    case 'ok': case 'configured': case 'ready': case 'buy': case 'sell': return 'good';
    case 'degraded': case 'warning': case 'unknown': case 'loading': case 'hold': return 'warn';
    default: return 'bad';
  }
}

/**
 * 状态徽章组件
 *
 * @component StatusBadge
 * @description 根据状态值显示颜色编码的徽章
 *
 * @param {Object} props
 * @param {string} props.status - 状态文本
 * @returns {JSX.Element} 状态徽章元素
 */
function StatusBadge({ status }) {
  const tone = getStatusTone(status);
  return <span className={`badge badge--${tone}`}>{status || 'unknown'}</span>;
}

/**
 * 通用面板区块组件
 *
 * @component Section
 * @description 带标题、描述和可选操作按钮的面板容器
 *
 * @param {Object} props
 * @param {string} props.title - 区块标题
 * @param {string} [props.description] - 区块描述文本
 * @param {JSX.Element} [props.action] - 右上角操作按钮区域
 * @param {React.ReactNode} props.children - 区块内容
 * @returns {JSX.Element} 面板区块 JSX
 */
function Section({ title, description, action, children }) {
  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <h2>{title}</h2>
          {description ? <p>{description}</p> : null}
        </div>
        {action ? <div className="section-action">{action}</div> : null}
      </div>
      {children}
    </section>
  );
}

/**
 * 顶部警告横幅组件
 *
 * @component Banner
 * @description 显示模拟交易警告信息
 * @returns {JSX.Element} 警告横幅 JSX
 */
function Banner() {
  const { t } = useTranslation();
  return (
    <div className="warning-banner" role="alert">
      <strong>{t('banner.title')}</strong>
      <span>{t('banner.description')}</span>
    </div>
  );
}

const STATUS_KEYS = ['backend', 'database', 'langgraph', 'chromadb', 'ollama'];

/**
 * 系统状态展示区块
 *
 * @component StatusSection
 * @description 展示后端、数据库、LangGraph、ChromaDB、Ollama 等系统组件的运行状态，
 * 以及最近一次管道运行的详细信息
 *
 * @param {Object} props
 * @param {Object} props.status - 系统状态数据对象
 * @param {boolean} props.loading - 是否正在加载
 * @param {string} props.error - 错误信息
 * @param {Function} props.onRefresh - 刷新回调
 * @returns {JSX.Element} 状态展示区块
 */
function StatusSection({ status, loading, error, onRefresh }) {
  const { t } = useTranslation();
  const cards = useMemo(() => {
    return STATUS_KEYS.map((key) => {
      const item = status?.[key] || {};
      return {
        key,
        label: t(`dashboard.statusCards.${key}`),
        status: item.status || (loading ? 'loading' : 'unknown'),
        detail: item.detail || '',
      };
    });
  }, [loading, status, t]);

  return (
    <Section
      title={t('dashboard.status.title')}
      description={t('dashboard.status.description')}
      action={
        <button type="button" className="button button--secondary" onClick={onRefresh}>
          {t('dashboard.status.refresh')}
        </button>
      }
    >
      {error ? <div className="inline-alert inline-alert--error">{error}</div> : null}
      <div className="status-grid">
        {cards.map((card) => (
          <article key={card.key} className="status-card">
            <div className="status-card__top">
              <h3>{card.label}</h3>
              <StatusBadge status={card.status} />
            </div>
            <p>{card.detail || t('dashboard.status.noDetail')}</p>
          </article>
        ))}
      </div>

      <div className="subpanel">
        <div className="subpanel__header">
          <h3>{t('dashboard.lastRun.title')}</h3>
        </div>
        {status?.last_run ? (
          <dl className="key-value-grid">
            <div><dt>{t('dashboard.lastRun.runId')}</dt><dd>{status.last_run.run_id || '—'}</dd></div>
            <div><dt>{t('dashboard.lastRun.status')}</dt><dd>{status.last_run.status || '—'}</dd></div>
            <div><dt>{t('dashboard.lastRun.asset')}</dt><dd>{status.last_run.asset_code || '—'}</dd></div>
            <div><dt>{t('dashboard.lastRun.route')}</dt><dd>{status.last_run.router_branch || '—'}</dd></div>
            <div><dt>{t('dashboard.lastRun.finalAction')}</dt><dd>{status.last_run.final_action || '—'}</dd></div>
          </dl>
        ) : (
          <p className="empty-state">{t('dashboard.lastRun.empty')}</p>
        )}
      </div>
    </Section>
  );
}

/**
 * LLM 设置管理区块
 *
 * @component SettingsSection
 * @description 管理 Ollama LLM 的连接配置，包括：
 * - API 基础 URL、模型名称、超时设置
 * - API Key 管理（支持持久化存储）
 * - 设置保存和连接测试
 * - 数据源状态展示
 *
 * @param {Object} props
 * @param {Object} props.settings - 当前设置对象
 * @param {Function} props.setSettings - 设置更新函数
 * @param {boolean} props.loading - 是否正在加载
 * @param {string} props.loadError - 加载错误信息
 * @param {Object} props.saveState - 保存状态 { pending, message, error }
 * @param {Object} props.testState - 测试状态 { pending, message, error }
 * @param {Function} props.onSave - 保存设置回调
 * @param {Function} props.onTest - 测试连接回调
 * @returns {JSX.Element} 设置管理区块
 */
function SettingsSection({ settings, setSettings, loading, loadError, saveState, testState, onSave, onTest }) {
  const { t } = useTranslation();

  /**
   * 处理表单输入变更
   * @function handleChange
   * @param {Event} event - 输入变更事件
   * @description 支持 text/number/url/password 类型和 checkbox 类型的输入
   */
  function handleChange(event) {
    const { name, value, type, checked } = event.target;
    setSettings((current) => ({ ...current, [name]: type === 'checkbox' ? checked : value }));
  }

  return (
    <Section title={t('dashboard.settings.title')} description={t('dashboard.settings.description')}>
      {loadError ? <div className="inline-alert inline-alert--error">{loadError}</div> : null}
      {saveState.message ? <div className="inline-alert inline-alert--success">{saveState.message}</div> : null}
      {saveState.error ? <div className="inline-alert inline-alert--error">{saveState.error}</div> : null}
      {testState.message ? <div className="inline-alert inline-alert--success">{testState.message}</div> : null}
      {testState.error ? <div className="inline-alert inline-alert--error">{testState.error}</div> : null}

      {!loading && !settings.has_api_key ? (
        <div className="api-key-warning" role="alert">
          <span className="api-key-warning__icon">{'\u26A0'}</span>
          <span className="api-key-warning__text">{t('toast.apiKeyRequired')}</span>
        </div>
      ) : null}

      {!loading ? (
        <div className="llm-settings-display subpanel">
          <div className="subpanel__header">
            <h3>{t('dashboard.settings.title')}</h3>
            <button type="button" className="button button--sm button--secondary" disabled={testState.pending} onClick={onTest}>
              {testState.pending ? t('dashboard.settings.testing') : t('dashboard.settings.test')}
            </button>
          </div>
          <dl className="llm-settings-grid">
            <div><dt>{t('dashboard.settings.baseUrl')}</dt><dd>{settings.base_url || '--'}</dd></div>
            <div><dt>{t('dashboard.settings.model')}</dt><dd>{settings.model || '--'}</dd></div>
            <div><dt>{t('dashboard.settings.apiKey')}</dt><dd>{settings.has_api_key ? 'true' : 'false'}</dd></div>
          </dl>
        </div>
      ) : null}

      <div className="subpanel">
        <div className="subpanel__header">
          <h3>{t('dataSource.title')}</h3>
        </div>
        <DataSourceStatus />
      </div>

      <form className="settings-form" onSubmit={(e) => { e.preventDefault(); onSave(); }}>
        <label>
          <span>{t('dashboard.settings.baseUrl')}</span>
          <input name="base_url" type="url" value={settings.base_url} onChange={handleChange}
            placeholder="http://127.0.0.1:11434" disabled={loading || saveState.pending} />
        </label>
        <label>
          <span>{t('dashboard.settings.generatePath')}</span>
          <input name="generate_path" type="text" value={settings.generate_path} onChange={handleChange}
            placeholder="/api/generate" disabled={loading || saveState.pending} />
        </label>
        <label>
          <span>{t('dashboard.settings.model')}</span>
          <input name="model" type="text" value={settings.model} onChange={handleChange}
            placeholder="hermes-2-pro" disabled={loading || saveState.pending} />
        </label>
        <label>
          <span>{t('dashboard.settings.timeoutSeconds')}</span>
          <input name="timeout_seconds" type="number" min="1" step="1" value={settings.timeout_seconds}
            onChange={handleChange} placeholder="30" disabled={loading || saveState.pending} />
        </label>
        <label>
          <span>{t('dashboard.settings.apiKey')}</span>
          <input name="api_key" type="password" autoComplete="new-password" value={settings.api_key}
            onChange={handleChange}
            placeholder={settings.has_api_key ? t('dashboard.settings.apiKeyMasked') : t('dashboard.settings.apiKeyPlaceholder')}
            disabled={loading || saveState.pending} />
          <small>{settings.has_api_key ? t('dashboard.settings.apiKeyStored') : t('dashboard.settings.apiKeyNotStored')}</small>
        </label>
        <label className="checkbox-row">
          <input name="persist_api_key" type="checkbox" checked={settings.persist_api_key}
            onChange={handleChange} disabled={loading || saveState.pending} />
          <span>{t('dashboard.settings.persistKey')}</span>
        </label>
        <div className="button-row">
          <button type="submit" className="button" disabled={loading || saveState.pending}>
            {saveState.pending ? t('dashboard.settings.saving') : t('dashboard.settings.save')}
          </button>
          <button type="button" className="button button--secondary" disabled={loading || testState.pending} onClick={onTest}>
            {testState.pending ? t('dashboard.settings.testing') : t('dashboard.settings.test')}
          </button>
        </div>
      </form>
    </Section>
  );
}

/**
 * 管道触发区块
 *
 * @component TriggerSection
 * @description 提供资产代码输入和管道运行触发功能
 *
 * @param {Object} props
 * @param {Function} props.onTriggered - 触发成功后的回调（用于刷新状态）
 * @returns {JSX.Element} 管道触发区块
 */
function TriggerSection({ onTriggered }) {
  const { t } = useTranslation();
  const [assetCode, setAssetCode] = useState('');
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  /**
   * 处理管道触发表单提交
   * @async
   * @function handleSubmit
   * @param {Event} event - 表单提交事件
   * @description 调用 triggerRun API，成功后清空输入并触发刷新回调
   */
  async function handleSubmit(event) {
    event.preventDefault();
    setPending(true); setMessage(''); setError('');
    try {
      const result = await triggerRun(assetCode);
      setMessage(t('dashboard.trigger.success', { runId: result.run_id || 'unknown' }));
      setAssetCode('');
      onTriggered?.();
    } catch (e) {
      setError(e.message || 'Failed to trigger pipeline run.');
    } finally {
      setPending(false);
    }
  }

  return (
    <Section title={t('dashboard.trigger.title')} description={t('dashboard.trigger.description')}>
      {message ? <div className="inline-alert inline-alert--success">{message}</div> : null}
      {error ? <div className="inline-alert inline-alert--error">{error}</div> : null}
      <form className="trigger-form" onSubmit={handleSubmit}>
        <label>
          <span>{t('dashboard.trigger.assetCode')}</span>
          <input type="text" value={assetCode} onChange={(e) => setAssetCode(e.target.value)}
            placeholder={t('dashboard.trigger.assetCodePlaceholder')} disabled={pending} />
        </label>
        <button type="submit" className="button" disabled={pending}>
          {pending ? t('dashboard.trigger.triggering') : t('dashboard.trigger.trigger')}
        </button>
      </form>
    </Section>
  );
}

/**
 * 模拟持仓区块
 *
 * @component LotsSection
 * @description 展示模拟交易的持仓记录表格
 *
 * @param {Object} props
 * @param {Array} props.lots - 持仓记录数组
 * @param {boolean} props.loading - 是否正在加载
 * @param {string} props.error - 错误信息
 * @param {Function} props.onRefresh - 刷新回调
 * @returns {JSX.Element} 持仓展示区块
 */
function LotsSection({ lots, loading, error, onRefresh }) {
  const { t } = useTranslation();
  return (
    <Section title={t('dashboard.lots.title')} description={t('dashboard.lots.description')}
      action={<button type="button" className="button button--secondary" onClick={onRefresh}>{t('dashboard.lots.refresh')}</button>}>
      {error ? <div className="inline-alert inline-alert--error">{error}</div> : null}
      {loading ? <p className="empty-state">{t('dashboard.lots.loading')}</p> : null}
      {!loading && lots.length === 0 ? <p className="empty-state">{t('dashboard.lots.empty')}</p> : null}
      {!loading && lots.length > 0 ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t('dashboard.lots.id')}</th>
                <th>{t('dashboard.lots.asset')}</th>
                <th>{t('dashboard.lots.buyDate')}</th>
                <th>{t('dashboard.lots.shares')}</th>
                <th>{t('dashboard.lots.costPrice')}</th>
                <th>{t('dashboard.lots.holdingDays')}</th>
                <th>{t('dashboard.lots.status')}</th>
              </tr>
            </thead>
            <tbody>
              {lots.map((lot) => (
                <tr key={lot.id}>
                  <td>{lot.id}</td>
                  <td>{lot.asset_code}</td>
                  <td>{formatDate(lot.buy_date)}</td>
                  <td>{formatNumber(lot.shares, 4)}</td>
                  <td>{formatNumber(lot.cost_price, 4)}</td>
                  <td>{lot.holding_days}</td>
                  <td>{lot.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </Section>
  );
}

/**
 * 运行日志区块
 *
 * @component LogsSection
 * @description 展示管道运行的历史日志，包含原始信号和守卫结果
 *
 * @param {Object} props
 * @param {Array} props.logs - 日志记录数组
 * @param {boolean} props.loading - 是否正在加载
 * @param {string} props.error - 错误信息
 * @param {Function} props.onRefresh - 刷新回调
 * @returns {JSX.Element} 日志展示区块
 */
function LogsSection({ logs, loading, error, onRefresh }) {
  const { t } = useTranslation();
  return (
    <Section title={t('dashboard.logs.title')} description={t('dashboard.logs.description')}
      action={<button type="button" className="button button--secondary" onClick={onRefresh}>{t('dashboard.logs.refresh')}</button>}>
      {error ? <div className="inline-alert inline-alert--error">{error}</div> : null}
      {loading ? <p className="empty-state">{t('dashboard.logs.loading')}</p> : null}
      {!loading && logs.length === 0 ? <p className="empty-state">{t('dashboard.logs.empty')}</p> : null}
      {!loading && logs.length > 0 ? (
        <div className="log-list">
          {logs.map((log) => (
            <article key={log.id || log.run_id} className="log-card">
              <div className="log-card__header">
                <div>
                  <h3>{log.run_id}</h3>
                  <p>{formatDate(log.timestamp)}</p>
                </div>
                <StatusBadge status={log.final_action} />
              </div>
              <dl className="key-value-grid key-value-grid--dense">
                <div><dt>{t('dashboard.lots.asset')}</dt><dd>{log.asset_code || '—'}</dd></div>
                <div><dt>{t('dashboard.lastRun.route')}</dt><dd>{log.router_branch || '—'}</dd></div>
              </dl>
              <div className="code-blocks">
                <div><h4>{t('dashboard.logs.rawSignal')}</h4><pre>{formatJson(log.raw_signal)}</pre></div>
                <div><h4>{t('dashboard.logs.guardResult')}</h4><pre>{formatJson(log.guard_result)}</pre></div>
              </div>
            </article>
          ))}
        </div>
      ) : null}
    </Section>
  );
}

/**
 * 应用主组件
 *
 * @component App
 * @description 微量化投研系统的根组件，管理以下功能：
 * - 多标签页导航（Dashboard、股票板块、基金板块、市场概览）
 * - 系统状态监控和 LLM 设置管理
 * - 管道触发和运行日志查看
 * - 全局搜索（Ctrl+K 快捷键）
 * - 懒加载视图组件（React.lazy + Suspense）
 * - 键盘快捷键支持（R 刷新、Ctrl+K 搜索）
 *
 * @returns {JSX.Element} 应用根组件
 *
 * @example
 * // 在 main.jsx 中使用
 * <App />
 */
export default function App() {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState('dashboard');
  const [globalSearchOpen, setGlobalSearchOpen] = useState(false);

  // Ctrl+K / Cmd+K to open global search
  useKeyboardShortcut('k', () => setGlobalSearchOpen(true), { ctrl: true });

  /**
   * 处理全局搜索导航
   * @function handleGlobalSearchNavigate
   * @param {Object} params - 导航参数
   * @param {string} params.type - 证券类型（stock/fund）
   * @param {string} params.code - 证券代码
   * @param {string} params.tab - 目标标签页
   * @description 切换到目标标签页并通过 localStorage 和自定义事件传递证券代码
   */
  function handleGlobalSearchNavigate({ type, code, tab }) {
    setActiveTab(tab);
    // Store the code in localStorage so the target tab can pick it up
    try {
      localStorage.setItem('global_search_code', JSON.stringify({ type, code }));
      // Dispatch a custom event so the active tab can listen
      window.dispatchEvent(new CustomEvent('global-search-navigate', { detail: { type, code } }));
    } catch {
      // ignore
    }
  }
  const [status, setStatus] = useState(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [statusError, setStatusError] = useState('');

  const EMPTY_SETTINGS = useMemo(() => ({
    base_url: '', generate_path: '', model: '', timeout_seconds: '', api_key: '', persist_api_key: false, has_api_key: false,
  }), []);

  const [settings, setSettings] = useState(EMPTY_SETTINGS);
  const [settingsLoading, setSettingsLoading] = useState(true);
  const [settingsLoadError, setSettingsLoadError] = useState('');
  const [saveState, setSaveState] = useState({ pending: false, message: '', error: '' });
  const [testState, setTestState] = useState({ pending: false, message: '', error: '' });

  const [lots, setLots] = useState([]);
  const [lotsLoading, setLotsLoading] = useState(true);
  const [lotsError, setLotsError] = useState('');

  const [logs, setLogs] = useState([]);
  const [logsLoading, setLogsLoading] = useState(true);
  const [logsError, setLogsError] = useState('');

  const apiBaseUrl = getApiBaseUrl();

  const NAV_TABS = useMemo(() => [
    { key: 'dashboard', label: t('nav.dashboard') },
    { key: 'stock-sector', label: t('nav.stockSector') },
    { key: 'fund-sector', label: t('nav.fundSector') },
    { key: 'market-overview', label: t('nav.marketOverview') },
    { key: 'watchlist-management', label: t('nav.watchlistManagement') },
  ], [t]);

  /**
   * 加载系统状态数据
   * @function loadStatus
   * @description 从 API 获取后端各组件的运行状态
   */
  const loadStatus = useCallback(async () => {
    setStatusLoading(true); setStatusError('');
    try { setStatus(await getStatus()); }
    catch (e) { setStatus(null); setStatusError(e.message); }
    finally { setStatusLoading(false); }
  }, []);

  /**
   * 加载 LLM 设置
   * @function loadSettings
   * @description 从 API 获取当前的 LLM 配置信息
   */
  const loadSettings = useCallback(async () => {
    setSettingsLoading(true); setSettingsLoadError('');
    try { setSettings(await getLlmSettings()); }
    catch (e) { setSettings(EMPTY_SETTINGS); setSettingsLoadError(e.message); }
    finally { setSettingsLoading(false); }
  }, [EMPTY_SETTINGS]);

  /**
   * 加载模拟持仓数据
   * @function loadLots
   * @description 从 API 获取模拟交易的持仓记录列表
   */
  const loadLots = useCallback(async () => {
    setLotsLoading(true); setLotsError('');
    try { setLots(Array.isArray(await getLots()) ? await getLots() : []); }
    catch (e) { setLots([]); setLotsError(e.message); }
    finally { setLotsLoading(false); }
  }, []);

  /**
   * 加载运行日志
   * @function loadLogs
   * @description 从 API 获取最近 20 条管道运行日志
   */
  const loadLogs = useCallback(async () => {
    setLogsLoading(true); setLogsError('');
    try { setLogs(Array.isArray(await getLogs(20)) ? await getLogs(20) : []); }
    catch (e) { setLogs([]); setLogsError(e.message); }
    finally { setLogsLoading(false); }
  }, []);

  /**
   * 刷新所有数据
   * @function refreshAll
   * @description 并行加载系统状态、LLM 设置、持仓和日志数据
   */
  const refreshAll = useCallback(async () => {
    await Promise.all([loadStatus(), loadSettings(), loadLots(), loadLogs()]);
  }, [loadLogs, loadLots, loadSettings, loadStatus]);

  // R key to refresh current tab data (skipped when in input fields)
  useKeyboardShortcut('r', refreshAll);

  useEffect(() => { refreshAll(); }, [refreshAll]);

  /**
   * 保存 LLM 设置
   * @async
   * @function handleSaveSettings
   * @description 将当前设置提交到后端保存，成功后更新设置状态
   */
  async function handleSaveSettings() {
    setSaveState({ pending: true, message: '', error: '' });
    setTestState((c) => ({ ...c, message: '', error: '' }));
    try {
      const response = await saveLlmSettings(settings);
      setSettings(response);
      setSaveState({ pending: false, message: t('dashboard.settings.saved'), error: '' });
    } catch (e) {
      setSaveState({ pending: false, message: '', error: e.message });
    }
  }

  /**
   * 测试 LLM 连接
   * @async
   * @function handleTestSettings
   * @description 使用当前设置测试与 Ollama LLM 的连接，显示测试结果
   */
  async function handleTestSettings() {
    setTestState({ pending: true, message: '', error: '' });
    try {
      const response = await testLlmSettings(settings);
      setTestState({ pending: false, message: response?.detail || response?.message || 'OK', error: '' });
    } catch (e) {
      setTestState({ pending: false, message: '', error: e.message });
    }
  }

  return (
    <ToastProvider>
    <main className="app-shell">
      <div className="app-container">
        <header className="hero">
          <div>
            <p className="eyebrow">{t('app.eyebrow')}</p>
            <h1>{t('app.title')}</h1>
            <p className="hero-copy">{t('app.description')}</p>
          </div>
          <div className="hero-meta">
            <div className="hero-meta__top">
              <ThemeToggle />
              <LanguageSwitcher />
              <div className="kbd-hint" title={`${t('keyboardShortcuts.refresh')}: R | ${t('keyboardShortcuts.search')}: Ctrl+K`}>
                <span className="kbd-hint__icon" aria-hidden="true">{'\u2328'}</span>
                <span className="kbd-hint__label">{t('keyboardShortcuts.hint')}</span>
              </div>
            </div>
            <span className="meta-label">{t('app.backendBaseUrl')}</span>
            <code>{apiBaseUrl}</code>
          </div>
        </header>

        <Banner />

        <ErrorBoundary>
        <nav className="tab-nav" aria-label="Primary navigation">
          {NAV_TABS.map((tab) => (
            <button
              key={tab.key}
              type="button"
              className={`tab-nav__button ${activeTab === tab.key ? 'tab-nav__button--active' : ''}`}
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </nav>

        {activeTab === 'dashboard' ? (
          <div className="layout-grid">
            <StatusSection status={status} loading={statusLoading} error={statusError} onRefresh={refreshAll} />
            <SettingsSection settings={settings} setSettings={setSettings} loading={settingsLoading}
              loadError={settingsLoadError} saveState={saveState} testState={testState}
              onSave={handleSaveSettings} onTest={handleTestSettings} />
            <TriggerSection onTriggered={refreshAll} />
            <LotsSection lots={lots} loading={lotsLoading} error={lotsError} onRefresh={loadLots} />
            <LogsSection logs={logs} loading={logsLoading} error={logsError} onRefresh={loadLogs} />
          </div>
        ) : activeTab === 'stock-sector' ? (
          <div className="layout-grid">
            <Suspense fallback={<SkeletonTable rows={8} columns={6} />}>
              <StockSector />
            </Suspense>
          </div>
        ) : activeTab === 'fund-sector' ? (
          <div className="layout-grid">
            <Suspense fallback={<SkeletonTable rows={5} columns={4} />}>
              <FundSector />
            </Suspense>
          </div>
        ) : activeTab === 'market-overview' ? (
          <div className="layout-grid">
            <Suspense fallback={<SkeletonTable rows={3} columns={4} />}>
              <MarketOverview onNavigateTab={setActiveTab} />
            </Suspense>
          </div>
        ) : activeTab === 'watchlist-management' ? (
          <div className="layout-grid">
            <Suspense fallback={<SkeletonTable rows={5} columns={7} />}>
              <WatchlistManagement />
            </Suspense>
          </div>
        ) : null}
        </ErrorBoundary>

        <GlobalSearch
          isOpen={globalSearchOpen}
          onClose={() => setGlobalSearchOpen(false)}
          onNavigate={handleGlobalSearchNavigate}
        />
        <ToastContainer />
      </div>
    </main>
    </ToastProvider>
  );
}
