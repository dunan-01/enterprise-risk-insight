# 企业关联风险智能洞察系统

## 项目名称

企业关联风险智能洞察系统（Enterprise Risk Insight System）

## 系统目标

构建一个基于 LLM Agent 的企业关联风险智能分析系统，通过：
1. **事实数据查询**：从 risk.db 查询企业工商信息、经营事件、司法事件和关联关系
2. **风险调查与推理**：由 LLM Agent（risk-orchestrator）完成多跳关联风险调查
3. **覆盖审核**：由 coverage-auditor 检查调查是否遗漏关键证据
4. **风险核验**：由 risk-verifier 检查事实准确性、归因合理性和过度推断

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                     React 前端 (Vite)                       │
│  ┌──────────┬──────────┬──────────┬──────────┬────────────┐ │
│  │ 企业搜索 │ 企业概况 │ 工商动态 │ 司法风险 │ AI 风险洞察│ │
│  └──────────┴──────────┴──────────┴──────────┴────────────┘ │
└─────────────────────────────┬───────────────────────────────┘
                              │ HTTP API
┌─────────────────────────────▼───────────────────────────────┐
│                  FastAPI 后端 (uvicorn)                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ GET  /api/companies/search                           │   │
│  │ GET  /api/companies/{id}                             │   │
│  │ GET  /api/companies/{id}/business-events             │   │
│  │ GET  /api/companies/{id}/judicial-events             │   │
│  │ GET  /api/companies/{id}/relations                   │   │
│  │ POST /api/analysis                                   │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ deps.py → src/risk_tools.py（复用已有查询函数）       │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ harness_adapter.py → opencode run risk-orchestrator  │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────┬───────────────────────────────┘
                              │ opencode CLI
┌─────────────────────────────▼───────────────────────────────┐
│                    Risk Harness（LLM Agent）                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐ │
│  │ risk-orchestrator│→│coverage-auditor │→│risk-verifier │ │
│  │ (风险调查)       │  │ (覆盖审核)      │  │ (风险核验)  │ │
│  └─────────────────┘  └─────────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────┐
│                       risk.db (SQLite)                       │
│  ┌──────────┬──────────────┬──────────────┬──────────────┐  │
│  │companies │business_events│judicial_events│  relations   │  │
│  └──────────┴──────────────┴──────────────┴──────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Harness 架构

Risk Harness 由三个 LLM Agent 组成，通过 opencode headless 模式执行：

### 1. risk-orchestrator（风险调查员）
- 职责：使用 risk_* 工具调查目标企业及其关联企业
- 输出：调查底稿 + 风险初稿报告

### 2. coverage-auditor（覆盖审核员）
- 职责：对照数据清单审核调查覆盖度
- 判定：INCOMPLETE（需补充调查）/ COMPLETE（覆盖充分）

### 3. risk-verifier（风险核验员）
- 职责：核验风险证据链，复核报告结论
- 判定：PASS（通过）/ REVISE（需修订）/ UNRESOLVED（未解决）

## 项目目录结构

```
risk/
├── risk.db                          # SQLite 风险数据库
├── schema.sql                       # 数据库建表脚本
├── src/
│   └── risk_tools.py                # 数据查询函数（6个核心工具）
├── backend/
│   ├── .venv/                       # Python 虚拟环境
│   ├── requirements.txt             # 后端依赖
│   └── app/
│       ├── main.py                  # FastAPI 应用入口
│       ├── api.py                   # API 路由层
│       ├── models.py                # Pydantic 数据模型
│       ├── deps.py                  # 公共依赖与工具函数
│       ├── analysis_service.py      # 风险分析服务层
│       └── harness_adapter.py       # Risk Harness 调用层
├── frontend/
│   ├── package.json                 # 前端依赖
│   ├── vite.config.ts               # Vite 配置
│   ├── src/
│   │   ├── App.tsx                  # 路由配置
│   │   ├── main.tsx                 # 应用入口
│   │   ├── api/                     # API 客户端
│   │   ├── components/              # 通用组件
│   │   ├── pages/                   # 页面组件
│   │   └── styles/                  # 样式文件
│   └── dist/                        # 构建产物
├── tests/
│   ├── gold_cases.json              # 测试用例集
│   └── evaluate_report.py           # 报告评估脚本
├── runs/
│   ├── C001-C005/                   # 正式实验结果（Harness 输出）
│   └── web/                         # Web 系统运行结果
│       ├── C001/
│       ├── C003/
│       ├── C004/
│       └── C005/
├── .opencode/
│   └── agents/                      # Agent 定义文件
│       ├── risk-orchestrator.md
│       ├── coverage-auditor.md
│       └── risk-verifier.md
└── scripts/                         # 启动脚本
    ├── start_backend.sh
    ├── start_frontend.sh
    └── start_all.sh
```

## 后端启动方式

