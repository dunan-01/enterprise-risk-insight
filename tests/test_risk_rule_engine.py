"""
Risk Rule Engine 单元测试。

验证：
1. 相同输入重复运行，风险评分和等级必须一致（确定性）
2. 修改 YAML 权重后，风险评分应随配置变化
3. 同一 Evidence 不得被同一规则重复计分
4. 每一个风险分都可以追溯到规则和 Evidence
5. 硬规则强制提升风险等级
6. 空输入时返回零分低风险
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# 确保 backend/app 在 Python 路径中
BACKEND_APP = Path(__file__).resolve().parents[1] / "backend" / "app"
if str(BACKEND_APP) not in sys.path:
    sys.path.insert(0, str(BACKEND_APP))

from risk_rule_engine import RiskRuleEngine, load_config  # noqa: E402


# ------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------

@pytest.fixture
def default_config():
    """加载默认配置。"""
    return load_config()


@pytest.fixture
def engine(default_config):
    """创建默认引擎实例。"""
    return RiskRuleEngine(default_config)


# ------------------------------------------------------------
# 1. 确定性：相同输入重复运行，结果必须一致
# ----------------------------------------------------------------

class TestDeterminism:
    """验证 Risk Rule Engine 的确定性。"""

    def test_same_input_same_output(self, engine):
        """相同输入多次运行，结果必须完全一致。"""
        facts = [
            {
                "evidence_id": "J008",
                "evidence_type": "judicial",
                "data": {"case_type": "被执行人", "amount": 500000},
            },
            {
                "evidence_id": "B011",
                "evidence_type": "business",
                "data": {"event_type": "经营异常"},
            },
        ]
        extra = {"business_status": "存续"}

        results = [engine.evaluate(facts, extra) for _ in range(5)]

        for i in range(1, len(results)):
            assert results[0]["risk_score"] == results[i]["risk_score"]
            assert results[0]["risk_level"] == results[i]["risk_level"]
            assert results[0]["triggered_rules"] == results[i]["triggered_rules"]

    def test_empty_input(self, engine):
        """空输入返回零分低风险。"""
        result = engine.evaluate([], {})
        assert result["risk_score"] == 0
        assert result["risk_level"] == "低风险"
        assert result["triggered_rules"] == []
        assert result["hard_rule_hits"] == []
        assert result["evidence_ids"] == []

    def test_unknown_evidence_id(self, engine):
        """未知 Evidence ID 不会触发任何规则。"""
        facts = [
            {
                "evidence_id": "X999",
                "evidence_type": "unknown",
                "data": {"some_field": "some_value"},
            },
        ]
        result = engine.evaluate(facts, {})
        assert result["risk_score"] == 0
        assert result["triggered_rules"] == []


# ------------------------------------------------------------
# 2. 规则匹配：正确触发对应规则
# ------------------------------------------------------------

class TestRuleMatching:
    """验证规则匹配逻辑。"""

    def test_judicial_dishonest_execution(self, engine):
        """失信被执行人触发 J001（30分）。"""
        facts = [
            {
                "evidence_id": "J001",
                "evidence_type": "judicial",
                "data": {"case_type": "失信被执行人"},
            },
        ]
        result = engine.evaluate(facts, {})
        assert result["risk_score"] == 30
        assert any(r["rule_id"] == "J001" for r in result["triggered_rules"])

    def test_judicial_executed_person(self, engine):
        """被执行人（非失信）触发 J002（20分）。"""
        facts = [
            {
                "evidence_id": "J002",
                "evidence_type": "judicial",
                "data": {"case_type": "被执行人"},
            },
        ]
        result = engine.evaluate(facts, {})
        assert result["risk_score"] == 20
        assert any(r["rule_id"] == "J002" for r in result["triggered_rules"])

    def test_business_abnormal(self, engine):
        """经营异常触发 B001（20分）。"""
        facts = [
            {
                "evidence_id": "B001",
                "evidence_type": "business",
                "data": {"event_type": "经营异常"},
            },
        ]
        result = engine.evaluate(facts, {})
        assert result["risk_score"] == 20
        assert any(r["rule_id"] == "B001" for r in result["triggered_rules"])

    def test_business_penalty(self, engine):
        """行政处罚触发 B002（15分）。"""
        facts = [
            {
                "evidence_id": "B002",
                "evidence_type": "business",
                "data": {"event_type": "行政处罚", "penalty_amount": 100000},
            },
        ]
        result = engine.evaluate(facts, {})
        assert result["risk_score"] == 15
        assert any(r["rule_id"] == "B002" for r in result["triggered_rules"])

    def test_large_penalty_over_500k(self, engine):
        """大额行政处罚（≥50万）同时触发 B002（15分）和 B003（25分），共40分。"""
        facts = [
            {
                "evidence_id": "B003",
                "evidence_type": "business",
                "data": {"event_type": "行政处罚", "penalty_amount": 600000},
            },
        ]
        result = engine.evaluate(facts, {})
        assert result["risk_score"] == 40  # B002(15) + B003(25)
        rule_ids = [r["rule_id"] for r in result["triggered_rules"]]
        assert "B002" in rule_ids
        assert "B003" in rule_ids

    def test_negative_verified_opinion(self, engine):
        """已核实负面舆情触发 P001（15分）。"""
        facts = [
            {
                "evidence_id": "P001",
                "evidence_type": "public_opinion",
                "data": {"sentiment": "negative", "verification_status": "verified"},
            },
        ]
        result = engine.evaluate(facts, {})
        assert result["risk_score"] == 15
        assert any(r["rule_id"] == "P001" for r in result["triggered_rules"])

    def test_negative_unverified_opinion(self, engine):
        """未经核实负面舆情触发 P002（5分）。"""
        facts = [
            {
                "evidence_id": "P002",
                "evidence_type": "public_opinion",
                "data": {"sentiment": "negative", "verification_status": "unverified"},
            },
        ]
        result = engine.evaluate(facts, {})
        assert result["risk_score"] == 5
        assert any(r["rule_id"] == "P002" for r in result["triggered_rules"])

    def test_guarantee_over_10m(self, engine):
        """大额对外担保（≥1000万）触发 R001（20分）。"""
        facts = [
            {
                "evidence_id": "R001",
                "evidence_type": "relation",
                "data": {"relation_type": "担保", "amount": 15000000},
            },
        ]
        result = engine.evaluate(facts, {})
        assert result["risk_score"] == 20
        assert any(r["rule_id"] == "R001" for r in result["triggered_rules"])

    def test_bankruptcy_case(self, engine):
        """破产案件触发 J007（35分）。"""
        facts = [
            {
                "evidence_id": "J007",
                "evidence_type": "judicial",
                "data": {"case_type": "破产案件"},
            },
        ]
        result = engine.evaluate(facts, {})
        assert result["risk_score"] == 35
        assert any(r["rule_id"] == "J007" for r in result["triggered_rules"])


# ------------------------------------------------------------
# 3. 去重：同一 Evidence + 同一 Rule 只计分一次
# ------------------------------------------------------------

class TestDeduplication:
    """验证去重逻辑。"""

    def test_same_evidence_same_rule_no_double_count(self, engine):
        """同一 Evidence + 同一 Rule 只计分一次。"""
        facts = [
            {
                "evidence_id": "J001",
                "evidence_type": "judicial",
                "data": {"case_type": "失信被执行人"},
            },
            {
                "evidence_id": "J001",  # 重复的 Evidence ID
                "evidence_type": "judicial",
                "data": {"case_type": "失信被执行人"},
            },
        ]
        result = engine.evaluate(facts, {})
        # 只应计分一次（30分），而不是两次（60分）
        assert result["risk_score"] == 30
        j001_rules = [r for r in result["triggered_rules"] if r["rule_id"] == "J001"]
        assert len(j001_rules) == 1

    def test_different_evidence_same_rule_both_count(self, engine):
        """不同 Evidence 匹配同一 Rule 时，分别计分。"""
        facts = [
            {
                "evidence_id": "J001",
                "evidence_type": "judicial",
                "data": {"case_type": "失信被执行人"},
            },
            {
                "evidence_id": "J002",
                "evidence_type": "judicial",
                "data": {"case_type": "失信被执行人"},  # 也是失信
            },
        ]
        result = engine.evaluate(facts, {})
        # 两个不同 Evidence 都触发 J001，各计 30 分
        assert result["risk_score"] == 60
        j001_rules = [r for r in result["triggered_rules"] if r["rule_id"] == "J001"]
        assert len(j001_rules) == 2

    def test_same_evidence_different_rules_both_count(self, engine):
        """同一 Evidence 匹配不同 Rule 时，分别计分。"""
        facts = [
            {
                "evidence_id": "B003",
                "evidence_type": "business",
                "data": {"event_type": "行政处罚", "penalty_amount": 600000},
            },
        ]
        result = engine.evaluate(facts, {})
        # B003 同时匹配 B002（行政处罚 15分）和 B003（大额行政处罚 25分）
        assert result["risk_score"] == 40
        rule_ids = [r["rule_id"] for r in result["triggered_rules"]]
        assert "B002" in rule_ids
        assert "B003" in rule_ids


# ------------------------------------------------------------
# 4. 维度得分计算
# ------------------------------------------------------------

class TestDimensionScores:
    """验证维度得分计算。"""

    def test_single_dimension(self, engine):
        """单维度事实，维度得分是加权贡献（非独立和）。"""
        facts = [
            {
                "evidence_id": "J001",
                "evidence_type": "judicial",
                "data": {"case_type": "失信被执行人"},
            },
        ]
        result = engine.evaluate(facts, {})
        # 司法维度得分 > 0
        assert result["dimension_scores"]["judicial"] > 0
        # 其他维度得分 = 0（没有对应规则触发）
        assert result["dimension_scores"]["business"] == 0
        assert result["dimension_scores"]["relationship"] == 0
        assert result["dimension_scores"]["public_opinion"] == 0
        assert result["dimension_scores"]["financial"] == 0
        assert result["dimension_scores"]["recruitment"] == 0

    def test_multi_dimension(self, engine):
        """多维度事实影响多个维度得分。"""
        facts = [
            {
                "evidence_id": "J001",
                "evidence_type": "judicial",
                "data": {"case_type": "失信被执行人"},
            },
            {
                "evidence_id": "B001",
                "evidence_type": "business",
                "data": {"event_type": "经营异常"},
            },
        ]
        result = engine.evaluate(facts, {})
        assert result["dimension_scores"]["judicial"] > 0
        assert result["dimension_scores"]["business"] > 0


# ------------------------------------------------------------
# 5. 硬规则：强制提升风险等级
# ------------------------------------------------------------

class TestHardRules:
    """验证硬规则逻辑。"""

    def test_bankruptcy_forces_high_risk(self, engine):
        """破产案件硬规则强制提升到高风险。"""
        facts = [
            {
                "evidence_id": "J007",
                "evidence_type": "judicial",
                "data": {"case_type": "破产案件"},
            },
        ]
        extra = {"has_bankruptcy_case": True}
        result = engine.evaluate(facts, extra)
        assert result["risk_level"] == "高风险"
        assert len(result["hard_rule_hits"]) > 0
        assert result["hard_rule_hits"][0]["rule_id"] == "HR001"

    def test_dishonest_execution_forces_high_risk(self, engine):
        """失信被执行人硬规则强制提升到高风险。"""
        facts = []
        extra = {"has_dishonest_execution": True}
        result = engine.evaluate(facts, extra)
        assert result["risk_level"] == "高风险"
        assert any(h["rule_id"] == "HR002" for h in result["hard_rule_hits"])

    def test_revoked_license_forces_high_risk(self, engine):
        """吊销营业执照硬规则强制提升到高风险。"""
        facts = []
        extra = {"business_status": "吊销"}
        result = engine.evaluate(facts, extra)
        assert result["risk_level"] == "高风险"
        assert any(h["rule_id"] == "HR003" for h in result["hard_rule_hits"])

    def test_high_debt_ratio_forces_high_risk(self, engine):
        """资产负债率>95%硬规则强制提升到高风险。"""
        facts = []
        extra = {"debt_ratio": 0.96}
        result = engine.evaluate(facts, extra)
        assert result["risk_level"] == "高风险"
        assert any(h["rule_id"] == "HR004" for h in result["hard_rule_hits"])

    def test_hard_rule_overrides_score_based_level(self, engine):
        """硬规则优先级高于基于分数的等级。"""
        # P002 触发（5分），正常应该是低风险
        facts = [
            {
                "evidence_id": "P002",
                "evidence_type": "public_opinion",
                "data": {"sentiment": "negative", "verification_status": "unverified"},
            },
        ]
        extra = {"has_bankruptcy_case": True}
        result = engine.evaluate(facts, extra)
        # 正常 5 分应该是低风险，但硬规则强制为高风险
        assert result["risk_level"] == "高风险"
        assert result["risk_score"] == 5  # 分数仍然是 5

    def test_no_hard_rule_score_based_level(self, engine):
        """无硬规则触发时，等级由分数决定。"""
        facts = [
            {
                "evidence_id": "J001",
                "evidence_type": "judicial",
                "data": {"case_type": "失信被执行人"},
            },
        ]
        result = engine.evaluate(facts, {})
        # 30 分应该在中高风险区间（51-75）以下
        # 根据配置：低风险 0-25，中风险 26-50，中高风险 51-75，高风险 76+
        assert result["risk_level"] == "中风险"
        assert result["hard_rule_hits"] == []


# ------------------------------------------------------------
# 6. 风险等级阈值
# ------------------------------------------------------------

class TestRiskLevels:
    """验证风险等级阈值。"""

    def test_low_risk(self, engine):
        """低分→低风险。"""
        facts = [
            {
                "evidence_id": "P002",
                "evidence_type": "public_opinion",
                "data": {"sentiment": "negative", "verification_status": "unverified"},
            },
        ]
        result = engine.evaluate(facts, {})
        assert result["risk_score"] == 5
        assert result["risk_level"] == "低风险"

    def test_medium_risk(self, engine):
        """中等分数→中风险。"""
        facts = [
            {
                "evidence_id": "J001",
                "evidence_type": "judicial",
                "data": {"case_type": "失信被执行人"},
            },
            {
                "evidence_id": "B001",
                "evidence_type": "business",
                "data": {"event_type": "经营异常"},
            },
        ]
        result = engine.evaluate(facts, {})
        # 30 + 20 = 50 分，应该在中风险区间
        assert result["risk_score"] == 50
        assert result["risk_level"] == "中风险"

    def test_high_medium_risk(self, engine):
        """较高分数→中高风险。"""
        facts = [
            {
                "evidence_id": "J001",
                "evidence_type": "judicial",
                "data": {"case_type": "失信被执行人"},
            },
            {
                "evidence_id": "J002",
                "evidence_type": "judicial",
                "data": {"case_type": "被执行人"},
            },
            {
                "evidence_id": "B001",
                "evidence_type": "business",
                "data": {"event_type": "经营异常"},
            },
        ]
        result = engine.evaluate(facts, {})
        # 30 + 20 + 20 = 70 分，应该在中高风险区间
        assert result["risk_score"] == 70
        assert result["risk_level"] == "中高风险"

    def test_high_risk(self, engine):
        """高分→高风险。"""
        facts = [
            {
                "evidence_id": "J001",
                "evidence_type": "judicial",
                "data": {"case_type": "失信被执行人"},
            },
            {
                "evidence_id": "J002",
                "evidence_type": "judicial",
                "data": {"case_type": "被执行人"},
            },
            {
                "evidence_id": "J003",
                "evidence_type": "judicial",
                "data": {"case_type": "限制消费令"},
            },
            {
                "evidence_id": "B001",
                "evidence_type": "business",
                "data": {"event_type": "经营异常"},
            },
            {
                "evidence_id": "P001",
                "evidence_type": "public_opinion",
                "data": {"sentiment": "negative", "verification_status": "verified"},
            },
        ]
        result = engine.evaluate(facts, {})
        # 30 + 20 + 25 + 20 + 15 = 110 分，应该在高风险区间
        assert result["risk_score"] == 110
        assert result["risk_level"] == "高风险"


# ------------------------------------------------------------
# 7. Extra 上下文条件
# ------------------------------------------------------------

class TestExtraContext:
    """验证 extra 上下文条件求值。"""

    def test_financial_indicators(self, engine):
        """财务指标通过 extra 注入，需要 Fxxx evidence 触发。"""
        facts = [
            {
                "evidence_id": "F001",
                "evidence_type": "financial",
                "data": {"audit_opinion": "unqualified"},
            },
        ]
        extra = {"debt_ratio": 0.75, "consecutive_loss_years": 3}
        result = engine.evaluate(facts, extra)
        # F001 触发（15分）+ F003 触发（20分）; F005 不触发（unqualified = 正常）
        assert result["risk_score"] == 35
        rule_ids = [r["rule_id"] for r in result["triggered_rules"]]
        assert "F001" in rule_ids
        assert "F003" in rule_ids
        assert "F005" not in rule_ids

    def test_recruitment_count(self, engine):
        """招聘信息数量通过 extra 注入，需要 Hxxx evidence 触发。"""
        facts = [
            {
                "evidence_id": "H001",
                "evidence_type": "recruitment",
                "data": {},
            },
        ]
        extra = {"recruitment_count": 0}
        result = engine.evaluate(facts, extra)
        # H001 触发（5分）
        assert result["risk_score"] == 5
        assert any(r["rule_id"] == "H001" for r in result["triggered_rules"])


# ------------------------------------------------------------
# 8. 可追溯性
# ------------------------------------------------------------

class TestTraceability:
    """验证评分可追溯到规则和 Evidence。"""

    def test_each_score_traceable_to_rule_and_evidence(self, engine):
        """每个触发的规则都包含 rule_id 和 evidence_id。"""
        facts = [
            {
                "evidence_id": "J001",
                "evidence_type": "judicial",
                "data": {"case_type": "失信被执行人"},
            },
            {
                "evidence_id": "B001",
                "evidence_type": "business",
                "data": {"event_type": "经营异常"},
            },
            {
                "evidence_id": "P001",
                "evidence_type": "public_opinion",
                "data": {"sentiment": "negative", "verification_status": "verified"},
            },
        ]
        result = engine.evaluate(facts, {})

        for rule in result["triggered_rules"]:
            assert "rule_id" in rule
            assert "evidence_id" in rule
            assert "score" in rule
            assert "dimension" in rule
            assert "description" in rule
            # 分数必须为正整数
            assert isinstance(rule["score"], int)
            assert rule["score"] > 0

    def test_evidence_ids_match_triggered_rules(self, engine):
        """evidence_ids 列表与 triggered_rules 中的 evidence_id 一致。"""
        facts = [
            {
                "evidence_id": "J001",
                "evidence_type": "judicial",
                "data": {"case_type": "失信被执行人"},
            },
            {
                "evidence_id": "B001",
                "evidence_type": "business",
                "data": {"event_type": "经营异常"},
            },
        ]
        result = engine.evaluate(facts, {})
        triggered_eids = set(r["evidence_id"] for r in result["triggered_rules"])
        result_eids = set(result["evidence_ids"])
        assert triggered_eids == result_eids

    def test_total_score_equals_sum_of_rule_scores(self, engine):
        """总分等于所有触发规则分数之和。"""
        facts = [
            {
                "evidence_id": "J001",
                "evidence_type": "judicial",
                "data": {"case_type": "失信被执行人"},
            },
            {
                "evidence_id": "B001",
                "evidence_type": "business",
                "data": {"event_type": "经营异常"},
            },
            {
                "evidence_id": "P001",
                "evidence_type": "public_opinion",
                "data": {"sentiment": "negative", "verification_status": "verified"},
            },
        ]
        result = engine.evaluate(facts, {})
        expected_score = sum(r["score"] for r in result["triggered_rules"])
        assert result["risk_score"] == expected_score


# ------------------------------------------------------------
# 9. 配置变化影响评分
# ------------------------------------------------------------

class TestConfigDriven:
    """验证配置变化对评分的影响。"""

    def test_changing_weights_changes_dimension_scores(self):
        """修改权重后，维度得分应随之变化。"""
        config = load_config()

        # 引擎 1：原始权重
        engine1 = RiskRuleEngine(config)

        # 引擎 2：修改权重（司法权重翻倍）
        config2 = {**config}
        config2["dimension_weights"] = {**config["dimension_weights"], "judicial": 60}
        engine2 = RiskRuleEngine(config2)

        facts = [
            {
                "evidence_id": "J001",
                "evidence_type": "judicial",
                "data": {"case_type": "失信被执行人"},
            },
            {
                "evidence_id": "B001",
                "evidence_type": "business",
                "data": {"event_type": "经营异常"},
            },
        ]

        r1 = engine1.evaluate(facts, {})
        r2 = engine2.evaluate(facts, {})

        # 总分不变（规则分数相同）
        assert r1["risk_score"] == r2["risk_score"]

        # 但维度得分不同（权重变了）
        assert r1["dimension_scores"]["judicial"] != r2["dimension_scores"]["judicial"]

    def test_changing_rule_score_changes_total(self):
        """修改规则分数后，总分应随之变化。"""
        config = load_config()

        # 修改 J001 的分数从 30 改为 50
        for rule in config["rules"]:
            if rule["id"] == "J001":
                rule["score"] = 50
                break

        engine = RiskRuleEngine(config)

        facts = [
            {
                "evidence_id": "J001",
                "evidence_type": "judicial",
                "data": {"case_type": "失信被执行人"},
            },
        ]
        result = engine.evaluate(facts, {})
        assert result["risk_score"] == 50


# ------------------------------------------------------------
# 10. 边界情况
# ------------------------------------------------------------

class TestEdgeCases:
    """验证边界情况。"""

    def test_invalid_condition_graceful(self, engine):
        """无效条件不会导致崩溃。"""
        facts = [
            {
                "evidence_id": "J999",
                "evidence_type": "judicial",
                "data": {"case_type": None},
            },
        ]
        result = engine.evaluate(facts, {})
        # 不应崩溃，只是不触发规则
        assert isinstance(result["risk_score"], int)

    def test_missing_data_field(self, engine):
        """缺少数据字段时规则不触发。"""
        facts = [
            {
                "evidence_id": "J001",
                "evidence_type": "judicial",
                "data": {},  # 空数据
            },
        ]
        result = engine.evaluate(facts, {})
        # case_type 为 None，不匹配任何规则
        assert result["risk_score"] == 0

    def test_extra_none_treated_as_empty(self, engine):
        """extra 为 None 时视为空 dict。"""
        facts = []
        result = engine.evaluate(facts, None)
        assert result["risk_score"] == 0
        assert result["risk_level"] == "低风险"


# ------------------------------------------------------------
# 11. Report Post-Processing: 风险等级注入
# ------------------------------------------------------------

class TestReportInjection:
    """验证 _inject_risk_level_into_report 确定性注入。"""

    def _get_inject_fn(self):
        """获取注入函数。"""
        from report_postprocessor import inject_risk_level_into_report
        return inject_risk_level_into_report

    def test_replace_existing_risk_level(self, engine):
        """替换报告中已存在的综合风险等级。"""
        inject = self._get_inject_fn()
        report = """## 六、综合风险判断

