# 企业关联风险智能洞察系统 V1.1 功能报告

## 1. 新增功能

### 功能一：完整企业关联关系网络图

**目标**：用户查看某一家企业时，能够展示该企业所在关联网络中可以从现有 relations 数据持续发现的完整关系网络，而不仅是一跳关系。

**实现方式**：
- 后端新增 BFS 遍历服务，从目标企业开始，递归查询所有关联企业
- 前端使用 ECharts graph 系列渲染完整网络图
- 支持节点拖拽、缩放、平移、Tooltip

### 功能二：AI 风险报告导出 PDF

**目标**：用户可以下载已生成的 AI 风险分析报告为正式 PDF 文件。

**实现方式**：
- 后端从已有分析结果（runs/web/<company_id>/）读取 Markdown 报告
- 使用 fpdf2 将 Markdown 转换为 PDF
- 前端在 AI 风险洞察 Tab 添加"导出 PDF"按钮

---

## 2. 新增/修改文件

### 后端新增文件

| 文件 | 说明 |
|------|------|
| `backend/app/relation_network_service.py` | 企业关联关系网络遍历服务（BFS） |
| `backend/app/pdf_service.py` | PDF 生成服务（Markdown → PDF） |

### 后端修改文件

| 文件 | 变更 |
|------|------|
| `backend/app/models.py` | 新增 NetworkNode、NetworkEdge、RelationNetworkResponse 模型 |
| `backend/app/api.py` | 新增 2 个 API 路由 |
| `backend/requirements.txt` | 新增 markdown、fpdf2 依赖 |

### 前端修改文件

| 文件 | 变更 |
|------|------|
| `frontend/src/api/types.ts` | 新增 NetworkNode、NetworkEdge、RelationNetworkResponse 类型 |
| `frontend/src/api/client.ts` | 新增 relationNetwork() 和 exportPdf() 方法 |
| `frontend/src/components/RelationGraph.tsx` | 重构支持多跳网络数据 |
| `frontend/src/pages/tabs/RelationsTab.tsx` | 并行加载一跳关系和完整网络 |
| `frontend/src/pages/tabs/AnalysisTab.tsx` | 新增"导出 PDF"按钮 |

---

## 3. 完整关系网络遍历方式

### 算法：广度优先搜索（BFS）

```
1. 从目标企业开始，将其加入队列和 visited 集合
2. 当队列不为空且节点数未超过 MAX_NODES：
   a. 从队列取出一个企业
   b. 调用 get_company_relations() 获取其一跳关系
   c. 对于每条关系：
      - 如果关系 ID 未访问过，添加到边列表
      - 如果目标企业未访问过，添加到节点列表和队列
3. 返回完整网络数据
```

### 关键实现

```python
def build_relation_network(company_id: str, max_nodes: int = 100) -> Dict:
    # 初始化
    nodes = []
    edges = []
    visited_companies: Set[str] = set()
    visited_relations: Set[str] = set()
    queue = deque()

    # 添加根节点
    root_node = {...}
    nodes.append(root_node)
    visited_companies.add(company_id)
    queue.append((company_id, 0))

    # BFS 遍历
    while queue and len(nodes) < max_nodes:
        current_id, depth = queue.popleft()
        relations = get_company_relations(current_id)

        for rel in relations:
            relation_id = rel.get("relation_id")
            # 边去重
            if relation_id in visited_relations:
                continue
            visited_relations.add(relation_id)

            # 添加边
            edges.append({...})

            # 处理目标节点
            target_id = to_id if from_id == current_id else from_id
            if target_id not in visited_companies:
                if len(nodes) >= max_nodes:
                    truncated = True
                    break
                # 获取目标企业信息
                target_profile = get_company_profile(target_id)
                if target_profile:
                    nodes.append({...})
                    visited_companies.add(target_id)
                    queue.append((target_id, depth + 1))

    return {
        "root_company_id": company_id,
        "nodes": nodes,
        "edges": edges,
        "truncated": truncated
    }
```

---

## 4. 如何防止闭环和无限递归

### 防护措施

1. **visited_companies 集合**：
   - 记录已访问的企业 ID
   - 同一企业不会被重复添加到节点列表
   - 防止闭环导致的无限递归

2. **visited_relations 集合**：
   - 记录已访问的关系 ID
   - 同一关系不会被重复添加到边列表
   - 避免重复边

3. **MAX_NODES 安全限制**：
   - 默认值：100
   - 可通过参数配置
   - 当节点数达到限制时，truncated = True
   - 防止数据量过大导致性能问题

4. **BFS 遍历**：
   - 使用队列而非递归
   - 天然避免栈溢出风险
   - 每个企业最多被访问一次

### 测试验证

