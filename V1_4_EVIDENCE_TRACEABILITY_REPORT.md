# V1.4 Evidence Traceability — 实施报告

> 实施时间：2026-08-24
> 状态：✅ 已完成并通过全量验证

---

## 1. 功能概述

用户在 AI 报告、调查轨迹、关系表格、关系图中看到的 Bxxx / Jxxx / Rxxx 编号，现在可以点击打开右侧抽屉，查看确定性数据库事实。

### 核心原则

- **Evidence Detail = 数据库事实**：不包含 AI 风险分数、风险等级判断、LLM 生成的解释
- **Risk Interpretation = AI Report**：风险判断和解释仍保留在 AI Report 内容中
- **Evidence 抽屉**：展示"原始事实"，不是"风险判断"

---

## 2. 实施内容

### 2.1 后端

| 文件 | 变更 |
|------|------|
| `src/risk_tools.py` | 新增 `get_business_event_by_id()`, `get_judicial_event_by_id()`, `get_relation_by_id()`, `get_evidence_by_id()` — 确定性 DB 查询，不含 LLM/风险判断 |
| `backend/app/deps.py` | Re-export `get_evidence_by_id`，新增 `ERROR_EVIDENCE_NOT_FOUND` |
| `backend/app/models.py` | 新增 `EvidenceResponse` 模型 |
| `backend/app/api.py` | 新增 `GET /api/evidence/{evidence_id}` 端点 |

### 2.2 前端

| 文件 | 变更 |
|------|------|
| `EvidenceDetailDrawer.tsx` | **新建** — 右侧抽屉，展示 B/J/R 三类 Evidence 的 DB 原始事实 |
| `MarkdownReport.tsx` | 增强 — 检测 `[B/J/R]\d+` 模式，渲染为可点击 Badge |
| `RelationsTab.tsx` | 增强 — 关系表格 `relation_id` 列可点击 |
| `InvestigationTrace.tsx` | 增强 — Evidence 标签可点击 |
| `RelationGraph.tsx` | 增强 — 边 tooltip 显示 relation_id badge |
| `Badges.tsx` | 增强 — `EvidenceTag` 支持 `onClick` prop |
| `global.css` | 新增 `.ev-*` 系列 CSS 类 |
| `api/types.ts` | 新增 `EvidenceResponse` 接口 |
| `api/client.ts` | 新增 `getEvidence()` 方法 |

---

## 3. 验证结果

### 3.1 后端 API

| 测试 | 结果 |
|------|------|
| `GET /api/evidence/J008` | ✅ 200 — judicial 事件，C007 鼎峰建设工程有限公司 |
| `GET /api/evidence/B001` | ✅ 200 — business 事件，C001 华辰智能科技有限公司 |
| `GET /api/evidence/R001` | ✅ 200 — relation，C001 → C002 |
| `GET /api/evidence/X999` | ✅ 400 — 无效格式 |
| `GET /api/evidence/B` | ✅ 400 — 无效格式 |
| 30/30 B/J/R Evidence IDs | ✅ 全部 200 |
| 现有 6 个端点回归 | ✅ 全部 200 |

### 3.2 前端

| 测试 | 结果 |
|------|------|
| TypeScript 编译 | ✅ 0 errors |
| Vite 构建 | ✅ 865 modules, 2.75s |
| 文件集成检查 | ✅ 7/7 文件正确导入 |

### 3.3 回归

| 检查项 | 结果 |
|--------|------|
| `risk_tools.py` 原有 6 个函数 | ✅ 完整 |
| `risk.db` 数据完整性 | ✅ 4 tables, 50 rows |
| `api.py` 无原始 SQL | ✅ 0 SQL keywords |
| Agent 定义文件 | ✅ 8 files unmodified |
| 测试目录 | ✅ 8/8 tests pass |

### 3.4 设计合规

| 要求 | 状态 |
|------|------|
| Evidence Detail = DB facts only | ✅ |
| 企业名称可点击跳转 | ✅ |
| ESC 关闭抽屉 | ✅ |
| Loading / Error 状态 | ✅ |
| Badge 颜色 B=蓝, J=紫, R=青 | ✅ |

---

## 4. VERDICT: PASS

所有验证通过，无问题发现。
