"""V2.4.1 Comprehensive Risk Fusion Engine 测试。"""
import sys
from pathlib import Path

import pytest

# 确保 backend/app 在路径中
BACKEND_APP = Path(__file__).resolve().parent.parent / "backend" / "app"
if str(BACKEND_APP) not in sys.path:
    sys.path.insert(0, str(BACKEND_APP))

from comprehensive_risk_engine import (
    classify_case,
    compute_comprehensive_risk,
    get_comprehensive_config_hash,
    load_comprehensive_config,
)


class TestComprehensiveRiskConfig:
    """配置加载测试。"""

    def test_config_loads(self):
        """配置文件可以正常加载。"""
        config = load_comprehensive_config()
        assert config["version"] == "1.0.0"
        assert config["fusion_strategy"] == "max_dominant_with_bonus"
        assert "high_threshold" in config
        assert "case_bonuses" in config
        assert "comprehensive_levels" in config
        assert "hard_rule_override" in config

    def test_config_hash_deterministic(self):
        """配置 hash 是确定性的。"""
        config = load_comprehensive_config()
        h1 = get_comprehensive_config_hash(config)
        h2 = get_comprehensive_config_hash(config)
        assert h1 == h2
        assert len(h1) == 16


class TestCaseClassification:
    """Case 判定测试。"""

    def _make_contributions(self, company_id, own_score, transmitted_score):
        """辅助：构建 company_contributions 条目。"""
        return [{
            "company_id": company_id,
            "company_name": f"Test {company_id}",
            "own_score": own_score,
            "transmitted_score": transmitted_score,
            "strongest_path": None,
        }]

    def test_case_d_both_low(self):
        """Case D: own low + exposure low。"""
        contributions = self._make_contributions("C01", 0, 0)
        case = classify_case(own_score=0, exposure_score=0, contributions=contributions,
                             high_threshold={"own_score": 50, "exposure_score": 50})
        assert case == "D"

    def test_case_c_high_own_low_exposure(self):
        """Case C: own high + exposure low。"""
        contributions = self._make_contributions("C01", 0, 0)
        case = classify_case(own_score=100, exposure_score=0, contributions=contributions,
                             high_threshold={"own_score": 50, "exposure_score": 50})
        assert case == "C"

    def test_case_b_low_own_high_exposure(self):
        """Case B: own low + exposure high (by score)。"""
        contributions = self._make_contributions("C01", 0, 0)
        case = classify_case(own_score=0, exposure_score=60, contributions=contributions,
                             high_threshold={"own_score": 50, "exposure_score": 50})
        assert case == "B"

    def test_case_b_via_transmission_source(self):
        """Case B: own low + exposure low score but high risk source。"""
        # exposure_score < 50，但存在高风险传导源
        contributions = self._make_contributions("C07", 300, 44)
        case = classify_case(own_score=5, exposure_score=44, contributions=contributions,
                             high_threshold={"own_score": 50, "exposure_score": 50})
        assert case == "B"

    def test_case_a_both_high(self):
        """Case A: own high + exposure high。"""
        contributions = self._make_contributions("C01", 100, 80)
        case = classify_case(own_score=100, exposure_score=80, contributions=contributions,
                             high_threshold={"own_score": 50, "exposure_score": 50})
        assert case == "A"

    def test_case_b_source_not_enough(self):
        """Case D: own low + exposure low + source own_score < threshold。"""
        # source own_score=30 < 50，不算传染通道
        contributions = self._make_contributions("C01", 30, 20)
        case = classify_case(own_score=5, exposure_score=20, contributions=contributions,
                             high_threshold={"own_score": 50, "exposure_score": 50})
        assert case == "D"

    def test_case_b_source_zero_transmitted(self):
        """Case D: source exists but transmitted_score=0。"""
        # source own_score=300 >= 50，但 transmitted_score=0
        contributions = self._make_contributions("C07", 300, 0)
        case = classify_case(own_score=5, exposure_score=0, contributions=contributions,
                             high_threshold={"own_score": 50, "exposure_score": 50})
        assert case == "D"


