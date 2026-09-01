# V1.5 — Cancel Running Analysis 交付报告

## 一、功能概述

支持用户主动取消正在运行的 AI 风险分析任务。取消操作必须是**后端真实取消**，而非前端假取消。

### 核心行为

```
Frontend → Cancel API → Task Manager → 终止 OpenCode risk-orchestrator process group
→ 确认进程已退出 → Task status = cancelled → 保留取消前 Trace → 释放 Harness Lock
```

---

## 二、修改文件清单

### 后端（7 个文件）

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `backend/app/task_manager.py` | **核心修改** | 新增 `cancel_task()` 方法、`_cancel_events` 管理、`on_process_start` PID 回调、`cancel_event` 竞态保护 |
| `backend/app/harness_adapter.py` | **核心修改** | 新增 `cancelled_event` 和 `on_process_start` 参数，重试前检查取消信号 |
| `backend/app/api.py` | 新增端点 | `POST /api/analysis/tasks/{task_id}/cancel` |
| `backend/app/analysis_service.py` | 透传参数 | `analyze_company` 透传 `cancelled_event` 和 `on_process_start` |
| `backend/app/trace_service.py` | 新增事件 | `analysis_cancelled` 事件类型处理 |
| `backend/app/models.py` | 无新增 | 已有 `cancel_reason` 字段 |
| `backend/app/deps.py` | 新增错误码 | `TASK_ALREADY_COMPLETED`、`TASK_ALREADY_FINISHED` |

### 前端（4 个文件）

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `frontend/src/api/client.ts` | 新增方法 | `cancelAnalysisTask()` |
| `frontend/src/pages/tabs/AnalysisTab.tsx` | **核心修改** | 取消按钮 + 确认弹窗 + cancelled 状态展示 |
| `frontend/src/pages/CompanyPage.tsx` | **核心修改** | `AnalysisState.cancelled` + `cancelAnalysis` 回调 + `activeTaskIdRef` |
| `frontend/src/components/InvestigationTrace.tsx` | 样式新增 | `analysis_cancelled` 事件红色样式 + cancelled 轮询停止 |

---

## 三、关键设计决策

### 3.1 复用现有进程清理

Cancel 操作**复用** `terminate_harness_process()` 作为唯一进程清理函数，不维护多套 kill 逻辑：

- timeout kill → `terminate_harness_process(reason="analysis_timeout")`
- cancel kill → `terminate_harness_process(reason="user_cancelled")`
- replace kill → `terminate_harness_process(reason="replaced_by_new_analysis")`

### 3.2 cancelled_event 竞态保护

引入 `threading.Event` 作为取消信号：

1. `cancel_task()` 调用时 `cancel_event.set()`
2. `harness_adapter.run_harness_analysis()` 在以下位置检查该 event：
   - 超时退出后 → 不重试
   - 进程退出后 → 不重试
   - 无 VERIFICATION_STATUS 时不重试
3. `_run_task_background()` 在以下位置检查该 event：
   - `analyze_company` 返回后 → 跳过 `completed` 状态更新
   - 异常处理 → 被取消的 `HarnessError` 不标记为 `failed`
   - watchdog 超时 → 设置 event 防止状态覆盖

### 3.3 PID 检测改进

**旧方案**（不可靠）：`pgrep -f "opencode.*run.*risk-orchestrator"` → 可能匹配到其他 opencode 进程

**新方案**（准确）：`on_process_start` 回调 → 直接从 `subprocess.Popen.pid` 获取准确 PID

```python
def _on_process_start(pid: int, pgid: int) -> None:
    task.process_pid = pid
    task.process_pgid = pgid
    task.process_alive = True
    self._persist_task(task)
```

### 3.4 Trace 保留

取消后：
- `session_events.jsonl` 完整保留（取消前的调查轨迹）
- `trace.json` 生成包含 `analysis_cancelled` 事件
- UI 展示"分析已取消"而非"分析失败"
- `cancelled ≠ failed` 语义区分

---

## 四、Cancel API 契约

### 端点

```
POST /api/analysis/tasks/{task_id}/cancel
```

### 请求体

无（空 body）

### 响应

```json
{
  "task_id": "task-xxx",
  "company_id": "C010",
  "status": "cancelled",
  "cancel_reason": "user_cancelled",
  "finished_at": "2026-08-31T...",
  "process_alive": false
}
```

### 错误码

| HTTP 状态码 | 错误码 | 说明 |
|------------|--------|------|
| 404 | `TASK_NOT_FOUND` | 任务不存在 |
| 409 | `TASK_ALREADY_COMPLETED` | 任务已完成，无法取消 |
| 409 | `TASK_ALREADY_FINISHED` | 任务已结束（failed），无法取消 |

### 幂等性

对已 `cancelled` 的任务重复调用 → 返回当前 task（不报错）

---

## 五、前端交互

### 5.1 取消按钮

Running 状态下显示红色"取消分析"按钮：

```
[✕ 取消分析]
```

### 5.2 确认弹窗

