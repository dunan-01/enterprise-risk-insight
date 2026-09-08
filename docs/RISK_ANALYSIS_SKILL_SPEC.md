# RISK_ANALYSIS_SKILL_SPEC.md

> Risk Analysis Skill — 设计规范  
> 版本：1.0.0  
> 日期：2026-09-08  
> 状态：Design Specification（非实现）

---

## 一、Skill 定位

### 1.1 名称

```
Risk Analysis Skill
```

### 1.2 能力描述

输入企业 ID，自动完成端到端的企业风险调查与报告生成：

1. 多源企业信息调查（工商、司法、关系、舆情、财务、招聘）
2. 风险证据抽取与 Provenance 标记
3. 企业自身风险评估（Own Risk Engine）
4. 关联企业关系分析（Related Company Profile）
5. 风险传导计算（Relationship Transmission）
6. 综合风险判断（Comprehensive Risk Fusion）
7. 生成标准化风险报告（Risk Report Contract）

### 1.3 适用场景

| 场景 | 说明 |
|------|------|
| 单企业风险调查 | 输入 C001，输出完整风险报告 |
| 批量企业筛查 | 依次输入 C001-C010，输出风险等级摘要 |
| 关联网络风险评估 | 输入目标企业，自动调查关联企业并计算传导风险 |
| 风险监控 | 定期重新分析，追踪风险变化 |

### 1.4 不适用场景

| 场景 | 原因 |
|------|------|
| 实时风险预警 | Skill 是批处理模式，非流式 |
| 投资决策 | 系统定位是风险洞察，不提供投资建议 |
| 法律意见 | 系统不替代专业法律、审计或授信决策 |

---

## 二、Skill 输入输出协议

### 2.1 Input

```typescript
interface SkillInput {
  /** 企业唯一 ID，如 C001 */
  company_id: string;
}
```

### 2.2 Output

```typescript
interface SkillOutput {
  /** 完整风险报告 Markdown 文本 */
  report: string;

  /** 综合风险等级：低风险 | 中风险 | 中高风险 | 高风险 */
  risk_level: string;

  /** 综合风险评分（0-300+） */
  risk_score: number;

  /** 风险模式：A（双重风险）| B（传染风险）| C（孤立风险）| D（低风险） */
  risk_case: 'A' | 'B' | 'C' | 'D';

  /** 支撑风险判断的关键 Evidence ID 列表 */
  evidence: string[];

  /** 完整风险推理链（用于审计和调试） */
  risk_trace: RiskTrace;
}

interface RiskTrace {
  /** 自身风险评估结果 */
  own_risk: {
    score: number;
    level: string;
    triggered_rules: string[];
    hard_rule_hits: string[];
  };

  /** 关联风险暴露评估结果 */
  relationship_exposure: {
    score: number;
    level: string;
    company_contributions: Array<{
      company_id: string;
      own_score: number;
      transmitted_score: number;
    }>;
  };

  /** 综合风险融合结果 */
  comprehensive_risk: {
    score: number;
    level: string;
    case: string;
    case_label: string;
    explanation: string;
    fusion_trace: {
      own_score: number;
      exposure_score: number;
      case_bonus: number;
      formula: string;
    };
  };

  /** Evidence provenance：每个 Evidence 的来源和归属 */
  evidence_provenance: Array<{
    evidence_id: string;
    source: string;
    owner_company: string;
    contributes_to: 'own_risk' | 'relationship_exposure' | 'both';
  }>;
}
```

### 2.3 字段来源约束

| 字段 | 允许来源 | 禁止来源 |
|------|----------|----------|
| `risk_level` | `comprehensive_risk.level` | `own_risk.level`、`relationship_exposure.level`、LLM 自行指定 |
| `risk_score` | `comprehensive_risk.score` | `own_risk.score`、`relationship_exposure.score`、LLM 自行指定 |
| `risk_case` | `comprehensive_risk.case` | LLM 自行判定 |
| `evidence` | Rule Engine 触发的 Evidence ID | 未参与风险判断的 Evidence |
| `report` | LLM 生成 + postprocessor 注入 | 纯 LLM 输出（未经确定性注入） |

