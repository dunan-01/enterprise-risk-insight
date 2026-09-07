"""
企业关联风险智能洞察系统 —— API 数据模型（Pydantic）。

所有字段与 risk.db 表结构（schema.sql）保持一致，
通过 FastAPI response_model 对输出做统一校验。
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class ErrorDetail(BaseModel):
    """统一错误响应模型：{"code": str, "message": str}。"""

    code: str = Field(..., description="机器可读错误码")
    message: str = Field(..., description="人类可读错误描述")


# ============================================================
# companies 表相关模型
# ============================================================


class SearchItem(BaseModel):
    """企业搜索结果条目（companies 表精简字段）。"""

    company_id: str = Field(..., description="企业唯一ID")
    company_name: str = Field(..., description="企业名称")
    credit_code: Optional[str] = Field(None, description="统一社会信用代码")
    legal_rep: Optional[str] = Field(None, description="法定代表人")
    industry: Optional[str] = Field(None, description="所属行业")
    business_status: Optional[str] = Field(None, description="经营状态")
    data_type: str = Field(..., description="数据来源类型")


class CompanyProfile(BaseModel):
    """企业完整工商信息（companies 表全部字段）。"""

    company_id: str = Field(..., description="企业唯一ID")
    data_type: str = Field(..., description="数据来源类型")
    company_name: str = Field(..., description="企业名称")
    credit_code: Optional[str] = Field(None, description="统一社会信用代码")
    legal_rep: Optional[str] = Field(None, description="法定代表人")
    reg_capital: Optional[float] = Field(None, description="注册资本（万元）")
    paid_capital: Optional[float] = Field(None, description="实缴资本（万元）")
    established_date: Optional[str] = Field(None, description="成立日期")
    company_type: Optional[str] = Field(None, description="企业类型")
    industry: Optional[str] = Field(None, description="所属行业")
    reg_address: Optional[str] = Field(None, description="注册地址")
    business_scope: Optional[str] = Field(None, description="经营范围")
    reg_authority: Optional[str] = Field(None, description="登记机关")
    business_status: Optional[str] = Field(None, description="经营状态")
    listed_status: Optional[str] = Field(None, description="上市状态")
    contact_phone: Optional[str] = Field(None, description="联系电话")
    contact_email: Optional[str] = Field(None, description="联系邮箱")
    website: Optional[str] = Field(None, description="企业官网")
    update_date: Optional[str] = Field(None, description="数据更新时间")


# ============================================================
# business_events 表相关模型
# ============================================================


class BusinessEvent(BaseModel):
    """企业经营事件（business_events 表全部字段）。"""

    event_id: str = Field(..., description="事件唯一ID")
    company_id: str = Field(..., description="所属企业ID")
    event_type: str = Field(..., description="事件类型")
    event_date: Optional[str] = Field(None, description="事件发生日期")
    old_value: Optional[str] = Field(None, description="变更前值")
    new_value: Optional[str] = Field(None, description="变更后值")
    detail: Optional[str] = Field(None, description="事件详细描述")
    authority: Optional[str] = Field(None, description="登记/处罚机关")
    penalty_amount: Optional[float] = Field(None, description="处罚金额（元）")
    status: Optional[str] = Field(None, description="处理状态")
    source: Optional[str] = Field(None, description="数据来源")
    create_time: Optional[str] = Field(None, description="记录入库时间")


# ============================================================
# judicial_events 表相关模型
# ============================================================


class JudicialEvent(BaseModel):
    """企业司法事件（judicial_events 表全部字段）。"""

    event_id: str = Field(..., description="事件唯一ID")
    company_id: str = Field(..., description="所属企业ID")
    case_type: str = Field(..., description="案件类型")
    case_number: Optional[str] = Field(None, description="案号")
    court: Optional[str] = Field(None, description="受理法院")
    filing_date: Optional[str] = Field(None, description="立案/公告日期")
    close_date: Optional[str] = Field(None, description="结案日期")
    cause: Optional[str] = Field(None, description="案由")
    role: Optional[str] = Field(None, description="企业在本案中的角色")
    amount: Optional[float] = Field(None, description="涉案金额（元）")
    result: Optional[str] = Field(None, description="审理结果/执行情况")
    status: Optional[str] = Field(None, description="案件状态")
    source: Optional[str] = Field(None, description="数据来源")


# ============================================================
# relations 表相关模型
# ============================================================


class Relation(BaseModel):
    """企业关联关系（relations 表全部字段 + 双方企业名称）。"""

    relation_id: str = Field(..., description="关系唯一ID")
    from_company_id: str = Field(..., description="关系主体企业ID")
    to_company_id: str = Field(..., description="关系客体企业ID")
    relation_type: str = Field(..., description="关系类型")
    relation_detail: Optional[str] = Field(None, description="关系具体描述")
    equity_ratio: Optional[float] = Field(None, description="股权比例（0-1 小数）")
    amount: Optional[float] = Field(None, description="涉及金额（元）")
    start_date: Optional[str] = Field(None, description="关系起始日期")
    end_date: Optional[str] = Field(None, description="关系结束日期")
    status: Optional[str] = Field(None, description="关系状态")
    source: Optional[str] = Field(None, description="数据来源")
    update_time: Optional[str] = Field(None, description="记录更新时间")
    from_company_name: Optional[str] = Field(None, description="关系主体企业名称")
    to_company_name: Optional[str] = Field(None, description="关系客体企业名称")


# ============================================================
# public_opinion_events 表相关模型
# ============================================================


class PublicOpinionEvent(BaseModel):
    """企业舆情事件（public_opinion_events 表全部字段）。"""

    event_id: str = Field(..., description="事件唯一ID")
    company_id: str = Field(..., description="所属企业ID")
    publish_date: Optional[str] = Field(None, description="发布日期")
    topic: Optional[str] = Field(None, description="舆情主题")
    sentiment: Optional[str] = Field(None, description="情感倾向")
    source_type: Optional[str] = Field(None, description="来源类型")
    source_name: Optional[str] = Field(None, description="来源名称")
    title: Optional[str] = Field(None, description="舆情标题")
    summary: Optional[str] = Field(None, description="舆情摘要")
    verification_status: Optional[str] = Field(None, description="核实状态")
    response_status: Optional[str] = Field(None, description="响应状态")
    data_type: str = Field("simulated", description="数据来源类型")


# ============================================================
# financial_reports 表相关模型
# ============================================================


class FinancialReport(BaseModel):
    """企业财务报告（financial_reports 表全部字段 + 计算指标）。"""

    report_id: str = Field(..., description="报告唯一ID")
    company_id: str = Field(..., description="所属企业ID")
    period: Optional[str] = Field(None, description="报告期间")
    report_date: Optional[str] = Field(None, description="报告日期")
    revenue: Optional[float] = Field(None, description="营业收入（元）")
    net_profit: Optional[float] = Field(None, description="净利润（元）")
    total_assets: Optional[float] = Field(None, description="总资产（元）")
    total_liabilities: Optional[float] = Field(None, description="总负债（元）")
    current_assets: Optional[float] = Field(None, description="流动资产（元）")
    current_liabilities: Optional[float] = Field(None, description="流动负债（元）")
    operating_cash_flow: Optional[float] = Field(None, description="经营性现金流（元）")
    accounts_receivable: Optional[float] = Field(None, description="应收账款（元）")
    audit_opinion: Optional[str] = Field(None, description="审计意见")
    currency: Optional[str] = Field(None, description="货币单位")
    data_type: str = Field("simulated", description="数据来源类型")
    # 计算指标
    debt_ratio: Optional[float] = Field(None, description="资产负债率")
    current_ratio: Optional[float] = Field(None, description="流动比率")
    net_margin: Optional[float] = Field(None, description="净利率")
    revenue_yoy: Optional[float] = Field(None, description="营业收入同比增长率")
    profit_yoy: Optional[float] = Field(None, description="净利润同比增长率")


# ============================================================
# recruitment_events 表相关模型
# ============================================================


class RecruitmentEvent(BaseModel):
    """企业招聘事件（recruitment_events 表全部字段）。"""

    event_id: str = Field(..., description="事件唯一ID")
    company_id: str = Field(..., description="所属企业ID")
    publish_date: Optional[str] = Field(None, description="发布日期")
    event_type: Optional[str] = Field(None, description="事件类型")
    position_category: Optional[str] = Field(None, description="职位类别")
    position_name: Optional[str] = Field(None, description="职位名称")
    planned_headcount: Optional[int] = Field(None, description="计划招聘人数")
    salary_min: Optional[float] = Field(None, description="最低薪资（元/月）")
    salary_max: Optional[float] = Field(None, description="最高薪资（元/月）")
    location: Optional[str] = Field(None, description="工作地点")
    status: Optional[str] = Field(None, description="招聘状态")
    description: Optional[str] = Field(None, description="职位描述")
    data_type: str = Field("simulated", description="数据来源类型")


# ============================================================
# 响应模型
# ============================================================


class SearchResponse(BaseModel):
    """企业搜索响应。"""

    keyword: str = Field(..., description="本次搜索关键词")
    total: int = Field(..., description="命中数量")
    items: List[SearchItem] = Field(..., description="搜索结果列表")


class ProfileResponse(BaseModel):
    """企业基本信息响应。"""

    company_id: str = Field(..., description="企业唯一ID")
    profile: CompanyProfile = Field(..., description="完整工商信息")


class BusinessEventsResponse(BaseModel):
    """企业经营事件响应。"""

    company_id: str = Field(..., description="企业唯一ID")
    total: int = Field(..., description="事件数量")
    items: List[BusinessEvent] = Field(..., description="经营事件列表")


class JudicialEventsResponse(BaseModel):
    """企业司法事件响应。"""

    company_id: str = Field(..., description="企业唯一ID")
    total: int = Field(..., description="事件数量")
    items: List[JudicialEvent] = Field(..., description="司法事件列表")


class RelationsResponse(BaseModel):
    """企业关联关系响应。"""

    company_id: str = Field(..., description="企业唯一ID")
    total: int = Field(..., description="关联关系数量")
    items: List[Relation] = Field(..., description="关联关系列表")


class PublicOpinionEventsResponse(BaseModel):
    """企业舆情事件响应。"""

    company_id: str = Field(..., description="企业唯一ID")
    total: int = Field(..., description="事件数量")
    items: List[PublicOpinionEvent] = Field(..., description="舆情事件列表")


class FinancialReportsResponse(BaseModel):
    """企业财务报告响应。"""

    company_id: str = Field(..., description="企业唯一ID")
    total: int = Field(..., description="报告数量")
    items: List[FinancialReport] = Field(..., description="财务报告列表")


class RecruitmentEventsResponse(BaseModel):
    """企业招聘事件响应。"""

    company_id: str = Field(..., description="企业唯一ID")
    total: int = Field(..., description="事件数量")
    items: List[RecruitmentEvent] = Field(..., description="招聘事件列表")


class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str = Field(..., description="服务状态")


# ============================================================
# 关系网络模型（V1.1 新增）
# ============================================================


class NetworkNode(BaseModel):
    """关系网络节点。"""

    company_id: str = Field(..., description="企业唯一ID")
    company_name: str = Field(..., description="企业名称")
    industry: Optional[str] = Field(None, description="所属行业")
    business_status: Optional[str] = Field(None, description="经营状态")
    depth: int = Field(..., description="距离目标企业的深度（0=目标企业自身）")


class NetworkEdge(BaseModel):
    """关系网络边。"""

    relation_id: str = Field(..., description="关系唯一ID")
    source: str = Field(..., description="关系主体企业ID")
    target: str = Field(..., description="关系客体企业ID")
    relation_type: str = Field(..., description="关系类型")
    equity_ratio: Optional[float] = Field(None, description="股权比例（0-1 小数）")
    amount: Optional[float] = Field(None, description="涉及金额（元）")
    status: Optional[str] = Field(None, description="关系状态")


class RelationNetworkResponse(BaseModel):
    """企业关联关系网络响应。"""

    root_company_id: str = Field(..., description="目标企业ID")
    nodes: List[NetworkNode] = Field(..., description="网络节点列表")
    edges: List[NetworkEdge] = Field(..., description="网络边列表")
    truncated: bool = Field(..., description="是否因达到最大节点数而截断")


# ============================================================
# 风险分析接口模型（第二阶段）
# ============================================================


class AnalysisRequest(BaseModel):
    """POST /api/analysis 请求体。"""

    company_id: str = Field(..., min_length=1, description="企业唯一ID，例如 C001")

    @field_validator("company_id")
    @classmethod
    def _company_id_not_blank(cls, value: str) -> str:
        """company_id 必填且不能为空白字符串。"""
        if not value.strip():
            raise ValueError("company_id 不能为空")
        return value


class TriggeredRuleItem(BaseModel):
    """Risk Rule Engine 触发的规则条目。"""

    rule_id: str = Field(..., description="规则唯一ID")
    rule_name: str = Field(..., description="规则名称")
    dimension: str = Field(..., description="所属维度")
    evidence_id: str = Field(..., description="关联的 Evidence ID")
    score: int = Field(..., description="该规则分值")
    severity: str = Field(..., description="严重程度: critical/high/medium/low")
    description: str = Field("", description="风险解释")


class HardRuleHitItem(BaseModel):
    """Risk Rule Engine 触发的硬规则条目。"""

    rule_id: str = Field(..., description="硬规则唯一ID")
    reason: str = Field(..., description="触发原因")
    force_level: str = Field(..., description="强制提升到的风险等级")


class RiskScoring(BaseModel):
    """Risk Rule Engine 确定性评分结果（V2.1 新增）。

    由 Rule Engine 确定，不允许 LLM 直接修改。
    """

    risk_score: int = Field(..., description="总风险分（正整数，越大越严重）")
    risk_level: str = Field(..., description="风险等级（低风险/中风险/中高风险/高风险）")
    triggered_rules: List[TriggeredRuleItem] = Field(
        default_factory=list, description="触发的规则列表"
    )
    hard_rule_hits: List[HardRuleHitItem] = Field(
        default_factory=list, description="触发的硬规则列表"
    )
    dimension_scores: Dict[str, float] = Field(
        default_factory=dict, description="各维度得分"
    )
    evidence_ids: List[str] = Field(
        default_factory=list, description="参与评分的 Evidence IDs（去重）"
    )
    total_evidence_count: int = Field(0, description="参与评分的 Evidence 总数")


class AnalysisResponse(BaseModel):
    """POST /api/analysis 响应。"""

    task_id: Optional[str] = Field(None, description="任务唯一ID（V1.4 新增）")
    company_id: str = Field(..., description="企业唯一ID")
    status: str = Field("completed", description="分析状态（恒为 completed，Harness 已结束）")
    report: str = Field("", description="最终企业风险调查报告全文")
    verification_status: Optional[str] = Field(
        None, description="Harness 审核状态：PASS / UNRESOLVED"
    )
    risk_level: Optional[str] = Field(None, description="风险等级（Rule Engine 确定，LLM best-effort 兜底）")
    summary: Optional[str] = Field(None, description="风险总结章节（best-effort 解析）")
    evidence_ids: List[str] = Field(
        default_factory=list, description="关键证据编号（Bxxx/Jxxx/Rxxx/Pxxx/Fxxx/Hxxx，去重保序）"
    )
    related_companies: List[str] = Field(
        default_factory=list, description="报告涉及的关联企业ID（不含目标企业）"
    )
    report_path: Optional[str] = Field(
        None, description="最终报告文件相对路径（runs/web/<id>/report_final.md）"
    )
    duration_seconds: float = Field(..., description="Harness 分析耗时（秒）")
    risk_scoring: Optional[RiskScoring] = Field(
        None, description="Risk Rule Engine 确定性评分结果（V2.1 新增）"
    )


# ============================================================
# 异步任务模型（第五阶段）
# ============================================================


class CreateTaskRequest(BaseModel):
    """POST /api/analysis/tasks 请求体。"""

    company_id: str = Field(..., min_length=1, description="企业唯一ID，例如 C007")
    force_new: bool = Field(False, description="是否强制创建新任务（替换旧任务）。用于重新分析按钮。")

    @field_validator("company_id")
    @classmethod
    def _company_id_not_blank(cls, value: str) -> str:
        """company_id 必填且不能为空白字符串。"""
        if not value.strip():
            raise ValueError("company_id 不能为空")
        return value


class TaskResponse(BaseModel):
    """异步任务响应模型。

    用于 POST /api/analysis/tasks 和 GET /api/analysis/tasks/{task_id}。
    """

    task_id: str = Field(..., description="任务唯一ID")
    company_id: str = Field(..., description="企业唯一ID")
    status: str = Field(..., description="任务状态: queued / running / completed / failed / cancelled")
    created_at: str = Field(..., description="任务创建时间（ISO 8601）")
    started_at: Optional[str] = Field(None, description="任务开始执行时间（ISO 8601）")
    finished_at: Optional[str] = Field(None, description="任务完成时间（ISO 8601）")
    error: Optional[str] = Field(None, description="失败时的错误信息")
    result: Optional[AnalysisResponse] = Field(None, description="分析结果（仅 completed 时有值）")
    event_count: int = Field(0, description="已收到的事件数（V1.3 新增）")
    last_event_at: Optional[str] = Field(None, description="最后一个事件的时间（V1.3 新增）")
    current_stage: Optional[str] = Field(None, description="当前阶段（V1.3 新增）")
    cancel_reason: Optional[str] = Field(None, description="取消原因（V1.4 新增）")
    replacement_task_id: Optional[str] = Field(None, description="替换此任务的新任务ID（V1.4 新增）")
    process_pid: Optional[int] = Field(None, description="Harness 进程 PID（V1.4 新增）")
    process_alive: bool = Field(False, description="Harness 进程是否存活（V1.4 新增）")


# ============================================================
# Investigation Trace 模型（V1.3 新增）
# ============================================================


class TraceEventResponse(BaseModel):
    """Investigation Trace 事件条目。"""

    event_id: str = Field(..., description="事件唯一ID")
    sequence: int = Field(..., description="事件序号")
    timestamp: str = Field(..., description="事件时间（ISO 8601）")
    type: str = Field(..., description="事件类型")
    agent: str = Field(..., description="执行 agent")
    title: str = Field(..., description="用户可读标题")
    description: str = Field(..., description="用户可读描述")
    company_id: Optional[str] = Field(None, description="相关企业ID")
    company_name: Optional[str] = Field(None, description="相关企业名称")
    tool: Optional[str] = Field(None, description="原始工具名")
    evidence_ids: List[str] = Field(default_factory=list, description="关键证据编号")
    status: str = Field(..., description="事件状态: completed / in_progress / failed")


class TraceResponse(BaseModel):
    """Investigation Trace 响应。"""

    task_id: str = Field(..., description="任务唯一ID")
    company_id: str = Field(..., description="企业唯一ID")
    task_status: str = Field(..., description="任务状态")
    event_count: int = Field(..., description="trace events 数量")
    events: List[TraceEventResponse] = Field(..., description="trace events 列表")


# ============================================================
# System Status 模型（V1.4 新增）
# ============================================================


class ActiveTaskInfo(BaseModel):
    """当前活跃任务信息。"""

    task_id: str = Field(..., description="任务唯一ID")
    company_id: str = Field(..., description="企业唯一ID")
    status: str = Field(..., description="任务状态")
    process_pid: Optional[int] = Field(None, description="Harness 进程 PID")
    process_pgid: Optional[int] = Field(None, description="Harness 进程 PGID")
    process_alive: bool = Field(False, description="进程是否存活")
    started_at: Optional[str] = Field(None, description="开始执行时间")


class SystemStatusResponse(BaseModel):
    """系统状态响应。

    显示当前是否有活跃的 Harness 进程运行。
    """

    active_task: Optional[ActiveTaskInfo] = Field(None, description="当前活跃任务（无则为 null）")
    harness_process_alive: bool = Field(False, description="是否有 harness 进程存活")
    pid: Optional[int] = Field(None, description="当前活跃进程 PID")
    project_root: str = Field(..., description="项目根目录")


# ============================================================
# Evidence Detail 模型（V1.4 新增）
# ============================================================


class EvidenceResponse(BaseModel):
    """Evidence 详情响应。

    返回确定性数据库事实，不包含模型判断。
    V2.0: 新增 title 和 description 字段，来自 Evidence Registry。
    """

    evidence_id: str = Field(..., description="证据编号（Bxxx/Jxxx/Rxxx）")
    evidence_type: str = Field(..., description="证据类型: business / judicial / relation")
    company_id: Optional[str] = Field(None, description="所属企业ID")
    company_name: Optional[str] = Field(None, description="所属企业名称")
    title: Optional[str] = Field(None, description="证据标题（人类可读）")
    description: Optional[str] = Field(None, description="证据描述")
    from_company_id: Optional[str] = Field(None, description="关系主体企业ID（仅 relation）")
    from_company_name: Optional[str] = Field(None, description="关系主体企业名称（仅 relation）")
    to_company_id: Optional[str] = Field(None, description="关系客体企业ID（仅 relation）")
    to_company_name: Optional[str] = Field(None, description="关系客体企业名称（仅 relation）")
    data: dict = Field(..., description="原始记录数据")
    source: Optional[str] = Field(None, description="数据来源: simulated / real")


# ============================================================
# V1.6 Investigation Network 模型
# ============================================================


class InvestigationNode(BaseModel):
    """调查网络节点：在关系网络节点基础上叠加调查状态。"""

    company_id: str = Field(..., description="企业唯一ID")
    company_name: str = Field(..., description="企业名称")
    industry: Optional[str] = Field(None, description="所属行业")
    business_status: Optional[str] = Field(None, description="经营状态")
    depth: int = Field(0, description="距离目标企业的深度（0=目标企业自身）")
    is_root: bool = Field(False, description="是否为目标企业")
    investigation_status: str = Field(
        ...,
        description="调查状态: root / investigated / discovered / not_investigated",
    )
    investigation_order: Optional[int] = Field(
        None, description="调查顺序（仅 investigated 状态有值）"
    )
    first_investigated_at: Optional[str] = Field(
        None, description="首次被调查的时间（ISO 8601）"
    )
    evidence_ids: List[str] = Field(
        default_factory=list, description="关联的证据编号列表"
    )
    evidence_count: int = Field(0, description="关联证据数量")
    supplementary: bool = Field(
        False, description="是否为 coverage auditor 补充调查的企业"
    )
    risk_level: Optional[str] = Field(None, description="风险等级（如：高风险、中等风险、低风险）")
    risk_tags: List[str] = Field(
        default_factory=list, description="关键风险标签（如：诉讼案件、被执行人、股权冻结）"
    )


class InvestigationEdge(BaseModel):
    """调查网络边：在关系网络边基础上叠加调查状态。"""

    relation_id: str = Field(..., description="关系唯一ID")
    source: str = Field(..., description="关系主体企业ID")
    target: str = Field(..., description="关系客体企业ID")
    relation_type: str = Field(..., description="关系类型")
    equity_ratio: Optional[float] = Field(None, description="股权比例（0-1 小数）")
    amount: Optional[float] = Field(None, description="涉及金额（元）")
    status: Optional[str] = Field(None, description="关系状态")
    investigation_status: str = Field(
        ..., description="调查状态: traversed / discovered / not_used"
    )
    first_used_at: Optional[str] = Field(
        None, description="首次被遍历的时间（ISO 8601）"
    )
    supplementary: bool = Field(
        False, description="是否涉及 coverage 补充企业"
    )
    evidence_referenced: bool = Field(
        False, description="该边的遍历是否引用了证据"
    )
    investigation_reason: Optional[str] = Field(
        None, description="调查原因说明"
    )


class InvestigationNetworkStats(BaseModel):
    """调查网络统计数据。"""

    total_network_nodes: int = Field(..., description="网络总节点数")
    investigated_nodes: int = Field(..., description="已调查节点数（含 root）")
    discovered_nodes: int = Field(..., description="已发现但未调查的节点数")
    uninvestigated_nodes: int = Field(..., description="未调查的节点数")
    investigated_edges: int = Field(..., description="已遍历的边数")
    total_evidence: int = Field(..., description="总证据数")


class InvestigationNetworkResponse(BaseModel):
    """调查网络响应（V1.6）。"""

    task_id: Optional[str] = Field(None, description="任务唯一ID（历史分析可能为 None）")
    company_id: str = Field(..., description="目标企业ID")
    task_status: str = Field(..., description="任务状态")
    nodes: List[InvestigationNode] = Field(..., description="网络节点列表")
    edges: List[InvestigationEdge] = Field(..., description="网络边列表")
    stats: InvestigationNetworkStats = Field(..., description="统计数据")
