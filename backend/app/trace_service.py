"""
企业关联风险智能洞察系统 —— Investigation Trace 事件解析器（V1.3 修复版）。

将 OpenCode raw event（JSONL）转换为用户可理解的 Structured Trace Event，
用于前端展示调查过程的时间线。

真实 OpenCode JSONL Schema（已验证）：
- tool_use: {type: "tool_use", part: {type: "tool", tool: "risk_xxx", callID: "call_xxx",
  state: {status: "completed", input: {company_id: "C010"}, output: "...", time: {start, end}}}}
- text: {type: "text", part: {type: "text", text: "...", time: {start, end}}}
- step_start: {type: "step_start", part: {id: "prt_xxx", sessionID: "ses_xxx"}}
- step_finish: {type: "step_finish", part: {reason: "tool-calls", tokens: {...}}}

关键设计原则：
1. analysis_started / analysis_completed / analysis_failed
   仅由 task_status 驱动，不从 OpenCode 文本推断
2. company_id 从 part.state.input 中提取，不猜测
3. coverage / verification 从 agent identity + 结构化文本识别
4. tool start/result 通过 callID 配对
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


# ------------------------------------------------------------
# 常量与映射
# ------------------------------------------------------------

# 工具名 → 用户可读名称映射
TOOL_DISPLAY_NAMES: Dict[str, str] = {
    "risk_get_company_profile": "查询企业基本信息",
    "risk_get_business_events": "查询工商事件",
    "risk_get_judicial_events": "查询司法事件",
    "risk_get_company_relations": "查询企业关联关系",
    "risk_search_company": "搜索企业",
}

# 工具名 → 动作描述
TOOL_ACTION_VERBS: Dict[str, str] = {
    "risk_get_company_profile": "查询",
    "risk_get_business_events": "查询",
    "risk_get_judicial_events": "查询",
    "risk_get_company_relations": "查询",
    "risk_search_company": "搜索",
}

# Evidence ID 匹配模式（Bxxx / Jxxx / Rxxx）
EVIDENCE_ID_PATTERN = re.compile(r"\b([BJR]\d{3})\b")

# 覆盖性审核状态模式
COVERAGE_STATUS_PATTERN = re.compile(r"COVERAGE_STATUS:\s*(\w+)")

# 风险审核状态模式
VERDICT_PATTERN = re.compile(r"VERDICT:\s*(\w+)")

# 审核状态模式
VERIFICATION_STATUS_PATTERN = re.compile(r"VERIFICATION_STATUS:\s*(\w+)")

# 企业 ID 模式
COMPANY_ID_PATTERN = re.compile(r"(?<![A-Za-z0-9-])(C\d{3})\b")


# ------------------------------------------------------------
# 辅助函数
# ------------------------------------------------------------


def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 8601 字符串。"""
    return datetime.now(timezone.utc).isoformat()


def _gen_event_id() -> str:
    """生成唯一事件 ID。"""
    return f"trace_{uuid.uuid4().hex[:8]}"


def _ts_to_iso(raw_ts: Any) -> str:
    """将 timestamp 转换为 ISO 字符串。"""
    if isinstance(raw_ts, (int, float)):
        try:
            return datetime.fromtimestamp(
                raw_ts / 1000.0, tz=timezone.utc
            ).isoformat()
        except (OSError, ValueError):
            return _now_iso()
    return str(raw_ts) if raw_ts else _now_iso()


def _extract_evidence_ids(text: str) -> List[str]:
    """从文本中提取 Evidence ID（Bxxx / Jxxx / Rxxx），去重保序。"""
    seen: set[str] = set()
    ids: List[str] = []
    for m in EVIDENCE_ID_PATTERN.finditer(text):
        eid = m.group(1)
        if eid not in seen:
            seen.add(eid)
            ids.append(eid)
    return ids


def _get_tool_display_name(tool_name: str) -> str:
    """获取工具的用户可读名称。"""
    return TOOL_DISPLAY_NAMES.get(tool_name, tool_name)


def _extract_company_from_input(tool_input: dict) -> Tuple[str, str]:
    """从工具输入参数中提取 company_id 和 keyword。

    Returns:
        (company_id, keyword) 元组
    """
    company_id = tool_input.get("company_id", "")
    keyword = tool_input.get("keyword", "")
    return company_id, keyword


def _is_reasoning_event(event: Dict[str, Any]) -> bool:
    """判断是否为 reasoning / thinking / thought 事件（应过滤）。"""
    part = event.get("part", {})
    if isinstance(part, dict):
        part_type = part.get("type", "")
        if part_type in ("thinking", "thought", "reasoning"):
            return True
        content = str(part.get("text", ""))
        if content.startswith("<thinking>") or content.startswith("<thought>"):
            return True
    return False


# ------------------------------------------------------------
# 核心解析函数
# ------------------------------------------------------------


