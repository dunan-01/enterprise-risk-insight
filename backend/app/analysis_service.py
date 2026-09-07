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
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import deps
from .deps import PROJECT_ROOT, company_exists
from .harness_adapter import CompanyNotFoundError, run_harness_analysis
from .risk_rule_engine import evaluate_risk, build_related_company_profiles, get_engine
from .report_postprocessor import inject_risk_level_into_report

logger = logging.getLogger("risk-api")

# ------------------------------------------------------------
# 运行记录保存目录：runs/web/<company_id>/
# （与第一阶段 runs/C001-C005 目录隔离，不触碰旧目录）
# ------------------------------------------------------------

RUNS_WEB_ROOT = PROJECT_ROOT / "runs" / "web"


def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 8601 字符串。"""
    return datetime.now(timezone.utc).isoformat()

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

# 关键证据编号：Bxxx / Jxxx / Rxxx / Pxxx / Fxxx / Hxxx
EVIDENCE_ID_PATTERN = re.compile(r"\b([BJRPFH]\d{3})\b")

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
    company_id: str,
    harness_result: Dict[str, Any],
    response: Dict[str, Any],
    task_id: Optional[str] = None,
    task_dir: Optional[Path] = None,
) -> Optional[Path]:
    """
    将一次分析的运行记录保存到 task 目录（source of truth）+ company-level（latest 兼容）。

    保存顺序：
    1. task 目录（runs/web/tasks/<task_id>/）—— 永久保留，不覆盖历史
    2. company-level（runs/web/<company_id>/）—— latest 兼容，可被下一次覆盖
    3. latest.json 指针 —— 指向最新 completed task

    文件清单：
    - task.json（已有，由 task_manager 维护）
    - session_events.jsonl（已有，由 harness_adapter 流式写入）
    - trace.json（由 trace parser 生成）
    - analysis_result.json
    - process.md
    - report_final.md

    返回报告文件路径（报告为空时返回 None）。
    """
    # V2.1 FIX: 使用 response["report"]（已含 Rule Engine 注入）而非 harness 原始 report
    report = (response.get("report") or "").strip()
    report_path: Optional[Path] = None

    # ============================================================
    # 1. 保存到 task 目录（source of truth）
    # ============================================================
    if task_dir is not None:
        task_dir.mkdir(parents=True, exist_ok=True)

        # report_final.md
        if report:
            report_path = task_dir / "report_final.md"
            report_path.write_text(report, encoding="utf-8")
            response["report_path"] = str(report_path.relative_to(PROJECT_ROOT))
        else:
            response["report_path"] = None
            logger.warning("报告为空，跳过 task report_final.md: %s", task_id)

        # analysis_result.json（包含 task_id）
        if task_id:
            response["task_id"] = task_id
        (task_dir / "analysis_result.json").write_text(
            json.dumps(response, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # process.md
        process_text = (harness_result.get("process_text") or "").strip()
        (task_dir / "process.md").write_text(process_text, encoding="utf-8")

        # session_events.jsonl（流式写入已有，此处兜底完整写入）
        events_file = task_dir / "session_events.jsonl"
        if not events_file.exists() or events_file.stat().st_size == 0:
            with events_file.open("w", encoding="utf-8") as fh:
                for ev in harness_result.get("raw_events", []):
                    fh.write(json.dumps(ev, ensure_ascii=False) + "\n")

        # trace.json（由 task_manager 在 completed 后生成，此处预留逻辑）
        # 实际生成在 task_manager._run_task_background completed 分支中

        logger.info(
            "[RunRecords] saved to task dir: %s files=%s",
            task_id,
            [f.name for f in task_dir.iterdir() if f.is_file()],
        )

    # ============================================================
    # 2. 同步到 company-level（latest compatibility）
    # ============================================================
    run_dir = RUNS_WEB_ROOT / company_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # report_final.md（company-level）
    if report:
        company_report_path = run_dir / "report_final.md"
        company_report_path.write_text(report, encoding="utf-8")
        if response.get("report_path") is None:
            response["report_path"] = str(company_report_path.relative_to(PROJECT_ROOT))

    # analysis_result.json（company-level，包含 task_id）
    (run_dir / "analysis_result.json").write_text(
        json.dumps(response, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # session_events.jsonl（company-level，覆盖为最新）
    with (run_dir / "session_events.jsonl").open("w", encoding="utf-8") as fh:
        for ev in harness_result.get("raw_events", []):
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")

    # process.md（company-level）
    process_text = (harness_result.get("process_text") or "").strip()
    (run_dir / "process.md").write_text(process_text, encoding="utf-8")

    # ============================================================
    # 3. latest.json 指针
    # ============================================================
    if task_id:
        latest_pointer = {
            "company_id": company_id,
            "latest_completed_task_id": task_id,
            "updated_at": _now_iso(),
        }
        (run_dir / "latest.json").write_text(
            json.dumps(latest_pointer, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(
            "[RunRecords] latest.json updated: company=%s task_id=%s",
            company_id, task_id,
        )

    return report_path


# ------------------------------------------------------------
# 读取已有分析结果
# ------------------------------------------------------------


class AnalysisNotFoundError(Exception):
    """指定企业的历史分析结果不存在。"""

    def __init__(self, company_id: str) -> None:
        super().__init__(f"未找到企业 {company_id} 的历史分析结果")
        self.company_id = company_id


def load_latest_analysis(company_id: str) -> Dict[str, Any]:
    """
    读取指定企业最近一次 Web 分析结果。

    读取路径优先级：
    1. runs/web/<company_id>/latest.json → 获取 latest_completed_task_id
    2. runs/web/tasks/<task_id>/analysis_result.json（source of truth）
    3. fallback: runs/web/<company_id>/analysis_result.json（company-level 兼容）

    返回响应 dict（与 POST /api/analysis 响应结构一致，包含 task_id）。

    异常：
        AnalysisNotFoundError —— 历史分析结果不存在
    """
    cid = company_id.strip().upper()
    company_dir = RUNS_WEB_ROOT / cid

    # 1. 尝试通过 latest.json 找到最新 completed task
    latest_json = company_dir / "latest.json"
    latest_task_id: Optional[str] = None
    if latest_json.exists():
        try:
            latest_data = json.loads(latest_json.read_text(encoding="utf-8"))
            latest_task_id = latest_data.get("latest_completed_task_id")
        except (json.JSONDecodeError, OSError):
            pass

    # 2. 如果有 latest_task_id，从 task 目录读取
    if latest_task_id:
        task_result_path = RUNS_WEB_ROOT / "tasks" / latest_task_id / "analysis_result.json"
        if task_result_path.exists():
            try:
                raw = task_result_path.read_text(encoding="utf-8")
                result = json.loads(raw)
                # 确保 task_id 存在
                if "task_id" not in result:
                    result["task_id"] = latest_task_id
                # 补充 report（如果为空）
                report = result.get("report") or ""
                if not report.strip():
                    task_report = RUNS_WEB_ROOT / "tasks" / latest_task_id / "report_final.md"
                    if task_report.exists():
                        try:
                            report = task_report.read_text(encoding="utf-8")
                            result["report"] = report
                        except OSError:
                            pass
                if report.strip():
                    logger.info(
                        "加载 latest task 分析结果: %s task_id=%s risk=%s status=%s",
                        cid, latest_task_id,
                        result.get("risk_level"),
                        result.get("verification_status"),
                    )
                    return result
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("读取 task analysis_result.json 失败: %s", exc)

    # 3. fallback: company-level analysis_result.json
    result_path = company_dir / "analysis_result.json"
    if not result_path.exists():
        raise AnalysisNotFoundError(cid)

    try:
        raw = result_path.read_text(encoding="utf-8")
        result = json.loads(raw)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("读取 analysis_result.json 失败: %s", exc)
        raise AnalysisNotFoundError(cid) from exc

    # 如果 report 为空但 report_final.md 存在，从文件补充
    report = result.get("report") or ""
    if not report.strip():
        report_path = company_dir / "report_final.md"
        if report_path.exists():
            try:
                report = report_path.read_text(encoding="utf-8")
                result["report"] = report
            except OSError:
                logger.warning("读取 report_final.md 失败: %s", cid)

    # 如果 report 仍然为空，视为异常
    if not report.strip():
        logger.warning("企业 %s 的分析结果中 report 为空", cid)
        raise AnalysisNotFoundError(cid)

    # 如果 task_id 不存在，尝试从 tasks 目录中查找匹配的任务
    if "task_id" not in result or result.get("task_id") is None:
        result["task_id"] = _find_task_id_for_company(cid)

    logger.info(
        "加载已有分析结果(fallback company-level): %s risk=%s status=%s task_id=%s",
        cid,
        result.get("risk_level"),
        result.get("verification_status"),
        result.get("task_id"),
    )
    return result


def _find_task_id_for_company(company_id: str) -> Optional[str]:
    """从 tasks 目录中查找指定企业的最新 completed 任务 ID。"""
    tasks_dir = RUNS_WEB_ROOT / "tasks"
    if not tasks_dir.exists():
        return None

    candidates: List[Tuple[str, str]] = []  # (created_at, task_id)

    for task_dir in tasks_dir.iterdir():
        if not task_dir.is_dir():
            continue
        task_file = task_dir / "task.json"
        if not task_file.exists():
            continue
        try:
            task_data = json.loads(task_file.read_text(encoding="utf-8"))
            if (
                task_data.get("company_id") == company_id
                and task_data.get("status") == "completed"
            ):
                candidates.append((
                    task_data.get("created_at", ""),
                    task_data.get("task_id", task_dir.name),
                ))
        except (json.JSONDecodeError, OSError):
            continue

    if not candidates:
        return None

    # 按创建时间降序排序，返回最新的
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


# ------------------------------------------------------------
# Risk Rule Engine 集成（V2.1 新增）
# ------------------------------------------------------------


def _format_risk_scoring(result: Dict[str, Any], related_profiles: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """将 Rule Engine 结果格式化为 API 响应字段（V2.3B.1: 含 RelatedCompanyRiskProfile）。

    参数：
        result: RiskRuleEngine.evaluate() 的返回值。
        related_profiles: 关联企业 Risk Profile 列表（V2.3B.1 新增）。

    返回：
        格式化的 risk_scoring dict。
    """
    # V2.1 兼容字段
    base = {
        "risk_score": result["risk_score"],
        "risk_level": result["risk_level"],
        "triggered_rules": [
            {
                "rule_id": r["rule_id"],
                "rule_name": r["rule_name"],
                "dimension": r["dimension"],
                "evidence_id": r["evidence_id"],
                "score": r["score"],
                "severity": r["severity"],
                "description": r["description"],
                # V2.2: provenance 信息
                "is_target_company": r.get("is_target_company", True),
                "owner_company_id": r.get("owner_company_id", ""),
                "relation_depth": r.get("relation_depth", 0),
            }
            for r in result["triggered_rules"]
        ],
        "hard_rule_hits": result["hard_rule_hits"],
        "dimension_scores": result["dimension_scores"],
        "evidence_ids": result["evidence_ids"],
        "total_evidence_count": result["total_evidence_count"],
    }

    # V2.2 新增：分离结构
    if "own_risk" in result:
        base["own_risk"] = result["own_risk"]

    # V2.3B.1: relationship_exposure 改为 NOT_CALIBRATED + profiles
    base["relationship_exposure"] = {
        "status": "NOT_CALIBRATED",
        "score": None,
        "level": None,
        "related_company_profiles": related_profiles or [],
    }

    if "comprehensive_risk" in result:
        base["comprehensive_risk"] = result["comprehensive_risk"]

    return base


# ------------------------------------------------------------
# Report Post-Processing: 确定性注入风险等级（V2.1 新增）
# 已迁移至 report_postprocessor.py（独立模块，便于测试）
# ------------------------------------------------------------


def _build_rule_engine_input(
    company_id: str,
    evidence_ids: List[str],
    related_companies: List[str],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """构建 Risk Rule Engine 所需的输入数据（V2.2: 含 evidence provenance）。

    参数：
        company_id: 目标企业ID。
        evidence_ids: 报告中提取的 Evidence ID 列表。
        related_companies: 报告中提到的关联企业ID列表。

    返回：
        (evidence_facts, extra)
        - evidence_facts: 从数据库查询的原始事实列表（含 provenance 字段）。
        - extra: 预计算的上下文指标。
    """
    evidence_facts: List[Dict[str, Any]] = []

    # 逐个查询 Evidence 原始数据
    for eid in evidence_ids:
        ev = deps.get_evidence_by_id(eid)
        if ev is not None:
            evidence_facts.append({
                "evidence_id": eid,
                "evidence_type": ev.get("evidence_type", ""),
                "data": ev.get("data", {}),
                "company_id": ev.get("company_id"),
            })

    # V2.2: 计算 evidence provenance（归属来源）
    try:
        # 获取所有关系数据（需要全量关系图来计算最短路径）
        all_relations: List[Dict[str, Any]] = []
        # 收集所有涉及的公司 ID
        all_company_ids = {company_id}
        for eid in evidence_ids:
            ev = deps.get_evidence_by_id(eid)
            if ev and ev.get("company_id"):
                all_company_ids.add(ev["company_id"])
        for rc in related_companies:
            all_company_ids.add(rc)

        # 查询所有涉及公司的直接关系
        seen_relation_ids: Set[str] = set()
        for cid in all_company_ids:
            try:
                rels = deps.get_company_relations(cid)
                for r in rels:
                    rid = r.get("relation_id", "")
                    if rid and rid not in seen_relation_ids:
                        seen_relation_ids.add(rid)
                        all_relations.append(r)
            except Exception:
                pass

        # 计算 provenance
        from app.risk_rule_engine import compute_provenance
        evidence_facts = compute_provenance(evidence_facts, company_id, all_relations)

        logger.info(
            "[RuleEngine] Provenance 计算完成: %s total=%d own=%d related=%d",
            company_id,
            len(evidence_facts),
            sum(1 for f in evidence_facts if f.get("is_target_company")),
            sum(1 for f in evidence_facts if not f.get("is_target_company")),
        )
    except Exception as exc:
        logger.warning("[RuleEngine] Provenance 计算失败（回退到无 provenance 模式）: %s", exc)
        # 回退：所有 evidence 视为目标企业自身
        for f in evidence_facts:
            f.setdefault("is_target_company", True)
            f.setdefault("owner_company_id", f.get("company_id", ""))
            f.setdefault("target_company_id", company_id)
            f.setdefault("relation_depth", 0)
            f.setdefault("relation_path", [company_id])
            f.setdefault("relation_ids", [])
            f.setdefault("relation_types", [])
            f.setdefault("target_role_in_relation", None)

    # 构建 extra 上下文
    extra: Dict[str, Any] = {}

    # 企业基本信息
    profile = deps.get_company_profile(company_id)
    if profile:
        extra["business_status"] = profile.get("business_status", "")

    # 财务指标（取最新一期）
    try:
        financial_reports = deps.get_financial_reports(company_id)
        if financial_reports:
            latest = financial_reports[-1]
            extra["debt_ratio"] = latest.get("debt_ratio")
            extra["latest_operating_cash_flow"] = latest.get("operating_cash_flow")
            extra["revenue_yoy"] = latest.get("revenue_yoy")
            extra["profit_yoy"] = latest.get("profit_yoy")

            # 计算连续亏损年数
            consecutive_loss = 0
            for report in reversed(financial_reports):
                net_profit = report.get("net_profit")
                if net_profit is not None and net_profit < 0:
                    consecutive_loss += 1
                else:
                    break
            extra["consecutive_loss_years"] = consecutive_loss
    except Exception as exc:
        logger.warning("[RuleEngine] 获取财务数据失败: %s", exc)

    # 招聘事件数量
    try:
        recruitment = deps.get_recruitment_events(company_id)
        extra["recruitment_count"] = len(recruitment)
    except Exception as exc:
        logger.warning("[RuleEngine] 获取招聘数据失败: %s", exc)

    # 司法事件标志（从数据库查询，仅目标企业自身）
    try:
        judicial_events = deps.get_judicial_events(company_id)
        extra["has_bankruptcy_case"] = any(
            je.get("case_type") == "破产案件" for je in judicial_events
        )
        extra["has_dishonest_execution"] = any(
            je.get("case_type") == "失信被执行人" for je in judicial_events
        )
    except Exception as exc:
        logger.warning("[RuleEngine] 获取司法数据失败: %s", exc)

    # V2.2: 关联企业风险等级通过 provenance 传递，不再需要 extra 注入
    # R003 已标记 DEPRECATED

    return evidence_facts, extra


def _get_all_relations(company_ids: List[str]) -> List[Dict[str, Any]]:
    """获取所有涉及公司的关系数据（V2.3B.1）。"""
    all_relations: List[Dict[str, Any]] = []
    seen_relation_ids: Set[str] = set()
    for cid in company_ids:
        try:
            rels = deps.get_company_relations(cid)
            for r in rels:
                rid = r.get("relation_id", "")
                if rid and rid not in seen_relation_ids:
                    seen_relation_ids.add(rid)
                    all_relations.append(r)
        except Exception:
            pass
    return all_relations


# ------------------------------------------------------------
# 服务入口
# ------------------------------------------------------------


def analyze_company(
    company_id: str,
    task_dir: Optional[Path] = None,
    on_event: Optional[Callable[[Dict[str, Any], int], None]] = None,
    task_id: Optional[str] = None,
    cancelled_event: Optional["threading.Event"] = None,
    on_process_start: Optional[Callable[[int, int], None]] = None,
) -> Dict[str, Any]:
    """
    对指定企业执行一次完整风险分析（同步阻塞，实测耗时 3-20 分钟；
    复杂案例如 C005 需多轮 verifier 复核，可达 10-20 分钟）。

    参数：
        company_id: 企业ID
        task_dir: per-task 输出目录（V1.3 新增），可选。
            提供时 session_events.jsonl 和 stderr.log 写入该目录。
        on_event: 实时事件回调（V1.3 新增），可选。
            每收到一个有效 JSONL event 就调用 on_event(event_dict, event_count)。
        task_id: 任务ID（V1.4 新增），可选。
            提供时 analysis_result.json 保存到 task 目录并包含 task_id。
        cancelled_event: 取消信号事件（V1.5 新增），可选。
            被 set() 时终止当前分析且不重试。
        on_process_start: subprocess 启动回调（V1.5 新增），可选。
            调用 on_process_start(pid, pgid) 通知调用方进程已启动。

    返回响应 dict：
        {
            "task_id": Optional[str],      # V1.4 新增
            "company_id": str,
            "status": "completed",
            "report": str,
            "verification_status": "PASS" | "UNRESOLVED" | None,
            "risk_level": Optional[str],
            "summary": Optional[str],
            "evidence_ids": List[str],
            "related_companies": List[str],
            "report_path": Optional[str],   # 相对项目根路径
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
    logger.info("[Analyze] before run_harness_analysis company_id=%s task_id=%s", cid, task_id)
    harness_result = run_harness_analysis(
        cid,
        task_dir=task_dir,
        on_event=on_event,
        cancelled_event=cancelled_event,
        on_process_start=on_process_start,
    )
    logger.info("[Analyze] run_harness_analysis returned company_id=%s status=%s", cid, harness_result.get("verification_status"))

    # 3. best-effort 结构化解析
    report = (harness_result.get("report") or "").strip()
    evidence_ids = _extract_evidence_ids(report)
    related_companies = _extract_related_companies(report, cid)

    # 3.5 确定性 Risk Rule Engine 评估（V2.1 新增）
    rule_engine_result: Optional[Dict[str, Any]] = None
    related_profiles: Optional[List[Dict[str, Any]]] = None
    try:
        evidence_facts, extra = _build_rule_engine_input(cid, evidence_ids, related_companies)
        rule_engine_result = evaluate_risk(evidence_facts, extra)
        logger.info(
            "[RuleEngine] 风险评估完成: %s score=%s level=%s rules=%d hard=%d",
            cid,
            rule_engine_result.get("risk_score"),
            rule_engine_result.get("risk_level"),
            len(rule_engine_result.get("triggered_rules", [])),
            len(rule_engine_result.get("hard_rule_hits", [])),
        )

        # V2.3B.1: 构建关联企业 Own Risk Profiles
        if related_companies:
            try:
                engine = get_engine()
                all_relations = _get_all_relations(related_companies + [cid])
                related_profiles = build_related_company_profiles(
                    target_company_id=cid,
                    related_company_ids=related_companies,
                    evidence_facts=evidence_facts,
                    all_relations=all_relations,
                    engine=engine,
                    deps_module=deps,
                )
                logger.info(
                    "[RuleEngine] 关联企业 Profile 构建完成: %s profiles=%d",
                    cid, len(related_profiles),
                )
            except Exception as exc:
                logger.warning("[RuleEngine] 关联企业 Profile 构建失败: %s", exc)

    except Exception as exc:
        logger.warning("[RuleEngine] 风险评估异常（回退到 best-effort）: %s", exc)

    # 3.6 确定性注入风险等级到报告正文（V2.1 新增）
    # 风险等级和评分的唯一 Source of Truth 是 Rule Engine，
    # 后端进行 deterministic post-processing，不依赖 LLM 正确回填。
    engine_risk_level = rule_engine_result["risk_level"] if rule_engine_result else None
    engine_risk_score = rule_engine_result["risk_score"] if rule_engine_result else 0

    if engine_risk_level and report:
        report = inject_risk_level_into_report(report, engine_risk_level, engine_risk_score)
        logger.info(
            "[RuleEngine] 报告风险等级注入完成: %s level=%s score=%s",
            cid, engine_risk_level, engine_risk_score,
        )

    response: Dict[str, Any] = {
        "task_id": task_id,
        "company_id": cid,
        "status": "completed",
        "report": report,
        "verification_status": harness_result.get("verification_status"),
        # V2.1: 风险等级唯一 Source of Truth = Rule Engine
        # risk_level 镜像自 risk_scoring.level，不是独立来源
        "risk_level": engine_risk_level or _extract_risk_level(report),
        "summary": _extract_summary(report),
        "evidence_ids": evidence_ids,
        "related_companies": related_companies,
        "report_path": None,
        "duration_seconds": harness_result.get("duration_seconds", 0.0),
        # V2.0: 多源数据版本标记
        "analysis_version": "v2-rule-engine",
        "data_sources": [
            "business",
            "judicial",
            "relations",
            "public_opinion",
            "financial",
            "recruitment",
        ],
        # V2.1: Risk Rule Engine 结果
        "risk_scoring": _format_risk_scoring(rule_engine_result, related_profiles) if rule_engine_result else None,
    }

    # V2.1 一致性校验：risk_level 必须镜像自 risk_scoring.level
    if response.get("risk_scoring"):
        scoring_level = response["risk_scoring"]["risk_level"]
        if response["risk_level"] != scoring_level:
            logger.warning(
                "[RuleEngine] risk_level 不一致: response=%s scoring=%s，强制镜像",
                response["risk_level"], scoring_level,
            )
            response["risk_level"] = scoring_level

    # 4. 保存运行记录（task 目录 + company-level + latest.json）
    _save_run_records(cid, harness_result, response, task_id=task_id, task_dir=task_dir)

    logger.info(
        "分析完成: %s task_id=%s status=%s risk=%s evidence=%d related=%d 耗时=%ss",
        cid,
        task_id,
        response["verification_status"],
        response["risk_level"],
        len(response["evidence_ids"]),
        len(response["related_companies"]),
        response["duration_seconds"],
    )

    return response
