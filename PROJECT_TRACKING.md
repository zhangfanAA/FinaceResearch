# 微量化系统 - 迭代跟进文档

更新日期：2026-05-25

---

## 一、迭代目标

将现有 Paper-only MVP 升级为具备**实时数据 + AI 分析**能力的 C/S 架构微量化系统：

| 板块 | 核心能力 | 状态 |
|------|---------|------|
| 股票板块 | 实时行情获取 + AI 板块分析 + 技术指标 | 进行中 |
| 基金板块 | 新闻舆情 + 实时净值 + AI 综合研判 | 进行中 |
| 系统架构 | C/S 架构，前后端分离，API 标准化 | 已完成 |
| LLM 接入 | MIMO-V2.5-PRO (OpenAI 兼容协议) | 已接入 |
| 国际化 | 中英文双语切换 + i18n 架构 | 已完成 |
| 自定义持仓 | 用户自选股票/基金管理 (文字+图片) | 已完成 |
| 数据可靠性 | 多数据源降级链路 + 代理穿透 | 已完成 |
| UX 优化 | 全局搜索 Ctrl+K + 导出 + 对比 | 已完成 |

---

## 二、架构设计总览

### 2.1 目标 C/S 架构

```
┌─────────────────────────────────────────────────────────┐
│                    Client (React SPA)                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
│  │ 股票面板  │  │ 基金面板  │  │ 持仓管理  │  │ 系统设置 │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬────┘ │
│       └──────────────┴──────────────┴─────────────┘     │
│                         HTTP/REST                        │
└─────────────────────────┬───────────────────────────────┘
                          │
┌─────────────────────────┴───────────────────────────────┐
│                  Server (FastAPI + LangGraph)             │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐ │
│  │ 股票分析引擎  │  │ 基金研判引擎  │  │ 持仓/风控引擎  │ │
│  │ - 实时行情    │  │ - 新闻聚合    │  │ - FIFO Lot    │ │
│  │ - 技术指标    │  │ - 净值追踪    │  │ - C类7天限制   │ │
│  │ - AI板块分析  │  │ - AI综合研判  │  │ - Paper执行    │ │
│  └──────┬───────┘  └──────┬───────┘  └───────┬────────┘ │
│         │                 │                   │          │
│  ┌──────┴─────────────────┴───────────────────┴───────┐ │
│  │              LLM Layer (MIMO-V2.5-PRO)              │ │
│  │         OpenAI Compatible: token-plan-cn            │ │
│  └─────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────┐ │
│  │         Data Layer (SQLite + ChromaDB RAG)          │ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### 2.2 新增 API 端点规划 (详见 ARCHITECTURE_UPGRADE_V2.md 第 3.8 节)

| 方法 | 路径 | 用途 | 状态 |
|------|------|------|------|
| GET | `/api/stocks/realtime?codes=...` | 股票实时行情 | 待开发 |
| GET | `/api/stocks/sectors?type=industry` | 板块行情排名 | 待开发 |
| POST | `/api/stocks/analyze` | AI 板块分析 | 待开发 |
| GET | `/api/funds/nav?codes=...` | 基金实时净值 | 待开发 |
| POST | `/api/funds/analyze` | AI 基金综合研判 | 待开发 |
| GET | `/api/market/overview` | 市场总览 | 待开发 |

---

## 三、迭代进度

> 详细架构设计见 `ARCHITECTURE_UPGRADE_V2.md`

### Phase 1: 数据层升级 (已完成)

- [x] 安装 akshare / pandas / pandas_ta 依赖
- [x] database.py 新增 4 张缓存表
- [x] stock_service.py: AkShare A股实时行情 + 板块排名 + 技术指标
- [x] fund_service.py: AkShare 基金净值 + 新闻聚合
- [x] 单元测试: test_stock_service.py (15 tests), test_fund_service.py (16 tests)

### Phase 2: AI 分析引擎 (已完成)

- [x] prompts.py 新增 STOCK_SECTOR / FUND_ANALYSIS 系统提示词
- [x] stock_analysis_service.py: 板块 AI 分析编排
- [x] fund_analysis_service.py: 基金 AI 研判编排
- [x] models.py 新增 Stock/Fund 相关 Pydantic 模型

### Phase 3: API 端点 (已完成)

- [x] main.py 新增 6 个端点 (stocks/realtime, sectors, analyze; funds/nav, analyze; market/overview)
- [x] config.py 新增 DataSourceConfig
- [x] config.yaml 新增 data_sources 段
- [x] 测试: 86 passed, 0 failed

### Phase 4: 前端升级 (已完成)

- [x] api/client.js 新增 6 个 API 函数
- [x] StockSector.jsx: 板块排名 + AI 分析面板
- [x] FundSector.jsx: 基金净值 + AI 研判面板
- [x] MarketOverview.jsx: 市场总览面板
- [x] App.jsx 新增 3 个 Tab (stock-sector, fund-sector, market-overview)
- [x] 提取共享组件 (SentimentMeter, AnalysisLoadingState)
- [x] npm run build 通过

### Phase 5: 系统集成与优化 (已完成)

- [x] 全链路联调测试 - 所有端点可用
- [x] 错误处理完善 - AkShare 网络异常自动降级到 mock 数据
- [x] 修复 dataclasses slots=True 的 __dict__ 问题
- [x] 前端自动刷新 (StockSector 60s, MarketOverview 30s, FundSector 5min)
- [x] 数据新鲜度指示器 (绿色/黄色/红色)
- [x] 骨架屏加载状态
- [x] 错误重试按钮
- [x] 响应式布局优化

### Phase 6: 进阶功能 (已完成)

- [x] AI 分析历史记录查看 (GET /api/analysis/history, AnalysisHistory 组件)
- [x] 股票/基金搜索自动补全 (SearchAutocomplete 组件, localStorage 持久化)
- [x] 前端: StockSector/FundSector 集成搜索和历史
- [x] 技术指标图表可视化 (TechnicalChart 组件: MA/RSI/MACD/KDJ/Bollinger)
- [x] Sparkline 组件 (用于净值趋势等)
- [x] 后端: 90 tests pass
- [x] 前端: 48 modules build clean

### Phase 7: 系统完善 (进行中)

- [ ] 分析结果对比功能
- [ ] 导出分析报告
- [ ] WebSocket 实时推送
- [ ] 更多技术指标
- [ ] 性能优化

### Phase 8: 国际化 (i18n) (已完成)

**目标**: 支持中英文双语切换，统一 UI 语言管理

- [x] 前端 i18n 框架搭建 (react-i18next)
  - 安装 `react-i18next`, `i18next`, `i18next-browser-languagedetector`
  - 创建 `frontend/src/i18n/index.js` 配置文件
  - 创建 `frontend/src/i18n/locales/zh.json` 中文语言包 (~360 key)
  - 创建 `frontend/src/i18n/locales/en.json` 英文语言包
- [x] 语言切换器组件 (`LanguageSwitcher.jsx`)
  - 支持 localStorage 持久化用户语言偏好
  - 中/EN 按钮组切换，放置在 App.jsx header 右上角
- [x] Dashboard 面板国际化 (App.jsx)
  - StatusSection / SettingsSection / TriggerSection / LotsSection / LogsSection
  - Banner: PAPER/DRY-RUN ONLY 提示文本
- [x] StockSector 面板国际化
  - 板块类型选择器、表格列头、分析按钮
  - AI 分析结果面板 (趋势/动量/情绪/关键因素/风险提示)
- [x] FundSector 面板国际化
  - 持仓概览、基金代码查询、净值表格
  - AI 研判结果面板 (判断/情绪/净值趋势/新闻/风险)
- [x] MarketOverview 面板国际化
  - VIX 恐慌指数、主要指数名称映射
  - 涨跌幅前5板块标题、数据更新时间格式
- [x] ResearchDashboard 面板国际化
- [x] 共享组件国际化 (AnalysisHistory)
- [x] 前端: 72 modules build clean

### Phase 9: 用户自选基金管理 (已完成)

**目标**: 用户可自由添加/删除自选股票和基金，持久化到本地

- [x] 后端: 自选列表 CRUD API
  - 新增 SQLite 表 `user_watchlist` (id, item_type, code, name, added_at, sort_order)
  - `GET /api/watchlist?type=all|stock|fund` - 获取自选列表
  - `POST /api/watchlist` - 添加自选 (body: {item_type, code, name})
  - `DELETE /api/watchlist/{id}` - 删除自选
  - `PUT /api/watchlist/reorder` - 批量排序
  - `POST /api/watchlist/parse-image` - 图片识别股票/基金代码
- [x] 后端: 自选列表服务层 (`watchlist_service.py`)
  - 添加/删除/查询/排序逻辑
  - 自动去重校验
  - 支持从 AkShare 补充股票/基金名称
- [x] 后端: OCR 服务 (`ocr_service.py`)
  - 正则提取 6 位股票/基金代码
  - pytesseract 图片 OCR (可选依赖，graceful fallback)
- [x] 后端: 33 个新测试全部通过
- [x] 前端: 自选管理组件 (`WatchlistManager.jsx`)
  - 输入代码添加 (股票/基金类型切换)
  - 图片上传识别 (拖拽/点击上传，预览，识别结果确认)
  - 自选列表: 显示代码、名称、分析/删除按钮
- [x] 前端: StockSector 集成自选侧边栏
- [x] 前端: FundSector 集成自选侧边栏
- [x] 前端: client.js 新增 5 个 watchlist API 函数
- [x] 修复: `analyzeFund()` 旧端点 `/api/research/analyze` -> `/api/funds/analyze`
  - 拖拽排序 (可选)、删除确认
  - 分组展示: 股票组 + 基金组
- [ ] 前端: StockSector 集成自选
  - 侧边栏显示自选股票列表
  - 点击自选股票直接触发 AI 分析
  - 一键添加当前分析的股票到自选
- [ ] 前端: FundSector 集成自选
  - 侧边栏显示自选基金列表 (与持仓并列)
  - 点击自选基金直接触发 AI 研判
  - 一键添加当前分析的基金到自选
- [ ] 前端: MarketOverview 集成自选
  - 显示自选股票的实时行情摘要卡片

**关键文件变更**:
```
backend/app/
  services/watchlist_service.py   # NEW - 自选列表服务
  main.py                         # MODIFY - 新增 4 个 watchlist 端点
  models.py                       # MODIFY - 新增 WatchlistRequest/Response 模型
  services/database.py            # MODIFY - 新增 user_watchlist 表