class TestComprehensiveRiskC001:
    """C001 模拟：Case D (both low)。"""

    def test_c001_comprehensive_risk(self):
        own_risk = {"score": 0, "level": "低风险", "hard_rule_hits": []}
        exposure = {
            "score": 0,
            "level": "低风险",
            "company_contributions": [],
        }

        result = compute_comprehensive_risk(own_risk, exposure)

        assert result["score"] == 0
        assert result["level"] == "低风险"
        assert result["case"] == "D"
        assert result["case_label"] == "低风险"
        assert result["fusion_trace"]["case_bonus"] == 0
        assert result["fusion_trace"]["has_hard_rule_override"] is False
        assert "max(0, 0)" in result["fusion_trace"]["formula"]
        assert "低风险" in result["explanation"]


class TestComprehensiveRiskC004:
    """C004 模拟：Case B (传染风险)。"""

    def test_c004_comprehensive_risk(self):
        own_risk = {"score": 5, "level": "低风险", "hard_rule_hits": []}
        exposure = {
            "score": 44,
            "level": "低风险",
            "company_contributions": [{
                "company_id": "C007",
                "company_name": "鼎峰建设工程有限公司",
                "own_score": 300,
                "transmitted_score": 44,
                "strongest_path": {
                    "path": ["C004", "C005", "C006", "C007"],
                    "depth": 3,
                    "relation_types": ["股权", "对外投资", "股权"],
                    "target_role": "shareholder",
                },
            }],
        }

        result = compute_comprehensive_risk(own_risk, exposure)

        assert result["case"] == "B"
        assert result["case_label"] == "传染风险"
        assert result["score"] == 54  # max(5, 44) + 10
        assert result["level"] == "中风险"
        assert result["fusion_trace"]["case_bonus"] == 10
        assert result["fusion_trace"]["max_component"] == "exposure"
        assert result["fusion_trace"]["has_hard_rule_override"] is False
        assert "max(5, 44)" in result["fusion_trace"]["formula"]
        assert "C007" in result["explanation"] or "鼎峰" in result["explanation"]


class TestComprehensiveRiskC007:
    """C007 模拟：Case C (孤立风险) + 硬规则覆盖。"""

    def test_c007_comprehensive_risk(self):
        own_risk = {
            "score": 300,
            "level": "高风险",
            "hard_rule_hits": ["HR002", "HR003"],
        }
        exposure = {
            "score": 1,
            "level": "低风险",
            "company_contributions": [{
                "company_id": "C004",
                "company_name": "新源新能源材料有限公司",
                "own_score": 5,
                "transmitted_score": 1,
                "strongest_path": None,
            }],
        }

        result = compute_comprehensive_risk(own_risk, exposure)

        assert result["case"] == "C"
        assert result["case_label"] == "孤立风险"
        assert result["score"] == 300  # hard_rule_override: own_score
        assert result["level"] == "高风险"
        assert result["fusion_trace"]["has_hard_rule_override"] is True
        assert "hard_rule_override" in result["fusion_trace"]["formula"]
        assert "高风险" in result["explanation"]


class TestComprehensiveRiskCaseA:
    """Case A 模拟：双重风险。"""

    def test_case_a_dual_high(self):
        own_risk = {"score": 100, "level": "高风险", "hard_rule_hits": []}
        exposure = {
            "score": 120,
            "level": "中高风险",
            "company_contributions": [{
                "company_id": "C07",
                "company_name": "Test Co",
                "own_score": 200,
                "transmitted_score": 120,
                "strongest_path": None,
            }],
        }

        result = compute_comprehensive_risk(own_risk, exposure)

        assert result["case"] == "A"
        assert result["case_label"] == "双重风险"
        assert result["score"] == 140  # max(100, 120) + 20
        assert result["fusion_trace"]["case_bonus"] == 20
        assert result["fusion_trace"]["max_component"] == "exposure"
        assert result["case_label"] == "双重风险"


