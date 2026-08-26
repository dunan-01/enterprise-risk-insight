# 企业关联风险智能洞察系统 V1.2 —— AI 分析异步化报告

## 一、架构变化

### V1.1（同步阻塞）

```
用户点击 AI 风险分析
↓
POST /api/analysis
↓
等待 Risk Harness 数分钟
↓
返回最终结果
```

**问题**：HTTP 请求阻塞 3-20 分钟，前端页面卡死，用户无法操作。

### V1.2（异步任务）

```
用户点击 AI 风险分析
↓
POST /api/analysis/tasks
↓
立即创建任务（< 1 秒）
↓
返回 task_id
↓
后台线程运行 Risk Harness
↓
前端每 3 秒轮询任务状态
↓
completed → 自动加载最终报告
```

**核心变化**：
- HTTP 请求不再阻塞（< 1 秒返回）
- Risk Harness 在后台线程中执行
- 前端通过轮询获取任务状态
- 任务状态持久化到磁盘，支持页面刷新恢复

### 数据流

```
Frontend
  ↓ POST /api/analysis/tasks
Analysis Task API (api.py)
  ↓ TaskManager.create_task()
Background Task Manager (task_manager.py)
  ↓ threading.Thread(daemon=True)
Harness Adapter (harness_adapter.py)
  ↓ subprocess: opencode run --agent risk-orchestrator
OpenCode Headless
  ↓
Risk Harness (risk-orchestrator → coverage-auditor → risk-verifier)
```

## 二、新增 API

### POST /api/analysis/tasks

创建异步分析任务，立即返回 task_id。

**Request：**
```json
{
  "company_id": "C007"
}
```

**Response（200）：**
```json
{
  "task_id": "task-a1b2c3d4-1724576800",
  "company_id": "C007",
  "status": "queued",
  "created_at": "2026-08-25T10:00:00+00:00",
  "started_at": null,
  "finished_at": null,
  "error": null,
  "result": null
}
```

**错误响应：**
- 404 `COMPANY_NOT_FOUND` — 企业不存在
- 400 `INVALID_REQUEST` — 请求体非法

### GET /api/analysis/tasks/{task_id}

查询任务状态。

**Response（200）：**
```json
{
  "task_id": "task-a1b2c3d4-1724576800",
  "company_id": "C007",
  "status": "running",
  "created_at": "2026-08-25T10:00:00+00:00",
  "started_at": "2026-08-25T10:00:05+00:00",
  "finished_at": null,
  "error": null,
  "result": null
}
```

**completed 状态时：**
```json
{
  "task_id": "task-a1b2c3d4-1724576800",
  "company_id": "C007",
  "status": "completed",
  "created_at": "2026-08-25T10:00:00+00:00",
  "started_at": "2026-08-25T10:00:05+00:00",
  "finished_at": "2026-08-25T10:15:30+00:00",
  "error": null,
  "result": {
    "company_id": "C007",
    "status": "completed",
    "report": "...",
    "verification_status": "PASS",
    "risk_level": "高风险",
    "summary": "...",
    "evidence_ids": ["B001", "J003"],
    "related_companies": ["C002", "C005"],
    "report_path": "runs/web/C007/report_final.md",
    "duration_seconds": 925.5
  }
}
```

**failed 状态时：**
```json
{
  "task_id": "task-a1b2c3d4-1724576800",
  "company_id": "C007",
  "status": "failed",
  "created_at": "2026-08-25T10:00:00+00:00",
  "started_at": "2026-08-25T10:00:05+00:00",
  "finished_at": "2026-08-25T10:05:30+00:00",
  "error": "Harness 分析超时（1200s，尝试 2 次）：C007",
  "result": null
}
```

**错误响应：**
- 404 `TASK_NOT_FOUND` — 任务不存在

### GET /api/analysis/tasks/company/{company_id}/active

查询企业当前活跃任务（queued/running）。

**Response（200）：** 同 TaskResponse 结构

**错误响应：**
- 404 `TASK_NOT_FOUND` — 企业无活跃任务
- 404 `COMPANY_NOT_FOUND` — 企业不存在

## 三、Task 状态设计

### 状态枚举

| 状态 | 说明 | result 字段 | error 字段 |
|------|------|-------------|------------|
| `queued` | 排队中，等待获取 Harness 锁 | null | null |
| `running` | 正在执行 Harness 分析 | null | null |
| `completed` | 分析完成 | AnalysisResponse | null |
| `failed` | 分析失败 | null | 错误描述 |

### 状态流转

```
queued → running → completed
                  → failed
```

### task_id 格式

`task-{uuid4前8位}-{Unix时间戳}`

示例：`task-a1b2c3d4-1724576800`