---

## 三、Skill 执行流程

### 3.1 完整 Pipeline

```
Input: company_id
    │
    ▼
┌─────────────────────────────────────────────┐
│ 1. Investigation Agent                      │
│    - 调用 risk_* 工具查询企业信息            │
│    - 调查关联企业（含多跳）                  │
│    - 收集 Evidence 并标记 Provenance         │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│ 2. Evidence Collection                      │
│    - 工商 (B)、司法 (J)、关系 (R)           │
│    - 舆情 (P)、财务 (F)、招聘 (H)           │
│    - 每条 Evidence 标记 owner_company_id     │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│ 3. Own Risk Evaluation                      │
│    - Rule Engine 基于企业自身 Evidence 计算  │
│    - 输出 own_risk: {score, level, rules}   │
│    - 关联企业 Evidence 不进入 own_risk       │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│ 4. Related Company Profile                  │
│    - 构建关联企业 Risk Profile               │
│    - 每个关联企业的 own_risk 独立计算        │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│ 5. Relationship Transmission                │
│    - 基于关系图 + 关联企业 own_risk 计算    │
│    - 输出 relationship_exposure:            │
│      {score, level, company_contributions}  │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│ 6. Comprehensive Risk Fusion                │
│    - 融合 own_risk + relationship_exposure  │
│    - 输出 comprehensive_risk:               │
│      {score, level, case, explanation}      │
│    - Case 判定 + 硬规则覆盖检查             │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│ 7. Report Generation                        │
│    - LLM 生成报告正文                       │
│    - postprocessor 注入 risk_level/score    │
│    - postprocessor 注入 case + explanation  │
│    - 输出 FINAL_REPORT_BEGIN/END 包裹的报告 │
└─────────────────────────────────────────────┘
    │
    ▼
Output: SkillOutput
```

### 3.2 阶段依赖关系

| 阶段 | 依赖 | 可并行 |
|------|------|--------|
| 1. Investigation | 无 | 是（多企业可并行） |
| 2. Evidence Collection | 阶段 1 | 否 |
| 3. Own Risk Evaluation | 阶段 2 | 否 |
| 4. Related Company Profile | 阶段 2 | 是（可与阶段 3 并行） |
| 5. Relationship Transmission | 阶段 3, 4 | 否 |
| 6. Comprehensive Risk Fusion | 阶段 3, 5 | 否 |
| 7. Report Generation | 阶段 6 | 否 |

---

## 四、工具调用规范

### 4.1 允许使用的工具

| 工具 | 用途 | 必须绑定 Evidence |
|------|------|-------------------|
| `risk_search_company` | 企业名称/ID 搜索 | 否 |
| `risk_get_company_profile` | 企业工商信息 | 否 |
| `risk_get_business_events` | 工商动态事件 | 是（B 类） |
| `risk_get_judicial_events` | 司法事件 | 是（J 类） |
| `risk_get_company_relations` | 企业关系 | 是（R 类） |
| `risk_get_public_opinion_events` | 舆情事件 | 是（P 类） |
| `risk_get_financial_reports` | 财务报告 | 是（F 类） |
| `risk_get_recruitment_events` | 招聘信息 | 是（H 类） |

### 4.2 Evidence 绑定规则

**必须绑定 Evidence 的场景：**
- 所有风险结论（"C007 存在被执行记录"→ 必须引用 J008）
- 所有关联风险传导判断（"风险通过 R001 传导"→ 必须引用 R001）
- 所有财务趋势判断（"营收连续下降"→ 必须引用 F001/F002/F003）

**禁止不绑定 Evidence 的场景：**
- "该企业存在风险" → 必须写 "该企业存在风险（J008、J010）"
- "关联企业风险较高" → 必须写 "关联企业 C007 风险较高（B011、F005）"

### 4.3 禁止操作