class TestHardRuleOverride:
    """硬规则覆盖测试。"""

    def test_bankruptcy_override(self):
        """HR001 (bankruptcy) 触发覆盖。"""
        own_risk = {"score": 50, "level": "中风险", "hard_rule_hits": ["HR001"]}
        exposure = {
            "score": 100,
            "level": "中高风险",
            "company_contributions": [{
                "company_id": "C01",
                "company_name": "Test",
                "own_score": 200,
                "transmitted_score": 100,
                "strongest_path": None,
            }],
        }

        result = compute_comprehensive_risk(own_risk, exposure)

        # 硬规则覆盖：使用 own_risk 的分数和等级
        assert result["score"] == 50
        assert result["level"] == "中风险"
        assert result["fusion_trace"]["has_hard_rule_override"] is True
        assert result["fusion_trace"]["case_bonus"] == 0

    def test_dishonest_execution_override(self):
        """HR002 (dishonest_execution) 触发覆盖。"""
        own_risk = {"score": 30, "level": "中风险", "hard_rule_hits": ["HR002"]}
        exposure = {"score": 0, "level": "低风险", "company_contributions": []}

        result = compute_comprehensive_risk(own_risk, exposure)

        assert result["score"] == 30
        assert result["level"] == "中风险"
        assert result["fusion_trace"]["has_hard_rule_override"] is True

    def test_no_override_for_non_listed_rules(self):
        """不在列表中的硬规则不触发覆盖。"""
        own_risk = {"score": 30, "level": "中风险", "hard_rule_hits": ["HR999"]}
        exposure = {"score": 0, "level": "低风险", "company_contributions": []}

        result = compute_comprehensive_risk(own_risk, exposure)

        assert result["fusion_trace"]["has_hard_rule_override"] is False
        # 正常融合：max(30, 0) + 0 = 30
        assert result["score"] == 30

    def test_no_hard_rules(self):
        """没有硬规则命中时，正常融合。"""
        own_risk = {"score": 100, "level": "高风险", "hard_rule_hits": []}
        exposure = {"score": 80, "level": "中高风险", "company_contributions": [{
            "company_id": "C01",
            "company_name": "Test",
            "own_score": 150,
            "transmitted_score": 80,
            "strongest_path": None,
        }]}

        result = compute_comprehensive_risk(own_risk, exposure)

        assert result["fusion_trace"]["has_hard_rule_override"] is False
        # Case A: max(100, 80) + 20 = 120
        assert result["score"] == 120


class TestEdgeCases:
    """边界条件测试。"""

    def test_zero_scores(self):
        """双零输入。"""
        own_risk = {"score": 0, "level": "低风险", "hard_rule_hits": []}
        exposure = {"score": 0, "level": "低风险", "company_contributions": []}

        result = compute_comprehensive_risk(own_risk, exposure)

        assert result["score"] == 0
        assert result["level"] == "低风险"
        assert result["case"] == "D"

    def test_negative_scores_clamped(self):
        """负分数被 clamp 到 0。"""
        own_risk = {"score": -10, "level": "低风险", "hard_rule_hits": []}
        exposure = {"score": -5, "level": "低风险", "company_contributions": []}

        result = compute_comprehensive_risk(own_risk, exposure)

        assert result["score"] == 0
        assert result["fusion_trace"]["own_score"] == 0
        assert result["fusion_trace"]["exposure_score"] == 0

    def test_large_scores(self):
        """超大分数正常处理。"""
        own_risk = {"score": 1000, "level": "高风险", "hard_rule_hits": []}
        exposure = {"score": 500, "level": "高风险", "company_contributions": []}

        result = compute_comprehensive_risk(own_risk, exposure)

        # Case A: max(1000, 500) + 20 = 1020
        assert result["score"] == 1020
        assert result["level"] == "高风险"
        assert result["case"] == "A"

    def test_missing_input_fields(self):
        """缺少字段时使用默认值。"""
        own_risk = {}
        exposure = {}

        result = compute_comprehensive_risk(own_risk, exposure)

        assert result["score"] == 0
        assert result["level"] == "低风险"
        assert result["case"] == "D"

    def test_fusion_trace_always_present(self):
        """fusion_trace 始终存在。"""
        own_risk = {"score": 50, "level": "中风险", "hard_rule_hits": []}
        exposure = {"score": 30, "level": "低风险", "company_contributions": []}

        result = compute_comprehensive_risk(own_risk, exposure)

        assert "fusion_trace" in result
        trace = result["fusion_trace"]
        assert "own_score" in trace
        assert "exposure_score" in trace
        assert "case_bonus" in trace
        assert "max_component" in trace
        assert "formula" in trace
        assert "has_hard_rule_override" in trace


