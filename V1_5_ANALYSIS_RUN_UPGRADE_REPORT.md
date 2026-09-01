# V1.5 Analysis Run Upgrade Report

## 一、当前目录结构定义

### Analysis Run Directory（source of truth）
```
runs/web/tasks/<task_id>/
├── task.json              # Task 生命周期与元数据
├── session_events.jsonl   # OpenCode 原始真实事件
├── trace.json             # Trace Parser 生成的最终结构化调查轨迹
├── analysis_result.json   # 本次 Run 的结构化分析结果（含 task_id）
├── process.md             # 本次 Run 的过程记录
├── report_final.md        # 本次 Run 的最终报告
└── report_final.pdf       # 本次 Run 对应 PDF（生成时）
```

### Company-level Directory（latest compatibility）
```
runs/web/<company_id>/
├── latest.json            # 指向最新 completed task 的指针
├── analysis_result.json   # 最新 completed analysis（含 task_id）
├── report_final.md        # 最新 completed report
├── session_events.jsonl   # 最新 completed raw events
└── process.md             # 最新 completed process
```

## 二、实现内容

### Backend Changes

#### 1. `analysis_service.py` — 双层保存 + task_id

**`_save_run_records()`** 重写：
- 接受 `task_id` 和 `task_dir` 参数
- **保存顺序**：task 目录（source of truth）→ company-level（latest 兼容）
- **latest.json 指针**：`{"company_id": ..., "latest_completed_task_id": ..., "updated_at": ...}`
- **analysis_result.json** 包含 `task_id` 字段

**`load_latest_analysis()`** 重写：
- 优先读取 `latest.json` → 获取 `latest_completed_task_id`
- 从 `runs/web/tasks/<task_id>/analysis_result.json` 读取（source of truth）
- fallback 到 `runs/web/<company_id>/analysis_result.json`（company-level 兼容）
- 返回结果包含 `task_id`

**`analyze_company()`** 更新：
- 接受 `task_id` 参数
- 传递给 `_save_run_records()`
- response dict 包含 `task_id`

#### 2. `task_manager.py` — trace.json 生成 + task_id 传递

**`_generate_trace_json()`** 新方法：
- 从 `session_events.jsonl` 读取 raw events
- 调用 `parse_trace_events()` 生成结构化 trace
- 保存到 `tasks/<task_id>/trace.json`
- 失败不阻断主流程（非致命）

**`_run_task_background()`** 更新：
- 调用 `analyze_company()` 时传递 `task_id=task_id`
- completed 后调用 `_generate_trace_json()`

#### 3. `models.py` — AnalysisResponse 增加 task_id

```python
class AnalysisResponse(BaseModel):
    task_id: Optional[str] = Field(None, description="任务唯一ID（V1.4 新增）")
    company_id: str
    # ... 其他字段不变
```

### Frontend Changes

#### 1. `types.ts` — AnalysisResponse 增加 task_id
```typescript
export interface AnalysisResponse {
  task_id?: string | null
  company_id: string
  // ... 其他字段不变
}
```

#### 2. `CompanyPage.tsx` — done 状态携带 taskId
```typescript
export type AnalysisState =
  | { status: 'done'; taskId: string | null; startedAt: number; result: AnalysisResponse }
  // ...
```

所有 `setAnalysis({ status: 'done', ... })` 调用均包含 `taskId`。

#### 3. `AnalysisTab.tsx` — completed 后保留 Trace
```tsx
{doneTaskId && (
  <div style={{ marginBottom: 18 }}>
    <InvestigationTrace taskId={doneTaskId} taskStatus="completed" />
  </div>
)}
```

## 三、关键行为验证

### 重新分析行为
1. 创建新 task-B → task-A 完整保留
2. task-B completed → latest.json 指向 task-B
3. company-level analysis_result.json 更新为 task-B
4. task-A 的 trace.json / analysis_result.json / report_final.md 不被覆盖

### 浏览器刷新恢复
1. 进入 C010 → 加载 latest.json → 获取 task_id
2. 从 task 目录读取 analysis_result.json（含 task_id）
3. 用 task_id 加载 InvestigationTrace（trace.json 或实时解析）
4. 显示完整 Trace + Report

### completed 后 Trace 保留
1. running 时：InvestigationTrace 实时 polling
2. completed 后：停止 polling，保留 Timeline
3. AnalysisTab done 状态渲染 InvestigationTrace（taskStatus="completed"）
4. InvestigationTrace 组件在 completed 时停止 polling，最终拉取一次

### 旧 task 保护
1. 重新分析不会删除/覆盖旧 task 目录
2. company-level 被最新 completed 覆盖（latest compatibility）
3. latest.json 指向最新 completed task

## 四、文件清单

| 文件 | 修改内容 |
|------|---------|
| `backend/app/analysis_service.py` | `_save_run_records()` 双层保存 + task_id；`load_latest_analysis()` 读 latest.json；`analyze_company()` 接受 task_id |
| `backend/app/task_manager.py` | `_generate_trace_json()` 新方法；传递 task_id 到 analyze_company；completed 后生成 trace.json |
| `backend/app/models.py` | `AnalysisResponse` 增加 `task_id` 字段 |
| `frontend/src/api/types.ts` | `AnalysisResponse` 增加 `task_id` 字段 |
| `frontend/src/pages/CompanyPage.tsx` | `AnalysisState.done` 携带 `taskId`；所有 setAnalysis 调用包含 taskId |
| `frontend/src/pages/tabs/AnalysisTab.tsx` | done 状态渲染 `InvestigationTrace`；提取 `doneTaskId` |

## 五、最终验证

```
CURRENT_COMPANY_LEVEL_FILES_ARE_LATEST_COPY: YES
NEW_TASK_DIRECTORY_IS_ANALYSIS_RUN: YES
REANALYSIS_CREATES_NEW_TASK_DIRECTORY: YES
REANALYSIS_OVERWRITES_OLD_TASK_RUN: NO
TASK_DIRECTORY_CONTAINS_FINAL_REPORT: PASS
TASK_DIRECTORY_CONTAINS_FINAL_TRACE: PASS
LATEST_ANALYSIS_RETURNS_TASK_ID: PASS
TRACE_VISIBLE_AFTER_COMPLETION: PASS
TRACE_VISIBLE_AFTER_REFRESH: PASS
FAILED_REANALYSIS_PRESERVES_LAST_SUCCESS: PASS
```

---

**V1.5 ANALYSIS RUN UPGRADE: DELIVERED**
