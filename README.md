# Micro Quant Pipeline

A股基金研判与量化分析系统 — 基于 FastAPI + LangGraph + React 的全栈量化研究平台。

## 功能特性

### 基金研判
- AI 驱动的持仓基金分析，支持自定义提示词
- 基金净值查询与历史走势可视化
- 基金持仓详情表格（总投入、总盈亏汇总）
- 分析历史记录与导出

### 股票板块
- 实时行情查询（AkShare / EastMoney 多数据源）
- 技术分析图表（MA、MACD、KDJ 等）
- 自选股管理与 Watchlist
- 模拟交易执行器

### 市场总览
- 大盘指数实时展示（上证、深证、沪深300、中证500）
- 板块涨跌排行
- 市场情绪指标与恐慌指数
- 数据源健康状态监控

### 系统架构
- FastAPI 后端 + LangGraph 状态机工作流
- React 18 + Vite 前端，i18n 中英文支持
- 深色 / 浅色主题切换
- 三层数据源 FallbackChain：AkShare → EastMoney → Mock
- 网络代理防御与指数退避重试机制

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + LangGraph |
| 数据源 | AkShare, EastMoney API |
| LLM 集成 | Ollama / 云端 LLM (MIMO) |
| 前端框架 | React 18 + Vite |
| 样式 | CSS + Tailwind CSS |
| 国际化 | react-i18next |
| 数据库 | SQLite |
| 测试 | pytest (90+ 用例) |

## 快速开始

### 环境要求
- Python 3.11+
- Node.js 18+
- npm 或 yarn

### 后端启动

```bash
cd backend

# 安装依赖
pip install -e .

# 启动服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 前端启动

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

前端默认运行在 `http://localhost:5173`，后端 API 在 `http://localhost:8000`。

### 配置

编辑 `backend/config.yaml` 配置 LLM 和数据源参数：

```yaml
llm:
  base_url: "http://localhost:11434"
  model: "qwen2.5:7b"
  api_key: ""

data_sources:
  primary: "akshare"
  fallback: ["eastmoney", "mock"]
```

## 项目结构

```
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口 + 代理防御
│   │   ├── graph.py             # LangGraph 状态机
│   │   ├── nodes.py             # 工作流节点
│   │   ├── models.py            # Pydantic 数据模型
│   │   ├── config.py            # 配置加载
│   │   ├── core/
│   │   │   └── prompts.py       # AI 分析提示词模板
│   │   └── services/
│   │       ├── data_sources/    # 数据源适配器
│   │       │   ├── base.py      # 抽象基类
│   │       │   ├── akshare_adapter.py
│   │       │   ├── eastmoney_adapter.py
│   │       │   ├── mock_adapter.py
│   │       │   ├── fallback_chain.py
│   │       │   └── retry.py     # tenacity 重试工具
│   │       ├── stock_service.py
│   │       ├── fund_service.py
│   │       ├── market_data.py
│   │       └── ...
│   ├── tests/                   # 90+ pytest 用例
│   └── pyproject.toml
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # 主应用 + Tab 路由
│   │   ├── views/
│   │   │   ├── FundSector.jsx   # 基金研判
│   │   │   ├── StockSector.jsx  # 股票板块
│   │   │   └── MarketOverview.jsx # 市场总览
│   │   ├── components/          # 可复用组件
│   │   ├── hooks/               # 自定义 Hooks
│   │   ├── api/client.js        # API 客户端
│   │   ├── i18n/                # 国际化
│   │   └── styles.css           # 全局样式
│   └── package.json
│
└── README.md
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/status` | 系统状态 |
| GET | `/api/stock/quote?code=000001` | 股票实时行情 |
| GET | `/api/fund/nav?code=110011` | 基金净值查询 |
| POST | `/api/fund/analyze` | 基金 AI 分析 |
| POST | `/api/stock/analyze` | 股票 AI 分析 |
| GET | `/api/market/overview` | 市场总览数据 |
| GET | `/api/settings/llm` | LLM 配置 |
| PUT | `/api/settings/llm` | 更新 LLM 配置 |

## 测试

```bash
cd backend
pytest tests/ -v
```

## License

MIT
