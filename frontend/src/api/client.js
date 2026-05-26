/**
 * @fileoverview API 客户端模块 - 封装所有后端 API 请求
 * @module api/client
 * @description 提供统一的 HTTP 请求封装和各业务模块的 API 调用函数，
 * 包括系统状态、LLM 设置、股票板块、基金板块、市场总览、分析历史、自选基金等接口
 */

import { getCached, setCached, DEFAULT_TTL } from '../hooks/useApiCache';

/** @type {string} API 基础 URL，优先使用环境变量配置 */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

/**
 * 通用请求函数 - 封装 fetch API，统一处理响应和错误
 *
 * @async
 * @param {string} path - API 路径（相对于基础 URL）
 * @param {Object} [options={}] - fetch 请求选项
 * @param {Object} [options.headers] - 自定义请求头
 * @param {string} [options.method] - HTTP 方法（GET/POST/PUT/DELETE）
 * @param {string} [options.body] - 请求体（JSON 字符串）
 * @returns {Promise<Object|string>} 解析后的响应数据（JSON 或文本）
 * @throws {Error} 请求失败时抛出包含状态码和错误信息的错误对象
 */
async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  });

  const contentType = response.headers.get('content-type') || '';
  const isJson = contentType.includes('application/json');
  const payload = isJson ? await response.json() : await response.text();

  if (!response.ok) {
    const detail =
      (payload && typeof payload === 'object' && (payload.detail || payload.message)) ||
      (typeof payload === 'string' && payload) ||
      `Request failed with status ${response.status}`;

    const error = new Error(detail);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }

  return payload;
}

/**
 * 清理 LLM 设置表单数据，准备发送到后端
 *
 * @param {Object} input - 表单输入数据
 * @param {string} input.base_url - LLM 服务基础 URL
 * @param {string} input.generate_path - 生成接口路径
 * @param {string} input.model - 模型名称
 * @param {number|string} input.timeout_seconds - 超时时间（秒）
 * @param {boolean} input.persist_api_key - 是否持久化 API Key
 * @param {string} [input.api_key] - API Key（可选）
 * @param {Object} [options] - 选项
 * @param {boolean} [options.includeApiKey=true] - 是否包含 API Key
 * @returns {Object} 清理后的请求体数据
 */
function sanitizeSettingsPayload(input, { includeApiKey = true } = {}) {
  const payload = {
    base_url: input.base_url?.trim() || '',
    generate_path: input.generate_path?.trim() || '',
    model: input.model?.trim() || '',
    timeout_seconds: Number(input.timeout_seconds),
    persist_api_key: Boolean(input.persist_api_key),
  };

  if (includeApiKey && input.api_key?.trim()) {
    payload.api_key = input.api_key.trim();
  }

  return payload;
}

/**
 * 标准化 LLM 设置响应数据，确保字段类型一致
 *
 * @param {Object} [payload={}] - 后端返回的原始设置数据
 * @returns {Object} 标准化后的设置对象
 * @property {string} base_url - LLM 服务基础 URL
 * @property {string} generate_path - 生成接口路径
 * @property {string} model - 模型名称
 * @property {string} timeout_seconds - 超时时间（字符串形式，便于表单绑定）
 * @property {boolean} persist_api_key - 是否持久化 API Key
 * @property {boolean} has_api_key - 是否已配置 API Key
 * @property {string} api_key - API Key（始终为空字符串，不从后端返回）
 */
function normalizeSettingsResponse(payload = {}) {
  return {
    base_url: payload.base_url || '',
    generate_path: payload.generate_path || '',
    model: payload.model || '',
    timeout_seconds:
      payload.timeout_seconds === undefined || payload.timeout_seconds === null
        ? ''
        : String(payload.timeout_seconds),
    persist_api_key: Boolean(payload.persist_api_key),
    has_api_key: Boolean(payload.has_api_key),
    api_key: '',
  };
}

/* ==========================================================================
   系统状态 API
   ========================================================================== */

/**
 * 获取 API 基础 URL
 *
 * @returns {string} 当前配置的 API 基础 URL
 */
export function getApiBaseUrl() {
  return API_BASE_URL;
}

/**
 * 获取系统状态信息
 *
 * @async
 * @returns {Promise<Object>} 系统状态数据，包含后端、数据库、LangGraph、ChromaDB、Ollama 等组件状态
 */
export function getStatus() {
  return request('/api/status');
}

/**
 * 获取持仓列表（Lots）
 *
 * @async
 * @returns {Promise<Array>} 持仓数据数组，每项包含 id、asset_code、buy_date、shares 等字段
 */