综合风险等级：中风险

核心判断：
目标企业存在若干风险信号。"""
        result = inject(report, "高风险", 82)
        assert "综合风险等级：高风险" in result
        assert "风险评分：82" in result
        assert "中风险" not in result

    def test_replace_placeholder(self, engine):
        """替换模板占位符。"""
        inject = self._get_inject_fn()
        report = """## 六、综合风险判断

综合风险等级：{risk_level}

核心判断：
目标企业存在若干风险信号。"""
        result = inject(report, "高风险", 82)
        assert "综合风险等级：高风险" in result
        assert "{risk_level}" not in result

    def test_replace_engine_placeholder(self, engine):
        """替换 Rule Engine 占位符文本。"""
        inject = self._get_inject_fn()
        report = """## 六、综合风险判断

综合风险等级：（由 Risk Rule Engine 自动计算）

核心判断：
目标企业存在若干风险信号。"""
        result = inject(report, "高风险", 82)
        assert "综合风险等级：高风险" in result
        assert "由 Risk Rule Engine 自动计算" not in result

    def test_insert_when_missing(self, engine):
        """章节存在但没有风险等级字段时，插入。"""
        inject = self._get_inject_fn()
        report = """## 六、综合风险判断

核心判断：
目标企业存在若干风险信号。

