"""
Evidence Registry 测试。

验证所有 evidence ID 可以点击和返回详情。
"""

import sys
from pathlib import Path

# 添加 backend 目录到 sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.evidence_registry import get_evidence_by_id, get_all_evidence_ids


def test_evidence_registry_basic():
    """测试 Evidence Registry 基本功能。"""
    # 测试获取所有 evidence IDs
    all_ids = get_all_evidence_ids()
    assert len(all_ids) > 0, "应该有 evidence IDs"
    
    # 验证 ID 格式
    for eid in all_ids:
        assert len(eid) >= 2, f"ID {eid} 长度不足"
        assert eid[0] in ("B", "J", "R"), f"ID {eid} 格式无效"
        assert eid[1:].isdigit(), f"ID {eid} 数字部分无效"


def test_specific_evidence_ids():
    """测试特定 evidence ID（B009/B010/B011/J007/R006/R010）。"""
    test_cases = [
        ("B009", "business", "C006"),
        ("B010", "business", "C007"),
        ("B011", "business", "C007"),
        ("J007", "judicial", "C005"),
        ("R006", "relation", "C005"),
        ("R010", "relation", "C004"),
    ]
    
    for evidence_id, expected_type, expected_company_id in test_cases:
        result = get_evidence_by_id(evidence_id)
        assert result is not None, f"{evidence_id} 应该存在"
        assert result["evidence_id"] == evidence_id, f"ID 不匹配"
        assert result["evidence_type"] == expected_type, f"{evidence_id} 类型不匹配"
        assert result["company_id"] == expected_company_id, f"{evidence_id} company_id 不匹配"
        assert result["company_name"], f"{evidence_id} company_name 不能为空"
        assert result["data"], f"{evidence_id} data 不能为空"


def test_evidence_response_structure():
    """测试 evidence 响应结构。"""
    result = get_evidence_by_id("B009")
    assert result is not None
    
    # 验证必需字段
    required_fields = [
        "evidence_id",
        "evidence_type",
        "company_id",
        "company_name",
        "data",
        "source",
        "from_company_id",
        "from_company_name",
        "to_company_id",
        "to_company_name",
    ]
    for field in required_fields:
        assert field in result, f"缺少字段: {field}"


def test_relation_evidence_fields():
    """测试关系证据的额外字段。"""
    result = get_evidence_by_id("R006")
    assert result is not None
    assert result["evidence_type"] == "relation"
    
    # 关系类型应该有 from/to 字段
    assert result["from_company_id"] is not None, "from_company_id 不能为空"
    assert result["to_company_id"] is not None, "to_company_id 不能为空"
    assert result["from_company_name"] is not None, "from_company_name 不能为空"
    assert result["to_company_name"] is not None, "to_company_name 不能为空"


def test_nonexistent_evidence():
    """测试不存在的 evidence ID。"""
    result = get_evidence_by_id("B999")
    assert result is None, "不存在的 evidence 应该返回 None"
    
    result = get_evidence_by_id("J999")
    assert result is None, "不存在的 evidence 应该返回 None"
    
    result = get_evidence_by_id("R999")
    assert result is None, "不存在的 evidence 应该返回 None"


def test_invalid_evidence_format():
    """测试无效的 evidence ID 格式。"""
    result = get_evidence_by_id("X001")
    assert result is None, "无效格式应该返回 None"
    
    result = get_evidence_by_id("A001")
    assert result is None, "无效格式应该返回 None"


def test_all_evidence_ids_are_accessible():
    """测试所有 evidence ID 都可以访问。"""
    all_ids = get_all_evidence_ids()
    failed_ids = []
    
    for eid in all_ids:
        result = get_evidence_by_id(eid)
        if result is None:
            failed_ids.append(eid)
    
    assert len(failed_ids) == 0, f"以下 evidence IDs 无法访问: {failed_ids}"


if __name__ == "__main__":
    # 运行所有测试
    test_evidence_registry_basic()
    print("✓ test_evidence_registry_basic passed")
    
    test_specific_evidence_ids()
    print("✓ test_specific_evidence_ids passed")
    
    test_evidence_response_structure()
    print("✓ test_evidence_response_structure passed")
    
    test_relation_evidence_fields()
    print("✓ test_relation_evidence_fields passed")
    
    test_nonexistent_evidence()
    print("✓ test_nonexistent_evidence passed")
    
    test_invalid_evidence_format()
    print("✓ test_invalid_evidence_format passed")
    
    test_all_evidence_ids_are_accessible()
    print("✓ test_all_evidence_ids_are_accessible passed")
    
    print("\n✓ All tests passed!")
