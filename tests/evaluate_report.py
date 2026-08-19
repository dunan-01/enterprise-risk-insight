import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
GOLD_PATH = ROOT / "tests" / "gold_cases.json"


def load_gold_case(case_id):
    with open(GOLD_PATH, "r", encoding="utf-8") as f:
        cases = json.load(f)

    for case in cases:
        if case["case_id"] == case_id:
            return case

    raise ValueError(f"找不到 Gold Case: {case_id}")


def load_report(report_path):
    with open(report_path, "r", encoding="utf-8") as f:
        return f.read()


def extract_evidence_ids(text):
    """
    提取报告中出现的证据ID：
    B001 / J001 / R001 等
    """
    ids = re.findall(r"\b[BRJ]\d{3}\b", text)
    return set(ids)


def evaluate(case_id, report_path):
    gold = load_gold_case(case_id)
    report = load_report(report_path)

    # ------------------------------------------------
    # 1. Evidence Coverage
    # ------------------------------------------------

    required = set(gold.get("required_evidence", []))
    found_ids = extract_evidence_ids(report)

    matched = required & found_ids
    missing = required - found_ids

    evidence_recall = (
        len(matched) / len(required)
        if required else 1.0
    )

    # ------------------------------------------------
    # 2. Forbidden Claims
    # ------------------------------------------------

    forbidden_results = []

    for claim in gold.get("forbidden_claims", []):
        appeared = claim in report

        forbidden_results.append({
            "claim": claim,
            "appeared": appeared
        })

    forbidden_hits = [
        item for item in forbidden_results
        if item["appeared"]
    ]

    # ------------------------------------------------
    # 3. 输出
    # ------------------------------------------------

    print("=" * 70)
    print(f"Evaluation: {case_id}")
    print("=" * 70)

    print("\n[Evidence Coverage]")
    print(
        f"Required: {len(required)}"
    )
    print(
        f"Matched:  {len(matched)}"
    )
    print(
        f"Recall:   {evidence_recall:.2%}"
    )

    print("\nMatched Evidence:")
    for evidence_id in sorted(matched):
        print(f"  ✓ {evidence_id}")

    if missing:
        print("\nMissing Evidence:")
        for evidence_id in sorted(missing):
            print(f"  ✗ {evidence_id}")
    else:
        print("\nMissing Evidence: None")

    print("\n[Forbidden Claims]")

    if forbidden_hits:
        for item in forbidden_hits:
            print(f"  ✗ 出现禁止结论：{item['claim']}")
    else:
        print("  ✓ 未发现禁止结论")

    print("\n[Summary]")

    print(
        f"Evidence Recall: {evidence_recall:.2%}"
    )

    print(
        f"Forbidden Claim Hits: "
        f"{len(forbidden_hits)}"
    )


if __name__ == "__main__":

    if len(sys.argv) != 3:
        print(
            "用法：python tests/evaluate_report.py "
            "GC001 runs/C001_report.txt"
        )
        sys.exit(1)

    case_id = sys.argv[1]
    report_path = sys.argv[2]

    evaluate(case_id, report_path)