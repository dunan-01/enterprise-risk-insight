# 企业关联风险智能洞察系统 —— 后端 API（第一、二阶段）

只读查询 API 层，封装现有 `src/risk_tools.py` 的 6 个查询函数，不包含任何业务逻辑，
不在 API 层直接写 SQL，不修改 `src/risk_tools.py` 与 `risk.db`。

第二阶段新增 POST `/api/analysis` 风险分析接口：通过 Risk Harness Adapter
（`app/harness_adapter.py`）以 headless 方式真实调用 OpenCode Agent
（risk-orchestrator + coverage-auditor + risk-verifier）完成企业风险调查，
API 层不复制 Harness 逻辑、不硬编码风险判断。

## 目录结构

```
backend/
├── requirements.txt        # fastapi, uvicorn（独立 venv 安装）
├── README.md
├── app/
│   ├── __init__.py
│   ├── main.py             # FastAPI 实例、CORS、异常兜底、启动入口
│   ├── api.py              # 路由（6 个查询接口 + POST /api/analysis）
│   ├── models.py           # Pydantic 请求/响应/错误模型
│   ├── deps.py             # sys.path 设置、risk_tools re-export、工具函数
│   ├── harness_adapter.py  # Risk Harness 调用层（opencode headless + JSONL 解析）
│   └── analysis_service.py # 风险分析服务层（存在性检查、结构化解析、记录保存）
```

## 启动方式

### 1. 创建虚拟环境并安装依赖（首次）

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

### 2. 启动服务

方式一（推荐）：

```bash
cd backend
.venv/bin/python -m app.main
```

方式二（uvicorn CLI）：

```bash
cd backend
.venv/bin/uvicorn app.main:app --port 8000
```

- 默认端口：`8000`
- 端口覆盖：环境变量 `PORT`（如 `PORT=8001 .venv/bin/python -m app.main`）
- 健康检查：`GET /health` 返回 `{"status": "ok"}`
- 交互式文档：启动后访问 `http://127.0.0.1:8000/docs`

## 接口清单

统一约定：
- 除 `/health` 外全部接口前缀 `/api`
- 企业不存在：`404` + `{"detail": {"code": "COMPANY_NOT_FOUND", "message": "未找到企业 <id>"}}`
- 内部错误（数据库缺失等）：`500` + `{"detail": {"code": "INTERNAL_ERROR", "message": ...}}`
- 请求体/参数校验失败：`400` + `{"detail": {"code": "INVALID_REQUEST", "message": ...}}`
- `company_id` 自动做 `strip + upper()` 规范化
- CORS 允许所有来源（`*`）

| # | 端点 | 方法 | 请求参数 | 响应字段 | 错误码 |
|---|------|------|----------|----------|--------|
| 1 | `/api/companies/search` | GET | `keyword`（必填，企业ID/名称/信用代码） | `keyword: str`、`total: int`、`items: [{company_id, company_name, credit_code, legal_rep, industry, business_status, data_type}]` | 400 `INVALID_KEYWORD`（keyword 缺失或为空）、500 |
| 2 | `/api/companies/{company_id}` | GET | 路径参数 `company_id` | `company_id: str`、`profile: {...完整工商信息，companies 表全部字段}` | 404 `COMPANY_NOT_FOUND`、500 |
| 3 | `/api/companies/{company_id}/business-events` | GET | 路径参数 `company_id` | `company_id: str`、`total: int`、`items: [{business_events 表全部字段}]` | 404、500 |
| 4 | `/api/companies/{company_id}/judicial-events` | GET | 路径参数 `company_id` | `company_id: str`、`total: int`、`items: [{judicial_events 表全部字段}]` | 404、500 |
| 5 | `/api/companies/{company_id}/relations` | GET | 路径参数 `company_id` | `company_id: str`、`total: int`、`items: [{relations 表全部字段 + from_company_name + to_company_name}]` | 404、500 |
| 6 | `/api/analysis` | POST | 请求体 `{"company_id": "C004"}`（必填非空） | `company_id`、`status`（恒为 `"completed"`）、`report`、`verification_status`（PASS/UNRESOLVED）、`risk_level`、`summary`、`evidence_ids`、`related_companies`、`report_path`、`duration_seconds` | 400 `INVALID_REQUEST`、404 `COMPANY_NOT_FOUND`、503 `ANALYSIS_FAILED` |
| 7 | `/health` | GET | 无 | `status: str`（恒为 `"ok"`） | — |

错误响应统一结构：`{"detail": {"code": str, "message": str}}`

## POST /api/analysis 说明

- 请求体：`{"company_id": "C004"}`；`company_id` 必填且不能为空白
- 处理流程：`api.py` → `analysis_service.analyze_company`（存在性检查 →
  `harness_adapter.run_harness_analysis`）→ `opencode run --agent risk-orchestrator
  --format json --dir <项目根> "<prompt>"` → 解析 JSONL 事件流 → 提取
  VERIFICATION_STATUS（正则取最后一个匹配，未提取到自动重试 1 次，最多 2 次）
- 同步阻塞：实测耗时 3-20 分钟；**复杂案例（多轮 risk-verifier 复核，如 C005）
  可能耗时 10-20 分钟，建议客户端/HTTP 超时设置 ≥ 20 分钟（1200s）**；
  Harness 调用通过模块级 `threading.Lock` 串行化
- 单次 Harness 调用超时默认 **1200 秒（20 分钟）**，可用环境变量覆盖：
  `HARNESS_TIMEOUT=<秒>`（如 `HARNESS_TIMEOUT=1500 .venv/bin/python -m app.main`），
  非法值回退默认 1200
- 超时与"未提取到 VERIFICATION_STATUS"均自动重试 1 次（共最多 2 次尝试，
  重试前 sleep 2s）；重试仍失败才返回 503
- 每次分析结果保存至 `runs/web/<company_id>/`：
  `analysis_result.json`、`session_events.jsonl`、`process.md`、`report_final.md`
- 成功：`200`，`status` 恒为 `"completed"`（Harness 已结束）
- 企业不存在：`404 COMPANY_NOT_FOUND`
- Harness 失败（opencode 缺失 / 超时 / 重试后仍无 VERIFICATION_STATUS）：
  `503 ANALYSIS_FAILED`（超时未单独使用 504，统一归入 503，便于前端处理）

## 实现说明

- 所有数据查询复用 `src/risk_tools.py`：
  `search_company` / `get_company_profile` / `get_business_events` / `get_judicial_events` /
  `get_company_relations` / `get_company_snapshot`（`deps.py` 集中 re-export，API 层唯一数据入口）
- 企业存在性检查复用 `get_company_profile`（返回 `None` 即不存在），不在 API 层写 SQL
- 查询异常统一转 `500 INTERNAL_ERROR`，另注册全局异常兜底，不抛裸异常
- 风险分析接口不复制 Harness 逻辑：风险判断完全由 OpenCode Agent（risk-orchestrator +
  coverage-auditor + risk-verifier）完成；`risk_level` / `summary` / `evidence_ids` /
  `related_companies` 为 best-effort 正则解析，失败时为 None/空，不影响报告本身
- 环境：Python 3.9.13（独立 venv，未污染系统环境）；新增代码仅用标准库
  （subprocess / json / re / threading）