主要关注事项：
1. 司法风险"""
        result = inject(report, "高风险", 82)
        assert "综合风险等级：高风险" in result
        assert "风险评分：82" in result
        # 核心判断仍在
        assert "核心判断：" in result

    def test_insert_score_after_existing_level(self, engine):
        """已有风险等级但没有评分时，插入评分。"""
        inject = self._get_inject_fn()
        report = """## 六、综合风险判断

综合风险等级：高风险

核心判断：
目标企业存在若干风险信号。"""
        result = inject(report, "高风险", 82)
        assert "综合风险等级：高风险" in result
        assert "风险评分：82" in result

    def test_no_placeholders_in_output(self, engine):
        """最终报告中不应有任何占位符。"""
        inject = self._get_inject_fn()
        report = """## 一、风险结论摘要

综合风险等级：{risk_level}

## 六、综合风险判断

综合风险等级：（由 Risk Rule Engine 自动计算）

核心判断：测试"""
        result = inject(report, "中风险", 45)
        assert "{risk_level}" not in result
        assert "由 Risk Rule Engine 自动计算" not in result
        assert "{{risk_level}}" not in result
        assert "待计算" not in result
        assert "待填充" not in result

    def test_inject_preserves_other_content(self, engine):
        """注入不破坏报告其他内容。"""
        inject = self._get_inject_fn()
        report = """# 企业关联风险调查报告

## 一、风险结论摘要

综合风险等级：低风险

风险结论：
企业整体风险可控。

---

## 六、综合风险判断

综合风险等级：低风险

核心判断：
目标企业经营稳定。

---

## 七、证据限制与不确定性
"""
        result = inject(report, "高风险", 82)
        # 风险等级被替换
        assert "综合风险等级：高风险" in result
        # 其他内容保留
        assert "# 企业关联风险调查报告" in result
        assert "风险结论：" in result
        assert "核心判断：" in result
        assert "## 七、证据限制与不确定性" in result


# ============================================================
# 8. 持久化回归测试：_save_run_records 保存注入后的报告
# ----------------------------------------------------------------

class TestReportPersistence:
    """验证 _save_run_records 保存的是注入后的报告，而非 harness 原始报告。"""

    def test_save_run_records_persists_injected_report(self, tmp_path):
        """_save_run_records 应使用 response['report']（含注入）而非 harness_result['report']。"""
        import json
        import sys
        from unittest.mock import patch

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
        import app.analysis_service as svc

        # 模拟 harness 原始报告（含占位符）
        raw_report = """# 企业关联风险调查报告

## 一、风险结论摘要

综合风险等级：（由 Risk Rule Engine 自动计算）

风险结论：测试。

---

## 六、综合风险判断

综合风险等级：（由 Risk Rule Engine 自动计算）

核心判断：测试。

