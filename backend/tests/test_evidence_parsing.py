"""
MarkdownReport Evidence ID 解析测试。

验证所有格式的 Evidence ID 均可被识别和点击。
"""

import re
import sys
from pathlib import Path

# ------------------------------------------------------------
# 复制前端的正则表达式用于测试
# ------------------------------------------------------------

# 匹配单个 Evidence ID（带可选括号或加粗标记）
EVIDENCE_ID_PATTERN = re.compile(r'[\(（]?\*{0,2}([BJR]\d{3})\*{0,2}[\)）]?')


def extract_evidence_ids(text: str) -> list[str]:
    """从文本中提取所有 Evidence ID（支持斜杠分隔的多个 ID）。"""
    # 收集所有匹配位置
    all_matches = []

    for match in EVIDENCE_ID_PATTERN.finditer(text):
        all_matches.append({
            'index': match.start(),
            'length': len(match.group(0)),
            'id': match.group(1),
        })

    # 按索引排序
    all_matches.sort(key=lambda x: x['index'])

    # 合并相邻的 ID（用斜杠分隔的）
    merged = []
    i = 0
    while i < len(all_matches):
        current = all_matches[i]
        group_ids = [current['id']]
        group_end = current['index'] + current['length']

        # 检查后续的 ID 是否与当前 ID 相邻（用斜杠分隔）
        while i + 1 < len(all_matches):
            next_match = all_matches[i + 1]
            # 检查两个 ID 之间是否只有斜杠和空白
            between = text[group_end:next_match['index']]
            if re.match(r'^\s*/\s*$', between):
                group_ids.append(next_match['id'])
                group_end = next_match['index'] + next_match['length']
                i += 1
            else:
                break

        merged.append(group_ids)
        i += 1

    # 去重并保持顺序
    seen = set()
    result = []
    for group in merged:
        for eid in group:
            if eid not in seen:
                result.append(eid)
                seen.add(eid)

    return result


# ------------------------------------------------------------
# 测试用例
# ------------------------------------------------------------

TEST_CASES = [
    # 格式1: 裸 ID
    ("B009：股东变更", ["B009"]),
    ("B010 行政处罚", ["B010"]),
    ("B011 经营异常", ["B011"]),

    # 格式2: 中文括号
    ("股东变更（B009）", ["B009"]),
    ("（J007）裁判文书", ["J007"]),
    ("（R010）共同股东", ["R010"]),

    # 格式3: 英文括号
    ("(B009) 股东变更", ["B009"]),
    ("(J007) 裁判文书", ["J007"]),
    ("(R010) 共同股东", ["R010"]),

    # 格式4: Markdown 加粗
    ("**B009** 股东变更", ["B009"]),
    ("**J007** 裁判文书", ["J007"]),
    ("**R010** 共同股东", ["R010"]),

    # 格式5: 斜杠分隔的多个 ID
    ("J008/J009/J010/J011", ["J008", "J009", "J010", "J011"]),
    ("B008/B009/B010", ["B008", "B009", "B010"]),
    ("R005/R006/R007", ["R005", "R006", "R007"]),

    # 格式6: 混合格式
    ("**J007**（被告）和**B009**（股东变更）", ["J007", "B009"]),
    ("R005）持有R006）30%股权", ["R005", "R006"]),
]


def test_pattern_matching():
    """测试正则表达式匹配。"""
    print("=" * 60)
    print("Testing Evidence ID Pattern Matching")
    print("=" * 60)

    all_passed = True
    for text, expected_ids in TEST_CASES:
        actual_ids = extract_evidence_ids(text)
        passed = actual_ids == expected_ids
        status = "✓" if passed else "✗"

        print(f"\n{status} Input: {text}")
        print(f"  Expected: {expected_ids}")
        print(f"  Actual:   {actual_ids}")

        if not passed:
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("✓ All pattern matching tests passed!")
    else:
        print("✗ Some tests failed!")
    print("=" * 60)

    return all_passed


def test_report_parsing():
    """测试实际报告文件的解析。"""
    print("\n" + "=" * 60)
    print("Testing Report File Parsing")
    print("=" * 60)

    report_files = [
        "runs/web/C005/report_final.md",
        "runs/web/C006/report_final.md",
        "runs/web/C007/report_final.md",
    ]

    target_ids = {"B009", "B010", "B011", "J007", "J008", "R005", "R010"}

    for report_file in report_files:
        file_path = Path(__file__).parent.parent.parent / report_file
        if not file_path.exists():
            print(f"\n⚠ File not found: {report_file}")
            continue

        content = file_path.read_text(encoding="utf-8")
        found_ids = set(extract_evidence_ids(content))

        print(f"\n{report_file}:")
        print(f"  Total IDs found: {len(found_ids)}")

        # 检查目标 ID
        missing = target_ids - found_ids
        if missing:
            print(f"  ✗ Missing target IDs: {sorted(missing)}")
        else:
            print(f"  ✓ All target IDs found: {sorted(target_ids & found_ids)}")

    print("\n" + "=" * 60)
    print("✓ Report parsing test completed!")
    print("=" * 60)


def test_specific_evidence_ids():
    """测试特定 Evidence ID 的可访问性。"""
    print("\n" + "=" * 60)
    print("Testing Specific Evidence IDs")
    print("=" * 60)

    # 添加 backend 到 sys.path
    backend_dir = Path(__file__).resolve().parent.parent
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    try:
        from app.evidence_registry import get_evidence_by_id

        test_ids = ["B009", "B010", "B011", "J007", "J008", "R005", "R010"]

        for eid in test_ids:
            result = get_evidence_by_id(eid)
            if result:
                print(f"✓ {eid}: {result['evidence_type']} - {result['company_name']}")
            else:
                print(f"✗ {eid}: NOT FOUND")

        print("\n" + "=" * 60)
        print("✓ Specific evidence IDs test completed!")
        print("=" * 60)

    except ImportError as e:
        print(f"\n⚠ Cannot import evidence_registry: {e}")
        print("  Skipping evidence registry test")


if __name__ == "__main__":
    pattern_ok = test_pattern_matching()
    test_report_parsing()
    test_specific_evidence_ids()

    if pattern_ok:
        print("\n✓ All tests passed!")
        sys.exit(0)
    else:
        print("\n✗ Some tests failed!")
        sys.exit(1)