export function getLots() {
  return request('/api/lots');
}

/**
 * 获取运行日志
 *
 * @async
 * @param {number} [limit=20] - 返回的日志条数
 * @returns {Promise<Array>} 日志数据数组
 */
export function getLogs(limit = 20) {
  return request(`/api/logs?limit=${encodeURIComponent(limit)}`);
}

/**
 * 触发一次 Pipeline 运行
 *
 * @async
 * @param {string} [assetCode] - 资产代码（可选）
 * @returns {Promise<Object>} 运行结果，包含 run_id 等信息
 */
export function triggerRun(assetCode) {
  const trimmed = assetCode?.trim();
  return request('/api/trigger', {
    method: 'POST',
    body: JSON.stringify(trimmed ? { asset_code: trimmed } : {}),
  });
}

/* ==========================================================================
   LLM 设置 API
   ========================================================================== */

/**
 * 获取当前 LLM 配置
 *
 * @async
 * @returns {Promise<Object>} 标准化后的 LLM 设置对象
 */
export function getLlmSettings() {
  return request('/api/settings/llm').then(normalizeSettingsResponse);
}

/**
 * 保存 LLM 配置
 *
 * @async
 * @param {Object} formState - 表单状态数据
 * @returns {Promise<Object>} 保存后的 LLM 设置对象
 */
export function saveLlmSettings(formState) {
  return request('/api/settings/llm', {
    method: 'PUT',
    body: JSON.stringify(sanitizeSettingsPayload(formState, { includeApiKey: true })),
  }).then(normalizeSettingsResponse);
}

/**
 * 测试 LLM 连接配置
 *
 * @async
 * @param {Object} formState - 表单状态数据
 * @returns {Promise<Object>} 测试结果
 */
export function testLlmSettings(formState) {
  return request('/api/settings/llm/test', {
    method: 'POST',
    body: JSON.stringify(sanitizeSettingsPayload(formState, { includeApiKey: true })),
  });
}

/* ==========================================================================
   基金分析 API（旧版 Research Dashboard 使用）
   ========================================================================== */

/**
 * 分析基金板块情绪与资讯
 *
 * @async
 * @param {string} assetCode - 基金代码
 * @param {string} [prompt=''] - 自定义分析提示词，为空时使用默认提示
 * @returns {Promise<Object>} 分析结果，包含 sentiment、score、logic、suggestion 等字段
 */
export async function analyzeFund(assetCode, prompt = '') {
  const trimmedAssetCode = assetCode?.trim() || '';
  const defaultPrompt = `请利用联网搜索，分析 ${trimmedAssetCode} 对应基金板块的今日宏观情绪与最新资讯，并严格按 JSON 格式返回 sentiment, score, logic 和 suggestion。`;

  return request('/api/funds/analyze', {
    method: 'POST',
    body: JSON.stringify({
      fund_code: trimmedAssetCode,
      custom_prompt: prompt?.trim() || defaultPrompt,
    }),
  });
}

/* ==========================================================================
   股票板块 API
   ========================================================================== */

/**
 * 获取股票实时行情数据（带缓存）
 *
 * @async
 * @param {string[]} codes - 股票代码数组
 * @returns {Promise<Array>} 股票实时数据数组
 */
export function getStockRealtime(codes) {
  const path = '/api/stocks/realtime';
  const params = { codes };
  const cached = getCached(path, params);
  if (cached) return Promise.resolve(cached);
  const encoded = encodeURIComponent(codes.join(','));
  return request(`/api/stocks/realtime?codes=${encoded}`).then((data) => {
    setCached(path, data, DEFAULT_TTL.stockRealtime, params);
    return data;
  });
}

/**
 * 获取板块排行数据（带缓存）
 *
 * @async
 * @param {string} [type='industry'] - 板块类型：'industry'（行业）或 'concept'（概念）
 * @param {number} [limit=20] - 返回数量
 * @returns {Promise<Array>} 板块数据数组
 */
export function getStockSectors(type = 'industry', limit = 20) {
  const path = '/api/stocks/sectors';
  const params = { type, limit };
  const cached = getCached(path, params);
  if (cached) return Promise.resolve(cached);
  return request(`/api/stocks/sectors?type=${encodeURIComponent(type)}&limit=${limit}`).then((data) => {
    setCached(path, data, DEFAULT_TTL.stockSectors, params);
    return data;
  });
}

/**
 * AI 分析股票板块
 *
 * @async
 * @param {Object} params - 分析参数
 * @param {string} [params.sectorName] - 板块名称
 * @param {string} [params.stockCode] - 股票代码
 * @param {string} [params.sectorType='industry'] - 板块类型
 * @returns {Promise<Object>} 分析结果，包含 trend、sentiment_score、reasoning 等字段
 */