def parse_trace_events(
    raw_events: List[dict],
    task_status: str = "running",
) -> List[dict]:
    """
    将 OpenCode raw events 转换为 structured trace events。

    关键设计：
    - analysis_started / analysis_completed 由 task_status 驱动
    - company_id 从 part.state.input 提取
    - tool start/result 通过 callID 配对
    - coverage / verification 从 agent identity + 结构化文本识别

    Args:
        raw_events: OpenCode 原始 JSONL 事件列表
        task_status: 任务状态（queued / running / completed / failed）

    Returns:
        List[dict]：结构化 trace events 列表
    """
    trace_events: List[dict] = []
    sequence = 0

    # 跟踪状态
    current_agent = "risk-orchestrator"
    discovered_companies: set[str] = set()
    tool_calls: Dict[str, dict] = {}  # callID → trace_event（用于配对 start/result）
    company_names: Dict[str, str] = {}  # company_id → company_name（缓存）

    # ---- 0. analysis_started（始终为第一条） ----
    sequence += 1
    trace_events.append({
        "event_id": _gen_event_id(),
        "sequence": sequence,
        "timestamp": _now_iso(),
        "type": "analysis_started",
        "agent": "risk-orchestrator",
        "title": "开始企业风险调查",
        "description": "AI 风险调查流程已启动",
        "company_id": None,
        "company_name": None,
        "tool": None,
        "evidence_ids": [],
        "status": "completed",
    })

    for raw_event in raw_events:
        # 过滤 reasoning 事件
        if _is_reasoning_event(raw_event):
            continue

        event_type = raw_event.get("type", "")
        part = raw_event.get("part", {})
        timestamp = _ts_to_iso(raw_event.get("timestamp"))

        # ---- 1. tool_use 事件（包含 start 和 result） ----
        if event_type == "tool_use" and isinstance(part, dict):
            tool_name = part.get("tool", "")
            call_id = part.get("callID", "")
            state = part.get("state", {})
            tool_status = state.get("status", "")
            tool_input = state.get("input", {})
            tool_output = str(state.get("output", ""))

            if not tool_name:
                continue

            # 提取 company_id
            company_id, keyword = _extract_company_from_input(tool_input)

            # 从 tool output 中提取 company_name
            if company_id and tool_output:
                try:
                    import json as _json
                    output_data = _json.loads(tool_output)
                    if isinstance(output_data, dict):
                        name = output_data.get("company_name", "")
                        if name:
                            company_names[company_id] = name
                    elif isinstance(output_data, list) and output_data:
                        for item in output_data:
                            if isinstance(item, dict):
                                cid = item.get("company_id", "")
                                name = item.get("company_name", "")
                                if cid and name:
                                    company_names[cid] = name
                except Exception:
                    pass

            display_name = _get_tool_display_name(tool_name)

            # 构建标题和描述
            if tool_name == "risk_search_company":
                title = f"搜索企业"
                description = f"关键词：{keyword or company_id or '未知'}"
                display_company = keyword or company_id
            elif company_id:
                cn = company_names.get(company_id, "")
                title = f"{display_name}"
                description = f"{cn}（{company_id}）" if cn else company_id
                display_company = company_id
            else:
                title = f"{display_name}"
                description = ""
                display_company = None

            # 提取 evidence_ids
            evidence_ids = _extract_evidence_ids(tool_output)

            # 如果是 completed 状态的 tool_use，直接生成 completed 事件
            if tool_status == "completed":
                sequence += 1
                trace_events.append({
                    "event_id": _gen_event_id(),
                    "sequence": sequence,
                    "timestamp": timestamp,
                    "type": "tool_call",
                    "agent": current_agent,
                    "title": title,
                    "description": description,
                    "company_id": display_company,
                    "company_name": company_names.get(display_company, "") if display_company else None,
                    "tool": tool_name,
                    "evidence_ids": evidence_ids,
                    "status": "completed",
                })

                # 检测关联企业发现
                if tool_output:
                    for m in COMPANY_ID_PATTERN.finditer(tool_output):
                        cid = m.group(1)
                        if cid not in discovered_companies and cid != company_id:
                            discovered_companies.add(cid)
                            cn = company_names.get(cid, "")
                            sequence += 1
                            trace_events.append({
                                "event_id": _gen_event_id(),
                                "sequence": sequence,
                                "timestamp": timestamp,
                                "type": "company_discovered",
                                "agent": current_agent,
                                "title": "发现关联企业",
                                "description": f"{cn}（{cid}）" if cn else cid,
                                "company_id": cid,
                                "company_name": cn or None,
                                "tool": None,
                                "evidence_ids": [],
                                "status": "completed",
                            })
            else:
                # in_progress 状态：记录但不闭合
                sequence += 1
                trace_ev = {
                    "event_id": _gen_event_id(),
                    "sequence": sequence,
                    "timestamp": timestamp,
                    "type": "tool_call",
                    "agent": current_agent,
                    "title": title,
                    "description": description,
                    "company_id": display_company,
                    "company_name": company_names.get(display_company, "") if display_company else None,
                    "tool": tool_name,
                    "evidence_ids": evidence_ids,
                    "status": "in_progress",
                }
                trace_events.append(trace_ev)
                if call_id:
                    tool_calls[call_id] = trace_ev

        # ---- 2. text 事件（识别 coverage / verification） ----
        if event_type == "text" and isinstance(part, dict):
            text = str(part.get("text", ""))

            # 识别 coverage-auditor 结果
            m_coverage = COVERAGE_STATUS_PATTERN.search(text)
            if m_coverage:
                status_val = m_coverage.group(1).upper()
                sequence += 1
                trace_events.append({
                    "event_id": _gen_event_id(),
                    "sequence": sequence,
                    "timestamp": timestamp,
                    "type": "coverage_result",
                    "agent": "coverage-auditor",
                    "title": "覆盖性审核",
                    "description": f"审核结论：{status_val}",
                    "company_id": None,
                    "company_name": None,
                    "tool": None,
                    "evidence_ids": [],
                    "status": "completed",
                })

            # 识别 risk-verifier 结果
            m_verdict = VERDICT_PATTERN.search(text)
            if m_verdict:
                verdict_val = m_verdict.group(1).upper()
                sequence += 1
                trace_events.append({
                    "event_id": _gen_event_id(),
                    "sequence": sequence,
                    "timestamp": timestamp,
                    "type": "verification_result",
                    "agent": "risk-verifier",
                    "title": "风险审核",
                    "description": f"审核结论：{verdict_val}",
                    "company_id": None,
                    "company_name": None,
                    "tool": None,
                    "evidence_ids": [],
                    "status": "completed",
                })

            # 识别 VERIFICATION_STATUS（报告生成）
            m_status = VERIFICATION_STATUS_PATTERN.search(text)
            if m_status and not m_verdict:
                status_val = m_status.group(1).upper()
                sequence += 1
                trace_events.append({
                    "event_id": _gen_event_id(),
                    "sequence": sequence,
                    "timestamp": timestamp,
                    "type": "report_generated",
                    "agent": "risk-orchestrator",
                    "title": "报告生成",
                    "description": f"最终报告已生成，审核状态：{status_val}",
                    "company_id": None,
                    "company_name": None,
                    "tool": None,
                    "evidence_ids": [],
                    "status": "completed",
                })

    # ---- N. analysis_completed / analysis_failed（仅当 task_status 指示完成时） ----
    if task_status == "completed":
        sequence += 1
        trace_events.append({
            "event_id": _gen_event_id(),
            "sequence": sequence,
            "timestamp": _now_iso(),
            "type": "analysis_completed",
            "agent": "risk-orchestrator",
            "title": "企业风险调查完成",
            "description": "所有调查和审核流程已完成",
            "company_id": None,
            "company_name": None,
            "tool": None,
            "evidence_ids": [],
            "status": "completed",
        })
    elif task_status == "failed":
        sequence += 1
        trace_events.append({
            "event_id": _gen_event_id(),
            "sequence": sequence,
            "timestamp": _now_iso(),
            "type": "analysis_failed",
            "agent": "risk-orchestrator",
            "title": "分析失败",
            "description": "风险分析过程中出现错误",
            "company_id": None,
            "company_name": None,
            "tool": None,
            "evidence_ids": [],
            "status": "failed",
        })

    return trace_events


