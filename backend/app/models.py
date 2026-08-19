"""
企业关联风险智能洞察系统 —— API 数据模型（Pydantic）。

所有字段与 risk.db 表结构（schema.sql）保持一致，
通过 FastAPI response_model 对输出做统一校验。
"""

from __future__ import annotations

from typing import List, Optional

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


class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str = Field(..., description="服务状态")


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


class AnalysisResponse(BaseModel):
    """POST /api/analysis 响应。"""

    company_id: str = Field(..., description="企业唯一ID")
    status: str = Field("completed", description="分析状态（恒为 completed，Harness 已结束）")
    report: str = Field("", description="最终企业风险调查报告全文")
    verification_status: Optional[str] = Field(
        None, description="Harness 审核状态：PASS / UNRESOLVED"
    )
    risk_level: Optional[str] = Field(None, description="风险等级（best-effort 解析）")
    summary: Optional[str] = Field(None, description="风险总结章节（best-effort 解析）")
    evidence_ids: List[str] = Field(
        default_factory=list, description="关键证据编号（Bxxx/Jxxx/Rxxx，去重保序）"
    )
    related_companies: List[str] = Field(
        default_factory=list, description="报告涉及的关联企业ID（不含目标企业）"
    )
    report_path: Optional[str] = Field(
        None, description="最终报告文件相对路径（runs/web/<id>/report_final.md）"
    )
    duration_seconds: float = Field(..., description="Harness 分析耗时（秒）")
