"""
C007 Parser Regression Test

使用 runs/web/C007/session_events.jsonl 作为 fixture，
验证 harness_adapter.py 的 parser 能正确解析报告。

测试项：
1. parser 成功恢复完整 report
2. verification_status == PASS
3. report 非空
4. report 包含 "鼎峰建设工程有限公司"
5. report 包含 "风险等级：高"
6. evidence 至少包含 B010 B011 J008 J009 J010 J011 R007 R008 R009
7. PASS + empty report 必须视为异常
"""

import json
import re
import sys
from pathlib import Path

# Add backend to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.harness_adapter import _extract_texts, _split_report, VERIFICATION_STATUS_PATTERN


def load_events(jsonl_path: Path) -> list:
    """Load events from JSONL file."""
    events = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        events.append(obj)
                except (json.JSONDecodeError, ValueError):
                    pass
    return events


def test_c007_parser():
    """Run C007 regression test."""
    jsonl_path = PROJECT_ROOT / "runs" / "web" / "C007" / "session_events.jsonl"
    
    print(f"Loading events from: {jsonl_path}")
    events = load_events(jsonl_path)
    print(f"Loaded {len(events)} events")
    
    # Extract texts
    texts = _extract_texts(events)
    print(f"Extracted {len(texts)} text events")
    
    # Join and split
    full_text = "\n\n".join(texts)
    report, process_text = _split_report(full_text)
    
    # Extract verification status
    matches = list(VERIFICATION_STATUS_PATTERN.finditer(full_text))
    verification_status = matches[0].group(1) if matches else None
    
    print(f"\n{'='*60}")
    print("C007 PARSER REGRESSION TEST RESULTS")
    print(f"{'='*60}")
    
    results = []
    
    # Test 1: verification_status == PASS
    test1 = verification_status == "PASS"
    results.append(("verification_status == PASS", test1, f"Got: {verification_status}"))
    print(f"{'✓' if test1 else '✗'} verification_status == PASS: {verification_status}")
    
    # Test 2: report 非空
    test2 = len(report) > 0
    results.append(("report 非空", test2, f"Length: {len(report)}"))
    print(f"{'✓' if test2 else '✗'} report 非空: {len(report)} chars")
    
    # Test 3: PASS + empty report 必须视为异常
    test3 = not (verification_status == "PASS" and len(report) == 0)
    results.append(("PASS + empty report 异常检查", test3, "PASS with empty report should not happen"))
    print(f"{'✓' if test3 else '✗'} PASS + empty report 异常检查: {'PASS' if test3 else 'FAIL'}")
    
    # Test 4: report 包含 "鼎峰建设工程有限公司"
    test4 = "鼎峰建设工程有限公司" in report
    results.append(("report 包含 鼎峰建设工程有限公司", test4, ""))
    print(f"{'✓' if test4 else '✗'} report 包含 '鼎峰建设工程有限公司': {test4}")
    
    # Test 5: report 包含 "风险等级"
    test5 = "风险等级" in report
    results.append(("report 包含 风险等级", test5, ""))
    print(f"{'✓' if test5 else '✗'} report 包含 '风险等级': {test5}")
    
    # Test 6: evidence 包含 required IDs
    evidence_pattern = re.compile(r"\b([BJR]\d{3})\b")
    evidence_ids = []
    seen = set()
    for m in evidence_pattern.finditer(report):
        eid = m.group(1)
        if eid not in seen:
            seen.add(eid)
            evidence_ids.append(eid)
    
    required_evidence = ["B010", "B011", "J008", "J009", "J010", "J011", "R007", "R008", "R009"]
    found_evidence = [e for e in required_evidence if e in evidence_ids]
    test6 = len(found_evidence) == len(required_evidence)
    results.append(("evidence 包含 required IDs", test6, f"Found {len(found_evidence)}/{len(required_evidence)}"))
    print(f"{'✓' if test6 else '✗'} evidence 包含 required IDs: {len(found_evidence)}/{len(required_evidence)}")
    if not test6:
        missing = [e for e in required_evidence if e not in evidence_ids]
        print(f"    Missing: {missing}")
    
    # Test 7: risk_level 提取
    risk_level_patterns = [
        re.compile(r"风险等级评定[：:]\s*([^\n|（(。．；;！!，,]{1,20})"),
        re.compile(r"\|\s*[^|]*?(?:（目标企业）|目标企业)[^|]*\|\s*([^\n|]{1,12})\s*\|"),
        re.compile(r"综合风险(?:评级|等级)[：:]\s*([^\n|（(。．；;！!，,]{1,20})"),
        re.compile(r"风险等级[：:]\s*([^\n|（(。．；;！!，,]{1,20})"),
    ]
    
    risk_level = None
    for pattern in risk_level_patterns:
        m = pattern.search(report)
        if m:
            level = m.group(1).strip().replace("**", "")
            level = level.rstrip("。．.！!；;：:、，,*#-| \t")
            if level and 1 <= len(level) <= 20:
                if re.fullmatch(r"[低中高]{1,2}", level):
                    risk_level = level + "风险"
                else:
                    risk_level = level
                break
    
    test7 = risk_level is not None and "高" in risk_level
    results.append(("risk_level 包含 '高'", test7, f"Got: {risk_level}"))
    print(f"{'✓' if test7 else '✗'} risk_level 包含 '高': {risk_level}")
    
    # Test 8: related_companies 提取
    company_pattern = re.compile(r"(?<![A-Za-z0-9-])(C\d{3})\b")
    related_companies = []
    seen_companies = set()
    for m in company_pattern.finditer(report):
        cid = m.group(1)
        if cid == "C007" or cid in seen_companies:
            continue
        seen_companies.add(cid)
        related_companies.append(cid)
    
    test8 = len(related_companies) > 0
    results.append(("related_companies 非空", test8, f"Count: {len(related_companies)}"))
    print(f"{'✓' if test8 else '✗'} related_companies 非空: {len(related_companies)}")
    
    # Summary
    print(f"\n{'='*60}")
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"TOTAL: {passed}/{total} tests passed")
    print(f"{'='*60}")
    
    # Generate report_final.md
    report_path = PROJECT_ROOT / "runs" / "web" / "C007" / "report_final.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\nGenerated report_final.md: {report_path}")
    
    return passed == total


if __name__ == "__main__":
    success = test_c007_parser()
    sys.exit(0 if success else 1)