点击后内联显示确认弹窗：

```
确定要取消本次 AI 风险分析吗？
已完成的调查过程将保留，但不会生成完整风险报告。

[继续分析]  [取消分析]
```

### 5.3 取消中状态

确认后按钮变为：

```
正在取消...
```

### 5.4 取消完成

显示红色"已取消"状态卡片 + 保留的调查轨迹 + "重新分析"按钮

---

## 六、验收测试结果

```
V1_5_CANCEL_ANALYSIS_REPORT:
CANCEL_API: PASS
RUNNING_TASK_CANCEL: PASS
QUEUED_TASK_CANCEL: PASS
PROCESS_GROUP_TERMINATED: PASS
TRACE_PRESERVED_AFTER_CANCEL: PASS
IDEMPOTENT_CANCEL: PASS
CANCEL_COMPLETED_TASK: PASS
REANALYSIS_AFTER_CANCEL: PASS
LATEST_COMPLETED_RUN_UNAFFECTED: PASS
NORMAL_OPENCODE_SERVICE_UNAFFECTED: PASS
REGRESSION: PASS
```

### 详细结果

| 测试项 | 结果 | 说明 |
|--------|------|------|
| CANCEL_API | ✅ PASS | `POST /api/analysis/tasks/{id}/cancel` 端点存在，404/409 错误码正确 |
| RUNNING_TASK_CANCEL | ✅ PASS | C010 running → cancelled，PID 消失，process_alive=False |
| QUEUED_TASK_CANCEL | ✅ PASS | queued → cancelled（无需杀进程） |
| PROCESS_GROUP_TERMINATED | ✅ PASS | 无残留 risk-orchestrator 进程 |
| TRACE_PRESERVED_AFTER_CANCEL | ✅ PASS | 4 个事件保留，最后一条为 analysis_cancelled |
| IDEMPOTENT_CANCEL | ✅ PASS | 重复取消已 cancelled 任务返回幂等结果 |
| CANCEL_COMPLETED_TASK | ✅ PASS | 返回 409 TASK_ALREADY_COMPLETED |
| REANALYSIS_AFTER_CANCEL | ✅ PASS | 取消后 force_new=true 可正常创建新任务 |
| LATEST_COMPLETED_RUN_UNAFFECTED | ✅ PASS | C007 latest 仍为 completed，risk_level=高风险 |
| NORMAL_OPENCODE_SERVICE_UNAFFECTED | ✅ PASS | opencode 服务、risk.db、agents 文件均未被破坏 |
| REGRESSION | ✅ PASS | 所有 C001-C010 查询正常，1 个现有测试通过 |

---

## 七、未修改清单

以下模块**未被修改**：

- ✅ risk-orchestrator agent
- ✅ coverage-auditor agent
- ✅ risk-verifier agent
- ✅ Gold Case
- ✅ risk.db
- ✅ src/risk_tools.py（仅有 V1.4 Evidence 查询函数，非 Cancel 引入）
- ✅ Evidence Lookup
- ✅ 风险等级规则
- ✅ PDF 内容
- ✅ Relation Graph
- ✅ tests/

---

## 八、Bug 修复记录

### Bug 1: harness_adapter 重试路径无取消检查

**问题**：用户取消后，`harness_adapter` 的重试逻辑会启动新的 subprocess

**修复**：在 3 个重试检查点添加 `cancelled_event.is_set()` 检查：
- 超时退出后
- 进程退出后
- 无 VERIFICATION_STATUS 重试前

### Bug 2: PID 检测通过 pgrep 不可靠

**问题**：`pgrep -f "opencode.*run.*risk-orchestrator"` 可能匹配到其他 opencode 进程

**修复**：新增 `on_process_start` 回调，直接从 `subprocess.Popen.pid` 获取准确 PID

### Bug 3: 状态竞态条件

**问题**：cancel 设置 cancelled 后，后台线程可能覆盖为 failed

**修复**：引入 `cancel_event` (threading.Event)，在所有状态更新路径前检查

### Bug 4: Vite 代理端口不匹配

**问题**：`vite.config.ts` 中代理配置指向 `http://127.0.0.1:8000`，但后端实际运行在端口 `8001`，导致所有前端 API 调用（包括 Cancel）都被代理到错误端口

**修复**：将后端启动端口改为 `8000`，与 Vite 代理配置一致。此修复同时解决了所有前端功能的代理问题

---

## 九、开发迭代记录

| 轮次 | 结果 | 说明 |
|------|------|------|
| 第 1 轮 | 后端实现 PASS → 前端实现 PASS → 集成测试 REVISE | 发现 3 个关键 bug |
| 第 2 轮 | Bug 修复 → 全量重新验收 PASS | 所有 9+ 项测试通过 |
| 第 3 轮 | 端到端浏览器测试 PASS | 修复 Vite 代理端口不匹配问题 |

---

*报告更新时间：2026-08-31*
*系统版本：V1.5 — Cancel Running Analysis*
*最终状态：全量验证通过，浏览器端到端测试 PASS*