def get_current_stage(events: List[dict]) -> str:
    """
    根据已有事件推断当前分析阶段。

    阶段：
    - investigating: 正在调查
    - auditing_coverage: 覆盖性审核中
    - verifying: 风险审核中
    - generating_report: 生成报告
    - completed: 已完成
    - failed: 失败
    - idle: 空闲（无事件）
    """
    if not events:
        return "idle"

    # 按时间排序取最新事件
    sorted_events = sorted(events, key=lambda e: e.get("timestamp", ""), reverse=True)

    for ev in sorted_events:
        ev_type = ev.get("type", "")

        if ev_type == "analysis_completed":
            return "completed"
        elif ev_type == "analysis_failed":
            return "failed"
        elif ev_type == "report_generated":
            return "generating_report"
        elif ev_type == "verification_result":
            return "generating_report"
        elif ev_type == "verification_started":
            return "verifying"
        elif ev_type == "coverage_result":
            if ev.get("status") == "failed":
                return "investigating"
            return "auditing_coverage"
        elif ev_type == "coverage_started":
            return "auditing_coverage"
        elif ev_type == "tool_call":
            return "investigating"
        elif ev_type == "company_discovered":
            return "investigating"
        elif ev_type == "analysis_started":
            return "investigating"

    return "investigating"