frontend/src/
  api/client.js                   # MODIFY - 新增 watchlist API 函数
  components/WatchlistManager.jsx # NEW - 自选管理组件
  views/StockSector.jsx           # MODIFY - 集成自选列表
  views/FundSector.jsx            # MODIFY - 集成自选列表
  views/MarketOverview.jsx        # MODIFY - 集成自选摘要
```

### Phase 10: 数据源可靠性提升 (已完成)

**目标**: 解决 AkShare 代理问题，建立多数据源降级链路

- [x] AkShare 代理穿透方案
  - 配置文件新增 `proxy` 字段 (http/https)
  - 环境变量 `HTTP_PROXY`/`HTTPS_PROXY` 自动读取
- [x] 多数据源降级链路
  - 第一优先: AkShare (直连或代理)
  - 第二优先: 东方财富 Web API 直接请求 (push2.eastmoney.com)
  - 最终兜底: Mock 数据 (标记 `is_mock=true`)
  - 每个数据源封装为独立 adapter，统一接口
- [x] 数据源适配器架构
  - `backend/app/services/data_sources/base.py` - 抽象基类 `DataSourceAdapter` + `DataSourceResult` + `AdapterStats`
  - `backend/app/services/data_sources/akshare_adapter.py` - AkShare 适配器 (priority=1)
  - `backend/app/services/data_sources/eastmoney_adapter.py` - 东方财富直连适配器 (priority=2)
  - `backend/app/services/data_sources/mock_adapter.py` - Mock 数据适配器 (priority=99)
  - `backend/app/services/data_sources/fallback_chain.py` - 降级链编排 + 统计
- [x] 数据源状态监控
  - 记录每个数据源的成功率、响应时间、最近错误
  - `GET /api/system/data-source-status` 端点
- [x] stock_service.py / fund_service.py 使用 FallbackChain 替代直接调用
- [x] models.py 新增 `data_source` 字段到 StockQuoteResponse/SectorQuoteResponse/FundNavResponse
- [x] 测试: 21 个新测试, 144 total pass

### Phase 10B: 移除冗余 Tab + 全局搜索 (已完成)

- [x] 移除 ResearchDashboard tab (文件保留，仅移除导航入口)
- [x] 全局搜索命令面板 (Ctrl+K / Cmd+K)
  - `GlobalSearch.jsx` - VS Code 风格命令面板
  - `useKeyboardShortcut.js` - 全局快捷键 hook
  - 自选列表优先显示，最近搜索次之
  - 6 位代码自动识别股票/基金类型
  - Enter 跳转到对应 Tab 并触发分析
- [x] App.jsx 集成 GlobalSearch + useKeyboardShortcut

### Phase 10C: 分析结果导出 + 对比 (已完成)

- [x] 分析结果导出
  - `ExportButton.jsx` - JSON/Markdown 下拉导出
  - 集成到 StockSector / FundSector / AnalysisHistory
- [x] 分析结果对比
  - `AnalysisComparison.jsx` - 2-3 个结果并排对比
  - 对比维度: 趋势/判断、情绪分数、置信度、关键因素、风险提示
  - 差异高亮显示
  - AnalysisHistory 新增多选 checkbox + "对比选中" 按钮
- [x] `GET /api/analysis/history/compare?ids=...` 端点 (client.js)
- [x] 前端: 75 modules build clean

### Phase 11: UX 体验优化 (已完成)

**已完成功能**:
- [x] 全局快捷分析入口 (Ctrl+K 命令面板)
- [x] 分析结果导出 (JSON/Markdown)
- [x] 分析结果对比 (2-3 个并排)
- [x] 移除冗余 ResearchDashboard tab
- [x] 响应式布局增强
  - 移动端 (< 768px): 单列布局，表格改为卡片列表，详情行展开
  - 平板端 (768-1024px): 双列布局
  - 触控优化: 按钮最小 44px 触控区域
- [x] Toast 通知系统 (useToast hook + ToastContainer)
  - 自选添加成功/失败/重复通知
  - 导出成功通知
  - AI 分析失败通知 (含 API key 缺失提示)
- [x] 数据源状态显示 (DataSourceStatus 组件)
- [x] 设置页面增强 (LLM 配置显示 + 测试连接 + 数据源状态)
- [x] 市场总览数据源指示器 (mock/real 数据标识)

**待开发功能**:
- [ ] 深色/浅色主题切换
  - CSS 变量方案 (已有 color-scheme: dark 基础)
  - 新增浅色主题变量
  - 主题切换器放置在 header
- [ ] 自选股异常波动提醒 (需要 WebSocket)

### Phase 12: 基金持仓管理增强 (已完成)

**目标**: 自选基金支持买入信息录入，持仓表格展示实时盈亏

- [x] 后端: user_watchlist 表新增 purchase_amount, purchase_nav, purchase_date, shares 字段
- [x] 后端: POST /api/watchlist 支持买入信息参数
- [x] 后端: PUT /api/watchlist/{id} 更新买入信息端点
- [x] 后端: GET /api/fund-holdings 返回持仓+实时净值+盈亏计算
- [x] 后端: cloud_llm.py 改用 Chat Completions API (MIMO 兼容)
- [x] 后端: 所有 LLM 端点增加 CloudLLMNoAPIKeyError 处理 (503 错误)
- [x] 前端: WatchlistManager 支持基金买入信息表单 (可折叠)
- [x] 前端: FundHoldingsTable 组件 (持仓表格+AI分析按钮)
- [x] 前端: FundSector 集成 FundHoldingsTable
- [x] 测试: 144 tests pass
- [x] 前端: 79 modules build clean

---

## 四、技术决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-05-25 | 保持 Paper-only 模式 | Phase 1 安全约束不变 |
| 2026-05-25 | 使用 MIMO-V2.5-PRO 作为主力 LLM | 用户提供的 API，OpenAI 兼容协议 |
| 2026-05-25 | 前端保持 Vite + React | 已有基础，不需要迁移 |
| 2026-05-25 | 后端保持 FastAPI + LangGraph | 已验证可用，扩展性好 |
| 2026-05-25 | A股数据源选择 AkShare | 免费、无需 API key、原生中国市场支持、覆盖沪深股票和板块指数 |
| 2026-05-25 | 技术指标使用 pandas_ta | 纯 Python、无二进制依赖、覆盖 MA/RSI/MACD/KDJ/Bollinger |
| 2026-05-25 | 新分析引擎不接入现有 LangGraph 图 | 保持现有 paper trading pipeline 不变，新功能作为独立 REST 端点 |
| 2026-05-25 | 新增 4 张缓存表 (stock_quotes, sector_quotes, fund_nav, analysis_logs) | 缓存实时数据避免频繁调 AkShare，TTL 控制新鲜度 |
| 2026-05-25 | i18n 方案选择 react-i18next | React 生态最成熟、支持命名空间/复数/插值、社区活跃 |
| 2026-05-25 | 自选列表持久化到 SQLite | 与现有架构一致，无需引入新的存储方案 |
| 2026-05-25 | 数据源采用 Adapter + FallbackChain 模式 | 统一接口、可插拔、降级链路清晰、便于扩展新数据源 |
| 2026-05-25 | 语言包采用扁平 JSON key 结构 | 简单直观、便于翻译工具处理、避免嵌套过深 |

---

## 五、Agent 分工

| Agent | 职责 | 当前任务 |
|-------|------|---------|
| architect | 架构设计、状态机、流程编排 | 已完成: `ARCHITECTURE_UPGRADE_V2.md` |
| pythonengineer | 后端 API、服务层、数据层 | 按架构文档实现 Phase 1-3 |
| frontexpert | 前端 UI、组件、状态管理 | 按架构文档实现 Phase 4 |

---

## 六、已知问题与风险

### 已确认问题 (需修复)

1. **AkShare 代理问题**: AkShare stock_zh_a_spot_em() 调用因网络代理问题失败，系统自动降级到 mock 数据。基金 NAV 获取正常。根因: AkShare 底层 requests 库未正确使用系统代理设置。
2. **~~UI 语言不一致~~**: ~~已通过 Phase 8 i18n 解决。~~ (已修复)
3. **~~自定义标的缺失~~**: ~~已通过 Phase 9 自选管理解决。~~ (已修复)
4. **~~旧 API 残留~~**: ~~已修正。~~ (已修复)
5. **~~ResearchDashboard 冗余~~**: ~~已移除导航入口。~~ (已修复)
6. **~~LLM API Key 缺失~~**: ~~已改善错误处理，返回 503 而非 500。~~ (已修复)
7. **~~基金研判 Failed to fetch~~**: ~~已修复，改为返回有意义的错误信息。~~ (已修复)

### 潜在风险

8. A股实时数据获取可能受限于 AkShare API 的稳定性和频率限制
9. LLM 分析结果的准确性和延迟需要平衡
10. 前端实时更新的性能考虑 (多 Tab 同时自动刷新)

---

## 七、变更日志

| 日期 | 变更内容 | 负责 |
|------|---------|------|
| 2026-05-25 | 初始化跟进文档，启动架构设计 | architect |
| 2026-05-25 | 完成 V2 架构设计文档 (`ARCHITECTURE_UPGRADE_V2.md`)，含数据层/服务层/API/前端完整设计 | architect |
| 2026-05-25 | Phase 1-3 后端实现完成: stock_service, fund_service, stock_analysis_service, fund_analysis_service, 6个新API端点, 86 tests pass | pythonengineer |
| 2026-05-25 | Phase 4 前端实现完成: StockSector, FundSector, MarketOverview 视图, 共享组件, 5个Tab, build通过 | frontexpert |
| 2026-05-25 | Phase 5: 网络异常降级处理, 自动刷新, 数据新鲜度指示, 骨架屏, 错误重试 | frontexpert |
| 2026-05-25 | Phase 6: 搜索自动补全, 分析历史查看, 技术指标图表(TechnicalChart/Sparkline), 90 tests, 48 modules | pythonengineer + frontexpert |
| 2026-05-25 | 架构评审: 识别 5 项关键问题, 制定 Phase 8-11 优化路线图 (i18n/自选管理/数据可靠性/UX优化) | architect |
| 2026-05-25 | Phase 8 完成: i18n 全界面中文化, LanguageSwitcher 组件, zh.json/en.json 语言包, 72 modules build clean | frontexpert |
| 2026-05-25 | Phase 9 完成: user_watchlist 表, CRUD API (5端点), watchlist_service, ocr_service, WatchlistManager 组件, 123 tests pass | pythonengineer + frontexpert |
| 2026-05-25 | 修复: analyzeFund() 旧端点修正, StockSector/FundSector 集成自选侧边栏 | frontexpert |
| 2026-05-25 | Phase 10 完成: 数据源适配器层 (AkShare/EastMoney/Mock), FallbackChain 降级链, 144 tests pass | pythonengineer |
| 2026-05-25 | Phase 10B 完成: 移除冗余 ResearchDashboard tab, GlobalSearch Ctrl+K 命令面板 | frontexpert |
| 2026-05-25 | Phase 10C 完成: ExportButton (JSON/Markdown), AnalysisComparison 并排对比, 75 modules build | frontexpert |
| 2026-05-25 | Phase 11 完成: Toast 通知系统, 响应式布局(移动端/平板), DataSourceStatus 组件, 设置页面增强, 79 modules build | frontexpert |
| 2026-05-25 | Phase 12 完成: 基金持仓管理增强, 买入信息录入, FundHoldingsTable 组件, LLM Chat Completions API 适配, 错误处理改善, 144 tests pass | pythonengineer + frontexpert |
| 2026-05-25 | 修复: cloud_llm.py 改用 Chat Completions API (MIMO 兼容), CloudLLMNoAPIKeyError 错误处理, 测试用例更新 | pythonengineer |

---

## 八、Phase 8-11 依赖关系与优先级

```
Phase 8 (i18n)          Phase 10 (数据可靠性)
    |                        |
    |  可并行开发              |  可并行开发
    v                        v
Phase 9 (自选管理)      Phase 11 (UX 优化)
    |                        |
    +--------+---------------+
             |
             v
        集成测试 & 发布
```

**建议执行顺序**:
1. **Phase 10** (数据可靠性) - 最高优先级，解决 AkShare 代理问题，确保数据可用
2. **Phase 8** (i18n) - 第二优先级，统一 UI 语言，提升用户体验
3. **Phase 9** (自选管理) - 第三优先级，依赖 Phase 10 数据源稳定
4. **Phase 11** (UX 优化) - 最后执行，依赖前三个 Phase 完成
