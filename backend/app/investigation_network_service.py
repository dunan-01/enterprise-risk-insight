"""
企业关联风险智能洞察系统 —— V1.6 调查网络服务。

在 Complete Relation Network 基础上叠加 Investigation Trace 数据，
构建带调查状态标注的调查网络（investigation network）。

确定性设计：完全基于 trace events，不依赖 LLM 推断。
"""

from __future__ import annotations

import json
import logging
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .relation_network_service import build_relation_network
from .task_manager import TaskManager

logger = logging.getLogger("risk-api")

# ------------------------------------------------------------
# 常量
# ------------------------------------------------------------

# 构成"调查"一个企业的工具集
# 注意：risk_get_company_relations 不属于调查工具，通过它发现的企业应标记为 discovered
INVESTIGATION_TOOLS: Set[str] = {
    "risk_get_company_profile",
    "risk_get_business_events",
    "risk_get_judicial_events",
    "risk_get_company_snapshot",
}

# 企业 ID 正则（从 coverage 描述中提取）
_COMPANY_ID_RE = re.compile(r"C\d{3}")


# ------------------------------------------------------------
# 公共 API
# ------------------------------------------------------------


def build_investigation_network(task_id: str) -> Optional[Dict[str, Any]]:
    """
    构建指定 Analysis Run 的调查网络。

    流程：
    1. 获取 task → company_id
    2. 构建完整关系网络（复用 build_relation_network）
    3. 解析 trace events（复用 parse_trace_events）
    4. 从 trace 提取调查数据：
       - tool_call 事件中的 investigation tools → 已调查企业
       - company_discovered 事件 → 已发现企业
       - coverage_result INCOMPLETE → 补充企业
    5. 将调查状态叠加到网络节点和边上
    6. 返回增强网络 + 统计数据

    Args:
        task_id: 任务唯一ID

    Returns:
        {
            "task_id": str,
            "company_id": str,
            "task_status": str,
            "nodes": [...],
            "edges": [...],
            "stats": {...},
        }
        任务不存在时返回 None。
    """
    # 1. 获取 task
    task_manager = TaskManager()
    task = task_manager.get_task(task_id)
    if task is None:
        return None

    company_id = task.company_id
    task_status = task.status.value

    # 2. 构建完整关系网络
    try:
        relation_network = build_relation_network(company_id)
    except ValueError:
        # 企业不存在 —— 仍然返回一个只有根节点的网络
        relation_network = {
            "root_company_id": company_id,
            "nodes": [],
            "edges": [],
            "truncated": False,
        }

    # 3. 解析 trace events
    raw_events = _load_raw_events(task_id)
    # 延迟导入避免循环依赖
    from .trace_service import parse_trace_events

    events = parse_trace_events(raw_events, task_status=task_status)

    # 4. 提取调查数据（需要 raw events 来检测 coverage 结果）
    investigation_data = _extract_investigation_data(events, company_id, raw_events=raw_events)

    # 5. 叠加到网络
    nodes = _build_investigation_nodes(
        relation_network["nodes"],
        investigation_data,
        company_id,
    )

    edges = _build_investigation_edges(
        relation_network["edges"],
        investigation_data,
    )

    # 6. 计算统计
    stats = _calculate_stats(nodes, edges)

    return {
        "task_id": task_id,
        "company_id": company_id,
        "task_status": task_status,
        "nodes": nodes,
        "edges": edges,
        "stats": stats,
    }


# ------------------------------------------------------------
# 内部函数
# ------------------------------------------------------------