| 禁止操作 | 原因 |
|----------|------|
| 使用 `edit`/`write`/`bash` 写入文件 | 报告在对话中输出，不写文件 |
| 使用非 `risk_*` 的工具 | 只允许查询，不允许修改 |
| 跳过 Evidence 直接给出结论 | 违反 Evidence Provenance 原则 |

---

## 五、Risk Reasoning Contract

### 5.1 三层风险模型

| 层级 | 字段 | 语义 | 数据来源 |
|------|------|------|----------|
| 第一层 | `own_risk` | 企业自身有多危险？ | Rule Engine（仅企业自身 Evidence） |
| 第二层 | `relationship_exposure` | 因关联关系被动承受多少风险？ | Transmission Engine（关联企业 own_risk + 关系图） |
| 第三层 | `comprehensive_risk` | 整体风险状况如何？ | Fusion Engine（own_risk + exposure 融合） |

### 5.2 不变量

| ID | 不变量 | 说明 |
|----|--------|------|
| I-1 | `comprehensive_risk.score >= own_risk.score` | 综合风险不低于自身风险 |
| I-2 | `comprehensive_risk.score >= exposure.score` | 综合风险不低于传导风险 |
| I-3 | 硬规则命中 → `comprehensive_risk.level == own_risk.level` | 硬规则不降级 |
| I-4 | `own=0 AND exposure=0 → comprehensive=0` | 双零则零 |
| I-5 | `case` 由 `own_is_high` 和 `exposure_is_high` 唯一确定 | Case 判定确定性 |

### 5.3 Case 分类

| Case | 名称 | own_risk | exposure | bonus | 语义 |
|------|------|----------|----------|-------|------|
| A | 双重风险 | high | high | +20 | 自身出问题 + 关联也出问题 |
| B | 传染风险 | low | high | +10 | 自身健康但被关联企业拖累 |
| C | 孤立风险 | high | low | +0 | 自身出问题但关联网络清洁 |
| D | 低风险 | low | low | +0 | 自身健康且关联网络清洁 |

### 5.4 引用契约

本 Skill 的 Risk Reasoning 遵循以下契约文档：

- `docs/COMPREHENSIVE_RISK_CONTRACT.md` — 三层风险模型、Case 分类、Fusion 公式
- `docs/RISK_REPORT_CONTRACT.md` — 报告结构、章节规则、Evidence 引用规则

---

## 六、Report Generation Contract

### 6.1 报告第一行

```
# 企业关联风险调查报告
```

### 6.2 固定一级章节（8 个，顺序不可调换）

| 序号 | 章节名称 | 动态规则 |
|------|----------|----------|
| 一 | 风险结论摘要 | 固定 |
| 二 | 企业自身主要风险 | 二级小节动态生成（仅当存在 Material Risk） |
| 三 | 关联企业及风险传导 | 按关联企业逐个展开 |
| 四 | 多源证据综合分析 | 交叉验证，非罗列 |
| 五 | 风险缓释因素与矛盾信号 | 呈现反面证据 |
| 六 | 综合风险判断 | 含确定性注入字段 |
| 七 | 证据限制与不确定性 | 事实/推断/未核实区分 |
| 八 | 关键证据引用 | 仅支撑判断的 Evidence |

### 6.3 第六章确定性注入字段

```markdown
## 六、综合风险判断

综合风险等级：{comprehensive_risk.level}
风险评分：{comprehensive_risk.score}
风险模式：{comprehensive_risk.case}（{case_label}）
风险解释：{comprehensive_risk.explanation}
```

这四个字段由 `report_postprocessor` 确定性注入，LLM 不允许自行指定。

### 6.4 禁止事项

- Agent 过程文本（"正在调查""下一步""Coverage""Verifier"）不得进入 Final Report
- `FINAL_REPORT_BEGIN` / `FINAL_REPORT_END` 标记不得出现在报告正文中
- 报告不得包含企业完整工商档案、完整财务数据表、全部舆情列表

---

## 七、Failure Handling

### 7.1 数据不足