### 不伪造进度

系统**不显示**虚假的百分比进度（如"65%"）或"预计剩余3分钟"。

只展示真实状态：
- 当前状态（queued/running/completed/failed）
- 已运行时间（elapsed time）

## 四、后台执行机制

### 实现方式

使用 `threading.Thread(daemon=True)` 在后台执行 Harness 分析。

```python
thread = threading.Thread(
    target=self._run_task_background,
    args=(task_id,),
    daemon=True,
    name=f"harness-task-{task_id}",
)
thread.start()
```

### 执行流程

1. 获取 `_HARNESS_LOCK`（串行化锁）
2. 更新任务状态为 `running`，持久化
3. 调用 `analyze_company(company_id)`（复用现有分析服务）
4. 成功：更新为 `completed`，保存 result
5. 失败：更新为 `failed`，保存 error
6. 释放锁

### 关键约束

- **不重新实现分析逻辑**：复用 `analysis_service.analyze_company()`
- **不修改 Harness**：`harness_adapter.py`、`risk-orchestrator`、`coverage-auditor`、`risk-verifier` 均未修改
- **不修改数据层**：`risk.db`、`src/risk_tools.py` 均未修改

## 五、并发处理

### 单执行锁

系统保持原有的串行化设计：**同一时间只允许一个 Harness 分析**。

```python
# harness_adapter.py
_HARNESS_LOCK = threading.Lock()

# task_manager.py
with _HARNESS_LOCK:
    # 执行分析
```

当任务 A 正在 `running` 时，任务 B 会停留在 `queued` 状态，等待 A 完成后再执行。

### 去重机制

如果同一企业已有 `queued` 或 `running` 的任务，再次创建时：

1. 不创建新任务
2. 返回现有任务的 `task_id`
3. 提示"该企业已有分析任务正在执行"

```python
existing = self.get_active_task_for_company(cid)
if existing is not None:
    return existing  # 返回现有任务
```

### 前端不阻塞

虽然后端同一时间只执行一个 Harness，但前端 HTTP 请求不会被阻塞：

- `POST /api/analysis/tasks` 立即返回（< 1 秒）
- 后台线程负责执行 Harness
- 前端通过轮询获取状态

## 六、任务持久化

### 存储位置

任务元信息保存到 `runs/web/tasks/{task_id}.json`。

### 存储格式

```json
{
  "task_id": "task-a1b2c3d4-1724576800",
  "company_id": "C007",
  "status": "completed",
  "created_at": "2026-08-25T10:00:00+00:00",
  "started_at": "2026-08-25T10:00:05+00:00",
  "finished_at": "2026-08-25T10:15:30+00:00",
  "error": null,
  "result": { ... }
}
```

### 页面刷新恢复

服务启动时调用 `startup_recovery()`：

1. 扫描 `runs/web/tasks/` 目录
2. 将 `queued` / `running` 的任务标记为 `failed`（进程重启无法恢复后台线程）
3. `completed` / `failed` 的任务保持不变

**已知限制**：服务重启后，正在执行的任务会被标记为 `failed`，无法恢复执行。这是因为后台线程随进程结束而终止，无法持久化线程状态。

## 七、前端行为

### 状态机

```
loading-history → (done | not-analyzed | task-running) → (done | error)
```

### 任务状态页面

点击"启动 AI 风险分析"后：

1. 调用 `POST /api/analysis/tasks` 创建任务
2. 立即进入 `task-running` 状态
3. 显示：
   - spinner 动画
   - "AI 正在进行企业风险调查与关联分析..."
   - 企业名称和 ID
   - 已等待时间（真实 elapsed time）
   - 静态流程示意（企业调查 → 覆盖审核 → 风险核验）
   - 提示"后台任务运行中，可自由切换 Tab"

### 轮询机制

- 每 3 秒调用 `GET /api/analysis/tasks/{task_id}`
- `completed` → 自动加载最终报告
- `failed` → 显示错误信息和重试按钮
- `queued` / `running` → 继续轮询

### 页面切换

用户启动 C007 分析后：

1. 可以切换到其他 Tab（企业概况、工商动态等）
2. 可以进入其他企业页面
3. 当重新回到 C007 的 AI 风险洞察 Tab：
   - 如果有活跃任务 → 显示"分析进行中"
   - 如果任务已完成 → 显示最新报告

### 刷新恢复

页面刷新时：

1. 检查 `GET /api/analysis/tasks/company/{company_id}/active`
2. 如果有活跃任务 → 恢复轮询
3. 如果没有 → 检查历史结果

### 重复提交

同一企业有活跃任务时：

1. 不创建重复任务
2. 返回现有 `task_id`
3. 前端继续轮询现有任务

