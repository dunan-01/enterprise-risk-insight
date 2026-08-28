"""
企业关联风险智能洞察系统 —— API 路由层。

第一阶段：6 个只读查询接口，全部封装 src/risk_tools.py 的查询函数，
不包含任何业务逻辑、不允许直接写 SQL。

第二阶段：POST /api/analysis 风险分析接口，通过 Risk Harness Adapter
真实调用 OpenCode Headless（risk-orchestrator + coverage-auditor + risk-verifier）
完成风险分析，本层不复制 Harness 逻辑、不硬编码风险判断。

第三阶段：GET /api/companies/{company_id}/analysis/latest 读取已有分析结果。

第四阶段（V1.1）：
- GET /api/companies/{company_id}/relation-network 企业完整关联关系网络（BFS 遍历）
- GET /api/analysis/{company_id}/latest/pdf AI 风险报告 PDF 导出

接口清单：
- GET  /api/companies/search?keyword=xxx
- GET  /api/companies/{company_id}
- GET  /api/companies/{company_id}/business-events
- GET  /api/companies/{company_id}/judicial-events
- GET  /api/companies/{company_id}/relations
- GET  /api/companies/{company_id}/analysis/latest
- POST /api/analysis
- GET  /api/companies/{company_id}/relation-network
- GET  /api/analysis/{company_id}/latest/pdf
（/health 在 main.py 中定义）
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List

from fastapi import APIRouter, HTTPException, Query, status

from . import deps
from .analysis_service import AnalysisNotFoundError, analyze_company, load_latest_analysis
from .relation_network_service import build_relation_network
from .pdf_service import generate_report_pdf
from .deps import (
    ERROR_ANALYSIS_FAILED,
    ERROR_ANALYSIS_NOT_FOUND,
    ERROR_COMPANY_NOT_FOUND,
    ERROR_INTERNAL,
    ERROR_INVALID_KEYWORD,
    ERROR_TASK_NOT_FOUND,
)
from .harness_adapter import CompanyNotFoundError, HarnessError
from .models import (
    AnalysisRequest,
    AnalysisResponse,
    BusinessEventsResponse,
    CreateTaskRequest,
    ErrorDetail,
    JudicialEventsResponse,
    ProfileResponse,
    RelationsResponse,
    RelationNetworkResponse,
    SearchResponse,
    SystemStatusResponse,
    ActiveTaskInfo,
    TaskResponse,
    TraceResponse,
)
from .task_manager import TaskManager, TaskInfo, _TASKS_DIR, _is_pid_alive

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
# 接口 6：读取已有分析结果（第三阶段）
#
# 从 runs/web/<company_id>/analysis_result.json 读取，
# 不触发 Harness、不修改任何数据。
#
# 错误码约定：
# - 企业不存在        → 404 COMPANY_NOT_FOUND
# - 无历史分析结果    → 404 ANALYSIS_NOT_FOUND
# - 文件读取失败      → 500 INTERNAL_ERROR
# ------------------------------------------------------------


@router.get(
    "/companies/{company_id}/analysis/latest",
    response_model=AnalysisResponse,
    responses={
        404: {"model": ErrorDetail},
        500: {"model": ErrorDetail},
    },
    summary="读取已有分析结果",
    description="读取指定企业最近一次 Web 分析结果（runs/web/<id>/analysis_result.json）。不触发 Harness。",
    tags=["analysis"],
)
def get_latest_analysis(company_id: str) -> AnalysisResponse:
    """读取指定企业最近一次 Web 分析结果。"""

    cid = deps.normalize_company_id(company_id)
    _require_company_exists(cid)

    try:
        result = load_latest_analysis(cid)
    except AnalysisNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=deps.error_detail(
                ERROR_ANALYSIS_NOT_FOUND,
                f"未找到企业 {cid} 的历史分析结果，请先执行 AI 风险分析",
            ),
        ) from exc

    return AnalysisResponse(**result)


# ------------------------------------------------------------
# 接口 7：AI 风险分析（第二阶段）
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


# ------------------------------------------------------------
# 内部工具：TaskInfo → TaskResponse 转换
# ------------------------------------------------------------


def _task_to_response(task: TaskInfo) -> TaskResponse:
    """将 TaskInfo 转换为 API 响应模型 TaskResponse。

    completed 状态下将 result dict 包装为 AnalysisResponse，
    其他状态下 result 为 None。
    """
    analysis_result = None
    if task.result is not None:
        try:
            analysis_result = AnalysisResponse(**task.result)
        except Exception:
            logger.warning("任务 %s 的 result 无法解析为 AnalysisResponse", task.task_id)

    return TaskResponse(
        task_id=task.task_id,
        company_id=task.company_id,
        status=task.status.value,
        created_at=task.created_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
        error=task.error,
        result=analysis_result,
        event_count=task.event_count,
        last_event_at=task.last_event_at,
        current_stage=task.current_stage,
        cancel_reason=task.cancel_reason,
        replacement_task_id=task.replacement_task_id,
        process_pid=task.process_pid,
        process_alive=task.process_alive,
    )


# ============================================================
# 接口 10：创建异步分析任务
# ============================================================

_task_manager = TaskManager()


@router.post(
    "/analysis/tasks",
    response_model=TaskResponse,
    responses={
        404: {"model": ErrorDetail},
        409: {"model": ErrorDetail},
        500: {"model": ErrorDetail},
    },
    summary="创建异步分析任务",
    description=(
        "创建一个异步风险分析任务并立即返回 task_id。"
        "后台线程将调用 Risk Harness 执行分析（耗时 3-20 分钟）。"
        "同一企业已有 queued/running 任务时返回现有任务（不重复创建）。"
    ),
    tags=["analysis"],
)
def create_analysis_task(payload: CreateTaskRequest) -> TaskResponse:
    """创建异步分析任务，立即返回 task_id。

    SINGLE ACTIVE HARNESS 流程：
    1. reconcile_existing_harness() —— 清理旧 active / orphan Harness
    2. 确认系统中不存在旧 risk-orchestrator
    3. 同企业双击防护：已有 running task 时返回 existing
    4. force_new=True 时：强制替换旧任务
    """

    try:
        task = _task_manager.create_task(
            payload.company_id,
            force_new=payload.force_new,
        )
    except CompanyNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=deps.error_detail(
                ERROR_COMPANY_NOT_FOUND, f"未找到企业 {exc.company_id}"
            ),
        ) from exc
    except HarnessError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=deps.error_detail(
                "HARNESS_CLEANUP_FAILED",
                str(exc),
            ),
        ) from exc

    return _task_to_response(task)


# ============================================================
# 接口 11：查询任务状态
# ============================================================


@router.get(
    "/analysis/tasks/{task_id}",
    response_model=TaskResponse,
    responses={
        404: {"model": ErrorDetail},
        500: {"model": ErrorDetail},
    },
    summary="查询分析任务状态",
    description="根据 task_id 查询异步分析任务的当前状态和结果。",
    tags=["analysis"],
)
def get_analysis_task(task_id: str) -> TaskResponse:
    """查询任务状态。"""

    task = _task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=deps.error_detail(
                ERROR_TASK_NOT_FOUND, f"未找到任务 {task_id}"
            ),
        )

    return _task_to_response(task)


# ============================================================
# 接口 12：查询企业当前活跃任务
# ============================================================


@router.get(
    "/analysis/tasks/company/{company_id}/active",
    response_model=TaskResponse,
    responses={
        404: {"model": ErrorDetail},
        500: {"model": ErrorDetail},
    },
    summary="查询企业当前活跃任务",
    description=(
        "查询指定企业当前的活跃分析任务（queued/running）。"
        "无活跃任务时返回 404。"
    ),
    tags=["analysis"],
)
def get_company_active_task(company_id: str) -> TaskResponse:
    """查询企业当前活跃任务。"""

    cid = deps.normalize_company_id(company_id)

    # 企业存在性检查
    exists = _run_tool(deps.company_exists, cid)
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=deps.error_detail(
                ERROR_COMPANY_NOT_FOUND, f"未找到企业 {cid}"
            ),
        )

    task = _task_manager.get_active_task_for_company(cid)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=deps.error_detail(
                ERROR_TASK_NOT_FOUND,
                f"企业 {cid} 当前无活跃分析任务",
            ),
        )

    return _task_to_response(task)


# ============================================================
# 接口 13：获取任务的 Investigation Trace（V1.3 新增）
# ============================================================


@router.get(
    "/analysis/tasks/{task_id}/trace",
    response_model=TraceResponse,
    responses={
        404: {"model": ErrorDetail},
        500: {"model": ErrorDetail},
    },
    summary="获取任务的 Investigation Trace",
    description=(
        "根据 task_id 获取任务的 Investigation Trace 事件流。"
        "返回结构化 trace events，用于前端展示调查过程的时间线。"
    ),
    tags=["analysis"],
)
def get_analysis_task_trace(task_id: str) -> TraceResponse:
    """获取任务的 Investigation Trace 事件流。"""

    task = _task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=deps.error_detail(
                ERROR_TASK_NOT_FOUND, f"未找到任务 {task_id}"
            ),
        )

    # 从 per-task 目录读取 session_events.jsonl
    task_dir = _TASKS_DIR / task_id
    raw_events_file = task_dir / "session_events.jsonl"

    raw_events: List[Dict[str, Any]] = []
    if raw_events_file.exists():
        try:
            with open(raw_events_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        import json as _json
                        raw_events.append(_json.loads(line))
                    except _json.JSONDecodeError:
                        continue
        except OSError as exc:
            logger.warning("[Trace] 读取 session_events.jsonl 失败: %s", exc)

    # 转换为结构化 trace events（传入 task_status 以控制 lifecycle 事件）
    from .trace_service import parse_trace_events
    trace_events = parse_trace_events(raw_events, task_status=task.status.value)

    return TraceResponse(
        task_id=task.task_id,
        company_id=task.company_id,
        task_status=task.status.value,
        event_count=len(trace_events),
        events=trace_events,
    )


# ============================================================
# 接口 8：企业关联关系网络（V1.1 新增）
# ============================================================


@router.get(
    "/companies/{company_id}/relation-network",
    response_model=RelationNetworkResponse,
    responses={404: {"model": ErrorDetail}, 500: {"model": ErrorDetail}},
    summary="查询企业完整关联关系网络",
    description="从目标企业开始，BFS 遍历所有关联企业，返回完整关系网络。",
)
def get_relation_network(company_id: str) -> RelationNetworkResponse:
    """查询指定企业的完整关联关系网络。"""

    cid = deps.normalize_company_id(company_id)
    _require_company_exists(cid)

    try:
        result = build_relation_network(cid)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=deps.error_detail(ERROR_COMPANY_NOT_FOUND, str(exc)),
        ) from exc
    except Exception as exc:
        logger.exception("关系网络构建失败: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=deps.error_detail(ERROR_INTERNAL, f"关系网络构建失败：{exc}"),
        ) from exc

    return RelationNetworkResponse(**result)


# ============================================================
# 接口 9：AI 风险报告 PDF 导出（V1.1 新增）
# ============================================================

from fastapi.responses import FileResponse

RUNS_WEB_ROOT = deps.PROJECT_ROOT / "runs" / "web"


@router.get(
    "/analysis/{company_id}/latest/pdf",
    response_class=FileResponse,
    responses={
        404: {"model": ErrorDetail},
        500: {"model": ErrorDetail},
    },
    summary="导出 AI 风险报告 PDF",
    description="读取已有分析结果并生成 PDF 下载。不触发 Harness。",
    tags=["analysis"],
)
def export_analysis_pdf(company_id: str) -> FileResponse:
    """导出指定企业最近一次 AI 风险分析报告的 PDF。"""

    cid = deps.normalize_company_id(company_id)
    _require_company_exists(cid)

    # 检查是否有分析结果
    result_path = RUNS_WEB_ROOT / cid / "analysis_result.json"
    if not result_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=deps.error_detail(
                ERROR_ANALYSIS_NOT_FOUND,
                f"未找到企业 {cid} 的历史分析结果，请先执行 AI 风险分析",
            ),
        )

    # 生成 PDF
    pdf_path = generate_report_pdf(cid)
    if pdf_path is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=deps.error_detail(
                ERROR_INTERNAL,
                f"企业 {cid} 的 PDF 报告生成失败",
            ),
        )

    # 获取企业名称用于文件名
    profile = deps.get_company_profile(cid)
    company_name = profile.get("company_name", cid) if profile else cid

    # 返回文件下载
    filename = f"{cid}_{company_name}_企业风险调查报告.pdf"
    return FileResponse(
        path=str(pdf_path),
        filename=filename,
        media_type="application/pdf",
    )


# ============================================================
# 接口 14：系统状态（V1.4 新增）
# ============================================================


@router.get(
    "/analysis/system-status",
    response_model=SystemStatusResponse,
    responses={500: {"model": ErrorDetail}},
    summary="查询系统状态",
    description=(
        "查询当前是否有活跃的 Harness 进程运行。"
        "用于前端和开发调试确认当前到底有没有 Harness 在执行。"
    ),
    tags=["analysis"],
)
def get_system_status() -> SystemStatusResponse:
    """查询系统状态：是否有活跃的 Harness 进程。"""
    task = _task_manager.get_active_task()
    if task is None:
        return SystemStatusResponse(
            active_task=None,
            harness_process_alive=False,
            pid=None,
            project_root=str(deps.PROJECT_ROOT),
        )

    pid = task.process_pid
    alive = False
    if pid is not None:
        alive = _is_pid_alive(pid)

    return SystemStatusResponse(
        active_task=ActiveTaskInfo(
            task_id=task.task_id,
            company_id=task.company_id,
            status=task.status.value,
            process_pid=task.process_pid,
            process_pgid=task.process_pgid,
            process_alive=task.process_alive,
            started_at=task.started_at,
        ),
        harness_process_alive=alive,
        pid=pid,
        project_root=str(deps.PROJECT_ROOT),
    )