---
"""

        # 模拟注入后的报告
        injected_report = raw_report.replace(
            "（由 Risk Rule Engine 自动计算）", "高风险"
        )
        injected_report = injected_report + "\n\n风险评分：450\n"

        # 构造 response（模拟 analyze_company 的返回值）
        response = {
            "task_id": "test-persistence-001",
            "company_id": "C999",
            "status": "completed",
            "report": injected_report,  # ← 注入后的报告
            "verification_status": "PASS",
            "risk_level": "高风险",
            "evidence_ids": ["J001"],
            "related_companies": [],
            "risk_scoring": {
                "risk_score": 450,
                "risk_level": "高风险",
                "triggered_rules": [],
                "hard_rule_hits": [],
                "dimension_scores": {},
                "evidence_ids": ["J001"],
                "total_evidence_count": 1,
            },
        }

        harness_result = {
            "report": raw_report,  # ← 原始 harness 报告（含占位符）
            "verification_status": "PASS",
            "process_text": "",
            "raw_events": [],
            "duration_seconds": 10.0,
        }

        # 创建 task_dir（在 tmp_path 下）
        task_dir = tmp_path / "task-test-001"
        task_dir.mkdir()

        # Patch PROJECT_ROOT to tmp_path so relative_to works
        with patch.object(svc, "PROJECT_ROOT", tmp_path):
            svc._save_run_records(
                company_id="C999",
                harness_result=harness_result,
                response=response,
                task_id="test-persistence-001",
                task_dir=task_dir,
            )

        # 读取磁盘上的 report_final.md
        disk_report = (task_dir / "report_final.md").read_text(encoding="utf-8")

        # 验证：磁盘报告必须包含注入后的风险等级，不含占位符
        assert "综合风险等级：高风险" in disk_report, (
            f"磁盘 report_final.md 未包含注入后的风险等级。"
            f"内容前200字: {disk_report[:200]}"
        )
        assert "风险评分：450" in disk_report, (
            f"磁盘 report_final.md 未包含注入后的风险评分。"
        )
        assert "（由 Risk Rule Engine 自动计算）" not in disk_report, (
            "磁盘 report_final.md 仍包含占位符！"
        )

    def test_save_run_records_response_matches_disk(self, tmp_path):
        """response['report'] 和磁盘 report_final.md 必须一致。"""
        import sys
        from unittest.mock import patch

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
        import app.analysis_service as svc

        injected_report = "# 报告\n\n## 六、综合风险判断\n\n综合风险等级：中风险\n\n风险评分：35\n"

        response = {
            "task_id": "test-002",
            "company_id": "C888",
            "status": "completed",
            "report": injected_report,
            "verification_status": "PASS",
            "risk_level": "中风险",
            "evidence_ids": [],
            "related_companies": [],
            "risk_scoring": None,
        }

        harness_result = {
            "report": "# 报告\n\n## 六、综合风险判断\n\n综合风险等级：（由 Risk Rule Engine 自动计算）\n",
            "verification_status": "PASS",
            "process_text": "",
            "raw_events": [],
            "duration_seconds": 5.0,
        }

        task_dir = tmp_path / "task-002"
        task_dir.mkdir()

        with patch.object(svc, "PROJECT_ROOT", tmp_path):
            svc._save_run_records(
                company_id="C888",
                harness_result=harness_result,
                response=response,
                task_id="test-002",
                task_dir=task_dir,
            )

        disk_report = (task_dir / "report_final.md").read_text(encoding="utf-8")
        # 核心内容必须一致（允许尾部换行差异）
        assert disk_report.strip() == injected_report.strip(), (
            f"磁盘报告与 response['report'] 不一致。\n"
            f"Expected: {injected_report.strip()[:200]}\n"
            f"Got: {disk_report.strip()[:200]}"
        )
        # 关键字段必须存在
        assert "综合风险等级：中风险" in disk_report
        assert "风险评分：35" in disk_report
        assert "（由 Risk Rule Engine 自动计算）" not in disk_report


# ============================================================
# 9. V2.3A: Company-Level 规则不再重复计分
# ----------------------------------------------------------------

class TestCompanyLevelDedup:
    """验证 company-level 规则（使用 extra）每个 owner_company_id 只触发一次。"""

    def test_financial_trend_rules_once_per_company(self, engine):
        """F001/F003/F004 等 company-level 规则不应因多条 F evidence 重复触发。"""
        # 模拟 3 条 F evidence 属于同一关联公司
        evidence_facts = [
            {
                "evidence_id": "F019",
                "evidence_type": "financial",
                "data": {"audit_opinion": "保留意见", "period": "2023FY"},
                "company_id": "C006",
                "owner_company_id": "C006",
                "target_company_id": "C007",
                "is_target_company": False,
                "relation_depth": 1,
                "relation_path": ["C007", "C006"],
                "relation_ids": ["R007"],
                "relation_types": ["对外投资"],
                "target_role_in_relation": "investee",
            },
            {
                "evidence_id": "F020",
                "evidence_type": "financial",
                "data": {"audit_opinion": "保留意见", "period": "2024FY"},
                "company_id": "C006",
                "owner_company_id": "C006",
                "target_company_id": "C007",
                "is_target_company": False,
                "relation_depth": 1,
                "relation_path": ["C007", "C006"],
                "relation_ids": ["R007"],
                "relation_types": ["对外投资"],
                "target_role_in_relation": "investee",
            },
            {
                "evidence_id": "F021",
                "evidence_type": "financial",
                "data": {"audit_opinion": "保留意见", "period": "2025FY"},
                "company_id": "C006",
                "owner_company_id": "C006",
                "target_company_id": "C007",
                "is_target_company": False,
                "relation_depth": 1,
                "relation_path": ["C007", "C006"],
                "relation_ids": ["R007"],
                "relation_types": ["对外投资"],
                "target_role_in_relation": "investee",
            },
        ]

        extra = {
            "debt_ratio": 0.85,
            "consecutive_loss_years": 3,
            "latest_operating_cash_flow": -500000,
            "recruitment_count": 0,
        }

        result = engine.evaluate(evidence_facts, extra)

        # V2.3B.1: relationship_exposure 改为 NOT_CALIBRATED
        rel = result["relationship_exposure"]
        assert rel["status"] == "NOT_CALIBRATED"
        assert rel["score"] is None

        # F001/F003/F004 是 company-level，C006 不是目标企业，不应触发
        all_rules = result["own_risk"]["triggered_rules"]
        f001_hits = [r for r in all_rules if r["rule_id"] == "F001"]
        f003_hits = [r for r in all_rules if r["rule_id"] == "F003"]
        f004_hits = [r for r in all_rules if r["rule_id"] == "F004"]
        assert len(f001_hits) == 0, f"F001 不应对非目标企业触发，实际 {len(f001_hits)}"
        assert len(f003_hits) == 0, f"F003 不应对非目标企业触发，实际 {len(f003_hits)}"
        assert len(f004_hits) == 0, f"F004 不应对非目标企业触发，实际 {len(f004_hits)}"

        # own_risk 分数 = 0（C006 非目标企业，所有 evidence 都不是 own）
        assert result["own_risk"]["score"] == 0

    def test_company_level_rules_once_for_target(self, engine):
        """company-level 规则对目标企业自身只触发一次。"""
        evidence_facts = [
            {
                "evidence_id": "F001",
                "evidence_type": "financial",
                "data": {"audit_opinion": "保留意见", "period": "2023FY"},
                "company_id": "C001",
                "owner_company_id": "C001",
                "target_company_id": "C001",
                "is_target_company": True,
                "relation_depth": 0,
                "relation_path": ["C001"],
                "relation_ids": [],
                "relation_types": [],
                "target_role_in_relation": None,
            },
            {
                "evidence_id": "F002",
                "evidence_type": "financial",
                "data": {"audit_opinion": "保留意见", "period": "2024FY"},
                "company_id": "C001",
                "owner_company_id": "C001",
                "target_company_id": "C001",
                "is_target_company": True,
                "relation_depth": 0,
                "relation_path": ["C001"],
                "relation_ids": [],
                "relation_types": [],
                "target_role_in_relation": None,
            },
            {
                "evidence_id": "F003",
                "evidence_type": "financial",
                "data": {"audit_opinion": "保留意见", "period": "2025FY"},
                "company_id": "C001",
                "owner_company_id": "C001",
                "target_company_id": "C001",
                "is_target_company": True,
                "relation_depth": 0,
                "relation_path": ["C001"],
                "relation_ids": [],
                "relation_types": [],
                "target_role_in_relation": None,
            },
        ]

        extra = {
            "debt_ratio": 0.85,
            "consecutive_loss_years": 3,
            "latest_operating_cash_flow": -500000,
            "recruitment_count": 0,
        }

        result = engine.evaluate(evidence_facts, extra)

        # F001/F003/F004 是 company-level，每个只触发一次
        f001_hits = [r for r in result["triggered_rules"] if r["rule_id"] == "F001"]
        f003_hits = [r for r in result["triggered_rules"] if r["rule_id"] == "F003"]
        f004_hits = [r for r in result["triggered_rules"] if r["rule_id"] == "F004"]
        assert len(f001_hits) == 1, f"F001 应触发 1 次，实际 {len(f001_hits)}"
        assert len(f003_hits) == 1, f"F003 应触发 1 次，实际 {len(f003_hits)}"
        assert len(f004_hits) == 1, f"F004 应触发 1 次，实际 {len(f004_hits)}"

        # 每条有 supporting_evidence_ids
        assert len(f001_hits[0].get("supporting_evidence_ids", [])) == 3
        assert f001_hits[0]["hit_count"] == 1

    def test_recruitment_weak_signal_no_accumulation(self, engine):
        """H001/H002 是 company-level，不会因多条 H evidence 重复触发。"""
        # H001 检查 extra.recruitment_count，需要至少一条 H evidence 激活类型过滤
        evidence_facts = [
            {
                "evidence_id": "H001",
                "evidence_type": "recruitment",
                "data": {"position_type": "技术", "position_name": "Python开发", "planned_count": 0, "status": "暂停"},
                "company_id": "C001",
                "owner_company_id": "C001",
                "target_company_id": "C001",
                "is_target_company": True,
                "relation_depth": 0,
                "relation_path": ["C001"],
                "relation_ids": [],
                "relation_types": [],
                "target_role_in_relation": None,
            },
        ]
        extra = {"recruitment_count": 0}

        result = engine.evaluate(evidence_facts, extra)

        h001_hits = [r for r in result["triggered_rules"] if r["rule_id"] == "H001"]
        assert len(h001_hits) == 1, f"H001 应触发 1 次，实际 {len(h001_hits)}"
        assert h001_hits[0]["score"] == 5

    def test_multiple_opinions_accumulate_but_capped_by_rule(self, engine):
        """P001/P002 是 evidence-level，每条独立计分（无 cap，但这是设计意图）。"""
        evidence_facts = [
            {
                "evidence_id": f"P{i:03d}",
                "evidence_type": "public_opinion",
                "data": {"sentiment": "negative", "verification_status": "unverified"},
                "company_id": "C001",
                "owner_company_id": "C001",
                "target_company_id": "C001",
                "is_target_company": True,
                "relation_depth": 0,
                "relation_path": ["C001"],
                "relation_ids": [],
                "relation_types": [],
                "target_role_in_relation": None,
            }
            for i in range(1, 6)  # 5 条未经核实负面舆情
        ]

        result = engine.evaluate(evidence_facts, {})

        p002_hits = [r for r in result["triggered_rules"] if r["rule_id"] == "P002"]
        assert len(p002_hits) == 5, f"P002 应触发 5 次，实际 {len(p002_hits)}"
        # 每条 5 分，共 25 分
        assert result["risk_score"] == 25

    def test_judicial_events_as_separate_risk_events(self, engine):
        """不同的司法案件应允许作为不同风险事件计分。"""
        evidence_facts = [
            {
                "evidence_id": "J001",
                "evidence_type": "judicial",
                "data": {"case_type": "被执行人", "role": "被告", "amount": 6000000},
                "company_id": "C001",
                "owner_company_id": "C001",
                "target_company_id": "C001",
                "is_target_company": True,
                "relation_depth": 0,
                "relation_path": ["C001"],
                "relation_ids": [],
                "relation_types": [],
                "target_role_in_relation": None,
            },
            {
                "evidence_id": "J002",
                "evidence_type": "judicial",
                "data": {"case_type": "限制消费令", "role": "被告", "amount": 6000000},
                "company_id": "C001",
                "owner_company_id": "C001",
                "target_company_id": "C001",
                "is_target_company": True,
                "relation_depth": 0,
                "relation_path": ["C001"],
                "relation_ids": [],
                "relation_types": [],
                "target_role_in_relation": None,
            },
        ]

        result = engine.evaluate(evidence_facts, {})

        # J001 (被执行人) + J006 (大额诉讼≥500万) = 20+15 = 35
        # J002 (限制消费令) + J006 (大额诉讼≥500万) = 25+15 = 40
        # 总分 = 75
        assert result["risk_score"] == 75

    def test_provenance_not_broken_by_calibration(self, engine):
        """V2.3A 校准不破坏 Evidence Provenance。"""
        evidence_facts = [
            {
                "evidence_id": "J001",
                "evidence_type": "judicial",
                "data": {"case_type": "被执行人"},
                "company_id": "C002",
                "owner_company_id": "C002",
                "target_company_id": "C001",
                "is_target_company": False,
                "relation_depth": 1,
                "relation_path": ["C001", "C002"],
                "relation_ids": ["R001"],
                "relation_types": ["股权"],
                "target_role_in_relation": "shareholder",
            },
        ]

        result = engine.evaluate(evidence_facts, {})

        # V2.3B.1: relationship_exposure 改为 NOT_CALIBRATED
        assert result["own_risk"]["score"] == 0
        rel = result["relationship_exposure"]
        assert rel["status"] == "NOT_CALIBRATED"
        assert rel["score"] is None


# ============================================================
# V2.3A.1: F005 审计意见 canonical value 修复测试
# ============================================================
class TestF005AuditOpinionNormalization:
    """V2.3A.1: F005 使用 canonical English values 判断审计意见。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.engine = RiskRuleEngine(load_config())
        self.base_facts = [
            {
                "evidence_id": "F001",
                "evidence_type": "financial",
                "data": {},
                "company_id": "C001",
                "owner_company_id": "C001",
                "target_company_id": "C001",
                "is_target_company": True,
                "relation_depth": 0,
                "relation_path": ["C001"],
                "relation_ids": [],
                "relation_types": [],
                "target_role_in_relation": None,
            },
        ]

    def _make_facts(self, opinion):
        facts = list(self.base_facts)
        facts[0] = dict(facts[0])
        facts[0]["data"] = {"audit_opinion": opinion}
        return facts

    def test_unqualified_no_trigger(self):
        """unqualified → F005 不触发。"""
        result = self.engine.evaluate(self._make_facts("unqualified"), {})
        f005 = [r for r in result["triggered_rules"] if r["rule_id"] == "F005"]
        assert len(f005) == 0, f"unqualified 不应触发 F005, 实际 {len(f005)}"

    def test_qualified_triggers(self):
        """qualified → F005 触发（score=20）。"""
        result = self.engine.evaluate(self._make_facts("qualified"), {})
        f005 = [r for r in result["triggered_rules"] if r["rule_id"] == "F005"]
        assert len(f005) == 1
        assert f005[0]["score"] == 20

    def test_adverse_triggers(self):
        """adverse → F005 触发（score=20）。"""
        result = self.engine.evaluate(self._make_facts("adverse"), {})
        f005 = [r for r in result["triggered_rules"] if r["rule_id"] == "F005"]
        assert len(f005) == 1
        assert f005[0]["score"] == 20

    def test_disclaimer_triggers(self):
        """disclaimer → F005 触发（score=20）。"""
        result = self.engine.evaluate(self._make_facts("disclaimer"), {})
        f005 = [r for r in result["triggered_rules"] if r["rule_id"] == "F005"]
        assert len(f005) == 1
        assert f005[0]["score"] == 20

    def test_chinese_display_value_no_trigger(self):
        """中文展示值 '无保留意见' 不触发 F005。
        注意：Rule Engine 只接受 canonical English values。
        数据管道负责在入库前将中文标准化为 English。
        此测试验证：如果中文值意外传入引擎，不会被误判为正常。
        '无保留意见' 不在 ('unqualified', '') 中，会触发 F005 ——
        这是正确行为：数据管道应确保传入 canonical value。
        """
        # 中文值传入引擎 → 触发 F005（数据管道应标准化）
        result = self.engine.evaluate(self._make_facts("无保留意见"), {})
        f005 = [r for r in result["triggered_rules"] if r["rule_id"] == "F005"]
        assert len(f005) == 1, "中文值传入引擎应触发 F005（数据管道应标准化）"

    def test_chinese_qualified_triggers(self):
        """中文 '保留意见' 属于异常，应触发 F005。"""
        result = self.engine.evaluate(self._make_facts("保留意见"), {})
        f005 = [r for r in result["triggered_rules"] if r["rule_id"] == "F005"]
        assert len(f005) == 1

    def test_max_hits_cap(self):
        """多年度 qualified 审计意见 → F005 最多触发 max_hits=2 次。"""
        facts = []
        for i, period in enumerate(["2023FY", "2024FY", "2025FY", "2026FY"]):
            facts.append({
                "evidence_id": f"F{i+1:03d}",
                "evidence_type": "financial",
                "data": {"audit_opinion": "qualified", "period": period},
                "company_id": "C001",
                "owner_company_id": "C001",
                "target_company_id": "C001",
                "is_target_company": True,
                "relation_depth": 0,
                "relation_path": ["C001"],
                "relation_ids": [],
                "relation_types": [],
                "target_role_in_relation": None,
            })

        result = self.engine.evaluate(facts, {})
        f005 = [r for r in result["triggered_rules"] if r["rule_id"] == "F005"]
        assert len(f005) == 2, f"max_hits=2, 4 年 qualified 应触发 2 次, 实际 {len(f005)}"
        assert result["risk_score"] == 40, f"2 × 20 = 40, 实际 {result['risk_score']}"

    def test_single_qualified_no_cap_needed(self):
        """单年 qualified → 正常触发 1 次。"""
        result = self.engine.evaluate(self._make_facts("qualified"), {})
        f005 = [r for r in result["triggered_rules"] if r["rule_id"] == "F005"]
        assert len(f005) == 1
        assert f005[0]["hit_count"] == 1
        assert f005[0]["max_hits"] == 2

    def test_c001_normal_financial_no_f005(self):
        """C001 正常财务（unqualified）→ 不因 F005 误判高风险。"""
        facts = []
        for i, period in enumerate(["2023FY", "2024FY", "2025FY"]):
            facts.append({
                "evidence_id": f"F{i+1:03d}",
                "evidence_type": "financial",
                "data": {"audit_opinion": "unqualified", "period": period},
                "company_id": "C001",
                "owner_company_id": "C001",
                "target_company_id": "C001",
                "is_target_company": True,
                "relation_depth": 0,
                "relation_path": ["C001"],
                "relation_ids": [],
                "relation_types": [],
                "target_role_in_relation": None,
            })

        result = self.engine.evaluate(facts, {})
        f005 = [r for r in result["triggered_rules"] if r["rule_id"] == "F005"]
        assert len(f005) == 0, "C001 正常财务不应触发 F005"
        assert result["risk_score"] == 0


