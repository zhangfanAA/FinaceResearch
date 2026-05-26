# micro-quant-pipeline 当前完成情况

更新日期：2026-05-06

## 1. 项目目标

当前项目已经实现为一个**本地 Paper / Dry-run only** 的微型量化代理原型，核心目标是：

- 不接真实券商 / 交易所 / 基金销售 API
- 使用 LangGraph 编排推理与执行流程
- 使用 SQLite 维护持仓批次与执行日志
- 使用 Python 风控规则兜底，LLM 只产生信号，不能直接执行交易
- 提供前后端本地可视化界面，便于观察运行状态与调整本地 LLM 连接参数

---

## 2. 已完成模块

### 2.1 后端基础框架

已完成：

- FastAPI 后端
- LangGraph 状态图编排
- 本地 YAML 配置加载
- 统一 Pydantic 配置与模型校验
- `/health`、`/api/status`、`/api/trigger` 等基础接口

主要位置：

- `micro-quant-pipeline/backend/app/main.py`
- `micro-quant-pipeline/backend/app/graph.py`
- `micro-quant-pipeline/backend/app/nodes.py`
- `micro-quant-pipeline/backend/app/config.py`
- `micro-quant-pipeline/backend/app/models.py`

---

### 2.2 Paper-only 交易约束

已完成并保持为强约束：

- 只允许 `paper` 模式启动
- 不存在真实下单执行路径
- `position_policy_guard` 必须在 `paper_executor` 之前
- LLM 输出只进入信号校验，不可直接执行
- 低置信度信号自动回退为 `Hold`
- 非法 / 非 JSON 的 Hermes 输出最多重试 2 次，随后回退 `Hold`

当前这是系统最核心的安全边界。

---

### 2.3 SQLite 持仓账本与执行日志

已完成：

- `lots` 批次持仓表
- `paper_execution_logs` 执行日志表
- `app_settings` 本地 LLM 设置表
- 旧 `positions` 数据向 `lots` 的兼容迁移

已支持：

- 批次插入
- OPEN/CLOSED lot 状态维护
- Paper 执行日志落库
- 本地 LLM 设置持久化

主要位置：

- `micro-quant-pipeline/backend/app/services/database.py`
- `micro-quant-pipeline/backend/app/services/positions.py`

---

### 2.4 FIFO 卖出与 C 类 7 天限制

已完成：

- FIFO 批次卖出检查
- FIFO 实际扣减
- C 类基金 `< 7 天` 卖出拦截
- override 仅允许来自 Python 规则链，不允许 LLM 注入绕过
- 部分 / 全部可卖份额判断

当前已经验证：

- FIFO 最老批次优先扣减
- C 类未满 7 天不会被正常卖出
- 风控链路没有被前端设置或 LLM 设置破坏

---

### 2.5 市场路由与图节点

已完成：

- 初始化上下文
- 获取市场快照
- VIX 路由分支：`emergency / sleep / deep`
- `retrieve_context`
- `reason_with_hermes`
- `validate_llm_json`
- `position_policy_guard`
- `paper_executor`
- `finalize`

当前路由逻辑：

- `vix >= 35` → `emergency`
- `vix < 12` → `sleep`
- 其他 → `deep`
- `vix is None` → `sleep`

主要位置：

- `micro-quant-pipeline/backend/app/nodes.py`
- `micro-quant-pipeline/backend/app/graph.py`

---

### 2.6 Hermes / Ollama 推理接入

已完成：

- 使用 Ollama `/api/generate`
- 本地 Hermes JSON 输出解析
- 只接受研究型字段：
  - `target_asset`
  - `sentiment_score`
  - `confidence`
  - `reasoning`
- 拒绝可执行字段注入，例如：
  - `action`
  - `shares`
  - `cost_price`
  - `extreme_stop_loss`
  - `crash_override`
- 运行时支持 `api_key`、`base_url`、`model`、`timeout_seconds`

主要位置：

- `micro-quant-pipeline/backend/app/services/ollama.py`
- `micro-quant-pipeline/backend/app/services/llm_settings.py`

---

### 2.7 本地 LLM 设置 API

已完成接口：