```
C004 关系网络：
- 节点数: 5 (C004, C005, C006, C007, C008)
- 边数: 6 (R005, R006, R007, R008, R009, R010)
- 节点去重: True
- 边去重: True
- 是否截断: False

闭环检测（C001）：
- 节点去重: True
- 边去重: True
```

---

## 5. PDF 生成方案

### 技术栈

- **库**：fpdf2（纯 Python，无系统依赖）
- **字体**：macOS STHeiti Light.ttc（支持中文）
- **流程**：Markdown → 解析 → PDF 直接渲染

### PDF 内容结构

1. **封面/报告头部**：
   - 企业风险调查报告（标题）
   - 企业名称
   - 企业 ID
   - 报告生成时间

2. **摘要信息**：
   - 风险等级
   - Verification Status
   - 关键证据（evidence_ids）
   - 关联企业（related_companies）

3. **完整 Final Report**：
   - 一级标题
   - 二级标题
   - 三级标题
   - 表格
   - 粗体
   - 列表
   - 中文、数字、百分比

### PDF 生成流程

```python
def _convert_md_to_pdf(markdown_content: str, analysis_result: dict, output_path: Path):
    from fpdf import FPDF

    # 创建 PDF
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_font("SimHei", "", "/System/Library/Fonts/STHeiti Light.ttc", uni=True)

    # 添加第一页：封面
    pdf.add_page()
    pdf.set_font("SimHei", size=24)
    pdf.cell(0, 20, "企业风险调查报告", ln=True, align="C")
    # ...

    # 解析并渲染 Markdown 内容
    _render_markdown_to_pdf(pdf, markdown_content)

    # 保存 PDF
    pdf.output(str(output_path))
```

---

## 6. 新增 API

### API 8：企业关联关系网络

```
GET /api/companies/{company_id}/relation-network
```

**请求参数**：
- `company_id`（路径参数）：企业唯一 ID

**响应模型**：
```json
{
  "root_company_id": "C004",
  "nodes": [
    {
      "company_id": "C004",
      "company_name": "鼎峰建设工程有限公司",
      "industry": "建筑业",
      "business_status": "存续",
      "depth": 0
    },
    {
      "company_id": "C005",
      "company_name": "鼎峰建材有限公司",
      "industry": "批发和零售业",
      "business_status": "存续",
      "depth": 1
    }
  ],
  "edges": [
    {
      "relation_id": "R005",
      "source": "C004",
      "target": "C005",
      "relation_type": "股权",
      "equity_ratio": 0.6,
      "amount": 27000000,
      "status": "存续"
    }
  ],
  "truncated": false
}
```

**错误响应**：
- 404：企业不存在
- 500：内部错误

### API 9：AI 风险报告 PDF 导出

```
GET /api/analysis/{company_id}/latest/pdf
```

**请求参数**：
- `company_id`（路径参数）：企业唯一 ID

**响应**：
- Content-Type: application/pdf
- Content-Disposition: attachment; filename="C007_鼎峰建设工程有限公司_企业风险调查报告.pdf"

**错误响应**：
- 404：企业不存在或无分析结果
- 500：PDF 生成失败

---

## 7. 前端变化

### 关系网络图组件（RelationGraph.tsx）

**新增功能**：
- 支持 `networkData` prop（完整多跳网络数据）
- 优先使用完整网络数据，回退到一跳关系
- 边标签格式化：`60% 股权`、`2250万对外投资`
- 节点按深度分色：root=#2563eb, depth=1=#3b82f6, depth>1=#60a5fa
- 显示网络统计信息：节点数、边数、是否截断

**保留功能**：
- 节点拖拽
- 滚轮缩放
- 平移
- Tooltip
- 关系类型图例

### 关联关系 Tab（RelationsTab.tsx）

**变化**：
- 并行加载一跳关系和完整网络（Promise.all）
- 同时传递 `relations` 和 `networkData` 给 RelationGraph

### AI 风险洞察 Tab（AnalysisTab.tsx）

**新增功能**：
- "导出 PDF"按钮（在"重新分析"按钮旁边）
- Loading 状态管理（pdfLoading）
- 错误状态管理（pdfError）
- 禁用控制（分析中不可重复点击）

**交互流程**：
1. 用户点击"导出 PDF"
2. 按钮显示"导出中..."，禁用
3. 调用 `api.exportPdf(companyId)`
4. 成功：浏览器下载 PDF 文件
5. 失败：显示错误提示

---

## 8. 测试结果

### 后端测试