```bash
# 方式一：使用启动脚本
bash scripts/start_backend.sh

# 方式二：手动启动
cd backend
source .venv/bin/activate
python -m app.main

# 方式三：使用 uvicorn
cd backend
source .venv/bin/activate
uvicorn app.main:app --port 8000
```

## 前端启动方式

```bash
# 方式一：使用启动脚本
bash scripts/start_frontend.sh

# 方式二：手动启动
cd frontend
npm run dev
```

## 同时启动

```bash
bash scripts/start_all.sh
```

## 访问地址

| 服务 | 地址 |
|------|------|
| 前端界面 | http://localhost:5173 |
| 后端 API | http://localhost:8000 |
| API 文档 | http://localhost:8000/docs |
| 健康检查 | http://localhost:8000/health |

## 示例企业 C001-C010

| 企业 ID | 企业名称 | 行业 | 风险等级 |
|---------|----------|------|----------|
| C001 | 华辰智能科技有限公司 | 软件和信息技术服务业 | 中等风险 |
| C002 | 远海供应链管理有限公司 | 供应链管理 | 高风险 |
| C003 | 恒达商贸有限公司 | 批发业 | 中等风险 |
| C004 | 新源新能源材料有限公司 | 新材料制造业 | 低风险 |
| C005 | 博远数字科技有限公司 | 软件和信息技术服务业 | 高风险 |
| C006 | 嘉盛产业投资有限公司 | 投资管理 | - |
| C007 | 鼎峰建设工程有限公司 | 建筑业 | - |
| C008 | 瑞泽机械制造有限公司 | 机械制造 | - |
| C009 | 云启信息服务有限公司 | 信息技术服务业 | - |
| C010 | 宏泰物流有限公司 | 物流业 | - |

## AI 风险分析流程

1. **用户触发**：在前端点击"启动 AI 风险分析"
2. **API 调用**：前端调用 `POST /api/analysis`
3. **存在性检查**：后端验证企业是否存在
4. **Harness 调用**：通过 opencode CLI 启动 risk-orchestrator
5. **风险调查**：risk-orchestrator 使用 risk_* 工具调查企业
6. **覆盖审核**：coverage-auditor 检查调查完整性
7. **风险核验**：risk-verifier 核验风险结论
8. **结果返回**：结构化结果返回前端展示

**重要说明**：
- 事实数据查询由 risk_tools.py 完成
- 风险调查、关联推理与风险判断由 LLM Agent 完成
- Coverage Auditor 检查调查是否遗漏
- Risk Verifier 检查事实、归因、关系推理与过度推断
- Web 层不得自行计算风险等级

## Coverage Auditor 的作用

Coverage Auditor 负责审核 risk-orchestrator 的调查覆盖度：
- 对照数据清单检查是否遗漏关键证据
- 判定调查是否充分（INCOMPLETE / COMPLETE）
- 如不完整，要求补充调查后再次审核

## Risk Verifier 的作用

Risk Verifier 负责核验风险报告的准确性：
- 检查事实准确性（证据编号与数据库一致）
- 检查归因合理性（风险判断有证据支撑）
- 检查关系推理（关联风险传导逻辑正确）
- 检查过度推断（避免放大风险）
- 判定：PASS（通过）/ REVISE（需修订）/ UNRESOLVED（未解决）

## runs/ 与 runs/web/ 的区别

| 目录 | 用途 | 内容 |
|------|------|------|
| `runs/C001-C005/` | 正式实验结果 | Harness 完整输出（草稿、审核、核验、最终报告） |
| `runs/web/` | Web 系统运行结果 | API 调用结果（analysis_result.json、report_final.md） |

**区别**：
- `runs/C001-C005/` 是通过 opencode CLI 直接运行 Harness 产生的完整实验数据
- `runs/web/` 是通过 Web 系统调用 `POST /api/analysis` 产生的运行记录
- 两者使用相同的 Harness 逻辑，但触发方式和输出格式不同

## 当前 V1 已知限制

1. **分析耗时**：单次 AI 风险分析需 3-20 分钟（同步阻塞）
2. **并发限制**：同一时间只允许一个分析任务（避免 opencode 并发冲突）
3. **无实时进度**：分析期间无法获取实时进度百分比
4. **无历史记录**：Web 系统不保存用户分析历史
5. **无用户系统**：无登录、权限、多用户支持
6. **数据为模拟数据**：当前使用 simulated 数据，非真实企业数据
7. **无流式输出**：分析结果一次性返回，不支持流式展示
8. **无导出功能**：不支持 PDF/Word 导出

## 技术栈

- **后端**：Python 3.9 + FastAPI + SQLite
- **前端**：React 19 + TypeScript + Vite + ECharts
- **AI Agent**：OpenCode + Risk Harness (risk-orchestrator / coverage-auditor / risk-verifier)
- **数据查询**：src/risk_tools.py（6个核心查询函数）
