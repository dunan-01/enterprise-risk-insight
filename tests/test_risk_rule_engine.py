"""
Risk Rule Engine 单元测试（V3.0 简化版）。

验证：
1. 相同输入重复运行，风险评分和等级必须一致（确定性）
2. 同一 Evidence 不得被同一规则重复计分
3. 每一个风险分都可以追溯到规则和 Evidence
4. 硬规则强制提升风险等级
5. 空输入时返回零分低风险
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
# ------------------------------------------------------------

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
        """失信被执行人触发 J001（40分）。"""
        facts = [
            {
                "evidence_id": "J001",
                "evidence_type": "judicial",
                "data": {"case_type": "失信被执行人"},
            },
        ]
        result = engine.evaluate(facts, {})
        assert result["risk_score"] == 40
        assert any(r["rule_id"] == "J001" for r in result["triggered_rules"])

    def test_judicial_executed_person(self, engine):
        """被执行人（非失信）触发 J002（25分）。"""
        facts = [
            {
                "evidence_id": "J002",
                "evidence_type": "judicial",
                "data": {"case_type": "被执行人"},
            },
        ]
        result = engine.evaluate(facts, {})
        assert result["risk_score"] == 25
        assert any(r["rule_id"] == "J002" for r in result["triggered_rules"])

    def test_business_abnormal(self, engine):
        """经营异常触发 B001（30分）。"""
        facts = [
            {
                "evidence_id": "B001",
                "evidence_type": "business",
                "data": {"event_type": "经营异常"},
            },
        ]
        result = engine.evaluate(facts, {})
        assert result["risk_score"] == 30
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
        """已核实负面舆情触发 P001（20分）。"""
        facts = [
            {
                "evidence_id": "P001",
                "evidence_type": "public_opinion",
                "data": {"sentiment": "negative", "verification_status": "verified"},
            },
        ]
        result = engine.evaluate(facts, {})
        assert result["risk_score"] == 20
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
        """破产案件触发 J007（50分）。"""
        facts = [
            {
                "evidence_id": "J007",
                "evidence_type": "judicial",
                "data": {"case_type": "破产案件"},
            },
        ]
        result = engine.evaluate(facts, {})
        assert result["risk_score"] == 50
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
        # 只应计分一次（40分），而不是两次（80分）
        assert result["risk_score"] == 40
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
        # 两个不同 Evidence 都触发 J001，各计 40 分
        assert result["risk_score"] == 80
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

    def test_bankruptcy_forces_major_risk(self, engine):
        """破产案件硬规则强制提升到重大风险。"""
        facts = [
            {
                "evidence_id": "J007",
                "evidence_type": "judicial",
                "data": {"case_type": "破产案件"},
            },
        ]
        extra = {"has_bankruptcy_case": True}
        result = engine.evaluate(facts, extra)
        assert result["risk_level"] == "重大风险"
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
        # 正常 5 分应该是低风险，但硬规则强制为重大风险
        assert result["risk_level"] == "重大风险"
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
        # 40 分应该在中风险区间（31-70）
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
        # 40 + 30 = 70 分，应该在中风险区间（31-70）
        assert result["risk_score"] == 70
        assert result["risk_level"] == "中风险"

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
                "evidence_id": "B001",
                "evidence_type": "business",
                "data": {"event_type": "经营异常"},
            },
        ]
        result = engine.evaluate(facts, {})
        # 40 + 25 + 30 = 95 分，应该在高风险区间（71-120）
        assert result["risk_score"] == 95
        assert result["risk_level"] == "高风险"

    def test_major_risk(self, engine):
        """超高分→重大风险。"""
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
        # 40 + 25 + 25 + 30 + 20 = 140 分，应该在重大风险区间（121+）
        assert result["risk_score"] == 140
        assert result["risk_level"] == "重大风险"


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
        config2["dimension_weights"] = {**config["dimension_weights"], "judicial": 70}
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

        # 修改 J001 的分数从 40 改为 60
        for rule in config["rules"]:
            if rule["id"] == "J001":
                rule["score"] = 60
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
        assert result["risk_score"] == 60


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
    """验证 inject_risk_level_into_report 确定性注入。"""

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
# 12. Company-Level 规则不再重复计分
# ------------------------------------------------------------

class TestCompanyLevelDedup:
    """验证 company-level 规则（使用 extra）每个 owner_company_id 只触发一次。"""

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


# ============================================================
# V3.0: F005 审计意见 canonical value 修复测试
# ============================================================
class TestF005AuditOpinionNormalization:
    """V3.0: F005 使用 canonical English values 判断审计意见。"""

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
# V3.0: Own/Related Evidence Separation 测试
# ============================================================
class TestOwnRelatedSeparation:
    """V3.0: Own/Related Evidence Separation 测试。"""

    def test_own_risk_only_includes_target_company(self, engine):
        """own_risk 只包含目标企业的 evidence。"""
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

        result = engine.evaluate(facts, {})

        # own_risk 只包含 C001 的 B001
        own_rules = [r["rule_id"] for r in result["own_risk"]["triggered_rules"]]
        assert "B001" in own_rules
        assert result["own_risk"]["score"] == 30

        # related_risk_facts 包含 C002 的 J001
        assert len(result["related_risk_facts"]) == 1
        assert result["related_risk_facts"][0]["company_id"] == "C002"

    def test_c001_c004_c007_own_risk(self, engine):
        """C001/C004/C007 Own Risk 测试。"""
        # C001: 健康公司
        c001_facts = [
            {"evidence_id": "F001", "evidence_type": "financial",
             "data": {"audit_opinion": "unqualified", "period": "2025FY"},
             "company_id": "C001"},
        ]
        c001_extra = {"debt_ratio": 0.34, "consecutive_loss_years": 0,
                      "latest_operating_cash_flow": 19000000, "recruitment_count": 4}
        r1 = engine.evaluate(c001_facts, c001_extra)
        assert r1["risk_score"] == 0, f"C001 own_score 应为 0, 实际 {r1['risk_score']}"
        assert r1["risk_level"] == "低风险"

        # C004: 健康公司（仅 1 条未核实负面舆情）
        c004_facts = [
            {"evidence_id": "P001", "evidence_type": "public_opinion",
             "data": {"sentiment": "negative", "verification_status": "partially_verified"},
             "company_id": "C004"},
        ]
        c004_extra = {"debt_ratio": 0.34, "consecutive_loss_years": 0,
                      "latest_operating_cash_flow": 42000000, "recruitment_count": 3}
        r4 = engine.evaluate(c004_facts, c004_extra)
        assert r4["risk_score"] == 5, f"C004 own_score 应为 5, 实际 {r4['risk_score']}"
        assert r4["risk_level"] == "低风险"

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
        r7 = engine.evaluate(c007_facts, c007_extra)
        # C007 的分数：J001(25) + J002(25) + J003(25) + J004(25) + B001(30) + B002(15) + F001(15) + F003(20) + F004(10) + P001(20) + P002*4(20) = 235
        # 加上 F005(20) 和 company-level rules
        assert r7["risk_score"] >= 200, f"C007 own_score 应 >= 200, 实际 {r7['risk_score']}"
        assert r7["risk_level"] in ["高风险", "重大风险"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])