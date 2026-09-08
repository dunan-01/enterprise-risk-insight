"""
V2.4.2 Integration Tests — Comprehensive Risk 集成验证。
"""
from __future__ import annotations

import pytest
from backend.app.comprehensive_risk_engine import compute_comprehensive_risk
from backend.app.report_postprocessor import inject_risk_level_into_report


class TestC001Integration:
    """C001: own=0, exposure=0 → Case D, 低风险"""

    def test_c001_comprehensive(self):
        own = {"score": 0, "level": "低风险", "hard_rule_hits": []}
        exposure = {"score": 0, "level": "低风险", "company_contributions": []}
        result = compute_comprehensive_risk(own, exposure)
        assert result["case"] == "D"
        assert result["score"] == 0
        assert result["level"] == "低风险"

    def test_c001_report_injection(self):
        report = "## 六、综合风险判断\n\n综合风险等级：待填充\n\n风险评分：待填充\n"
        result = inject_risk_level_into_report(report, "低风险", 0, case="D", explanation="低风险")
        assert "低风险" in result
        assert "风险模式：D" in result


class TestC004Integration:
    """C004: own=5, exposure=44 → Case B, 中风险"""

    def test_c004_comprehensive(self):
        own = {"score": 5, "level": "低风险", "hard_rule_hits": []}
        exposure = {"score": 44, "level": "中风险", "company_contributions": [
            {"company_id": "C007", "own_score": 50, "transmitted_score": 10, "depth": 1}
        ]}
        result = compute_comprehensive_risk(own, exposure)
        assert result["case"] == "B"
        assert result["score"] == 54  # max(5, 44) + 10
        assert result["level"] == "中风险"

    def test_c004_report_injection(self):
        report = "## 六、综合风险判断\n\n综合风险等级：待填充\n"
        result = inject_risk_level_into_report(report, "中风险", 54, case="B", explanation="传染风险")
        assert "中风险" in result
        assert "风险模式：B" in result


class TestC007Integration:
    """C007: own=300, exposure=1 → Case C, 高风险"""

    def test_c007_comprehensive(self):
        own = {"score": 300, "level": "高风险", "hard_rule_hits": ["HR001"]}
        exposure = {"score": 1, "level": "低风险", "company_contributions": []}
        result = compute_comprehensive_risk(own, exposure)
        assert result["case"] == "C"
        assert result["score"] == 300  # max(300, 1) + 0
        assert result["level"] == "高风险"

    def test_c007_report_injection(self):
        report = "## 六、综合风险判断\n\n综合风险等级：待填充\n"
        result = inject_risk_level_into_report(report, "高风险", 300, case="C", explanation="孤立风险")
        assert "高风险" in result
        assert "风险模式：C" in result


class TestReportPostprocessorV2:
    """验证 report_postprocessor 新增功能。"""

    def test_case_injection_in_existing_section(self):
        report = "综合风险等级：中风险\n\n风险评分：54\n"
        result = inject_risk_level_into_report(report, "中风险", 54, case="B")
        assert "风险模式：B（传染风险）" in result

    def test_explanation_injection(self):
        report = "综合风险等级：高风险\n"
        result = inject_risk_level_into_report(report, "高风险", 300, case="C", explanation="自身高风险，关联低风险")
        assert "风险解释：自身高风险，关联低风险" in result

    def test_no_case_no_explanation(self):
        """不传 case 和 explanation 时行为不变。"""
        report = "综合风险等级：低风险\n\n风险评分：0\n"
        result = inject_risk_level_into_report(report, "低风险", 0)
        assert "风险模式" not in result
        assert "风险解释" not in result
        assert "低风险" in result
        assert "0" in result
