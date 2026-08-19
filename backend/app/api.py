"""
企业关联风险智能洞察系统 —— API 路由层。

第一阶段：6 个只读查询接口，全部封装 src/risk_tools.py 的查询函数，
不包含任何业务逻辑、不允许直接写 SQL。

第二阶段：POST /api/analysis 风险分析接口，通过 Risk Harness Adapter
真实调用 OpenCode Headless（risk-orchestrator + coverage-auditor + risk-verifier）
完成风险分析，本层不复制 Harness 逻辑、不硬编码风险判断。

接口清单：
- GET  /api/companies/search?keyword=xxx
- GET  /api/companies/{company_id}
- GET  /api/companies/{company_id}/business-events
- GET  /api/companies/{company_id}/judicial-events
- GET  /api/companies/{company_id}/relations
- POST /api/analysis
（/health 在 main.py 中定义）
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List

from fastapi import APIRouter, HTTPException, Query, status

from . import deps
from .analysis_service import analyze_company
from .deps import (
    ERROR_ANALYSIS_FAILED,
    ERROR_COMPANY_NOT_FOUND,
    ERROR_INTERNAL,
    ERROR_INVALID_KEYWORD,
)
from .harness_adapter import CompanyNotFoundError, HarnessError
from .models import (
    AnalysisRequest,
    AnalysisResponse,
    BusinessEventsResponse,
    ErrorDetail,
    JudicialEventsResponse,
    ProfileResponse,
    RelationsResponse,
    SearchResponse,
)

logger = logging.getLogger("risk-api")

router = APIRouter(prefix="/api", tags=["companies"])


# ------------------------------------------------------------
# 内部工具
# ------------------------------------------------------------


def _run_tool(fn: Callable[..., Any], *args: Any) -> Any:
    """
    执行 risk_tools 查询函数，异常统一转为 500 INTERNAL_ERROR。

    risk_tools 内部只抛 sqlite3 / OSError 等异常，不会抛 HTTPException，
    因此这里直接捕获 Exception 即可，不抛裸异常。
    """
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001 —— 统一转为内部错误响应
        logger.exception("risk_tools 调用失败: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=deps.error_detail(ERROR_INTERNAL, f"服务器内部错误：{exc}"),
        ) from exc


def _require_company_exists(company_id: str) -> None:
    """
    企业存在性检查（复用 risk_tools.get_company_profile）。

    不存在时抛出 404 + COMPANY_NOT_FOUND。
    """
    exists = _run_tool(deps.company_exists, company_id)
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=deps.error_detail(
                ERROR_COMPANY_NOT_FOUND, f"未找到企业 {company_id}"
            ),
        )


# ------------------------------------------------------------
# 接口 1：企业搜索
# ------------------------------------------------------------


@router.get(
    "/companies/search",
    response_model=SearchResponse,
    responses={400: {"model": ErrorDetail}, 500: {"model": ErrorDetail}},
    summary="搜索企业",
    description="根据企业ID、企业名称或统一社会信用代码搜索企业；keyword 必填。",
)
def search_companies(
    keyword: str = Query(None, description="企业ID、企业名称或统一社会信用代码"),
) -> SearchResponse:
    """按关键词搜索企业。"""

    if keyword is None or not keyword.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=deps.error_detail(ERROR_INVALID_KEYWORD, "keyword 不能为空"),
        )

    keyword = keyword.strip()
    items: List[Dict[str, Any]] = _run_tool(deps.search_company, keyword)

    return SearchResponse(keyword=keyword, total=len(items), items=items)


# ------------------------------------------------------------
# 接口 2：企业基本信息
# ------------------------------------------------------------


@router.get(
    "/companies/{company_id}",
    response_model=ProfileResponse,
    responses={404: {"model": ErrorDetail}, 500: {"model": ErrorDetail}},
    summary="查询企业基本信息",
)
def get_company(company_id: str) -> ProfileResponse:
    """查询指定企业的完整工商信息。"""

    cid = deps.normalize_company_id(company_id)
    profile: Dict[str, Any] = _run_tool(deps.get_company_profile, cid)

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=deps.error_detail(ERROR_COMPANY_NOT_FOUND, f"未找到企业 {cid}"),
        )

    return ProfileResponse(company_id=cid, profile=profile)


# ------------------------------------------------------------
# 接口 3：企业经营事件
# ------------------------------------------------------------


@router.get(
    "/companies/{company_id}/business-events",
    response_model=BusinessEventsResponse,
    responses={404: {"model": ErrorDetail}, 500: {"model": ErrorDetail}},
    summary="查询企业经营事件",
)
def get_company_business_events(company_id: str) -> BusinessEventsResponse:
    """查询指定企业的全部经营（工商动态）事件。"""

    cid = deps.normalize_company_id(company_id)
    _require_company_exists(cid)

    items: List[Dict[str, Any]] = _run_tool(deps.get_business_events, cid)
    return BusinessEventsResponse(company_id=cid, total=len(items), items=items)


# ------------------------------------------------------------
# 接口 4：企业司法事件
# ------------------------------------------------------------


@router.get(
    "/companies/{company_id}/judicial-events",
    response_model=JudicialEventsResponse,
    responses={404: {"model": ErrorDetail}, 500: {"model": ErrorDetail}},
    summary="查询企业司法事件",
)
def get_company_judicial_events(company_id: str) -> JudicialEventsResponse:
    """查询指定企业的全部司法事件（诉讼、被执行、失信等）。"""

    cid = deps.normalize_company_id(company_id)
    _require_company_exists(cid)

    items: List[Dict[str, Any]] = _run_tool(deps.get_judicial_events, cid)
    return JudicialEventsResponse(company_id=cid, total=len(items), items=items)


# ------------------------------------------------------------
# 接口 5：企业关联关系
# ------------------------------------------------------------


@router.get(
    "/companies/{company_id}/relations",
    response_model=RelationsResponse,
    responses={404: {"model": ErrorDetail}, 500: {"model": ErrorDetail}},
    summary="查询企业关联关系",
    description="返回指定企业的一跳直接关联关系。",
)
def get_company_relations(company_id: str) -> RelationsResponse:
    """查询指定企业的全部一跳关联关系。"""

    cid = deps.normalize_company_id(company_id)
    _require_company_exists(cid)

    items: List[Dict[str, Any]] = _run_tool(deps.get_company_relations, cid)
    return RelationsResponse(company_id=cid, total=len(items), items=items)


# ------------------------------------------------------------
# 接口 6：AI 风险分析（第二阶段）
#
# 错误码约定（见代码注释）：
# - 企业不存在        → 404 COMPANY_NOT_FOUND（与服务层 CompanyNotFoundError 对齐）
# - Harness 不可用    → 503 ANALYSIS_FAILED（opencode 缺失 / 超时 / 重试后无状态）
#   说明：超时未单独使用 504，统一归入 503，简化前端错误处理；
#   所有 Harness 相关失败都代表"分析服务当前不可用"，语义一致。
# - 请求体非法        → 400 INVALID_REQUEST（main.py 的 RequestValidationError 处理器）
# ------------------------------------------------------------


@router.post(
    "/analysis",
    response_model=AnalysisResponse,
    responses={
        400: {"model": ErrorDetail},
        404: {"model": ErrorDetail},
        503: {"model": ErrorDetail},
    },
    summary="AI 风险分析",
    description=(
        "对指定企业执行一次完整风险分析：真实调用 Risk Harness"
        "（opencode headless：risk-orchestrator + coverage-auditor + risk-verifier）。"
        "同步阻塞，实测耗时 3-20 分钟；复杂案例（多轮 verifier 复核）可达 10-20 分钟，"
        "建议客户端/HTTP 超时设置 ≥ 20 分钟。"
    ),
    tags=["analysis"],
)
def create_analysis(payload: AnalysisRequest) -> AnalysisResponse:
    """对指定企业执行完整风险分析并返回结构化结果。"""

    try:
        result = analyze_company(payload.company_id)
    except CompanyNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=deps.error_detail(
                ERROR_COMPANY_NOT_FOUND, f"未找到企业 {exc.company_id}"
            ),
        ) from exc
    except HarnessError as exc:
        # 503：Harness 调用失败（opencode 缺失 / 超时 / 重试后仍无审核状态）
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=deps.error_detail(ERROR_ANALYSIS_FAILED, str(exc)),
        ) from exc

    return AnalysisResponse(**result)