def build_investigation_network_from_session_events(company_id: str) -> Optional[Dict[str, Any]]:
    """
    从 session_events.jsonl 文件构建调查网络（用于没有 task 记录的历史分析）。

    Args:
        company_id: 企业 ID，例如 C004

    Returns:
        与 build_investigation_network 相同的结构
    """
    from .deps import PROJECT_ROOT

    # 1. 查找 session_events.jsonl
    company_dir = PROJECT_ROOT / "runs" / "web" / company_id
    events_file = company_dir / "session_events.jsonl"

    if not events_file.exists():
        logger.info("[InvestigationNetwork] 未找到 %s 的 session_events.jsonl", company_id)
        return None

    # 2. 加载 raw events
    raw_events: List[dict] = []
    try:
        with open(events_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw_events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except OSError as exc:
        logger.warning("[InvestigationNetwork] 读取 session_events.jsonl 失败: %s", exc)
        return None

    if not raw_events:
        return None

    # 3. 构建完整关系网络
    try:
        relation_network = build_relation_network(company_id)
    except ValueError:
        relation_network = {
            "root_company_id": company_id,
            "nodes": [],
            "edges": [],
            "truncated": False,
        }

    # 4. 解析 trace events
    from .trace_service import parse_trace_events
    events = parse_trace_events(raw_events, task_status="completed")

    # 5. 提取调查数据
    investigation_data = _extract_investigation_data(events, company_id, raw_events=raw_events)

    # 6. 叠加到网络
    nodes = _build_investigation_nodes(
        relation_network["nodes"],
        investigation_data,
        company_id,
    )

    edges = _build_investigation_edges(
        relation_network["edges"],
        investigation_data,
    )

    # 7. 计算统计
    stats = _calculate_stats(nodes, edges)

    return {
        "task_id": None,
        "company_id": company_id,
        "task_status": "completed",
        "nodes": nodes,
        "edges": edges,
        "stats": stats,
    }


def _load_raw_events(task_id: str) -> List[dict]:
    """从 per-task 目录加载 raw session events（JSONL）。"""
    from .deps import PROJECT_ROOT
    task_dir = PROJECT_ROOT / "runs" / "web" / "tasks" / task_id
    events_file = task_dir / "session_events.jsonl"

    if not events_file.exists():
        return []

    events: List[dict] = []
    try:
        with open(events_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except OSError as exc:
        logger.warning("[InvestigationNetwork] 读取 session_events.jsonl 失败: %s", exc)

    return events


def _extract_missing_companies(coverage_output: str) -> Set[str]:
    """
    Extract missing companies from coverage auditor output.
    
    The coverage output has a section like:
    MISSING_INVESTIGATION:
    1. Path:
       C010 → C002 → C001 → C003
    
       Missing companies:
       C003
    
    2. Path:
       C010 → C002 → C001 → C009
    
       Missing companies:
       C009
    
    We need to extract only the companies listed under "Missing companies:" sections.
    """
    missing = set()
    
    # Find MISSING_INVESTIGATION section
    missing_section_match = re.search(r"MISSING_INVESTIGATION:(.+)", coverage_output, re.DOTALL)
    if not missing_section_match:
        return missing
    
    missing_section = missing_section_match.group(1)
    
    # Find all "Missing companies:" lines and extract company IDs after them
    # Pattern: "Missing companies:" followed by company IDs on the same or next lines
    lines = missing_section.split("\n")
    capture = False
    for line in lines:
        if "Missing companies:" in line:
            capture = True
            # Check if company IDs are on the same line after the colon
            after_colon = line.split("Missing companies:")[-1]
            ids = _COMPANY_ID_RE.findall(after_colon)
            missing.update(ids)
        elif capture:
            # Check if line is empty or starts a new section (indented or not)
            stripped = line.strip()
            if not stripped or stripped.startswith("Why investigate:") or stripped.startswith("Key evidence"):
                capture = False
            else:
                # Check for company IDs on this line
                ids = _COMPANY_ID_RE.findall(line)
                if ids:
                    missing.update(ids)
                else:
                    # No more company IDs, stop capturing
                    capture = False
    
    return missing


def _extract_investigation_data(
    events: List[dict],
    root_company_id: str,
    raw_events: Optional[List[dict]] = None,
) -> Dict[str, Any]:
    """
    从 parsed trace events 中提取调查数据。

    Returns:
        {
            "investigated_companies": OrderedDict({
                company_id: {
                    "order": int,
                    "first_at": str,
                    "tools": set,
                    "evidence_ids": list,
                    "supplementary": bool,
                }
            }),
            "discovered_companies": OrderedDict({
                company_id: {"first_at": str}
            }),
            "coverage_supplementary": set,
            "investigated_edges_by_source": OrderedDict({
                company_id: {"first_at": str, "evidence_referenced": bool}
            }),
            "company_evidence": OrderedDict({
                company_id: [evidence_ids]
            }),
            "investigation_order_counter": int,
        }
    """
    investigated: OrderedDict[str, Dict[str, Any]] = OrderedDict()
    discovered: OrderedDict[str, Dict[str, Any]] = OrderedDict()
    investigated_edges_by_source: OrderedDict[str, Dict[str, Any]] = OrderedDict()
    company_evidence: OrderedDict[str, List[str]] = OrderedDict()
    coverage_supplementary: Set[str] = set()

    investigation_order = 0
    coverage_missing_companies: Set[str] = set()
    coverage_incomplete_timestamp: Optional[str] = None  # Track when INCOMPLETE happened
    coverage_missing_at_incomplete: Set[str] = set()  # Companies missing at INCOMPLETE time

    # First pass: check raw events for coverage results (parsed events may not include them)
    if raw_events:
        for raw_event in raw_events:
            raw_type = raw_event.get("type", "")
            part = raw_event.get("part", {})
            raw_tool = raw_event.get("tool") or part.get("tool", "")
            if raw_type == "tool_use" and raw_tool == "task":
                output = str(part.get("state", {}).get("output", ""))
                timestamp = raw_event.get("timestamp", "")
                if "COVERAGE_STATUS" in output:
                    if "INCOMPLETE" in output.upper():
                        # Extract missing companies from MISSING_INVESTIGATION section
                        missing = _extract_missing_companies(output)
                        coverage_missing_companies.update(missing)
                        coverage_missing_at_incomplete.update(missing)
                        coverage_incomplete_timestamp = timestamp
                    else:
                        # COMPLETE - companies investigated after INCOMPLETE are supplementary
                        # Keep coverage_missing_at_incomplete for supplementary marking
                        coverage_missing_companies.clear()
                        coverage_incomplete_timestamp = None

    for event in events:
        event_type = event.get("type", "")
        timestamp = event.get("timestamp", "")
        company_id = event.get("company_id")
        tool = event.get("tool", "")
        evidence_ids = event.get("evidence_ids", [])
        description = event.get("description", "")

        # --- 跟踪 coverage 审核结果 (from parsed events) ---
        if event_type == "coverage_result":
            if "INCOMPLETE" in description.upper():
                # 提取缺失企业 ID
                missing = set(_COMPANY_ID_RE.findall(description))
                coverage_missing_companies.update(missing)
            else:
                coverage_missing_companies.clear()
            continue

        # --- 跟踪 tool_call → 已调查企业 ---
        if event_type == "tool_call" and company_id and tool in INVESTIGATION_TOOLS:
            if company_id not in investigated:
                investigation_order += 1
                investigated[company_id] = {
                    "order": investigation_order,
                    "first_at": timestamp,
                    "tools": set(),
                    "evidence_ids": [],
                    "supplementary": False,
                }
            investigated[company_id]["tools"].add(tool)
            if evidence_ids:
                investigated[company_id]["evidence_ids"].extend(evidence_ids)

            # 跟踪每个企业的证据
            if company_id not in company_evidence:
                company_evidence[company_id] = []
            company_evidence[company_id].extend(evidence_ids)

        # --- 跟踪关系查询来源（边遍历检测）---
        # 注意：risk_get_company_relations 不属于 INVESTIGATION_TOOLS，需要单独处理
        # 通过它发现的企业应标记为 discovered，但需要记录边遍历信息
        if event_type == "tool_call" and company_id and tool == "risk_get_company_relations":
            if company_id not in investigated_edges_by_source:
                investigated_edges_by_source[company_id] = {
                    "first_at": timestamp,
                    "evidence_referenced": bool(evidence_ids),
                }

        # --- 跟踪公司发现 ---
        elif event_type == "company_discovered" and company_id:
            if company_id not in investigated and company_id not in discovered:
                discovered[company_id] = {"first_at": timestamp}

    # 标记 coverage 补充企业
    # A company is supplementary if:
    # 1. It was listed as missing in an INCOMPLETE coverage result, AND
    # 2. It was investigated (has tool_call events)
    # Note: Even if coverage later becomes COMPLETE, we still mark these as supplementary
    # because they were initially missing and required supplementary investigation.
    for comp_id in coverage_missing_at_incomplete:
        if comp_id in investigated:
            investigated[comp_id]["supplementary"] = True
            coverage_supplementary.add(comp_id)

    return {
        "investigated_companies": investigated,
        "discovered_companies": discovered,
        "coverage_supplementary": coverage_supplementary,
        "investigated_edges_by_source": investigated_edges_by_source,
        "company_evidence": company_evidence,
        "investigation_order_counter": investigation_order,
    }


def _build_investigation_nodes(
    network_nodes: List[dict],
    investigation_data: Dict[str, Any],
    root_company_id: str,
) -> List[dict]:
    """
    将调查状态叠加到关系网络节点。

    规则：
    - root: 目标企业本身
    - investigated: 在 tool_call 事件中出现过且工具属于 INVESTIGATION_TOOLS
    - discovered: 在 company_discovered 事件中出现但未被调查
    - not_investigated: 在网络中但未出现在任何 trace 事件中
    """
    from .deps import PROJECT_ROOT
    investigated = investigation_data["investigated_companies"]
    discovered = investigation_data["discovered_companies"]
    company_evidence = investigation_data["company_evidence"]

    result: List[dict] = []
    for node in network_nodes:
        cid = node["company_id"]

        if cid == root_company_id:
            status = "root"
            order = 0
            first_at: Optional[str] = None
            supplementary = False
        elif cid in investigated:
            status = "investigated"
            order = investigated[cid]["order"]
            first_at = investigated[cid]["first_at"]
            supplementary = investigated[cid].get("supplementary", False)
        elif cid in discovered:
            status = "discovered"
            order = None
            first_at = discovered[cid]["first_at"]
            supplementary = False
        else:
            status = "not_investigated"
            order = None
            first_at = None
            supplementary = False

        evidence_ids = company_evidence.get(cid, [])

        # 加载风险等级和风险标签
        risk_level, risk_tags = _load_risk_info(cid, evidence_ids)

        result.append({
            "company_id": cid,
            "company_name": node.get("company_name", ""),
            "industry": node.get("industry"),
            "business_status": node.get("business_status"),
            "depth": node.get("depth", 0),
            "is_root": cid == root_company_id,
            "investigation_status": status,
            "investigation_order": order,
            "first_investigated_at": first_at,
            "evidence_ids": evidence_ids,
            "evidence_count": len(evidence_ids),
            "supplementary": supplementary,
            "risk_level": risk_level,
            "risk_tags": risk_tags,
        })

    return result


def _load_risk_info(company_id: str, evidence_ids: List[str]) -> tuple:
    """
    加载企业的风险等级和风险标签。

    Returns:
        (risk_level, risk_tags) 元组
    """
    from .deps import PROJECT_ROOT
    import json as _json

    risk_level = None
    risk_tags = []

    # 1. 从 analysis_result.json 加载风险等级
    analysis_file = PROJECT_ROOT / "runs" / "web" / company_id / "analysis_result.json"
    if analysis_file.exists():
        try:
            with open(analysis_file, "r", encoding="utf-8") as f:
                analysis_data = _json.load(f)
                risk_level = analysis_data.get("risk_level")
        except (OSError, _json.JSONDecodeError):
            pass

    # 2. 从 evidence 提取风险标签
    for evidence_id in evidence_ids:
        tag = _extract_risk_tag_from_evidence(evidence_id)
        if tag and tag not in risk_tags:
            risk_tags.append(tag)

    return risk_level, risk_tags


def _extract_risk_tag_from_evidence(evidence_id: str) -> Optional[str]:
    """
    从 evidence ID 提取风险标签。

    规则：
    - J001-J003: 诉讼案件
    - J004-J006: 被执行人
    - J007-J008: 失信被执行人
    - J009-J010: 限制消费令
    - J011-J012: 股权冻结
    - B001-B003: 经营异常
    - B004-B006: 行政处罚
    - B007-B009: 股东变更
    - B010-B012: 法人变更
    - B013-B015: 注册资本变更
    - B016: 地址变更
    """
    if not evidence_id:
        return None

    # J 开头的是司法事件
    if evidence_id.startswith("J"):
        num = int(evidence_id[1:]) if evidence_id[1:].isdigit() else 0
        if 1 <= num <= 3:
            return "诉讼案件"
        elif 4 <= num <= 6:
            return "被执行人"
        elif 7 <= num <= 8:
            return "失信被执行人"
        elif 9 <= num <= 10:
            return "限制消费令"
        elif 11 <= num <= 12:
            return "股权冻结"
        elif 13 <= num <= 14:
            return "司法案件"

    # B 开头的是经营事件
    if evidence_id.startswith("B"):
        num = int(evidence_id[1:]) if evidence_id[1:].isdigit() else 0
        if 1 <= num <= 3:
            return "经营异常"
        elif 4 <= num <= 6:
            return "行政处罚"
        elif 7 <= num <= 9:
            return "股东变更"
        elif 10 <= num <= 12:
            return "法人变更"
        elif 13 <= num <= 15:
            return "注册资本变更"
        elif num == 16:
            return "地址变更"

    return None


def _build_investigation_edges(
    network_edges: List[dict],
    investigation_data: Dict[str, Any],
) -> List[dict]:
    """
    将调查状态叠加到关系网络边。

    规则：
    - traversed: 源企业和目标企业均已调查，且源企业查询过关系
    - discovered: 至少一端企业已调查但边未被主动遍历
    - not_used: 边存在于网络中但未被引用
    """
    investigated = investigation_data["investigated_companies"]
    investigated_by_source = investigation_data["investigated_edges_by_source"]

    result: List[dict] = []
    for edge in network_edges:
        source = edge["source"]
        target = edge["target"]

        source_investigated = source in investigated
        target_investigated = target in investigated
        source_queried_relations = source in investigated_by_source

        # 判断边是否被遍历
        if source_investigated and target_investigated and source_queried_relations:
            status = "traversed"
            first_at: Optional[str] = investigated_by_source[source]["first_at"]
            evidence_referenced: bool = investigated_by_source[source]["evidence_referenced"]
        elif source_investigated or target_investigated:
            status = "discovered"
            first_at = None
            evidence_referenced = False
        else:
            status = "not_used"
            first_at = None
            evidence_referenced = False

        # 检查 supplementary
        supplementary = False
        if target in investigated and investigated[target].get("supplementary"):
            supplementary = True
        if source in investigated and investigated[source].get("supplementary"):
            supplementary = True

        # 生成调查原因
        investigation_reason = _generate_investigation_reason(
            source, target, investigated, edge
        )

        result.append({
            "relation_id": edge.get("relation_id", ""),
            "source": source,
            "target": target,
            "relation_type": edge.get("relation_type", ""),
            "equity_ratio": edge.get("equity_ratio"),
            "amount": edge.get("amount"),
            "status": edge.get("status"),
            "investigation_status": status,
            "first_used_at": first_at,
            "supplementary": supplementary,
            "evidence_referenced": evidence_referenced,
            "investigation_reason": investigation_reason,
        })

    return result


def _generate_investigation_reason(
    source: str,
    target: str,
    investigated: Dict[str, Any],
    edge: Dict[str, Any],
) -> str:
    """
    生成调查原因说明。

    Returns:
        调查原因字符串
    """
    # 如果目标企业有风险标签，说明是因为风险而调查
    target_data = investigated.get(target, {})
    if target_data:
        # 检查目标企业的风险标签
        risk_tags = target_data.get("risk_tags", [])
        if risk_tags:
            return f"发现{target}存在{'、'.join(risk_tags[:3])}等风险"

    # 根据关系类型生成原因
    relation_type = edge.get("relation_type", "")
    if relation_type == "股权":
        equity_ratio = edge.get("equity_ratio", 0)
        if equity_ratio and equity_ratio >= 0.5:
            return f"控股子公司，需调查经营风险"
        else:
            return f"参股公司，需调查投资风险"
    elif relation_type == "对外投资":
        return f"对外投资企业，需调查投资风险"
    elif relation_type == "担保":
        return f"存在担保关系，需调查担保风险"
    elif relation_type == "共同法人":
        return f"法定代表人相同，需调查关联交易"
    elif relation_type == "共同股东":
        return f"股东相同，需调查关联交易"

    return f"通过{source}关联发现"


def _calculate_stats(nodes: List[dict], edges: List[dict]) -> Dict[str, int]:
    """计算网络统计数据。"""
    investigated = sum(
        1 for n in nodes if n["investigation_status"] in ("root", "investigated")
    )
    discovered = sum(
        1 for n in nodes if n["investigation_status"] == "discovered"
    )
    not_investigated = sum(
        1 for n in nodes if n["investigation_status"] == "not_investigated"
    )
    investigated_edges = sum(
        1 for e in edges if e["investigation_status"] == "traversed"
    )
    total_evidence = sum(n["evidence_count"] for n in nodes)

    return {
        "total_network_nodes": len(nodes),
        "investigated_nodes": investigated,
        "discovered_nodes": discovered,
        "uninvestigated_nodes": not_investigated,
        "investigated_edges": investigated_edges,
        "total_evidence": total_evidence,
    }