- `GET /api/settings/llm`
- `PUT /api/settings/llm`
- `POST /api/settings/llm/test`

已支持设置项：

- `base_url`
- `generate_path`
- `model`
- `timeout_seconds`
- `api_key`
- `persist_api_key`

行为约束：

- `api_key` 为 write-only
- `GET` 只返回 `has_api_key`
- 非 secret 设置持久化到 SQLite
- `persist_api_key=false` 时可作为本进程运行时覆盖
- `/api/settings/llm/test` 只测试 LLM 连通性，不触发 LangGraph、不触发执行器

---

### 2.8 RAG / ChromaDB

已完成基础版：

- ChromaDB 本地检索接入
- `retrieve_context` 节点可调用检索器
- 检索失败时不会中断主图，会回退到默认提示片段
- 使用确定性 embedding fallback

主要位置：

- `micro-quant-pipeline/backend/app/services/retriever.py`

说明：

- 当前属于可运行的最小版本地 RAG
- 状态接口里 `chromadb` 仍显示为 `unknown`，这属于状态展示未完全同步，不代表相关代码不存在

---

### 2.9 前端客户端

已完成主工作区前端接入：

- Vite + React 单页客户端
- 页面 / 区块：
  - Status
  - Settings
  - Trigger Run
  - Lots
  - Logs
- 明确的 `PAPER / DRY-RUN ONLY` 提示
- 本地 CSS 样式
- Settings 支持编辑 LLM 连接设置
- `api_key` 输入框遮罩，保存后不回显真实 key

主要位置：

- `micro-quant-pipeline/frontend/package.json`
- `micro-quant-pipeline/frontend/src/App.jsx`
- `micro-quant-pipeline/frontend/src/api/client.js`
- `micro-quant-pipeline/frontend/src/styles.css`

---

## 3. 已完成接口清单

### 后端基础接口

- `GET /health`
- `GET /api/status`
- `POST /api/trigger`
- `GET /api/lots`
- `GET /api/logs`

### LLM 设置接口

- `GET /api/settings/llm`
- `PUT /api/settings/llm`
- `POST /api/settings/llm/test`

---

## 4. 已完成测试与验证

### 后端

已通过：

- `ruff check app tests`
- `pytest`

当前最近一次验证结果：

- `45 passed, 1 warning`

覆盖方向包括：

- 配置校验
- Graph 路由
- Hermes JSON 校验与 fallback
- Ollama 请求与 header 注入
- FIFO / C 类风控
- Paper 执行
- 主 API

### 前端

已通过：

- `npm run lint`
- `npm run build`

---

## 5. 当前可运行方式

### 启动后端

```bash
cd E:/Develop/SubAgengtsDevelop/FInance_Agent/micro-quant-pipeline/backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 启动前端

```bash
cd E:/Develop/SubAgengtsDevelop/FInance_Agent/micro-quant-pipeline/frontend
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev -- --host 127.0.0.1 --port 5173
```

### 本次会话中已启动的演示地址

- 后端：`http://127.0.0.1:8001`
- 前端：`http://127.0.0.1:5174`

---

## 6. 当前已知状态 / 待完善项

### 已知状态

- 系统核心链路已经能本地运行
- 前后端都已接入主工作区
- Settings 页面与后端 Settings API 已打通

### 待完善项

- `/api/status` 中 `chromadb` / `ollama` 的状态展示仍较粗糙，尚未反映更细粒度真实状态
- ChromaDB 目前是最小可用版本，后续可增强 embedding 与 metadata filter
- 前端目前是单页 dashboard，适合作为 MVP，后续可再拆分路由或页面结构
- 还没有调度器、历史分页、长期运行任务管理等增强模块

---

## 7. 当前结论

截至目前，项目已经完成一个可运行的本地 MVP：

- 有后端
- 有前端
- 有 LangGraph
- 有 SQLite lot ledger
- 有 FIFO 卖出逻辑
- 有 C 类 7 天保护
- 有 Paper-only 执行器
- 有 Ollama / Hermes 接入
- 有本地 LLM Settings 可配置能力
- 有测试保障

也就是说，**核心 MVP 已经搭起来并可本地演示**。