## 八、文件变更清单

### 新建文件

| 文件 | 说明 |
|------|------|
| `backend/app/task_manager.py` | 异步任务管理器（TaskManager 单例 + TaskInfo + TaskStatus） |

### 修改文件

| 文件 | 变更 |
|------|------|
| `backend/app/models.py` | 新增 `CreateTaskRequest`、`TaskResponse` 模型 |
| `backend/app/api.py` | 新增 3 个端点：创建任务、查询任务、查询活跃任务 |
| `backend/app/deps.py` | 新增 `ERROR_TASK_NOT_FOUND`、`ERROR_TASK_CONFLICT` 错误码 |
| `backend/app/main.py` | 新增 startup 事件调用 `startup_recovery()` |
| `frontend/src/api/types.ts` | 新增 `TaskResponse` 接口 |
| `frontend/src/api/client.ts` | 新增 3 个 API 方法 |
| `frontend/src/pages/CompanyPage.tsx` | 修改状态机、新增轮询逻辑 |
| `frontend/src/pages/tabs/AnalysisTab.tsx` | 新增 `task-running` 状态展示 |

### 未修改文件（验证通过）

| 文件 | 状态 |
|------|------|
| `src/risk_tools.py` | ✅ 未修改 |
| `risk.db` | ✅ 未修改 |
| `.opencode/agents/risk-orchestrator.md` | ✅ 未修改 |
| `.opencode/agents/coverage-auditor.md` | ✅ 未修改 |
| `.opencode/agents/risk-verifier.md` | ✅ 未修改 |
| `backend/app/harness_adapter.py` | ✅ 未修改（`run_harness_analysis` 签名不变） |
| `backend/app/analysis_service.py` | ✅ 未修改（`analyze_company` 签名不变） |

## 九、测试结果

### 后端验证

| 测试项 | 结果 |
|--------|------|
| 后端启动 | ✅ 正常启动 |
| 健康检查 | ✅ `{"status":"ok"}` |
| POST /api/analysis/tasks 创建任务 | ✅ 立即返回 task_id（< 1 秒） |
| GET /api/analysis/tasks/{task_id} 查询状态 | ✅ 返回完整 TaskResponse |
| GET /api/analysis/tasks/company/{id}/active | ✅ 返回活跃任务 |
| 重复创建去重 | ✅ 返回现有 task_id |
| 不存在企业 404 | ✅ COMPANY_NOT_FOUND |
| 不存在任务 404 | ✅ TASK_NOT_FOUND |
| 任务持久化 | ✅ 文件存在于 runs/web/tasks/ |
| 启动恢复 | ✅ 未完成任务标记为 failed |

### 回归测试

| 测试项 | 结果 |
|--------|------|
| GET /api/companies/search | ✅ 正常返回 |
| GET /api/companies/{id} | ✅ 正常返回 |
| GET /api/companies/{id}/business-events | ✅ 正常返回 |
| GET /api/companies/{id}/judicial-events | ✅ 正常返回 |
| GET /api/companies/{id}/relations | ✅ 正常返回 |
| GET /api/companies/{id}/relation-network | ✅ 正常返回 |
| GET /api/companies/{id}/analysis/latest | ✅ 正常返回 |
| POST /api/analysis（同步接口） | ✅ 保留不变 |

### 前端验证

| 测试项 | 结果 |
|--------|------|
| TypeScript 编译 | ✅ 无错误 |
| 前端构建 | ✅ 构建成功 |
| 前后端接口一致性 | ✅ 12 个方法与后端路由完全匹配 |

### Harness 完整性

| 测试项 | 结果 |
|--------|------|
| src/risk_tools.py | ✅ 未修改 |
| risk.db | ✅ 未修改 |
| .opencode/agents/ | ✅ 未修改 |
| harness_adapter.py | ✅ 未修改 |
| analysis_service.py | ✅ 未修改 |

## 十、已知限制

1. **服务重启恢复**：服务重启后，正在执行的任务会被标记为 `failed`，无法恢复执行。这是因为后台线程随进程结束而终止，无法持久化线程状态。

2. **单 Harness 并发**：系统保持串行化设计，同一时间只允许一个 Harness 分析。这是为了保持与现有 Harness 的兼容性。

3. **轮询间隔**：前端每 3 秒轮询一次任务状态。如果需要更实时的状态更新，可以考虑使用 WebSocket（当前版本未实现）。

4. **FastAPI deprecation**：`@app.on_event("startup")` 已被 FastAPI 标记为 deprecated，建议在后续迭代中迁移到 `lifespan` context manager。

---

**版本**：V1.2  
**日期**：2026-08-25  
**状态**：已交付（DELIVERED）
