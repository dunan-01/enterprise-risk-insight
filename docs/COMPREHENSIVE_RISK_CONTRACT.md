# COMPREHENSIVE_RISK_CONTRACT.md

> V2.4 Comprehensive Risk Fusion — 设计契约  
> 状态：设计阶段（Design Phase）  
> 日期：2026-09-08

---

## 1. 语义边界

### 1.1 own_risk（自身风险）

**定义：** 企业自身的经营、财务、司法风险评估。

**数据来源：** Rule Engine 基于企业自身 evidence 计算：
- B 类（工商）：行政处罚、经营异常、吊销注销
- J 类（司法）：诉讼、被执行、失信被执行、限制消费、股权冻结
- F 类（财务）：审计意见、资产负债率、现金流、连续亏损
- P 类（舆情）：负面舆情（已核实/未核实）
- H 类（招聘）：招聘信号（弱信号）

**语义：** "这家企业自身有多危险？"

**不变量：**
- own_risk.score 仅由企业自身的 evidence 贡献
- 关联企业的 evidence 不会进入 own_risk 计算
- own_risk.level 由 risk_rules.yaml 的硬规则和分数阈值决定

### 1.2 relationship_exposure（传导风险）

**定义：** 因关联企业风险而被动承受的风险暴露。

**数据来源：** Transmission Engine 基于关联企业的 own_risk 和关系图计算：
- 目标企业到关联企业的所有路径（depth ≤ 4）
- 每条路径的传导分数 = own_score × relation_type_factor × target_role_factor × depth_factor
- 同一关联企业取最强路径（strongest_only 策略）
- 最终 exposure.score = max(所有 company_contributions 的 transmitted_score)

**语义：** "这家企业因为关联关系，被动承受了多少风险？"

**不变量：**
- exposure.score 不包含企业自身的风险
- 零风险企业（own_score=0）不会传导任何风险
- exposure.level 使用独立阈值（0-50/51-100/101-150/151+），不复用 own_risk 阈值

### 1.3 comprehensive_risk（综合风险）

**定义：** 融合自身风险和传导风险后的最终企业风险判断。

**数据来源：** Fusion Engine 基于 own_risk + relationship_exposure 计算。

**语义：** "这家企业的整体风险状况如何？"

**关键区别：**
- own_risk 回答："企业自身是否危险？"
- exposure 回答："企业是否因关联关系而危险？"
- comprehensive_risk 回答："企业整体是否危险？（含自身 + 关联）"

---

## 2. 风险模式分类

### 2.1 四种 Case

| Case | 名称 | own_risk | exposure | 语义 | 典型场景 |
|------|------|----------|----------|------|----------|
| A | 双重风险 | high | high | 自身出问题 + 关联也出问题 | 企业经营恶化，且关联企业也在危机中 |
| B | 传染风险 | low | high | 自身健康但被关联企业拖累 | 报表正常，但担保链/股权链传导风险 |
| C | 孤立风险 | high | low | 自身出问题但关联网络清洁 | 企业自身困境，但未波及关联方 |
| D | 低风险 | low | low | 自身健康且关联网络清洁 | 正常经营状态 |

### 2.2 风险优先级

```
Case A > Case B ≥ Case C > Case D
```

**Case B ≥ Case C 的理由：**
- 传染风险（B）的不可控性高于孤立风险（C）
- 企业无法控制关联企业的行为，只能被动承受
- 孤立风险（C）可以通过自身经营改善来缓解
- 实务中，传染风险更容易被低估和忽略

### 2.3 Case 判定规则

```
own_is_high = (own_risk.score >= high_threshold.own_score)

exposure_is_high = 
    (relationship_exposure.score >= high_threshold.exposure_score)
    OR has_risk_transmission_source(relationship_exposure)

has_risk_transmission_source(exposure):
    对于 exposure.company_contributions 中的每个 contribution:
        if contribution.own_score >= high_threshold.own_score
           AND contribution.transmitted_score > 0
        then return True
    return False
```

**high_threshold（默认值）：**
```yaml
high_threshold:
  own_score: 50
  exposure_score: 50
```

**Case 判定矩阵：**

```
                    exposure_is_high
                    false       true
own_is_high  false   D           B
             true    C           A
```

**Case B 判定的特殊规则：**
- 不能仅依赖 exposure_score < 50 就判定 exposure=low
- 必须检查是否存在"风险传染通道"：
  - 传染通道 = 存在关联企业 own_score >= 50 且 transmitted_score > 0
  - 即使传导后分数被衰减到 < 50，通道存在本身就是风险
  - 因为企业无法控制关联企业未来是否恶化

---

## 3. Fusion 公式（V1 方案）

### 3.1 评分公式

```
comprehensive_score = max(own_score, exposure_score) + case_bonus
```

**设计理由：**
- `max()` 确保不因一个维度低而掩盖另一个维度的高风险
- `case_bonus` 反映不同风险模式的额外风险溢价
- 不使用加法（own + exposure），因为两个维度有语义重叠

**case_bonus 值：**