# ============================================================
# V2.3B.1: Related Company Own Risk Profile 测试
# ============================================================
class TestRelatedCompanyRiskProfile:
    """V2.3B.1: 关联企业使用自己的数据计算 Own Risk。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.engine = RiskRuleEngine(load_config())

    def test_same_company_same_own_score(self):
        """同一家公司作为主目标和关联企业时，Own Risk Score 完全一致。"""
        # 模拟 C007 的 evidence（is_target_company=True）
        c007_own_facts = [
            {
                "evidence_id": "J001", "evidence_type": "judicial",
                "data": {"case_type": "被执行人", "role": "被告", "amount": 6000000},
                "company_id": "C007", "owner_company_id": "C007",
                "target_company_id": "C007", "is_target_company": True,
                "relation_depth": 0, "relation_path": ["C007"],
                "relation_ids": [], "relation_types": [],
                "target_role_in_relation": None,
            },
            {
                "evidence_id": "B001", "evidence_type": "business",
                "data": {"event_type": "经营异常", "description": "被列入经营异常名录"},
                "company_id": "C007", "owner_company_id": "C007",
                "target_company_id": "C007", "is_target_company": True,
                "relation_depth": 0, "relation_path": ["C007"],
                "relation_ids": [], "relation_types": [],
                "target_role_in_relation": None,
            },
        ]
        extra = {"debt_ratio": 0.85, "consecutive_loss_years": 2, "latest_operating_cash_flow": -500000, "recruitment_count": 0}

        # 作为主目标评估
        result_direct = self.engine.evaluate(c007_own_facts, extra)
        direct_score = result_direct["own_risk"]["score"]
        direct_level = result_direct["own_risk"]["level"]

        # 通过 evaluate_company_own_risk 评估（模拟作为关联企业）
        result_as_related = self.engine.evaluate_company_own_risk("C007", c007_own_facts, extra)

        assert result_as_related["score"] == direct_score, \
            f"直接={direct_score}, 作为关联={result_as_related['score']}"
        assert result_as_related["level"] == direct_level

    def test_c007_as_related_uses_own_data(self):
        """C007 作为 C004 的关联企业时，own_score=300（使用自己的数据）。"""
        # C007 自己的 evidence（来自 DB 的真实数据模式）
        c007_facts = [
            {"evidence_id": "J001", "evidence_type": "judicial",
             "data": {"case_type": "被执行人", "role": "被告", "amount": 6000000},
             "company_id": "C007"},
            {"evidence_id": "J002", "evidence_type": "judicial",
             "data": {"case_type": "被执行人", "role": "被告", "amount": 8000000},
             "company_id": "C007"},
            {"evidence_id": "J003", "evidence_type": "judicial",
             "data": {"case_type": "限制消费令", "role": "被告", "amount": 6000000},
             "company_id": "C007"},
            {"evidence_id": "J004", "evidence_type": "judicial",
             "data": {"case_type": "股权冻结", "role": "被告", "amount": 6000000},
             "company_id": "C007"},
            {"evidence_id": "B001", "evidence_type": "business",
             "data": {"event_type": "行政处罚", "description": "环保处罚"},
             "company_id": "C007"},
            {"evidence_id": "B002", "evidence_type": "business",
             "data": {"event_type": "经营异常", "description": "被列入经营异常名录"},
             "company_id": "C007"},
            {"evidence_id": "F001", "evidence_type": "financial",
             "data": {"audit_opinion": "qualified", "period": "2024FY"},
             "company_id": "C007"},
            {"evidence_id": "F002", "evidence_type": "financial",
             "data": {"audit_opinion": "qualified", "period": "2025FY"},
             "company_id": "C007"},
            {"evidence_id": "P001", "evidence_type": "public_opinion",
             "data": {"sentiment": "negative", "verification_status": "verified"},
             "company_id": "C007"},
            {"evidence_id": "P002", "evidence_type": "public_opinion",
             "data": {"sentiment": "negative", "verification_status": "unverified"},
             "company_id": "C007"},
            {"evidence_id": "P003", "evidence_type": "public_opinion",
             "data": {"sentiment": "negative", "verification_status": "unverified"},
             "company_id": "C007"},
            {"evidence_id": "P004", "evidence_type": "public_opinion",
             "data": {"sentiment": "negative", "verification_status": "unverified"},
             "company_id": "C007"},
        ]
        extra = {"debt_ratio": 0.86, "consecutive_loss_years": 2, "latest_operating_cash_flow": -15000000, "recruitment_count": 4}

        result = self.engine.evaluate_company_own_risk("C007", c007_facts, extra)
        assert result["score"] == 300, f"C007 own_score 应为 300, 实际 {result['score']}"
        assert result["level"] == "高风险"

    def test_company_level_financial_uses_own_extra(self):
        """关联企业 Company-Level Financial Rules 使用自己的财务数据。"""
        # C007 有高 debt_ratio
        c007_facts = [
            {"evidence_id": "F001", "evidence_type": "financial",
             "data": {"audit_opinion": "qualified", "period": "2024FY"},
             "company_id": "C007"},
        ]
        c007_extra = {"debt_ratio": 0.86, "consecutive_loss_years": 2, "latest_operating_cash_flow": -15000000, "recruitment_count": 4}

        result = self.engine.evaluate_company_own_risk("C007", c007_facts, c007_extra)
        rule_ids = [r["rule_id"] for r in result["triggered_rules"]]
        # F001 (debt_ratio>0.70), F003 (consecutive_loss>=2), F004 (cashflow<0), F005 (qualified)
        assert "F001" in rule_ids, "F001 应触发（debt_ratio=0.86 > 0.70）"
        assert "F003" in rule_ids, "F003 应触发（consecutive_loss=2 >= 2）"
        assert "F004" in rule_ids, "F004 应触发（cashflow=-15M < 0）"
        assert "F005" in rule_ids, "F005 应触发（qualified）"

    def test_multi_path_dedup(self):
        """同一关联企业存在多路径时，Own Risk 只计算一次。"""
        from app.risk_rule_engine import build_related_company_profiles

        # 模拟 deps 模块
        class MockDeps:
            def get_company_profile(self, cid):
                return {"company_name": f"Company_{cid}", "business_status": "存续"}
            def get_financial_reports(self, cid):
                return [{"debt_ratio": 0.3, "net_profit": 1000000, "operating_cash_flow": 500000,
                         "period": "2025FY", "total_liabilities": 3000000, "total_assets": 10000000}]
            def get_recruitment_events(self, cid):
                return [{"position_category": "技术", "position_name": "开发"}] * 5
            def get_judicial_events(self, cid):
                return []
            def get_business_events(self, cid):
                return []
            def get_public_opinion_events(self, cid):
                return []
            def get_company_relations(self, cid):
                return []

        evidence_facts = [
            # 两条路径指向 C008，但 company_id 相同
            {"evidence_id": "J001", "evidence_type": "judicial",
             "data": {"case_type": "被执行人", "role": "被告", "amount": 6000000},
             "company_id": "C008", "owner_company_id": "C008",
             "target_company_id": "C004", "is_target_company": False,
             "relation_depth": 2, "relation_path": ["C004", "C005", "C008"],
             "relation_ids": ["R005", "R006"], "relation_types": ["股权", "对外投资"],
             "target_role_in_relation": "investee"},
            {"evidence_id": "J002", "evidence_type": "judicial",
             "data": {"case_type": "被执行人", "role": "被告", "amount": 6000000},
             "company_id": "C008", "owner_company_id": "C008",
             "target_company_id": "C004", "is_target_company": False,
             "relation_depth": 1, "relation_path": ["C004", "C008"],
             "relation_ids": ["R007"], "relation_types": ["共同法人"],
             "target_role_in_relation": "common_legal_rep"},
        ]

        # V2.3B.2: 需要传入真实的 all_relations 以支持 find_all_paths
        all_relations = [
            {"relation_id": "R005", "from_company_id": "C004", "to_company_id": "C005",
             "relation_type": "股权", "relation_detail": "", "equity_ratio": None,
             "amount": None, "start_date": None, "end_date": None, "status": "active",
             "source": "simulated", "from_company_name": "C004", "to_company_name": "C005"},
            {"relation_id": "R006", "from_company_id": "C005", "to_company_id": "C008",
             "relation_type": "对外投资", "relation_detail": "", "equity_ratio": None,
             "amount": None, "start_date": None, "end_date": None, "status": "active",
             "source": "simulated", "from_company_name": "C005", "to_company_name": "C008"},
            {"relation_id": "R007", "from_company_id": "C004", "to_company_id": "C008",
             "relation_type": "共同法人", "relation_detail": "", "equity_ratio": None,
             "amount": None, "start_date": None, "end_date": None, "status": "active",
             "source": "simulated", "from_company_name": "C004", "to_company_name": "C008"},
        ]

        profiles = build_related_company_profiles(
            "C004", ["C005", "C008"], evidence_facts, all_relations,
            self.engine, MockDeps()
        )

        # C008 只应有一个 profile
        c008_profiles = [p for p in profiles if p["company_id"] == "C008"]
        assert len(c008_profiles) == 1, f"C008 应只有 1 个 profile, 实际 {len(c008_profiles)}"

        # V2.3B.2: 路径由 find_all_paths 计算，最短路径 depth=1（C004→C008）
        assert c008_profiles[0]["relation_depth"] == 1
        assert "R007" in c008_profiles[0]["relation_ids"]

    def test_profile_path_provenance(self):
        """RelatedCompanyRiskProfile 路径由 find_all_paths 计算。"""
        from app.risk_rule_engine import build_related_company_profiles

        class MockDeps:
            def get_company_profile(self, cid):
                return {"company_name": f"Company_{cid}", "business_status": "存续"}
            def get_financial_reports(self, cid):
                return [{"debt_ratio": 0.3, "net_profit": 1000000, "operating_cash_flow": 500000,
                         "period": "2025FY", "total_liabilities": 3000000, "total_assets": 10000000}]
            def get_recruitment_events(self, cid):
                return [{"position_category": "技术", "position_name": "开发"}] * 5
            def get_judicial_events(self, cid):
                return []
            def get_business_events(self, cid):
                return []
            def get_public_opinion_events(self, cid):
                return []
            def get_company_relations(self, cid):
                return []

        evidence_facts = [
            {"evidence_id": "J001", "evidence_type": "judicial",
             "data": {"case_type": "被执行人", "role": "被告", "amount": 6000000},
             "company_id": "C005", "owner_company_id": "C005",
             "target_company_id": "C001", "is_target_company": False,
             "relation_depth": 1, "relation_path": ["C001", "C005"],
             "relation_ids": ["R001"], "relation_types": ["股权"],
             "target_role_in_relation": "shareholder"},
        ]

        # V2.3B.2: 需要传入真实的 all_relations 以支持 find_all_paths
        all_relations = [
            {"relation_id": "R001", "from_company_id": "C001", "to_company_id": "C005",
             "relation_type": "股权", "relation_detail": "", "equity_ratio": None,
             "amount": None, "start_date": None, "end_date": None, "status": "active",
             "source": "simulated", "from_company_name": "C001", "to_company_name": "C005"},
        ]

        profiles = build_related_company_profiles(
            "C001", ["C005"], evidence_facts, all_relations,
            self.engine, MockDeps()
        )

        assert len(profiles) == 1
        p = profiles[0]
        assert p["company_id"] == "C005"
        assert p["relation_depth"] == 1
        assert p["relation_path"] == ["C001", "C005"]
        assert "R001" in p["relation_ids"]
        assert "股权" in p["relation_types"]

    def test_relationship_exposure_status_not_calibrated(self):
        """relationship_exposure: score=null, level=null, status=NOT_CALIBRATED。"""
        facts = [
            {"evidence_id": "J001", "evidence_type": "judicial",
             "data": {"case_type": "被执行人", "role": "被告", "amount": 6000000},
             "company_id": "C001", "owner_company_id": "C001",
             "target_company_id": "C001", "is_target_company": True,
             "relation_depth": 0, "relation_path": ["C001"],
             "relation_ids": [], "relation_types": [],
             "target_role_in_relation": None},
        ]

        result = self.engine.evaluate(facts, {})
        rel = result["relationship_exposure"]
        assert rel["status"] == "NOT_CALIBRATED"
        assert rel["score"] is None
        assert rel["level"] is None

    def test_v22_own_related_separation_not_broken(self):
        """V2.2 Own/Related Evidence Separation 不得回归。"""
        facts = [
            # C001 自身的 evidence
            {"evidence_id": "B001", "evidence_type": "business",
             "data": {"event_type": "经营异常", "description": "被列入经营异常名录"},
             "company_id": "C001", "owner_company_id": "C001",
             "target_company_id": "C001", "is_target_company": True,
             "relation_depth": 0, "relation_path": ["C001"],
             "relation_ids": [], "relation_types": [],
             "target_role_in_relation": None},
            # C002 的 evidence（关联企业）
            {"evidence_id": "J001", "evidence_type": "judicial",
             "data": {"case_type": "失信被执行人"},
             "company_id": "C002", "owner_company_id": "C002",
             "target_company_id": "C001", "is_target_company": False,
             "relation_depth": 1, "relation_path": ["C001", "C002"],
             "relation_ids": ["R001"], "relation_types": ["股权"],
             "target_role_in_relation": "shareholder"},
        ]

        result = self.engine.evaluate(facts, {})

        # own_risk 只包含 C001 的 B001
        own_rules = [r["rule_id"] for r in result["own_risk"]["triggered_rules"]]
        assert "B001" in own_rules
        assert result["own_risk"]["score"] == 20

        # related_exposure 包含 C002 的 J001
        rel = result["relationship_exposure"]
        assert rel["status"] == "NOT_CALIBRATED"

    def test_c001_c004_c007_own_risk_calibration(self):
        """C001/C004/C007 Own Risk 继续保持当前校准结果。"""
        # C001: 健康公司
        c001_facts = [
            {"evidence_id": "F001", "evidence_type": "financial",
             "data": {"audit_opinion": "unqualified", "period": "2025FY"},
             "company_id": "C001"},
        ]
        c001_extra = {"debt_ratio": 0.34, "consecutive_loss_years": 0,
                      "latest_operating_cash_flow": 19000000, "recruitment_count": 4}
        r1 = self.engine.evaluate_company_own_risk("C001", c001_facts, c001_extra)
        assert r1["score"] == 0, f"C001 own_score 应为 0, 实际 {r1['score']}"
        assert r1["level"] == "低风险"

        # C004: 健康公司（仅 1 条未核实负面舆情）
        c004_facts = [
            {"evidence_id": "P001", "evidence_type": "public_opinion",
             "data": {"sentiment": "negative", "verification_status": "partially_verified"},
             "company_id": "C004"},
        ]
        c004_extra = {"debt_ratio": 0.34, "consecutive_loss_years": 0,
                      "latest_operating_cash_flow": 42000000, "recruitment_count": 3}
        r4 = self.engine.evaluate_company_own_risk("C004", c004_facts, c004_extra)
        assert r4["score"] == 5, f"C004 own_score 应为 5, 实际 {r4['score']}"
        assert r4["level"] == "低风险"

        # C007: 高风险公司
        c007_facts = [
            {"evidence_id": "J001", "evidence_type": "judicial",
             "data": {"case_type": "被执行人", "role": "被告", "amount": 6000000},
             "company_id": "C007"},
            {"evidence_id": "J002", "evidence_type": "judicial",
             "data": {"case_type": "被执行人", "role": "被告", "amount": 8000000},
             "company_id": "C007"},
            {"evidence_id": "J003", "evidence_type": "judicial",
             "data": {"case_type": "限制消费令", "role": "被告", "amount": 6000000},
             "company_id": "C007"},
            {"evidence_id": "J004", "evidence_type": "judicial",
             "data": {"case_type": "股权冻结", "role": "被告", "amount": 6000000},
             "company_id": "C007"},
            {"evidence_id": "B001", "evidence_type": "business",
             "data": {"event_type": "行政处罚", "description": "环保处罚"},
             "company_id": "C007"},
            {"evidence_id": "B002", "evidence_type": "business",
             "data": {"event_type": "经营异常", "description": "被列入经营异常名录"},
             "company_id": "C007"},
            {"evidence_id": "F001", "evidence_type": "financial",
             "data": {"audit_opinion": "qualified", "period": "2024FY"},
             "company_id": "C007"},
            {"evidence_id": "F002", "evidence_type": "financial",
             "data": {"audit_opinion": "qualified", "period": "2025FY"},
             "company_id": "C007"},
            {"evidence_id": "P001", "evidence_type": "public_opinion",
             "data": {"sentiment": "negative", "verification_status": "verified"},
             "company_id": "C007"},
            {"evidence_id": "P002", "evidence_type": "public_opinion",
             "data": {"sentiment": "negative", "verification_status": "unverified"},
             "company_id": "C007"},
            {"evidence_id": "P003", "evidence_type": "public_opinion",
             "data": {"sentiment": "negative", "verification_status": "unverified"},
             "company_id": "C007"},
            {"evidence_id": "P004", "evidence_type": "public_opinion",
             "data": {"sentiment": "negative", "verification_status": "unverified"},
             "company_id": "C007"},
        ]
        c007_extra = {"debt_ratio": 0.86, "consecutive_loss_years": 2,
                      "latest_operating_cash_flow": -15000000, "recruitment_count": 4}
        r7 = self.engine.evaluate_company_own_risk("C007", c007_facts, c007_extra)
        assert r7["score"] == 300, f"C007 own_score 应为 300, 实际 {r7['score']}"
        assert r7["level"] == "高风险"


# ============================================================
# V2.3B.2: 关联企业风险传导测试
# ============================================================


class TestRelationshipRiskTransmission:
    """V2.3B.2: 关联企业风险传导测试。"""

    @pytest.fixture(autouse=True)
    def _setup(self):
        """创建引擎和加载配置。"""
        from risk_rule_engine import (
            load_transmission_config,
            find_all_paths,
            build_relation_graph,
            compute_path_transmission,
            compute_company_exposure_contribution,
            compute_relationship_exposure,
        )
        self.config = load_config()
        self.engine = RiskRuleEngine(self.config)
        self.transmission_config = load_transmission_config()
        self.find_all_paths = find_all_paths
        self.build_relation_graph = build_relation_graph
        self.compute_path_transmission = compute_path_transmission
        self.compute_company_exposure_contribution = compute_company_exposure_contribution
        self.compute_relationship_exposure = compute_relationship_exposure

    def _make_relation(self, rid: str, from_id: str, to_id: str, rel_type: str) -> Dict[str, Any]:
        """构造一条 relation 记录。"""
        return {
            "relation_id": rid,
            "from_company_id": from_id,
            "to_company_id": to_id,
            "relation_type": rel_type,
            "relation_detail": "",
            "equity_ratio": None,
            "amount": None,
            "start_date": None,
            "end_date": None,
            "status": "active",
            "source": "simulated",
            "from_company_name": from_id,
            "to_company_name": to_id,
        }

    def _make_profile(self, company_id: str, own_score: int, own_level: str = "低风险",
                      name: str = "") -> Dict[str, Any]:
        """构造一个 related company profile。"""
        return {
            "company_id": company_id,
            "company_name": name or company_id,
            "own_score": own_score,
            "own_level": own_level,
            "triggered_rules": [],
            "dimension_scores": {},
            "evidence_ids": [],
            "evidence_count": 0,
            "hard_rule_hits": [],
            "relation_depth": 0,
            "relation_path": [],
            "relation_ids": [],
            "relation_types": [],
            "target_role_in_relation": None,
            "all_paths": [],
        }

    def test_same_own_score_depth1_stronger_than_depth2(self):
        """同一 Own Risk，depth=1 比 depth=2 transmission 更强。"""
        relations = [
            self._make_relation("R01", "TGT", "C01", "股权"),
            self._make_relation("R02", "TGT", "C02", "股权"),
            self._make_relation("R03", "C02", "C01", "股权"),
        ]
        graph = self.build_relation_graph(relations)

        # C01: 直接关联 TGT (depth=1)
        paths_c01 = self.find_all_paths(graph, "TGT", "C01")
        # C01: 间接关联通过 C02 (depth=2)
        paths_c02 = self.find_all_paths(graph, "TGT", "C01")

        own_score = 100
        tc = self.transmission_config

        # depth=1 路径
        d1_path = {"path": ["TGT", "C01"], "depth": 1,
                    "relation_ids": ["R01"], "relation_types": ["股权"]}
        d1_result = self.compute_path_transmission(own_score, d1_path, tc, relations, "TGT")

        # depth=2 路径
        d2_path = {"path": ["TGT", "C02", "C01"], "depth": 2,
                    "relation_ids": ["R03", "R02"], "relation_types": ["股权", "股权"]}
        d2_result = self.compute_path_transmission(own_score, d2_path, tc, relations, "TGT")

        assert d1_result["transmitted_score"] > d2_result["transmitted_score"], (
            f"depth=1 ({d1_result['transmitted_score']}) 应大于 depth=2 ({d2_result['transmitted_score']})"
        )

    def test_guarantee_path_stronger_than_common_shareholder(self):
        """担保路径比共同股东路径有更强传导语义。"""
        relations = [
            self._make_relation("R01", "TGT", "C01", "担保"),
            self._make_relation("R02", "TGT", "C02", "共同股东"),
        ]
        graph = self.build_relation_graph(relations)
        tc = self.transmission_config
        own_score = 100

        # 担保路径
        guarantee_path = {"path": ["TGT", "C01"], "depth": 1,
                          "relation_ids": ["R01"], "relation_types": ["担保"]}
        guarantee_result = self.compute_path_transmission(
            own_score, guarantee_path, tc, relations, "TGT"
        )

        # 共同股东路径
        common_path = {"path": ["TGT", "C02"], "depth": 1,
                       "relation_ids": ["R02"], "relation_types": ["共同股东"]}
        common_result = self.compute_path_transmission(
            own_score, common_path, tc, relations, "TGT"
        )

        assert guarantee_result["transmitted_score"] > common_result["transmitted_score"], (
            f"担保 ({guarantee_result['transmitted_score']}) 应大于 "
            f"共同股东 ({common_result['transmitted_score']})"
        )

    def test_guarantor_vs_guaranteed_party_different(self):
        """guarantor 与 guaranteed_party 有不同的传导语义。"""
        relations = [
            # TGT 担保 C01（TGT 是 guarantor）
            self._make_relation("R01", "TGT", "C01", "担保"),
        ]
        graph = self.build_relation_graph(relations)
        tc = self.transmission_config
        own_score = 100

        # TGT 担保 C01 → TGT 是 guarantor
        path = {"path": ["TGT", "C01"], "depth": 1,
                "relation_ids": ["R01"], "relation_types": ["担保"]}
        result = self.compute_path_transmission(own_score, path, tc, relations, "TGT")

        # 对于 TGT 担保 C01 的路径，TGT 是 guarantor（role_factor=1.0）
        assert result["target_role"] == "guarantor"
        assert result["target_role_factor"] == 1.0

        # 反向：C01 担保 TGT（C01 是 guarantor，TGT 是 guaranteed_party）
        relations2 = [
            self._make_relation("R02", "C01", "TGT", "担保"),
        ]
        path2 = {"path": ["TGT", "C01"], "depth": 1,
                 "relation_ids": ["R02"], "relation_types": ["担保"]}
        result2 = self.compute_path_transmission(own_score, path2, tc, relations2, "TGT")

        assert result2["target_role"] == "guaranteed_party"
        assert result2["target_role_factor"] == 0.8

        # guarantor 传导更强
        assert result["transmitted_score"] > result2["transmitted_score"]

    def test_multi_path_no_double_counting_own_risk(self):
        """同一 related company 多路径不重复计算 Own Risk。"""
        relations = [
            self._make_relation("R01", "TGT", "C01", "股权"),
            self._make_relation("R02", "TGT", "C02", "对外投资"),
            self._make_relation("R03", "C02", "C01", "股权"),
        ]
        graph = self.build_relation_graph(relations)

        # 查找所有路径
        all_paths = self.find_all_paths(graph, "TGT", "C01")
        assert len(all_paths) >= 2, "C01 应至少有两条路径可达"

        profiles = [self._make_profile("C01", own_score=100)]
        tc = self.transmission_config

        exposure = self.compute_relationship_exposure(
            "TGT", profiles, relations, tc
        )

        # contribution 应该只有一个（C01）
        assert len(exposure["company_contributions"]) == 1
        contribution = exposure["company_contributions"][0]
        assert contribution["company_id"] == "C01"

        # Own Risk 不应被重复计算
        assert contribution["own_score"] == 100

    def test_multi_path_strongest_strategy(self):
        """多路径不简单求和，strongest path 策略正确。"""
        relations = [
            self._make_relation("R01", "TGT", "C01", "股权"),
            self._make_relation("R02", "TGT", "C02", "对外投资"),
            self._make_relation("R03", "C02", "C01", "股权"),
        ]
        graph = self.build_relation_graph(relations)

        all_paths = self.find_all_paths(graph, "TGT", "C01")
        tc = self.transmission_config
        own_score = 100

        # 计算每条路径的传导
        transmissions = []
        for p in all_paths:
            pt = self.compute_path_transmission(own_score, p, tc, relations, "TGT")
            transmissions.append(pt)

        # contribution 应该取最强路径
        contribution = self.compute_company_exposure_contribution(
            "C01", own_score, "高风险", "Test Co",
            transmissions, all_paths, tc
        )

        strongest = contribution["strongest_path"]
        assert strongest is not None
        assert contribution["transmitted_score"] == strongest["transmitted_score"]

        # 最强路径的 transmitted_score 应大于等于任何单条路径
        for t in transmissions:
            assert contribution["transmitted_score"] >= t["transmitted_score"]

    def test_zero_risk_company_zero_transmission(self):
        """related company own_score=0 → transmitted_score 应为 0。"""
        tc = self.transmission_config
        relations = [
            self._make_relation("R01", "TGT", "C01", "担保"),
        ]
        path = {"path": ["TGT", "C01"], "depth": 1,
                "relation_ids": ["R01"], "relation_types": ["担保"]}
        result = self.compute_path_transmission(0, path, tc, relations, "TGT")

        assert result["transmitted_score"] == 0
        assert "零风险" in result["transmission_reasons"][0]

    def test_c007_own_risk_independent(self):
        """C007 作为 C004 关联企业仍使用 Own Risk=300。"""
        from risk_rule_engine import build_company_evidence_and_extra
        import sys
        from pathlib import Path

        # 确保 backend/app 在路径中
        BACKEND_APP = Path(__file__).resolve().parents[1] / "backend" / "app"
        if str(BACKEND_APP) not in sys.path:
            sys.path.insert(0, str(BACKEND_APP))
        import deps

        # 构建 C007 的 evidence
        c007_evidence, c007_extra = build_company_evidence_and_extra("C007", deps)

        # 计算 C007 的 own risk
        own_risk = self.engine.evaluate_company_own_risk("C007", c007_evidence, c007_extra)
        assert own_risk["score"] == 300, f"C007 own_score 应为 300, 实际 {own_risk['score']}"

    def test_transmission_config_version_saved(self):
        """Transmission config version/hash 保存在结果中。"""
        from risk_rule_engine import get_transmission_config_hash
        tc = self.transmission_config
        profiles = [self._make_profile("C01", own_score=100)]
        relations = [self._make_relation("R01", "TGT", "C01", "股权")]

        exposure = self.compute_relationship_exposure("TGT", profiles, relations, tc)

        assert exposure["status"] == "CALIBRATED_V1"
        assert exposure["transmission_version"] == "1.0.0"
        assert exposure["transmission_config_hash"] == get_transmission_config_hash(tc)

    def test_c001_relationship_exposure(self):
        """C001 的 Relationship Exposure 应主要来自 C002。"""
        import sys
        from pathlib import Path

        BACKEND_APP = Path(__file__).resolve().parents[1] / "backend" / "app"
        if str(BACKEND_APP) not in sys.path:
            sys.path.insert(0, str(BACKEND_APP))
        import deps

        from risk_rule_engine import build_company_evidence_and_extra

        # 构建 C002 的 own risk profile
        c002_evidence, c002_extra = build_company_evidence_and_extra("C002", deps)
        c002_own_risk = self.engine.evaluate_company_own_risk("C002", c002_evidence, c002_extra)

        profiles = [self._make_profile(
            "C002", c002_own_risk["score"], c002_own_risk["level"], "C002"
        )]
        relations = [self._make_relation("R01", "C001", "C002", "股权")]
        tc = self.transmission_config

        exposure = self.compute_relationship_exposure("C001", profiles, relations, tc)

        assert exposure["status"] == "CALIBRATED_V1"
        assert len(exposure["company_contributions"]) == 1
        contrib = exposure["company_contributions"][0]
        assert contrib["company_id"] == "C002"
        # 传导分数应大于 0（如果 C002 有 own risk）
        if c002_own_risk["score"] > 0:
            assert exposure["score"] > 0

    def test_c004_relationship_exposure(self):
        """C004 的 Relationship Exposure 应主要来自 C007。"""
        import sys
        from pathlib import Path

        BACKEND_APP = Path(__file__).resolve().parents[1] / "backend" / "app"
        if str(BACKEND_APP) not in sys.path:
            sys.path.insert(0, str(BACKEND_APP))
        import deps

        from risk_rule_engine import build_company_evidence_and_extra

        # 构建 C007 的 own risk profile
        c007_evidence, c007_extra = build_company_evidence_and_extra("C007", deps)
        c007_own_risk = self.engine.evaluate_company_own_risk("C007", c007_evidence, c007_extra)

        profiles = [self._make_profile(
            "C007", c007_own_risk["score"], c007_own_risk["level"], "C007"
        )]
        # C004 → C005 → C006 → C007 (depth=3, 股权 0.7 * 0.3 = 0.21)
        # C004 → C008 → C007 (depth=2, 共同股东 0.3 * 0.5 = 0.15)
        # depth=3 路径传导更强（股权 factor 远高于共同股东）
        relations = [
            self._make_relation("R004", "C004", "C005", "股权"),
            self._make_relation("R005", "C005", "C006", "对外投资"),
            self._make_relation("R006", "C006", "C007", "股权"),
            self._make_relation("R007", "C004", "C008", "对外投资"),
            self._make_relation("R008", "C008", "C007", "共同股东"),
        ]
        tc = self.transmission_config

        exposure = self.compute_relationship_exposure("C004", profiles, relations, tc)

        assert exposure["status"] == "CALIBRATED_V1"
        contrib = exposure["company_contributions"][0]
        assert contrib["company_id"] == "C007"
        assert contrib["own_score"] == 300
        # 最强路径是 depth=3（C004→C005→C006→C007，最后关系类型为股权 0.7）
        # 因为 股权(0.7) × depth_factor(0.3) = 0.21 > 共同股东(0.3) × depth_factor(0.5) = 0.15
        assert contrib["strongest_path"] is not None
        assert contrib["strongest_path"]["depth"] == 3

    def test_c007_relationship_exposure_lower_than_own_risk(self):
        """C007 的 Relationship Exposure 应显著低于其 Own Risk。"""
        import sys
        from pathlib import Path

        BACKEND_APP = Path(__file__).resolve().parents[1] / "backend" / "app"
        if str(BACKEND_APP) not in sys.path:
            sys.path.insert(0, str(BACKEND_APP))
        import deps

        from risk_rule_engine import build_company_evidence_and_extra

        # C007 的 own risk = 300
        c007_evidence, c007_extra = build_company_evidence_and_extra("C007", deps)
        c007_own_risk = self.engine.evaluate_company_own_risk("C007", c007_evidence, c007_extra)
        assert c007_own_risk["score"] == 300

        # 当 C007 是 C004 的关联企业时
        # 最强路径 C004→C008→C007 (depth=2, 共同股东 relation_type_factor=0.3)
        # transmitted_score = 300 * 0.3 * 0.5 * 0.5 = 22.5 → 23
        profiles = [self._make_profile(
            "C007", c007_own_risk["score"], c007_own_risk["level"], "C007"
        )]
        relations = [
            self._make_relation("R004", "C004", "C005", "股权"),
            self._make_relation("R005", "C005", "C006", "对外投资"),
            self._make_relation("R006", "C006", "C007", "股权"),
            self._make_relation("R007", "C004", "C008", "对外投资"),
            self._make_relation("R008", "C008", "C007", "共同股东"),
        ]
        tc = self.transmission_config

        exposure = self.compute_relationship_exposure("C004", profiles, relations, tc)

        # relationship_exposure 应显著低于 C007 的 own_risk
        assert exposure["score"] < c007_own_risk["score"], (
            f"Relationship Exposure ({exposure['score']}) 应小于 "
            f"Own Risk ({c007_own_risk['score']})"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