class TestInvariants:
    """不变量测试。"""

    def test_i1_comprehensive_ge_own(self):
        """I-1: comprehensive_score >= own_score。"""
        own_risk = {"score": 100, "level": "高风险", "hard_rule_hits": []}
        exposure = {"score": 0, "level": "低风险", "company_contributions": []}

        result = compute_comprehensive_risk(own_risk, exposure)
        assert result["score"] >= own_risk["score"]

    def test_i2_comprehensive_ge_exposure(self):
        """I-2: comprehensive_score >= exposure_score。"""
        own_risk = {"score": 0, "level": "低风险", "hard_rule_hits": []}
        exposure = {"score": 100, "level": "中高风险", "company_contributions": [{
            "company_id": "C01", "company_name": "Test",
            "own_score": 200, "transmitted_score": 100,
            "strongest_path": None,
        }]}

        result = compute_comprehensive_risk(own_risk, exposure)
        assert result["score"] >= exposure["score"]

    def test_i3_hard_rule_no_downgrade(self):
        """I-3: 硬规则覆盖时，level 不降级。"""
        own_risk = {"score": 30, "level": "中风险", "hard_rule_hits": ["HR002"]}
        exposure = {"score": 200, "level": "高风险", "company_contributions": [{
            "company_id": "C01", "company_name": "Test",
            "own_score": 300, "transmitted_score": 200,
            "strongest_path": None,
        }]}

        result = compute_comprehensive_risk(own_risk, exposure)
        # 硬规则覆盖：level = own_risk.level
        assert result["level"] == "中风险"
        assert result["score"] == 30

    def test_i4_both_zero_implies_zero(self):
        """I-4: 双零则零。"""
        own_risk = {"score": 0, "level": "低风险", "hard_rule_hits": []}
        exposure = {"score": 0, "level": "低风险", "company_contributions": []}

        result = compute_comprehensive_risk(own_risk, exposure)
        assert result["score"] == 0

    def test_i6_trace_own_matches_input(self):
        """I-6: fusion_trace.own_score == own_risk.score。"""
        own_risk = {"score": 75, "level": "中高风险", "hard_rule_hits": []}
        exposure = {"score": 30, "level": "低风险", "company_contributions": []}

        result = compute_comprehensive_risk(own_risk, exposure)
        assert result["fusion_trace"]["own_score"] == 75

    def test_i7_trace_exposure_matches_input(self):
        """I-7: fusion_trace.exposure_score == exposure.score。"""
        own_risk = {"score": 10, "level": "低风险", "hard_rule_hits": []}
        exposure = {"score": 80, "level": "中高风险", "company_contributions": [{
            "company_id": "C01", "company_name": "Test",
            "own_score": 150, "transmitted_score": 80,
            "strongest_path": None,
        }]}

        result = compute_comprehensive_risk(own_risk, exposure)
        assert result["fusion_trace"]["exposure_score"] == 80

    def test_i8_version_and_hash_exist(self):
        """I-8: version 和 config_hash 存在。"""
        own_risk = {"score": 0, "level": "低风险", "hard_rule_hits": []}
        exposure = {"score": 0, "level": "低风险", "company_contributions": []}

        result = compute_comprehensive_risk(own_risk, exposure)
        assert result["version"] == "1.0.0"
        assert len(result["config_hash"]) == 16