| Case | bonus | 理由 |
|------|-------|------|
| A（双重风险） | +20 | 双重压力，最危险 |
| B（传染风险） | +10 | 不可控的外部风险溢价 |
| C（孤立风险） | +0 | 可通过自身改善缓解 |
| D（低风险） | +0 | 无额外风险 |

### 3.2 等级映射

```
comprehensive_level:
  score >= 150  → 高风险
  score >= 100  → 中高风险
  score >= 50   → 中风险
  score < 50    → 低风险
```

### 3.3 硬规则覆盖

如果 own_risk 包含以下硬规则命中：
- `bankruptcy`（破产）
- `dishonest_execution`（失信被执行）
- `revoked_license`（吊销执照）

则：
```
comprehensive_level = own_risk.level（不降级）
comprehensive_score = own_risk.score（使用 own_risk 分数）
```

**理由：** 这些是致命风险信号，无论关联网络多健康，企业本身已处于极端风险。

---

## 4. 输入字段

### 4.1 必需输入

```typescript
interface ComprehensiveRiskInput {
  // 自身风险
  own_risk: {
    score: number           // 自身风险分 (0-300+)
    level: string           // 低风险 | 中风险 | 中高风险 | 高风险
    hard_rule_hits: string[] // 命中的硬规则 ID 列表
  }

  // 传导风险
  relationship_exposure: {
    score: number           // 传导风险分 (0-150+)
    level: string           // 低风险 | 中风险 | 中高风险 | 高风险
    company_contributions: Array<{
      company_id: string
      company_name: string
      own_score: number     // 关联企业的 own_risk 分数
      transmitted_score: number  // 传导后的分数
      strongest_path: {
        path: string[]
        depth: number
        relation_types: string[]
        target_role: string | null
      } | null
    }>
  }
}
```

### 4.2 可选输入（上下文）

```typescript
interface ComprehensiveRiskContext {
  company_id?: string
  industry?: string
  business_status?: string
  // 未来扩展：行业特定规则、区域因素等
}
```

---

## 5. 输出字段

### 5.1 输出结构

```typescript
interface ComprehensiveRiskOutput {
  // 核心结果
  score: number              // 综合风险分
  level: string              // 低风险 | 中风险 | 中高风险 | 高风险

  // Case 分类
  case: 'A' | 'B' | 'C' | 'D'
  case_label: string         // 双重风险 | 传染风险 | 孤立风险 | 低风险

  // 可解释性
  explanation: string        // 自然语言解释（1-2 句话）

  // 融合追踪
  fusion_trace: {
    own_score: number
    exposure_score: number
    case_bonus: number
    max_component: 'own' | 'exposure'
    formula: string          // 例如 "max(5, 44) + 10 = 54"
    has_hard_rule_override: boolean
  }

  // 元数据
  version: string            // "1.0.0"
  config_hash: string        // comprehensive_risk.yaml 的 hash
}
```

### 5.2 explanation 生成规则

```
Case A: "企业自身风险{own_level}({own_score}分)，且关联企业风险传导{exposure_level}({exposure_score}分)，综合判定为{comprehensive_level}。"
Case B: "企业自身风险{own_level}({own_score}分)，但因关联企业{source_company}({source_own_score}分)的传导，承受{exposure_level}({exposure_score}分)传染风险，综合判定为{comprehensive_level}。"
Case C: "企业自身风险{own_level}({own_score}分)，关联企业风险传导{exposure_level}({exposure_score}分)。风险集中在企业自身经营/财务/司法问题。"
Case D: "企业自身风险{own_level}({own_score}分)，关联企业风险传导{exposure_level}({exposure_score}分)，综合判定为{comprehensive_level}。"
```

---

## 6. 配置文件

### 6.1 config/comprehensive_risk.yaml

```yaml
# V2.4: Comprehensive Risk Fusion 配置
version: "1.0.0"

# 融合策略
fusion_strategy: "max_dominant_with_bonus"

# Case 判定阈值
high_threshold:
  own_score: 50
  exposure_score: 50

# Case bonus 值
case_bonuses:
  A_both_high: 20
  B_low_own_high_exposure: 10
  C_high_own_low_exposure: 0
  D_both_low: 0

# 综合风险等级阈值
comprehensive_levels:
  - min_score: 150
    max_score: 9999
    level: "高风险"
  - min_score: 100
    max_score: 149
    level: "中高风险"
  - min_score: 50
    max_score: 99
    level: "中风险"
  - min_score: 0
    max_score: 49
    level: "低风险"

# 硬规则覆盖
hard_rule_override:
  enabled: true
  rules:
    - "bankruptcy"
    - "dishonest_execution"
    - "revoked_license"
```

---

## 7. 模拟结果

### 7.1 C001

```
输入:
  own_risk:     score=0,   level=低风险, hard_rule_hits=[]
  exposure:     score=0,   level=低风险, contributions=[]

Case 判定:
  own_is_high = (0 >= 50) = false
  exposure_is_high = (0 >= 50) = false
  has_risk_transmission_source = false
  → Case D (低风险)

计算:
  comprehensive_score = max(0, 0) + 0 = 0
  comprehensive_level = 低风险

输出:
  {
    score: 0,
    level: "低风险",
    case: "D",
    case_label: "低风险",
    explanation: "企业自身风险低(0分)，关联企业风险传导低(0分)，综合判定为低风险。",
    fusion_trace: {
      own_score: 0,
      exposure_score: 0,
      case_bonus: 0,
      max_component: "own",
      formula: "max(0, 0) + 0 = 0",
      has_hard_rule_override: false,
    },
  }
```