export function analyzeStockSector({ sectorName, stockCode, sectorType = 'industry' }) {
  const body = {};
  if (sectorName) body.sector_name = sectorName;
  if (stockCode) body.stock_code = stockCode;
  body.sector_type = sectorType;
  return request('/api/stocks/analyze', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/* ==========================================================================
   基金板块 API
   ========================================================================== */

/**
 * 获取基金净值数据（带缓存）
 *
 * @async
 * @param {string[]} codes - 基金代码数组
 * @returns {Promise<Array>} 基金净值数据数组
 */
export function getFundNav(codes) {
  const path = '/api/funds/nav';
  const params = { codes };
  const cached = getCached(path, params);
  if (cached) return Promise.resolve(cached);
  const encoded = encodeURIComponent(codes.join(','));
  return request(`/api/funds/nav?codes=${encoded}`).then((data) => {
    setCached(path, data, DEFAULT_TTL.fundNav, params);
    return data;
  });
}

/**
 * AI 分析基金板块
 *
 * @async
 * @param {string} fundCode - 基金代码
 * @param {string} [customPrompt=''] - 自定义分析提示词
 * @returns {Promise<Object>} 分析结果，包含 judgment、suggestion、reasoning 等字段
 */
export function analyzeFundSector(fundCode, customPrompt = '') {
  const body = { fund_code: fundCode };
  if (customPrompt?.trim()) {
    body.custom_prompt = customPrompt.trim();
  }
  return request('/api/funds/analyze', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/* ==========================================================================
   市场总览 API
   ========================================================================== */

/**
 * 获取市场总览数据（带缓存）
 *
 * @async
 * @returns {Promise<Object>} 市场总览数据，包含 vix、major_indices、top_sectors、bottom_sectors 等
 */
export function getMarketOverview() {
  const path = '/api/market/overview';
  const cached = getCached(path);
  if (cached) return Promise.resolve(cached);
  return request(path).then((data) => {
    setCached(path, data, DEFAULT_TTL.marketOverview);
    return data;
  });
}

/* ==========================================================================
   分析历史 API
   ========================================================================== */

/**
 * 获取分析历史记录
 *
 * @async
 * @param {string} [type='all'] - 筛选类型：'all'、'stock_sector'、'fund_sector'
 * @param {number} [limit=20] - 返回数量
 * @returns {Promise<Array>} 分析历史记录数组
 */
export function getAnalysisHistory(type = 'all', limit = 20) {
  return request(`/api/analysis/history?type=${encodeURIComponent(type)}&limit=${limit}`);
}

/**
 * 获取分析结果对比数据
 *
 * @async
 * @param {string[]} ids - 要对比的分析记录 ID 数组
 * @returns {Promise<Array>} 对比数据数组
 */
export function getAnalysisComparison(ids) {
  const encoded = ids.join(',');
  return request(`/api/analysis/history/compare?ids=${encodeURIComponent(encoded)}`);
}

/* ==========================================================================
   自选股/基金 API（Watchlist）
   ========================================================================== */

/**
 * 获取自选列表
 *
 * @async
 * @param {string} [type='all'] - 筛选类型：'all'、'stock'、'fund'
 * @returns {Promise<Array>} 自选列表数据
 */
export function getWatchlist(type = 'all') {
  return request(`/api/watchlist?type=${encodeURIComponent(type)}`);
}

/**
 * 添加自选项目
 *
 * @async
 * @param {string} itemType - 项目类型：'stock' 或 'fund'
 * @param {string} code - 代码
 * @param {string} [name=null] - 名称（可选）
 * @param {Object} [purchaseInfo={}] - 购买信息（基金专用）
 * @param {number} [purchaseInfo.purchase_amount] - 购买金额
 * @param {number} [purchaseInfo.purchase_nav] - 购买净值
 * @param {string} [purchaseInfo.purchase_date] - 购买日期
 * @param {number} [purchaseInfo.shares] - 持有份额
 * @returns {Promise<Object>} 添加结果
 */
export function addToWatchlist(itemType, code, name = null, purchaseInfo = {}) {
  const body = { item_type: itemType, code };
  if (name) body.name = name;
  if (purchaseInfo.purchase_amount) body.purchase_amount = purchaseInfo.purchase_amount;
  if (purchaseInfo.purchase_nav) body.purchase_nav = purchaseInfo.purchase_nav;
  if (purchaseInfo.purchase_date) body.purchase_date = purchaseInfo.purchase_date;
  if (purchaseInfo.shares) body.shares = purchaseInfo.shares;
  return request('/api/watchlist', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/**
 * 删除自选项目
 *
 * @async
 * @param {number|string} itemId - 自选项目 ID
 * @returns {Promise<Object>} 删除结果
 */
export function removeFromWatchlist(itemId) {
  return request(`/api/watchlist/${itemId}`, {
    method: 'DELETE',
  });
}

/**
 * 重新排序自选列表
 *
 * @async
 * @param {Array<number|string>} itemIds - 按新顺序排列的项目 ID 数组
 * @returns {Promise<Object>} 排序结果
 */
export function reorderWatchlist(itemIds) {
  return request('/api/watchlist/reorder', {
    method: 'PUT',
    body: JSON.stringify({ item_ids: itemIds }),
  });
}

/**
 * 通过图片解析自选项目（OCR 识别持仓截图）
 *
 * @async
 * @param {string} imageBase64 - 图片的 Base64 编码字符串
 * @returns {Promise<Object>} 解析结果，包含识别出的项目列表
 */
export function parseWatchlistImage(imageBase64) {
  return request('/api/watchlist/parse-image', {
    method: 'POST',
    body: JSON.stringify({ image_base64: imageBase64 }),
  });
}

/**
 * 更新自选项目信息
 *
 * @async
 * @param {number|string} itemId - 自选项目 ID
 * @param {Object} updates - 要更新的字段
 * @returns {Promise<Object>} 更新结果
 */
export function updateWatchlistItem(itemId, updates) {
  return request(`/api/watchlist/${itemId}`, {
    method: 'PUT',
    body: JSON.stringify(updates),
  });
}

/* ==========================================================================
   自选管理操作 API（Watchlist Management Operations）
   ========================================================================== */

/**
 * 添加自选操作记录（加仓/减仓）
 *
 * @async
 * @param {number|string} itemId - 自选项目 ID
 * @param {Object} data - 操作数据
 * @param {string} data.operation_type - 操作类型：'add'（加仓）或 'reduce'（减仓）
 * @param {number} [data.amount] - 操作金额
 * @param {number} [data.shares] - 操作份额
 * @param {number} [data.nav] - 操作净值
 * @param {string} [data.note] - 备注
 * @returns {Promise<Object>} 操作结果
 */
export function addWatchlistOperation(itemId, data) {
  return request(`/api/watchlist/${itemId}/operations`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * 获取自选项目的操作记录
 *
 * @async
 * @param {number|string} itemId - 自选项目 ID
 * @returns {Promise<Array>} 操作记录数组
 */
export function getWatchlistOperations(itemId) {
  return request(`/api/watchlist/${itemId}/operations`);
}

/**
 * 获取自选列表汇总统计
 *
 * @async
 * @returns {Promise<Object>} 汇总统计数据
 */
export function getWatchlistSummary() {
  return request('/api/watchlist/summary');
}

/* ==========================================================================
   基金持仓 API
   ========================================================================== */

/**
 * 获取基金持仓详情列表
 *
 * @async
 * @returns {Promise<Array>} 基金持仓数据，包含净值、收益率、盈亏等信息
 */
export function getFundHoldings() {
  return request('/api/fund-holdings');
}

/* ==========================================================================
   AI 风向标 API
   ========================================================================== */

/**
 * 获取 AI 风向标数据
 *
 * @async
 * @param {boolean} [forceRefresh=false] - 是否强制刷新（忽略缓存）
 * @returns {Promise<Object>} AI 风向标数据，包含 hot_sectors、fund_recommendations、market_sentiment 等
 */
export function getAIWind(forceRefresh = false) {
  return request('/api/funds/ai-wind', {
    method: 'POST',
    body: JSON.stringify({ force_refresh: forceRefresh }),
  });
}

/**
 * 获取基金实时净值
 *
 * @async
 * @param {string[]} codes - 基金代码数组
 * @returns {Promise<Array>} 基金实时净值数据数组
 */
export function getFundNavRealtime(codes) {
  const encoded = encodeURIComponent(codes.join(','));
  return request(`/api/funds/nav-realtime?codes=${encoded}`);
}

/* ==========================================================================
   数据源状态 API
   ========================================================================== */

/**
 * 获取数据源适配器状态
 *
 * @async
 * @returns {Promise<Object>} 数据源状态对象，键为适配器名称（akshare/eastmoney/mock），
 *   值包含 success_count、failure_count、avg_latency_ms、last_error 等统计信息
 */
export function getDataSourceStatus() {
  return request('/api/system/data-source-status');
}