| 测试项 | 结果 |
|--------|------|
| 后端启动 | ✅ 正常启动 |
| 健康检查 | ✅ 返回 {"status": "ok"} |
| 关系网络 API | ✅ C004 返回 5 节点 6 边 |
| PDF 导出 API | ✅ C007 返回 7 页 PDF |
| 回归测试 | ✅ C001-C010 全部正常 |

### 前端测试

| 测试项 | 结果 |
|--------|------|
| TypeScript 编译 | ✅ 无错误 |
| Vite 构建 | ✅ 成功 |
| 开发服务器 | ✅ 正常启动 |
| 页面渲染 | ✅ 正常显示 |

### 集成测试

| 测试项 | 结果 |
|--------|------|
| 前端代理到后端 | ✅ 正常 |
| API 调用 | ✅ 全部成功 |
| 接口一致性 | ✅ 路径/字段完全对齐 |

### 验收要求验证

#### A. 完整关系图

| 要求 | 结果 |
|------|------|
| C004 包含 5 个节点 | ✅ |
| C004 包含 6 条边 | ✅ |
| 节点去重 | ✅ |
| 边去重 | ✅ |
| 闭环检测 | ✅ |
| 点击节点识别企业 | ✅ |
| 关系表格正常 | ✅ |

#### B. PDF 导出

| 要求 | 结果 |
|------|------|
| 有分析结果时返回 PDF | ✅ |
| PDF 文件类型正确 | ✅ |
| 无分析结果时返回 404 | ✅ |
| PDF 包含企业名称 | ✅ |
| PDF 包含风险等级 | ✅ |
| PDF 包含完整报告 | ✅ |
| 中文正常 | ✅ |
| 表格正常 | ✅ |

#### C. 回归测试

| 要求 | 结果 |
|------|------|
| 企业搜索正常 | ✅ |
| 企业详情正常 | ✅ |
| 工商动态正常 | ✅ |
| 司法风险正常 | ✅ |
| AI 风险分析正常 | ✅ |
| 已有报告恢复正常 | ✅ |
| 重新分析正常 | ✅ |

---

## 9. Risk Harness 是否保持不变

**是的，Risk Harness 完全保持不变。**

### 验证结果

| 文件 | 状态 |
|------|------|
| src/risk_tools.py | ✅ 未修改 |
| risk.db | ✅ 未修改 |
| tests/gold_cases.json | ✅ 未修改 |
| .opencode/agents/ | ✅ 未修改 |
| tests/ | ✅ 未修改 |
| runs/ | ✅ 未修改 |

### 设计边界

- **Risk Intelligence**：由 Risk Harness 负责（risk-orchestrator → coverage-auditor → risk-verifier）
- **Web Presentation / Export**：由 Web 系统负责（关系网络图、PDF 导出）

两者保持解耦，Web 功能扩展不影响 Risk Harness 的研究设计。

---

## 10. 已知限制

### 1. PDF 中文字体

- **限制**：当前使用 macOS 系统字体 STHeiti Light.ttc
- **影响**：在 Linux/Windows 环境可能需要调整字体路径
- **解决方案**：后续可添加字体配置或使用嵌入字体

### 2. PDF 布局

- **限制**：fpdf2 的 Markdown 解析相对简单
- **影响**：复杂 Markdown 格式可能渲染不完美
- **解决方案**：后续可升级为更强大的 Markdown 解析器

### 3. 关系网络深度

- **限制**：MAX_NODES 默认 100
- **影响**：超大网络可能被截断
- **解决方案**：可通过参数配置，或后续添加分页加载

### 4. PDF 生成性能

- **限制**：每次请求都重新生成 PDF
- **影响**：大报告可能需要几秒
- **解决方案**：后续可添加缓存机制

---

## 11. 启动方式

### 后端

```bash
cd backend
.venv/bin/python -m app.main
# 或
.venv/bin/uvicorn app.main:app --port 8000
```

### 前端

```bash
cd frontend
npm run dev    # 开发模式：http://localhost:5173/
npm run build  # 生产构建 → dist/
```

### 完整启动

```bash
# 终端 1：启动后端
cd backend
.venv/bin/python -m app.main

# 终端 2：启动前端
cd frontend
npm run dev
```

---

## 12. 总结

### V1.1 功能完成情况

| 功能 | 状态 |
|------|------|
| 完整企业关联关系网络图 | ✅ 已完成 |
| AI 风险报告导出 PDF | ✅ 已完成 |

### 验证结果

- 后端验证：✅ PASS
- 前端验证：✅ PASS
- 集成验证：✅ PASS
- 回归验证：✅ PASS

### 最终结论

**企业关联风险智能洞察系统 V1.1 功能开发完成，所有验收要求均已满足。**

---

**报告生成时间**：2026-08-19
**报告版本**：V1.1
**系统版本**：企业关联风险智能洞察系统 V1.1