### 7.2 C004

```
输入:
  own_risk:     score=5,   level=低风险, hard_rule_hits=[]
  exposure:     score=44,  level=低风险, contributions=[
    { company_id: "C007", own_score: 300, transmitted_score: 44 },
  ]

Case 判定:
  own_is_high = (5 >= 50) = false
  exposure_is_high = (44 >= 50) = false
  has_risk_transmission_source:
    C007.own_score=300 >= 50 AND C007.transmitted_score=44 > 0
    → true
  → Case B (传染风险)

计算:
  comprehensive_score = max(5, 44) + 10 = 54
  comprehensive_level = 中风险

输出:
  {
    score: 54,
    level: "中风险",
    case: "B",
    case_label: "传染风险",
    explanation: "企业自身风险低(5分)，但因关联企业鼎峰建设工程有限公司(C007, 300分)的传导，承受44分传染风险，综合判定为中风险。",
    fusion_trace: {
      own_score: 5,
      exposure_score: 44,
      case_bonus: 10,
      max_component: "exposure",
      formula: "max(5, 44) + 10 = 54",
      has_hard_rule_override: false,
    },
  }
```

### 7.3 C007

```
输入:
  own_risk:     score=300, level=高风险, hard_rule_hits=["dishonest_execution", "restrict_consumption"]
  exposure:     score=1,   level=低风险, contributions=[
    { company_id: "C004", own_score: 5, transmitted_score: 1 },
  ]

Case 判定:
  own_is_high = (300 >= 50) = true
  exposure_is_high = (1 >= 50) = false
  has_risk_transmission_source:
    C004.own_score=5 < 50 → false
  → Case C (孤立风险)

硬规则覆盖检查:
  hard_rule_hits 包含 "dishonest_execution" → 触发覆盖
  comprehensive_level = own_risk.level = "高风险"
  comprehensive_score = own_risk.score = 300

输出:
  {
    score: 300,
    level: "高风险",
    case: "C",
    case_label: "孤立风险",
    explanation: "企业自身风险极高(300分，高风险)，关联企业风险传导极低(1分)。风险集中在企业自身经营/财务/司法问题。",
    fusion_trace: {
      own_score: 300,
      exposure_score: 1,
      case_bonus: 0,
      max_component: "own",
      formula: "max(300, 1) + 0 = 300 (hard_rule_override: dishonest_execution)",
      has_hard_rule_override: true,
    },
  }
```

---

## 8. 不变量（Invariants）

### 8.1 语义不变量

1. **I-1:** `comprehensive_risk.score >= own_risk.score`（综合风险不低于自身风险）
2. **I-2:** `comprehensive_risk.score >= relationship_exposure.score`（综合风险不低于传导风险）
3. **I-3:** 如果 `own_risk.hard_rule_hits` 包含致命规则，则 `comprehensive_risk.level == own_risk.level`（硬规则不降级）
4. **I-4:** 如果 `own_risk.score == 0 AND exposure.score == 0`，则 `comprehensive_risk.score == 0`（双零则零）
5. **I-5:** `comprehensive_risk.case` 由 `own_is_high` 和 `exposure_is_high` 唯一确定

### 8.2 数据不变量

1. **I-6:** `comprehensive_risk.fusion_trace.own_score == own_risk.score`
2. **I-7:** `comprehensive_risk.fusion_trace.exposure_score == relationship_exposure.score`
3. **I-8:** `comprehensive_risk.version` 和 `comprehensive_risk.config_hash` 存在且非空

---

## 9. 边界条件

### 9.1 输入为空

```
如果 own_risk 或 relationship_exposure 缺失：
  comprehensive_risk = 非缺失的那个维度（fallback）

如果两者都缺失：
  comprehensive_risk = { score: null, level: null, case: null }
```

### 9.2 分数为负

```
如果 own_score < 0 或 exposure_score < 0：
  视为 0（不产生负的综合分数）
```

### 9.3 超大分数

```
如果 own_score > 1000 或 exposure_score > 1000：
  仍然正常计算，不截断
  comprehensive_level = 高风险（score >= 150）
```

---

## 10. 扩展点（V2.5+）

1. **行业调整因子**：不同行业的 Case bonus 可能不同（例如金融业的传染风险溢价更高）
2. **动态阈值**：high_threshold 可能需要根据宏观经济环境调整
3. **时序分析**：追踪 comprehensive_risk 的变化趋势
4. **网络中心性**：如果企业在关系网络中处于中心位置，传染风险溢价可能更高
5. **预警阈值**：当 comprehensive_risk 接近中风险线时触发预警

---

## 11. 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| 1.0.0 | 2026-09-08 | 初始设计，定义四种 Case、Fusion 公式、输出结构 |
