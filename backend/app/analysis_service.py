"""
企业关联风险智能洞察系统 —— 风险分析服务层。

编排一次完整的风险分析流程：
1. 规范化 company_id 并做存在性检查（复用 src/risk_tools.get_company_profile）；
2. 调用 harness_adapter.run_harness_analysis 触发真实 Risk Harness；
3. best-effort 结构化解析（风险等级 / 风险总结 / 证据编号 / 关联企业），
   解析失败不影响主流程，对应字段为 None / 空列表；
4. 将运行记录保存到 runs/web/<company_id>/（UTF-8）；
5. 返回完整响应 dict（供 api.py 包装为 AnalysisResponse）。

注意：本模块不复制任何 Harness 逻辑，不硬编码风险判断；
风险分析完全由 Risk Harness（opencode headless）完成。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import deps
from .deps import PROJECT_ROOT, company_exists
from .harness_adapter import CompanyNotFoundError, run_harness_analysis

logger = logging.getLogger("risk-api")

# ------------------------------------------------------------
# 运行记录保存目录：runs/web/<company_id>/
# （与第一阶段 runs/C001-C005 目录隔离，不触碰旧目录）
# ------------------------------------------------------------

RUNS_WEB_ROOT = PROJECT_ROOT / "runs" / "web"

# ------------------------------------------------------------
# best-effort 结构化解析正则
# ------------------------------------------------------------

# 风险等级解析（best-effort），按优先级排列：
#   1. 明确格式："风险等级评定：xxx"（最高优先）
#   2. 报告表格中"目标企业"行：如 "| C001（目标企业）| 高风险 | ... |"
#   3. 综合风险评级/等级行：如 "综合风险评级：中等偏高（中高）"（C001 类报告）
#   4. 其他兜底："风险等级：xxx"（C004/C005 类报告）
# 捕获统一限制 1-20 字符（表格单元格 1-12 字符），
# 字符集排除竖线/括号/句尾标点等噪音，配合 _strip_noise() 清洗。
RISK_LEVEL_PATTERNS = [
    re.compile(r"风险等级评定[：:]\s*([^\n|（(。．；;！!，,]{1,20})"),
    re.compile(r"\|\s*[^|]*?(?:（目标企业）|目标企业)[^|]*\|\s*([^\n|]{1,12})\s*\|"),
    re.compile(r"综合风险(?:评级|等级)[：:]\s*([^\n|（(。．；;！!，,]{1,20})"),
    re.compile(r"风险等级[：:]\s*([^\n|（(。．；;！!，,]{1,20})"),
]

# 风险总结章节：从"风险总结"章节标题开始，切到下一章节（六/关键证据索引）或结尾
SUMMARY_PATTERN = re.compile(
    r"(?:五、风险总结|##\s*五|###\s*5\.\d?\s*风险总结)[\s\S]*?(?=##\s*六|关键证据索引|$)"
)

# 关键证据编号：Bxxx / Jxxx / Rxxx
EVIDENCE_ID_PATTERN = re.compile(r"\b([BJR]\d{3})\b")

# 关联企业ID：Cxxx（负向后顾排除 SYN-C001 之类的信用代码片段误匹配）
COMPANY_ID_PATTERN = re.compile(r"(?<![A-Za-z0-9-])(C\d{3})\b")

# 无风险总结章节时的摘要兜底长度
SUMMARY_FALLBACK_CHARS = 500


# ------------------------------------------------------------
# best-effort 结构化解析
# ------------------------------------------------------------


def _extract_risk_level(report: str) -> Optional[str]:
    """
    提取风险等级（best-effort），按优先级：

    1. 明确格式："风险等级评定：xxx"
    2. 报告表格中"目标企业"行（如 "| C001（目标企业）| 高风险 | ... |"）
    3. 综合风险评级/等级行（如 "综合风险评级：中等偏高（中高）"）
    4. 其他兜底："风险等级：xxx"

    捕获结果经 _normalize_level() 清洗（去 markdown 加粗符、去句尾噪音、
    限制长度），全部失败返回 None（前端有兜底展示）。
    """
    if not report:
        return None

    for pattern in RISK_LEVEL_PATTERNS:
        m = pattern.search(report)
        if m:
            level = _normalize_level(m.group(1))
            if level:
                return level

    return None


def _strip_noise(text: str) -> str:
    """
    清洗风险等级捕获文本中的噪音：
    - 首尾空白
    - 全部 markdown 加粗符 **（如 "**高**" → "高"、"**较高**风险**" → "较高风险"）
    - 句尾标点/竖线/星号（如 "中低**。" → "中低"）
    """
    text = text.strip().replace("**", "")
    return text.rstrip("。．.！!；;：:、，,*#-| \t")


def _normalize_level(level: str) -> Optional[str]:
    """
    归一化风险等级文本：去噪音后校验长度（1-20 字符）。

    纯等级词（低/中/高 单字或两字组合，如 高/中低/中高）追加"风险"后缀，
    保证输出风格统一（"高风险"、"中低风险"）；带修饰词（如"中等偏高"、
    "较高"）保持原样。
    """
    level = _strip_noise(level)
    if not level or not (1 <= len(level) <= 20):
        return None
    if re.fullmatch(r"[低中高]{1,2}", level):
        # 纯等级词（低/中/高 单字或两字组合）：追加"风险"后缀统一风格
        return level + "风险"
    if re.fullmatch(r"[低中高]{3,}", level):
        # 无意义的重复串（如"高高高..."），视为噪音
        return None
    return level


def _extract_summary(report: str) -> Optional[str]:
    """
    提取"风险总结"章节文本（best-effort）。

    匹配到章节则返回章节原文（到下一章节或结尾）；
    匹配失败返回报告前 500 字符作为兜底摘要。
    """
    if not report:
        return None

    m = SUMMARY_PATTERN.search(report)
    if m:
        text = m.group(0).strip()
        if text:
            return text

    return report[:SUMMARY_FALLBACK_CHARS]


def _extract_evidence_ids(report: str) -> List[str]:
    """
    提取关键证据编号（Bxxx/Jxxx/Rxxx），去重并保持出现顺序。
    """
    ids: List[str] = []
    seen = set()
    if report:
        for m in EVIDENCE_ID_PATTERN.finditer(report):
            eid = m.group(1)
            if eid not in seen:
                seen.add(eid)
                ids.append(eid)
    return ids


def _extract_related_companies(report: str, target: str) -> List[str]:
    """
    提取报告涉及的关联企业ID（Cxxx），去重、保持出现顺序并排除目标企业自身。
    """
    ids: List[str] = []
    seen = set()
    if report:
        for m in COMPANY_ID_PATTERN.finditer(report):
            cid = m.group(1)
            if cid == target or cid in seen:
                continue
            seen.add(cid)
            ids.append(cid)
    return ids


# ------------------------------------------------------------
# 运行记录持久化
# ------------------------------------------------------------


def _save_run_records(
    company_id: str, harness_result: Dict[str, Any], response: Dict[str, Any]
) -> Optional[Path]:
    """
    将一次分析的运行记录保存到 runs/web/<company_id>/：

    - analysis_result.json ：最终结构化结果（report_path 与 API 响应一致）
    - session_events.jsonl ：raw_events 完整事件流（每行一个 JSON）
    - process.md           ：分析过程文本
    - report_final.md      ：最终报告（仅当报告非空）

    注意：先计算 report_path 并回填 response["report_path"]，
    再序列化 analysis_result.json —— 保证落盘 JSON 与 API 响应字段一致。

    返回报告文件路径（报告为空时返回 None）。
    """
    run_dir = RUNS_WEB_ROOT / company_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # 1. 先落盘 report_final.md 并回填 response["report_path"]
    report = (harness_result.get("report") or "").strip()
    report_path: Optional[Path] = None
    if report:
        report_path = run_dir / "report_final.md"
        report_path.write_text(report, encoding="utf-8")
        response["report_path"] = str(report_path.relative_to(PROJECT_ROOT))
    else:
        response["report_path"] = None
        logger.warning("报告为空，跳过 report_final.md: %s", company_id)

    # 2. 再序列化 analysis_result.json（此时 report_path 已就绪）
    (run_dir / "analysis_result.json").write_text(
        json.dumps(response, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 3. 其余记录文件
    with (run_dir / "session_events.jsonl").open("w", encoding="utf-8") as fh:
        for ev in harness_result.get("raw_events", []):
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")

    process_text = (harness_result.get("process_text") or "").strip()
    (run_dir / "process.md").write_text(process_text, encoding="utf-8")

    return report_path


# ------------------------------------------------------------
# 服务入口
# ------------------------------------------------------------


def analyze_company(company_id: str) -> Dict[str, Any]:
    """
    对指定企业执行一次完整风险分析（同步阻塞，实测耗时 3-20 分钟；
    复杂案例如 C005 需多轮 verifier 复核，可达 10-20 分钟）。

    返回响应 dict：
        {
            "company_id": str,
            "status": "completed",
            "report": str,
            "verification_status": "PASS" | "UNRESOLVED" | None,
            "risk_level": Optional[str],
            "summary": Optional[str],
            "evidence_ids": List[str],
            "related_companies": List[str],
            "report_path": Optional[str],   # 相对项目根路径 runs/web/<id>/report_final.md
            "duration_seconds": float,
        }

    异常：
        CompanyNotFoundError —— 企业不存在
        HarnessError         —— Harness 调用失败（由 api.py 转 503）
    """
    cid = company_id.strip().upper()

    # 1. 存在性检查（复用 src/risk_tools.get_company_profile，不写 SQL）
    if not company_exists(cid):
        raise CompanyNotFoundError(cid)

    # 2. 调用真实 Risk Harness（opencode headless）
    harness_result = run_harness_analysis(cid)

    # 3. best-effort 结构化解析
    report = (harness_result.get("report") or "").strip()
    response: Dict[str, Any] = {
        "company_id": cid,
        "status": "completed",
        "report": report,
        "verification_status": harness_result.get("verification_status"),
        "risk_level": _extract_risk_level(report),
        "summary": _extract_summary(report),
        "evidence_ids": _extract_evidence_ids(report),
        "related_companies": _extract_related_companies(report, cid),
        "report_path": None,
        "duration_seconds": harness_result.get("duration_seconds", 0.0),
    }

    # 4. 保存运行记录（内部会回填 response["report_path"]）
    _save_run_records(cid, harness_result, response)

    logger.info(
        "分析完成: %s status=%s risk=%s evidence=%d related=%d 耗时=%ss",
        cid,
        response["verification_status"],
        response["risk_level"],
        len(response["evidence_ids"]),
        len(response["related_companies"]),
        response["duration_seconds"],
    )

    return response