| 情况 | 处理方式 |
|------|----------|
| 企业不存在 | 输出 "未找到企业 {company_id}"，终止分析 |
| 某类数据源无数据 | 在报告中标注 "该数据源未返回有效信息"，继续分析 |
| 关联企业调查失败 | 在报告中标注 "关联企业 {id} 调查失败"，继续分析 |
| 财务数据缺失 | 在报告中标注 "财务数据不可用"，不生成财务风险小节 |

### 7.2 禁止行为

| 禁止行为 | 原因 |
|----------|------|
| 编造风险结论 | 违反 Evidence Provenance 原则 |
| 无 Evidence 生成结论 | 每个风险结论必须有 Evidence 支撑 |
| 隐瞒不利证据 | 必须如实呈现所有相关证据 |
| 将未核实信息当事实 | 必须标注核实状态 |
| 将关联企业风险等同于已传导 | 传导需要证据支持 |

### 7.3 降级策略

```
如果 comprehensive_risk 计算失败：
    使用 own_risk.level 作为 risk_level
    在报告中标注 "综合风险融合失败，显示自身风险等级"

如果 report_postprocessor 注入失败：
    使用 LLM 生成的报告（保留占位符）
    在 risk_trace 中标注 "postprocessor 注入失败"
```

---

## 八、Evaluation Criteria

### 8.1 验收企业

| 企业 | 预期 Case | 预期 Level | 验收要点 |
|------|-----------|------------|----------|
| C001 | D | 低风险 | 报告简洁、无大量"未发现"章节、第二章一段话结论 |
| C004 | B | 中风险 | 必须体现 C007 风险来源、传染风险、传导路径 |
| C007 | C | 高风险 | 必须体现自身高风险、孤立风险、5+ 个二级小节 |

### 8.2 验收检查项

| # | 检查项 | 验收标准 |
|---|--------|----------|
| 1 | 第一行 | `# 企业关联风险调查报告` |
| 2 | 无过程文本 | 不包含 "正在调查""下一步""Coverage""Verifier" |
| 3 | 8 章节完整 | 一至八章全部存在 |
| 4 | 二级章节动态 | Case D 无二级小节，Case C 有 5+ 个小节 |
| 5 | 风险等级正确 | comprehensive_risk.level 已注入 |
| 6 | Case 正确 | comprehensive_risk.case 已注入 |
| 7 | Evidence 引用 | 每个风险结论有 Evidence ID |
| 8 | 无占位符 | 不包含 `{risk_level}`、`待填充` |

### 8.3 自动化验收

```bash
# 运行验收测试
python tests/test_comprehensive_risk.py
python tests/test_comprehensive_integration.py
python tests/test_risk_rule_engine.py
```

---

## 九、未来 Skill 封装规划

### 9.1 目标目录结构

```
.opencode/skills/risk-analysis/
├── skill.md                    # Skill 定义文件
├── prompts/
│   ├── investigation.md        # 调查阶段 prompt
│   ├── coverage_check.md       # 覆盖度检查 prompt
│   └── report_generation.md    # 报告生成 prompt
├── templates/
│   └── risk_report_template.md # 报告模板
└── references/
    ├── RISK_REPORT_CONTRACT.md     # 报告契约
    ├── COMPREHENSIVE_RISK_CONTRACT.md  # 融合契约
    └── RISK_ANALYSIS_SKILL_SPEC.md     # 本文件
```

### 9.2 Skill 注册

```json
{
  "name": "risk-analysis",
  "description": "企业关联风险智能调查与报告生成",
  "version": "1.0.0",
  "input_schema": {
    "type": "object",
    "properties": {
      "company_id": {
        "type": "string",
        "description": "企业唯一 ID，如 C001"
      }
    },
    "required": ["company_id"]
  }
}
```

### 9.3 本次不创建

本文件是设计规范，不是实现。真正的 Skill 目录和文件将在后续版本中创建。

---

## 十、变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| 1.0.0 | 2026-09-08 | 初始规范，定义 Skill 定位、输入输出、执行流程、契约引用 |
