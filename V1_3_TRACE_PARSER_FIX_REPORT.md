# V1.3 Trace Parser 语义修复报告

## 问题根因

### TRACE_ROOT_CAUSE_UNKNOWN_COMPANY

**原因**：旧 Parser 从 `part.arguments` 读取 company_id，但真实 OpenCode schema 中参数位于 `part.state.input`。

**真实 Tool Use Event Schema**（已验证）：
```json
{
  "type": "tool_use",
  "timestamp": 1787817765196,
  "part": {
    "type": "tool",
    "tool": "risk_search_company",
    "callID": "call_xxx",
    "state": {
      "status": "completed",
      "input": {
        "company_id": "C010"
      },
      "output": "...",
      "time": {"start": 1787817765123, "end": 1787817765194}
    }
  }
}
```

**修复**：从 `part.state.input.company_id` 提取，从 `part.state.output` 解析 company_name 缓存。

### TRACE_ROOT_CAUSE_EARLY_COMPLETION

**原因**：旧 Parser 在遍历完所有 raw events 后无条件追加 `analysis_completed`：

```python
# 旧代码（错误）
if analysis_started and trace_events:
    last_type = trace_events[-1].get("type", "")
    if last_type != "analysis_completed":
        trace_events.append({"type": "analysis_completed", ...})
```

这导致即使 task_status=running，只要 raw_events 遍历完毕就会生成 analysis_completed。

**原始触发事件**：不是某个特定 raw event，而是遍历结束后的无条件追加逻辑。

**修复**：`analysis_completed` / `analysis_failed` 仅在 `task_status` 指示完成/失败时生成，由 api.py 传入 `task_status` 参数。

### Real Tool Args Schema

```
risk_search_company:
  part.state.input.keyword = "C010"
  part.state.input.company_id = (可能为空)

risk_get_company_profile:
  part.state.input.company_id = "C010"

risk_get_business_events:
  part.state.input.company_id = "C010"

risk_get_judicial_events:
  part.state.input.company_id = "C010"

risk_get_company_relations:
  part.state.input.company_id = "C010"

task (subagent spawn):
  part.state.input.subagent_type = "coverage-auditor" / "risk-verifier"
```

## 修改文件

| 文件 | 改动 |
|------|------|
| `backend/app/trace_service.py` | 完全重写，修复所有语义错误 |
| `backend/app/api.py` | 传入 `task_status` 给 `parse_trace_events` |

## 关键改动

### 1. analysis_started 始终为第一条事件

不再从 OpenCode 文本中识别，直接生成：
```python
sequence += 1
trace_events.append({
    "type": "analysis_started",
    "title": "开始企业风险调查",
    ...
})
```

### 2. company_id 从 part.state.input 提取

```python
tool_input = state.get("input", {})
company_id, keyword = _extract_company_from_input(tool_input)
```

### 3. analysis_completed 由 task_status 驱动

```python
if task_status == "completed":
    trace_events.append({"type": "analysis_completed", ...})
elif task_status == "failed":
    trace_events.append({"type": "analysis_failed", ...})
# task_status == "running" → 不追加任何 lifecycle 事件
```

### 4. tool start/result 通过 callID 配对

同一次 tool call 的 start 和 result 通过 `callID` 配对，不会生成重复 Trace Event。

### 5. coverage / verification 从结构化文本识别

```python
# COVERAGE_STATUS: COMPLETE / INCOMPLETE
m_coverage = COVERAGE_STATUS_PATTERN.search(text)

# VERDICT: PASS / REVISE
m_verdict = VERDICT_PATTERN.search(text)
```

## 验收测试结果

### TEST 1: Company ID 提取
```
risk_get_company_profile args company_id=C010
→ company_id == "C010"
→ 不出现 "未知"
✅ PASS
```

### TEST 2: Tool start/result 配对
```
tool_use (status=completed) → 单个 completed trace event
通过 callID 配对，不生成重复事件
✅ PASS
```

### TEST 3: 普通 orchestrator message completed
```
task_status=running → 不产生 analysis_completed
✅ PASS
```

### TEST 4: coverage-auditor completed
```
COVERAGE_STATUS: COMPLETE → coverage_result
不产生 analysis_completed
✅ PASS
```

### TEST 5: risk-verifier PASS
```
VERDICT: PASS → verification_result
不产生 analysis_completed
✅ PASS
```

### TEST 6: task.status=running
```
task_status=running → Trace 不允许 analysis_completed
✅ PASS
```

### TEST 7: task.status=completed
```
task_status=completed → 最后生成且只生成一个 analysis_completed
✅ PASS
```

### TEST 8: analysis_started 顺序
```
analysis_started 位于所有 tool_call 之前
✅ PASS
```

### TEST 9: 多企业调查
```
C010 调查后又查询 C002 → 两者属于同一 task
不产生第二个 analysis_started
✅ PASS
```

### TEST 10: 已完成 Tool 状态
```
completed task 中，所有 tool_call status=completed
✅ PASS
```

### TASK_STATUS_AS_SOURCE_OF_TRUTH: PASS
### COMPANY_ID_EXTRACTION: PASS
### TOOL_START_RESULT_PAIRING: PASS
### ANALYSIS_START_ORDER: PASS
### NO_EARLY_ANALYSIS_COMPLETED: PASS
### COVERAGE_SEMANTICS: PASS
### VERIFIER_SEMANTICS: PASS
### REAL_BROWSER_TEST: PASS

## 真实 OpenCode JSONL Event Types

| 类型 | 说明 |
|------|------|
| `tool_use` | 工具调用（含 state.status=input/output） |
| `text` | 助手文本输出 |
| `step_start` | 步骤开始 |
| `step_finish` | 步骤结束（含 tokens/cost） |

## 已知限制

1. Coverage/Verification 识别依赖文本中的 `COVERAGE_STATUS` / `VERDICT` 模式
2. company_name 缓存依赖 tool output 解析，首次调用可能没有名称
3. subagent spawn（`task` tool）不生成单独的 coverage_started / verification_started 事件
